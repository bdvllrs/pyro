from collections import defaultdict
from collections.abc import Iterable
from typing import Union

import libcst as cst
import libcst.matchers as m
from libcst.metadata import Assignment, Scope


def _get_attribute(
    node: cst.BaseExpression,
) -> Union[m.Attribute, m.Name]:
    if isinstance(node, cst.Name):
        return m.Name(value=node.value)
    if isinstance(node, cst.Attribute):
        return m.Attribute(
            value=_get_attribute(node.value),
            attr=m.Name(value=node.attr.value),
        )
    raise ValueError(f"Unexpected node type {type(node)}")


def _get_match_node(
    node: cst.Import | cst.ImportFrom,
) -> Union[m.Import, m.ImportFrom]:
    if isinstance(node, cst.Import):
        return m.Import(
            names=[
                m.ImportAlias(name=_get_attribute(name.name))
                for name in node.names
            ]
        )
    elif isinstance(node, cst.ImportFrom):
        if isinstance(node.names, cst.ImportStar):
            names = m.ImportStar()
        else:
            names = [
                m.ImportAlias(name=_get_attribute(name.name))
                for name in node.names
            ]
        module = _get_attribute(node.module) if node.module else None

        return m.ImportFrom(module=module, names=names)
    else:
        raise NotImplementedError


def _find_unused_imports(
    scopes: Iterable[Scope | None],
) -> dict[Union[m.Import, m.ImportFrom], set[str]]:
    """
    Inspired from libCST scope analysis tutorial.
    """
    unused_imports: dict[
        Union[m.Import, m.ImportFrom], set[str]
    ] = defaultdict(set)
    for scope in scopes:
        if scope is None:
            continue
        for assignment in scope.assignments:
            node = assignment.node  # type: ignore
            if isinstance(assignment, Assignment) and isinstance(
                node, (cst.Import, cst.ImportFrom)
            ):
                if not len(assignment.references):
                    match_node = _get_match_node(node)
                    unused_imports[match_node].add(assignment.name)
    return unused_imports


class RemoveUnusedImports(cst.CSTTransformer):
    """
    Inspired from libCST scope analysis tutorial.
    """

    def __init__(self, scopes: Iterable[Scope | None]) -> None:
        super().__init__()

        self._scopes = scopes
        self.unused_imports = _find_unused_imports(self._scopes)

    def leave_import_alike(
        self,
        original_node: cst.Import | cst.ImportFrom,
        updated_node: cst.Import | cst.ImportFrom,
    ) -> cst.Import | cst.ImportFrom | cst.RemovalSentinel:
        for unused_import, names in self.unused_imports.items():
            if m.matches(updated_node, unused_import):
                unused_import_names = names
                break
        else:
            return updated_node

        names_to_keep = []
        names = updated_node.names
        if isinstance(names, cst.ImportStar):
            raise NotImplementedError("Not impolemented for ImportStar.")
        for name in names:
            asname = name.asname
            if asname is not None:
                if not isinstance(asname.name, cst.Name):
                    raise NotImplementedError(
                        f"Not implemented when {asname.name} is a list or tuple."
                    )
                name_value = asname.name.value
            else:
                name_value = name.name.value
            if name_value not in unused_import_names:
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
