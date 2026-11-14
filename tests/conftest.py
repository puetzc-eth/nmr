import os
import zipfile
from pathlib import Path

import pytest

# Run GUI tests without opening real windows (also needed on CI without a display).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DATA = Path(__file__).parent / "data"


@pytest.fixture
def jcamp_dir() -> Path:
    return DATA / "jcamp"


@pytest.fixture
def bruker_experiment(tmp_path):
    """Unpack one of the zipped Bruker examples and return its experiment folder."""

    def unpack(name: str) -> Path:
        target = tmp_path / name
        with zipfile.ZipFile(DATA / "bruker" / f"{name}.zip") as archive:
            archive.extractall(target)
        fids = [p for p in target.rglob("fid") if "__MACOSX" not in p.parts]
        assert len(fids) == 1
        return fids[0].parent

    return unpack
