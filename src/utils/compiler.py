"""Java 编译与运行工具。"""

import subprocess
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass

from src.utils.java_compat import format_java6_compatibility_errors


@dataclass
class CompileResult:
    success: bool
    output: str
    errors: str
    return_code: int


@dataclass
class TestRunResult:
    success: bool
    output: str
    errors: str
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0


class JavaCompiler:
    """Java 编译和测试运行工具。"""

    def __init__(self, java_home: str = None, compile_timeout: int = 30, test_timeout: int = 60):
        self.java_home = java_home or os.environ.get("JAVA_HOME", "")
        self.compile_timeout = compile_timeout
        self.test_timeout = test_timeout

    @property
    def javac(self) -> str:
        if self.java_home:
            return str(Path(self.java_home) / "bin" / "javac")
        return "javac"

    @property
    def java(self) -> str:
        if self.java_home:
            return str(Path(self.java_home) / "bin" / "java")
        return "java"

    def compile(self, java_file: str, classpath: str = None, output_dir: str = None) -> CompileResult:
        """编译 Java 文件。"""
        cmd = [self.javac]
        if classpath:
            cmd.extend(["-cp", classpath])
        if output_dir:
            cmd.extend(["-d", output_dir])
            os.makedirs(output_dir, exist_ok=True)
        cmd.append(java_file)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.compile_timeout,
            )
            return CompileResult(
                success=result.returncode == 0,
                output=result.stdout,
                errors=result.stderr,
                return_code=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(
                success=False,
                output="",
                errors="Compilation timed out",
                return_code=-1,
            )
        except FileNotFoundError:
            return CompileResult(
                success=False,
                output="",
                errors=f"javac not found. JAVA_HOME={self.java_home}",
                return_code=-1,
            )

    def compile_test(self, test_code: str, source_file: str = None, classpath: str = None) -> CompileResult:
        """编译测试代码字符串，返回编译结果。"""
        if not test_code or not test_code.strip():
            return CompileResult(
                success=False,
                output="",
                errors="Generated test code is empty",
                return_code=-1,
            )

        # 从代码中提取类名
        class_name = self._extract_class_name(test_code)
        if not class_name:
            return CompileResult(
                success=False,
                output="",
                errors="Generated test code does not contain a Java class declaration",
                return_code=-1,
            )

        if source_file and self._requires_java6_compatibility(source_file):
            compatibility_errors = format_java6_compatibility_errors(test_code)
            if compatibility_errors:
                return CompileResult(
                    success=False,
                    output="",
                    errors=compatibility_errors,
                    return_code=2,
                )

        # 写入临时文件
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / f"{class_name}.java"
            test_file.write_text(test_code, encoding="utf-8")

            # 构建 classpath
            cp_parts = []
            if classpath:
                cp_parts.append(classpath)
            if source_file:
                cp_parts.extend(self._classpath_for_source_file(source_file))

            cp = os.pathsep.join(cp_parts) if cp_parts else None
            return self.compile(str(test_file), classpath=cp, output_dir=tmpdir)

    def _classpath_for_source_file(self, source_file: str) -> list[str]:
        """Build a useful compile classpath for a Java source file."""
        source_path = Path(source_file).resolve()
        project_root = self._find_maven_project_root(source_path)
        if not project_root:
            return [str(source_path.parent)]

        cp_parts = [
            str(project_root / "src" / "main" / "java"),
            str(project_root / "target" / "classes"),
        ]
        maven_cp = self._maven_test_classpath(project_root)
        if maven_cp:
            cp_parts.extend(maven_cp.split(os.pathsep))
        return [part for part in cp_parts if part]

    def _find_maven_project_root(self, path: Path) -> Path | None:
        """Find the nearest parent directory containing pom.xml."""
        current = path.parent if path.is_file() else path
        for candidate in [current, *current.parents]:
            if (candidate / "pom.xml").exists():
                return candidate
        return None

    def _requires_java6_compatibility(self, source_file: str) -> bool:
        normalized = str(source_file).replace("\\", "/").lower()
        return "/defects4j-work/" in normalized and "/lang-1b/" in normalized

    def _maven_test_classpath(self, project_root: Path) -> str:
        """Ask Maven for the test classpath when pom.xml is available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cp_file = Path(tmpdir) / "test-classpath.txt"
            cmd = [
                "mvn",
                "-q",
                "dependency:build-classpath",
                f"-Dmdep.outputFile={cp_file}",
                "-Dmdep.includeScope=test",
            ]
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                    timeout=max(self.compile_timeout, 120),
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return ""

            if result.returncode != 0 or not cp_file.exists():
                return ""
            return cp_file.read_text(encoding="utf-8").strip()

    def _extract_class_name(self, java_code: str) -> str:
        """从 Java 代码中提取类名。"""
        for line in java_code.split("\n"):
            line = line.strip()
            if "class " in line and ("{" in line or line.endswith("{")):
                parts = line.split("class ")
                if len(parts) > 1:
                    name = parts[1].split()[0].strip("{").strip()
                    return name
        return None
