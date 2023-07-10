import click

from pyro.cli.move import move_command

__all__ = ["cli"]


@click.group()
def cli():
    pass


cli.add_command(move_command)
