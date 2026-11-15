"""JEOL and Varian/Agilent import, JCAMP-DX and CSV export."""

from dataclasses import replace
from pathlib import Path

import nmrglue as ng
import numpy as np
import pytest

from nmr.core.document import Document
from nmr.core.io import LoadError, find_datasets, load, origin_of
from nmr.core.io.export import save_csv, save_jcamp
from nmr.core.io.jeol import _group_delay
from nmr.core.processing import ProcessingParams, auto_phase, default_params, process

DATA = Path(__file__).parent / "data"
JEOL_FILE = DATA / "jeol" / "rutin-1h.jdf"

PROCPAR = """sfrq 1 1 1000 0 0 2 1 11 1 64
1 399.95
0
reffrq 1 1 1000 0 0 2 1 11 1 64
1 399.948
0
sw 1 1 1e9 0 0 2 1 0 1 64
1 6400.0
0
rfl 1 1 1e9 -1e9 0 2 1 0 1 64
1 800.0
0
rfp 1 1 1e9 -1e9 0 2 1 0 1 64
1 0.0
0
tn 2 2 4 0 0 2 1 11 1 64
1 "H1"
0
solvent 2 2 20 0 0 2 1 0 1 64
1 "CDCl3"
0
"""


# ---- JEOL -------------------------------------------------------------------------------


def test_jeol_fid():
    ds = load(JEOL_FILE)

    assert ds.domain == "time"
    assert ds.nucleus == "1H"
    assert ds.solvent == "DMSO-D6"
    assert ds.title == "Rutin_RUTI01_3080u200u"
    assert ds.size == 32768 and np.iscomplexobj(ds.data)
    assert ds.ref_freq_mhz == pytest.approx(399.7822, abs=1e-4)
    assert ds.sw_hz == pytest.approx(10016.03, abs=0.01)
    # Two filter stages of order 54 and 73, decimating by 8 and 2.
    assert ds.group_delay == pytest.approx(53 / 2 / 16 + 72 / 2 / 2)
    assert np.argmax(np.abs(ds.data)) == pytest.approx(ds.group_delay, abs=1)


def test_jeol_matches_the_spectrum_processed_by_jeol(jcamp_dir):
    """Our processing of the raw file must agree with JEOL's own export of it."""
    fid = load(JEOL_FILE)
    reference = load(jcamp_dir / "rutin-1h.jdx")

    spectrum = process(fid, auto_phase(fid, default_params(fid)))

    ours = np.interp(reference.ppm_axis[::-1], spectrum.ppm_axis[::-1], spectrum.data.real[::-1])
    assert np.corrcoef(ours[::-1], reference.data.real)[0, 1] > 0.95
    tallest = spectrum.ppm_axis[np.argmax(spectrum.data.real)]
    assert tallest == pytest.approx(reference.ppm_axis[np.argmax(reference.data.real)], abs=0.002)


@pytest.mark.parametrize(
    ("orders", "factors", "expected"),
    [
        ("25473", "82", 53 / 2 / 16 + 72 / 2 / 2),
        ("2 54 73", "8 2", 53 / 2 / 16 + 72 / 2 / 2),
        ("1 65", "4", 64 / 2 / 4),
    ],
)
def test_jeol_group_delay_formats(orders, factors, expected):
    params = {"digital_filter": "TRUE", "orders": orders, "factors": factors}
    assert _group_delay(params, np.zeros(8, dtype=complex)) == pytest.approx(expected)


def test_jeol_group_delay_fallbacks():
    fid = np.zeros(64, dtype=complex)
    fid[17] = 1.0
    assert _group_delay({"digital_filter": "FALSE"}, fid) == 0.0
    # Unreadable filter description: fall back to where the signal starts.
    assert _group_delay({"digital_filter": "TRUE", "orders": "?", "factors": "?"}, fid) == 17.0


def test_jeol_file_is_imported_into_a_document(tmp_path):
    assert origin_of(JEOL_FILE) == (JEOL_FILE, "")
    document = Document()
    try:
        (entry,), errors = document.import_path(JEOL_FILE)
        assert errors == [] and entry.dataset.nucleus == "1H"
        document.save(tmp_path / "jeol.nmrx")
        reopened = Document.open(tmp_path / "jeol.nmrx")
        np.testing.assert_array_equal(reopened.entries[0].dataset.data, entry.dataset.data)
        reopened.close()
    finally:
        document.close()


# ---- Varian / Agilent -------------------------------------------------------------------


@pytest.fixture
def varian_experiment(tmp_path):
    """A VnmrJ folder with two lines at 7.26 and 1.50 ppm (amplitudes 2 : 1).

    Written with nmrglue. There is no freely licensed real Varian data in the test set
    yet, so this checks our reading of the parameters, not the instrument itself.
    """
    n, sw, reffrq = 8192, 6400.0, 399.948
    right_edge_ppm = (0.0 - 800.0) / reffrq
    centre_ppm = right_edge_ppm + sw / 2 / reffrq
    t = np.arange(n) / sw
    fid = np.zeros(n, dtype=complex)
    for ppm, amplitude in ((7.26, 2.0), (1.50, 1.0)):
        offset_hz = (ppm - centre_ppm) * reffrq
        # VnmrJ convention: a line left of the centre rotates with negative frequency.
        fid += amplitude * np.exp(-2j * np.pi * offset_hz * t - np.pi * 1.0 * t)

    universal = {
        "ndim": 1,
        0: {
            "sw": sw,
            "complex": True,
            "obs": 399.95,
            "car": 0.0,
            "size": n,
            "label": "H1",
            "encoding": "direct",
            "time": True,
            "freq": False,
        },
    }
    converter = ng.convert.converter()
    converter.from_universal(universal, fid.astype("complex64"))
    header, _ = converter.to_varian()
    folder = tmp_path / "sample_PROTON_01.fid"
    folder.mkdir()
    ng.varian.write_fid(str(folder / "fid"), header, fid.astype("complex64"), overwrite=True)
    (folder / "procpar").write_text(PROCPAR)
    _, written = ng.varian.read(str(folder))
    np.testing.assert_allclose(np.squeeze(written), fid, rtol=1e-5, atol=1e-5)
    return folder


def test_varian_fid(varian_experiment):
    ds = load(varian_experiment)

    assert ds.domain == "time"
    assert ds.nucleus == "1H"
    assert ds.solvent == "CDCl3"
    assert ds.title == "sample_PROTON_01"
    assert ds.size == 8192
    assert ds.obs_freq_mhz == 399.95 and ds.ref_freq_mhz == 399.948
    assert ds.sw_hz == 6400.0
    assert ds.group_delay == 0.0
    # Right edge at (rfp - rfl) / reffrq = -2 ppm, 16 ppm wide.
    assert ds.offset_ppm == pytest.approx((6400.0 - 800.0) / 399.948)


def test_varian_lines_land_at_their_shifts(varian_experiment):
    spectrum = process(load(varian_experiment), ProcessingParams())
    ppm, real = spectrum.ppm_axis, spectrum.data.real

    assert ppm[np.argmax(real)] == pytest.approx(7.26, abs=0.002)
    upfield = ppm < 4
    assert ppm[upfield][np.argmax(real[upfield])] == pytest.approx(1.50, abs=0.002)
    assert real.max() / real[upfield].max() == pytest.approx(2.0, rel=0.02)
    assert real.min() > -0.02 * real.max()  # both lines in pure absorption


def test_varian_folder_is_recognised_everywhere(varian_experiment):
    assert load(varian_experiment / "fid").size == 8192
    assert load(varian_experiment / "procpar").size == 8192
    assert find_datasets(varian_experiment) == [varian_experiment]
    assert find_datasets(varian_experiment.parent) == [varian_experiment]
    assert origin_of(varian_experiment / "procpar") == (varian_experiment, "")


def test_varian_without_frequency_is_rejected(varian_experiment):
    (varian_experiment / "procpar").write_text(PROCPAR.split("sw ")[0].split("reffrq")[1])
    with pytest.raises(LoadError):
        load(varian_experiment)


# ---- export -----------------------------------------------------------------------------


@pytest.fixture
def spectrum(jcamp_dir):
    fid = load(jcamp_dir / "aspirin-1h.fid.dx")
    params = replace(auto_phase(fid, default_params(fid)), reference_shift_ppm=0.013)
    return process(fid, params)


def test_jcamp_export_round_trip(spectrum, tmp_path):
    path = tmp_path / "out.jdx"
    save_jcamp(spectrum, path)

    back = load(path)

    assert back.domain == "frequency"
    assert back.nucleus == "1H" and back.solvent == "CDCl3" and back.title == "1H BBI"
    assert back.size == spectrum.size
    np.testing.assert_allclose(back.ppm_axis, spectrum.ppm_axis, atol=1e-9)
    # Intensities are stored as integers scaled to about nine significant digits.
    scale = np.abs(spectrum.data.real).max()
    np.testing.assert_allclose(back.data.real, spectrum.data.real, atol=2e-9 * scale)
    assert back.sw_hz == pytest.approx(spectrum.sw_hz, rel=1e-9)


def test_jcamp_export_is_plain_standard_text(spectrum, tmp_path):
    path = tmp_path / "out.jdx"
    save_jcamp(spectrum, path)
    lines = path.read_text(encoding="ascii").splitlines()

    assert lines[0] == "##TITLE=1H BBI"
    assert lines[1].startswith("##JCAMP-DX=5.01")
    assert "##DATA TYPE=NMR SPECTRUM" in lines
    assert "##XUNITS=HZ" in lines
    assert f"##NPOINTS={spectrum.size}" in lines
    assert lines[-1] == "##END="
    data_start = lines.index("##XYDATA=(X++(Y..Y))") + 1
    first = lines[data_start].split()
    assert float(first[0]) == pytest.approx(spectrum.ppm_axis[0] * spectrum.ref_freq_mhz)
    assert len(first) == 9 and all(v.lstrip("-").isdigit() for v in first[1:])


def test_csv_export(spectrum, tmp_path):
    path = tmp_path / "out.csv"
    save_csv(spectrum, path)

    assert path.read_text().splitlines()[0] == "ppm,intensity"
    table = np.loadtxt(path, delimiter=",", skiprows=1)
    assert table.shape == (spectrum.size, 2)
    np.testing.assert_allclose(table[:, 0], spectrum.ppm_axis, rtol=1e-9)
    np.testing.assert_allclose(table[:, 1], spectrum.data.real, rtol=1e-9)


def test_fids_cannot_be_exported_as_spectra(jcamp_dir, tmp_path):
    fid = load(jcamp_dir / "aspirin-1h.fid.dx")
    with pytest.raises(ValueError):
        save_jcamp(fid, tmp_path / "x.jdx")
    with pytest.raises(ValueError):
        save_csv(fid, tmp_path / "x.csv")
