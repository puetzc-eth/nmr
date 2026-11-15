"""JEOL Delta files (.jdf)."""

from pathlib import Path

import nmrglue as ng
import numpy as np

from nmr.core.dataset import Dataset
from nmr.core.io.errors import LoadError


def load(path: Path) -> Dataset:
    try:
        dic, data = ng.jeol.read(str(path))
        header, params = dic["header"], dic["parameters"]
    except Exception as exc:
        raise LoadError(f"Could not read the JEOL file: {exc}") from exc
    data = np.squeeze(data)
    if data.ndim != 1 or header.get("data_dimension_number", 1) != 1:
        raise LoadError("This is not a 1D experiment; only 1D data is supported so far.")
    if not np.iscomplexobj(data):
        raise LoadError("This JEOL file holds a processed spectrum, which is not supported yet.")

    try:
        ref_freq = float(params["x_freq"]) / 1e6
        sw_hz = float(params["x_sweep"])
        carrier_ppm = float(params["x_offset"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LoadError("The JEOL file lacks the frequency or sweep width.") from exc

    return Dataset(
        data=data,
        domain="time",
        nucleus=_nucleus(str(params.get("x_domain", ""))),
        obs_freq_mhz=ref_freq * (1 + carrier_ppm * 1e-6),
        ref_freq_mhz=ref_freq,
        sw_hz=sw_hz,
        offset_ppm=carrier_ppm + 0.5 * sw_hz / ref_freq,
        group_delay=_group_delay(params, data),
        title=str(header.get("title") or path.stem).strip(),
        solvent=str(params.get("solvent", "")).strip(),
        source=path,
        params=dic,
    )


def _nucleus(domain: str) -> str:
    """JEOL names nuclei '1H', '13C' or 'Proton', 'Carbon13'."""
    names = {"proton": "1H", "carbon13": "13C", "fluorine19": "19F", "phosphorus31": "31P"}
    return names.get(domain.strip().lower(), domain.strip())


def _group_delay(params: dict, data: np.ndarray) -> float:
    """Delay of the digital filter in points.

    The filter is a chain of decimating stages. `orders` holds the number of stages
    followed by the order of each, `factors` the decimation factor of each. A stage of
    order n delays by (n - 1) / 2 of its input samples, which is then scaled down by
    the decimation of that stage and all later ones.
    """
    if str(params.get("digital_filter", "")).strip().upper() not in ("TRUE", "1"):
        return 0.0
    try:
        orders = _numbers(params["orders"])
        stages, orders = orders[0], orders[1:]
        if len(orders) != stages:
            # Written without separators, e.g. '25473' for two stages of order 54 and 73.
            digits = "".join(str(n) for n in orders)
            width = len(digits) // stages
            orders = [int(digits[i * width : (i + 1) * width]) for i in range(stages)]
        factors = _numbers(params["factors"])
        if len(factors) != stages:
            factors = [int(d) for d in "".join(str(n) for n in factors)]
        if len(factors) != stages or len(orders) != stages:
            raise ValueError("orders and factors do not match")
        delay = 0.0
        for stage in range(stages):
            delay += (orders[stage] - 1) / 2 / np.prod(factors[stage:])
        return float(delay)
    except (KeyError, ValueError, ZeroDivisionError, IndexError):
        # Unknown layout: the signal starts where the FID is largest.
        return float(np.argmax(np.abs(data[:256])))


def _numbers(value) -> list[int]:
    """'2 54 73' -> [2, 54, 73]; a bare number yields its leading digit and the rest."""
    parts = str(value).split()
    if len(parts) == 1 and len(parts[0]) > 1:
        return [int(parts[0][0]), int(parts[0][1:])]
    return [int(part) for part in parts]
