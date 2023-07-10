from collections.abc import Iterable, Sequence
from typing import Union

import libcst as cst
import libcst.matchers as m
from libcst.metadata import CodeRange, PositionProvider

from pyro.project import Project


class RemoveSymbolAtLocation(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        current_line: int,
        current_column: int,
    ) -> None:
        super().__init__()
        self._current_line = current_line
        self._current_column = current_column
        self.removed_symbol: cst.FunctionDef | None = None
        self.symbol_name: str | None = None

    def _is_in_block(self, code_range: CodeRange | None):
        if code_range is None:
            return False

        correct_line = (
            code_range.start.line <= self._current_line <= code_range.end.line
        )
        corrent_column = (
            code_range.start.column
            <= self._current_column
            <= code_range.end.column
        )
        return correct_line and corrent_column

    def visit_Module(self, node: cst.Module) -> bool | None:
        return super().visit_Module(node)

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        code_range = self.get_metadata(PositionProvider, node, None)
        if self._is_in_block(code_range):
            self.removed_symbol = node
            self.symbol_name = node.name.value
            return False

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef | cst.RemovalSentinel:
        if self.removed_symbol is original_node:
            return cst.RemovalSentinel.REMOVE
        return updated_node


class InsertSymbolEnd(cst.CSTTransformer):
    def __init__(self, symbol: cst.BaseCompoundStatement) -> None:
        super().__init__()
        self._symbol = symbol

    def visit_Module(self, _) -> bool | None:
        return False

    def leave_Module(
        self, _, updated_node: cst.Module
    ) -> cst.Module | cst.RemovalSentinel:
        new_body = list(updated_node.body[:])
        new_body.append(self._symbol)

        return cst.ensure_type(
            updated_node.with_changes(body=new_body),
            cst.Module,
        )


class ReplaceImportIfNeeded(cst.CSTTransformer):
    def __init__(
        self,
        old_module_name: str,
        new_module_name: str,
    ) -> None:
        super().__init__()

        self._new_module_name = new_module_name.split(".")
        self._new_package_name = ".".join(self._new_module_name[:-1])

        self._old_module_name = old_module_name.split(".")
        self._old_package_name = ".".join(self._old_module_name[:-1])

        self._add_import: bool = False
        self._import_alread_added: bool = False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool | None:
        # Do not visit inside import so that the visit_Name only
        # concerns using the symbol
        return False

    def visit_Import(self, node: cst.From) -> bool | None:
        # Do not visit inside import so that the visit_Name only
        # concerns using the symbol
        return False

    def visit_Name(self, node: cst.Name) -> bool | None:
        if node.value == self._new_module_name[-1]:
            self._add_import = True
            return False

    def _get_import_module(
        self, module: Sequence[str]
    ) -> Union[m.Name, m.Attribute]:
        if len(module) == 1:
            return m.Name(value=module[0])
        return m.Attribute(
            value=self._get_import_module(module[:-1]),
            attr=m.Name(value=module[-1]),
        )

    def _remove_import_from_names(
        self, names: Iterable[cst.ImportAlias] | cst.ImportStar
    ) -> list[cst.ImportAlias] | cst.ImportStar:
        new_names: list[cst.ImportAlias] = []
        if isinstance(names, cst.ImportStar):
            return names
        for name in names:
            if not m.matches(
                name,
                m.ImportAlias(
                    name=m.Name(
                        value=self._old_module_name[-1],
                    )
                ),
            ):
                new_names.append(
                    name.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                )
        return new_names

    def _imports_symbol_from_old_path(self, node: cst.CSTNode) -> bool:
        return m.matches(
            node,
            m.ImportFrom(
                module=self._get_import_module(self._old_module_name[:-1]),
                names=[
                    m.ZeroOrMore(),
                    m.ImportAlias(
                        name=m.Name(value=self._old_module_name[-1])
                    ),
                    m.ZeroOrMore(),
                ],
            ),
        )

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom | cst.RemovalSentinel:
        if self._imports_symbol_from_old_path(updated_node):
            names = self._remove_import_from_names(
                cst.ensure_type(updated_node, cst.ImportFrom).names
            )

            if isinstance(names, cst.ImportStar):
                return updated_node

            if not len(names):
                return cst.RemoveFromParent()
            return updated_node.with_changes(names=names)
        if m.matches(
            updated_node,
            m.ImportFrom(
                module=self._get_import_module(self._new_module_name[:-1]),
            ),
        ):
            names = cst.ensure_type(updated_node, cst.ImportFrom).names

            if isinstance(names, cst.ImportStar):
                return updated_node

            new_names: list[cst.ImportAlias] = []
            for name in names:
                new_names.append(
                    name.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                )
            new_names.append(
                cst.ImportAlias(
                    name=cst.Name(value=self._new_module_name[-1]),
                    comma=cst.MaybeSentinel.DEFAULT,
                )
            )
            self._import_alread_added = True
            return updated_node.with_changes(names=new_names)
        return updated_node

    def _end_imports_index(self, body: Sequence[cst.CSTNode]) -> int:
        for i, node in enumerate(body):
            if m.matches(
                node,
                m.SimpleStatementLine(
                    body=[
                        m.AtLeastN(
                            n=1,
                            matcher=(m.Import | m.ImportFrom),
                        )  # type: ignore
                    ]
                )
                | m.Import
                | m.ImportFrom,
            ):
                continue
            return i
        return len(body)

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        if self._add_import and not self._import_alread_added:
            end_imports_index = self._end_imports_index(updated_node.body)
            import_statements = updated_node.body[:end_imports_index]
            rest_body = updated_node.body[end_imports_index:]
            new_import = cst.parse_statement(
                f"from {self._new_package_name} import {self._new_module_name[-1]}",
                config=original_node.config_for_parsing,
            )
            new_body = (*import_statements, new_import, *rest_body)
            return cst.ensure_type(
                updated_node.with_changes(
                    body=new_body,
                ),
                cst.Module,
            )
        return updated_node


def move(
    project: Project,
    module_name_start: str,
    line_number: int,
    column_offset: int,
    module_name_end: str,
) -> None:
    module_start = project.get_module(module_name_start)
    module_end = project.get_module(module_name_end)

    symbol_remover = RemoveSymbolAtLocation(line_number, column_offset)
    module_start.visit_with_metadata(symbol_remover)
    if (
        symbol_remover.removed_symbol is None
        or symbol_remover.symbol_name is None
    ):
        raise Exception("No symbol found at location")

    old_symbol_location = f"{module_name_start}.{symbol_remover.symbol_name}"
    new_symbol_location = f"{module_name_end}.{symbol_remover.symbol_name}"
    module_end.visit(InsertSymbolEnd(symbol_remover.removed_symbol))
    module_start.visit(
        ReplaceImportIfNeeded(old_symbol_location, new_symbol_location)
    )

    project.save_module(module_name_start, module_start)
    project.save_module(module_name_end, module_end)
    for module_name, module in project.walk_modules():
        if module_name == module_name_start or module_name == module_name_end:
            continue

        module.visit(
            ReplaceImportIfNeeded(old_symbol_location, new_symbol_location)
        )
        project.save_module(module_name, module)
