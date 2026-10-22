"""Bounded, source-grounded import declarations; no retrieval filtering or graph claims."""

import hashlib
from pathlib import Path

import javalang


def declaration_context(target, source_roots, max_chars=12000):
    target = Path(target)
    tree = javalang.parse.parse(target.read_text(encoding="utf-8"))
    records = []
    used = 0
    names = [item.path for item in tree.imports if not item.static and not item.wildcard]
    for declaration in tree.types:
        inherited = getattr(declaration, "extends", None)
        inherited = inherited if isinstance(inherited, list) else [inherited]
        inherited += getattr(declaration, "implements", None) or []
        for parent in inherited:
            if parent and tree.package:
                names.append(tree.package.name + "." + parent.name)
    for name in dict.fromkeys(names):
        relative = Path(*name.split(".")).with_suffix(".java")
        found = None
        for root in source_roots:
            candidate = Path(root) / relative
            if candidate.is_file():
                found = candidate
                break
        if found is None:
            continue
        code = found.read_text(encoding="utf-8")
        try:
            imported = javalang.parse.parse(code)
        except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError):
            continue
        lines = code.splitlines()
        snippets = []
        for declaration in imported.types:
            nodes = [declaration] + [node for node in declaration.body if isinstance(node, (
                javalang.tree.ConstructorDeclaration, javalang.tree.MethodDeclaration))]
            for node in nodes[:17]:
                if not node.position:
                    continue
                header = " ".join(lines[node.position.line - 1:node.position.line + 7])
                endings = [offset for symbol in ("{", ";") if (offset := header.find(symbol)) >= 0]
                snippets.append(header[:min(endings)] if endings else header[:250])
        text = "\n".join(snippets)[:1800]
        record = {"fqcn": name, "source": str(found), "partial_declarations": True,
                  "sha256": hashlib.sha256(found.read_bytes()).hexdigest(), "declarations": text}
        if used + len(text) > max_chars:
            break
        records.append(record)
        used += len(text)
    return records


def grounded_context(method, projects_root, include_declarations):
    source = Path(method["target"]).read_text(encoding="utf-8")
    roots = [method["source_root"], Path(projects_root) / method["project_id"] / "src/main/java",
             Path(projects_root) / method["project_id"] / "core/src/java"]
    declarations = declaration_context(method["target"], roots) if include_declarations else []
    context = "Focal source (bounded):\n```java\n" + source[:30000] + "\n```"
    if declarations:
        import json
        context += "\nActual dependency declarations:\n" + json.dumps(declarations, ensure_ascii=False)
    return {"target_sha256": hashlib.sha256(Path(method["target"]).read_bytes()).hexdigest(),
            "source_truncated": len(source) > 30000, "declarations": declarations, "context": context}
