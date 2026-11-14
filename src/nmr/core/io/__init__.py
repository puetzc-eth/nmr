"""Reading vendor files into `Dataset` objects."""

from pathlib import Path

from nmr.core.dataset import Dataset
from nmr.core.io import bruker, jcamp
from nmr.core.io.errors import LoadError

__all__ = ["LoadError", "load"]

JCAMP_SUFFIXES = {".dx", ".jdx", ".jcamp"}
BRUKER_FID_FILES = {"fid", "acqus", "acqu"}
BRUKER_PROCESSED_FILES = {"1r", "1i", "procs", "proc"}


def load(path: str | Path) -> Dataset:
    """Load a 1D data set from a Bruker folder (or a file inside one) or a JCAMP-DX file."""
    path = Path(path)
    if not path.exists():
        raise LoadError(f"Path not found: {path}")

    if path.is_dir():
        return _load_bruker_dir(path)

    name = path.name.lower()
    if path.suffix.lower() in JCAMP_SUFFIXES:
        return jcamp.load(path)
    if name in BRUKER_FID_FILES:
        return bruker.load_fid(path.parent)
    if name in BRUKER_PROCESSED_FILES:
        return bruker.load_processed(path.parent)
    raise LoadError(f"Unknown file format: {path.name}")


def _load_bruker_dir(folder: Path) -> Dataset:
    if (folder / "fid").is_file():
        return bruker.load_fid(folder)
    if (folder / "1r").is_file():
        return bruker.load_processed(folder)
    if (folder / "ser").is_file():
        raise LoadError("This is a 2D experiment; only 1D data is supported so far.")

    # A sample folder holding numbered experiments: open it if there is exactly one.
    experiments = sorted(p for p in folder.iterdir() if (p / "fid").is_file())
    if len(experiments) == 1:
        return bruker.load_fid(experiments[0])
    if experiments:
        names = ", ".join(p.name for p in experiments)
        raise LoadError(
            f"The folder contains several experiments ({names}). Please open one of them."
        )
    raise LoadError(f"No Bruker data (fid or 1r) found in {folder}.")
