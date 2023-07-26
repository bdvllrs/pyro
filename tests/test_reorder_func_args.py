from pyro.refactorings.reorder_func_args import reorder_func_arg
from utils import code, get_temp_project


def test_rename_func_name():
    project = get_temp_project()

    mod1 = code(
        """
        def test(a, b, c, /, d, *, e, **kwargs):
            return a + b + c + d + e
    """
    )

    project.create_module("mod1", mod1)

    reorder_func_arg(project, "mod1", "test", [2, 1, 0, 3, 4])
    mod1_expected = code(
        """
        def test(c, b, a, /, d, *, e, **kwargs):
            return a + b + c + d + e
    """
    )
    assert project.get_module_content("mod1") == mod1_expected


def test_rename_func_name_invert_pos():
    project = get_temp_project()

    mod1 = code(
        """
        def test(a, b, c, /, d, e):
            return a + b + c + d
    """
    )

    project.create_module("mod1", mod1)

    reorder_func_arg(project, "mod1", "test", [0, 1, 2, 4, 3, 5])
    mod1_expected = code(
        """
        def test(a, b, c, d, /, e):
            return a + b + c + d
    """
    )
    assert project.get_module_content("mod1") == mod1_expected


def test_rename_func_name_other_file():
    project = get_temp_project()

    mod1 = code(
        """
        def test(a, b, c, /, d, e):
            return a + b + c + d
    """
    )

    mod2 = code(
        """
        from mod1 import test

        x = test(1, 2, 3, 4, e=5)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", mod2)

    reorder_func_arg(project, "mod1", "test", [0, 1, 2, 4, 3, 5])
    mod1_expected = code(
        """
        def test(a, b, c, d, /, e):
            return a + b + c + d
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2


def test_rename_func_name_other_file_change_order():
    project = get_temp_project()

    mod1 = code(
        """
        def test(a, b, c):
            return a + b + c
    """
    )

    mod2 = code(
        """
        from mod1 import test

        x = test(1, 2, 3)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", mod2)

    reorder_func_arg(project, "mod1", "test", [0, 2, 1])
    mod1_expected = code(
        """
        def test(a, c, b):
            return a + b + c
    """
    )

    mod2_expected = code(
        """
        from mod1 import test

        x = test(1, 3, 2)
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
