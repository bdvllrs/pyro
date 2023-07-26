from collections.abc import Iterable, Sequence
import libcst as cst
import libcst.matchers as m
from typing import Any

from libcst.metadata import Assignment, GlobalScope, Scope, ScopeProvider
from pyro.module import Module


from pyro.project import Project
from pyro.refactorings.imports import attribute_matcher_from_module_name


class ReorderFuncDefArgs(cst.CSTTransformer):
    def __init__(self, func_name: str, new_order: Sequence[int]):
        self.func_name = func_name
        self.new_order = new_order
        self.order: list[int] = []

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        if original_node.name.value == self.func_name:
            params: list[cst.Param | cst.ParamSlash] = []
            has_pos_params = False
            slash_index: int = len(self.new_order)
            for param in original_node.params.posonly_params:
                params.append(param)
            if isinstance(original_node.params.posonly_ind, cst.ParamSlash):
                params.append(original_node.params.posonly_ind)
                has_pos_params = True
                slash_index = len(params) - 1
            for param in original_node.params.params:
                params.append(param)
            assert len(self.new_order) == len(params)
            posonly_params: list[cst.Param] = []
            generic_params: list[cst.Param] = []
            after_slash = False
            for i in range(len(params)):
                param = params[self.new_order[i]]
                if isinstance(param, cst.ParamSlash):
                    after_slash = True
                    continue
                assert isinstance(param, cst.Param)

                if has_pos_params and not after_slash:
                    posonly_params.append(
                        param.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                    )
                else:
                    generic_params.append(
                        param.with_changes(comma=cst.MaybeSentinel.DEFAULT)
                    )
            for k, order in enumerate(self.new_order):
                if k == slash_index:
                    continue
                if slash_index + 1 < k:
                    self.order.append(order - 1)
                else:
                    self.order.append(order)
            return updated_node.with_changes(
                params=updated_node.params.with_changes(
                    params=generic_params, posonly_params=posonly_params
                )
            )

        return updated_node


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
                m.AtLeastN(
                    n=1,
                    matcher=m.ImportAlias(
                        name=attribute_matcher_from_module_name(names)
                    ),
                )
            ],
        ),
    )
    if is_matching:
        return True
    return is_import_from_of_module(list(module) + [names[0]], names[1:], node)


def sequence_from_attr(node: cst.BaseExpression) -> list[str]:
    if isinstance(node, cst.Name):
        return [node.value]
    elif isinstance(node, cst.Attribute):
        return sequence_from_attr(node.value) + [node.attr.value]
    raise ValueError(f"Expected Name or Attribute, got {node}")


def reorder_args(
    args: Sequence[cst.Arg], new_order: Sequence[int]
) -> list[cst.Arg]:
    new_args: list[cst.Arg] = []
    for i in new_order:
        new_args.append(args[i].with_changes(comma=cst.MaybeSentinel.DEFAULT))
    return new_args


class ReorderFuncCallArgs(cst.CSTTransformer):
    def __init__(
        self,
        scopes: Iterable[Scope | None],
        module_name: Sequence[str],
        new_order: Sequence[int],
    ):
        self._scopes = scopes
        self.module_name = module_name
        self.new_order = new_order

    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.Call:
        for scope in self._scopes:
            if isinstance(scope, GlobalScope):
                for assignment in scope.assignments:
                    if isinstance(assignment, Assignment) and isinstance(
                        assignment.node, (cst.ImportFrom)
                    ):
                        for access in assignment.references:
                            access_elems = sequence_from_attr(access.node)
                            if not is_import_from_of_module(
                                [self.module_name[0]],
                                list(self.module_name[1:]) + access_elems[1:],
                                assignment.node,
                            ):
                                continue
                            if original_node.func == access.node:
                                new_args = reorder_args(
                                    updated_node.args, self.new_order
                                )
                                return updated_node.with_changes(args=new_args)
        return updated_node


def reorder_func_arg(
    project: Project,
    source_mod_name: str,
    func_name: str,
    new_order: Sequence[int],
) -> dict[str, Any]:
    source_mod = project.get_module(source_mod_name)

    func_reorderer = ReorderFuncDefArgs(func_name, new_order)
    source_mod.visit(func_reorderer)

    modules_to_save: list[tuple[str, Module]] = [(source_mod_name, source_mod)]

    for module_name, module in project.walk_modules():
        if module_name == source_mod_name:
            continue

        wrapper = cst.MetadataWrapper(module.tree)
        scopes = set(wrapper.resolve(ScopeProvider).values())
        reorderer = ReorderFuncCallArgs(
            scopes,
            source_mod_name.split(".") + [func_name],
            func_reorderer.order,
        )
        module.visit_with_metadata(wrapper, reorderer)
        modules_to_save.append((module_name, module))

    for mod_name, mod in modules_to_save:
        project.save_module(mod_name, mod)

    return {"success": True}
