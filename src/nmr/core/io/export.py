"""Writing spectra in open exchange formats."""

from pathlib import Path

import numpy as np

from nmr import __version__
from nmr.core.dataset import Dataset

JCAMP_VALUES_PER_LINE = 8
JCAMP_MAX_INTEGER = 2**30


def save_jcamp(spectrum: Dataset, path: str | Path) -> None:
    """Write the real part of a spectrum as JCAMP-DX 5.01.

    Uses the plainest variant of the format (uncompressed XYDATA with X in Hz), which
    TopSpin, Mnova and every other NMR program can read.
    """
    if spectrum.domain != "frequency":
        raise ValueError("only spectra can be exported, not FIDs")
    real = spectrum.data.real
    n = real.size
    # Shifts are converted with the same frequency a reader will use to convert back.
    hz = spectrum.ppm_axis * spectrum.ref_freq_mhz
    first_x, last_x = float(hz[0]), float(hz[-1])
    peak = float(np.abs(real).max()) or 1.0
    y_factor = peak / JCAMP_MAX_INTEGER
    integers = np.rint(real / y_factor).astype(np.int64)

    header = [
        ("TITLE", spectrum.title or "Untitled"),
        ("JCAMP-DX", f"5.01  $$ nmr {__version__}"),
        ("DATA TYPE", "NMR SPECTRUM"),
        ("DATA CLASS", "XYDATA"),
        ("ORIGIN", f"nmr {__version__}"),
        ("OWNER", ""),
        (".OBSERVE FREQUENCY", repr(float(spectrum.ref_freq_mhz))),
        (".OBSERVE NUCLEUS", f"^{spectrum.nucleus}"),
        (".SOLVENT NAME", spectrum.solvent),
        ("XUNITS", "HZ"),
        ("YUNITS", "ARBITRARY UNITS"),
        ("XFACTOR", "1"),
        ("YFACTOR", repr(float(y_factor))),
        ("FIRSTX", repr(first_x)),
        ("LASTX", repr(last_x)),
        ("DELTAX", repr((last_x - first_x) / (n - 1))),
        ("MAXY", repr(float(real.max()))),
        ("MINY", repr(float(real.min()))),
        ("NPOINTS", str(n)),
        ("FIRSTY", repr(float(real[0]))),
        ("XYDATA", "(X++(Y..Y))"),
    ]
    lines = [f"##{key}={value}" for key, value in header if value != "" or key == "OWNER"]
    for start in range(0, n, JCAMP_VALUES_PER_LINE):
        values = " ".join(str(v) for v in integers[start : start + JCAMP_VALUES_PER_LINE])
        lines.append(f"{float(hz[start])!r} {values}")
    lines.append("##END=")
    Path(path).write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")


def save_csv(spectrum: Dataset, path: str | Path) -> None:
    """Write shift and intensity as two comma-separated columns."""
    if spectrum.domain != "frequency":
        raise ValueError("only spectra can be exported, not FIDs")
    table = np.column_stack((spectrum.ppm_axis, spectrum.data.real))
    np.savetxt(path, table, delimiter=",", header="ppm,intensity", comments="", fmt="%.10g")
