"""按节点求解、全部成果输出，以及前后端共享的变量契约。"""

import json
import pytest
from starlette.testclient import TestClient
from core.formula import registry
from core.pipeline import Pipeline, pipeline_registry
from core.state_machine import WorkflowManager
from server.web_app import app


def power_pipeline(target="theoretical_power"):
    formula = registry.get("thermal.theoretical_power")
    knowns, outputs = formula.pin_contract(target)
    values = {"steam_mass_flow": 14.4, "enthalpy_diff": 2500, "theoretical_power": 10}
    return {
        "id": "target_demo", "name": "产汽关系", "category": "custom", "description": "", "notes": "",
        "required_inputs": [{"name": name, "description": pin.description, "unit": pin.unit,
                             "default_value": values[name]} for name, pin in knowns.items()],
        "steps": [{"step_id": "power", "formula_id": formula.metadata.id, "solve_target": target,
                   "input_map": {name: name for name in knowns}, "output_map": {name: name for name in outputs}}],
    }


@pytest.mark.parametrize("target, expected", [("steam_mass_flow", 14.4), ("enthalpy_diff", 2500), ("theoretical_power", 10)])
def test_every_variable_can_be_solved_in_pipeline(target, expected):
    result = Pipeline.from_dict(power_pipeline(target)).execute({})
    assert result.final_outputs == {target: pytest.approx(expected)}
    assert len(result.results) == 1
    output = result.results[0]
    assert output.step_id == "power" and output.pin == target and output.variable == target
    assert output.description and output.unit and output.value == pytest.approx(expected)
    assert not set(result.initial_inputs) & set(result.final_outputs)


def test_same_formula_in_both_directions_and_downstream_consumes_inverse():
    data = power_pipeline()
    data["steps"] += [
        {"step_id": "inverse", "formula_id": "thermal.theoretical_power", "solve_target": "steam_mass_flow",
         "input_map": {"theoretical_power": "theoretical_power", "enthalpy_diff": "enthalpy_diff"},
         "output_map": {"steam_mass_flow": "recovered_flow"}},
        {"step_id": "downstream", "formula_id": "thermal.theoretical_power",
         "input_map": {"steam_mass_flow": "recovered_flow", "enthalpy_diff": "enthalpy_diff"},
         "output_map": {"theoretical_power": "recovered_power"}},
    ]
    data["steps"].reverse()
    result = Pipeline.from_dict(data).execute({})
    assert result.final_outputs == {"theoretical_power": pytest.approx(10), "recovered_flow": pytest.approx(14.4), "recovered_power": pytest.approx(10)}
    assert [item.step_id for item in result.results] == ["power", "inverse", "downstream"]
    assert list(registry.get("thermal.theoretical_power").output_pins) == ["theoretical_power"]


@pytest.mark.parametrize("damage, code", [("target", "target"), ("pin", "pins"), ("unit", "unit"), ("cycle", "cycle"), ("missing", "missing_source")])
def test_inverse_validates_effective_pins_and_dependencies(damage, code):
    data = power_pipeline("steam_mass_flow")
    step = data["steps"][0]
    if damage == "target":
        step["solve_target"] = "nonexistent"
    elif damage == "pin":
        step["input_map"]["steam_mass_flow"] = "theoretical_power"
    elif damage == "unit":
        data["required_inputs"][0]["unit"] = "t/h"
    elif damage == "cycle":
        step["input_map"]["theoretical_power"] = "steam_mass_flow"
    else:
        step["input_map"]["theoretical_power"] = "missing"
    validation = Pipeline.from_dict(data).validate()
    assert code in {error["code"] for error in validation["errors"]}


def test_inverse_accepts_knowns_and_results_outside_display_bounds():
    pipeline = Pipeline.from_dict(power_pipeline("steam_mass_flow"))
    assert pipeline.execute({"theoretical_power": -1}).final_outputs["steam_mass_flow"] < 0
    assert pipeline.execute({"theoretical_power": 2000, "enthalpy_diff": 100}).final_outputs["steam_mass_flow"] == 72000


def test_empirical_keeps_forward_contract_and_all_outputs_are_results():
    data = pipeline_registry.get("scenario_electric_heater_salt_steam").to_dict()
    result = Pipeline.from_dict(data).execute({})
    assert len(result.results) == sum(len(step["output_map"]) for step in data["steps"])
    assert {item.variable for item in result.results} == set(result.final_outputs)
    assert not set(result.initial_inputs) & set(result.final_outputs)
    data["steps"][0]["solve_target"] = "steam_pressure"
    assert any(error["code"] == "target" for error in Pipeline.from_dict(data).validate()["errors"])


def test_legacy_groups_are_ignored_and_catalog_explains_all_targets():
    data = power_pipeline("steam_mass_flow")
    data.update(output_groups=[{"id": "old", "name": "旧成果", "keys": ["nonexistent"]}], sizing_output_keys=["nonexistent"])
    pipeline = Pipeline.from_dict(data)
    assert pipeline.validate()["is_valid"]
    assert "output_groups" not in pipeline.to_dict() and "sizing_output_keys" not in pipeline.to_dict()
    formula = next(item for item in registry.to_ai_catalog() if item["id"] == "thermal.theoretical_power")
    assert set(formula["solve_targets"]) == {"steam_mass_flow", "enthalpy_diff", "theoretical_power"}
    assert all(pin["description"] and pin["unit"] for pin in formula["variables"])
    for target, expression in formula["display_expressions"].items():
        assert expression.split("=")[0].strip() == next(pin["description"] for pin in formula["variables"] if pin["name"] == target)
        assert not any(pin["name"] in expression for pin in formula["variables"])


def test_web_inverse_reconfirms_and_restores_configuration():
    client = TestClient(app)
    base = "/api/session/target_web"
    client.get(base)
    data = power_pipeline("steam_mass_flow")
    assert client.post(base + "/pipeline", json={"pipeline": data}).status_code == 200
    assert client.post(base + "/calculate").status_code == 400

    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 200
    assert client.post(base + "/parameters", json={"parameters": {"theoretical_power": 20}}).status_code == 200
    assert client.post(base + "/confirm_parameters", json={"confirmed": True}).status_code == 200
    result = client.post(base + "/calculate").json()["result"]
    assert result["final_outputs"]["steam_mass_flow"] == pytest.approx(28.8)
    view = client.get(base).json()
    assert view["variables"]["steam_mass_flow"]["unit"] == "t/h"
    restored = WorkflowManager().get_session_view("target_web")
    assert restored["pipeline"]["steps"][0]["solve_target"] == "steam_mass_flow"
    assert restored["calculation_result"] is None
    assert client.post(base + "/pipeline", json={"pipeline": power_pipeline()}).status_code == 200
    assert client.get(base).json()["calculation_result"] is None
    assert "theoretical_power" not in client.get(base).json()["provided_parameters"]
    assert client.post(base + "/calculate").status_code == 400


def test_mcp_catalog_and_scenario_use_the_same_inverse_contract(monkeypatch):
    from server import mcp_server
    monkeypatch.setattr(mcp_server, "editor_link", lambda *args: "http://127.0.0.1/editor")
    monkeypatch.setattr(mcp_server.webbrowser, "open", lambda *args: None)
    catalog = json.loads(mcp_server.list_formulas())
    formula = next(item for item in catalog if item["id"] == "thermal.theoretical_power")
    assert "steam_mass_flow" in formula["solve_targets"]
    proposed = json.loads(mcp_server.match_or_propose_scenario(
        "target_mcp", "已知功率与焓差求流量", new_scenario_def=power_pipeline("steam_mass_flow")))
    assert "error" not in proposed
    assert json.loads(mcp_server.execute_calculation("target_mcp"))["security_block"]
    mcp_server.confirm_scenario("target_mcp", True)
    mcp_server.inspect_and_validate_parameters("target_mcp", {"theoretical_power": 10})
    mcp_server.confirm_parameters("target_mcp", True)
    result = json.loads(mcp_server.execute_calculation("target_mcp"))["result"]
    assert result["final_outputs"]["steam_mass_flow"] == pytest.approx(14.4)
