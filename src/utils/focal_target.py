"""Resolve a Java focal method by declaring type and erased parameter types."""

from __future__ import annotations

import javalang


def parameter_types(method) -> list[str]:
    result = []
    for parameter in method.parameters:
        node = parameter.type
        names = [node.name]
        child = getattr(node, "sub_type", None)
        while child is not None:
            names.append(child.name)
            child = getattr(child, "sub_type", None)
        dimensions = len(getattr(node, "dimensions", None) or []) + int(parameter.varargs)
        result.append(".".join(names) + "[]" * dimensions)
    return result


def select_method(tree, method_name: str, owner: str, types: list[str] | None = None):
    package = tree.package.name + "." if tree.package else ""
    candidates = []
    for path, method in tree.filter(javalang.tree.MethodDeclaration):
        if method.name != method_name:
            continue
        declarations = [node for node in path if isinstance(node, javalang.tree.TypeDeclaration)]
        if not declarations or any(isinstance(node, javalang.tree.ClassCreator) for node in path):
            continue
        chain = ".".join(node.name for node in declarations)
        normalized_owner = owner.replace("$", ".")
        if normalized_owner not in {chain, package + chain}:
            continue
        if types is not None and parameter_types(method) != types:
            continue
        candidates.append((declarations[-1], method))
    if len(candidates) != 1:
        raise ValueError(
            f"Expected one focal declaration for {owner}.{method_name}({types}); "
            f"found {len(candidates)}"
        )
    return candidates[0]
