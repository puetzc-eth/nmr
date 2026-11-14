from dataclasses import replace

import numpy as np
import pytest

from nmr.core.dataset import Dataset
from nmr.core.io import load
from nmr.core.processing import (
    ProcessingParams,
    auto_phase,
    default_params,
    fourier_transform,
    polynomial_baseline,
    process,
)

REF_FREQ = 400.0
SW_HZ = 8000.0
CARRIER_PPM = 5.0


def synthetic_fid(
    peaks: list[tuple[float, float]],
    *,
    n: int = 16384,
    width_hz: float = 1.0,
    phase_deg: float = 0.0,
    group_delay: int = 0,
    noise: float = 0.0,
) -> Dataset:
    """A FID with Lorentzian lines given as (shift in ppm, amplitude)."""
    t = np.arange(n) / SW_HZ
    data = np.zeros(n, dtype=complex)
    for ppm, amplitude in peaks:
        offset_hz = (ppm - CARRIER_PPM) * REF_FREQ
        data += amplitude * np.exp(2j * np.pi * offset_hz * t - np.pi * width_hz * t)
    data *= np.exp(1j * np.deg2rad(phase_deg))
    if noise:
        rng = np.random.default_rng(0)
        data += noise * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    if group_delay:
        data = np.concatenate([np.zeros(group_delay, dtype=complex), data[:-group_delay]])
    return Dataset(
        data=data,
        domain="time",
        nucleus="1H",
        obs_freq_mhz=REF_FREQ * (1 + CARRIER_PPM * 1e-6),
        ref_freq_mhz=REF_FREQ,
        sw_hz=SW_HZ,
        offset_ppm=CARRIER_PPM + 0.5 * SW_HZ / REF_FREQ,
        group_delay=float(group_delay),
    )


def peak_ppm(spectrum: Dataset) -> float:
    return float(spectrum.ppm_axis[np.argmax(spectrum.data.real)])


def phase_deg_at(spectrum: Dataset, ppm: float) -> float:
    """Phase of the line at `ppm`; 0 for pure absorption.

    Uses the integral over the line, because the phase of a single point depends on
    where the digital points happen to fall relative to the line centre.
    """
    window = np.abs(spectrum.ppm_axis - ppm) < 0.05
    return float(np.degrees(np.angle(spectrum.data[window].sum())))


def test_peak_lands_at_its_shift():
    spectrum = process(synthetic_fid([(7.26, 1.0)]), ProcessingParams())

    assert spectrum.domain == "frequency"
    assert spectrum.size == 32768
    assert peak_ppm(spectrum) == pytest.approx(7.26, abs=spectrum.sw_ppm / spectrum.size)
    assert phase_deg_at(spectrum, 7.26) == pytest.approx(0.0, abs=1.0)


def test_input_is_not_modified():
    fid = synthetic_fid([(2.0, 1.0)])
    before = fid.data.copy()
    process(fid, ProcessingParams(lb_hz=1.0, ph0_deg=30.0, baseline_order=3))
    np.testing.assert_array_equal(fid.data, before)


def test_zero_fill_factor_sets_size():
    fid = synthetic_fid([(2.0, 1.0)], n=10000)
    assert process(fid, ProcessingParams(zero_fill_factor=1)).size == 16384
    assert process(fid, ProcessingParams(zero_fill_factor=4)).size == 65536


def test_line_broadening_widens_and_preserves_area():
    fid = synthetic_fid([(3.0, 1.0)], width_hz=1.0)
    narrow = process(fid, ProcessingParams())
    broad = process(fid, ProcessingParams(lb_hz=4.0))

    def width_hz(spectrum: Dataset) -> float:
        real = spectrum.data.real
        return (real > real.max() / 2).sum() * spectrum.sw_hz / spectrum.size

    assert width_hz(narrow) == pytest.approx(1.0, abs=0.3)
    assert width_hz(broad) == pytest.approx(5.0, abs=0.3)
    assert broad.data.real.sum() == pytest.approx(narrow.data.real.sum(), rel=0.01)


def test_group_delay_is_compensated():
    plain = process(synthetic_fid([(1.0, 1.0), (8.5, 0.5)]), ProcessingParams())
    delayed = process(synthetic_fid([(1.0, 1.0), (8.5, 0.5)], group_delay=68), ProcessingParams())

    assert phase_deg_at(delayed, 1.0) == pytest.approx(0.0, abs=1.0)
    assert phase_deg_at(delayed, 8.5) == pytest.approx(0.0, abs=1.0)
    assert np.corrcoef(plain.data.real, delayed.data.real)[0, 1] > 0.999


def test_manual_phase_correction():
    fid = synthetic_fid([(4.0, 1.0)], phase_deg=40.0)
    assert phase_deg_at(process(fid, ProcessingParams()), 4.0) == pytest.approx(40.0, abs=1.0)
    corrected = process(fid, ProcessingParams(ph0_deg=-40.0))
    assert phase_deg_at(corrected, 4.0) == pytest.approx(0.0, abs=1.0)


def test_first_order_phase_leaves_pivot_untouched():
    fid = synthetic_fid([(2.0, 1.0), (8.0, 0.8)])
    spectrum = process(fid, ProcessingParams(ph1_deg=200.0, pivot_ppm=2.0))

    assert phase_deg_at(spectrum, 2.0) == pytest.approx(0.0, abs=1.0)
    # 6 ppm of a 20 ppm wide spectrum, towards the left edge: -200° * 6/20.
    assert phase_deg_at(spectrum, 8.0) == pytest.approx(-60.0, abs=2.0)


@pytest.mark.parametrize("phase_deg", [-150.0, -35.0, 80.0, 175.0])
def test_auto_phase_recovers_zero_order_error(phase_deg):
    peaks = [(0.9, 1.0), (1.3, 0.4), (2.4, 0.3), (3.7, 0.6), (7.2, 0.5)]
    fid = synthetic_fid(peaks, phase_deg=phase_deg, noise=0.002)
    params = ProcessingParams(lb_hz=0.3)
    ideal = process(fid, replace(params, ph0_deg=-phase_deg))

    found = auto_phase(fid, params)

    ph0_error = (found.ph0_deg + phase_deg + 180.0) % 360.0 - 180.0
    assert ph0_error == pytest.approx(0.0, abs=3.0)
    assert found.ph1_deg == pytest.approx(0.0, abs=15.0)
    assert found.pivot_ppm == pytest.approx(0.9, abs=0.01)
    assert np.corrcoef(process(fid, found).data.real, ideal.data.real)[0, 1] > 0.999


def test_auto_phase_skips_real_data(jcamp_dir):
    spectrum = load(jcamp_dir / "jeol-1h.dx")
    params = ProcessingParams()
    assert auto_phase(spectrum, params) == params


def test_baseline_correction_removes_polynomial():
    flat = process(synthetic_fid([(2.0, 1.0), (7.0, 0.5)], noise=0.002), ProcessingParams())
    x = np.linspace(-1, 1, flat.size)
    height = flat.data.real.max()
    drift = height * (0.05 + 0.04 * x - 0.06 * x**2)
    bent = replace(flat, data=flat.data + drift)

    corrected = process(bent, ProcessingParams(baseline_order=3))

    residual = corrected.data.real - flat.data.real
    assert np.abs(residual).max() < 0.002 * height
    # Phase and transform settings must be ignored for data that is already a spectrum.
    assert corrected.size == flat.size


def test_baseline_of_empty_spectrum_is_flat():
    assert not polynomial_baseline(np.zeros(1024), 3).any()


def test_reference_shift_moves_axis():
    fid = synthetic_fid([(7.20, 1.0)])
    spectrum = process(fid, ProcessingParams(reference_shift_ppm=0.06))
    assert peak_ppm(spectrum) == pytest.approx(7.26, abs=0.001)


def test_default_line_broadening_depends_on_nucleus(bruker_experiment):
    assert default_params(load(bruker_experiment("ibuprofen-1h-processed"))).lb_hz == 0.3
    assert default_params(load(bruker_experiment("ibuprofen-13c-processed"))).lb_hz == 1.0


@pytest.mark.parametrize(
    ("name", "min_correlation"),
    [("ibuprofen-1h-processed", 0.999), ("ibuprofen-13c-processed", 0.99)],
)
def test_matches_topspin(bruker_experiment, name, min_correlation):
    """Processing a real FID automatically must reproduce TopSpin's own spectrum."""
    experiment = bruker_experiment(name)
    fid = load(experiment)
    reference = load(experiment / "pdata" / "1")
    params = replace(default_params(fid), zero_fill_factor=reference.size // fid.size)

    unphased = fourier_transform(fid, params)
    assert unphased.size == reference.size
    assert np.argmax(np.abs(unphased.data)) == np.argmax(np.abs(reference.data))
    assert np.corrcoef(np.abs(unphased.data), np.abs(reference.data))[0, 1] > 0.999

    spectrum = process(fid, auto_phase(fid, params))
    assert np.corrcoef(spectrum.data.real, reference.data.real)[0, 1] > min_correlation
