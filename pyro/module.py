import ast
from collections.abc import Container, Generator


def filter_node_types(
    generator: "Generator[Module, None, None]", node_types: Container
) -> "Generator[Module, None, None]":
    for item in generator:
        if type(item.ast) in node_types:
            yield item


def get_first_node(generator: "Generator[Module, None, None]") -> "Module":
    return next(generator)


class FilterNodeTransformer(ast.NodeTransformer):
    def __init__(self, node) -> None:
        super().__init__()
        self.node = node

    def generic_visit(self, node: ast.AST) -> ast.AST | None:
        if node is self.node:
            return None
        node = super().generic_visit(node)
        return node


class Module:
    def __init__(self, node: ast.AST):
        self.ast = node

    @classmethod
    def from_content(cls, content: str) -> "Module":
        return cls(ast.parse(content, type_comments=True))

    def get_content(self) -> str:
        return ast.unparse(self.ast)

    def is_at(self, lineno: int, col_offset: int) -> bool:
        if not hasattr(self.ast, "lineno"):
            correct_line = True
        else:
            correct_line = self.ast.lineno <= lineno
            if self.ast.end_lineno is not None:
                correct_line = correct_line and lineno <= self.ast.end_lineno
        if not hasattr(self.ast, "col_offset"):
            correct_col = True
        else:
            correct_col = self.ast.col_offset <= col_offset
            if self.ast.end_col_offset is not None:
                correct_col = (
                    correct_col and col_offset <= self.ast.end_col_offset
                )
        return correct_line and correct_col

    def at(
        self, lineno: int, col_offset: int
    ) -> "Generator[Module, None, None]":
        for item in ast.walk(self.ast):
            if self.is_at(lineno, col_offset):
                yield Module(item)

    def _get_insert_location_after(self, after: Container) -> int:
        assert hasattr(self.ast, "body")

        last_index: int | None = None
        for k, node in enumerate(self.ast.body):  # type: ignore
            if type(node) not in after and last_index is not None:
                break
            if type(node) in after:
                last_index = k

        if last_index is None:
            return 0

        return last_index + 1

    def _get_insert_location_before(self, before: Container) -> int:
        assert hasattr(self.ast, "body")

        for k, node in enumerate(self.ast.body):  # type: ignore
            if type(node) in before:
                return k

        return 0

    def get_insert_location(
        self,
        before: Container | None = None,
        after: Container | None = None,
    ) -> int:
        assert hasattr(self.ast, "body")

        location_before = (
            len(self.ast.body) - 1  # type: ignore
            if before is None
            else self._get_insert_location_before(before)
        )
        location_after = (
            0 if after is None else self._get_insert_location_after(after)
        )
        return min(location_before, location_after)

    def add_node(
        self,
        node: ast.AST,
        location: int | None = None,
        before: Container | None = None,
        after: Container | None = None,
    ) -> None:
        if not hasattr(self.ast, "body"):
            raise ValueError("Cannot add node into this type of node")

        if location is None:
            location = self.get_insert_location(before, after)

        self.ast.body.insert(location, node)  # type: ignore
        ast.fix_missing_locations(self.ast)

    def filter_node(self, node: ast.AST) -> None:
        self.ast = ast.fix_missing_locations(
            FilterNodeTransformer(node).visit(self.ast)
        )
