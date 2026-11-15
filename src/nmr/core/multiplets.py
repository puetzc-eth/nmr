"""Multiplet analysis: peaks in a region, their splitting pattern, coupling constants,
and the report text chemists put into the experimental section.

Pattern recognition handles first-order multiplets: every coupling splits each line in
two, equal couplings pile up into triplets, quartets and so on. Anything that does not
fit such a pattern within tolerance is reported as a multiplet "m" with its shift range.
"""

from dataclasses import dataclass, replace
from itertools import combinations

import numpy as np
from scipy.signal import find_peaks

from nmr.core.dataset import Dataset
from nmr.core.integration import area

MAX_COUPLINGS = 6
"""Most couplings considered; 2**6 = 64 lines is beyond anything resolvable."""
PEAK_THRESHOLD = 0.04
"""Lines below this fraction of the tallest line in the region are ignored."""
NOISE_FACTOR = 5.0
INTENSITY_TOLERANCE = 0.3
"""Allowed deviation of a line's intensity from the ideal pattern, relative."""
MAX_ASYMMETRY = 2.5
"""Largest height ratio of mirror-image lines still accepted as one multiplet."""
MULTIPLICITY_NAMES = {1: "d", 2: "t", 3: "q", 4: "quint", 5: "sext", 6: "sept"}
_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


@dataclass(frozen=True)
class Region:
    """A stretch of the spectrum the user marked as one multiplet."""

    high_ppm: float
    low_ppm: float
    pattern: str | None = None
    """Set when the user overrides the recognised pattern."""
    nuclei: int | None = None
    """Set when the user overrides the number of nuclei."""


@dataclass(frozen=True)
class MultipletSet:
    regions: tuple[Region, ...] = ()

    def add(self, a_ppm: float, b_ppm: float) -> "MultipletSet":
        new = Region(max(a_ppm, b_ppm), min(a_ppm, b_ppm))
        kept = [r for r in self.regions if (r.high_ppm, r.low_ppm) != (new.high_ppm, new.low_ppm)]
        ordered = sorted([*kept, new], key=lambda r: r.high_ppm, reverse=True)
        return MultipletSet(tuple(ordered))

    def remove(self, index: int) -> "MultipletSet":
        return MultipletSet(self.regions[:index] + self.regions[index + 1 :])

    def edited(self, index: int, **changes) -> "MultipletSet":
        """Override pattern or nuclei of one region; None restores the automatic value."""
        regions = list(self.regions)
        regions[index] = replace(regions[index], **changes)
        return MultipletSet(tuple(regions))

    def shifted(self, delta_ppm: float) -> "MultipletSet":
        return MultipletSet(
            tuple(
                replace(r, high_ppm=r.high_ppm + delta_ppm, low_ppm=r.low_ppm + delta_ppm)
                for r in self.regions
            )
        )


@dataclass(frozen=True)
class Multiplet:
    high_ppm: float
    low_ppm: float
    shift_ppm: float
    """Centre of the multiplet."""
    pattern: str
    """'s', 'd', 't', 'dd', 'td', ... or 'm' if no first-order pattern fits."""
    couplings_hz: tuple[float, ...]
    """One value per letter of the pattern, largest first. Empty for 's' and 'm'."""
    peaks_ppm: tuple[float, ...]
    area: float
    nuclei: int


# ---- peaks ----------------------------------------------------------------------------


def noise_level(real: np.ndarray) -> float:
    """Standard deviation of the noise, estimated robustly.

    Signals occupy only a small part of a spectrum, so the median absolute deviation
    of all points is set by the noise alone. (Differences between neighbouring points
    would underestimate it: line broadening and zero filling make them correlated.)
    """
    if real.size < 3:
        return 0.0
    return float(1.4826 * np.median(np.abs(real - np.median(real))))


def pick_peaks(spectrum: Dataset, high_ppm: float, low_ppm: float) -> list[tuple[float, float]]:
    """Lines between two shifts as (shift, height), from high to low shift.

    Positions are refined between the data points with a parabola through the top
    three points of each line.
    """
    real = spectrum.data.real
    axis = spectrum.ppm_axis
    inside = np.flatnonzero((axis <= high_ppm) & (axis >= low_ppm))
    if inside.size < 3:
        return []
    start, stop = inside[0], inside[-1] + 1
    segment = real[start:stop]
    threshold = max(PEAK_THRESHOLD * float(segment.max()), NOISE_FACTOR * noise_level(real))
    indices, _ = find_peaks(segment, height=threshold, prominence=0.5 * threshold)

    step = spectrum.sw_ppm / spectrum.size
    peaks = []
    for index in indices:
        offset, height = 0.0, float(segment[index])
        if 0 < index < segment.size - 1:
            left, centre, right = segment[index - 1 : index + 2]
            curvature = left - 2 * centre + right
            if curvature < 0:
                offset = 0.5 * (left - right) / curvature
                height = float(centre - 0.25 * (left - right) * offset)
        peaks.append((float(axis[start + index] - offset * step), height))
    return peaks


# ---- pattern recognition ----------------------------------------------------------------


def recognise(
    positions_hz: np.ndarray, heights: np.ndarray, tolerance_hz: float
) -> tuple[str, tuple[float, ...]]:
    """Splitting pattern and coupling constants of a set of lines.

    Tries to explain the lines with n couplings for increasing n. With n couplings a
    multiplet consists of 2**n component lines of equal intensity, some of which
    coincide. The couplings are read off the outermost components (Hoye's method,
    J. Org. Chem. 1994, 59, 4096), and the multiplet rebuilt from them must reproduce
    every observed line.
    """
    order = np.argsort(positions_hz)[::-1]
    positions = np.asarray(positions_hz, dtype=float)[order]
    heights = np.asarray(heights, dtype=float)[order]
    if positions.size == 0:
        return "m", ()
    if positions.size == 1:
        return "s", ()

    if np.max(heights / heights[::-1]) > MAX_ASYMMETRY:
        return "m", ()
    # Second-order "roofing" tilts a multiplet; averaging mirror-image lines removes it.
    symmetric = 0.5 * (heights + heights[::-1])
    for n in range(1, MAX_COUPLINGS + 1):
        if 2**n < positions.size:
            continue
        units = symmetric / symmetric.sum() * 2**n
        counts = np.rint(units).astype(int)
        if counts.min() < 1 or counts.sum() != 2**n:
            continue
        if np.max(np.abs(units - counts) / counts) > INTENSITY_TOLERANCE:
            continue
        couplings = _couplings_from_components(np.repeat(positions, counts), n)
        if couplings is None or min(couplings) <= tolerance_hz:
            continue
        if _reproduces(couplings, positions, counts, tolerance_hz):
            return _name(couplings, tolerance_hz)
    return "m", ()


def _couplings_from_components(components: np.ndarray, n: int) -> list[float] | None:
    """Hoye's method on the 2**n unit components, sorted from high to low frequency.

    The distance from the first component to the next unexplained one is a coupling.
    Components that are sums of couplings already found are explained and skipped.
    """
    remaining = list(components[1:] - components[0])  # all negative or zero
    couplings: list[float] = []
    while len(couplings) < n:
        if not remaining:
            return None
        coupling = -remaining.pop(0)
        # Every sum of the new coupling with a subset of the earlier ones is explained.
        for size in range(1, len(couplings) + 1):
            for subset in combinations(couplings, size):
                expected = -(coupling + sum(subset))
                if not remaining:
                    return None
                nearest = min(range(len(remaining)), key=lambda i: abs(remaining[i] - expected))
                remaining.pop(nearest)
        couplings.append(coupling)
    return couplings


def _reproduces(
    couplings: list[float], positions: np.ndarray, counts: np.ndarray, tolerance_hz: float
) -> bool:
    """Whether a multiplet built from `couplings` has the observed lines and intensities."""
    centre = 0.5 * (positions[0] + positions[-1])
    lines = np.array([centre])
    for coupling in couplings:
        lines = np.concatenate((lines + coupling / 2, lines - coupling / 2))
    nearest = np.abs(lines[:, None] - positions[None, :]).argmin(axis=1)
    if np.any(np.abs(lines - positions[nearest]) > tolerance_hz):
        return False
    return bool(np.array_equal(np.bincount(nearest, minlength=positions.size), counts))


def _name(couplings: list[float], tolerance_hz: float) -> tuple[str, tuple[float, ...]]:
    """Group equal couplings: two equal ones make a triplet, three a quartet, ..."""
    groups: list[list[float]] = []
    for coupling in sorted(couplings, reverse=True):
        if groups and abs(groups[-1][-1] - coupling) <= max(tolerance_hz, 0.08 * coupling):
            groups[-1].append(coupling)
        else:
            groups.append([coupling])
    if any(len(group) not in MULTIPLICITY_NAMES for group in groups):
        return "m", ()
    # By convention the larger coupling comes first: "td" is a triplet of doublets
    # whose triplet coupling is the larger one.
    return (
        "".join(MULTIPLICITY_NAMES[len(group)] for group in groups),
        tuple(float(np.mean(group)) for group in groups),
    )


# ---- analysis -------------------------------------------------------------------------


def analyse(
    spectrum: Dataset, multiplets: MultipletSet, area_per_nucleus: float | None = None
) -> list[Multiplet]:
    """Evaluate every marked region.

    `area_per_nucleus` converts areas into numbers of nuclei. Without it the smallest
    multiplet counts as one nucleus.
    """
    areas = [area(spectrum, r.high_ppm, r.low_ppm) for r in multiplets.regions]
    positive = [a for a in areas if a > 0]
    if area_per_nucleus is None or area_per_nucleus <= 0:
        area_per_nucleus = min(positive) if positive else 1.0

    resolution_hz = spectrum.sw_hz / spectrum.size
    tolerance_hz = max(0.35, 1.5 * resolution_hz)
    results = []
    for region, region_area in zip(multiplets.regions, areas, strict=True):
        peaks = pick_peaks(spectrum, region.high_ppm, region.low_ppm)
        shifts = np.array([ppm for ppm, _ in peaks])
        pattern, couplings = recognise(
            shifts * spectrum.ref_freq_mhz, np.array([h for _, h in peaks]), tolerance_hz
        )
        if region.pattern is not None and region.pattern != pattern:
            # The user knows better; our couplings belong to the pattern we saw.
            pattern, couplings = region.pattern, ()
        if pattern == "m" or shifts.size == 0:
            centre = 0.5 * (region.high_ppm + region.low_ppm)
        else:
            centre = 0.5 * (shifts.max() + shifts.min())
        nuclei = region.nuclei or max(1, round(region_area / area_per_nucleus))
        results.append(
            Multiplet(
                region.high_ppm,
                region.low_ppm,
                float(centre),
                pattern,
                couplings,
                tuple(float(s) for s in shifts),
                region_area,
                int(nuclei),
            )
        )
    return results


# ---- report ---------------------------------------------------------------------------


def format_report(spectrum: Dataset, multiplets: list[Multiplet], *, html: bool = False) -> str:
    """The multiplet list in the style of the ACS journals, e.g.

    ¹H NMR (400 MHz, CDCl₃) δ 7.21 (d, J = 8.1 Hz, 2H), 3.71 (q, J = 7.2 Hz, 1H).

    With `html` the J is set in italics and isotope and solvent numbers are real
    super- and subscripts, so the text pastes correctly into a word processor.
    """
    if not multiplets:
        return ""
    digits = len(spectrum.nucleus) - len(spectrum.nucleus.lstrip("0123456789"))
    mass, element = spectrum.nucleus[:digits], spectrum.nucleus[digits:]
    decimals = 2 if element in ("H", "F") else 1
    j_symbol = "<i>J</i>" if html else "J"

    if html:
        nucleus = f"<sup>{mass}</sup>{element}"
        solvent = "".join(f"<sub>{c}</sub>" if c.isdigit() else c for c in spectrum.solvent)
    else:
        nucleus = mass.translate(_SUPERSCRIPT) + element
        solvent = spectrum.solvent.translate(_SUBSCRIPT)
    conditions = f"{round(spectrum.obs_freq_mhz)} MHz" + (f", {solvent}" if solvent else "")

    entries = []
    for m in sorted(multiplets, key=lambda m: m.shift_ppm, reverse=True):
        if m.pattern == "m":
            shift = f"{m.high_ppm:.{decimals}f}–{m.low_ppm:.{decimals}f}"
        else:
            shift = f"{m.shift_ppm:.{decimals}f}"
        details = [m.pattern]
        if m.couplings_hz:
            details.append(f"{j_symbol} = {', '.join(f'{j:.1f}' for j in m.couplings_hz)} Hz")
        details.append(f"{m.nuclei}{element}")
        entries.append(f"{shift} ({', '.join(details)})")
    return f"{nucleus} NMR ({conditions}) δ {', '.join(entries)}."
