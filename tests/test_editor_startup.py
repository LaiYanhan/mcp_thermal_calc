"""独立调试入口与指定场景的网页会话回归。"""

import os
from pathlib import Path
import subprocess
import sys
from starlette.testclient import TestClient
from core.formula import registry
from core.pipeline import Pipeline, pipeline_registry
from server.web_app import app


def test_list_pipelines_works_in_windows_gbk_console():
    result = subprocess.run(
        [sys.executable, "run_web.py", "--list"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONIOENCODING": "gbk"},
        capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("gbk", errors="replace")
    assert b"scenario_valley_salt_steam" in result.stdout


def test_selected_custom_pipeline_survives_edit_confirm_calculate_and_sync():
    registry.save_operator({
        "id": "custom.multiply", "name": "数量换算", "equation": "y = x * k",
        "inputs": [{"name": "x", "description": "数量", "unit": "t"},
                   {"name": "k", "description": "倍率", "unit": "/"}],
        "outputs": [{"name": "y", "description": "换算数量", "unit": "t"}],
    })
    pipeline_registry.save_pipeline(Pipeline.from_dict({
        "id": "custom_scene", "name": "自定义场景", "required_inputs": [
            {"name": "quantity", "description": "数量", "unit": "t", "default_value": 2},
            {"name": "factor", "description": "倍率", "unit": "/", "default_value": 3, "kind": "constant"}],
        "steps": [{"step_id": "multiply", "formula_id": "custom.multiply",
                   "input_map": {"x": "quantity", "k": "factor"}, "output_map": {"y": "answer"}}],
    }))
    client = TestClient(app)
    base = "/api/session/selected_scene"
    view = client.get(base + "?pipeline=custom_scene&reset=1").json()
    assert view["pipeline"]["id"] == "custom_scene"
    pipeline = view["pipeline"]
    pipeline["layout"] = {"step:multiply": {"left": 420, "top": 280}}
    assert client.post(base + "/pipeline", json={"pipeline": pipeline}).status_code == 200
    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 200
    assert client.post(base + "/parameters", json={"parameters": {"quantity": 5}}).status_code == 200
    assert client.post(base + "/confirm_parameters", json={"confirmed": True}).status_code == 200
    result = client.post(base + "/calculate").json()["result"]
    assert result["final_outputs"] == {"answer": 15}
    restored = client.get(base).json()
    assert restored["current_state"] == "CALCULATED"
    assert restored["pipeline"]["layout"] == pipeline["layout"]
    assert restored["calculation_result"] == result
