"""Java 编译与运行工具。"""

import subprocess
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass


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

        # 写入临时文件
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / f"{class_name}.java"
            test_file.write_text(test_code, encoding="utf-8")

            # 构建 classpath
            cp_parts = []
            if classpath:
                cp_parts.append(classpath)
            if source_file:
                cp_parts.append(str(Path(source_file).parent))

            cp = os.pathsep.join(cp_parts) if cp_parts else None
            return self.compile(str(test_file), classpath=cp, output_dir=tmpdir)

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
