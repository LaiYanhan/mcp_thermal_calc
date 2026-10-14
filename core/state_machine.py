"""
State machine implementing the human-in-the-loop workflow from Image #2.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from core.pipeline import Pipeline, pipeline_registry
from core.formula import registry as default_formula_registry


class WorkflowState(str, Enum):
    """工作流阶段状态枚举"""
    INITIAL = "INITIAL"  # 初始态：等待输入数据与人类需求
    SCENARIO_PROPOSED = "SCENARIO_PROPOSED"  # 场景提议态：AI匹配或新建场景，等待人工确认
    SCENARIO_CONFIRMED = "SCENARIO_CONFIRMED"  # 场景确认态：人工已确认场景，进入输入变量匹配
    PARAMETERS_INSPECTED = "PARAMETERS_INSPECTED"  # 参数检查态：已分析缺项并补全默认值，等待人工确认参数
    PARAMETERS_CONFIRMED = "PARAMETERS_CONFIRMED"  # 参数确认态：人工已确认参数，授权执行程序计算
    CALCULATED = "CALCULATED"  # 计算完成态：输出结构化结果
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"  # 修改态：人类提出修改意见，AI根据反馈调整


class StateTransitionError(Exception):
    """状态转移非法异常"""
    pass


class SessionState(BaseModel):
    """
    单个计算会话的完整上下文状态
    """
    session_id: str
    current_state: WorkflowState = WorkflowState.INITIAL
    scenario_id: Optional[str] = None
    scenario_name: Optional[str] = None
    scenario_description: Optional[str] = None
    is_new_scenario: bool = False
    new_scenario_draft: Optional[Dict[str, Any]] = None

    user_requirements: str = ""
    provided_parameters: Dict[str, Any] = Field(default_factory=dict)
    inspected_parameters: Dict[str, Any] = Field(default_factory=dict)

    human_feedback: Optional[str] = None
    calculation_result: Optional[Dict[str, Any]] = None


class WorkflowManager:
    """
    状态机会话控制器
    """
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def get_or_create_session(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]

    def propose_existing_scenario(
        self, session_id: str, scenario_id: str, user_requirements: str, initial_inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """AI 匹配到现有场景，进入场景待确认状态"""
        session = self.get_or_create_session(session_id)
        pipeline = pipeline_registry.get(scenario_id)

        session.scenario_id = scenario_id
        session.scenario_name = pipeline.name
        session.scenario_description = pipeline.description
        session.is_new_scenario = False
        session.user_requirements = user_requirements
        session.provided_parameters = initial_inputs
        session.current_state = WorkflowState.SCENARIO_PROPOSED

        return {
            "session_id": session_id,
            "status": session.current_state.value,
            "action_required": "HUMAN_SCENARIO_CONFIRMATION",
            "message": (
                f"已为您的需求匹配到计算场景: 【{pipeline.name}】。\n"
                f"场景说明: {pipeline.description}\n"
                f"工程注意事项: {pipeline.notes}\n"
                f"请人工核对并确认是否使用该场景（或提出修改意见）。"
            ),
            "scenario": {
                "id": pipeline.id,
                "name": pipeline.name,
                "category": pipeline.category,
                "description": pipeline.description,
                "notes": pipeline.notes,
                "required_inputs": [
                    {
                        "name": pin.name,
                        "unit": pin.unit,
                        "description": pin.description,
                        "default": pin.default_value
                    }
                    for pin in pipeline.required_inputs
                ]
            }
        }

    def propose_new_scenario(
        self, session_id: str, new_scenario_def: Dict[str, Any], user_requirements: str, initial_inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """AI 自主分析计算流程，提议新场景管道草案，进入场景待确认状态"""
        session = self.get_or_create_session(session_id)

        session.scenario_id = new_scenario_def.get("id", "custom_scenario")
        session.scenario_name = new_scenario_def.get("name", "自定义扩展场景")
        session.scenario_description = new_scenario_def.get("description", "")
        session.is_new_scenario = True
        session.new_scenario_draft = new_scenario_def
        session.user_requirements = user_requirements
        session.provided_parameters = initial_inputs
        session.current_state = WorkflowState.SCENARIO_PROPOSED

        return {
            "session_id": session_id,
            "status": session.current_state.value,
            "action_required": "HUMAN_SCENARIO_CONFIRMATION",
            "message": (
                f"未匹配到现有场景。AI 自主分析提议新计算流程: 【{session.scenario_name}】。\n"
                f"场景设计逻辑: {session.scenario_description}\n"
                f"包含节点数: {len(new_scenario_def.get('steps', []))}\n"
                f"请人工严格审核该计算管道设计并确认（或提出修改意见）。"
            ),
            "scenario_draft": new_scenario_def
        }

    def confirm_scenario(self, session_id: str, confirmed: bool, feedback: str = "") -> Dict[str, Any]:
        """人类确认或打回场景"""
        session = self.get_or_create_session(session_id)
        if session.current_state not in (WorkflowState.SCENARIO_PROPOSED, WorkflowState.MODIFICATION_REQUESTED):
            raise StateTransitionError(
                f"当前状态为 {session.current_state.value}，不可进行场景确认。前置操作必须为提议场景。"
            )

        if not confirmed:
            session.current_state = WorkflowState.MODIFICATION_REQUESTED
            session.human_feedback = feedback
            return {
                "session_id": session_id,
                "status": session.current_state.value,
                "action_required": "AI_MODIFY_SCENARIO",
                "message": f"人工未认可当前场景。反馈意见: '{feedback}'。请 AI 根据反馈调整场景并重新提议。"
            }

        session.current_state = WorkflowState.SCENARIO_CONFIRMED
        session.human_feedback = None
        return {
            "session_id": session_id,
            "status": session.current_state.value,
            "action_required": "INSPECT_PARAMETERS",
            "message": f"人工已确认场景【{session.scenario_name}】。已解锁参数匹配阶段，请调用参数检查工具。"
        }

    def inspect_parameters(self, session_id: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """参数匹配与缺项检查"""
        session = self.get_or_create_session(session_id)
        if session.current_state not in (WorkflowState.SCENARIO_CONFIRMED, WorkflowState.PARAMETERS_INSPECTED):
            raise StateTransitionError(
                f"当前状态为 {session.current_state.value}，必须先完成场景确认（SCENARIO_CONFIRMED）才能检查参数。"
            )

        if parameters:
            session.provided_parameters.update(parameters)

        pipeline = pipeline_registry.get(session.scenario_id)
        inspection = pipeline.inspect_inputs(session.provided_parameters)
        session.inspected_parameters = inspection
        session.current_state = WorkflowState.PARAMETERS_INSPECTED

        if not inspection["is_complete"]:
            return {
                "session_id": session_id,
                "status": session.current_state.value,
                "action_required": "PROVIDE_MISSING_PARAMETERS",
                "is_complete": False,
                "message": "检测到必需输入参数存在缺失，已分析缺项如下，请人工补充输入：",
                "missing_inputs": inspection["missing_inputs"],
                "defaults_applied": inspection["defaults_applied"],
                "filled_inputs": inspection["filled_inputs"]
            }

        return {
            "session_id": session_id,
            "status": session.current_state.value,
            "action_required": "HUMAN_PARAMETER_CONFIRMATION",
            "is_complete": True,
            "message": (
                "所有必需输入参数已明确（含工程基准默认值）。\n"
                "请人工确认以下输入参数清单，确认无误后授权计算；如需修改请提出意见。"
            ),
            "parameters_summary": inspection["filled_inputs"],
            "defaults_applied": inspection["defaults_applied"]
        }

    def confirm_parameters(self, session_id: str, confirmed: bool, feedback: str = "") -> Dict[str, Any]:
        """人类确认或修改参数"""
        session = self.get_or_create_session(session_id)
        if session.current_state != WorkflowState.PARAMETERS_INSPECTED:
            raise StateTransitionError(
                f"当前状态为 {session.current_state.value}，必须先执行参数检查（PARAMETERS_INSPECTED）后才能确认参数。"
            )

        if not confirmed:
            session.current_state = WorkflowState.MODIFICATION_REQUESTED
            session.human_feedback = feedback
            return {
                "session_id": session_id,
                "status": session.current_state.value,
                "action_required": "AI_MODIFY_PARAMETERS",
                "message": f"人工对输入参数提出修改意见: '{feedback}'。请更新参数并重新检查确认。"
            }

        session.current_state = WorkflowState.PARAMETERS_CONFIRMED
        session.human_feedback = None
        return {
            "session_id": session_id,
            "status": session.current_state.value,
            "action_required": "EXECUTE_CALCULATION",
            "message": "人工已确认所有参数！已正式授权执行确定性计算程序。"
        }

    def execute_calculation(self, session_id: str) -> Dict[str, Any]:
        """
        核心计算执行（强守卫拦截）
        """
        session = self.get_or_create_session(session_id)
        # 严苛拦截：必须处于 PARAMETERS_CONFIRMED 态
        if session.current_state != WorkflowState.PARAMETERS_CONFIRMED:
            raise StateTransitionError(
                f"【安全拦截】当前会话处于 {session.current_state.value} 状态，未经人工确认授权，"
                f"计算引擎坚决拒绝执行！合法流转必须为: SCENARIO_CONFIRMED -> PARAMETERS_CONFIRMED -> 执行计算。"
            )

        pipeline = pipeline_registry.get(session.scenario_id)
        result = pipeline.execute(session.provided_parameters, default_formula_registry)

        session.current_state = WorkflowState.CALCULATED
        session.calculation_result = result.model_dump()

        return {
            "session_id": session_id,
            "status": session.current_state.value,
            "action_required": "PRESENT_STRUCTURED_RESULTS",
            "message": "计算完成！已生成确定性结构化工程测算结果。",
            "result": session.calculation_result
        }


workflow_manager = WorkflowManager()
