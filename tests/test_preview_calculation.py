"""前端预览是临时计算，不进入正式会话或人工确认流程。"""

from copy import deepcopy
import json

import pytest
from starlette.testclient import TestClient

from server.web_app import app


def test_preview_calculates_current_values_without_changing_session_or_authorizing_execution():
    client = TestClient(app)
    base = "/api/session/preview_isolation"
    client.get(base)
    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 200
    assert client.post(base + "/parameters", json={"parameters": {}}).status_code == 200
    before = client.get(base).json()
    response = client.post("/api/preview_calculation", json={
        "pipeline": before["pipeline"], "parameters": {"steam_mass_flow": 120},
    })
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    preview = response.json()["preview_result"]
    assert preview["initial_inputs"]["steam_mass_flow"] == 120
    assert preview["final_outputs"]["annual_steam_wan_tons"] == 31.68
    assert client.get(base).json() == before
    assert client.post(base + "/calculate").status_code == 400
    from server import mcp_server
    formal = json.loads(mcp_server.execute_calculation("preview_isolation"))
    assert formal["security_block"] is True
    assert "result" not in formal


def test_preview_does_not_replace_previously_completed_official_result():
    client = TestClient(app)
    base = "/api/session/preview_after_formal"
    client.get(base)
    client.post(base + "/confirm_scenario", json={"confirmed": True})
    client.post(base + "/parameters", json={"parameters": {}})
    client.post(base + "/confirm_parameters", json={"confirmed": True})
    assert client.post(base + "/calculate").status_code == 200
    before = client.get(base).json()
    response = client.post("/api/preview_calculation", json={
        "pipeline": before["pipeline"], "parameters": {"steam_mass_flow": 120},
    })
    assert response.status_code == 200
    assert response.json()["preview_result"]["initial_inputs"]["steam_mass_flow"] == 120
    assert before["calculation_result"]["initial_inputs"]["steam_mass_flow"] == 100
    assert client.get(base).json() == before


@pytest.mark.parametrize("damage", ["missing", "number", "graph", "division", "payload"])
def test_invalid_preview_is_rejected_without_changing_session(damage):
    client = TestClient(app)
    base = "/api/session/preview_error"
    before = client.get(base).json()
    body = {"pipeline": deepcopy(before["pipeline"]), "parameters": {}}
    if damage == "missing":
        body["pipeline"]["required_inputs"][0]["default_value"] = None
    elif damage == "number":
        body["parameters"]["steam_mass_flow"] = True
    elif damage == "graph":
        body["pipeline"]["steps"][0]["formula_id"] = "missing.formula"
    elif damage == "division":
        body["parameters"].update(salt_hot_temperature=190, salt_cold_temperature=190)
    else:
        body["parameters"] = []
    response = client.post("/api/preview_calculation", json=body)
    assert response.status_code == 400, response.text
    assert "error" in response.json()
    assert client.get(base).json() == before


def test_preview_obeys_existing_same_origin_write_boundary():
    client = TestClient(app)
    assert client.post("/api/preview_calculation", json={}, headers={"Origin": "https://unrelated.invalid"}).status_code == 403
