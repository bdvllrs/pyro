import ast
from collections.abc import Container, Generator


def filter_node_types(
    generator: "Generator[Module, None, None]",
    node_types: Container[type[ast.AST]],
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
        return super().generic_visit(node)


class AddImport(ast.NodeTransformer):
    def __init__(self, module: str, name: str) -> None:
        super().__init__()
        self.module = module
        self.name = name
        self.has_been_added = False

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom | None:
        if node.module == self.module:
            for name in node.names:
                if name.name == self.name:
                    self.has_been_added = True
                    return node
            node.names.append(ast.alias(name=self.name, asname=None))
            self.has_been_added = True
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

    def contains_node(
        self, node_type: type[ast.AST], attributes: dict[str, str]
    ) -> bool:
        for item in ast.walk(self.ast):
            if isinstance(item, node_type):
                for k, v in attributes.items():
                    if getattr(item, k) != v:
                        break
                else:
                    return True
        return False

    def _get_insert_location_after(
        self, after: Container[type[ast.AST]]
    ) -> int:
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

    def _get_insert_location_before(
        self, before: Container[type[ast.AST]]
    ) -> int:
        assert hasattr(self.ast, "body")

        for k, node in enumerate(self.ast.body):  # type: ignore
            if type(node) in before:
                return k

        return 0

    def get_insert_location(
        self,
        before: Container[type[ast.AST]] | None = None,
        after: Container[type[ast.AST]] | None = None,
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
        before: Container[type[ast.AST]] | None = None,
        after: Container[type[ast.AST]] | None = None,
    ) -> None:
        if not hasattr(self.ast, "body"):
            raise ValueError("Cannot add node into this type of node")

        if location is None:
            location = self.get_insert_location(before, after)

        self.ast.body.insert(location, node)  # type: ignore
        ast.fix_missing_locations(self.ast)

    def apply_transform(self, transformer: ast.NodeTransformer) -> None:
        self.ast = ast.fix_missing_locations(transformer.visit(self.ast))

    def filter_node(self, node: ast.AST) -> None:
        self.apply_transform(FilterNodeTransformer(node))

    def add_import(self, module: str, name: str) -> None:
        transformer = AddImport(module, name)
        self.apply_transform(transformer)
        if not transformer.has_been_added:
            self.add_node(
                ast.ImportFrom(
                    module=module,
                    names=[ast.alias(name=name, asname=None)],
                    level=0,
                ),
                after=(ast.Import, ast.ImportFrom),
            )
