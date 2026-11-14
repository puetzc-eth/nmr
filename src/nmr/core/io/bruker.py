"""Bruker TopSpin/XWIN-NMR experiment folders."""

from pathlib import Path

import nmrglue as ng

from nmr.core.dataset import Dataset
from nmr.core.io.errors import LoadError


def load_fid(folder: Path) -> Dataset:
    """Load the raw FID from an experiment folder (the one containing `fid` and `acqus`)."""
    try:
        dic, data = ng.bruker.read(str(folder))
    except Exception as exc:
        raise LoadError(f"Bruker-FID konnte nicht gelesen werden: {exc}") from exc
    if data.ndim != 1:
        raise LoadError("Das ist kein 1D-Experiment.")

    acqus = dic["acqus"]
    ref_freq = float(acqus["BF1"])
    obs_freq = float(acqus["SFO1"])
    sw_hz = float(acqus["SW_h"])
    carrier_ppm = (obs_freq - ref_freq) / ref_freq * 1e6
    return Dataset(
        data=data,
        domain="time",
        nucleus=str(acqus.get("NUC1", "")),
        obs_freq_mhz=obs_freq,
        ref_freq_mhz=ref_freq,
        sw_hz=sw_hz,
        offset_ppm=carrier_ppm + 0.5 * sw_hz / ref_freq,
        group_delay=group_delay(acqus),
        title=_title(folder),
        solvent=str(acqus.get("SOLVENT", "")),
        source=folder,
        params=dic,
    )


def load_processed(pdata_folder: Path) -> Dataset:
    """Load a spectrum processed by TopSpin from a `pdata/<n>` folder."""
    try:
        dic, parts = ng.bruker.read_pdata(str(pdata_folder), all_components=True)
    except Exception as exc:
        raise LoadError(f"Bruker-Spektrum konnte nicht gelesen werden: {exc}") from exc
    real = parts[0]
    if real.ndim != 1:
        raise LoadError("Das ist kein 1D-Spektrum.")
    data = real + 1j * parts[1] if len(parts) > 1 else real

    procs = dic["procs"]
    acqus = dic.get("acqus", {})
    ref_freq = float(procs["SF"])
    experiment = pdata_folder.parent.parent
    return Dataset(
        data=data,
        domain="frequency",
        nucleus=str(acqus.get("NUC1", procs.get("AXNUC", ""))),
        obs_freq_mhz=float(acqus.get("SFO1", ref_freq)),
        ref_freq_mhz=ref_freq,
        sw_hz=float(procs["SW_p"]),
        offset_ppm=float(procs["OFFSET"]),
        title=_title(experiment, pdata_folder),
        solvent=str(acqus.get("SOLVENT", "")),
        source=pdata_folder,
        params=dic,
    )


def group_delay(acqus: dict) -> float:
    """Digital-filter group delay in points; 0 for analogue acquisition."""
    grpdly = acqus.get("GRPDLY")
    if grpdly is not None and grpdly > 0:
        return float(grpdly)
    # Older consoles do not store GRPDLY; it follows from the filter version and decimation.
    try:
        return float(ng.bruker.bruker_dsp_table[acqus["DSPFVS"]][acqus["DECIM"]])
    except KeyError:
        return 0.0


def _title(experiment: Path, pdata_folder: Path | None = None) -> str:
    title_file = (pdata_folder or experiment / "pdata" / "1") / "title"
    if title_file.is_file():
        text = title_file.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return " | ".join(line.strip() for line in text.splitlines() if line.strip())
    return experiment.name
