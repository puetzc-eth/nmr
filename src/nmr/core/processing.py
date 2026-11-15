"""Turning a FID into a spectrum.

Processing is non-destructive: the loaded data is never modified. A spectrum is always
recomputed from the original data plus a `ProcessingParams` object, so every setting
can be changed or undone at any time.

Order of operations: apodization -> zero filling -> Fourier transform -> phase
correction -> baseline correction -> referencing. Data that is already in the frequency
domain skips the first three.
"""

from dataclasses import dataclass, replace

import numpy as np
from scipy.ndimage import maximum_filter1d, minimum_filter1d
from scipy.optimize import minimize

from nmr.core.dataset import Dataset

DEFAULT_LINE_BROADENING = {"1H": 0.3, "13C": 1.0}


@dataclass(frozen=True)
class ProcessingParams:
    lb_hz: float = 0.0
    """Exponential line broadening."""
    gb_hz: float = 0.0
    """Gaussian line broadening (full width at half maximum)."""
    zero_fill_factor: int = 2
    """Spectrum size is the next power of two at or above the FID size, times this."""
    ph0_deg: float = 0.0
    ph1_deg: float = 0.0
    """First-order phase: total phase change across the whole spectrum."""
    pivot_ppm: float | None = None
    """Shift (on the referenced axis) where ph1 has no effect. None: spectrum centre."""
    baseline_order: int | None = None
    """Polynomial order of the baseline correction, None to switch it off."""
    reference_shift_ppm: float = 0.0
    """Added to the whole shift axis."""


def default_params(dataset: Dataset) -> ProcessingParams:
    return ProcessingParams(lb_hz=DEFAULT_LINE_BROADENING.get(dataset.nucleus, 0.0))


def process(dataset: Dataset, params: ProcessingParams) -> Dataset:
    """Return the spectrum for `dataset` under `params`. The input is left untouched."""
    spectrum = fourier_transform(dataset, params) if dataset.domain == "time" else dataset
    spectrum = replace(spectrum, offset_ppm=spectrum.offset_ppm + params.reference_shift_ppm)
    data = spectrum.data
    if np.iscomplexobj(data):
        data = data * _phase_factor(spectrum, params.ph0_deg, params.ph1_deg, params.pivot_ppm)
    if params.baseline_order is not None:
        data = data - polynomial_baseline(data.real, params.baseline_order)
    return replace(spectrum, data=data)


def shift_reference(params: ProcessingParams, delta_ppm: float) -> ProcessingParams:
    """Move the shift axis by `delta_ppm`; the phase pivot stays on the same signal."""
    pivot = None if params.pivot_ppm is None else params.pivot_ppm + delta_ppm
    return replace(
        params,
        reference_shift_ppm=params.reference_shift_ppm + delta_ppm,
        pivot_ppm=pivot,
    )


def fourier_transform(fid: Dataset, params: ProcessingParams) -> Dataset:
    """Apodize, zero fill and Fourier transform a FID. No phase correction."""
    data = fid.data.astype(complex)
    n = data.shape[0]

    # The signal really starts at the end of the digital filter's group delay.
    t = np.clip((np.arange(n) - fid.group_delay) / fid.sw_hz, 0.0, None)
    if params.lb_hz or params.gb_hz:
        window = np.exp(-np.pi * params.lb_hz * t)
        window *= np.exp(-((np.pi * params.gb_hz * t) ** 2) / (4 * np.log(2)))
        data *= window
    if not fid.group_delay:
        # Halving the first point avoids a constant baseline offset.
        data[0] *= 0.5

    size = _next_power_of_two(n) * max(1, params.zero_fill_factor)
    spectrum = np.fft.fftshift(np.fft.fft(data, size))
    if fid.group_delay:
        # A delay of d points in time is a linear phase ramp in frequency; undo it.
        frequencies = np.fft.fftshift(np.fft.fftfreq(size))
        spectrum *= np.exp(2j * np.pi * fid.group_delay * frequencies)
    # Highest frequency first, to match the descending ppm axis. The roll puts the
    # Nyquist point at the left edge, where `offset_ppm` is defined.
    spectrum = np.roll(spectrum[::-1], 1)

    return replace(fid, data=spectrum, domain="frequency", group_delay=0.0)


def auto_phase(dataset: Dataset, params: ProcessingParams) -> ProcessingParams:
    """Return `params` with ph0, ph1 and pivot chosen automatically.

    Minimises the entropy of the spectrum's derivative plus a penalty for negative
    intensity (the ACME criterion, Chen et al., J. Magn. Reson. 2002, 158, 164).
    """
    if dataset.domain == "time":
        # The phase does not depend on zero filling, so search on the smallest spectrum.
        spectrum = fourier_transform(dataset, replace(params, zero_fill_factor=1))
    else:
        spectrum = dataset
    data = spectrum.data
    if not np.iscomplexobj(data):
        return params
    data = data / np.abs(data).max()
    n = data.shape[0]
    pivot_index = int(np.argmax(np.abs(data)))
    pivot_ppm = float(spectrum.ppm_axis[pivot_index]) + params.reference_shift_ppm
    ramp = (np.arange(n) - pivot_index) / n

    # Only the neighbourhood of signals says anything about the phase. Most of a
    # spectrum is noise, so leaving it out makes the search several times faster.
    magnitude = np.abs(data)
    near_signal = maximum_filter1d(magnitude, max(16, n // 256)) > 6.0 * np.median(magnitude)
    if 64 < near_signal.sum() < 0.6 * n:
        data, ramp = data[near_signal], ramp[near_signal]

    def score_real(real: np.ndarray) -> float:
        slope = np.abs(np.diff(real))
        p = slope / slope.sum()
        entropy = -np.sum(p * np.log(p + 1e-300))
        negative = real[real < 0]
        return entropy + 1000.0 * np.sum(negative**2)

    def score(phases: np.ndarray) -> float:
        return score_real((data * np.exp(1j * np.deg2rad(phases[0] + phases[1] * ramp))).real)

    # The criterion has local minima, so start from the best points of a coarse grid.
    # The first-order rotation is the expensive part and is shared by a whole grid row.
    grid = []
    for ph1 in range(-360, 361, 60):
        rotated = data * np.exp(1j * np.deg2rad(ph1 * ramp))
        for ph0 in range(0, 360, 20):
            angle = np.deg2rad(ph0)
            real = np.cos(angle) * rotated.real - np.sin(angle) * rotated.imag
            grid.append((score_real(real), ph0, ph1))
    starts = [(ph0, ph1) for _, ph0, ph1 in sorted(grid)[:2]]
    options = {"xatol": 0.05, "fatol": 1e-6}
    best = min(
        (minimize(score, start, method="Nelder-Mead", options=options) for start in starts),
        key=lambda result: result.fun,
    )
    ph0 = (best.x[0] + 180.0) % 360.0 - 180.0
    return replace(
        params,
        ph0_deg=float(ph0),
        ph1_deg=float(best.x[1]),
        pivot_ppm=pivot_ppm,
    )


def polynomial_baseline(real: np.ndarray, order: int) -> np.ndarray:
    """Fit a polynomial through the signal-free regions of a spectrum."""
    n = real.shape[0]
    mask = _signal_free(real)
    x = np.linspace(-1.0, 1.0, n)
    if mask.sum() <= order + 1:
        return np.zeros(n)
    coefficients = np.polynomial.chebyshev.chebfit(x[mask], real[mask], order)
    return np.polynomial.chebyshev.chebval(x, coefficients)


def _signal_free(real: np.ndarray) -> np.ndarray:
    """Mask of points that contain only noise.

    A point counts as baseline if the intensity range in a small window around it is
    not much larger than the typical range, which is set by the noise because most of
    a spectrum is empty.
    """
    window = max(8, real.shape[0] // 512)
    spread = maximum_filter1d(real, window) - minimum_filter1d(real, window)
    mask = spread < 2.0 * np.median(spread)
    # Stay clear of the feet of the peaks.
    return minimum_filter1d(mask.astype(np.uint8), 4 * window).astype(bool)


def _phase_factor(
    spectrum: Dataset, ph0_deg: float, ph1_deg: float, pivot_ppm: float | None
) -> np.ndarray | complex:
    if not ph0_deg and not ph1_deg:
        return 1.0
    n = spectrum.size
    if pivot_ppm is None:
        pivot_index = n / 2
    else:
        pivot_index = (spectrum.offset_ppm - pivot_ppm) / spectrum.sw_ppm * n
    ramp = (np.arange(n) - pivot_index) / n
    return np.exp(1j * np.deg2rad(ph0_deg + ph1_deg * ramp))


def _next_power_of_two(n: int) -> int:
    return 1 << (n - 1).bit_length()
