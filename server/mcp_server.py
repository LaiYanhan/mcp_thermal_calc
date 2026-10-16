"""MCP 工具适配层：所有计算、编辑与授权均委托给核心模块。"""

import json
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from pydantic import StrictBool

# 兼容 README 中直接执行 server/mcp_server.py 的启动方式。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.mcpserver import MCPServer
import formulas
import pipelines
from core.formula import default_formula_registry
from core.pipeline import pipeline_registry
from core.state_machine import workflow_manager, StateTransitionError
from core.extensions import parse_definition, validate_filename
from server.web_app import ensure_web_server_running

mcp_server = MCPServer("thermal-calc-sizing-engine")


def response(data):
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)


def run_workflow(function, **kwargs):
    try:
        return response(function(**kwargs))
    except (ValueError, KeyError, TypeError, StateTransitionError, ArithmeticError) as error:
        return response({"error": str(error), "security_block": isinstance(error, StateTransitionError)})


def editor_link(session_id, stage):
    base = ensure_web_server_running()
    return base + "/editor?" + urlencode({"session_id": session_id, "stage": stage})


@mcp_server.tool()
def list_scenarios() -> str:
    """列出已注册、可执行的场景管道。"""
    return response(pipeline_registry.to_ai_catalog())


@mcp_server.tool()
def list_formulas() -> str:
    """列出原子公式。variables 给出所有参数的含义、单位和约束，solve_targets 为可选待求量。
    inputs/outputs 表示默认方向；节点设置 solve_target 后，其余 variables 全部作为已知输入。
    """
    return response(default_formula_registry.to_ai_catalog())


@mcp_server.tool()
def match_or_propose_scenario(session_id: str, user_requirements: str, scenario_id: Optional[str] = None,
                              initial_inputs: Optional[Dict[str, Any]] = None,
                              new_scenario_def: Optional[Dict[str, Any]] = None) -> str:
    """提议明确选择的已有场景或声明式新场景。调用后必须等待人工确认。
    new_scenario_def.steps 中每步可设置 solve_target（公式变量名），input_map 绑定其余全部变量的来源，
    output_map 将待求变量映射到本步骤产出变量。省略 solve_target 使用公式默认方向，查表算子不可反算。
    全部步骤输出自动成为成果，不需要输出分组。先用 list_formulas 获取可求变量及物理含义。
    """
    if scenario_id is None and new_scenario_def is None:
        return response({"status": "SCENARIO_SELECTION_REQUIRED", "message": "请从场景目录选择匹配的场景 ID，或提交新场景定义；不自动把陌生需求当成基准场景。", "scenarios": pipeline_registry.to_ai_catalog()})
    if scenario_id is not None and new_scenario_def is not None:
        return response({"error": "已有场景 ID 与新场景定义只能指定一个"})
    try:
        if new_scenario_def is not None:
            result = workflow_manager.propose_new_scenario(session_id, new_scenario_def, user_requirements, initial_inputs or {})
        else:
            result = workflow_manager.propose_existing_scenario(session_id, scenario_id, user_requirements, initial_inputs or {})
        try:
            result["editor_url"] = editor_link(session_id, 1)
            webbrowser.open(result["editor_url"])
        except RuntimeError as error:
            result["editor_error"] = str(error)
        return response(result)
    except (ValueError, KeyError, TypeError) as error:
        return response({"error": str(error)})


@mcp_server.tool()
def confirm_scenario(session_id: str, confirmed: StrictBool, feedback: str = "") -> str:
    """记录用户明确给出的场景确认或修改意见。"""
    return run_workflow(workflow_manager.confirm_scenario, session_id=session_id, confirmed=confirmed, feedback=feedback)


@mcp_server.tool()
def inspect_and_validate_parameters(session_id: str, parameters: Optional[Dict[str, Any]] = None) -> str:
    """核对当前会话管道的输入、缺项和默认值；变更参数会撤销旧计算授权。"""
    return run_workflow(workflow_manager.inspect_parameters, session_id=session_id, parameters=parameters)


@mcp_server.tool()
def confirm_parameters(session_id: str, confirmed: StrictBool, feedback: str = "") -> str:
    """用户核对参数后显式授权，或者打回修改。"""
    return run_workflow(workflow_manager.confirm_parameters, session_id=session_id, confirmed=confirmed, feedback=feedback)


@mcp_server.tool()
def execute_calculation(session_id: str) -> str:
    """仅对已确认且未变化的场景、算子与参数执行确定性计算。"""
    return run_workflow(workflow_manager.execute_calculation, session_id=session_id)


@mcp_server.tool()
def solve_atomic_formula(formula_id: str, known_variables: Dict[str, Any], target_variable: str, session_id: str) -> str:
    """在已确认工况范围内正向或逆向求解原子公式，不能绕过会话授权。"""
    return run_workflow(workflow_manager.solve_atomic_formula, session_id=session_id, formula_id=formula_id,
                        known_variables=known_variables, target_variable=target_variable)


@mcp_server.tool()
def register_new_formula(formula_code: str, sub_category: str, filename: str, human_approved: StrictBool) -> str:
    """保存人工审核通过的声明式公式（JSON 或受限模板），校验、落盘并即时注册。"""
    if human_approved is not True:
        return response({"status": "REJECTED", "error": "请先获得人类工程师对公式的审核同意"})
    try:
        validate_filename(filename)
        validate_filename(sub_category)
        data = parse_definition(formula_code, "formula")
        data["category"] = sub_category
        formula = default_formula_registry.save_operator(data)
        return response({"status": "SUCCESS", "formula_id": formula.metadata.id, "message": "公式已保存并注册"})
    except (ValueError, TypeError, KeyError, SyntaxError) as error:
        return response({"error": str(error)})


@mcp_server.tool()
def register_new_pipeline(pipeline_code: str, pipeline_filename: str, human_approved: StrictBool) -> str:
    """保存人工审核通过的声明式 Pipeline（JSON 或受限模板），验证 DAG 后即时注册。"""
    if human_approved is not True:
        return response({"status": "REJECTED", "error": "请先获得人类对流水线的审核同意"})
    try:
        validate_filename(pipeline_filename)
        pipeline = parse_definition(pipeline_code, "pipeline")
        pipeline_registry.save_pipeline(pipeline)
        return response({"status": "SUCCESS", "pipeline_id": pipeline.id, "message": "流水线已保存并注册"})
    except (ValueError, TypeError, KeyError, SyntaxError) as error:
        return response({"error": str(error)})


@mcp_server.tool()
def open_pipeline_editor(session_id: str = "default_session", stage: int = 1) -> str:
    """打开同进程的流水线编辑器，页面以会话真实状态为准。"""
    try:
        url = editor_link(session_id, stage)
        webbrowser.open(url)
        return response({"status": "SUCCESS", "editor_url": url})
    except RuntimeError as error:
        return response({"error": str(error)})


def run_server():
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    run_server()
