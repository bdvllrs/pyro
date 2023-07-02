import ast

from pyro.module import filter_node_types, get_first_node
from pyro.project import Project


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

    new_import = ast.ImportFrom(
        module=target_name,
        names=[
            ast.alias(
                name=node.ast.name,  # type: ignore
                asname=None,
            )
        ],
        level=0,
    )
    import_types = {ast.Import, ast.ImportFrom}

    target_module.add_node(node.ast, after=import_types)
    original_module.filter_node(node.ast)
    original_module.add_node(new_import, after=import_types)

    project.save_module(original_name, original_module)
    project.save_module(target_name, target_module)
