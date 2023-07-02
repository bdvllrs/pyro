from pathlib import Path

from pyro.module import Module


class Project:
    def __init__(self, root: Path):
        assert root.is_dir()

        self.root = root

    def get_module_path(self, name: str) -> Path:
        return self.root / (name.replace(".", "/") + ".py")

    def create_module(self, name: str, content: str) -> None:
        module_path = name.split(".")
        for k in range(len(module_path) - 1):
            package_name = "/".join(module_path[: k + 1])
            if not self.package_exists(package_name):
                self.create_package(package_name)

        self.save_module_content(name, content)

    def package_exists(self, name: str) -> bool:
        location = self.root / name.replace(".", "/")
        init_file = location / "__init__.py"
        return init_file.exists()

    def create_package(self, name: str) -> None:
        module_path = name.split(".")
        for k in range(len(module_path) - 1):
            package_name = "/".join(module_path[: k + 1])
            if not self.package_exists(package_name):
                self.create_package(package_name)
        location = self.root / name.replace(".", "/")

        init_file = location / "__init__.py"
        init_file.parent.mkdir(exist_ok=True)
        init_file.touch()

    def get_module_content(self, name: str) -> str:
        location = self.get_module_path(name)
        with open(location, "r") as f:
            return f.read()

    def save_module_content(self, name: str, content: str) -> None:
        location = self.get_module_path(name)
        with open(location, "w") as f:
            f.write(content)

    def get_module(self, name: str) -> Module:
        content = self.get_module_content(name)
        return Module.from_content(content)

    def save_module(self, name: str, module: Module) -> None:
        self.save_module_content(name, module.get_content())
