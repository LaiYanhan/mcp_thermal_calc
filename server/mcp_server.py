"""
Model Context Protocol (MCP) Server for Thermal Calculation & Sizing System.
Strictly implements the Image #2 state machine with staged human-in-the-loop authorization guards.
"""

import json
import os
from typing import Any, Dict, List, Optional
from mcp.server.mcpserver import MCPServer
import formulas
import pipelines
from core.formula import default_formula_registry
from core.pipeline import pipeline_registry
from core.state_machine import WorkflowState, workflow_manager, StateTransitionError


# 初始化 MCP 服务器实例
mcp_server = MCPServer("thermal-calc-sizing-engine")


@mcp_server.tool()
def list_scenarios() -> str:
    """
    列出系统中所有已注册的计算场景管道（Pipeline）清单。
    返回每个场景的唯一ID、名称、业务领域、适用工况、详细说明及所需输入变量定义。
    """
    catalog = pipeline_registry.to_ai_catalog()
    return json.dumps(catalog, ensure_ascii=False, indent=2)


@mcp_server.tool()
def list_formulas() -> str:
    """
    列出系统中所有已注册的原子公式（Atomic Formula）清单。
    包含每个公式的ID、中文名称、类别（热平衡/选型/运行经济）、物理方程或查表逻辑、
    每个入参/出参的物理单位、详细中文释义及物理区间约束。
    """
    catalog = default_formula_registry.to_ai_catalog()
    return json.dumps(catalog, ensure_ascii=False, indent=2)


@mcp_server.tool()
def match_or_propose_scenario(
    session_id: str,
    user_requirements: str,
    scenario_id: Optional[str] = None,
    initial_inputs: Optional[Dict[str, Any]] = None,
) -> str:
    """
    【流程第1步 - 模式匹配】
    根据用户输入的工程需求与数据，匹配现有管道或提议新管道。
    注意：调用此工具后，会话状态自动切换为 SCENARIO_PROPOSED（场景待确认）。
    AI 必须停下来向人类汇报该场景匹配结果与设计逻辑，等待人类确认后方可调用 confirm_scenario！
    
    参数：
      session_id: 当前会话唯一ID（如 "session_001"）
      user_requirements: 人类工程需求描述文本
      scenario_id: 若明确知道场景ID可直接指定（如 "scenario_valley_salt_steam"），不填则默认匹配基准场景
      initial_inputs: 用户在对话中已提及的已知参数键值对（可选）
    """
    inputs = initial_inputs or {}
    matched_id = scenario_id or "scenario_valley_salt_steam"

    try:
        pipeline = pipeline_registry.get(matched_id)
        result = workflow_manager.propose_existing_scenario(
            session_id=session_id,
            scenario_id=matched_id,
            user_requirements=user_requirements,
            initial_inputs=inputs,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except KeyError:
        return json.dumps(
            {
                "error": f"未找到场景 '{matched_id}'。如需为陌生场景新建管道，请先草拟管道结构并提交审核。",
                "status": "SCENARIO_NOT_FOUND",
            },
            ensure_ascii=False,
            indent=2,
        )


@mcp_server.tool()
def confirm_scenario(
    session_id: str,
    confirmed: bool,
    feedback: str = "",
) -> str:
    """
    【流程第2步 - 人工确认场景】
    记录人类对场景匹配结果的确认决策。
    若 confirmed=True，状态解锁为 SCENARIO_CONFIRMED，允许进入下一步参数检查；
    若 confirmed=False，状态重置为 MODIFICATION_REQUESTED，AI 必须根据 feedback 重新调整场景。
    
    参数：
      session_id: 当前会话唯一ID
      confirmed: 人类是否明确同意当前场景（True 或 False）
      feedback: 若人类不同意，在此传入人类的具体修改意见
    """
    try:
        res = workflow_manager.confirm_scenario(
            session_id=session_id,
            confirmed=confirmed,
            feedback=feedback,
        )
        return json.dumps(res, ensure_ascii=False, indent=2)
    except StateTransitionError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


@mcp_server.tool()
def inspect_and_validate_parameters(
    session_id: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> str:
    """
    【流程第3步 - 输入变量匹配与缺项分析】
    前置依赖：场景必须已被人工确认（SCENARIO_CONFIRMED）。
    根据选定管道的参数规范，校验传入的数值是否合法，并自动从 constants 注入标准工程默认值。
    - 若存在无默认值的必填缺失项：输出缺失变量清单及详细工程释义，提示 AI 询问人类补充；
    - 若所有输入参数已完整明确：状态切换为 PARAMETERS_INSPECTED，输出包含单位和注释的完整参数清单，
      提示 AI 必须向人类汇报并征求确认！
    
    参数：
      session_id: 当前会话唯一ID
      parameters: 本次提供或补充的输入参数字典（如 {"steam_mass_flow": 120.0}）
    """
    try:
        res = workflow_manager.inspect_parameters(
            session_id=session_id,
            parameters=parameters,
        )
        return json.dumps(res, ensure_ascii=False, indent=2)
    except StateTransitionError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


@mcp_server.tool()
def confirm_parameters(
    session_id: str,
    confirmed: bool,
    feedback: str = "",
) -> str:
    """
    【流程第4步 - 人工确认参数】
    记录人类对所有输入参数与默认值配置的最终审核结果。
    若 confirmed=True，状态流转至 PARAMETERS_CONFIRMED，正式授权程序计算；
    若 confirmed=False，状态进入 MODIFICATION_REQUESTED，AI 根据意见修改参数后重新校验。
    
    参数：
      session_id: 当前会话唯一ID
      confirmed: 人类是否确认参数清单完全准确（True 或 False）
      feedback: 若人类要求修改参数，填入修改意见
    """
    try:
        res = workflow_manager.confirm_parameters(
            session_id=session_id,
            confirmed=confirmed,
            feedback=feedback,
        )
        return json.dumps(res, ensure_ascii=False, indent=2)
    except StateTransitionError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


@mcp_server.tool()
def execute_calculation(
    session_id: str,
) -> str:
    """
    【流程第5步 - 确定性程序计算】
    【强硬安全守卫】：未经人工确认参数（即会话状态非 PARAMETERS_CONFIRMED），直接抛出异常，拒绝执行！
    只有在获得人类确认授权后，计算引擎才按照有向无环图执行各原子公式，
    严禁任何 AI 随意生成数字或私自估算。返回完整的确定性选型规格、能耗、收益与计算步骤明细。
    
    参数：
      session_id: 当前会话唯一ID
    """
    try:
        res = workflow_manager.execute_calculation(session_id=session_id)
        return json.dumps(res, ensure_ascii=False, indent=2)
    except StateTransitionError as e:
        return json.dumps(
            {
                "security_block": True,
                "error": str(e),
                "instruction_for_agent": (
                    "严重警告：计算被系统状态机安全守卫物理拦截！"
                    "您必须按照图2工作流先向人类呈现参数清单，获得人类显式确认后"
                    "调用 confirm_parameters(confirmed=True)，方可授权计算。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )


@mcp_server.tool()
def solve_atomic_formula(
    formula_id: str,
    known_variables: Dict[str, float],
    target_variable: str,
) -> str:
    """
    单独调用或逆向推导单个原子公式。
    对于代数公式支持任意未知数反推（如已知功率和温差，逆推所需流量）。
    
    参数：
      formula_id: 公式唯一ID（如 "thermal.sgs_power"）
      known_variables: 已知参数变量字典（如 {"sgs_power": 75.33, "enthalpy_diff": 2712.0}）
      target_variable: 目标待求解变量名（如 "steam_mass_flow"）
    """
    try:
        formula = default_formula_registry.get(formula_id)
        val = formula.solve(known_variables, target_variable)
        target_pin = (
            formula.output_pins.get(target_variable)
            or formula.input_pins.get(target_variable)
        )
        unit = target_pin.unit if target_pin else ""
        desc = target_pin.description if target_pin else target_variable
        return json.dumps(
            {
                "formula_id": formula_id,
                "formula_name": formula.metadata.name,
                "target_variable": target_variable,
                "target_description": desc,
                "calculated_value": val,
                "unit": unit,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)


@mcp_server.tool()
def register_new_formula(
    formula_code: str,
    sub_category: str,
    filename: str,
    human_approved: bool,
) -> str:
    """
    【AI自扩展能力】为陌生场景编写并注册新的原子公式文件。
    必须满足：
    1. 遵循标准原子公式模板规范；
    2. human_approved 必须为 True（即人类工程师已审查确认代码安全与数学公式准确）；
    3. 成功后写入 formulas/<sub_category>/<filename>.py 并加载注册。
    """
    if not human_approved:
        return json.dumps(
            {
                "error": "未获人类工程师审查批准，禁止写入并注册新公式代码！请先展示代码向人类汇报并征求同意。",
                "status": "REJECTED",
            },
            ensure_ascii=False,
            indent=2,
        )

    target_dir = os.path.join("formulas", sub_category)
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, filename if filename.endswith(".py") else f"{filename}.py")

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(formula_code)

    return json.dumps(
        {
            "status": "SUCCESS",
            "message": f"新原子公式已通过人工审查并成功写入 {target_path}。重启或重载后即可在计算管道中引用。",
            "file_path": target_path,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp_server.tool()
def register_new_pipeline(
    pipeline_code: str,
    pipeline_filename: str,
    human_approved: bool,
) -> str:
    """
    【AI自扩展能力】将人类确认通过的新场景计算管道持久化保存至 pipelines/ 目录。
    下次遇到同类场景即可直接复用，无需重复编排。
    human_approved 必须为 True！
    """
    if not human_approved:
        return json.dumps(
            {
                "error": "未获人类工程师确认批准，禁止持久化保存新计算管道！请先向人类展示管道拓扑设计。",
                "status": "REJECTED",
            },
            ensure_ascii=False,
            indent=2,
        )

    target_dir = "pipelines"
    os.makedirs(target_dir, exist_ok=True)
    fname = pipeline_filename if pipeline_filename.endswith(".py") else f"{pipeline_filename}.py"
    target_path = os.path.join(target_dir, fname)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(pipeline_code)

    return json.dumps(
        {
            "status": "SUCCESS",
            "message": f"新场景计算管道已成功保存至 {target_path}。今后可直接作为已有场景调用！",
            "file_path": target_path,
        },
        ensure_ascii=False,
        indent=2,
    )


def run_server():
    """启动 MCP 服务"""
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    run_server()
