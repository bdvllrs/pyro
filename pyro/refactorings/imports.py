from collections import defaultdict
from collections.abc import Iterable, Sequence

import libcst as cst
import libcst.matchers as m
from libcst.metadata import Assignment, Scope

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


def import_from_module_name(
    module_name: Sequence[str],
    names: Sequence[cst.ImportAlias] | cst.ImportStar,
) -> cst.ImportFrom:
    return cst.ImportFrom(
        module=attribute_from_module_name(module_name),
        names=names,
    )


def find_unused_imports(
    scopes: Iterable[Scope | None],
) -> dict[cst.Import | cst.ImportFrom, set[str]]:
    """
    Inspired from libCST scope analysis tutorial.
    """
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
                if not len(assignment.references):
                    unused_imports[assignment.node].add(assignment.name)
    return unused_imports


class RemoveUnusedImports(cst.CSTTransformer):
    """
    Inspired from libCST scope analysis tutorial.
    """

    def __init__(self, scopes: Iterable[Scope | None]) -> None:
        super().__init__()

        self.unused_imports = find_unused_imports(scopes)

    def leave_import_alike(
        self,
        original_node: cst.Import | cst.ImportFrom,
        updated_node: cst.Import | cst.ImportFrom,
    ) -> cst.Import | cst.ImportFrom | cst.RemovalSentinel:
        if original_node not in self.unused_imports:
            return updated_node
        names_to_keep = []

        if isinstance(updated_node.names, cst.ImportStar):
            return updated_node

        for name in updated_node.names:
            asname = name.asname
            if asname is not None:
                name_value = asname.name.value
            else:
                name_value = name.name.value
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
