"""Reading vendor files into `Dataset` objects."""

import re
from pathlib import Path

from nmr.core.dataset import Dataset
from nmr.core.io import bruker, jcamp, jeol, varian
from nmr.core.io.errors import LoadError

__all__ = ["LoadError", "find_datasets", "load", "origin_of"]

JCAMP_SUFFIXES = {".dx", ".jdx", ".jcamp"}
JEOL_SUFFIXES = {".jdf"}
FILE_SUFFIXES = JCAMP_SUFFIXES | JEOL_SUFFIXES
BRUKER_FID_FILES = {"fid", "acqus", "acqu"}
BRUKER_PROCESSED_FILES = {"1r", "1i", "procs", "proc"}
VARIAN_FILES = {"fid", "procpar"}
IGNORED_FOLDERS = {"__MACOSX"}


def load(path: str | Path) -> Dataset:
    """Load a 1D data set.

    Accepts a Bruker or Varian/Agilent experiment folder (or a file inside one), a
    JCAMP-DX file or a JEOL Delta file.
    """
    path = Path(path)
    if not path.exists():
        raise LoadError(f"Path not found: {path}")

    if path.is_dir():
        if _is_varian(path):
            return varian.load(path)
        return _load_bruker_dir(path)

    name = path.name.lower()
    if path.suffix.lower() in JCAMP_SUFFIXES:
        return jcamp.load(path)
    if path.suffix.lower() in JEOL_SUFFIXES:
        return jeol.load(path)
    if name in VARIAN_FILES and _is_varian(path.parent):
        return varian.load(path.parent)
    if name in BRUKER_FID_FILES:
        return bruker.load_fid(path.parent)
    if name in BRUKER_PROCESSED_FILES:
        return bruker.load_processed(path.parent)
    raise LoadError(f"Unknown file format: {path.name}")


def find_datasets(path: str | Path) -> list[Path]:
    """Everything loadable at or below `path`, in natural order.

    A file or a single experiment folder yields itself. A folder of experiments (a
    Bruker sample folder, an unpacked archive) yields each 1D data set inside it.
    """
    path = Path(path)
    if not path.exists():
        raise LoadError(f"Path not found: {path}")
    if path.is_file() or _is_bruker_dataset(path):
        return [path]

    found: list[Path] = []
    _collect(path, found)
    if not found:
        raise LoadError(f"No 1D NMR data found in {path}.")
    return found


def origin_of(path: str | Path) -> tuple[Path, str]:
    """The original file or folder a data set belongs to, and the path inside it to load.

    Used to keep a complete, unmodified copy of the measurement: for Bruker data that
    is the whole experiment folder, whichever file or sub-folder the user picked.
    """
    path = Path(path)
    if path.is_file():
        name = path.name.lower()
        if name in BRUKER_FID_FILES | VARIAN_FILES:
            return path.parent, ""
        if name in BRUKER_PROCESSED_FILES:
            path = path.parent
        else:
            return path, ""
    if (path / "1r").is_file() and not (path / "fid").is_file() and path.parent.name == "pdata":
        return path.parent.parent, f"pdata/{path.name}"
    return path, ""


def _collect(folder: Path, found: list[Path]) -> None:
    for child in sorted(folder.iterdir(), key=_natural_key):
        if child.is_file():
            if child.suffix.lower() in FILE_SUFFIXES:
                found.append(child)
        elif child.name in IGNORED_FOLDERS:
            continue
        elif (child / "fid").is_file():
            found.append(child)
        elif not (child / "ser").is_file():
            # Not an experiment itself (and not a 2D one): look inside.
            _collect(child, found)


def _is_varian(folder: Path) -> bool:
    return (folder / "procpar").is_file() and (folder / "fid").is_file()


def _is_bruker_dataset(folder: Path) -> bool:
    return any((folder / name).is_file() for name in ("fid", "1r", "ser"))


def _natural_key(path: Path) -> list:
    """Sort '2' before '10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


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
