from collections.abc import Mapping
from typing import TypeVar

import libcst as cst
from libcst.metadata import MetadataWrapper

_T = TypeVar("_T")


class Module:
    def __init__(self, module: cst.Module):
        self.history: list[cst.Module] = []
        self.tree = module

    @classmethod
    def from_content(cls, content: str) -> "Module":
        return cls(cst.parse_module(content))

    def get_content(self) -> str:
        return self.tree.code

    def update(self, new_tree: cst.Module):
        self.history.append(self.tree)
        self.tree = new_tree

    def visit(self, visitor: cst.CSTVisitorT) -> cst.Module:
        self.update(self.tree.visit(visitor))
        return self.tree

    def visit_with_metadata(self, visitor: cst.CSTVisitorT) -> cst.Module:
        wrapper = MetadataWrapper(self.tree)
        self.update(wrapper.visit(visitor))
        return self.tree

    def resolve_metadata(
        self, provider: type[cst.BaseMetadataProvider[_T]]
    ) -> Mapping[cst.CSTNode, _T]:
        wrapper = MetadataWrapper(self.tree)
        return wrapper.resolve(provider)
