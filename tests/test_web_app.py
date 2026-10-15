"""
Unit and integration tests for Starlette Web Service and REST API.
"""

import pytest
from starlette.testclient import TestClient
from server.web_app import app
from core.state_machine import workflow_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_index_and_editor_pages(client):
    """测试根路径和 /editor 页面正常返回 HTML"""
    resp_index = client.get("/")
    assert resp_index.status_code == 200
    assert "工业热工流程与参数可视化核对系统" in resp_index.text

    resp_editor = client.get("/editor?session_id=test_web_001&stage=1")
    assert resp_editor.status_code == 200
    assert "dag-workspace" in resp_editor.text


def test_full_web_api_lifecycle(client):
    """测试完整的 Web API 交互流转：获取会话 -> 确认场景 -> 更新参数 -> 确认参数 -> 计算执行"""
    session_id = "test_lifecycle_web_999"

    # 1. 获取会话数据
    resp_get = client.get(f"/api/session/{session_id}")
    assert resp_get.status_code == 200
    data = resp_get.json()
    assert data["session_id"] == session_id
    assert data["current_state"] == "SCENARIO_PROPOSED"
    assert "pipeline" in data

    # 2. 中断点 1：确认场景拓扑
    resp_confirm_scen = client.post(
        f"/api/session/{session_id}/confirm_scenario",
        json={"confirmed": True, "feedback": ""}
    )
    assert resp_confirm_scen.status_code == 200
    assert resp_confirm_scen.json()["status"] == "SCENARIO_CONFIRMED"

    # 3. 中断点 2：填报与微调参数
    new_params = {
        "steam_mass_flow": 120.0,
        "steam_pressure": 1.6,
        "steam_temperature": 210.0,
    }
    resp_params = client.post(
        f"/api/session/{session_id}/parameters",
        json={"parameters": new_params}
    )
    assert resp_params.status_code == 200
    p_data = resp_params.json()
    assert p_data["is_complete"] is True
    assert p_data["parameters_summary"]["steam_mass_flow"] == 120.0
    # 4. 中断点 2：确认参数并授权计算
    resp_confirm_params = client.post(
        f"/api/session/{session_id}/confirm_parameters",
        json={"confirmed": True, "feedback": ""}
    )
    assert resp_confirm_params.status_code == 200
    assert resp_confirm_params.json()["status"] == "PARAMETERS_CONFIRMED"

    # 5. 执行程序计算
    resp_calc = client.post(f"/api/session/{session_id}/calculate")
    assert resp_calc.status_code == 200
    calc_res = resp_calc.json()
    assert calc_res["status"] == "CALCULATED"
    assert "result" in calc_res
    # 流量提升至 120t/h 时，电加热器与 SGS 选型相应调整
    assert calc_res["result"]["sizing_summary"]["heater_sizing_mw"] >= 80.0


def test_operator_update_and_add_apis(client):
    """测试算子原地修改与新增算子 REST API"""
    # 1. 算子原地修改
    resp_update = client.post(
        "/api/operator/update",
        json={
            "operator_id": "thermal.sgs_power",
            "name": "SGS换热功率计算(已更新)",
            "formula": "sgs_power = theoretical_power / heat_exchanger_efficiency",
            "description": "测试更新描述"
        }
    )
    assert resp_update.status_code == 200
    assert resp_update.json()["status"] == "SUCCESS"

    # 2. 新增自定义算子
    resp_add = client.post(
        "/api/operator/add",
        json={
            "id": "thermal.test_custom_add",
            "name": "测试自定义换热计算",
            "equation": "q_test = m_flow * dt_val"
        }
    )
    assert resp_add.status_code == 200
    assert resp_add.json()["status"] == "SUCCESS"
