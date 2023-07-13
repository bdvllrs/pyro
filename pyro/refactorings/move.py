from collections.abc import Iterable, Sequence
from typing import Union

import libcst as cst
import libcst.matchers as m
from libcst.metadata import CodeRange, PositionProvider, ScopeProvider

from pyro.module import Module
from pyro.project import Project
from pyro.refactorings.unused_imports import RemoveUnusedImports


class FindSymbolDependencies(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        current_line: int,
        current_column: int,
    ) -> None:
        super().__init__()
        self._current_line = current_line
        self._current_column = current_column


SymbolT = cst.FunctionDef | cst.ClassDef


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
        self.removed_symbol: SymbolT | cst.SimpleStatementLine | None = None
        self.symbol_names: list[str] | None = None

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

    def visit_symbol(self, node: SymbolT) -> bool | None:
        code_range = self.get_metadata(PositionProvider, node, None)
        if self._is_in_block(code_range):
            self.removed_symbol = node
            self.symbol_names = [node.name.value]
            return False

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        return self.visit_symbol(node)

    def visit_ClassDef(self, node: cst.ClassDef) -> bool | None:
        return self.visit_symbol(node)

    def visit_SimpleStatementLine(
        self, node: cst.SimpleStatementLine
    ) -> bool | None:
        code_range = self.get_metadata(PositionProvider, node, None)
        if self._is_in_block(code_range):
            if m.matches(
                node,
                m.SimpleStatementLine(
                    body=[m.Assign(targets=[m.AssignTarget(target=m.Name())])]
                ),
            ):
                symbol_name = cst.ensure_type(
                    cst.ensure_type(node.body[0], cst.Assign)
                    .targets[0]
                    .target,
                    cst.Name,
                ).value
            elif m.matches(
                node,
                m.SimpleStatementLine(body=[m.AnnAssign(target=m.Name())]),
            ):
                symbol_name = cst.ensure_type(
                    cst.ensure_type(node.body[0], cst.AnnAssign).target,
                    cst.Name,
                ).value
            else:
                raise ValueError(
                    "Cannot extract assignment of multiple variables yet."
                )
            self.removed_symbol = node
            self.symbol_names = [symbol_name]
            return False

    def leave_symbol(
        self,
        original_node: cst.BaseCompoundStatement | cst.SimpleStatementLine,
        updated_node: cst.BaseCompoundStatement | cst.SimpleStatementLine,
    ) -> (
        cst.BaseCompoundStatement
        | cst.SimpleStatementLine
        | cst.RemovalSentinel
    ):
        if self.removed_symbol is original_node:
            return cst.RemovalSentinel.REMOVE
        return updated_node

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> (
        cst.BaseCompoundStatement
        | cst.SimpleStatementLine
        | cst.RemovalSentinel
    ):
        return self.leave_symbol(original_node, updated_node)

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> (
        cst.BaseCompoundStatement
        | cst.SimpleStatementLine
        | cst.RemovalSentinel
    ):
        return self.leave_symbol(original_node, updated_node)

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> (
        cst.BaseCompoundStatement
        | cst.SimpleStatementLine
        | cst.RemovalSentinel
    ):
        return self.leave_symbol(original_node, updated_node)


class InsertSymbolEnd(cst.CSTTransformer):
    def __init__(
        self, symbol: cst.BaseCompoundStatement | cst.SimpleStatementLine
    ) -> None:
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


def _get_symbol_access_matcher(
    module: list[str],
) -> Union[m.Name, m.Attribute]:
    if len(module) == 1:
        return m.Name(value=module[0])
    return m.Attribute(
        value=_get_symbol_access_matcher(module[:-1]),
        attr=m.Name(value=module[-1]),
    )


class ReplaceImportIfNeeded(cst.CSTTransformer):
    def __init__(
        self,
        old_package_name: str,
        new_package_name: str,
        symbol_names: Sequence[str],
    ) -> None:
        super().__init__()

        self._new_module_name = new_package_name.split(".")
        self._new_package_name = new_package_name

        self._old_module_name = old_package_name.split(".")
        self._old_package_name = old_package_name
        self._symbol_names = symbol_names

        self._add_import: bool = False
        self._import_alread_added: bool = False
        self._symbol_schemas: list[m.BaseMatcherNode] = []

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool | None:
        # Do not visit inside import so that the visit_Name only
        # concerns using the symbol
        return False

    def _imports_package_or_module(
        self, node: cst.Name | cst.Attribute, module: list[str]
    ) -> tuple[Union[m.Name, m.Attribute], list[str]]:
        name = m.Name(value=module[0])
        if m.matches(node, name):
            return name, [module[0]]

        assert isinstance(node, cst.Attribute)

        sub_match, sub_module = self._imports_package_or_module(
            cst.ensure_type(node, cst.Attribute).value, module  # type: ignore
        )
        rest_module = module[len(sub_module) :]
        new_attr = m.Attribute(
            value=sub_match, attr=m.Name(value=rest_module[0])
        )
        return new_attr, sub_module + [rest_module[0]]

    def visit_Import(self, node: cst.Import) -> bool | None:
        for name in node.names:
            match_attr, _ = self._imports_package_or_module(
                name.name, self._old_module_name + [self._symbol_names[0]]
            )
            if m.matches(name.name, match_attr):
                self._symbol_schemas.append(
                    _get_symbol_access_matcher(
                        self._old_module_name + [self._symbol_names[0]]
                    )
                )
        # Do not visit inside import so that the visit_Name only
        # concerns using the symbol
        return False

    def visit_Name(self, node: cst.Name) -> bool | None:
        if node.value in self._symbol_names:
            self._add_import = True
            return False

    def leave_Attribute(
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.Attribute | cst.Name:
        for schema in self._symbol_schemas:
            if m.matches(original_node, schema):
                return cst.Name(value=self._symbol_names[0])
        return updated_node

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
                        value=self._symbol_names[0],
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
                module=self._get_import_module(self._old_module_name),
                names=[
                    m.ZeroOrMore(),
                    m.ImportAlias(name=m.Name(value=self._symbol_names[0])),
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
                module=self._get_import_module(self._new_module_name),
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
                    name=cst.Name(value=self._symbol_names[0]),
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
                f"from {self._new_package_name} import {self._symbol_names[0]}",
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


def symbol_dependencies(
    module: Module,
    line_number: int,
    column_oofset: int,
):
    pass


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
        or symbol_remover.symbol_names is None
    ):
        raise Exception("No symbol found at location")

    module_end.visit(InsertSymbolEnd(symbol_remover.removed_symbol))
    module_start.visit(
        ReplaceImportIfNeeded(
            module_name_start,
            module_name_end,
            symbol_remover.symbol_names,
        )
    )

    project.save_module(module_name_start, module_start)
    project.save_module(module_name_end, module_end)
    for module_name, module in project.walk_modules():
        if module_name == module_name_start or module_name == module_name_end:
            continue

        module.visit(
            ReplaceImportIfNeeded(
                module_name_start, module_name_end, symbol_remover.symbol_names
            )
        )

        scopes = set(module.resolve_metadata(ScopeProvider).values())
        module.visit(RemoveUnusedImports(scopes))

        project.save_module(module_name, module)
