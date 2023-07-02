import ast

from pyro.module import filter_node_types, get_first_node
from pyro.project import Project


class RemoveImport(ast.NodeTransformer):
    def __init__(self, module: str, name: str) -> None:
        super().__init__()
        self.module = module
        self.name = name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom | None:
        if node.module == self.module:
            for name in node.names:
                if name.name == self.name:
                    node.names.remove(name)
                    if not node.names:
                        return None
                    break
        return node


def move(
    project: Project,
    original_name: str,
    lineno: int,
    col_offset: int,
    target_name: str,
):
    original_module = project.get_module(original_name)
    target_module = project.get_module(target_name)
    possible_nodes = {ast.FunctionDef}
    nodes = filter_node_types(
        original_module.at(lineno, col_offset), possible_nodes
    )
    node = get_first_node(nodes)
    assert hasattr(node.ast, "name")

    import_types = {ast.Import, ast.ImportFrom}
    import_name = node.ast.name  # type: ignore

    target_module.add_node(node.ast, after=import_types)
    original_module.filter_node(node.ast)

    original_module_needs_import = original_module.contains_node(
        ast.Name, {"id": import_name}
    )

    if original_module_needs_import:
        new_import = ast.ImportFrom(
            module=target_name,
            names=[
                ast.alias(
                    name=import_name,
                    asname=None,
                )
            ],
            level=0,
        )
        original_module.add_node(new_import, after=import_types)

    project.save_module(original_name, original_module)
    project.save_module(target_name, target_module)

    for module_name, module in project.walk_modules():
        contains_import_from = module.contains_node(
            ast.ImportFrom, {"module": original_name}
        )
        if contains_import_from:
            module.add_import(target_name, import_name)
            module.apply_transform(RemoveImport(original_name, import_name))
            project.save_module(module_name, module)
