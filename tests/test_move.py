import pytest
from utils import get_temp_project

from pyro.refactorings import move


def test_move():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1")
    project.create_module("mod2", "")

    move(project, "mod1", 1, 5, "mod2")

    assert project.get_module_content("mod1") == ""
    assert project.get_module_content("mod2") == "def test():\n    return 1"


def test_move_after_existing():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1\n\nx = 2")
    project.create_module("mod2", "def fn():\n    return 1")

    move(project, "mod1", 1, 5, "mod2")

    assert project.get_module_content("mod1") == "\nx = 2"
    assert (
        project.get_module_content("mod2")
        == "def fn():\n    return 1\n\ndef test():\n    return 1"
    )


def test_move_dependency():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1\nx = test()")
    project.create_module("mod2", "")

    move(project, "mod1", 1, 5, "mod2")

    assert (
        project.get_module_content("mod1")
        == "from mod2 import test\nx = test()"
    )
    assert project.get_module_content("mod2") == "def test():\n    return 1"


def test_move_long_term_dependency():
    project = get_temp_project()

    project.create_module("mod1.mod2", "def test():\n    return 1\nx = test()")
    project.create_module("mod2", "")

    move(project, "mod1.mod2", 1, 5, "mod2")

    assert (
        project.get_module_content("mod1.mod2")
        == "from mod2 import test\nx = test()"
    )
    assert project.get_module_content("mod2") == "def test():\n    return 1"


def test_move_long_term_dependency_2():
    project = get_temp_project()

    project.create_module("mod2", "def test():\n    return 1\nx = test()")
    project.create_module("mod1.mod2", "")

    move(project, "mod2", 1, 5, "mod1.mod2")

    assert (
        project.get_module_content("mod2")
        == "from mod1.mod2 import test\nx = test()"
    )
    assert (
        project.get_module_content("mod1.mod2") == "def test():\n    return 1"
    )


def test_move_other_unrelated_file():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1\nx = test()")
    project.create_module("mod2", "")
    project.create_module("mod3", "from mod4 import x\n\nprint(x)")
    project.create_module("mod4", "x = 2")

    move(project, "mod1", 1, 5, "mod2")

    assert (
        project.get_module_content("mod1")
        == "from mod2 import test\nx = test()"
    )
    assert project.get_module_content("mod2") == "def test():\n    return 1"
    assert (
        project.get_module_content("mod3") == "from mod4 import x\n\nprint(x)"
    )
    assert project.get_module_content("mod4") == "x = 2"


def test_move_other_unrelated_file_absolute_import():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1\nx = test()")
    project.create_module("mod2", "")
    project.create_module("mod3", "import math\n\nprint(math.pi)")

    move(project, "mod1", 1, 5, "mod2")

    assert (
        project.get_module_content("mod1")
        == "from mod2 import test\nx = test()"
    )
    assert project.get_module_content("mod2") == "def test():\n    return 1"
    assert (
        project.get_module_content("mod3") == "import math\n\nprint(math.pi)"
    )


def test_move_other_dependencies_import_from():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1\nx = test()")
    project.create_module("mod2", "")
    project.create_module("mod3", "from mod1 import test\nx = test()")

    move(project, "mod1", 1, 5, "mod2")

    assert (
        project.get_module_content("mod1")
        == "from mod2 import test\nx = test()"
    )
    assert project.get_module_content("mod2") == "def test():\n    return 1"
    assert (
        project.get_module_content("mod3")
        == "from mod2 import test\nx = test()"
    )


def test_move_other_dependencies_multiple_import_from_start():
    project = get_temp_project()

    project.create_module(
        "mod1", "def test():\n    return 1\nx = test()\ny = 0"
    )
    project.create_module("mod2", "")
    project.create_module(
        "mod3", "from mod1 import test, y\nx = test()\nz = y"
    )

    move(project, "mod1", 1, 5, "mod2")

    assert (
        project.get_module_content("mod1")
        == "from mod2 import test\nx = test()\ny = 0"
    )
    assert project.get_module_content("mod2") == "def test():\n    return 1"
    assert (
        project.get_module_content("mod3")
        == "from mod1 import y\nfrom mod2 import test\nx = test()\nz = y"
    )


def test_move_other_dependencies_multiple_import_from_end():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1\nx = test()")
    project.create_module("mod2", "y = 0")
    project.create_module(
        "mod3", "from mod1 import test\nfrom mod2 import y\nx = test()\nz = y"
    )

    move(project, "mod1", 1, 5, "mod2")

    assert (
        project.get_module_content("mod1")
        == "from mod2 import test\nx = test()"
    )
    assert (
        project.get_module_content("mod2")
        == "y = 0\n\ndef test():\n    return 1"
    )
    assert (
        project.get_module_content("mod3")
        == "from mod2 import y, test\nx = test()\nz = y"
    )


def test_move_other_dependencies_absolute():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1")
    project.create_module("mod2", "")
    project.create_module("mod3", "import mod1\n\ny = mod1.test()")

    move(project, "mod1", 1, 5, "mod2")

    assert project.get_module_content("mod1") == ""
    assert project.get_module_content("mod2") == "def test():\n    return 1"
    assert (
        project.get_module_content("mod3")
        == "from mod2 import test\n\ny = test()"
    )


def test_move_long_term_other_dependencies_absolute():
    project = get_temp_project()

    project.create_module("pkg.mod1", "def test():\n    return 1")
    project.create_module("mod2", "")
    project.create_module("mod3", "import pkg\n\ny = pkg.mod1.test()")

    move(project, "pkg.mod1", 1, 5, "mod2")

    assert project.get_module_content("pkg.mod1") == ""
    assert project.get_module_content("mod2") == "def test():\n    return 1"
    assert (
        project.get_module_content("mod3")
        == "from mod2 import test\n\ny = test()"
    )


def test_move_module():
    project = get_temp_project()

    project.create_module(
        "mod1", "class test:\n    def test(self):\n       return 1"
    )
    project.create_module("mod2", "")

    move(project, "mod1", 1, 6, "mod2")

    assert project.get_module_content("mod1") == ""
    assert (
        project.get_module_content("mod2")
        == "class test:\n    def test(self):\n       return 1"
    )


def test_move_variable():
    project = get_temp_project()

    project.create_module("mod1", "test = 1")
    project.create_module("mod2", "")

    move(project, "mod1", 1, 1, "mod2")

    assert project.get_module_content("mod1") == ""
    assert project.get_module_content("mod2") == "test = 1"


def test_move_variable_fail_multiple_assignments():
    project = get_temp_project()

    project.create_module("mod1", "test = other_var = 1")
    project.create_module("mod2", "")

    with pytest.raises(ValueError):
        move(project, "mod1", 1, 1, "mod2")


def test_move_variable_with_annotation():
    project = get_temp_project()

    project.create_module("mod1", "test: int = 1")
    project.create_module("mod2", "")

    move(project, "mod1", 1, 1, "mod2")

    assert project.get_module_content("mod1") == ""
    assert project.get_module_content("mod2") == "test: int = 1"
