"""Recovery Audit P0/P1 的实际调用路径回归。"""

import ast
import json
import re
import shutil
import subprocess
import os
from copy import deepcopy
from pathlib import Path
import pytest
from starlette.testclient import TestClient
from server.web_app import app
from core.formula import default_formula_registry as registry
from core.pipeline import Pipeline, pipeline_registry
from core.state_machine import WorkflowManager, StateTransitionError, workflow_manager
from core.types import Pin

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def prepare(client, session="recovery"):
    base = f"/api/session/{session}"
    assert client.get(base).status_code == 200
    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 200
    assert client.post(base + "/parameters", json={"parameters": {}}).status_code == 200
    assert client.post(base + "/confirm_parameters", json={"confirmed": True}).status_code == 200
    return base


def test_mcp_entry_syntax():
    ast.parse((ROOT / "server/mcp_server.py").read_text(encoding="utf-8"))


def test_html_explicit_nesting_and_unique_ids():
    from html.parser import HTMLParser

    class EditorParser(HTMLParser):
        stack = []
        ids = set()

        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            if "id" in attrs:
                assert attrs["id"] not in self.ids, f"重复 DOM ID: {attrs['id']}"
                self.ids.add(attrs["id"])
            if tag not in {"meta", "link", "input", "br", "hr", "img"}:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            assert self.stack and self.stack.pop() == tag, f"HTML 标签错配: {tag}"

    parser = EditorParser()
    parser.feed((ROOT / "ui_prototype.html").read_text(encoding="utf-8"))
    assert not parser.stack


def test_browser_script_compiles():
    node = shutil.which("node")
    assert node, "需要 Node 运行前端脚本语法回归"
    source = (ROOT / "ui_prototype.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b([^>]*)>([\s\S]*?)</script>", source, flags=re.I)
    for attributes, script in scripts:
        src = re.search(r'src="([^"]+)"', attributes)
        if src:
            if src[1].startswith("http"):
                continue
            script = (ROOT / src[1].lstrip("/")).read_text(encoding="utf-8")
        result = subprocess.run([node, "--check"], input=script, text=True, encoding="utf-8", capture_output=True)
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("body", [{}, {"confirmed": "false"}, {"confirmed": 1}])
def test_confirmation_requires_explicit_boolean(client, body):
    client.get("/api/session/confirm")
    response = client.post("/api/session/confirm/confirm_scenario", json=body)
    assert response.status_code == 400
    assert client.get("/api/session/confirm").json()["current_state"] == "SCENARIO_PROPOSED"


def test_edit_requires_reconfirmation_and_recalculates(client):
    base = prepare(client)
    response = client.post(base + "/parameters", json={"parameters": {"steam_mass_flow": 120}})
    assert response.status_code == 200
    assert response.json()["status"] == "PARAMETERS_INSPECTED"
    assert client.post(base + "/calculate").status_code == 400
    assert client.post(base + "/confirm_parameters", json={"confirmed": True}).status_code == 200
    assert client.post(base + "/calculate").json()["result"]["initial_inputs"]["steam_mass_flow"] == 120
    assert client.post(base + "/parameters", json={"parameters": {"steam_mass_flow": 110}}).status_code == 200
    assert client.get(base).json()["calculation_result"] is None


def test_failed_parameter_edit_is_atomic(client):
    base = prepare(client)
    before = client.get(base).json()
    response = client.post(base + "/parameters", json={"parameters": {"steam_mass_flow": -1}})
    assert response.status_code == 400
    after = client.get(base).json()
    assert after["provided_parameters"] == before["provided_parameters"]
    assert after["current_state"] == before["current_state"]


def test_parameter_rejection_can_be_corrected(client):
    base = prepare(client)
    client.post(base + "/parameters", json={"parameters": {"steam_mass_flow": 110}})
    assert client.post(base + "/confirm_parameters", json={"confirmed": False}).status_code == 200
    assert client.post(base + "/parameters", json={"parameters": {"steam_mass_flow": 120}}).status_code == 200


def test_edited_pipeline_is_inspected_and_invalidates_confirmation(client):
    base = prepare(client)
    data = client.get(base).json()["pipeline"]
    data["required_inputs"].append({"name": "extra", "unit": "MW", "description": "新增必填量"})
    assert client.post(base + "/pipeline", json=data).status_code == 200
    assert client.post(base + "/calculate").status_code == 400
    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 200
    inspection = client.post(base + "/parameters", json={"parameters": {}}).json()
    assert inspection["is_complete"] is False
    assert any(p["name"] == "extra" for p in inspection["missing_inputs"])
    assert client.post(base + "/confirm_parameters", json={"confirmed": True}).status_code == 400


def test_empty_pipeline_is_rejected_without_mutation(client):
    base = prepare(client)
    before = client.get(base).json()["pipeline"]
    data = deepcopy(before)
    data["steps"] = []
    assert client.post(base + "/pipeline", json=data).status_code == 400
    assert client.get(base).json()["pipeline"] == before


def test_unordered_dag_executes_in_dependency_order():
    data = pipeline_registry.get("scenario_valley_salt_steam").to_dict()
    expected = Pipeline.from_dict(data).execute({}).final_outputs
    data["steps"].reverse()
    assert Pipeline.from_dict(data).execute({}).final_outputs == expected


@pytest.mark.parametrize("damage", ["cycle", "duplicate", "missing_output", "unit"])
def test_invalid_graph_is_rejected(client, damage):
    base = prepare(client)
    data = client.get(base).json()["pipeline"]
    if damage == "cycle":
        data["steps"][0]["input_map"]["steam_pressure"] = "sgs_power"
    elif damage == "duplicate":
        data["steps"][1]["step_id"] = data["steps"][0]["step_id"]
    elif damage == "missing_output":
        data["steps"][0]["output_map"] = {}
    else:
        data["required_inputs"][0]["unit"] = "t/h"
    assert client.post(base + "/pipeline", json=data).status_code == 400


def operator_payload(identifier="thermal.recovery"):
    return {"id": identifier, "name": "测试算子", "equation": "y = x * 2",
            "inputs": [{"name": "x", "unit": "MW", "description": "输入功率"}],
            "outputs": [{"name": "y", "unit": "MW", "description": "输出功率"}]}


def test_added_operator_has_executable_pins(client):
    assert client.post("/api/operator/add", json=operator_payload()).status_code == 200
    assert registry.get("thermal.recovery").execute({"x": 3}) == {"y": 6}


def test_add_does_not_overwrite_existing_operator(client):
    before = registry.get("thermal.sgs_power")
    assert client.post("/api/operator/add", json=operator_payload("thermal.sgs_power")).status_code == 400
    assert registry.get("thermal.sgs_power") is before


def test_failed_operator_update_is_atomic(client):
    before = deepcopy(registry.to_ai_catalog())
    response = client.post("/api/operator/update", json={"operator_id": "thermal.sgs_power", "name": "不应保留", "formula": "invalid = !"})
    assert response.status_code == 400
    assert registry.to_ai_catalog() == before


def test_expression_cannot_call_python(client):
    data = operator_payload()
    data["equation"] = "y = __import__('builtins').len([]) + x"
    assert client.post("/api/operator/add", json=data).status_code == 400


@pytest.mark.parametrize("equation", ["y ** 2 = x", "y = (x ** 12) ** 12", "y = x ** x"])
def test_unsupported_or_ambiguous_formula_is_rejected_at_registration(client, equation):
    data = operator_payload()
    data["equation"] = equation
    assert client.post("/api/operator/add", json=data).status_code == 400
    with pytest.raises(KeyError):
        registry.get(data["id"])


def test_global_formula_change_revokes_confirmation(client):
    base = prepare(client)
    response = client.post("/api/operator/update", json={"operator_id": "thermal.theoretical_power", "formula": "theoretical_power = steam_mass_flow * enthalpy_diff / 7200"})
    assert response.status_code == 200
    assert client.post(base + "/calculate").status_code == 400
    assert client.get(base).json()["calculation_result"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_pin_rejects_nonfinite_or_boolean(value):
    with pytest.raises(ValueError):
        Pin("x", "MW", "功率", min_value=0).validate(value)


def test_inverse_respects_pin_ranges():
    with pytest.raises(ValueError):
        registry.get("thermal.theoretical_power").solve({"theoretical_power": -10, "enthalpy_diff": 2712}, "steam_mass_flow")


@pytest.mark.parametrize("parameters", [{"salt_hot_temperature": 190, "salt_cold_temperature": 190}, {"salt_hot_temperature": 600}])
def test_salt_boundaries_fail_during_inspection(client, parameters):
    client.get("/api/session/salt")
    client.post("/api/session/salt/confirm_scenario", json={"confirmed": True})
    assert client.post("/api/session/salt/parameters", json={"parameters": parameters}).status_code == 400


def test_new_proposal_clears_old_result(client):
    base = prepare(client)
    client.post(base + "/calculate")
    workflow_manager.propose_existing_scenario("recovery", "scenario_valley_salt_steam", "修改", {"steam_mass_flow": 120})
    assert client.get(base).json()["calculation_result"] is None


def test_foreign_origin_cannot_write(client):
    response = client.post("/api/operator/add", json=operator_payload(), headers={"Origin": "https://unrelated.invalid"})
    assert response.status_code == 403


def test_session_restores_draft_but_not_authorization(client):
    base = prepare(client)
    restored = WorkflowManager().get_session_view("recovery")
    assert restored["pipeline"] == client.get(base).json()["pipeline"]
    assert restored["current_state"] == "SCENARIO_PROPOSED"
    assert restored["calculation_result"] is None


@pytest.mark.parametrize("parameters", [{"steam_pressure": 10, "steam_temperature": 200},
                                      {"feedwater_pressure": 0.05, "feedwater_temperature": 150}])
def test_wrong_phase_rejected_before_confirmation(client, parameters):
    base = prepare(client)
    response = client.post(base + "/parameters", json={"parameters": parameters})
    assert response.status_code == 400
    assert "相" in response.json()["error"]


def test_saturated_steam_uses_dry_vapor_enthalpy():
    from formulas.thermal.water_steam_properties import _xsteam
    temperature = _xsteam.tsat_p(15)
    result = registry.get("thermal.steam_enthalpy").execute({"steam_pressure": 1.5, "steam_temperature": temperature})
    assert result["steam_enthalpy"] == pytest.approx(_xsteam.hV_p(15))


def test_atomic_solver_cannot_bypass_confirmed_workload(client):
    with pytest.raises(StateTransitionError):
        workflow_manager.solve_atomic_formula("unapproved", "thermal.theoretical_power", {"steam_mass_flow": 100, "enthalpy_diff": 2700}, "theoretical_power")
    base = prepare(client)
    calculation = client.post(base + "/calculate").json()["result"]
    result = {**calculation["initial_inputs"], **calculation["final_outputs"]}
    known = {"steam_mass_flow": result["steam_mass_flow"], "enthalpy_diff": result["enthalpy_diff"]}
    assert workflow_manager.solve_atomic_formula("recovery", "thermal.theoretical_power", known, "theoretical_power")["calculated_value"] == result["theoretical_power"]
    known["steam_mass_flow"] = 120
    with pytest.raises(StateTransitionError):
        workflow_manager.solve_atomic_formula("recovery", "thermal.theoretical_power", known, "theoretical_power")


def test_missing_connection_draft_can_be_repaired(client):
    base = prepare(client)
    data = client.get(base).json()["pipeline"]
    removed = data["steps"].pop(0)
    response = client.post(base + "/pipeline", json={"pipeline": data, "allow_incomplete": True})
    assert response.json()["status"] == "DRAFT"
    assert any(item["code"] == "missing_source" for item in response.json()["validation"]["errors"])
    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 400
    data["steps"].append(removed)
    assert client.post(base + "/pipeline", json=data).status_code == 200
    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 200
    client.post(base + "/parameters", json={"parameters": {}})
    client.post(base + "/confirm_parameters", json={"confirmed": True})
    assert client.post(base + "/calculate").status_code == 200


def test_layout_only_edit_preserves_confirmation(client):
    base = prepare(client)
    data = client.get(base).json()["pipeline"]
    data["layout"] = {"step:steam": {"left": 30, "top": 70}}
    assert client.post(base + "/pipeline", json=data).status_code == 200
    assert client.post(base + "/calculate").status_code == 200


def test_unit_payload_requires_explicit_conversion(client):
    base = prepare(client)
    assert client.post(base + "/parameters", json={"parameters": {"steam_pressure": {"value": 15, "unit": "bar"}}}).status_code == 400
    assert client.post(base + "/parameters", json={"parameters": {"steam_pressure": {"value": 1.5, "unit": "MPa"}}}).status_code == 200


def test_new_formula_pipeline_and_session_survive_process_restart(client):
    assert client.post("/api/operator/add", json=operator_payload()).status_code == 200
    data = {"id": "recovery_pipeline", "name": "双分支恢复测试", "required_inputs": [
        {"name": "x", "unit": "MW", "description": "输入", "default_value": 3, "kind": "constant"},
        {"name": "z", "unit": "MW", "description": "独立输入", "default_value": 4}],
        "steps": [{"step_id": "double", "formula_id": "thermal.recovery", "input_map": {"x": "x"}, "output_map": {"y": "answer"}},
                  {"step_id": "other", "formula_id": "thermal.recovery", "input_map": {"x": "z"}, "output_map": {"y": "other_answer"}}],
        "output_groups": [{"id": "a", "name": "分支一", "keys": ["answer"]}, {"id": "b", "name": "分支二", "keys": ["other_answer"]}]}
    pipeline_registry.save_pipeline(Pipeline.from_dict(data))
    workflow_manager.propose_new_scenario("persist", data, "恢复测试", {"x": 5})
    script = """
import json, formulas, pipelines
from core.state_machine import WorkflowManager
from core.pipeline import pipeline_registry
from core.formula import default_formula_registry
m = WorkflowManager()
view = m.get_session_view('persist')
assert view['current_state'] == 'SCENARIO_PROPOSED'
assert view['provided_parameters']['x'] == 5
assert 'output_groups' not in view['pipeline']
m.confirm_scenario('persist', True)
m.inspect_parameters('persist')
m.confirm_parameters('persist', True)
result = m.execute_calculation('persist')['result']['final_outputs']
assert result['answer'] == 10 and result['other_answer'] == 8
assert pipeline_registry.get('recovery_pipeline').execute({}).final_outputs['answer'] == 6
print('RESTORE_OK')
"""
    import sys
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "RESTORE_OK" in result.stdout


def test_dynamic_registration_rejects_code_paths_and_unknown_match(monkeypatch):
    from server import mcp_server
    monkeypatch.setattr(mcp_server, "editor_link", lambda *args: "http://127.0.0.1/editor")
    monkeypatch.setattr(mcp_server.webbrowser, "open", lambda *args: None)
    source = json.dumps(operator_payload("custom.registered"))
    assert json.loads(mcp_server.register_new_formula(source, "thermal", "../escape.py", True)).get("error")
    assert json.loads(mcp_server.register_new_formula("import os\nos.system('echo BAD')", "thermal", "safe.py", True)).get("error")
    assert json.loads(mcp_server.register_new_formula(source, "thermal", "safe.json", True))["status"] == "SUCCESS"
    assert registry.get("custom.registered").execute({"x": 3}) == {"y": 6}
    result = json.loads(mcp_server.match_or_propose_scenario("unknown", "陌生场景"))
    assert result["status"] == "SCENARIO_SELECTION_REQUIRED"
    assert workflow_manager.get_or_create_session("unknown").pipeline_data is None


def test_existing_declarative_template_registers_without_executing_code():
    from core.extensions import parse_definition
    source = '''
from core.types import Pin, FormulaMetadata, FormulaType
from core.formula import AlgebraicFormula, default_formula_registry
metadata = FormulaMetadata(id="custom.template", name="模板功率", category="custom",
    description="测试声明式模板", notes="", formula_type=FormulaType.ALGEBRAIC,
    inputs=[Pin(name="x", unit="MW", description="输入")],
    outputs=[Pin(name="y", unit="MW", description="输出")])
formula = AlgebraicFormula(metadata, "y = x * 2")
default_formula_registry.register(formula)
'''
    data = parse_definition(source, "formula")
    with pytest.raises(KeyError):
        registry.get("custom.template")
    saved = registry.save_operator(data)
    assert saved.execute({"x": 4}) == {"y": 8}


def test_editor_behavior_regressions():
    result = subprocess.run([shutil.which("node"), "--test", str(ROOT / "tests/test_editor.js")], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_mcp_stdio_entry_initializes_and_blocks_unapproved_calculation(tmp_path):
    import sys
    import anyio
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def run():
        with anyio.fail_after(20):
            settings = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server/mcp_server.py")],
                                             cwd=ROOT, env={"THERMAL_CALC_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"})
            async with stdio_client(settings) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    initialized = await session.initialize()
                    assert initialized.server_info.name == "thermal-calc-sizing-engine"
                    catalog = await session.list_tools()
                    assert len(catalog.tools) == 11
                    result = await session.call_tool("execute_calculation", {"session_id": "unapproved"})
                    assert json.loads(result.content[0].text)["security_block"] is True
                    invalid = await session.call_tool("confirm_scenario", {"session_id": "unapproved", "confirmed": 1})
                    assert invalid.is_error
                    scenarios = await session.call_tool("list_scenarios", {})
                    assert "scenario_electric_heater_salt_steam" in scenarios.content[0].text

    anyio.run(run)
