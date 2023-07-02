from utils import get_temp_project

from pyro.refactorings import move


def test_move():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1")
    project.create_module("mod2", "")

    move(project, "mod1", 1, 5, "mod2")

    assert project.get_module_content("mod1") == ""
    assert project.get_module_content("mod2") == "def test():\n    return 1"


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


def test_move_long_term_other_dependencies_import_from():
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


def test_move_long_term_other_dependencies_multiple_import_from_start():
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


def test_move_long_term_other_dependencies_multiple_import_from_end():
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
        == "def test():\n    return 1\ny = 0"
    )
    assert (
        project.get_module_content("mod3")
        == "from mod2 import y, test\nx = test()\nz = y"
    )


def test_move_long_term_other_dependencies_absolute():
    project = get_temp_project()

    project.create_module("mod1", "def test():\n    return 1")
    project.create_module("mod2", "")
    project.create_module("mod3", "import mod1\ny = mod1.test()")

    move(project, "mod1", 1, 5, "mod2")

    assert project.get_module_content("mod1") == ""
    assert project.get_module_content("mod2") == "def test():\n    return 1"
    assert project.get_module_content("mod3") == "import mod2\nmod2.test()"
