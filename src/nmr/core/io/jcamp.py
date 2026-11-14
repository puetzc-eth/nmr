"""JCAMP-DX files (.dx, .jdx) as exported by Bruker, JEOL, Varian/Agilent and others."""

import warnings
from pathlib import Path

import nmrglue as ng
import numpy as np

from nmr.core.dataset import Dataset
from nmr.core.io import bruker
from nmr.core.io.errors import LoadError


def load(path: Path) -> Dataset:
    try:
        with warnings.catch_warnings():
            # nmrglue warns about harmless empty header fields.
            warnings.simplefilter("ignore", UserWarning)
            dic, data = ng.jcampdx.read(str(path))
    except Exception as exc:
        raise LoadError(f"JCAMP-Datei konnte nicht gelesen werden: {exc}") from exc

    # NTUPLES files carry real and imaginary parts, XYDATA files only one array.
    if isinstance(data, list):
        if not data or data[0].ndim != 1:
            raise LoadError("Die JCAMP-Datei enthält keine 1D-Daten.")
        values = data[0] + 1j * data[1] if len(data) > 1 else data[0]
        first, last, x_units = (_ntuple_x(dic, key) for key in ("FIRST", "LAST", "UNITS"))
    else:
        if data.ndim != 1:
            raise LoadError("Die JCAMP-Datei enthält keine 1D-Daten.")
        values = data
        first, last, x_units = (_get(dic, key) for key in ("FIRSTX", "LASTX", "XUNITS"))

    try:
        obs_freq = float(_get(dic, ".OBSERVEFREQUENCY"))
        first, last = float(first), float(last)
    except (TypeError, ValueError) as exc:
        raise LoadError("In der JCAMP-Datei fehlen Angaben zu Messfrequenz oder X-Achse.") from exc

    data_type = (_get(dic, "DATATYPE") or "").upper()
    if "NMR" not in data_type:
        raise LoadError(f"Die JCAMP-Datei enthält keine NMR-Daten ({data_type or 'unbekannt'}).")

    n = values.shape[0]
    span = abs(last - first) * n / (n - 1)
    common = dict(
        nucleus=(_get(dic, ".OBSERVENUCLEUS") or "").lstrip("^"),
        obs_freq_mhz=obs_freq,
        title=_get(dic, "TITLE") or path.stem,
        solvent=_get(dic, ".SOLVENTNAME") or "",
        source=path,
        params=dic,
    )

    if "FID" in data_type:
        # X is the acquisition time in seconds.
        ref_freq = _float(dic, "$BF1") or obs_freq
        sw_hz = n / span
        carrier_ppm = (obs_freq - ref_freq) / ref_freq * 1e6
        return Dataset(
            data=values,
            domain="time",
            ref_freq_mhz=ref_freq,
            sw_hz=sw_hz,
            offset_ppm=carrier_ppm + 0.5 * sw_hz / ref_freq,
            group_delay=_group_delay(dic),
            **common,
        )

    ref_freq = _float(dic, "$SF") or obs_freq
    if first < last:
        values = values[::-1]
    if (x_units or "").strip().upper() == "PPM":
        sw_hz = span * ref_freq
        offset_ppm = max(first, last)
    else:
        sw_hz = span
        offset_ppm = max(first, last) / ref_freq
    # Bruker writes X as Hz relative to the right edge; the true shift is in ##$OFFSET.
    bruker_offset = _float(dic, "$OFFSET")
    if bruker_offset is not None:
        offset_ppm = bruker_offset
    return Dataset(
        data=np.ascontiguousarray(values),
        domain="frequency",
        ref_freq_mhz=ref_freq,
        sw_hz=sw_hz,
        offset_ppm=offset_ppm,
        **common,
    )


def _get(dic: dict, key: str) -> str | None:
    value = dic.get(key)
    return value[0].strip() if value else None


def _float(dic: dict, key: str) -> float | None:
    try:
        return float(_get(dic, key))
    except (TypeError, ValueError):
        return None


def _ntuple_x(dic: dict, key: str) -> str | None:
    """First (X) entry of a comma-separated NTUPLES header line."""
    value = _get(dic, key)
    return value.split(",")[0].strip() if value else None


def _group_delay(dic: dict) -> float:
    params = {}
    for name in ("GRPDLY", "DSPFVS", "DECIM"):
        value = _float(dic, f"${name}")
        if value is not None:
            params[name] = value if name == "GRPDLY" else int(value)
    return bruker.group_delay(params)
