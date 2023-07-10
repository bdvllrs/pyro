from pathlib import Path

import click

from pyro.project import Project
from pyro.refactorings.move import move


@click.command("move", help="Move a symbol to another module")
@click.argument(
    "root_path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
)
@click.argument(
    "module_start",
    type=str,
    required=True,
)
@click.argument(
    "lineno",
    type=int,
    required=True,
)
@click.argument(
    "colno",
    type=int,
    required=True,
)
@click.argument("module_end", type=str, required=True)
def move_command(
    root_path: Path,
    module_start: str,
    lineno: int,
    colno: int,
    module_end: str,
) -> None:
    project = Project(root_path)
    move(project, module_start, lineno, colno, module_end)
