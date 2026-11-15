from itertools import product

import numpy as np
import pytest

from nmr.core.io import load
from nmr.core.multiplets import (
    Multiplet,
    MultipletSet,
    analyse,
    format_report,
    noise_level,
    pick_peaks,
    recognise,
)
from nmr.core.processing import ProcessingParams, auto_phase, default_params, process
from test_processing import REF_FREQ, synthetic_fid


def first_order(shift_ppm: float, couplings_hz: list[float], nuclei: float = 1.0):
    """Lines of a first-order multiplet as (shift, amplitude) for `synthetic_fid`."""
    lines: dict[float, float] = {}
    for signs in product((-0.5, 0.5), repeat=len(couplings_hz)):
        offset = sum(s * j for s, j in zip(signs, couplings_hz, strict=True))
        ppm = round(shift_ppm + offset / REF_FREQ, 9)
        lines[ppm] = lines.get(ppm, 0.0) + nuclei / 2 ** len(couplings_hz)
    return list(lines.items())


def spectrum_of(*multiplets, noise: float = 0.0):
    lines = [line for multiplet in multiplets for line in multiplet]
    fid = synthetic_fid(lines, n=32768, width_hz=0.8, noise=noise)
    return process(fid, ProcessingParams(lb_hz=0.2))


def one(spectrum, high, low) -> Multiplet:
    (result,) = analyse(spectrum, MultipletSet().add(high, low))
    return result


@pytest.mark.parametrize(
    ("couplings", "pattern", "expected"),
    [
        ([], "s", ()),
        ([7.2], "d", (7.2,)),
        ([7.2, 7.2], "t", (7.2,)),
        ([7.0, 7.0, 7.0], "q", (7.0,)),
        ([6.9] * 4, "quint", (6.9,)),
        ([6.6] * 6, "sept", (6.6,)),
        ([8.4, 2.1], "dd", (8.4, 2.1)),
        ([15.6, 10.3, 2.2], "ddd", (15.6, 10.3, 2.2)),
        ([7.6, 7.6, 1.4], "td", (7.6, 1.4)),
        ([12.9, 4.1, 4.1], "dt", (12.9, 4.1)),
        ([10.2, 6.8, 6.8, 6.8], "dq", (10.2, 6.8)),
    ],
)
def test_first_order_patterns(couplings, pattern, expected):
    spectrum = spectrum_of(first_order(4.0, couplings), noise=0.0005)

    multiplet = one(spectrum, 4.15, 3.85)

    assert multiplet.pattern == pattern
    assert multiplet.couplings_hz == pytest.approx(expected, abs=0.15)
    assert multiplet.shift_ppm == pytest.approx(4.0, abs=0.001)
    assert multiplet.nuclei == 1


def test_roofing_is_tolerated_but_unrelated_lines_are_not():
    hz = np.array([10.0, 2.0, -2.0, -10.0])
    assert recognise(hz, np.array([0.7, 0.8, 1.2, 1.3]), 0.35) == ("dd", (12.0, 8.0))
    # Two singlets that merely sit next to each other are not a doublet.
    assert recognise(np.array([5.0, -5.0]), np.array([1.0, 4.0]), 0.35) == ("m", ())
    # Imperfect intensities still give the quartet.
    quartet = recognise(np.array([10.5, 3.5, -3.5, -10.5]), np.array([1.0, 2.8, 3.1, 1.1]), 0.35)
    assert quartet == ("q", (7.0,))
    # Unevenly spaced lines.
    assert recognise(np.array([9.0, 1.0, -3.0, -9.0]), np.ones(4), 0.35) == ("m", ())
    assert recognise(np.array([]), np.array([]), 0.35) == ("m", ())


def test_overlapping_signals_become_m():
    spectrum = spectrum_of(first_order(4.00, [7.0]), first_order(4.012, [5.0, 3.0]))
    multiplet = one(spectrum, 4.1, 3.9)

    assert multiplet.pattern == "m"
    assert multiplet.couplings_hz == ()
    assert multiplet.shift_ppm == pytest.approx(4.0)  # the middle of the region


def test_nuclei_from_areas():
    spectrum = spectrum_of(
        first_order(1.2, [7.0, 7.0], nuclei=3),
        first_order(4.1, [7.0, 7.0, 7.0], nuclei=2),
        first_order(7.3, [], nuclei=1),
    )
    regions = MultipletSet().add(1.3, 1.1).add(4.2, 4.0).add(7.4, 7.2)

    results = analyse(spectrum, regions)
    assert [(m.pattern, m.nuclei) for m in results] == [("s", 1), ("q", 2), ("t", 3)]

    # With a known area per nucleus (taken from the integrals) the scale is fixed.
    per_nucleus = results[0].area / 2
    assert [m.nuclei for m in analyse(spectrum, regions, per_nucleus)] == [2, 4, 6]


def test_user_overrides():
    spectrum = spectrum_of(first_order(4.0, [7.0, 7.0]))
    regions = MultipletSet().add(4.1, 3.9)

    kept = analyse(spectrum, regions.edited(0, pattern="t", nuclei=5))[0]
    assert (kept.pattern, kept.couplings_hz, kept.nuclei) == (
        "t",
        pytest.approx((7.0,), abs=0.1),
        5,
    )

    changed = analyse(spectrum, regions.edited(0, pattern="br s"))[0]
    assert (changed.pattern, changed.couplings_hz) == ("br s", ())

    restored = analyse(spectrum, regions.edited(0, pattern="m").edited(0, pattern=None))[0]
    assert restored.pattern == "t"


def test_multiplet_set_editing():
    regions = MultipletSet().add(1.0, 1.2).add(7.4, 7.2).add(4.2, 4.0)
    assert [(r.high_ppm, r.low_ppm) for r in regions.regions] == [
        (7.4, 7.2),
        (4.2, 4.0),
        (1.2, 1.0),
    ]
    assert len(regions.add(4.2, 4.0).regions) == 3  # same region twice is one region
    assert [r.high_ppm for r in regions.remove(1).regions] == [7.4, 1.2]
    assert regions.shifted(0.5).regions[0].high_ppm == pytest.approx(7.9)


def test_peak_picking_refines_between_points_and_ignores_noise():
    spectrum = spectrum_of(first_order(4.0, [7.2]), noise=0.002)
    peaks = pick_peaks(spectrum, 4.3, 3.7)

    assert len(peaks) == 2
    shifts = [ppm for ppm, _ in peaks]
    assert shifts == pytest.approx([4.0 + 3.6 / REF_FREQ, 4.0 - 3.6 / REF_FREQ], abs=2e-4)
    assert pick_peaks(spectrum, 9.0, 8.0) == []  # only noise there
    assert noise_level(spectrum.data.real) > 0


def test_report_text_and_html():
    spectrum = spectrum_of(
        first_order(1.21, [7.1, 7.1], nuclei=3),
        first_order(4.12, [7.1, 7.1, 7.1], nuclei=2),
        first_order(7.26, [], nuclei=1),
        first_order(2.50, [7.0]),
        first_order(2.512, [5.0, 3.0]),
    )
    spectrum.solvent = "CDCl3"
    regions = MultipletSet().add(1.3, 1.1).add(4.2, 4.0).add(7.4, 7.2).add(2.6, 2.4)
    results = analyse(spectrum, regions, analyse(spectrum, MultipletSet().add(7.4, 7.2))[0].area)

    assert format_report(spectrum, results) == (
        "¹H NMR (400 MHz, CDCl₃) δ 7.26 (s, 1H), 4.12 (q, J = 7.1 Hz, 2H), "
        "2.60–2.40 (m, 2H), 1.21 (t, J = 7.1 Hz, 3H)."
    )
    html = format_report(spectrum, results, html=True)
    assert html.startswith("<sup>1</sup>H NMR (400 MHz, CDCl<sub>3</sub>) δ 7.26 (s, 1H)")
    assert "<i>J</i> = 7.1 Hz" in html
    assert format_report(spectrum, []) == ""


def test_ibuprofen(bruker_experiment):
    """The textbook assignment of ibuprofen from the real 600 MHz spectrum."""
    fid = load(bruker_experiment("ibuprofen-1h-processed"))
    spectrum = process(fid, auto_phase(fid, default_params(fid)))
    regions = MultipletSet().add(0.96, 0.84).add(1.56, 1.44).add(2.50, 2.40).add(3.76, 3.68)

    methyls, methyl, methylene, methine = reversed(analyse(spectrum, regions))

    assert (methyls.pattern, methyls.nuclei) == ("d", 6)
    assert methyls.couplings_hz == pytest.approx((6.6,), abs=0.15)
    assert (methyl.pattern, methyl.nuclei) == ("d", 3)
    assert methyl.couplings_hz == pytest.approx((7.2,), abs=0.15)
    assert (methylene.pattern, methylene.nuclei) == ("d", 2)
    assert methylene.couplings_hz == pytest.approx((7.2,), abs=0.15)
    assert (methine.pattern, methine.nuclei) == ("q", 1)
    assert methine.couplings_hz == pytest.approx((7.2,), abs=0.15)
    assert methyls.shift_ppm == pytest.approx(0.90, abs=0.03)
