"""Varian/Agilent VnmrJ experiment folders (`fid` + `procpar`)."""

import warnings
from pathlib import Path

import nmrglue as ng
import numpy as np

from nmr.core.dataset import Dataset
from nmr.core.io.errors import LoadError


def load(folder: Path) -> Dataset:
    try:
        with warnings.catch_warnings():
            # nmrglue warns when procpar lacks the fields it uses to guess the shape.
            warnings.simplefilter("ignore", UserWarning)
            dic, data = ng.varian.read(str(folder))
        procpar = dic["procpar"]
    except Exception as exc:
        raise LoadError(f"Could not read the Varian/Agilent data: {exc}") from exc
    data = np.squeeze(data)
    if data.ndim != 1:
        raise LoadError(
            "This is an arrayed or multi-dimensional experiment; "
            "only single 1D data is supported so far."
        )

    try:
        obs_freq = float(_value(procpar, "sfrq"))
        sw_hz = float(_value(procpar, "sw"))
    except (KeyError, TypeError, ValueError) as exc:
        raise LoadError("The procpar file lacks the frequency or sweep width.") from exc
    ref_freq = _number(procpar, "reffrq") or obs_freq
    # rfl is the distance of the reference line from the right edge of the spectrum,
    # rfp the shift (in Hz) assigned to that line.
    right_edge_hz = (_number(procpar, "rfp") or 0.0) - (_number(procpar, "rfl") or 0.0)

    return Dataset(
        # VnmrJ stores the FID with the opposite sense of rotation to Bruker and JEOL.
        data=np.conj(data),
        domain="time",
        nucleus=_nucleus(str(_value(procpar, "tn", ""))),
        obs_freq_mhz=obs_freq,
        ref_freq_mhz=ref_freq,
        sw_hz=sw_hz,
        offset_ppm=(right_edge_hz + sw_hz) / ref_freq,
        title=folder.stem if folder.suffix.lower() == ".fid" else folder.name,
        solvent=str(_value(procpar, "solvent", "")),
        source=folder,
        params=dic,
    )


def _value(procpar: dict, name: str, default=None):
    try:
        return procpar[name]["values"][0]
    except (KeyError, IndexError, TypeError):
        if default is None:
            raise KeyError(name) from None
        return default


def _number(procpar: dict, name: str) -> float | None:
    try:
        return float(_value(procpar, name))
    except (KeyError, TypeError, ValueError):
        return None


def _nucleus(name: str) -> str:
    """'H1' -> '1H', 'C13' -> '13C'."""
    letters = name.rstrip("0123456789")
    return name[len(letters) :] + letters
