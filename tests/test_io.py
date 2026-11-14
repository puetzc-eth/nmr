import numpy as np
import pytest

from nmr.core.io import LoadError, load


def test_bruker_fid(bruker_experiment):
    ds = load(bruker_experiment("ibuprofen-1h-processed"))

    assert ds.domain == "time"
    assert ds.nucleus == "1H"
    assert ds.solvent == "CDCl3"
    assert ds.size == 32768
    assert np.iscomplexobj(ds.data)
    assert ds.obs_freq_mhz == pytest.approx(600.1337, abs=1e-4)
    assert ds.sw_hz == pytest.approx(12335.526, abs=1e-3)
    assert ds.group_delay == pytest.approx(67.987, abs=1e-3)
    assert ds.time_axis[-1] == pytest.approx((ds.size - 1) / ds.sw_hz)
    assert "Ibuprofen" in ds.title


@pytest.mark.parametrize("name", ["ibuprofen-1h-processed", "ibuprofen-13c-processed"])
def test_bruker_fid_axis_matches_topspin(bruker_experiment, name):
    """The ppm axis we predict from the FID must equal the one TopSpin wrote."""
    experiment = bruker_experiment(name)
    fid = load(experiment)
    spectrum = load(experiment / "pdata" / "1")

    assert spectrum.domain == "frequency"
    assert np.iscomplexobj(spectrum.data)
    assert fid.offset_ppm == pytest.approx(spectrum.offset_ppm, abs=1e-4)
    assert fid.sw_ppm == pytest.approx(spectrum.sw_ppm, rel=1e-9)
    assert spectrum.ppm_axis[0] == spectrum.offset_ppm
    assert np.all(np.diff(spectrum.ppm_axis) < 0)


def test_bruker_group_delay_from_table(bruker_experiment):
    """Older data sets have no GRPDLY; it is derived from DSPFVS and DECIM."""
    ds = load(bruker_experiment("aspirin-1h"))
    assert ds.size == 8192
    assert ds.group_delay == pytest.approx(61.0208, abs=1e-3)


def test_bruker_accepts_file_and_parent_folder(bruker_experiment):
    experiment = bruker_experiment("aspirin-1h")
    assert load(experiment / "fid").size == 8192
    assert load(experiment / "acqus").size == 8192
    assert load(experiment.parent).size == 8192


def test_bruker_spectrum_peak_positions(bruker_experiment):
    """Sanity check of the shift axis: CDCl3 carbon triplet at 77 ppm is the right place."""
    ds = load(bruker_experiment("ibuprofen-13c-processed") / "pdata" / "1")
    ppm, real = ds.ppm_axis, ds.data.real
    window = (ppm > 76) & (ppm < 78)
    assert real[window].max() > 20 * np.median(np.abs(real))


def test_jcamp_fid(jcamp_dir):
    ds = load(jcamp_dir / "aspirin-1h.fid.dx")

    assert ds.domain == "time"
    assert ds.nucleus == "1H"
    assert ds.size == 8192
    assert np.iscomplexobj(ds.data)
    assert ds.sw_hz == pytest.approx(4789.272, abs=0.01)
    assert ds.group_delay > 0


def test_jcamp_fid_matches_bruker_original(jcamp_dir, bruker_experiment):
    """The JCAMP export and the Bruker folder are the same measurement."""
    jcamp = load(jcamp_dir / "aspirin-1h.fid.dx")
    original = load(bruker_experiment("aspirin-1h"))

    assert jcamp.sw_hz == pytest.approx(original.sw_hz, rel=1e-5)
    assert jcamp.offset_ppm == pytest.approx(original.offset_ppm, abs=1e-3)
    assert jcamp.group_delay == original.group_delay
    np.testing.assert_allclose(jcamp.data, original.data)


def test_jcamp_bruker_spectrum(jcamp_dir):
    ds = load(jcamp_dir / "aspirin-1h.dx")

    assert ds.domain == "frequency"
    assert ds.size == 32768
    assert ds.offset_ppm == pytest.approx(15.47866)
    assert ds.sw_hz == pytest.approx(4789.272, abs=0.01)
    # Acetyl CH3 of aspirin, the tallest signal.
    assert ds.ppm_axis[np.argmax(ds.data.real)] == pytest.approx(2.35, abs=0.1)


@pytest.mark.parametrize(
    ("name", "left", "right"),
    [("jeol-1h.dx", 15.10, -4.89), ("varian-1h.jdx", 16.09, -0.75)],
)
def test_jcamp_other_vendors(jcamp_dir, name, left, right):
    ds = load(jcamp_dir / name)

    assert ds.domain == "frequency"
    assert ds.nucleus == "1H"
    assert ds.ppm_axis[0] == pytest.approx(left, abs=0.01)
    assert ds.ppm_axis[-1] == pytest.approx(right, abs=0.01)


def test_load_errors(tmp_path):
    with pytest.raises(LoadError):
        load(tmp_path / "missing")
    with pytest.raises(LoadError):
        load(tmp_path)
    unknown = tmp_path / "notes.txt"
    unknown.write_text("hello")
    with pytest.raises(LoadError):
        load(unknown)
