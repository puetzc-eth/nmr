"""Integrals: areas under regions of a spectrum, normalised to a reference integral."""

from dataclasses import dataclass, replace

import numpy as np

from nmr.core.dataset import Dataset


@dataclass(frozen=True)
class IntegralSet:
    """The integration regions of one spectrum and how their values are normalised.

    Regions are (high ppm, low ppm) pairs, ordered left to right as in the spectrum.
    The integral at `ref_index` is defined to have the value `ref_value`; all others
    are scaled relative to it.
    """

    ranges: tuple[tuple[float, float], ...] = ()
    ref_index: int = 0
    ref_value: float = 1.0

    def add(self, a_ppm: float, b_ppm: float) -> "IntegralSet":
        """Add a region. The reference stays on the integral it was on."""
        new = (max(a_ppm, b_ppm), min(a_ppm, b_ppm))
        reference = self.ranges[self.ref_index] if self.ranges else new
        ranges = tuple(sorted({*self.ranges, new}, reverse=True))
        return replace(self, ranges=ranges, ref_index=ranges.index(reference))

    def remove(self, index: int) -> "IntegralSet":
        """Remove a region. If it was the reference, the first integral takes over."""
        ranges = self.ranges[:index] + self.ranges[index + 1 :]
        if index == self.ref_index:
            return replace(self, ranges=ranges, ref_index=0)
        shift = 1 if index < self.ref_index else 0
        return replace(self, ranges=ranges, ref_index=self.ref_index - shift)

    def with_reference(self, index: int, value: float) -> "IntegralSet":
        """Define the integral at `index` to have `value`."""
        return replace(self, ref_index=index, ref_value=value)

    def shifted(self, delta_ppm: float) -> "IntegralSet":
        """Move all regions, e.g. after the spectrum was re-referenced."""
        ranges = tuple((high + delta_ppm, low + delta_ppm) for high, low in self.ranges)
        return replace(self, ranges=ranges)


@dataclass(frozen=True)
class Integral:
    high_ppm: float
    low_ppm: float
    area: float
    """Absolute area in intensity × ppm; independent of zero filling."""
    value: float
    """Area relative to the reference integral."""


def area(spectrum: Dataset, high_ppm: float, low_ppm: float) -> float:
    """Area under the real part between two shifts."""
    real = spectrum.data.real[_slice(spectrum, high_ppm, low_ppm)]
    return float(real.sum() * spectrum.sw_ppm / spectrum.size)


def evaluate(spectrum: Dataset, integrals: IntegralSet) -> list[Integral]:
    """Compute area and normalised value of every region."""
    areas = [area(spectrum, high, low) for high, low in integrals.ranges]
    if not areas:
        return []
    reference = areas[integrals.ref_index]
    scale = integrals.ref_value / reference if reference else float("nan")
    return [
        Integral(high, low, a, a * scale)
        for (high, low), a in zip(integrals.ranges, areas, strict=True)
    ]


def running_integral(
    spectrum: Dataset, high_ppm: float, low_ppm: float
) -> tuple[np.ndarray, np.ndarray]:
    """Shift axis and cumulative area across a region, for drawing the integral curve."""
    region = _slice(spectrum, high_ppm, low_ppm)
    step = spectrum.sw_ppm / spectrum.size
    return spectrum.ppm_axis[region], np.cumsum(spectrum.data.real[region]) * step


def _slice(spectrum: Dataset, high_ppm: float, low_ppm: float) -> slice:
    """Points between two shifts; the ppm axis is descending."""
    to_index = spectrum.size / spectrum.sw_ppm
    start = int(np.ceil((spectrum.offset_ppm - high_ppm) * to_index))
    stop = int(np.floor((spectrum.offset_ppm - low_ppm) * to_index)) + 1
    return slice(max(start, 0), min(max(stop, 0), spectrum.size))
