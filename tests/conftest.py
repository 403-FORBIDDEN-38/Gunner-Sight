import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config_manager import ConfigManager


@pytest.fixture
def config(tmp_path):
    return ConfigManager(config_dir=str(tmp_path / "config"))
