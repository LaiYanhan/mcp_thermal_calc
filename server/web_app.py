"""本地 Starlette 编辑器接口；校验和计算由 core 统一处理。"""

import threading
import socket
from functools import wraps
from pathlib import Path
from typing import Optional
import uvicorn
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route
import core.catalog
from core.formula import default_formula_registry
from core.pipeline import PipelineValidationError, pipeline_registry
from core.state_machine import workflow_manager, StateTransitionError
from core.storage import engine_lock

WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8765
ROOT = Path(__file__).resolve().parents[1]
_server_thread: Optional[threading.Thread] = None


def api_endpoint(function):
    @wraps(function)
    async def wrapped(request):
        try:
            return await function(request)
        except PipelineValidationError as error:
            return JSONResponse({"error": str(error), "validation": {"is_valid": False, "errors": error.errors}}, status_code=400)
        except (StateTransitionError, ValueError, KeyError, TypeError, ValidationError, ArithmeticError) as error:
            return JSONResponse({"error": str(error)}, status_code=400)
    return wrapped


async def request_body(request):
    if int(request.headers.get("content-length", "0")) > 200000:
        raise ValueError("请求内容过大")
    body = await request.json()
    if not isinstance(body, dict):
        raise ValueError("请求必须是 JSON 对象")
    return body


class LocalEditorMiddleware:
    """只接受编辑器同源写入；非浏览器 MCP/本地客户端仍可直接调用。"""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope)
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.url.netloc}"
            if (origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site":
                await JSONResponse({"error": "仅允许本地编辑器同源请求"}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def index_endpoint(request):
    return HTMLResponse((ROOT / "preview" / "pipeline_editor_preview.html").read_text(encoding="utf-8"))


async def editor_script_endpoint(request):
    return Response((ROOT / "ui_editor.js").read_text(encoding="utf-8"), media_type="application/javascript")


@api_endpoint
async def get_session_endpoint(request):
    session_id = request.path_params["session_id"]
    pipeline_target = request.query_params.get("pipeline") or request.query_params.get("pipeline_id") or request.query_params.get("scenario_id")
    reset_param = request.query_params.get("reset") in ("1", "true", "True")
    with engine_lock:
        session = workflow_manager.get_or_create_session(session_id)
        if pipeline_target:
            pipeline = pipeline_registry.resolve(pipeline_target)
            if not session.scenario_id or session.scenario_id != pipeline.id or reset_param:
                workflow_manager.propose_existing_scenario(session_id, pipeline.id, "独立测试调试", {})
        elif not session.scenario_id or reset_param:
            workflow_manager.propose_existing_scenario(session_id, "scenario_electric_heater_salt_steam", "基准工况", {})
        return JSONResponse({**workflow_manager.get_session_view(session_id),
                             "editor_debug": bool(getattr(request.app.state, "editor_debug", False))})

@api_endpoint
async def update_pipeline_endpoint(request):
    body = await request_body(request)
    if "pipeline" in body:
        if type(body.get("allow_incomplete", False)) is not bool:
            raise ValueError("allow_incomplete 必须为布尔值")
        data, allow_incomplete = body["pipeline"], body.get("allow_incomplete", False)
    else:
        data, allow_incomplete = body, False
    validation = workflow_manager.update_pipeline_in_session(request.path_params["session_id"], data, allow_incomplete)
    return JSONResponse({"status": "SUCCESS" if validation["is_valid"] else "DRAFT", "validation": validation})


@api_endpoint
async def confirm_scenario_endpoint(request):
    body = await request_body(request)
    return JSONResponse(workflow_manager.confirm_scenario(request.path_params["session_id"], body.get("confirmed"), body.get("feedback", "")))


@api_endpoint
async def update_parameters_endpoint(request):
    body = await request_body(request)
    if not isinstance(body.get("parameters"), dict):
        raise ValueError("parameters 必须为对象")
    return JSONResponse(workflow_manager.update_parameters_in_session(request.path_params["session_id"], body["parameters"]))


@api_endpoint
async def confirm_parameters_endpoint(request):
    body = await request_body(request)
    return JSONResponse(workflow_manager.confirm_parameters(request.path_params["session_id"], body.get("confirmed"), body.get("feedback", "")))


@api_endpoint
async def calculate_endpoint(request):
    return JSONResponse(workflow_manager.execute_calculation(request.path_params["session_id"]))


@api_endpoint
async def list_formulas_endpoint(request):
    return JSONResponse({"formulas": default_formula_registry.to_ai_catalog()})

@api_endpoint
async def list_pipelines_endpoint(request):
    return JSONResponse({"pipelines": pipeline_registry.to_ai_catalog()})


@api_endpoint
async def update_operator_endpoint(request):
    body = await request_body(request)
    with engine_lock:
        formula = default_formula_registry.save_operator(body, update=True)
        workflow_manager.invalidate_formula(formula.metadata.id)
    return JSONResponse({"status": "SUCCESS", "message": "算子已全局更新，请重新确认相关场景"})


@api_endpoint
async def add_operator_endpoint(request):
    body = await request_body(request)
    default_formula_registry.save_operator(body)
    return JSONResponse({"status": "SUCCESS", "message": "算子已保存，可选装到流水线"})


routes = [
    Route("/", index_endpoint),
    Route("/editor", index_endpoint),
    Route("/ui_editor.js", editor_script_endpoint),
    Route("/api/session/{session_id}", get_session_endpoint),
    Route("/api/session/{session_id}/pipeline", update_pipeline_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/confirm_scenario", confirm_scenario_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/parameters", update_parameters_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/confirm_parameters", confirm_parameters_endpoint, methods=["POST"]),
    Route("/api/session/{session_id}/calculate", calculate_endpoint, methods=["POST"]),
    Route("/api/formulas", list_formulas_endpoint),
    Route("/api/operator/update", update_operator_endpoint, methods=["POST"]),
    Route("/api/operator/add", add_operator_endpoint, methods=["POST"]),
    Route("/api/pipelines", list_pipelines_endpoint),
]
app = Starlette(debug=False, routes=routes, middleware=[
    Middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]),
    Middleware(LocalEditorMiddleware),
])


def ensure_web_server_running(host: str = WEB_SERVER_HOST, port: int = WEB_SERVER_PORT) -> str:
    global _server_thread
    if _server_thread is not None and _server_thread.is_alive():
        return f"http://{host}:{port}"
    # 先占用监听套接字，避免把其他进程的同端口编辑器误认成本会话。
    sock = socket.socket()
    try:
        sock.bind((host, port))
        sock.listen(128)
    except OSError:
        sock.close()
        raise RuntimeError(f"编辑器端口 {port} 已被占用，请先关闭独立 Web 服务再从 MCP 打开")
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    _server_thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    _server_thread.start()
    return f"http://{host}:{port}"
