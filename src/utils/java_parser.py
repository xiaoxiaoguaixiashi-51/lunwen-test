"""Java 源码解析工具，优先基于 javalang，缺依赖时使用轻量兜底解析。"""

import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import javalang
except ImportError:
    javalang = None


@dataclass
class DependencyInfo:
    """目标方法的依赖信息。"""
    method_name: str = ""
    class_name: str = ""
    imports: list[str] = field(default_factory=list)
    external_calls: list[dict] = field(default_factory=list)  # [{target, method, args}]
    field_dependencies: list[dict] = field(default_factory=list)  # [{name, type, is_static}]
    constructor_params: list[dict] = field(default_factory=list)  # [{name, type}]
    exceptions_thrown: list[str] = field(default_factory=list)
    has_time_dependency: bool = False
    has_random_dependency: bool = False
    has_io_dependency: bool = False
    parameters: list[dict] = field(default_factory=list)  # [{name, type}]
    return_type: str = ""

    def to_dict(self) -> dict:
        return {
            "method_name": self.method_name,
            "class_name": self.class_name,
            "imports": self.imports,
            "external_calls": self.external_calls,
            "field_dependencies": self.field_dependencies,
            "constructor_params": self.constructor_params,
            "exceptions_thrown": self.exceptions_thrown,
            "has_time_dependency": self.has_time_dependency,
            "has_random_dependency": self.has_random_dependency,
            "has_io_dependency": self.has_io_dependency,
            "parameters": self.parameters,
            "return_type": self.return_type,
        }


def parse_java_file(file_path: str):
    """解析 Java 文件为 AST。"""
    if javalang is None:
        raise RuntimeError("javalang is required for full AST parsing. Run: pip install -r requirements.txt")

    source = Path(file_path).read_text(encoding="utf-8")
    return javalang.parse.parse(source)


def extract_dependencies(file_path: str, method_name: str = None) -> DependencyInfo:
    """从 Java 文件中提取目标方法的依赖信息。

    如果 method_name 为 None，则分析文件中第一个 public 方法。
    """
    source = Path(file_path).read_text(encoding="utf-8")
    if javalang is None:
        return _extract_dependencies_fallback(source, method_name, file_path)

    tree = parse_java_file(file_path)
    info = DependencyInfo()

    # 提取 imports
    for imp in tree.imports:
        info.imports.append(imp.path)

    # 找到目标类
    for _, class_decl in tree.filter(javalang.tree.ClassDeclaration):
        info.class_name = class_decl.name

        # 提取构造函数参数（即字段依赖）
        for _, constructor in class_decl.filter(javalang.tree.ConstructorDeclaration):
            for param in constructor.parameters:
                param_type = _get_type_name(param.type)
                info.constructor_params.append({
                    "name": param.name,
                    "type": param_type,
                })

        # 提取字段
        for _, field_decl in class_decl.filter(javalang.tree.FieldDeclaration):
            for declarator in field_decl.declarators:
                is_static = "static" in (field_decl.modifiers or set())
                info.field_dependencies.append({
                    "name": declarator.name,
                    "type": _get_type_name(field_decl.type),
                    "is_static": is_static,
                })

        # 找到目标方法
        for _, method_decl in class_decl.filter(javalang.tree.MethodDeclaration):
            if method_name and method_decl.name != method_name:
                continue
            if not method_name and "public" not in (method_decl.modifiers or set()):
                continue

            info.method_name = method_decl.name
            info.return_type = _get_type_name(method_decl.return_type) if method_decl.return_type else "void"

            # 方法参数
            for param in (method_decl.parameters or []):
                info.parameters.append({
                    "name": param.name,
                    "type": _get_type_name(param.type),
                })

            # 异常声明
            for throw in (method_decl.throws or []):
                info.exceptions_thrown.append(throw)

            # 分析方法体中的调用
            if method_decl.body:
                _analyze_method_body(method_decl.body, info)

            if method_name or info.method_name:
                break
        break

    if not info.method_name:
        target = method_name or "first public method"
        raise ValueError(f"Method not found in {file_path}: {target}")

    return info


def _get_type_name(type_node) -> str:
    """从类型节点提取类型名称。"""
    if type_node is None:
        return "void"
    if isinstance(type_node, javalang.tree.ReferenceType):
        name = type_node.name
        if type_node.arguments:
            args = ", ".join(_get_type_name(a.type) for a in type_node.arguments if a.type)
            name += f"<{args}>"
        return name
    if isinstance(type_node, javalang.tree.BasicType):
        return type_node.name
    return str(type_node)


def _analyze_method_body(body: list, info: DependencyInfo):
    """分析方法体，提取外部调用和特殊依赖。"""
    time_indicators = {"LocalDateTime", "Instant", "Clock", "System.currentTimeMillis", "now"}
    random_indicators = {"Random", "ThreadLocalRandom", "Math.random"}
    io_indicators = {"File", "InputStream", "OutputStream", "Socket", "URL", "HttpClient"}

    source_repr = str(body)

    for indicator in time_indicators:
        if indicator in source_repr:
            info.has_time_dependency = True
            break

    for indicator in random_indicators:
        if indicator in source_repr:
            info.has_random_dependency = True
            break

    for indicator in io_indicators:
        if indicator in source_repr:
            info.has_io_dependency = True
            break

    # 提取方法调用（简化版，基于字符串匹配 AST 节点）
    _extract_invocations(body, info)


def _extract_invocations(nodes, info: DependencyInfo):
    """递归提取方法调用。"""
    if isinstance(nodes, list):
        for node in nodes:
            _extract_invocations(node, info)
    elif hasattr(nodes, '__dict__'):
        if isinstance(nodes, javalang.tree.MethodInvocation):
            call = {
                "target": nodes.qualifier or "this",
                "method": nodes.member,
                "args_count": len(nodes.arguments) if nodes.arguments else 0,
            }
            info.external_calls.append(call)
        for child in getattr(nodes, 'children', []):
            if child is not None:
                _extract_invocations(child, info)


def _extract_dependencies_fallback(source: str, method_name: str = None, file_path: str = "") -> DependencyInfo:
    """轻量解析器：用于本地没安装 javalang 时跑离线测试和示例 smoke test。"""
    info = DependencyInfo()
    info.imports = re.findall(r"^\s*import\s+([\w.*]+)\s*;", source, flags=re.MULTILINE)

    class_match = re.search(r"\bclass\s+(\w+)\b", source)
    if not class_match:
        raise ValueError(f"Class not found in {file_path or '<source>'}")
    info.class_name = class_match.group(1)

    _extract_fields_fallback(source, info)
    _extract_constructor_fallback(source, info)

    method_match = _find_method_signature(source, method_name)
    if not method_match:
        target = method_name or "first public method"
        raise ValueError(f"Method not found in {file_path or '<source>'}: {target}")

    info.return_type = _normalize_type(method_match.group("return_type"))
    info.method_name = method_match.group("name")
    info.parameters = _parse_params_fallback(method_match.group("params"))
    throws = method_match.group("throws") or ""
    info.exceptions_thrown = [item.strip() for item in throws.split(",") if item.strip()]

    body = _extract_braced_block(source, method_match.end() - 1)
    _analyze_source_body_fallback(body, info)
    return info


def _extract_fields_fallback(source: str, info: DependencyInfo):
    field_pattern = re.compile(
        r"^\s*(?:private|protected|public)\s+"
        r"(?P<static>static\s+)?(?:final\s+)?"
        r"(?P<type>[\w.<>, ?\[\]]+)\s+"
        r"(?P<name>\w+)\s*(?:=|;)",
        flags=re.MULTILINE,
    )
    for match in field_pattern.finditer(source):
        if match.group("name") == info.class_name:
            continue
        info.field_dependencies.append({
            "name": match.group("name"),
            "type": _normalize_type(match.group("type")),
            "is_static": bool(match.group("static")),
        })


def _extract_constructor_fallback(source: str, info: DependencyInfo):
    pattern = re.compile(rf"\b{re.escape(info.class_name)}\s*\((?P<params>[^)]*)\)")
    for match in pattern.finditer(source):
        prefix = source[max(0, match.start() - 40):match.start()]
        if any(keyword in prefix for keyword in ("new ", "return ")):
            continue
        info.constructor_params.extend(_parse_params_fallback(match.group("params")))
        break


def _find_method_signature(source: str, method_name: str = None):
    if method_name:
        name_pattern = re.escape(method_name)
    else:
        name_pattern = r"\w+"

    pattern = re.compile(
        rf"\bpublic\s+(?:static\s+)?(?P<return_type>[\w.<>, ?\[\]]+)\s+"
        rf"(?P<name>{name_pattern})\s*\((?P<params>[^)]*)\)"
        rf"\s*(?:throws\s+(?P<throws>[\w.,\s]+))?\s*\{{",
        flags=re.MULTILINE,
    )
    return pattern.search(source)


def _parse_params_fallback(params_text: str) -> list[dict]:
    params = []
    if not params_text.strip():
        return params
    for raw_param in params_text.split(","):
        pieces = raw_param.strip().replace("final ", "").split()
        if len(pieces) < 2:
            continue
        params.append({
            "name": pieces[-1],
            "type": _normalize_type(" ".join(pieces[:-1])),
        })
    return params


def _extract_braced_block(source: str, open_brace_index: int) -> str:
    depth = 0
    for index in range(open_brace_index, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace_index + 1:index]
    return source[open_brace_index + 1:]


def _analyze_source_body_fallback(body: str, info: DependencyInfo):
    info.has_time_dependency = any(token in body for token in ("LocalDateTime", "Instant", "Clock", "currentTimeMillis", ".now("))
    info.has_random_dependency = any(token in body for token in ("Random", "ThreadLocalRandom", "Math.random"))
    info.has_io_dependency = any(token in body for token in ("File", "InputStream", "OutputStream", "Socket", "URL", "HttpClient"))

    skip_methods = {"if", "for", "while", "switch", "catch", "throw", "return", "new"}
    for match in re.finditer(r"(?:(?P<target>\b\w+)\s*\.)?(?P<method>\b\w+)\s*\(", body):
        method = match.group("method")
        if method in skip_methods or method == info.method_name:
            continue
        info.external_calls.append({
            "target": match.group("target") or "this",
            "method": method,
            "args_count": _count_args_fallback(body, match.end() - 1),
        })


def _count_args_fallback(source: str, open_paren_index: int) -> int:
    args = _extract_parenthesized_block(source, open_paren_index).strip()
    if not args:
        return 0
    depth = 0
    count = 1
    for char in args:
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
        elif char == "," and depth == 0:
            count += 1
    return count


def _extract_parenthesized_block(source: str, open_paren_index: int) -> str:
    depth = 0
    for index in range(open_paren_index, len(source)):
        char = source[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren_index + 1:index]
    return source[open_paren_index + 1:]


def _normalize_type(type_text: str) -> str:
    return " ".join(type_text.replace("\n", " ").split())
