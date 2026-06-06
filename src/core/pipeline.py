"""端到端 Pipeline：串联 TaskAgent → PlanAgent → GenerationAgent → 编译反馈。"""

import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field

from src.core.llm_client import LLMClient, load_config
from src.agents.task_agent import TaskAgent
from src.agents.plan_agent import PlanAgent
from src.agents.generation_agent import GenerationAgent
from src.utils.compiler import JavaCompiler, CompileResult


@dataclass
class PipelineResult:
    """Pipeline 执行结果。"""
    target_file: str
    method_name: str
    dependency_analysis: dict = field(default_factory=dict)
    test_plan: dict = field(default_factory=dict)
    generated_test: str = ""
    compile_results: list = field(default_factory=list)
    final_test: str = ""
    success: bool = False
    iterations: int = 0

    def to_dict(self) -> dict:
        return {
            "target_file": self.target_file,
            "method_name": self.method_name,
            "dependency_analysis": self.dependency_analysis,
            "test_plan": self.test_plan,
            "generated_test_length": len(self.generated_test),
            "compile_attempts": len(self.compile_results),
            "success": self.success,
            "iterations": self.iterations,
            "final_test_preview": self.final_test[:500] if self.final_test else "",
        }


class Pipeline:
    """端到端测试生成 Pipeline。"""

    def __init__(self, config: dict = None, llm_client=None, compiler=None):
        if config is None:
            config = {}

        self.llm = llm_client or LLMClient(config or load_config())
        self.task_agent = TaskAgent(self.llm)
        self.plan_agent = PlanAgent(self.llm)
        self.generation_agent = GenerationAgent(self.llm)
        self.compiler = compiler or JavaCompiler(
            java_home=config.get("java", {}).get("home", ""),
            compile_timeout=config.get("java", {}).get("compile_timeout", 30),
            test_timeout=config.get("java", {}).get("test_timeout", 60),
        )
        self.max_fix_iterations = config.get("pipeline", {}).get("max_fix_iterations", 3)
        self.feedback_enabled = config.get("pipeline", {}).get("feedback_enabled", True)

    def run(self, java_file_path: str, method_name: str = None, output_dir: str = None) -> PipelineResult:
        """执行完整 pipeline。"""
        result = PipelineResult(target_file=java_file_path, method_name=method_name or "")
        source_code = Path(java_file_path).read_text(encoding="utf-8")

        # Step 1: 依赖分析
        print("[1/4] TaskAgent: 分析依赖...")
        result.dependency_analysis = self.task_agent.analyze(java_file_path, method_name)
        result.method_name = result.dependency_analysis["static_analysis"]["method_name"]
        print(f"      识别到方法: {result.method_name}")
        print(f"      外部调用数: {len(result.dependency_analysis['static_analysis']['external_calls'])}")

        # Step 2: 生成测试计划
        print("[2/4] PlanAgent: 生成测试计划...")
        result.test_plan = self.plan_agent.generate_plan(
            result.dependency_analysis, source_code
        )
        if "test_cases" in result.test_plan:
            print(f"      生成测试场景: {len(result.test_plan['test_cases'])} 个")
        else:
            print("      警告: 测试计划解析可能有问题")

        # Step 3: 生成测试代码
        print("[3/4] GenerationAgent: 生成测试代码...")
        result.generated_test = self.generation_agent.generate(
            result.test_plan,
            source_code,
            result.dependency_analysis,
            source_file=java_file_path,
        )
        result.final_test = result.generated_test
        print(f"      生成代码长度: {len(result.generated_test)} 字符")

        # Step 4: 编译反馈循环
        if self.feedback_enabled:
            print("[4/4] 编译反馈循环...")
            (
                result.final_test,
                result.success,
                result.iterations,
                result.compile_results,
            ) = self._compile_feedback_loop(
                result.generated_test, source_code, source_file=java_file_path
            )
            if result.success:
                print(f"      编译成功（第 {result.iterations} 轮）")
            else:
                print(f"      编译失败（已尝试 {result.iterations} 轮）")
        else:
            print("[4/4] 跳过编译反馈（已禁用）")

        # 保存结果
        if output_dir:
            self._save_results(result, output_dir)

        return result

    def _compile_feedback_loop(
        self, test_code: str, source_code: str, source_file: str = None
    ) -> tuple[str, bool, int, list]:
        """编译反馈循环：尝试编译，失败则修复。"""
        current_code = test_code
        compile_results = []

        for i in range(1, self.max_fix_iterations + 1):
            compile_result = self.compiler.compile_test(current_code, source_file=source_file)
            compile_results.append(compile_result)

            if compile_result.success:
                return current_code, True, i, compile_results

            print(f"      第 {i} 轮编译失败: {compile_result.errors[:100]}...")

            # 让 GenerationAgent 修复
            current_code = self.generation_agent.fix_compilation_error(
                current_code,
                compile_result.errors,
                source_code,
                source_file=source_file,
            )

        return current_code, False, self.max_fix_iterations, compile_results

    def _save_results(self, result: PipelineResult, output_dir: str):
        """保存生成结果到文件。"""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # 保存测试代码
        test_file = out_path / f"{result.method_name}Test.java"
        test_file.write_text(result.final_test, encoding="utf-8")

        # 保存分析报告
        report_file = out_path / f"{result.method_name}_report.json"
        report_file.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n结果已保存到: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Java 单元测试生成 Pipeline")
    parser.add_argument("--target", required=True, help="目标 Java 文件路径")
    parser.add_argument("--method", default=None, help="目标方法名（默认分析第一个 public 方法）")
    parser.add_argument("--output", default="examples/generated_tests", help="输出目录")
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args()

    config = load_config(args.config)
    pipeline = Pipeline(config)
    result = pipeline.run(args.target, args.method, args.output)

    print("\n" + "=" * 50)
    print(f"Pipeline 完成: {'成功' if result.success else '失败'}")
    print(f"目标方法: {result.method_name}")
    print(f"编译尝试: {result.iterations} 轮")
    print("=" * 50)


if __name__ == "__main__":
    main()
