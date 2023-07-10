from collections import defaultdict
from collections.abc import Iterable

import libcst as cst
from libcst.metadata import Assignment, Scope


def _find_unused_imports(
    scopes,
) -> dict[cst.Import | cst.ImportFrom, set[str]]:
    """
    Inspired from libCST scope analysis tutorial.
    """
    unused_imports: dict[cst.Import | cst.ImportFrom, set[str]] = defaultdict(
        set
    )
    for scope in scopes:
        for assignment in scope.assignments:
            node = assignment.node  # type: ignore
            if isinstance(assignment, Assignment) and isinstance(
                node, (cst.Import, cst.ImportFrom)
            ):
                if len(assignment.references) == 0:
                    unused_imports[node].add(assignment.name)
    return unused_imports


class RemoveUnusedImports(cst.CSTTransformer):
    """
    Inspired from libCST scope analysis tutorial.
    """

    def __init__(self, scopes: Iterable[Scope]) -> None:
        super().__init__()

        self._scopes = scopes
        self.unused_imports = _find_unused_imports(self._scopes)

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
