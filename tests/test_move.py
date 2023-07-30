import pytest
from utils import code, get_temp_project

from pyro.refactorings import move


def test_move():
    project = get_temp_project()

    mod1 = code(
        """
        def not_moved():
            return 2


        def test():
            return 1
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 5, 5, "mod2")
    mod1_expected = code(
        """
        def not_moved():
            return 2
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_after_existing():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = 2
    """
    )

    mod2 = code(
        """
        def fn():
            return 1
        """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", mod2)

    move(project, "mod1", 1, 5, "mod2")

    mod2_expected = code(
        """
        def fn():
            return 1


        def test():
            return 1
        """
    )

    assert project.get_module_content("mod1") == "x = 2\n"
    assert project.get_module_content("mod2") == mod2_expected


def test_move_dependency():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
    """
    )
    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 1, 4, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_long_term_dependency():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
    """
    )

    project.create_module("mod1.mod2", mod1)
    project.create_module("mod2", "")

    move(project, "mod1.mod2", 1, 5, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )

    assert project.get_module_content("mod1.mod2") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_long_term_dependency_2():
    project = get_temp_project()

    mod2 = code(
        """
        def test():
            return 1


        x = test()
    """
    )
    project.create_module("mod2", mod2)
    project.create_module("mod1.mod2", "")

    move(project, "mod2", 1, 5, "mod1.mod2")

    mod2_expected = code(
        """
        from mod1.mod2 import test

        x = test()
    """
    )

    mod1_2_expected = code(
        """
        def test():
            return 1
    """
    )

    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod1.mod2") == mod1_2_expected


def test_move_other_unrelated_file():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
    """
    )

    mod3 = code(
        """
        from mod4 import x

        print(x)
        """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("mod3", mod3)
    project.create_module("mod4", "x = 2\n")

    move(project, "mod1", 1, 5, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    mod3_expected = code(
        """
        from mod4 import x

        print(x)
    """
    )
    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected
    assert project.get_module_content("mod4") == "x = 2\n"


def test_move_other_unrelated_file_absolute_import():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
    """
    )
    mod3 = code(
        """
        import math

        print(math.pi)
    """
    )
    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("mod3", mod3)

    move(project, "mod1", 1, 5, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )

    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    mod3_expected = code(
        """
        import math

        print(math.pi)
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected


def test_move_other_dependencies_import_from():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
    """
    )
    mod3 = code(
        """
        from mod1 import test

        x = test()
    """
    )
    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("mod3", mod3)

    move(project, "mod1", 1, 5, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    mod3_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )
    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected


def test_move_other_dependencies_import_from_in_local_scope():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
    """
    )
    mod3 = code(
        """
        def fn():
            from mod1 import test

            return test()


        x = fn()
    """
    )
    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("mod3", mod3)

    move(project, "mod1", 1, 5, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    mod3_expected = code(
        """
        def fn():
            from mod2 import test

            return test()


        x = fn()
    """
    )
    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected


def test_move_other_dependencies_multiple_import_from_start():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
        y = 0
    """
    )
    mod3 = code(
        """
        from mod1 import test, y

        x = test()
        z = y
    """
    )
    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("mod3", mod3)

    move(project, "mod1", 1, 5, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
        y = 0
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    mod3_expected = code(
        """
        from mod1 import y
        from mod2 import test

        x = test()
        z = y
    """
    )
    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected


def test_move_other_dependencies_multiple_import_from_end():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        x = test()
    """
    )
    mod3 = code(
        """
        from mod1 import test
        from mod2 import y

        x = test()
        z = y
    """
    )
    project.create_module("mod1", mod1)
    project.create_module("mod2", "y = 0")
    project.create_module("mod3", mod3)

    move(project, "mod1", 1, 5, "mod2")

    mod1_expected = code(
        """
        from mod2 import test

        x = test()
    """
    )
    mod2_expected = code(
        """
        y = 0


        def test():
            return 1
    """
    )
    mod3_expected = code(
        """
        from mod2 import test, y

        x = test()
        z = y
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected


def test_move_other_dependencies_absolute():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1
        """
    )
    mod3 = code(
        """
        import mod1

        y = mod1.test()
        """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("mod3", mod3)

    move(project, "mod1", 1, 5, "mod2")

    mod2_expected = code(
        """
        def test():
            return 1
        """
    )
    mod3_expected = code(
        """
        from mod2 import test

        y = test()
        """
    )

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected


def test_move_long_term_other_dependencies_absolute():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1
    """
    )
    mod3 = code(
        """
        import pkg

        y = pkg.mod1.test()
    """
    )
    project.create_module("pkg.mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("mod3", mod3)

    move(project, "pkg.mod1", 1, 5, "mod2")

    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    mod3_expected = code(
        """
        from mod2 import test

        y = test()
    """
    )
    assert project.get_module_content("pkg.mod1") == "\n"
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("mod3") == mod3_expected


def test_move_module():
    project = get_temp_project()

    mod1 = code(
        """
        class Test:
            def test(self):
                return 1
    """
    )
    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 1, 6, "mod2")

    mod2_expected = code(
        """
        class Test:
            def test(self):
                return 1
    """
    )

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod2_expected


def test_move_variable():
    project = get_temp_project()

    project.create_module("mod1", "test = 1\n")
    project.create_module("mod2", "")

    move(project, "mod1", 1, 1, "mod2")

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == "test = 1\n"


def test_move_variable_fail_multiple_assignments():
    project = get_temp_project()

    project.create_module("mod1", "test = other_var = 1\n")
    project.create_module("mod2", "")

    with pytest.raises(ValueError):
        move(project, "mod1", 1, 1, "mod2")


def test_move_variable_with_annotation():
    project = get_temp_project()

    project.create_module("mod1", "test: int = 1\n")
    project.create_module("mod2", "")

    move(project, "mod1", 1, 1, "mod2")

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == "test: int = 1\n"


def test_move_symbol_with_external_dependency():
    project = get_temp_project()

    mod1 = code(
        """
        from mod import fn


        def test():
            return fn(1)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 4, 4, "mod2")

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod1


def test_move_symbol_with_external_dependency_variable():
    project = get_temp_project()

    mod1 = code(
        """
        from mod import fn

        test = fn(1)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 3, 1, "mod2")

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod1


def test_move_symbol_with_external_dependency_variable_complex():
    project = get_temp_project()

    mod1 = code(
        """
        from mod import fn

        test = {}
        test[fn(1)] = 1
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 3, 1, "mod2")

    mod1_expected = code(
        """
        from mod import fn
        from mod2 import test

        test[fn(1)] = 1
    """
    )
    mod2_expected = code(
        """
        test = {}
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_symbol_with_external_dependency_variable_attr():
    project = get_temp_project()

    mod1 = code(
        """
        from mod import fn

        test = fn.test(1)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 3, 1, "mod2")

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod1


def test_move_symbol_with_external_dependency_variable_annotation():
    project = get_temp_project()

    mod1 = code(
        """
        from typing import List

        from mod import fn

        test: List = fn(1)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 5, 1, "mod2")

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod1


def test_move_symbol_with_external_dependency_class():
    project = get_temp_project()

    mod1 = code(
        """
        from mod import fn
        import fn2
        import fn3


        class Test:
            def fn(self):
                return fn(1)

            def a(self, x):
                return fn2.test(x)


        x = fn3.test(fn(1))
    """
    )

    mod2 = ""

    project.create_module("mod1", mod1)
    project.create_module("mod2", mod2)

    move(project, "mod1", 6, 6, "mod2")

    mod1_expected = code(
        """
        import fn3
        from mod import fn

        x = fn3.test(fn(1))
    """
    )

    mod2_expected = code(
        """
        import fn2
        from mod import fn


        class Test:
            def fn(self):
                return fn(1)

            def a(self, x):
                return fn2.test(x)
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_symbol_class_with_dependencies():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        class Test:
            attr = 3

            def fn(self):
                return test()

            def a(self, x):
                x = self.fn()
                return x + self.attr
    """
    )

    mod2 = ""

    project.create_module("mod1", mod1)
    project.create_module("mod2", mod2)

    move(project, "mod1", 5, 6, "mod2")

    mod1_expected = code(
        """
        def test():
            return 1
    """
    )

    mod2_expected = code(
        """
        from mod1 import test


        class Test:
            attr = 3

            def fn(self):
                return test()

            def a(self, x):
                x = self.fn()
                return x + self.attr
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_symbol_with_external_dependency_keep_dependency():
    project = get_temp_project()

    mod1 = code(
        """
        from mod import fn


        def test():
            return fn(1)


        def test2():
            return fn(2)
    """
    )

    mod2 = ""

    project.create_module("mod1", mod1)
    project.create_module("mod2", mod2)

    move(project, "mod1", 4, 5, "mod2")
    mod1_expected = code(
        """
        from mod import fn


        def test2():
            return fn(2)
        """
    )
    mod2_expected = code(
        """
        from mod import fn


        def test():
            return fn(1)
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_symbol_with_external_dependency_absolute_import():
    project = get_temp_project()

    mod1 = code(
        """
        import mod as m


        def test():
            return m.fn(1)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 4, 5, "mod2")
    mod2_expected = code(
        """
        import mod as m


        def test():
            return m.fn(1)
    """
    )

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod2_expected


def test_move_symbol_with_external_dependency_absolute_import_renamed():
    project = get_temp_project()

    mod1 = code(
        """
        import mod as m

        x = m(1)
        m = 2


        def test():
            return m
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 7, 5, "mod2")
    mod1_expected = code(
        """
        import mod as m

        x = m(1)
        m = 2
    """
    )
    mod2_expected = code(
        """
        from mod1 import m


        def test():
            return m
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_symbol_with_internal_dependency():
    project = get_temp_project()

    mod1 = code(
        """
        def fn(x):
            return x + 1


        def test():
            return fn(1)
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 5, 5, "mod2")
    mod1_expected = code(
        """
        def fn(x):
            return x + 1
    """
    )
    mod2_expected = code(
        """
        from mod1 import fn


        def test():
            return fn(1)
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_move_symbol_with_init_file():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        def fn():
            return 2
    """
    )

    init_file = code(
        """
        from mod1 import test, fn

        __all__ = ["fn", "test"]
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("__init__", init_file)

    move(project, "mod1", 1, 5, "mod2")
    mod1_expected = code(
        """
        def fn():
            return 2
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    init_expected = code(
        """
        from mod1 import fn
        from mod2 import test

        __all__ = ["fn", "test"]
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("__init__") == init_expected


def test_move_symbol_with_init_file_2():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1
    """
    )

    init_file = code(
        """
        from mod import fn
        from mod1 import test

        __all__ = ["test", "fn"]
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("__init__", init_file)

    move(project, "mod1", 1, 5, "mod2")
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    init_expected = code(
        """
        from mod import fn
        from mod2 import test

        __all__ = ["test", "fn"]
    """
    )

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("__init__") == init_expected


def test_move_symbol_with_init_file_3():
    project = get_temp_project()

    mod1 = code(
        """
        def test():
            return 1


        def fn():
            return 2
    """
    )

    init_file = code(
        """
        from mod import fn2
        from mod1 import fn

        __all__ = ["fn", "fn2"]
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")
    project.create_module("__init__", init_file)

    move(project, "mod1", 1, 5, "mod2")
    mod1_expected = code(
        """
        def fn():
            return 2
    """
    )
    mod2_expected = code(
        """
        def test():
            return 1
    """
    )
    init_expected = code(
        """
        from mod import fn2
        from mod1 import fn

        __all__ = ["fn", "fn2"]
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected
    assert project.get_module_content("__init__") == init_expected


def test_type_requirements():
    project = get_temp_project()

    mod1 = code(
        """
        from typing import List


        class Test:
            def test(self, x: List[str]):
                return 1
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 4, 5, "mod2")
    mod2_expected = code(
        """
        from typing import List


        class Test:
            def test(self, x: List[str]):
                return 1
    """
    )

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod2_expected


def test_type_local_requirements():
    project = get_temp_project()

    mod1 = code(
        """
        from typing import List, TypeVar

        T = TypeVar("T")


        def test(x: List[T]) -> T:
            return x[0]
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 6, 5, "mod2")
    mod1_expected = code(
        """
        from typing import TypeVar

        T = TypeVar("T")
    """
    )
    mod2_expected = code(
        """
        from typing import List

        from mod1 import T


        def test(x: List[T]) -> T:
            return x[0]
    """
    )

    assert project.get_module_content("mod1") == mod1_expected
    assert project.get_module_content("mod2") == mod2_expected


def test_type_local_requirements_string():
    project = get_temp_project()

    mod1 = code(
        """
        from typing import List, TypeVar

        T = TypeVar("T")


        def test(x: "List[T]") -> T:
            return x[0]
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    with pytest.raises(ValueError):
        move(project, "mod1", 6, 5, "mod2")
    # mod1_expected = code(
    #     """
    #     from typing import TypeVar
    #
    #     T = TypeVar("T")
    # """
    # )
    # mod2_expected = code(
    #     """
    #     from typing import List
    #
    #     from mod1 import T
    #
    #
    #     def test(x: "List[T]") -> T:
    #         return x[0]
    # """
    # )
    #
    # assert project.get_module_content("mod1") == mod1_expected
    # assert project.get_module_content("mod2") == mod2_expected


def test_type_local_param_has_requirements():
    project = get_temp_project()

    mod1 = code(
        """
        import math


        def test(x=math.pi):
            return x
    """
    )

    project.create_module("mod1", mod1)
    project.create_module("mod2", "")

    move(project, "mod1", 4, 5, "mod2")
    mod2_expected = code(
        """
        import math


        def test(x=math.pi):
            return x
    """
    )

    assert project.get_module_content("mod1") == "\n"
    assert project.get_module_content("mod2") == mod2_expected
