"""通过 MCP 注册、人工确认样例和正式执行验收场景内工程数据。"""

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from server import mcp_server as mcp
from starlette.testclient import TestClient
from server.web_app import app


def call(name, **kwargs):
    return json.loads(getattr(mcp, name)(**kwargs))


def definitions(rule_type="fixed_step", unit="kW", output_unit=None, **rule):
    output_unit = output_unit or unit
    formula = {
        "id": "test.engineering_data", "name": "通用数据取值", "category": "custom",
        "formula_type": "empirical", "handler": f"data.{rule_type}",
        "inputs": [{"name": "value", "unit": unit, "description": "查询量"}],
        "outputs": [{"name": "result", "unit": output_unit, "description": "取值成果"}],
        "data_inputs": [{"name": "table", "rule_type": rule_type,
                         "input_unit": unit, "output_unit": output_unit}],
    }
    pipeline = {
        "id": "test_engineering_data", "name": "陌生工程数据",
        "required_inputs": [{"name": "novel_quantity", "unit": unit, "description": "任意需求",
                             "default_value": 2.5, "kind": "constant"}],
        "data_tables": [{"id": "novel_rule", "description": "场景自有规则",
                         "input_unit": unit, "output_unit": output_unit, "rule_type": rule_type, **rule}],
        "steps": [{"step_id": "lookup", "formula_id": formula["id"],
                   "input_map": {"value": "novel_quantity"}, "output_map": {"result": "answer"},
                   "data_map": {"table": "novel_rule"}}],
    }
    return formula, pipeline


def register(formula, pipeline):
    result = call("register_new_formula", formula_definition=formula,
                  filename="通用数据_engineering_data.json", human_approved=True)
    assert result.get("status") == "SUCCESS", result
    result = call("register_new_pipeline", pipeline_definition=pipeline,
                  pipeline_filename="test_engineering_data.json", human_approved=True)
    assert result.get("status") == "SUCCESS", result


@pytest.fixture
def no_browser(monkeypatch):
    # 只替换打开浏览器这一外部副作用；使用真实核心和状态机。
    monkeypatch.setattr(mcp, "editor_link", lambda *args: "http://localhost/fixture")
    monkeypatch.setattr(mcp.webbrowser, "open", lambda *args: False)


def calculate(value=2.5, session="data-fixture"):
    proposed = call("match_or_propose_scenario", session_id=session, user_requirements="自动化确认样例",
                    scenario_id="test_engineering_data", initial_inputs={"novel_quantity": value})
    assert proposed["status"] == "SCENARIO_PROPOSED", proposed
    assert call("execute_calculation", session_id=session)["security_block"]
    assert call("confirm_scenario", session_id=session, confirmed=True)["status"] == "SCENARIO_CONFIRMED"
    assert call("inspect_and_validate_parameters", session_id=session)["is_complete"]
    assert call("confirm_parameters", session_id=session, confirmed=True)["status"] == "PARAMETERS_CONFIRMED"
    result = call("execute_calculation", session_id=session)
    assert result["status"] == "CALCULATED", result
    return result["result"]


def test_json_fixed_step_runs_through_existing_mcp_workflow(no_browser):
    register(*definitions(step=1, mode="nearest"))
    result = calculate()
    assert result["final_outputs"] == {"answer": 3}
    assert result["results"] == [{"step_id": "lookup", "formula_id": "test.engineering_data",
                                   "formula_name": "通用数据取值", "pin": "result", "variable": "answer",
                                   "description": "取值成果", "unit": "kW", "value": 3}]


@pytest.mark.parametrize("rule,mode,value,expected", [
    ({"step": 1}, "ceil", 2.1, 3), ({"step": 1}, "floor", 2.9, 2),
    ({"step": 1}, "nearest", 2.4, 2), ({"step": 1}, "nearest", 2.5, 3),
    ({"step": 1}, "nearest", -2.5, -3), ({"step": 1}, "ceil", -2.5, -2),
    ({"step": 1}, "floor", -2.5, -3), ({"step": 0.1}, "ceil", 0.3, 0.3),
    ({"step": 0.1}, "floor", 0.3, 0.3), ({"step": 0.1}, "nearest", 0.25, 0.3),
    ({"levels": [-9, -3, 2, 8, 15]}, "ceil", 3, 8),
    ({"levels": [-9, -3, 2, 8, 15]}, "floor", 3, 2),
    ({"levels": [-9, -3, 2, 8, 15]}, "nearest", 5, 8),
    ({"levels": [-9, -3, 2, 8, 15]}, "nearest", -6, -9),
    ({"levels": [-9, -3, 2, 8, 15]}, "nearest", 2, 2),
    ({"levels": [-9, -3, 2, 8, 15]}, "floor", -100, -9),
    ({"levels": [-9, -3, 2, 8, 15]}, "ceil", 100, 15),
    ({"levels": [0.1, 0.4, 1]}, "nearest", 0.25, 0.4),
])
def test_json_quantization_modes_and_half_away_from_zero(no_browser, rule, mode, value, expected):
    rule_type = "fixed_step" if "step" in rule else "discrete"
    register(*definitions(rule_type, mode=mode, **rule))
    assert calculate(value)["final_outputs"] == {"answer": expected}


@pytest.mark.parametrize("value,expected", [(-100, 40), (0, 40), (9, 40), (10, 90),
                                          (19, 90), (20, 15), (100, 15)])
def test_piecewise_uses_left_closed_segments_and_input_order_boundaries(no_browser, value, expected):
    register(*definitions("piecewise", output_unit="元/kWh", rows=[
        {"threshold": 0, "value": 40}, {"threshold": 10, "value": 90}, {"threshold": 20, "value": 15},
    ]))
    result = calculate(value)
    assert result["final_outputs"] == {"answer": expected}
    assert result["results"][0]["unit"] == "元/kWh"


def test_same_generic_formula_reuses_json_tables_and_emits_intermediate_results(no_browser):
    formula, pipeline = definitions(unit="t", step=1, mode="nearest")
    pipeline["required_inputs"][0].update(min_value=50, max_value=100)
    pipeline["data_tables"].append({**pipeline["data_tables"][0], "id": "other_scale", "step": 2, "mode": "floor"})
    pipeline["steps"].append({"step_id": "another_lookup", "formula_id": formula["id"],
                              "input_map": {"value": "answer"}, "output_map": {"result": "second_answer"},
                              "data_map": {"table": "other_scale"}})
    register(formula, pipeline)
    result = calculate()
    assert result["final_outputs"] == {"answer": 3, "second_answer": 2}
    assert [row["value"] for row in result["results"]] == [3, 2]
    assert [row["unit"] for row in result["results"]] == ["t", "t"]
    catalog = next(item for item in call("list_formulas") if item["id"] == formula["id"])
    assert catalog["definition"]["data_inputs"] == formula["data_inputs"]


@pytest.mark.parametrize("damage", ["missing", "duplicate", "name", "rule", "unit", "numeric_pin"])
def test_mcp_rejects_formula_data_port_contract_mismatches(damage):
    formula, _ = definitions(step=1, mode="nearest")
    if damage == "missing":
        del formula["data_inputs"]
    elif damage == "duplicate":
        formula["data_inputs"].append(deepcopy(formula["data_inputs"][0]))
    elif damage == "name":
        formula["data_inputs"][0]["name"] = "other"
    elif damage == "rule":
        formula["data_inputs"][0]["rule_type"] = "discrete"
    elif damage == "unit":
        formula["data_inputs"][0]["input_unit"] = "MW"
    else:
        formula["inputs"][0]["name"] = "other"
    before = call("list_formulas")
    assert "error" in call("register_new_formula", formula_definition=formula,
                           filename="通用数据_engineering_data.json", human_approved=True)
    assert call("list_formulas") == before


def test_tables_survive_editor_save_and_edits_require_confirmation(no_browser):
    formula, pipeline = definitions(step=1, mode="nearest")
    register(formula, pipeline)
    assert calculate()["final_outputs"] == {"answer": 3}
    assert calculate(session="other-data-session")["final_outputs"] == {"answer": 3}
    client = TestClient(app)
    base = "/api/session/data-fixture"
    before = client.get(base).json()
    edited = deepcopy(before["pipeline"])
    # 既有前端保存完整快照、只改布局，不撤销授权或丢失表字段。
    edited["layout"] = {"lookup": {"left": 10, "top": 20}}
    assert client.post(base + "/pipeline", json={"pipeline": edited, "allow_incomplete": True}).status_code == 200
    saved = client.get(base).json()
    assert saved["pipeline"]["data_tables"] == before["pipeline"]["data_tables"]
    assert saved["pipeline"]["steps"][0]["data_map"] == {"table": "novel_rule"}
    assert saved["current_state"] == "CALCULATED"
    # AI 或工程师更改数据规则后，复用原有失效与重新确认流程。
    edited["data_tables"][0]["step"] = 2
    assert client.post(base + "/pipeline", json={"pipeline": edited}).status_code == 200
    view = client.get(base).json()
    assert view["current_state"] == "SCENARIO_PROPOSED"
    assert view["calculation_result"] is None
    assert call("execute_calculation", session_id="data-fixture")["security_block"]
    assert call("confirm_scenario", session_id="data-fixture", confirmed=True)["status"] == "SCENARIO_CONFIRMED"
    call("inspect_and_validate_parameters", session_id="data-fixture")
    call("confirm_parameters", session_id="data-fixture", confirmed=True)
    assert call("execute_calculation", session_id="data-fixture")["result"]["final_outputs"] == {"answer": 2}
    other = client.get("/api/session/other-data-session").json()
    assert other["current_state"] == "CALCULATED"
    assert other["pipeline"]["data_tables"][0]["step"] == 1
    assert other["calculation_result"]["final_outputs"] == {"answer": 3}
    catalog = next(item for item in call("list_scenarios") if item["id"] == pipeline["id"])
    assert catalog["definition"]["data_tables"][0]["step"] == 1


@pytest.mark.parametrize("invalid", [False, True])
def test_table_preview_never_changes_formal_session(no_browser, invalid):
    register(*definitions("discrete", levels=[1, 4, 9], mode="ceil"))
    calculate()
    client = TestClient(app)
    base = "/api/session/data-fixture"
    before = client.get(base).json()
    snapshot = deepcopy(before["pipeline"])
    snapshot["data_tables"][0]["levels"] = [1, 6, 10] if not invalid else []
    response = client.post("/api/preview_calculation", json={"pipeline": snapshot, "parameters": {"novel_quantity": 5}})
    assert response.status_code == (400 if invalid else 200), response.text
    if not invalid:
        assert response.json()["preview_result"]["final_outputs"] == {"answer": 6}
        assert response.headers["cache-control"] == "no-store"
    assert client.get(base).json() == before


def test_registered_tables_and_session_snapshot_survive_restart(no_browser):
    formula, pipeline = definitions("piecewise", output_unit="元/kWh", rows=[
        {"threshold": 0, "value": 40}, {"threshold": 10, "value": 90}, {"threshold": 20, "value": 15},
    ])
    register(formula, pipeline)
    assert calculate(20)["final_outputs"] == {"answer": 15}
    script = '''
import json
from starlette.testclient import TestClient
from server import mcp_server as mcp
from server.web_app import app
def call(name, **kwargs):
    return json.loads(getattr(mcp, name)(**kwargs))
scene = next(s for s in call("list_scenarios") if s["id"] == "test_engineering_data")
assert scene["definition"]["data_tables"][0]["rows"][2]["value"] == 15
assert scene["definition"]["steps"][0]["data_map"] == {"table": "novel_rule"}
client = TestClient(app)
view = client.get("/api/session/data-fixture").json()
assert view["pipeline"]["data_tables"] == scene["definition"]["data_tables"]
assert view["calculation_result"] is None
assert call("execute_calculation", session_id="data-fixture")["security_block"]
call("confirm_scenario", session_id="data-fixture", confirmed=True)
call("inspect_and_validate_parameters", session_id="data-fixture")
call("confirm_parameters", session_id="data-fixture", confirmed=True)
assert call("execute_calculation", session_id="data-fixture")["result"]["final_outputs"] == {"answer": 15}
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                            env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("damage", ["step", "mode", "unknown", "unit", "missing_binding", "unknown_binding",
                                    "duplicate_table", "table_unit", "rule", "boolean", "numeric_table"])
def test_invalid_table_definitions_are_rejected_without_registering(damage):
    formula, pipeline = definitions(step=1, mode="nearest")
    if damage == "step":
        pipeline["data_tables"][0]["step"] = 0
    elif damage == "mode":
        pipeline["data_tables"][0]["mode"] = "bankers"
    elif damage == "unknown":
        pipeline["data_tables"][0]["python"] = "unsafe"
    elif damage == "unit":
        pipeline["data_tables"][0]["output_unit"] = "MW"
    elif damage == "missing_binding":
        pipeline["steps"][0]["data_map"] = {}
    elif damage == "unknown_binding":
        pipeline["steps"][0]["data_map"] = {"table": "absent"}
    elif damage == "duplicate_table":
        pipeline["data_tables"].append(deepcopy(pipeline["data_tables"][0]))
    elif damage == "table_unit":
        pipeline["data_tables"][0].update(input_unit="MW", output_unit="MW")
    elif damage == "rule":
        pipeline["data_tables"][0] = {"id": "novel_rule", "description": "规则不匹配", "input_unit": "kW",
                                      "output_unit": "kW", "rule_type": "discrete", "levels": [1, 2], "mode": "ceil"}
    elif damage == "boolean":
        pipeline["data_tables"][0]["step"] = True
    else:
        pipeline["steps"][0]["input_map"]["value"] = "novel_rule"
    call("register_new_formula", formula_definition=formula, filename="通用数据_engineering_data.json", human_approved=True)
    before = call("list_scenarios")
    assert "error" in call("register_new_pipeline", pipeline_definition=pipeline,
                           pipeline_filename="test_engineering_data.json", human_approved=True)
    assert call("list_scenarios") == before


@pytest.mark.parametrize("rule_type,rule", [
    ("discrete", {"levels": [], "mode": "ceil"}),
    ("discrete", {"levels": [2, 1], "mode": "ceil"}),
    ("discrete", {"levels": [1, 1], "mode": "floor"}),
    ("piecewise", {"rows": []}),
    ("piecewise", {"rows": [{"threshold": 1, "value": 5}, {"threshold": 1, "value": 6}]}),
])
def test_invalid_table_order_is_rejected_by_mcp(rule_type, rule):
    formula, pipeline = definitions(rule_type, **rule)
    call("register_new_formula", formula_definition=formula, filename="通用数据_engineering_data.json", human_approved=True)
    assert "error" in call("register_new_pipeline", pipeline_definition=pipeline,
                           pipeline_filename="test_engineering_data.json", human_approved=True)


@pytest.mark.parametrize("rule,rule_data,expected", [
    ("discrete", {"levels": [1, 4, 9], "mode": "nearest"}, 4),
    ("correlation", {"terms": [{"coefficient": 2, "power": 1}], "divisor": 1}, 5),
])
def test_real_stdio_exposes_data_schema_and_executes_proposed_table_scene(tmp_path, rule, rule_data, expected):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def exercise():
        root = Path(__file__).resolve().parents[1]
        launcher = ("import sys; sys.path.insert(0,sys.argv[1]); from server import mcp_server as m; "
                    "m.editor_link=lambda *a:'http://localhost/fixture'; "
                    "m.webbrowser.open=lambda *a:False; m.run_server()")
        server = StdioServerParameters(command=sys.executable, args=["-c", launcher, str(root)],
                                       cwd=str(tmp_path), env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=30) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                schema = next(t.input_schema for t in tools if t.name == "register_new_pipeline")
                assert "data_tables" in json.dumps(schema)
                assert "data_map" in json.dumps(schema)
                schema = next(t.input_schema for t in tools if t.name == "register_new_formula")
                assert "data_inputs" in json.dumps(schema)

                async def wire_call(name, **kwargs):
                    result = await client.call_tool(name, kwargs)
                    assert not result.is_error, result
                    return json.loads(next(c.text for c in result.content if c.type == "text"))

                formula, pipeline = definitions(rule, unit="t", **rule_data)
                result = await wire_call("register_new_formula", formula_definition=formula,
                                         filename="通用数据_engineering_data.json", human_approved=True)
                assert result["status"] == "SUCCESS", result
                assert (await wire_call("execute_calculation", session_id="wire-data"))["security_block"]
                proposed = await wire_call("match_or_propose_scenario", session_id="wire-data",
                                           user_requirements="自动化确认样例", new_scenario_def=pipeline)
                assert proposed["status"] == "SCENARIO_PROPOSED", proposed
                for key, value in rule_data.items():
                    assert proposed["scenario"]["data_tables"][0][key] == value
                await wire_call("confirm_scenario", session_id="wire-data", confirmed=True)
                await wire_call("inspect_and_validate_parameters", session_id="wire-data")
                await wire_call("confirm_parameters", session_id="wire-data", confirmed=True)
                result = await wire_call("execute_calculation", session_id="wire-data")
                assert result["result"]["final_outputs"] == {"answer": expected}, result

    asyncio.run(asyncio.wait_for(exercise(), timeout=60))
