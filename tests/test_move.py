from utils import get_temp_project

from pyro.refactorings import move


def test_move():
    project = get_temp_project()

    project.create_module("foo", "def baz():\n    return 1")
    project.create_module("bar", "")

    move(project, "foo", 1, 5, "bar")

    assert project.get_module_content("foo") == ""
    assert project.get_module_content("bar") == "def baz():\n    return 1"


def test_move_depedency():
    project = get_temp_project()

    project.create_module("foo", "def baz():\n    return 1\nx = baz()")
    project.create_module("bar", "")

    move(project, "foo", 1, 5, "bar")

    assert (
        project.get_module_content("foo") == "from bar import baz\nx = baz()"
    )
    assert project.get_module_content("bar") == "def baz():\n    return 1"
