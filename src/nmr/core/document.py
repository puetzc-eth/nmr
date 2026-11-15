"""A document: several spectra with their processing and analysis, saved as one file.

The project file (`.nmrx`) is a plain ZIP archive that anyone can open:

    manifest.json           format version and the list of spectra
    001/data/...            unmodified copy of the original instrument files
    001/state.json          processing settings and analysis results for that spectrum
    002/...

Only the original data and the settings are stored. Spectra are recomputed from them
when the file is opened, so nothing saved can go stale, and the original files can be
taken out of the archive and opened in any other NMR program.

Importing copies the original files into a private workspace folder. The files the
user pointed at are only ever read.
"""

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import numpy as np

from nmr import __version__
from nmr.core.dataset import Dataset
from nmr.core.integration import IntegralSet
from nmr.core.io import LoadError, find_datasets, load, origin_of
from nmr.core.processing import ProcessingParams, auto_phase, default_params

PROJECT_SUFFIX = ".nmrx"
FORMAT_NAME = "nmr-project"
FORMAT_VERSION = 1
MANIFEST = "manifest.json"
STATE = "state.json"
ARCHIVE_SUFFIXES = {".zip"}


@dataclass
class Entry:
    """One spectrum of a document."""

    dataset: Dataset
    """The data as loaded from the original files; never modified."""
    params: ProcessingParams
    integrals: IntegralSet
    folder: str
    """Name of this entry's folder in the workspace and in the project file."""
    load_path: str
    """Path below `<folder>/data` that is handed to the loader."""
    runtime: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)
    """Scratch space for the application (caches, undo history). Never saved."""


class Document:
    def __init__(self) -> None:
        self.entries: list[Entry] = []
        self.path: Path | None = None
        """The project file this document was opened from or last saved to."""
        self._workspace = tempfile.TemporaryDirectory(prefix="nmr-")
        self._root = Path(self._workspace.name)
        self._counter = 0

    def close(self) -> None:
        """Delete the workspace. The document must not be used afterwards."""
        self._workspace.cleanup()

    # ---- importing ----------------------------------------------------------------

    def import_path(self, path: str | Path) -> tuple[list[Entry], list[str]]:
        """Add every 1D data set found at `path` (file, folder or ZIP archive).

        Returns the new entries and a message for each data set that could not be
        read. Raises LoadError if nothing at all could be imported.
        """
        path = Path(path)
        if path.is_file() and path.suffix.lower() in ARCHIVE_SUFFIXES:
            with tempfile.TemporaryDirectory(prefix="nmr-import-") as unpacked:
                _extract(path, Path(unpacked))
                return self._import_all(find_datasets(unpacked), label=path.name)
        return self._import_all(find_datasets(path), label=str(path))

    def _import_all(self, sources: list[Path], label: str) -> tuple[list[Entry], list[str]]:
        added, errors = [], []
        for source in sources:
            try:
                added.append(self._import_one(source))
            except LoadError as exc:
                errors.append(f"{source.name}: {exc}")
        if not added:
            detail = errors[0] if len(errors) == 1 else f"no readable 1D data in {label}"
            raise LoadError(detail)
        return added, errors

    def _import_one(self, source: Path) -> Entry:
        origin, inner = origin_of(source)
        self._counter += 1
        folder = f"{self._counter:03d}"
        data_dir = self._root / folder / "data"
        data_dir.mkdir(parents=True)
        if origin.is_dir():
            shutil.copytree(origin, data_dir / origin.name)
        else:
            shutil.copy2(origin, data_dir / origin.name)
        load_path = f"{origin.name}/{inner}".rstrip("/")
        try:
            dataset = load(data_dir / load_path)
        except LoadError:
            shutil.rmtree(self._root / folder, ignore_errors=True)
            raise

        # A FID is transformed and phased right away; a finished spectrum stays as it is.
        if dataset.domain == "time":
            params = auto_phase(dataset, default_params(dataset))
        else:
            params = ProcessingParams()
        entry = Entry(dataset, params, IntegralSet(), folder, load_path)
        self.entries.append(entry)
        return entry

    def remove(self, index: int) -> None:
        entry = self.entries.pop(index)
        shutil.rmtree(self._root / entry.folder, ignore_errors=True)

    # ---- saving and opening ---------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Write the project file. An existing file is only replaced once the new one
        has been written completely."""
        path = Path(path)
        manifest = {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "app_version": __version__,
            "spectra": [
                {
                    "folder": entry.folder,
                    "load": entry.load_path,
                    "title": entry.dataset.title,
                    "nucleus": entry.dataset.nucleus,
                }
                for entry in self.entries
            ],
        }
        temporary = path.with_name(path.name + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(MANIFEST, json.dumps(manifest, indent=2))
                for entry in self.entries:
                    state = {
                        "processing": asdict(entry.params),
                        "integrals": asdict(entry.integrals),
                    }
                    archive.writestr(f"{entry.folder}/{STATE}", json.dumps(state, indent=2))
                    data_dir = self._root / entry.folder / "data"
                    for file in sorted(p for p in data_dir.rglob("*") if p.is_file()):
                        archive.write(file, file.relative_to(self._root).as_posix())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> "Document":
        path = Path(path)
        document = cls()
        try:
            document._read(path)
        except Exception:
            document.close()
            raise
        document.path = path
        return document

    def _read(self, path: Path) -> None:
        try:
            _extract(path, self._root)
            manifest = json.loads((self._root / MANIFEST).read_text(encoding="utf-8"))
        except (LoadError, OSError, ValueError) as exc:
            raise LoadError(f"{path.name} is not a readable project file.") from exc
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_NAME:
            raise LoadError(f"{path.name} is not an nmr project file.")
        if manifest.get("version", 0) > FORMAT_VERSION:
            raise LoadError(
                f"{path.name} was written by a newer version of nmr "
                f"({manifest.get('app_version', 'unknown')}). Please update to open it."
            )

        for item in manifest.get("spectra", []):
            folder, load_path = str(item.get("folder", "")), str(item.get("load", ""))
            if not re.fullmatch(r"\d+", folder):
                raise LoadError(f"{path.name} is damaged: invalid spectrum folder {folder!r}.")
            data_dir = (self._root / folder / "data").resolve()
            target = (data_dir / load_path).resolve()
            if not target.is_relative_to(data_dir):
                raise LoadError(f"{path.name} is damaged: invalid data path {load_path!r}.")
            dataset = load(target)
            try:
                state = json.loads((self._root / folder / STATE).read_text(encoding="utf-8"))
                params = _from_dict(ProcessingParams, state.get("processing", {}))
                integrals = _integrals_from_dict(state.get("integrals", {}))
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                raise LoadError(
                    f"{path.name} is damaged: unreadable settings for {folder}."
                ) from exc
            self.entries.append(Entry(dataset, params, integrals, folder, load_path))
            self._counter = max(self._counter, int(folder))


def _extract(archive_path: Path, target: Path) -> None:
    """Unpack a ZIP archive. `extractall` strips absolute paths and '..' components."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(target)
    except (OSError, zipfile.BadZipFile) as exc:
        raise LoadError(f"Could not unpack {archive_path.name}: {exc}") from exc


def _from_dict(cls, values: dict):
    """Build a settings object, ignoring keys this version does not know."""
    known = {f.name for f in fields(cls)}
    return cls(**{key: value for key, value in values.items() if key in known})


def _integrals_from_dict(values: dict) -> IntegralSet:
    integrals = _from_dict(IntegralSet, values)
    ranges = tuple((float(high), float(low)) for high, low in integrals.ranges)
    index = int(integrals.ref_index) if ranges else 0
    if not 0 <= index < max(len(ranges), 1) or not np.isfinite(integrals.ref_value):
        raise ValueError("invalid integral reference")
    return IntegralSet(ranges, index, float(integrals.ref_value))
