"""Structural repair checks; not a proof that changed test oracles are correct."""

import javalang


def test_contract(code):
    tree = javalang.parse.parse(code)
    tests = {}
    for path, method in tree.filter(javalang.tree.MethodDeclaration):
        if not any(annotation.name.rsplit(".", 1)[-1] == "Test" for annotation in method.annotations):
            continue
        owner = tuple(node.name for node in path if isinstance(node, javalang.tree.TypeDeclaration))
        assertions = sum(node.member.startswith("assert") or node.member == "fail"
                         for _, node in method.filter(javalang.tree.MethodInvocation))
        assertions += sum(1 for _ in method.filter(javalang.tree.AssertStatement))
        for annotation in method.annotations:
            elements = annotation.element if isinstance(annotation.element, list) else [annotation.element]
            assertions += sum(isinstance(element, javalang.tree.ElementValuePair) and element.name == "expected" for element in elements)
        tests[(owner, method.name)] = assertions
    return tree, tests


def check_repair_integrity(original, repaired):
    errors = []
    try:
        _old_tree, before = test_contract(original)
        tree, after = test_contract(repaired)
    except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError, TypeError):
        return {"ok": False, "errors": ["Java parse failed"], "semantic_review_required": True}
    if not before:
        errors.append("Original has no recognized @Test methods")
    for name, count in before.items():
        if name not in after:
            errors.append(f"Removed or renamed test: {name}")
        elif after[name] < count:
            errors.append(f"Reduced assertions/expected-exception checks: {name}")
    for _, annotation in tree.filter(javalang.tree.Annotation):
        if annotation.name.rsplit(".", 1)[-1] in {"Ignore", "Disabled"}:
            errors.append("Disabled test annotation")
    for _, call in tree.filter(javalang.tree.MethodInvocation):
        if call.member.startswith("assume"):
            errors.append("Assumption-based test bypass")
        if call.member in {"assertTrue", "assertFalse"} and call.arguments:
            last = call.arguments[-1]
            if isinstance(last, javalang.tree.Literal) and last.value in {"true", "false"}:
                errors.append("Literal boolean assertion requires rejection")
    for _, method in tree.filter(javalang.tree.MethodDeclaration):
        if any(annotation.name.rsplit(".", 1)[-1] == "Test" for annotation in method.annotations):
            if method.body and isinstance(method.body[0], javalang.tree.ReturnStatement):
                errors.append("Test returns before exercising code")
    return {"ok": not errors, "errors": errors, "test_count_before": len(before),
            "test_count_after": len(after), "semantic_review_required": True}
