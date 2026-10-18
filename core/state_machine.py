"""分阶段人工确认、会话编辑及确定性计算的统一入口。"""

import json
from copy import deepcopy
from dataclasses import asdict
from enum import Enum
from hashlib import sha256
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from core.pipeline import Pipeline, PipelineValidationError, pipeline_registry
from core.formula import default_formula_registry
from core.storage import read_json, write_json, record_path, synchronized


class WorkflowState(str, Enum):
    INITIAL = "INITIAL"
    SCENARIO_PROPOSED = "SCENARIO_PROPOSED"
    SCENARIO_CONFIRMED = "SCENARIO_CONFIRMED"
    PARAMETERS_INSPECTED = "PARAMETERS_INSPECTED"
    PARAMETERS_CONFIRMED = "PARAMETERS_CONFIRMED"
    CALCULATED = "CALCULATED"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"


class StateTransitionError(Exception):
    """状态转移非法异常。"""


class SessionState(BaseModel):
    session_id: str
    editor_stage: int = Field(default=1, ge=1, le=2, strict=True)
    current_state: WorkflowState = WorkflowState.INITIAL
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None
    scenario_description: Optional[str] = None
    is_new_scenario: bool = False
    new_scenario_draft: Optional[Dict[str, Any]] = None
    pipeline_data: Optional[Dict[str, Any]] = None
    user_requirements: str = ""
    provided_parameters: Dict[str, Any] = Field(default_factory=dict)
    inspected_parameters: Dict[str, Any] = Field(default_factory=dict)
    human_feedback: Optional[str] = None
    calculation_result: Optional[Dict[str, Any]] = None
    scenario_signature: Optional[str] = None
    parameter_signature: Optional[str] = None
    modification_target: Optional[str] = None


class WorkflowManager:
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    @synchronized
    def get_or_create_session(self, session_id: str) -> SessionState:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 200:
            raise ValueError("会话 ID 不能为空或超过 200 个字符")
        if session_id not in self._sessions:
            saved = read_json(record_path("sessions", session_id))
            session = SessionState.model_validate(saved) if saved else SessionState(session_id=session_id)
            if saved and session.pipeline_data:
                session.pipeline_data = Pipeline.from_dict(session.pipeline_data).to_dict()
                # 恢复工程草稿，授权不跨进程恢复。
                self._reset_confirmation(session)
            self._sessions[session_id] = session
        return self._sessions[session_id]

    def _commit(self, session: SessionState) -> None:
        write_json(record_path("sessions", session.session_id), session.model_dump(mode="json"))
        self._sessions[session.session_id] = session

    @staticmethod
    def _reset_confirmation(session: SessionState) -> None:
        session.editor_stage = 1
        session.current_state = WorkflowState.SCENARIO_PROPOSED
        session.scenario_signature = None
        session.parameter_signature = None
        session.inspected_parameters = {}
        session.calculation_result = None
        session.modification_target = None

    @staticmethod
    def _pipeline(session: SessionState) -> Pipeline:
        if session.pipeline_data is None:
            raise StateTransitionError("请先提议计算场景")
        return Pipeline.from_dict(session.pipeline_data)

    def _signature(self, session: SessionState, include_parameters=False) -> str:
        pipeline = self._pipeline(session)
        data = pipeline.to_dict()
        data.pop("layout", None)
        operators = {step.formula_id: asdict(default_formula_registry.get(step.formula_id).metadata) for step in pipeline.steps}
        payload = {"pipeline": data, "operators": operators}
        if include_parameters:
            payload["parameters"] = pipeline.inspect_inputs(session.provided_parameters)["filled_inputs"]
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def _refresh(self, session: SessionState) -> SessionState:
        if session.scenario_signature and session.scenario_signature != self._signature(session):
            session = session.model_copy(deep=True)
            self._reset_confirmation(session)
            self._commit(session)
        return session

    @staticmethod
    def _check_confirmation(confirmed):
        if type(confirmed) is not bool:
            raise ValueError("confirmed 必须显式填写 true 或 false")

    def _propose(self, session_id, pipeline, requirements, inputs, is_new=False):
        self.get_or_create_session(session_id)
        pipeline.validated_steps()
        pipeline.inspect_inputs(inputs)
        session = SessionState(
            session_id=session_id, current_state=WorkflowState.SCENARIO_PROPOSED,
            scenario_id=pipeline.id, scenario_name=pipeline.name, scenario_description=pipeline.description,
            pipeline_data=pipeline.to_dict(), user_requirements=requirements,
            provided_parameters=deepcopy(inputs), is_new_scenario=is_new,
            new_scenario_draft=pipeline.to_dict() if is_new else None,
        )
        self._commit(session)
        return {"session_id": session_id, "status": session.current_state.value,
                "action_required": "HUMAN_SCENARIO_CONFIRMATION",
                "message": f"请人工核对并确认计算场景：【{pipeline.name}】。",
                "scenario": pipeline.to_dict()}

    @synchronized
    def propose_existing_scenario(self, session_id: str, scenario_id: str, user_requirements: str, initial_inputs: Dict[str, Any]) -> Dict[str, Any]:
        return self._propose(session_id, pipeline_registry.get(scenario_id), user_requirements, initial_inputs)

    @synchronized
    def propose_new_scenario(self, session_id: str, new_scenario_def: Dict[str, Any], user_requirements: str, initial_inputs: Dict[str, Any]) -> Dict[str, Any]:
        return self._propose(session_id, Pipeline.from_dict(new_scenario_def), user_requirements, initial_inputs, True)

    @synchronized
    def confirm_scenario(self, session_id: str, confirmed: bool, feedback: str = "") -> Dict[str, Any]:
        self._check_confirmation(confirmed)
        current = self._refresh(self.get_or_create_session(session_id))
        if current.current_state not in (WorkflowState.SCENARIO_PROPOSED, WorkflowState.MODIFICATION_REQUESTED):
            raise StateTransitionError("必须先提议场景，才能进行场景确认")
        session = current.model_copy(deep=True)
        if confirmed:
            self._pipeline(session).validated_steps()
            session.scenario_signature = self._signature(session)
            session.current_state = WorkflowState.SCENARIO_CONFIRMED
            session.modification_target = None
        else:
            self._reset_confirmation(session)
            session.current_state = WorkflowState.MODIFICATION_REQUESTED
            session.modification_target = "scenario"
        session.human_feedback = feedback or None
        self._commit(session)
        return {"session_id": session_id, "status": session.current_state.value,
                "action_required": "INSPECT_PARAMETERS" if confirmed else "AI_MODIFY_SCENARIO",
                "message": "场景已确认，请检查参数" if confirmed else "请修改场景并重新提议"}

    @synchronized
    def inspect_parameters(self, session_id: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        current = self._refresh(self.get_or_create_session(session_id))
        if not current.scenario_signature:
            raise StateTransitionError("必须先完成场景确认（SCENARIO_CONFIRMED）才能检查参数")
        session = current.model_copy(deep=True)
        candidate = {**session.provided_parameters, **(parameters or {})}
        pipeline = self._pipeline(session)
        pipeline.validated_steps()
        inspection = pipeline.inspect_inputs(candidate)
        # 校验全部成功后才提交；任何错误均不修改原会话。
        session.provided_parameters = candidate
        session.inspected_parameters = inspection
        session.parameter_signature = None
        session.calculation_result = None
        session.current_state = WorkflowState.PARAMETERS_INSPECTED
        session.modification_target = None
        self._commit(session)
        return {"session_id": session_id, "status": session.current_state.value,
                "action_required": "HUMAN_PARAMETER_CONFIRMATION" if inspection["is_complete"] else "PROVIDE_MISSING_PARAMETERS",
                "message": "请人工核对参数并确认" if inspection["is_complete"] else "请补齐缺失参数",
                "parameters_summary": inspection["filled_inputs"], **inspection}

    @synchronized
    def confirm_parameters(self, session_id: str, confirmed: bool, feedback: str = "") -> Dict[str, Any]:
        self._check_confirmation(confirmed)
        current = self._refresh(self.get_or_create_session(session_id))
        if current.current_state != WorkflowState.PARAMETERS_INSPECTED:
            raise StateTransitionError("必须先执行参数检查（PARAMETERS_INSPECTED）后才能确认参数")
        session = current.model_copy(deep=True)
        if confirmed:
            inspection = self._pipeline(session).inspect_inputs(session.provided_parameters)
            if not inspection["is_complete"] or inspection != session.inspected_parameters:
                raise StateTransitionError("参数缺失或已变化，请重新检查")
            session.parameter_signature = self._signature(session, True)
            session.current_state = WorkflowState.PARAMETERS_CONFIRMED
        else:
            session.current_state = WorkflowState.MODIFICATION_REQUESTED
            session.modification_target = "parameters"
            session.parameter_signature = None
        session.human_feedback = feedback or None
        self._commit(session)
        return {"session_id": session_id, "status": session.current_state.value,
                "action_required": "EXECUTE_CALCULATION" if confirmed else "AI_MODIFY_PARAMETERS",
                "message": "参数已确认，允许执行计算" if confirmed else "请修改参数并重新检查"}

    def _check_calculation_authorization(self, session):
        if not session.parameter_signature or session.parameter_signature != self._signature(session, True):
            raise StateTransitionError("未经人工确认授权，或已确认的数据已变化，计算引擎拒绝执行")

    @synchronized
    def execute_calculation(self, session_id: str) -> Dict[str, Any]:
        current = self._refresh(self.get_or_create_session(session_id))
        if current.current_state != WorkflowState.PARAMETERS_CONFIRMED:
            raise StateTransitionError("未经人工确认授权，计算引擎拒绝执行；请先确认场景和参数")
        self._check_calculation_authorization(current)
        result = self._pipeline(current).execute(current.inspected_parameters["filled_inputs"], default_formula_registry)
        session = current.model_copy(deep=True)
        session.current_state = WorkflowState.CALCULATED
        session.calculation_result = result.model_dump()
        self._commit(session)
        return {"session_id": session_id, "status": session.current_state.value,
                "action_required": "PRESENT_STRUCTURED_RESULTS", "message": "计算完成",
                "result": session.calculation_result}

    @synchronized
    def solve_atomic_formula(self, session_id, formula_id, known_variables, target_variable):
        session = self._refresh(self.get_or_create_session(session_id))
        if session.current_state not in (WorkflowState.PARAMETERS_CONFIRMED, WorkflowState.CALCULATED):
            raise StateTransitionError("单公式求解同样需要先确认场景和参数")
        self._check_calculation_authorization(session)
        pipeline = self._pipeline(session)
        steps = [step for step in pipeline.steps if step.formula_id == formula_id]
        if not steps:
            raise ValueError("只能求解已确认流水线中的算子")
        result = session.calculation_result
        if result is None:
            result = pipeline.execute(session.inspected_parameters["filled_inputs"]).model_dump()
        context = {**result["initial_inputs"], **result["final_outputs"]}
        if not any(all(name in {**step.input_map, **step.output_map} and
                       context[{**step.input_map, **step.output_map}[name]] == value
                       for name, value in known_variables.items()) for step in steps):
            raise StateTransitionError("求解使用的已知值不属于当前已确认工况")
        formula = default_formula_registry.get(formula_id)
        value = formula.solve(known_variables, target_variable)
        pin = {**formula.input_pins, **formula.output_pins}[target_variable]
        return {"formula_id": formula_id, "formula_name": formula.metadata.name,
                "target_variable": target_variable, "target_description": pin.description,
                "calculated_value": value, "unit": pin.unit}

    @synchronized
    def set_editor_stage(self, session_id: str, stage: int) -> None:
        """AI 显式切换展示阶段，不代替场景确认、参数确认或计算。"""
        if type(stage) is not int or stage not in (1, 2):
            raise ValueError("编辑器阶段必须为 1 或 2")
        current = self._refresh(self.get_or_create_session(session_id))
        if stage == 2 and not current.scenario_signature:
            raise StateTransitionError("请先获得人工场景确认，再切换至阶段 02")
        session = current.model_copy(deep=True)
        session.editor_stage = stage
        self._commit(session)

    @synchronized
    def get_session_view(self, session_id: str) -> Dict[str, Any]:
        session = self._refresh(self.get_or_create_session(session_id))
        pipeline = self._pipeline(session) if session.pipeline_data else None
        variables = {}
        if pipeline:
            variables.update({pin.name: asdict(pin) for pin in pipeline.required_inputs})
            for step in pipeline.steps:
                formula = default_formula_registry.get(step.formula_id)
                _, output_pins = formula.pin_contract(step.solve_target)
                for name, variable in step.output_map.items():
                    if name in output_pins:
                        variables[variable] = {**asdict(output_pins[name]), "name": variable}
        return deepcopy({"session_id": session_id, "current_state": session.current_state.value,
                         "editor_stage": session.editor_stage,
                         "scenario_id": session.scenario_id, "scenario_name": session.scenario_name,
                         "scenario_description": session.scenario_description, "pipeline": pipeline.to_dict() if pipeline else None,
                         "provided_parameters": session.provided_parameters,
                         "inspected_parameters": session.inspected_parameters,
                         "calculation_result": session.calculation_result,
                         "formulas": default_formula_registry.to_ai_catalog(), "variables": variables,
                         "validation": pipeline.validate() if pipeline else None})

    @synchronized
    def update_pipeline_in_session(self, session_id: str, new_pipeline_dict: Dict[str, Any], allow_incomplete: bool = False):
        current = self.get_or_create_session(session_id)
        pipeline = Pipeline.from_dict(new_pipeline_dict)
        validation = pipeline.validate()
        fatal = [item for item in validation["errors"] if item["code"] not in ("missing_source", "missing_output")]
        if fatal or (not allow_incomplete and not validation["is_valid"]):
            raise PipelineValidationError(fatal or validation["errors"])
        session = current.model_copy(deep=True)
        session.pipeline_data = pipeline.to_dict()
        session.scenario_id = pipeline.id
        session.scenario_name = pipeline.name
        session.scenario_description = pipeline.description
        before = deepcopy(current.pipeline_data or {})
        after = deepcopy(session.pipeline_data)
        before.pop("layout", None)
        after.pop("layout", None)
        if before != after:
            allowed = {pin.name for pin in pipeline.required_inputs}
            session.provided_parameters = {key: value for key, value in session.provided_parameters.items() if key in allowed}
            self._reset_confirmation(session)
        self._commit(session)
        return validation

    def update_parameters_in_session(self, session_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        return self.inspect_parameters(session_id, parameters)

    @synchronized
    def invalidate_formula(self, formula_id: str) -> None:
        for session in list(self._sessions.values()):
            if session.pipeline_data and any(step["formula_id"] == formula_id for step in session.pipeline_data["steps"]):
                candidate = session.model_copy(deep=True)
                self._reset_confirmation(candidate)
                self._commit(candidate)


workflow_manager = WorkflowManager()
