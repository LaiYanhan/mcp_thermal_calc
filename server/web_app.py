"""
Lightweight local Starlette web application and REST API for Visual Pipeline Editor.
Runs seamlessly alongside the MCP server on http://127.0.0.1:8765.
"""

import json
import os
import threading
from typing import Any, Dict, Optional
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route
import formulas
import pipelines
from core.formula import AlgebraicFormula, default_formula_registry
from core.pipeline import pipeline_registry
from core.state_machine import WorkflowState, workflow_manager, StateTransitionError
from core.types import FormulaMetadata, FormulaType, Pin

WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8765
_server_thread: Optional[threading.Thread] = None


async def index_endpoint(request: Request) -> Response:
    """提供纯净可视化流水线编辑器 HTML 界面"""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui_prototype.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content)
    return HTMLResponse("<h1>ui_prototype.html 未找到</h1>", status_code=404)


async def get_session_endpoint(request: Request) -> Response:
    """获取指定会话的完整图纸拓扑、参数与算子数据"""
    session_id = request.path_params["session_id"]
    # 确保初始化时有默认基准场景
    session = workflow_manager.get_or_create_session(session_id)
    if not session.scenario_id:
        workflow_manager.propose_existing_scenario(
            session_id=session_id,
            scenario_id="scenario_valley_salt_steam",
            user_requirements="基准工况",
            initial_inputs={}
        )

    data = workflow_manager.get_session_view(session_id)
    return JSONResponse(data)


async def update_pipeline_endpoint(request: Request) -> Response:
    """前端可视化修改流水线拓扑后保存"""
    session_id = request.path_params["session_id"]
    body = await request.json()
    workflow_manager.update_pipeline_in_session(session_id, body)
    return JSONResponse({"status": "SUCCESS", "message": "流水线拓扑已同步更新"})


async def confirm_scenario_endpoint(request: Request) -> Response:
    """中断点 1：人工确认场景拓扑并进入参数阶段"""
    session_id = request.path_params["session_id"]
    body = await request.json()
    confirmed = body.get("confirmed", True)
    feedback = body.get("feedback", "")
    try:
        res = workflow_manager.confirm_scenario(session_id, confirmed=confirmed, feedback=feedback)
        return JSONResponse(res)
    except StateTransitionError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def update_parameters_endpoint(request: Request) -> Response:
    """中断点 2：实时保存前端填报微调的工况参数"""
    session_id = request.path_params["session_id"]
    body = await request.json()
    params = body.get("parameters", {})
    res = workflow_manager.update_parameters_in_session(session_id, params)
    return JSONResponse(res)


async def confirm_parameters_endpoint(request: Request) -> Response:
    """中断点 2：人工确认参数并授权程序计算"""
    session_id = request.path_params["session_id"]
    body = await request.json()
    confirmed = body.get("confirmed", True)
    feedback = body.get("feedback", "")
    try:
        res = workflow_manager.confirm_parameters(session_id, confirmed=confirmed, feedback=feedback)
        return JSONResponse(res)
    except StateTransitionError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def calculate_endpoint(request: Request) -> Response:
    """执行确定性程序计算并返回多目标成果"""
    session_id = request.path_params["session_id"]
    try:
        res = workflow_manager.execute_calculation(session_id)
        return JSONResponse(res)
    except StateTransitionError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def list_formulas_endpoint(request: Request) -> Response:
    """获取所有已注册的原子算子库列表"""
    formulas_list = default_formula_registry.to_ai_catalog()
    return JSONResponse({"formulas": formulas_list})


async def update_operator_endpoint(request: Request) -> Response:
    """原地全局修改原子算子名称或代数公式（遵循 ADR 0006）"""
    body = await request.json()
    op_id = body.get("operator_id")
    new_name = body.get("name")
    new_formula = body.get("formula")
    new_desc = body.get("description")

    try:
        f = default_formula_registry.get(op_id)
        if new_name:
            f.metadata.name = new_name
        if new_desc:
            f.metadata.description = new_desc
        if new_formula and isinstance(f, AlgebraicFormula):
            f.metadata.notes = new_formula
            # 若包含等号，重新初始化 SymPy 方程
            if "=" in new_formula:
                f.__init__(f.metadata, new_formula)

        return JSONResponse({"status": "SUCCESS", "message": f"算子 {op_id} 已全局原地更新生效！"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def add_operator_endpoint(request: Request) -> Response:
    """新增自定义原子算子"""
    body = await request.json()
    op_id = body.get("id")
    op_name = body.get("name")
    op_eq = body.get("equation", "y = x")

    if not op_id or not op_name:
        return JSONResponse({"error": "缺少算子ID或名称"}, status_code=400)

    try:
        new_f = AlgebraicFormula(
            metadata=FormulaMetadata(
                id=op_id,
                name=op_name,
                category="custom",
                description="由工程师在前端界面直接创建的原子算子",
                notes=op_eq,
                formula_type=FormulaType.ALGEBRAIC,
                inputs=[],
                outputs=[],
                expression=op_eq,
                is_bidirectional=True
            ),
            equation_str=op_eq
        )
        default_formula_registry.register(new_f)
        return JSONResponse({"status": "SUCCESS", "message": f"算子 {op_id} 已成功注册至全局公式库！"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


routes = [
    Route("/", endpoint=index_endpoint, methods=["GET"]),
    Route("/editor", endpoint=index_endpoint, methods=["GET"]),
    Route("/api/session/{session_id}", endpoint=get_session_endpoint, methods=["GET"]),
    Route("/api/session/{session_id}/pipeline", endpoint=update_pipeline_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/confirm_scenario", endpoint=confirm_scenario_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/parameters", endpoint=update_parameters_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/confirm_parameters", endpoint=confirm_parameters_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/calculate", endpoint=calculate_endpoint, methods=["POST"]),
    Route("/api/formulas", endpoint=list_formulas_endpoint, methods=["GET"]),
    Route("/api/operator/update", endpoint=update_operator_endpoint, methods=["POST"]),
    Route("/api/operator/add", endpoint=add_operator_endpoint, methods=["POST"]),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(debug=True, routes=routes, middleware=middleware)


def ensure_web_server_running(host: str = WEB_SERVER_HOST, port: int = WEB_SERVER_PORT) -> str:
    """
    确保轻量级 Web 服务在后台守护线程中启动运行，返回访问基地址
    """
    global _server_thread
    base_url = f"http://{host}:{port}"
    if _server_thread is not None and _server_thread.is_alive():
        return base_url

    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config=config)

    def _run():
        server.run()

    _server_thread = threading.Thread(target=_run, daemon=True)
    _server_thread.start()
    return base_url
