import hashlib
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from nmr.core.document import Document
from nmr.core.integration import evaluate
from nmr.core.io import LoadError, find_datasets, origin_of
from nmr.core.processing import process

DATA = Path(__file__).parent / "data"


def digest(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def document():
    document = Document()
    yield document
    document.close()


def test_import_copies_and_leaves_originals_untouched(document, bruker_experiment):
    experiment = bruker_experiment("ibuprofen-1h-processed")
    before = digest(experiment)

    entries, errors = document.import_path(experiment)

    assert errors == []
    assert len(entries) == 1 and document.entries == entries
    entry = entries[0]
    assert entry.dataset.domain == "time"
    assert entry.params.lb_hz == 0.3 and entry.params.ph0_deg != 0.0  # phased on import
    assert digest(experiment) == before
    # The data now lives in the document's own workspace, as a complete copy.
    assert experiment not in entry.dataset.source.parents
    assert digest(entry.dataset.source) == before


def test_import_picks_up_every_experiment_in_a_folder(document, bruker_experiment, tmp_path):
    proton = bruker_experiment("ibuprofen-1h-processed")
    carbon = bruker_experiment("ibuprofen-13c-processed")
    sample = tmp_path / "sample"
    sample.mkdir()
    proton.rename(sample / "10")
    carbon.rename(sample / "2")
    (sample / "notes.txt").write_text("ignored")

    assert [p.name for p in find_datasets(sample)] == ["2", "10"]  # natural order
    entries, _ = document.import_path(sample)
    assert [e.dataset.nucleus for e in entries] == ["13C", "1H"]
    assert [e.folder for e in entries] == ["001", "002"]


def test_import_zip_archive_and_jcamp(document, jcamp_dir):
    document.import_path(DATA / "bruker" / "ibuprofen-13c-processed.zip")
    document.import_path(jcamp_dir / "aspirin-1h.dx")

    assert [e.dataset.nucleus for e in document.entries] == ["13C", "1H"]
    assert [e.dataset.domain for e in document.entries] == ["time", "frequency"]
    assert document.entries[1].params == type(document.entries[1].params)()


def test_processed_bruker_data_keeps_the_whole_experiment(document, bruker_experiment):
    experiment = bruker_experiment("ibuprofen-1h-processed")
    assert origin_of(experiment / "pdata" / "1") == (experiment, "pdata/1")
    assert origin_of(experiment / "pdata" / "1" / "1r") == (experiment, "pdata/1")
    assert origin_of(experiment / "fid") == (experiment, "")

    (entry,), _ = document.import_path(experiment / "pdata" / "1")
    assert entry.dataset.domain == "frequency"
    assert entry.load_path == f"{experiment.name}/pdata/1"
    assert (entry.dataset.source.parent.parent / "fid").is_file()


def test_import_errors(document, tmp_path):
    with pytest.raises(LoadError):
        document.import_path(tmp_path / "missing")
    with pytest.raises(LoadError):
        document.import_path(tmp_path)  # empty folder
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip")
    with pytest.raises(LoadError):
        document.import_path(broken)
    assert document.entries == []
    assert list(Path(document._workspace.name).iterdir()) == []


def test_save_and_open_round_trip(document, jcamp_dir, tmp_path):
    document.import_path(DATA / "bruker" / "ibuprofen-1h-processed.zip")
    document.import_path(jcamp_dir / "aspirin-1h.fid.dx")
    first = document.entries[0]
    first.params = replace(first.params, lb_hz=1.5, baseline_order=4, reference_shift_ppm=0.02)
    first.integrals = first.integrals.add(1.0, 0.8).add(2.55, 2.35).with_reference(1, 6.0)
    path = tmp_path / "work.nmrx"

    document.save(path)
    reopened = Document.open(path)

    try:
        assert reopened.path == path and document.path == path
        assert [e.params for e in reopened.entries] == [e.params for e in document.entries]
        assert [e.integrals for e in reopened.entries] == [e.integrals for e in document.entries]
        for old, new in zip(document.entries, reopened.entries, strict=True):
            np.testing.assert_array_equal(new.dataset.data, old.dataset.data)
            assert new.dataset.title == old.dataset.title
        spectrum = process(reopened.entries[0].dataset, reopened.entries[0].params)
        values = [i.value for i in evaluate(spectrum, reopened.entries[0].integrals)]
        assert values[1] == pytest.approx(6.0)

        # Importing into a reopened document must not reuse a folder name.
        (added,), _ = reopened.import_path(jcamp_dir / "jeol-1h.dx")
        assert added.folder == "003"
    finally:
        reopened.close()


def test_project_file_is_a_plain_zip_with_the_original_files(document, tmp_path):
    document.import_path(DATA / "bruker" / "aspirin-1h.zip")
    path = tmp_path / "work.nmrx"
    document.save(path)

    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        state = json.loads(archive.read("001/state.json"))
        saved_fid = archive.read("001/data/1/fid")
    with zipfile.ZipFile(DATA / "bruker" / "aspirin-1h.zip") as original:
        original_fid = original.read("1/fid")

    assert manifest["format"] == "nmr-project" and manifest["version"] == 1
    assert manifest["spectra"] == [
        {"folder": "001", "load": "1", "title": "1H BBI", "nucleus": "1H"}
    ]
    assert state["processing"]["lb_hz"] == 0.3
    assert state["integrals"] == {"ranges": [], "ref_index": 0, "ref_value": 1.0}
    assert "001/data/1/acqus" in names
    assert saved_fid == original_fid  # byte for byte


def test_saving_again_replaces_the_file_and_removed_spectra_are_gone(document, jcamp_dir, tmp_path):
    document.import_path(jcamp_dir / "aspirin-1h.dx")
    document.import_path(jcamp_dir / "jeol-1h.dx")
    path = tmp_path / "work.nmrx"
    document.save(path)

    document.remove(0)
    document.save(path)

    with zipfile.ZipFile(path) as archive:
        assert not any(name.startswith("001/") for name in archive.namelist())
    assert not path.with_name("work.nmrx.tmp").exists()
    reopened = Document.open(path)
    try:
        assert [e.dataset.title for e in reopened.entries] == ["auto"]
    finally:
        reopened.close()


def make_project(tmp_path, manifest, extra=()):
    path = tmp_path / "bad.nmrx"
    with zipfile.ZipFile(path, "w") as archive:
        if manifest is not None:
            archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in extra:
            archive.writestr(name, content)
    return path


def test_open_rejects_foreign_newer_and_damaged_files(tmp_path, jcamp_dir):
    not_zip = tmp_path / "x.nmrx"
    not_zip.write_text("hello")
    with pytest.raises(LoadError, match="not a readable project"):
        Document.open(not_zip)
    with pytest.raises(LoadError, match="not a readable project"):
        Document.open(make_project(tmp_path, None))
    with pytest.raises(LoadError, match="not an nmr project"):
        Document.open(make_project(tmp_path, {"format": "something else"}))
    with pytest.raises(LoadError, match="newer version"):
        Document.open(
            make_project(tmp_path, {"format": "nmr-project", "version": 99, "app_version": "9"})
        )

    def with_spectrum(folder, load):
        return {
            "format": "nmr-project",
            "version": 1,
            "spectra": [{"folder": folder, "load": load}],
        }

    with pytest.raises(LoadError, match="invalid spectrum folder"):
        Document.open(make_project(tmp_path, with_spectrum("../evil", "x")))
    with pytest.raises(LoadError, match="invalid data path"):
        Document.open(make_project(tmp_path, with_spectrum("001", "../../outside.dx")))

    spectrum = (jcamp_dir / "jeol-1h.dx").read_bytes()
    with pytest.raises(LoadError, match="unreadable settings"):
        Document.open(
            make_project(
                tmp_path,
                with_spectrum("001", "a.dx"),
                [("001/data/a.dx", spectrum), ("001/state.json", "{broken")],
            )
        )


def test_open_ignores_settings_from_the_future(tmp_path, jcamp_dir):
    """Unknown keys must not break opening, so newer minor versions stay readable."""
    state = {"processing": {"lb_hz": 2.0, "some_new_option": True}, "brand_new_section": {}}
    path = make_project(
        tmp_path,
        {"format": "nmr-project", "version": 1, "spectra": [{"folder": "001", "load": "a.dx"}]},
        [
            ("001/data/a.dx", (jcamp_dir / "jeol-1h.dx").read_bytes()),
            ("001/state.json", json.dumps(state)),
        ],
    )
    document = Document.open(path)
    try:
        assert document.entries[0].params.lb_hz == 2.0
        assert document.entries[0].integrals.ranges == ()
    finally:
        document.close()
