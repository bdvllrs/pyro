from collections.abc import Iterable
from typing import Any

import libcst as cst
import libcst.matchers as m
from libcst.metadata import (
    Assignment,
    BuiltinScope,
    CodeRange,
    GlobalScope,
    PositionProvider,
    Scope,
    ScopeProvider,
)
from libcst.metadata.scope_provider import LocalScope

from pyro.module import Module
from pyro.project import Project
from pyro.refactorings.imports import (
    AddImports,
    GatherExportsVisitor,
    ImportT,
    RemoveUnusedImports,
    ReplaceImport,
    import_from_module_name,
)

SymbolT = cst.FunctionDef | cst.ClassDef


def _get_symbol_scope(
    node: SymbolT | cst.SimpleStatementLine, scopes: Iterable[Scope | None]
) -> Scope | None:
    for scope in scopes:
        if scope is None or not isinstance(scope, LocalScope):
            continue
        if scope.node == node:
            return scope
    return None


def is_subscope_of(parent_scope: Scope, scope: Scope | None) -> bool:
    if scope is None:
        return False
    if scope == parent_scope:
        return True
    if isinstance(parent_scope, BuiltinScope):
        return True
    if isinstance(scope, BuiltinScope):
        return False
    return is_subscope_of(parent_scope, scope.parent)


class RemoveSymbolAtLocation(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        scopes: Iterable[Scope | None],
        line_number: int,
        col_offset: int,
        module_name: str,
    ) -> None:
        self._line_number = line_number
        self._col_offset = col_offset
        self._module_name = module_name.split(".")
        self.removed_symbol: SymbolT | cst.SimpleStatementLine | None = None
        self.symbol_name: str | None = None
        self.symbol_requirements: dict[str, ImportT] = {}
        self._scopes = scopes
        self._code_range: CodeRange | None = None

    def _is_in_block(self, code_range: CodeRange | None):
        if code_range is None:
            return False

        correct_line = (
            code_range.start.line <= self._line_number <= code_range.end.line
        )
        correct_column = (
            code_range.start.column
            <= self._col_offset
            <= code_range.end.column
        )
        return correct_line and correct_column

    def _node_requirements(
        self,
        parent_scope: Scope,
        scope: Scope,
        node: cst.CSTNode | None = None,
    ) -> dict[str, ImportT]:
        referents: dict[str, ImportT] = {}
        for access in scope.accesses:
            for referent in access.referents:
                if not isinstance(referent, Assignment):
                    continue
                if node is not None and access.node != node:
                    continue

                if isinstance(parent_scope, LocalScope) and is_subscope_of(
                    parent_scope, referent.scope
                ):
                    continue

                if isinstance(referent.node, (cst.Import, cst.ImportFrom)):
                    import_node = referent.node
                elif isinstance(referent.node, cst.Name):
                    import_node = import_from_module_name(
                        self._module_name,
                        names=[
                            cst.ImportAlias(
                                name=cst.Name(value=referent.node.value),
                            )
                        ],
                    )
                elif isinstance(
                    referent.node, (cst.ClassDef, cst.FunctionDef)
                ):
                    import_node = import_from_module_name(
                        self._module_name,
                        names=[
                            cst.ImportAlias(
                                name=referent.node.name,
                            )
                        ],
                    )
                else:
                    continue

                referents[referent.name] = import_node
        return referents

    def visit_symbol(self, node: SymbolT) -> bool | None:
        code_range = self.get_metadata(PositionProvider, node, None)
        if self._is_in_block(code_range):
            self._code_range = code_range
            self.removed_symbol = node
            self.symbol_name = node.name.value
            parent_scope = _get_symbol_scope(node, self._scopes)
            if parent_scope is not None:
                for scope in self._scopes:
                    if scope is None or not is_subscope_of(
                        parent_scope, scope
                    ):
                        continue
                    self.symbol_requirements.update(
                        self._node_requirements(parent_scope, scope)
                    )
            return False
        return True

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        return self.visit_symbol(node)

    def visit_ClassDef(self, node: cst.ClassDef) -> bool | None:
        return self.visit_symbol(node)

    def visit_SimpleStatementLine(
        self, node: cst.SimpleStatementLine
    ) -> bool | None:
        code_range = self.get_metadata(PositionProvider, node, None)
        if self._is_in_block(code_range):
            self._code_range = code_range
            if m.matches(
                node,
                m.SimpleStatementLine(
                    body=[m.Assign(targets=[m.AssignTarget(target=m.Name())])]
                ),
            ):
                assign = cst.ensure_type(node.body[0], cst.Assign)
                symbol_name = cst.ensure_type(
                    assign.targets[0].target,
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
            self.symbol_name = symbol_name
        return True

    def look_for_inline_referent(self, node: cst.Attribute | cst.Name) -> bool:
        if self._code_range is None:
            return True

        for scope in self._scopes:
            if scope is None or not isinstance(scope, GlobalScope):
                continue
            self.symbol_requirements.update(
                self._node_requirements(scope, scope, node)
            )
        return True

    def visit_Attribute(self, node: cst.Attribute) -> bool | None:
        return self.look_for_inline_referent(node)

    def visit_Name(self, node: cst.Name) -> bool | None:
        if node.value == self.symbol_name:
            return False
        return self.look_for_inline_referent(node)

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
            self._code_range = None
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

    @staticmethod
    def _remove_leading_lines(
        node: cst.SimpleStatementLine | cst.BaseCompoundStatement,
    ) -> cst.SimpleStatementLine | cst.BaseCompoundStatement:
        leading_lines = []
        for line in node.leading_lines:
            if line.comment is not None:
                leading_lines.append(line)
        return node.with_changes(leading_lines=leading_lines)

    def leave_Module(
        self, _: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        new_body = list(updated_node.body)
        if len(updated_node.body):
            new_body[0] = self._remove_leading_lines(new_body[0])
        return updated_node.with_changes(body=new_body)


class InsertSymbolEnd(cst.CSTTransformer):
    def __init__(
        self,
        symbol: cst.BaseCompoundStatement | cst.SimpleStatementLine,
    ) -> None:
        super().__init__()
        self._symbol = symbol

    def visit_Module(self, _) -> bool | None:
        return False

    def _get_leading_lines(
        self, previous_node: cst.CSTNode | None
    ) -> list[cst.EmptyLine]:
        leading_lines = list(self._symbol.leading_lines)
        empty_lines = 0
        for line in leading_lines:
            if line.comment is None:
                empty_lines += 1
            else:
                break

        number_leading_lines = 0
        if previous_node is not None:
            number_leading_lines = 2

        if empty_lines == number_leading_lines:
            return leading_lines

        if empty_lines > number_leading_lines:
            for _ in range(empty_lines):
                leading_lines.pop(0)
            return leading_lines

        for _ in range(number_leading_lines - empty_lines):
            leading_lines.append(
                cst.EmptyLine(indent=True, newline=cst.Newline(value=None))
            )
        return leading_lines

    def leave_Module(self, _, updated_node: cst.Module) -> cst.Module:
        new_body = list(updated_node.body)
        last_node = new_body[-1] if len(new_body) else None
        new_body.append(
            self._symbol.with_changes(
                leading_lines=self._get_leading_lines(last_node)
            )
        )

        return cst.ensure_type(
            updated_node.with_changes(body=new_body),
            cst.Module,
        )


def move(
    project: Project,
    module_name_start: str,
    line_number: int,
    column_offset: int,
    module_name_end: str,
) -> dict[str, Any]:
    module_start = project.get_module(module_name_start)
    module_end = project.get_module(module_name_end)

    export_gatherer = GatherExportsVisitor()
    module_start.visit(export_gatherer)

    wrapper = cst.MetadataWrapper(module_start.tree)
    scopes = set(wrapper.resolve(ScopeProvider).values())
    symbol_remover = RemoveSymbolAtLocation(
        scopes, line_number, column_offset, module_name_start
    )
    module_start.visit_with_metadata(wrapper, symbol_remover)
    if (
        symbol_remover.removed_symbol is None
        or symbol_remover.symbol_name is None
    ):
        raise Exception("No symbol found at location")

    module_start.visit(
        AddImports(
            [
                import_from_module_name(
                    module_name_end.split("."),
                    names=[
                        cst.ImportAlias(
                            name=cst.Name(value=symbol_remover.symbol_name),
                        )
                    ],
                )
            ]
        )
    )

    wrapper = cst.MetadataWrapper(module_start.tree)
    scopes = set(wrapper.resolve(ScopeProvider).values())
    module_start.visit_with_metadata(
        wrapper,
        RemoveUnusedImports(scopes, export_gatherer.explicit_exported_objects),
    )

    module_end.visit(
        AddImports(list(symbol_remover.symbol_requirements.values()))
    )
    module_end.visit(InsertSymbolEnd(symbol_remover.removed_symbol))

    modules_to_save: list[tuple[str, Module]] = [
        (module_name_start, module_start),
        (module_name_end, module_end),
    ]

    for module_name, module in project.walk_modules():
        if module_name == module_name_start or module_name == module_name_end:
            continue

        export_gatherer = GatherExportsVisitor()
        module.visit(export_gatherer)

        wrapper = cst.MetadataWrapper(module.tree)
        scopes = set(wrapper.resolve(ScopeProvider).values())
        replacer = ReplaceImport(
            scopes,
            module_name_start.split(".") + [symbol_remover.symbol_name],
            module_name_end.split(".") + [symbol_remover.symbol_name],
            export_gatherer.explicit_exported_objects,
        )
        module.visit_with_metadata(wrapper, replacer)

        if replacer.did_update:
            wrapper = cst.MetadataWrapper(module.tree)
            scopes = set(wrapper.resolve(ScopeProvider).values())
            module.visit_with_metadata(
                wrapper,
                RemoveUnusedImports(
                    scopes, export_gatherer.explicit_exported_objects
                ),
            )

            modules_to_save.append((module_name, module))

    for module_name, mod in modules_to_save:
        project.save_module(module_name, mod)

    return {"success": True}
