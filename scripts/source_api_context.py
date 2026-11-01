"""Simple source API baseline, not type resolution or a new generation mechanism."""
import hashlib
from pathlib import Path
import javalang

from scripts.minimal_source_context import context_parts, node_source, declaration_header
from src.utils.focal_target import select_method


def type_name(node):
    if isinstance(node, str):
        return node
    return node.name + ('.' + type_name(node.sub_type) if getattr(node, 'sub_type', None) else '')


def body_members(node):
    body = getattr(node, 'body', []) or []
    return body if isinstance(body, list) else (getattr(body, 'declarations', []) or [])


class SourceIndex:
    """Explicit main-source root and closed SHA manifest; no tests or network access."""
    def __init__(self, root, expected_files):
        self.root = Path(root).resolve()
        self.types = {}
        paths = {p.relative_to(self.root).as_posix(): p for p in self.root.rglob('*.java')}
        if set(paths) != set(expected_files):
            raise ValueError('Main-source set differs from frozen manifest')
        for relative, path in sorted(paths.items()):
            if not path.resolve().is_relative_to(self.root) or any(
                    part.lower() in {'test', 'tests', 'test-classes'} for part in path.relative_to(self.root).parts):
                raise ValueError('Test source or escaping source path')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected_files[relative]:
                raise ValueError('Source hash changed: ' + relative)
            text = raw.decode('utf-8')
            tree = javalang.parse.parse(text)
            tokens = list(javalang.tokenizer.tokenize(text))
            package = tree.package.name if tree.package else ''
            def add(node, prefix):
                name = '.'.join(part for part in (prefix, node.name) if part)
                if name in self.types:
                    raise ValueError('Duplicate declared type: ' + name)
                self.types[name] = {'node': node, 'tree': tree, 'source': text, 'tokens': tokens,
                    'relative_source': relative, 'source_sha256': expected_files[relative], 'package': package}
                for member in body_members(node):
                    if isinstance(member, javalang.tree.TypeDeclaration):
                        add(member, name)
            for node in tree.types:
                add(node, package)

    def resolve(self, name, origin):
        """Only exact names, same package and explicit/wildcard source imports."""
        if name in self.types:
            return name
        candidates = set()
        package = origin['package']
        local = (package + '.' if package else '') + name
        if local in self.types:
            candidates.add(local)
        for imp in origin['tree'].imports:
            if imp.static:
                continue
            if imp.wildcard:
                candidate = imp.path + '.' + name
            elif imp.path.split('.')[-1] == name.split('.')[0]:
                candidate = imp.path + name[len(name.split('.')[0]):]
            else:
                continue
            if candidate in self.types:
                candidates.add(candidate)
        return next(iter(candidates)) if len(candidates) == 1 else None

    def parents(self, name):
        record = self.types[name]
        node = record['node']
        extends = getattr(node, 'extends', None)
        values = extends if isinstance(extends, list) else ([extends] if extends else [])
        values += list(getattr(node, 'implements', None) or [])
        return [(type_name(value), self.resolve(type_name(value), record)) for value in values]

    def api(self, name):
        record = self.types[name]
        node, source, tokens = record['node'], record['source'], record['tokens']
        headers = []
        for field in getattr(node, 'fields', []):
            if 'private' not in field.modifiers:
                headers.append(' '.join(sorted(field.modifiers)) + ' ' + type_name(field.type) +
                    '[]' * len(field.type.dimensions or []) + ' ' + ', '.join(
                        d.name + '[]' * len(d.dimensions or []) for d in field.declarators) + '; [erased field; initializer omitted]')
        for member in body_members(node):
            if isinstance(member, (javalang.tree.MethodDeclaration, javalang.tree.ConstructorDeclaration)) and 'private' not in member.modifiers:
                headers.append(declaration_header(node_source(source, tokens, member)) + ';')
        imports = '\n'.join('import ' + ('static ' if imp.static else '') + imp.path +
            ('.*' if imp.wildcard else '') + ';' for imp in record['tree'].imports)
        text = ('SOURCE API HEADERS: ' + name + '\n' +
            'Declarations only; access modifiers apply. Interface members may have implicit public visibility.\n' +
            'Bodies, field initializers, Javadoc and behavioral preconditions are omitted.\n' +
            imports + '\n' + declaration_header(node_source(source, tokens, node)) + '\n' + '\n'.join(headers))
        return text, {'type': name, 'relative_source': record['relative_source'],
                      'source_sha256': record['source_sha256'], 'header_count': len(headers)}


def build_api_context(method, index, fits):
    """F1 plus declared/ancestor headers; whole direct-dependency blocks if they fit."""
    parts = context_parts(method)
    owner = method['method_owner']
    if owner not in index.types or index.types[owner]['source_sha256'] != method['source_sha256']:
        raise ValueError('Exact owner is missing from frozen source index')
    _, focal = select_method(index.types[owner]['tree'], method['method'], owner, method['method_parameter_types'])
    mandatory_types, unresolved, pending = [], [], [owner]
    while pending:
        name = pending.pop(0)
        if name in mandatory_types:
            continue
        mandatory_types.append(name)
        for raw, resolved in index.parents(name):
            if resolved:
                pending.append(resolved)
            else:
                unresolved.append({'name': raw, 'origin': name, 'reason': 'ancestor_not_uniquely_in_main_source_index'})
    text = parts['mandatory']
    included = []
    for name in mandatory_types:
        block, record = index.api(name)
        text += '\n' + block
        included.append({**record, 'role': 'declaring_or_ancestor_type'})
    mandatory_fits = bool(fits(text))
    names = {type_name(node) for _, node in focal.filter(javalang.tree.ReferenceType)}
    names.update(focal.throws or [])
    names.update(type_name(f.type) for f in getattr(index.types[owner]['node'], 'fields', []))
    # Static call qualifiers are only name candidates, not resolved receiver types.
    names.update(call.qualifier.split('.')[0] for _, call in focal.filter(javalang.tree.MethodInvocation)
                 if call.qualifier and call.qualifier.split('.')[0][:1].isupper())
    dependencies = set()
    for raw in sorted(names):
        resolved = index.resolve(raw, index.types[owner])
        if resolved:
            if resolved not in mandatory_types:
                dependencies.add(resolved)
        else:
            unresolved.append({'name': raw, 'origin': owner, 'reason': 'not_uniquely_in_main_source_index'})
    excluded = []
    for name in sorted(dependencies):
        block, record = index.api(name)
        candidate = text + '\n' + block
        if fits(candidate):
            text = candidate
            included.append({**record, 'role': 'direct_syntactic_dependency'})
        else:
            excluded.append({**record, 'reason': 'context_budget'})
    return {'F3': text, 'mandatory_fits': mandatory_fits, 'included_api_types': included,
        'excluded_api_types': excluded, 'unresolved_type_candidates': unresolved,
        'focal_sha256': parts['focal_sha256'], 'source_sha256': parts['source_sha256'],
        'limits': ['Simple source headers, not a type checker, full hierarchy contract or new algorithm.',
                   'Exact focal declaration and whole owner/ancestor API blocks are never truncated.',
                   'Only direct syntactic type-name candidates; no recursive dependency closure or API bodies.',
                   'Unresolved or excluded types do not mean unavailable; no tests or evaluation answers used.']}
