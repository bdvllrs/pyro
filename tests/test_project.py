from utils import get_temp_project


def test_package_exists():
    project = get_temp_project()
    assert not project.package_exists("foo")
    project.create_package("foo")
    assert project.package_exists("foo")
    assert not project.package_exists("foo.bar")
    project.create_package("foo.bar")
    assert project.package_exists("foo")
    assert project.package_exists("foo.bar")


def test_project_add_package():
    project = get_temp_project()

    project.create_package("foo")

    module_path = project.root / "foo"
    init_file = module_path / "__init__.py"
    assert module_path.is_dir()
    assert init_file.exists()


def test_project_add_package_recursive():
    project = get_temp_project()

    project.create_package("foo.bar.baz")

    module_path = project.root / "foo"
    init_file = module_path / "__init__.py"
    assert module_path.is_dir()
    assert init_file.exists()

    module_path = project.root / "foo/bar"
    init_file = module_path / "__init__.py"
    assert module_path.is_dir()
    assert init_file.exists()

    module_path = project.root / "foo/bar/baz"
    init_file = module_path / "__init__.py"
    assert module_path.is_dir()
    assert init_file.exists()


def test_project_add_module():
    project = get_temp_project()

    project.create_module("foo", "x = 1\n")

    module_path = project.root / "foo.py"
    assert module_path.exists()
    with open(module_path, "r") as f:
        assert f.read() == "x = 1\n"


def test_project_add_module_and_subpackages():
    project = get_temp_project()

    project.create_module("foo.bar.baz", "x = 1\n")

    module_path = project.root / "foo/bar/baz.py"
    assert (project.root / "foo/bar/__init__.py").exists()
    assert (project.root / "foo/__init__.py").exists()
    assert module_path.exists()
    with open(module_path, "r") as f:
        assert f.read() == "x = 1\n"
