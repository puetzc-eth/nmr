import numpy as np
import pytest

from nmr.core.integration import IntegralSet, area, evaluate, running_integral
from nmr.core.processing import ProcessingParams, process
from test_processing import synthetic_fid


@pytest.fixture
def spectrum():
    """Three lines with areas 3 : 2 : 1."""
    fid = synthetic_fid([(1.0, 3.0), (4.0, 2.0), (7.0, 1.0)], width_hz=1.0)
    return process(fid, ProcessingParams(lb_hz=0.5))


def test_areas_are_proportional_to_the_number_of_nuclei(spectrum):
    integrals = IntegralSet().add(0.5, 1.5).add(3.5, 4.5).add(6.5, 7.5)

    results = evaluate(spectrum, integrals)

    # Ordered like the spectrum: high shift first.
    assert [(r.high_ppm, r.low_ppm) for r in results] == [(7.5, 6.5), (4.5, 3.5), (1.5, 0.5)]
    # The integral drawn first (1 ppm, three nuclei) is the reference with value 1.
    assert [r.value for r in results] == pytest.approx([1 / 3, 2 / 3, 1.0], rel=0.01)
    assert results[0].area > 0


def test_reference_can_be_set_on_any_integral(spectrum):
    integrals = IntegralSet().add(0.5, 1.5).add(3.5, 4.5).add(6.5, 7.5).with_reference(0, 1.0)
    assert [r.value for r in evaluate(spectrum, integrals)] == pytest.approx(
        [1.0, 2.0, 3.0], rel=0.01
    )


def test_reference_follows_its_integral_when_regions_change(spectrum):
    integrals = IntegralSet().add(3.5, 4.5).with_reference(0, 2.0)

    integrals = integrals.add(6.5, 7.5)  # sorts in before the reference
    assert integrals.ranges[integrals.ref_index] == (4.5, 3.5)
    assert evaluate(spectrum, integrals)[0].value == pytest.approx(1.0, rel=0.01)

    integrals = integrals.remove(0)
    assert integrals.ranges == ((4.5, 3.5),)
    assert evaluate(spectrum, integrals)[0].value == pytest.approx(2.0)

    # Removing the reference itself hands the role to the first integral.
    both = integrals.add(0.5, 1.5)
    assert both.remove(both.ref_index).ref_index == 0


def test_area_does_not_depend_on_zero_filling():
    fid = synthetic_fid([(4.0, 1.0)])
    small = process(fid, ProcessingParams(lb_hz=1.0, zero_fill_factor=1))
    large = process(fid, ProcessingParams(lb_hz=1.0, zero_fill_factor=4))
    assert area(large, 4.5, 3.5) == pytest.approx(area(small, 4.5, 3.5), rel=1e-3)


def test_region_order_and_bounds(spectrum):
    assert IntegralSet().add(0.5, 1.5).ranges == ((1.5, 0.5),)
    # Regions outside the spectrum are empty rather than an error.
    assert area(spectrum, 500.0, 400.0) == 0.0
    assert area(spectrum, 1000.0, -1000.0) == pytest.approx(
        spectrum.data.real.sum() * spectrum.sw_ppm / spectrum.size
    )


def test_running_integral_ends_at_the_area(spectrum):
    ppm, running = running_integral(spectrum, 4.5, 3.5)

    assert ppm[0] <= 4.5 and ppm[-1] >= 3.5
    assert np.all(np.diff(ppm) < 0)
    assert running[-1] == pytest.approx(area(spectrum, 4.5, 3.5))
    # A single absorption line: the curve only goes up, half way at the line centre.
    assert np.all(np.diff(running) > -1e-9 * running[-1])
    assert ppm[np.argmin(np.abs(running - running[-1] / 2))] == pytest.approx(4.0, abs=0.01)


def test_shifted_moves_regions():
    integrals = IntegralSet().add(1.0, 2.0).shifted(0.5)
    assert integrals.ranges == ((2.5, 1.5),)


def test_empty_set_and_zero_reference(spectrum):
    assert evaluate(spectrum, IntegralSet()) == []
    empty_region = IntegralSet().add(500.0, 400.0).add(3.5, 4.5)
    assert np.isnan(evaluate(spectrum, empty_region)[1].value)
