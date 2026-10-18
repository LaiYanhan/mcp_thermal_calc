"""
Pipeline DAG execution engine and pipeline registry.
"""

from typing import Any, Dict, List, Optional, Set
from dataclasses import asdict
from copy import deepcopy
from pathlib import Path
import math
import re
from core.formula import FormulaRegistry, registry as default_registry
from core.types import (
    Pin,
    InputConstraint,
    PipelineStep,
    PipelineExecutionResult,
    StepExecutionRecord,
    FormulaOutput,
    units_match,
)
from core.storage import read_json, write_json, synchronized
from core.assets import asset_directory, definition_path
from core.definitions import PipelineDefinition


class PipelineValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("；".join(item["message"] for item in errors))


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
        layout: Optional[Dict[str, Any]] = None,
        input_constraints: Optional[List[InputConstraint]] = None,
    ):
        self.id = id
        self.name = name
        self.category = category
        self.description = description
        self.notes = notes
        self.required_inputs = required_inputs
        self.steps = steps
        self.layout = layout or {}
        self.input_constraints = list(input_constraints or [])

    def _constraint_errors(self):
        inputs = {pin.name: pin for pin in self.required_inputs}
        errors = []
        for constraint in self.input_constraints:
            names = [constraint.variable]
            if constraint.greater_than is not None:
                names.append(constraint.greater_than)
            if any(name not in inputs for name in names):
                errors.append("输入约束引用了未声明的输入：" + ", ".join(names))
            elif len(names) == 2 and not units_match(inputs[names[0]].unit, inputs[names[1]].unit):
                errors.append("输入约束比较的参数单位不兼容：" + ", ".join(names))
        return errors

    def validate(self, formula_registry=None) -> Dict[str, Any]:
        """检查图契约并返回稳定拓扑序；不执行任何业务计算。"""
        reg = formula_registry or default_registry
        errors = []

        def error(code, message, step_id=None, pin=None):
            errors.append({"code": code, "message": message, "step_id": step_id, "pin": pin})

        if not self.steps:
            error("empty", "流水线至少需要一个算子")
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", self.id):
            error("identity", "流水线 ID 格式不正确")
        sources = {}
        for pin in self.required_inputs:
            if pin.name in sources:
                error("duplicate", f"重复输入 {pin.name}")
            sources[pin.name] = (None, pin.unit)
        for message in self._constraint_errors():
            error("constraint", message)
        steps = {}
        contracts = {}
        for step in self.steps:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", step.step_id):
                error("identity", f"步骤 ID 格式不正确：{step.step_id}", step.step_id)
            if step.step_id in steps:
                error("duplicate", f"重复步骤 {step.step_id}", step.step_id)
            steps[step.step_id] = step
            try:
                formula = reg.get(step.formula_id)
            except KeyError:
                error("formula", f"未注册算子 {step.formula_id}", step.step_id)
                continue
            try:
                inputs, outputs = formula.pin_contract(step.solve_target)
            except ValueError as exc:
                error("target", str(exc), step.step_id)
                continue
            contracts[step.step_id] = (inputs, outputs)
            if set(step.input_map) != set(inputs):
                error("pins", f"步骤 {step.step_id} 的输入引脚与算子不一致", step.step_id)
            if set(step.output_map) != set(outputs):
                error("pins", f"步骤 {step.step_id} 的输出引脚与算子不一致", step.step_id)
            for pin, variable in step.output_map.items():
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", variable):
                    error("variable", f"输出变量标识不正确：{variable}", step.step_id, pin)
                if variable in sources:
                    error("duplicate", f"变量 {variable} 有多个来源", step.step_id, pin)
                if pin in outputs:
                    sources[variable] = (step.step_id, outputs[pin].unit)
        dependencies = {step.step_id: set() for step in self.steps}
        for step in self.steps:
            if step.step_id not in contracts:
                continue
            inputs, _ = contracts[step.step_id]
            for pin, variable in step.input_map.items():
                if variable not in sources:
                    error("missing_source", f"步骤 {step.step_id} 的 {pin} 待选择来源（{variable or '未连接'}）", step.step_id, pin)
                else:
                    producer, unit = sources[variable]
                    if producer is not None:
                        dependencies[step.step_id].add(producer)
                    if pin in inputs and not units_match(unit, inputs[pin].unit):
                        error("unit", f"步骤 {step.step_id} 的 {pin} 单位不兼容：{unit} / {inputs[pin].unit}", step.step_id, pin)
        ordered = []
        pending = dict(dependencies)
        while pending:
            ready = [key for key, parents in pending.items() if not parents]
            if not ready:
                error("cycle", "流水线存在循环依赖：" + ", ".join(pending))
                break
            for key in ready:
                ordered.append(key)
                pending.pop(key)
            for parents in pending.values():
                parents.difference_update(ready)
        if not isinstance(self.layout, dict):
            error("layout", "节点布局必须为对象")
            return {"is_valid": False, "errors": errors, "order": ordered}
        for key, position in self.layout.items():
            if not isinstance(position, dict) or any(type(position.get(axis)) not in (int, float) or not math.isfinite(position[axis]) for axis in ("left", "top")):
                error("layout", f"节点 {key} 的位置无效")
        return {"is_valid": not errors, "errors": errors, "order": ordered}

    def validated_steps(self, formula_registry=None) -> List[PipelineStep]:
        validation = self.validate(formula_registry)
        if not validation["is_valid"]:
            raise PipelineValidationError(validation["errors"])
        by_id = {step.step_id: step for step in self.steps}
        return [by_id[key] for key in validation["order"]]

    def inspect_inputs(self, provided_inputs: Dict[str, Any], formula_registry=None) -> Dict[str, Any]:
        """
        检查入参完整性，输出已有参数、缺失必填参数与默认值补全
        """
        missing: List[Dict[str, Any]] = []
        filled: Dict[str, Any] = {}
        defaults_applied: Dict[str, Any] = {}

        unknown = set(provided_inputs) - {p.name for p in self.required_inputs}
        if unknown:
            raise ValueError("未声明的工况参数：" + ", ".join(sorted(unknown)))

        for pin in self.required_inputs:
            if pin.name in provided_inputs and provided_inputs[pin.name] is not None:
                raw = provided_inputs[pin.name]
                if isinstance(raw, dict):
                    if set(raw) != {"value", "unit"} or not units_match(raw["unit"], pin.unit):
                        raise ValueError(f"参数 {pin.name} 必须使用 {pin.unit}，请显式换算后提交")
                    raw = raw["value"]
                if isinstance(raw, bool):
                    raise ValueError(f"参数 {pin.name} 不能为布尔值")
                val = float(raw)
                pin.validate(val)
                filled[pin.name] = val
            elif pin.default_value is not None:
                pin.validate(pin.default_value)
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

        constraint_errors = self._constraint_errors()
        if constraint_errors:
            raise ValueError("；".join(constraint_errors))
        for constraint in self.input_constraints:
            constraint.validate(filled)
        for step in self.steps:
            formula = (formula_registry or default_registry).get(step.formula_id)
            known_pins, _ = formula.pin_contract(step.solve_target)
            for name, variable in step.input_map.items():
                if variable in filled and name in known_pins:
                    known_pins[name].validate(filled[variable])
            if all(variable in filled for variable in step.input_map.values()):
                formula.validate_knowns({name: filled[variable] for name, variable in step.input_map.items()}, step.solve_target)
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
        steps = self.validated_steps(reg)
        inspection = self.inspect_inputs(inputs, reg)
        if not inspection["is_complete"]:
            missing_names = [m["description"] + f"({m['name']})" for m in inspection["missing_inputs"]]
            raise ValueError(f"管道 '{self.name}' 执行失败：缺少必需的输入参数: {', '.join(missing_names)}")

        # 当前变量上下文，以校验填补好的输入为初始基底
        ctx: Dict[str, Any] = dict(inspection["filled_inputs"])
        records: List[StepExecutionRecord] = []
        outputs = {}
        results = []

        for step in steps:
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
            step_outputs = formula.execute_for_target(step_inputs, step.solve_target)
            _, output_pins = formula.pin_contract(step.solve_target)

            # 映射输出写回全局上下文
            for formula_out_pin, ctx_var in step.output_map.items():
                if formula_out_pin not in step_outputs:
                    raise KeyError(f"公式 '{step.formula_id}' 未产出引脚 '{formula_out_pin}'")
                ctx[ctx_var] = step_outputs[formula_out_pin]
                outputs[ctx_var] = ctx[ctx_var]
                pin = output_pins[formula_out_pin]
                results.append(FormulaOutput(
                    step_id=step.step_id, formula_id=step.formula_id,
                    formula_name=formula.metadata.name, pin=formula_out_pin,
                    variable=ctx_var, description=pin.description, unit=pin.unit, value=ctx[ctx_var],
                ))

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

        return PipelineExecutionResult(
            pipeline_id=self.id,
            pipeline_name=self.name,
            scenario_description=self.description,
            initial_inputs=inspection["filled_inputs"],
            final_outputs=outputs,
            step_records=records,
            results=results
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典结构，供前端渲染引擎与持久化存储使用"""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "notes": self.notes,
            "required_inputs": [asdict(pin) for pin in self.required_inputs],
            "steps": [step.model_dump() for step in self.steps],
            "layout": deepcopy(self.layout),
            "input_constraints": [asdict(constraint) for constraint in self.input_constraints],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pipeline":
        """从字典反序列化生成管道实例"""
        data = deepcopy(data)
        required_inputs = [
            Pin(
                name=p["name"],
                unit=p["unit"],
                description=p["description"],
                min_value=p.get("min_value"),
                max_value=p.get("max_value"),
                default_value=p.get("default_value"),
                kind=p.get("kind", "input"),
            )
            for p in data.get("required_inputs", [])
        ]
        steps = [
            PipelineStep(
                step_id=s["step_id"],
                formula_id=s["formula_id"],
                solve_target=s.get("solve_target"),
                input_map=s["input_map"],
                output_map=s["output_map"],
                description=s.get("description", ""),
            )
            for s in data.get("steps", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            category=data.get("category", "custom"),
            description=data.get("description", ""),
            notes=data.get("notes", ""),
            required_inputs=required_inputs,
            steps=steps,
            layout=data.get("layout", {}),
            input_constraints=[InputConstraint(**item) for item in data.get("input_constraints", [])],
        )

    def insert_step(self, target_step_id: str, new_step: PipelineStep, position: str = "after") -> None:
        """在指定步骤的前方或后方插入新算子步骤"""
        idx = next((i for i, s in enumerate(self.steps) if s.step_id == target_step_id), -1)
        if idx == -1:
            raise ValueError(f"不存在的插入目标：{target_step_id}")
        else:
            insert_idx = idx + 1 if position == "after" else idx
            self.steps.insert(insert_idx, new_step)

    def delete_step(self, step_id: str) -> Optional[PipelineStep]:
        """从流水线中移除指定算子步骤"""
        idx = next((i for i, s in enumerate(self.steps) if s.step_id == step_id), -1)
        if idx != -1:
            return self.steps.pop(idx)
        return None

    def replace_step(self, step_id: str, new_step: PipelineStep) -> bool:
        """替换流水线中的指定算子步骤"""
        idx = next((i for i, s in enumerate(self.steps) if s.step_id == step_id), -1)
        if idx != -1:
            self.steps[idx] = new_step
            return True
        return False


class PipelineRegistry:
    """
    计算管道全局注册表
    """
    def __init__(self):
        self._pipelines: Dict[str, Pipeline] = {}

    def register(self, pipeline: Pipeline) -> None:
        if pipeline.id in self._pipelines:
            raise ValueError(f"流水线 {pipeline.id} 已存在")
        self._pipelines[pipeline.id] = pipeline

    @synchronized
    def save_pipeline(self, pipeline: Pipeline, filename=None) -> None:
        pipeline.validated_steps()
        if pipeline.id in self._pipelines:
            raise ValueError(f"流水线 {pipeline.id} 已存在")
        definition = PipelineDefinition.model_validate(pipeline.to_dict()).model_dump()
        write_json(definition_path("pipelines", pipeline.id, filename), definition)
        self.register(pipeline)

    @synchronized
    def load_directory(self, directory=None, formula_registry=None) -> None:
        candidates = dict(self._pipelines)
        for path in sorted((directory or asset_directory("pipelines")).rglob("*.json")):
            try:
                data = PipelineDefinition.model_validate(read_json(path)).model_dump()
                pipeline = Pipeline.from_dict(data)
                pipeline.validated_steps(formula_registry)
                if pipeline.id in candidates:
                    raise ValueError(f"重复流水线 ID：{pipeline.id}")
                candidates[pipeline.id] = pipeline
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"流水线 JSON {path} 无效：{error}") from error
        self._pipelines = candidates

    def get(self, pipeline_id: str) -> Pipeline:
        if pipeline_id not in self._pipelines:
            raise KeyError(f"未注册的计算管道ID: '{pipeline_id}'")
        return self._pipelines[pipeline_id]

    @synchronized
    def resolve(self, target: str) -> Pipeline:
        """按 ID、名称或 JSON 文件解析管道，绝不查找或执行 Python 文件。"""
        clean = target.strip().replace("\\", "/")
        if clean in self._pipelines:
            return self._pipelines[clean]
        path = Path(clean)
        if path.suffix and path.suffix != ".json":
            raise ValueError("流水线文件必须为 JSON")
        if path.suffix == ".json":
            for candidate in (path, asset_directory("pipelines") / path.name):
                if candidate.is_file():
                    pipeline = Pipeline.from_dict(PipelineDefinition.model_validate(read_json(candidate)).model_dump())
                    pipeline.validated_steps()
                    if pipeline.id in self._pipelines:
                        existing = self._pipelines[pipeline.id]
                        if existing.to_dict() != pipeline.to_dict():
                            raise ValueError(f"流水线 {pipeline.id} 已注册且与 JSON 文件不同，请重启加载或使用独立 ID")
                        return existing
                    self.register(pipeline)
                    return pipeline
        stem = path.stem
        matches = [pipeline for pipeline in self._pipelines.values()
                   if stem in (pipeline.id, pipeline.name) or pipeline.id == "scenario_" + stem]
        if len(matches) == 1:
            return matches[0]
        raise KeyError(f"未找到唯一匹配的计算管道: '{target}'。当前已注册管道: {list(self._pipelines)}")

    def list_all(self) -> List[Pipeline]:
        return list(self._pipelines.values())
    def to_ai_catalog(self) -> List[Dict[str, Any]]:
        """输出供大模型（Agent）场景匹配的场景清单"""
        catalog = []
        for p in self._pipelines.values():
            catalog.append({
                "definition": p.to_dict(),
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
                "steps_count": len(p.steps),
                "input_constraints": [asdict(constraint) for constraint in p.input_constraints],
            })
        return catalog


pipeline_registry = PipelineRegistry()
