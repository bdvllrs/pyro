import tempfile
from pathlib import Path

from pyro import Project


def get_temp_project() -> Project:
    tmp_dir = tempfile.mkdtemp(prefix="pyro_test_project")
    return Project(Path(tmp_dir))
