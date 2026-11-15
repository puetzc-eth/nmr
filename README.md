# nmr

Open-source desktop app for processing and analysing NMR spectra on Windows, Linux and macOS.

Status: early development. The first milestone is 1D spectra (¹H/¹³C): import, processing,
peak picking, integration, multiplet reports and export.

## Development setup

Requires Python 3.11 or newer.

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run

```
python -m nmr
```

## Test

```
pytest
ruff check .
```

## Project files

Data is imported by opening or dropping the original instrument files. The originals are
only read, never changed.

| Format | Import | Export |
|---|---|---|
| Bruker TopSpin folder (FID and processed spectrum) | yes | |
| JEOL Delta `.jdf` (FID) | yes | |
| Varian/Agilent VnmrJ folder (`fid` + `procpar`) | yes, not yet verified on instrument data | |
| JCAMP-DX (`.dx`, `.jdx`) | yes | yes |
| ZIP archive of any of the above | yes | |
| CSV (shift, intensity) | | yes |

A project is saved as a `.nmrx` file, which is a plain ZIP archive:

| Entry | Content |
|---|---|
| `manifest.json` | Format version and the list of spectra |
| `001/data/…` | Unmodified copy of the original instrument files of the first spectrum |
| `001/state.json` | Its processing settings and integrals |

Spectra are recomputed from the original data and the settings when a project is opened.

## Layout

| Path | Purpose |
|---|---|
| `src/nmr/core/` | File import, processing, analysis and the project file. No GUI imports, usable from scripts and notebooks. |
| `src/nmr/gui/` | Desktop application (PySide6 + pyqtgraph). |
| `tests/` | pytest suite. |
| `tests/data/` | Real example spectra (third-party, MIT, see `tests/data/README.md`). |

## Licence

Copyright © 2026 puetzc

This program is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version. It is distributed without any warranty.
See [LICENSE](LICENSE) for the full text.
