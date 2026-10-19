"""AI 控制展示阶段；前端调试开关不改变计算授权规则。"""

import json
import sys
import pytest
from starlette.testclient import TestClient
from core.state_machine import workflow_manager, StateTransitionError
from server.web_app import app
from server import mcp_server
import run_web


def test_ai_controls_existing_editor_without_authorizing_calculation(monkeypatch):
    client = TestClient(app)
    base = "/api/session/ai_stage_control"
    assert client.get(base).json()["editor_stage"] == 1
    # 未审核场景不能由展示命令跳过确认。
    blocked = json.loads(mcp_server.open_pipeline_editor("ai_stage_control", 2))
    assert "error" in blocked
    workflow_manager.confirm_scenario("ai_stage_control", True)
    workflow_manager.inspect_parameters("ai_stage_control")
    # 参数检查并不自行切换阶段，由 AI 显式调用工具。
    assert client.get(base).json()["editor_stage"] == 1
    monkeypatch.setattr(mcp_server, "ensure_web_server_running", lambda: "http://127.0.0.1:8765")
    monkeypatch.setattr(mcp_server.webbrowser, "open", lambda *args: False)
    switched = json.loads(mcp_server.open_pipeline_editor("ai_stage_control", 2))
    assert switched["status"] == "SUCCESS"
    assert switched["stage"] == 2
    assert client.get(base).json()["editor_stage"] == 2
    with pytest.raises(StateTransitionError):
        workflow_manager.execute_calculation("ai_stage_control")


@pytest.mark.parametrize("stage", [0, 3, True, "2"])
def test_editor_stage_rejects_invalid_values(stage):
    with pytest.raises(ValueError):
        workflow_manager.set_editor_stage("invalid_editor_stage", stage)


def test_debug_flag_is_server_controlled_and_required_for_stage_option(monkeypatch):
    monkeypatch.setattr(app.state, "editor_debug", False, raising=False)
    client = TestClient(app)
    assert client.get("/api/session/no_debug?debug=1&stage=2").json()["editor_debug"] is False
    monkeypatch.setattr(sys, "argv", ["run_web.py", "--stage", "2"])
    with pytest.raises(SystemExit) as error:
        run_web.parse_args()
    assert error.value.code == 2
    monkeypatch.setattr(sys, "argv", ["run_web.py", "--debug", "--stage", "2", "--no-browser"])
    monkeypatch.setattr(run_web.editor_backend, "serve", lambda *args, **kwargs: None)
    run_web.main()
    assert client.get("/api/session/with_debug").json()["editor_debug"] is True


def test_parameter_edit_revokes_result_and_requires_new_confirmation():
    client = TestClient(app)
    base = "/api/session/no_automatic_recalculation"
    client.get(base)
    workflow_manager.confirm_scenario("no_automatic_recalculation", True)
    workflow_manager.inspect_parameters("no_automatic_recalculation")
    workflow_manager.confirm_parameters("no_automatic_recalculation", True)
    workflow_manager.execute_calculation("no_automatic_recalculation")
    response = client.post(base + "/parameters", json={"parameters": {"steam_mass_flow": 120}})
    assert response.status_code == 200
    view = client.get(base).json()
    assert view["current_state"] == "PARAMETERS_INSPECTED"
    assert view["calculation_result"] is None
    assert client.post(base + "/calculate").status_code == 400
