import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/build-run/scripts"))

from test_delivery import delivered  # noqa: E402, F401 -- register native merge fixture
from test_plan_compiler import authored  # noqa: E402, F401 -- register complete plan fixture
from test_scorer_contract import attempt  # noqa: E402, F401 -- register shared real-Git fixture


@pytest.fixture(autouse=True)
def roomy_disk(monkeypatch):
    """The 40 GiB floor is a host property; test_low_disk_blocks_before_admission pins it."""
    monkeypatch.setattr(shutil, "disk_usage", lambda path: SimpleNamespace(free=1 << 50))
