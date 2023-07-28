from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Union, cast
from typing import Set, Union

import libcst as cst
import libcst.matchers as m
from libcst.helpers import get_full_name_for_node

import libcst as cst
import libcst.matchers as m
from libcst.metadata import (
    Assignment,
    BuiltinScope,
    ImportAssignment,
    ParentNodeProvider,
    Scope,
)

ImportT = cst.Import | cst.ImportFrom


def attribute_from_module_name(
    module_name: Sequence[str],
) -> cst.Attribute | cst.Name:
    if len(module_name) == 0:
        raise ValueError("module_name must not be empty")

    if len(module_name) == 1:
        return cst.Name(value=module_name[0])
    return cst.Attribute(
        value=attribute_from_module_name(module_name[:-1]),
        attr=cst.Name(value=module_name[-1]),
    )


def attribute_matcher_from_module_name(
    module_name: Sequence[str],
) -> Union[m.Attribute, m.Name]:
    if len(module_name) == 0:
        raise ValueError("module_name must not be empty")

    if len(module_name) == 1:
        return m.Name(value=module_name[0])
    return m.Attribute(
        value=attribute_matcher_from_module_name(module_name[:-1]),
        attr=m.Name(value=module_name[-1]),
    )


def import_from_module_name(
    module_name: Sequence[str],
    names: Sequence[cst.ImportAlias] | cst.ImportStar,
) -> cst.ImportFrom:
    return cst.ImportFrom(
        module=attribute_from_module_name(module_name),
        names=names,
    )


def find_unused_imports(
    scopes: Iterable[Scope | None], exports: set[str] | None = None
) -> dict[cst.Import | cst.ImportFrom, set[str]]:
    """
    Inspired from libCST scope analysis tutorial.
    """
    mod_exports = exports or set()
    unused_imports: dict[cst.Import | cst.ImportFrom, set[str]] = defaultdict(
        set
    )
    for scope in scopes:
        if scope is None:
            continue
        for assignment in scope.assignments:
            if isinstance(assignment, Assignment) and isinstance(
                assignment.node, (cst.Import, cst.ImportFrom)
            ):
                if (
                    not len(assignment.references)
                    and assignment.name not in mod_exports
                ):
                    unused_imports[assignment.node].add(assignment.name)
    return unused_imports


def sequence_from_attr(node: cst.BaseExpression) -> list[str]:
    return [node.value for node in sequence_of_names(node)]


def sequence_of_names(node: cst.BaseExpression) -> list[cst.Name]:
    if isinstance(node, cst.Name):
        return [node]
    elif isinstance(node, cst.Attribute):
        return sequence_of_names(node.value) + [node.attr]
    raise ValueError(f"Expected Name or Attribute, got {node}")


class RemoveUnusedImports(cst.CSTTransformer):
    """
    Inspired from libCST scope analysis tutorial.
    """

    def __init__(
        self, scopes: Iterable[Scope | None], exports: set[str] | None = None
    ) -> None:
        super().__init__()

        self.unused_imports = find_unused_imports(scopes, exports)

    def leave_import_alike(
        self,
        original_node: cst.Import | cst.ImportFrom,
        updated_node: cst.Import | cst.ImportFrom,
    ) -> cst.Import | cst.ImportFrom | cst.RemovalSentinel:
        if original_node not in self.unused_imports:
            return updated_node
        names_to_keep = []

        names = updated_node.names
        if isinstance(names, cst.ImportStar):
            return updated_node

        for name in cast(Sequence[cst.ImportAlias], names):
            asname = name.asname
            if asname is not None:
                name_value = cst.ensure_type(asname.name, cst.Name).value
            else:
                name_value = cst.ensure_type(name.name, cst.Name).value
            if name_value not in self.unused_imports[original_node]:
                names_to_keep.append(
                    name.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                )
        if len(names_to_keep) == 0:
            return cst.RemoveFromParent()
        else:
            return updated_node.with_changes(names=names_to_keep)

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> cst.Import | cst.ImportFrom | cst.RemovalSentinel:
        return self.leave_import_alike(original_node, updated_node)

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.Import | cst.ImportFrom | cst.RemovalSentinel:
        return self.leave_import_alike(original_node, updated_node)


def split_imports(
    body: Sequence[cst.SimpleStatementLine | cst.BaseCompoundStatement],
) -> tuple[
    list[cst.SimpleStatementLine],
    list[cst.SimpleStatementLine | cst.BaseCompoundStatement],
]:
    import_statements: list[cst.SimpleStatementLine] = []
    other_statements: list[
        cst.SimpleStatementLine | cst.BaseCompoundStatement
    ] = []

    for k, statement in enumerate(body):
        if m.matches(
            statement,
            m.SimpleStatementLine(body=[m.Import() | m.ImportFrom()]),
        ):
            import_statements.append(
                cst.ensure_type(statement, cst.SimpleStatementLine)
            )
        else:
            other_statements = list(body[k:])
            break

    return import_statements, other_statements


class AddImports(cst.CSTTransformer):
    def __init__(self, imports: Sequence[ImportT]):
        super().__init__()
        self._imports = imports

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        import_statements, other_statements = split_imports(updated_node.body)
        for imp in self._imports:
            import_statements.append(cst.SimpleStatementLine(body=[imp]))
        return updated_node.with_changes(
            body=[
                *import_statements,
                *other_statements,
            ]
        )


def is_import_from_of_module(
    module: Sequence[str],
    names: Sequence[str],
    node: cst.ImportFrom,
) -> bool:
    if not len(names) or not len(module):
        return False

    is_matching = m.matches(
        node,
        m.ImportFrom(
            module=attribute_matcher_from_module_name(module),
            names=[
                m.ZeroOrMore(),
                m.ImportAlias(name=attribute_matcher_from_module_name(names)),
                m.ZeroOrMore(),
            ],
        ),
    )
    if is_matching:
        return True
    return is_import_from_of_module(list(module) + [names[0]], names[1:], node)


def is_import_of_module(
    module: Sequence[str],
    names: Sequence[str],
    node: cst.Import | cst.ImportFrom,
) -> bool:
    if isinstance(node, cst.ImportFrom):
        return is_import_from_of_module(module, names, node)

    if not len(names) or not len(module):
        return False

    is_matching = m.matches(
        node,
        m.Import(
            names=[
                m.ZeroOrMore(),
                m.ImportAlias(name=attribute_matcher_from_module_name(module)),
                m.ZeroOrMore(),
            ],
        ),
    )
    if is_matching:
        return True
    return is_import_of_module(list(module) + [names[0]], names[1:], node)


class ReplaceImport(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (ParentNodeProvider,)

    def __init__(
        self,
        scopes: Iterable[Scope | None],
        module_from: Sequence[str],
        module_to: Sequence[str],
        mod_exports: set[str],
    ):
        self._scopes = scopes
        self._from = module_from
        self._to = module_to
        self._mod_exports = mod_exports
        self._should_add_import = False
        self.did_update = False
        self._old_import_computed: bool = False
        self._old_import: cst.Import | cst.ImportFrom | None = None
        self._other_assignments: bool = False
        self._ref_replacements: set[
            cst.Name | cst.Attribute | cst.BaseString
        ] = set()

    def _get_full_call_attr(
        self, node: cst.CSTNode
    ) -> tuple[list[str], cst.Name | cst.Attribute | None]:
        ref_parent = cst.ensure_type(
            self.get_metadata(ParentNodeProvider, node), cst.CSTNode
        )
        if isinstance(node, cst.BaseString):
            raise ValueError("TODO")
        if isinstance(node, cst.Name):
            attr, par_node = self._get_full_call_attr(ref_parent)
            return [
                node.value
            ] + attr, par_node if par_node is not None else node
        if isinstance(node, cst.Attribute):
            attr, par_node = self._get_full_call_attr(ref_parent)
            return [
                node.attr.value
            ] + attr, par_node if par_node is not None else node
        return [], None

    def _get_old_import(
        self,
    ) -> tuple[cst.Import | cst.ImportFrom | None, bool]:
        if self._old_import_computed:
            return (
                self._old_import,
                self._other_assignments,
            )

        self._old_import_computed = True
        assignment_node: cst.Import | cst.ImportFrom | None = None
        other_assignments: bool = False
        for scope in self._scopes:
            if scope is None or isinstance(scope, BuiltinScope):
                continue
            for assignment in scope.assignments:
                if isinstance(assignment, ImportAssignment) and isinstance(
                    assignment.node, (cst.ImportFrom, cst.Import)
                ):
                    for reference in assignment.references:
                        ref_attr_strs, ref_attr = self._get_full_call_attr(
                            reference.node
                        )
                        if (
                            is_import_of_module(
                                [self._from[0]],
                                list(self._from[1:]) + ref_attr_strs[1:],
                                assignment.node,
                            )
                            and ref_attr is not None
                        ):
                            if self._from[-1] == ref_attr_strs[-1]:
                                self._should_add_import = True
                                assignment_node = assignment.node
                                self._ref_replacements.add(ref_attr)
                            else:
                                other_assignments = True

                    if assignment_node is not None:
                        continue

                    for export in self._mod_exports:
                        if is_import_of_module(
                            [self._from[0]],
                            list(self._from[1:]),
                            assignment.node,
                        ):
                            if self._from[-1] == export:
                                self._should_add_import = True
                                assignment_node = assignment.node
                            else:
                                other_assignments = True

        self._old_import = assignment_node
        self._other_assignments = other_assignments
        return self._old_import, self._other_assignments

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> (
        cst.SimpleStatementLine | cst.FlattenSentinel[cst.SimpleStatementLine]
    ):
        bodies: list[list[cst.BaseSmallStatement]] = [[]]
        for orig_subnode, updated_subnode in zip(
            original_node.body, updated_node.body
        ):
            if isinstance(updated_subnode, cst.Import) and isinstance(
                orig_subnode, cst.Import
            ):
                new_import = self.get_new_import(orig_subnode, updated_subnode)

            elif isinstance(updated_subnode, cst.ImportFrom) and isinstance(
                orig_subnode, cst.ImportFrom
            ):
                new_import = self.get_new_import_from(
                    orig_subnode, updated_subnode
                )
            else:
                bodies[0].append(updated_subnode)
                continue
            for k, new_import_node in enumerate(new_import):
                if len(bodies) <= k:
                    bodies.append([])
                bodies[k].append(new_import_node)

        if len(bodies) == 1:
            return updated_node.with_changes(body=bodies[0])
        return cst.FlattenSentinel(
            [cst.SimpleStatementLine(body=body) for body in bodies]
        )

    def get_new_import_from(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> list[cst.ImportFrom]:
        old_import, other_assignments = self._get_old_import()
        if old_import != original_node:
            return [updated_node]

        new_import = self._get_new_import()
        self.should_add_import = False
        self.did_update = True

        if not other_assignments:
            return [new_import]

        names = updated_node.names
        if isinstance(names, cst.ImportStar):
            return [new_import, updated_node]

        new_names: list[cst.ImportAlias] = []
        for name in names:  # type: ignore
            assert isinstance(name, cst.ImportAlias)

            if (
                isinstance(name.name, cst.Name)
                and name.name.value == self._from[-1]
            ):
                continue
            new_names.append(
                name.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            )

        return [updated_node.with_changes(names=new_names), new_import]

    def get_new_import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> list[ImportT]:
        old_import, other_assignments = self._get_old_import()
        if old_import != updated_node:
            return [updated_node]

        new_import = self._get_new_import()
        self.should_add_import = False
        self.did_update = True

        if not other_assignments:
            return [new_import]
        return [updated_node, new_import]

    def _get_new_import(self) -> cst.ImportFrom:
        symbol_name = self._to[-1]
        return import_from_module_name(
            self._to[:-1],
            [cst.ImportAlias(name=cst.Name(symbol_name))],
        )

    def _get_new_import_ref(self) -> cst.Name:
        return cst.Name(value=self._to[-1])

    def leave_Attribute(
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.Attribute | cst.Name:
        self._get_old_import()
        if original_node in self._ref_replacements:
            return self._get_new_import_ref()
        return updated_node

    def leave_Name(
        self, original_node: cst.Name, updated_node: cst.Name
    ) -> cst.Name:
        self._get_old_import()
        if original_node in self._ref_replacements:
            return self._get_new_import_ref()
        return updated_node

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        if self._should_add_import:
            import_statements, other_statements = split_imports(
                updated_node.body
            )
            new_import = cst.SimpleStatementLine(body=[self._get_new_import()])
            new_body = (*import_statements, new_import, *other_statements)
            self.did_update = True
            return cst.ensure_type(
                updated_node.with_changes(
                    body=new_body,
                ),
                cst.Module,
            )
        return updated_node


class GatherExportsVisitor(cst.CSTVisitor):
    """
    Inspired from libcst.codemod._gather_exports
    """

    def __init__(self) -> None:
        super().__init__()
        self.explicit_exported_objects: Set[str] = set()
        self._is_assigned_export: Set[
            Union[cst.Tuple, cst.List, cst.Set]
        ] = set()
        self._in_assigned_export: Set[
            Union[cst.Tuple, cst.List, cst.Set]
        ] = set()

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool:
        value = node.value
        if value:
            if self._handle_assign_target(node.target, value):
                return True
        return False

    def visit_AugAssign(self, node: cst.AugAssign) -> bool:
        if m.matches(
            node,
            m.AugAssign(
                target=m.Name("__all__"),
                operator=m.AddAssign(),
                value=m.List() | m.Tuple(),
            ),
        ):
            value = node.value
            if isinstance(value, (cst.List, cst.Tuple)):
                self._is_assigned_export.add(value)
            return True
        return False

    def visit_Assign(self, node: cst.Assign) -> bool:
        for target_node in node.targets:
            if self._handle_assign_target(target_node.target, node.value):
                return True
        return False

    def _handle_assign_target(
        self, target: cst.BaseExpression, value: cst.BaseExpression
    ) -> bool:
        target_name = get_full_name_for_node(target)
        if target_name == "__all__":
            # Assignments such as `__all__ = ["os"]`
            # or `__all__ = exports = ["os"]`
            if isinstance(value, (cst.List, cst.Tuple, cst.Set)):
                self._is_assigned_export.add(value)
                return True
        elif isinstance(target, cst.Tuple) and isinstance(value, cst.Tuple):
            # Assignments such as `__all__, x = ["os"], []`
            for element_idx, element_node in enumerate(target.elements):
                element_name = get_full_name_for_node(element_node.value)
                if element_name == "__all__":
                    element_value = value.elements[element_idx].value
                    if isinstance(
                        element_value, (cst.List, cst.Tuple, cst.Set)
                    ):
                        self._is_assigned_export.add(value)
                        self._is_assigned_export.add(element_value)
                        return True
        return False

    def visit_List(self, node: cst.List) -> bool:
        if node in self._is_assigned_export:
            self._in_assigned_export.add(node)
            return True
        return False

    def leave_List(self, original_node: cst.List) -> None:
        self._is_assigned_export.discard(original_node)
        self._in_assigned_export.discard(original_node)

    def visit_Tuple(self, node: cst.Tuple) -> bool:
        if node in self._is_assigned_export:
            self._in_assigned_export.add(node)
            return True
        return False

    def leave_Tuple(self, original_node: cst.Tuple) -> None:
        self._is_assigned_export.discard(original_node)
        self._in_assigned_export.discard(original_node)

    def visit_Set(self, node: cst.Set) -> bool:
        if node in self._is_assigned_export:
            self._in_assigned_export.add(node)
            return True
        return False

    def leave_Set(self, original_node: cst.Set) -> None:
        self._is_assigned_export.discard(original_node)
        self._in_assigned_export.discard(original_node)

    def visit_SimpleString(self, node: cst.SimpleString) -> bool:
        self._handle_string_export(node)
        return False

    def visit_ConcatenatedString(self, node: cst.ConcatenatedString) -> bool:
        self._handle_string_export(node)
        return False

    def _handle_string_export(
        self, node: Union[cst.SimpleString, cst.ConcatenatedString]
    ) -> None:
        if self._in_assigned_export:
            name = node.evaluated_value
            if name is None:
                return
            self.explicit_exported_objects.add(name)  # type: ignore
