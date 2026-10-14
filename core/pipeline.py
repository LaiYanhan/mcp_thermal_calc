"""
Pipeline DAG execution engine and pipeline registry.
"""

from typing import Any, Dict, List, Optional, Set
from core.formula import FormulaRegistry, registry as default_registry
from core.types import (
    Pin,
    PipelineStep,
    PipelineExecutionResult,
    StepExecutionRecord,
)


class Pipeline:
    """
    声明式计算管道（DAG 拓扑）
    """
    def __init__(
        self,
        id: str,
        name: str,
        category: str,
        description: str,
        notes: str,
        required_inputs: List[Pin],
        steps: List[PipelineStep],
        sizing_output_keys: Optional[List[str]] = None,
        economic_output_keys: Optional[List[str]] = None,
    ):
        self.id = id
        self.name = name
        self.category = category
        self.description = description
        self.notes = notes
        self.required_inputs = required_inputs
        self.steps = steps
        self.sizing_output_keys = sizing_output_keys or []
        self.economic_output_keys = economic_output_keys or []

    def inspect_inputs(self, provided_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查入参完整性，输出已有参数、缺失必填参数与默认值补全
        """
        missing: List[Dict[str, Any]] = []
        filled: Dict[str, Any] = {}
        defaults_applied: Dict[str, Any] = {}

        for pin in self.required_inputs:
            if pin.name in provided_inputs and provided_inputs[pin.name] is not None:
                val = float(provided_inputs[pin.name])
                pin.validate(val)
                filled[pin.name] = val
            elif pin.default_value is not None:
                filled[pin.name] = pin.default_value
                defaults_applied[pin.name] = {
                    "value": pin.default_value,
                    "unit": pin.unit,
                    "description": pin.description
                }
            else:
                missing.append({
                    "name": pin.name,
                    "unit": pin.unit,
                    "description": pin.description,
                    "min": pin.min_value,
                    "max": pin.max_value
                })

        return {
            "is_complete": len(missing) == 0,
            "filled_inputs": filled,
            "defaults_applied": defaults_applied,
            "missing_inputs": missing
        }

    def execute(
        self,
        inputs: Dict[str, Any],
        formula_registry: Optional[FormulaRegistry] = None
    ) -> PipelineExecutionResult:
        """
        按拓扑顺序执行各步骤节点
        """
        reg = formula_registry or default_registry
        inspection = self.inspect_inputs(inputs)
        if not inspection["is_complete"]:
            missing_names = [m["description"] + f"({m['name']})" for m in inspection["missing_inputs"]]
            raise ValueError(f"管道 '{self.name}' 执行失败：缺少必需的输入参数: {', '.join(missing_names)}")

        # 当前变量上下文，以校验填补好的输入为初始基底
        ctx: Dict[str, Any] = dict(inspection["filled_inputs"])
        records: List[StepExecutionRecord] = []

        for step in self.steps:
            formula = reg.get(step.formula_id)
            step_inputs: Dict[str, float] = {}

            # 映射输入
            for formula_pin, ctx_var in step.input_map.items():
                if ctx_var not in ctx:
                    raise KeyError(
                        f"步骤 '{step.step_id}' ({step.description}) 缺少变量 '{ctx_var}'，"
                        f"无法传递给公式 '{step.formula_id}' 的引脚 '{formula_pin}'"
                    )
                step_inputs[formula_pin] = float(ctx[ctx_var])

            # 执行公式
            step_outputs = formula.execute(step_inputs)

            # 映射输出写回全局上下文
            for formula_out_pin, ctx_var in step.output_map.items():
                if formula_out_pin not in step_outputs:
                    raise KeyError(f"公式 '{step.formula_id}' 未产出引脚 '{formula_out_pin}'")
                ctx[ctx_var] = step_outputs[formula_out_pin]

            records.append(
                StepExecutionRecord(
                    step_id=step.step_id,
                    formula_id=step.formula_id,
                    formula_name=formula.metadata.name,
                    inputs=step_inputs,
                    outputs=step_outputs,
                    notes=step.description or formula.metadata.description
                )
            )

        # 汇总主要设备选型
        sizing_summary = {k: ctx[k] for k in self.sizing_output_keys if k in ctx}
        # 汇总经济测算
        economic_summary = {k: ctx[k] for k in self.economic_output_keys if k in ctx}

        return PipelineExecutionResult(
            pipeline_id=self.id,
            pipeline_name=self.name,
            scenario_description=self.description,
            initial_inputs=inspection["filled_inputs"],
            final_outputs=ctx,
            step_records=records,
            sizing_summary=sizing_summary,
            economic_summary=economic_summary
        )


class PipelineRegistry:
    """
    计算管道全局注册表
    """
    def __init__(self):
        self._pipelines: Dict[str, Pipeline] = {}

    def register(self, pipeline: Pipeline) -> None:
        self._pipelines[pipeline.id] = pipeline

    def get(self, pipeline_id: str) -> Pipeline:
        if pipeline_id not in self._pipelines:
            raise KeyError(f"未注册的计算管道ID: '{pipeline_id}'")
        return self._pipelines[pipeline_id]

    def list_all(self) -> List[Pipeline]:
        return list(self._pipelines.values())

    def to_ai_catalog(self) -> List[Dict[str, Any]]:
        """输出供大模型（Agent）场景匹配的场景清单"""
        catalog = []
        for p in self._pipelines.values():
            catalog.append({
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "notes": p.notes,
                "required_inputs": [
                    {
                        "name": pin.name,
                        "unit": pin.unit,
                        "description": pin.description,
                        "default": pin.default_value
                    }
                    for pin in p.required_inputs
                ],
                "steps_count": len(p.steps)
            })
        return catalog


pipeline_registry = PipelineRegistry()
