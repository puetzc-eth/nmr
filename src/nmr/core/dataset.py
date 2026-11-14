"""The in-memory representation of one 1D NMR data set."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

Domain = Literal["time", "frequency"]


@dataclass
class Dataset:
    """A 1D FID (time domain) or spectrum (frequency domain).

    The frequency axis follows the TopSpin convention: `offset_ppm` is the chemical
    shift of the first (leftmost) point, and shifts decrease with the point index.
    """

    data: np.ndarray
    domain: Domain
    nucleus: str
    obs_freq_mhz: float
    """Transmitter frequency (Bruker SFO1)."""
    ref_freq_mhz: float
    """Frequency of 0 ppm (Bruker SF); converts Hz to ppm."""
    sw_hz: float
    offset_ppm: float
    """Shift of the leftmost spectrum point. For a FID: where it will land after FT."""
    group_delay: float = 0.0
    """Digital-filter group delay in points (Bruker FIDs), 0 if none."""
    title: str = ""
    solvent: str = ""
    source: Path | None = None
    params: dict[str, Any] = field(default_factory=dict, repr=False)
    """Raw vendor parameters as read from the file."""

    @property
    def size(self) -> int:
        return self.data.shape[-1]

    @property
    def sw_ppm(self) -> float:
        return self.sw_hz / self.ref_freq_mhz

    @property
    def time_axis(self) -> np.ndarray:
        """Acquisition time of each FID point in seconds."""
        return np.arange(self.size) / self.sw_hz

    @property
    def ppm_axis(self) -> np.ndarray:
        """Chemical shift of each spectrum point, descending."""
        return self.offset_ppm - np.arange(self.size) * (self.sw_ppm / self.size)

    @property
    def x_axis(self) -> np.ndarray:
        return self.time_axis if self.domain == "time" else self.ppm_axis
