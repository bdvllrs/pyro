from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Union

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
    ImportT,
    RemoveUnusedImports,
    import_from_module_name,
)


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
        self, scope: Scope, node: cst.CSTNode | None = None
    ) -> dict[str, ImportT]:
        referents: dict[str, ImportT] = {}
        for access in scope.accesses:
            for referent in access.referents:
                if not isinstance(referent, Assignment):
                    continue
                if node is not None and access.node != node:
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
                        self._node_requirements(scope)
                    )
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

    def look_for_inline_referent(
        self, node: cst.Attribute | cst.Name
    ) -> bool | None:
        if self._code_range is None:
            return True

        for scope in self._scopes:
            if scope is None or not isinstance(scope, GlobalScope):
                continue
            self.symbol_requirements.update(
                self._node_requirements(scope, node)
            )

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

    def leave_Module(
        self, _, updated_node: cst.Module
    ) -> cst.Module | cst.RemovalSentinel:
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
        symbol_name: str,
        symbol_requirements: Mapping[str, ImportT],
    ) -> None:
        super().__init__()

        self._new_module_name = new_package_name.split(".")
        self._new_package_name = new_package_name

        self._old_module_name = old_package_name.split(".")
        self._old_package_name = old_package_name
        self._symbol_name = symbol_name
        self._symbol_requirement = symbol_requirements

        self._add_import: bool = False
        self._import_alread_added: bool = False
        self._symbol_schemas: list[m.BaseMatcherNode] = []

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool | None:
        # Do not visit inside import so that the visit_Name only
        # concerns using the symbol
        return False

    def _imports_package_or_module(
        self, node: cst.BaseExpression, module: list[str]
    ) -> tuple[Union[m.Name, m.Attribute, None], list[str] | None]:
        name = m.Name(value=module[0])
        if m.matches(node, name):
            return name, [module[0]]

        if isinstance(node, cst.Name):
            return None, None

        if not isinstance(node, cst.Attribute):
            raise ValueError()

        sub_match, sub_module = self._imports_package_or_module(
            cst.ensure_type(node, cst.Attribute).value, module
        )
        if sub_match is None or sub_module is None:
            return None, None

        rest_module = module[len(sub_module) :]
        new_attr = m.Attribute(
            value=sub_match, attr=m.Name(value=rest_module[0])
        )
        return new_attr, sub_module + [rest_module[0]]

    def visit_Import(self, node: cst.Import) -> bool | None:
        for name in node.names:
            match_attr, _ = self._imports_package_or_module(
                name.name, self._old_module_name + [self._symbol_name]
            )
            if match_attr is None:
                return False

            if m.matches(name.name, match_attr):
                self._symbol_schemas.append(
                    _get_symbol_access_matcher(
                        self._old_module_name + [self._symbol_name]
                    )
                )
        # Do not visit inside import so that the visit_Name only
        # concerns using the symbol
        return False

    def visit_Name(self, node: cst.Name) -> bool | None:
        if node.value == self._symbol_name:
            self._add_import = True
            return False

    def leave_Attribute(
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.Attribute | cst.Name:
        for schema in self._symbol_schemas:
            if m.matches(original_node, schema):
                return cst.Name(value=self._symbol_name)
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
                        value=self._symbol_name,
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
                    m.ImportAlias(name=m.Name(value=self._symbol_name)),
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
                    name=cst.Name(value=self._symbol_name),
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
                f"from {self._new_package_name} import {self._symbol_name}",
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
    column_offset: int,
):
    pass


def move(
    project: Project,
    module_name_start: str,
    line_number: int,
    column_offset: int,
    module_name_end: str,
) -> dict[str, Any]:
    module_start = project.get_module(module_name_start)
    module_end = project.get_module(module_name_end)

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
        ReplaceImportIfNeeded(
            module_name_start,
            module_name_end,
            symbol_remover.symbol_name,
            symbol_remover.symbol_requirements,
        )
    )
    wrapper = cst.MetadataWrapper(module_start.tree)
    scopes = set(wrapper.resolve(ScopeProvider).values())
    module_start.visit_with_metadata(wrapper, RemoveUnusedImports(scopes))

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

        module.visit(
            ReplaceImportIfNeeded(
                module_name_start,
                module_name_end,
                symbol_remover.symbol_name,
                symbol_remover.symbol_requirements,
            )
        )

        wrapper = cst.MetadataWrapper(module.tree)
        scopes = set(wrapper.resolve(ScopeProvider).values())
        module.visit_with_metadata(wrapper, RemoveUnusedImports(scopes))

        modules_to_save.append((module_name, module))

    for module_name, mod in modules_to_save:
        project.save_module(module_name, mod)

    return {"success": True}
