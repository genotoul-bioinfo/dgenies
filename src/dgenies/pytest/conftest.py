import os
import sys
import tempfile
from pathlib import Path

import pytest


PACKAGE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PACKAGE_DIR.parent
TEST_ROOT = Path(tempfile.mkdtemp(prefix="dgenies-pytest-"))

sys.path.insert(0, str(SRC_DIR))

for dirname in ("config", "uploads", "data", "mpl"):
    (TEST_ROOT / dirname).mkdir(parents=True, exist_ok=True)

os.environ.setdefault("CONFIG_DIR", str(TEST_ROOT / "config"))
os.environ.setdefault("UPLOAD_DIR", str(TEST_ROOT / "uploads"))
os.environ.setdefault("DATA_DIR", str(TEST_ROOT / "data"))
os.environ.setdefault("DATABASE_URL", ":memory:")
os.environ.setdefault("DISABLE_CRONS", "True")
os.environ.setdefault("DISABLE_MAIL", "true")
os.environ.setdefault("MPLCONFIGDIR", str(TEST_ROOT / "mpl"))


@pytest.fixture(scope="session")
def package_dir():
    return PACKAGE_DIR


@pytest.fixture(scope="session")
def launched_app():
    import dgenies

    if dgenies.app is None:
        dgenies.launch(mode="webserver", debug=True)
    return dgenies.app


@pytest.fixture
def fasta_file(tmp_path):
    path = tmp_path / "sample.fa"
    path.write_text(">ctg1\nAAAA\n>ctg2\nCCCCCC\n")
    return path
