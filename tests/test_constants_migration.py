"""迁移资料经 JSON 与公开 MCP 工作流执行，不依赖已删除的常量 Python 模块。"""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def catalog(filename):
    return json.loads((ROOT / "constants" / filename).read_text(encoding="utf-8"))


def scene(formula_id, table):
    return {"id": "fixture", "name": "迁移资料验收", "required_inputs": [
        {"name": "query", "unit": table["input_unit"], "description": "查询量"}],
        "data_tables": [deepcopy(table)], "steps": [{"step_id": "lookup", "formula_id": formula_id,
            "input_map": {"value": "query"}, "output_map": {"result": "answer"},
            "data_map": {"table": table["id"]}}]}


# 删除旧模块前执行旧关联式捕获的结果，不由迁移后的算法生成期望。
@pytest.mark.parametrize("alias,prop,temperature,expected", [
    ("HITEC", "density", 200, 1934.988), ("HITEC", "density", 350, 1818.8895),
    ("HITEC", "thermal_conductivity", 200, 0.37496399999999996),
    ("HITEC", "thermal_conductivity", 350, 0.31380862500000006),
    ("HITEC", "viscosity", 200, 8.11823033730758), ("HITEC", "viscosity", 350, 2.2807440680430715),
    ("HITEC", "specific_heat", 200, 1.42), ("HITEC", "specific_heat", 350, 1.42),
    ("SOLAR_SALT", "density", 200, 1962.8), ("SOLAR_SALT", "density", 350, 1867.4),
    ("SOLAR_SALT", "thermal_conductivity", 200, 0.481),
    ("SOLAR_SALT", "thermal_conductivity", 350, 0.5095000000000001),
    ("SOLAR_SALT", "viscosity", 200, 6.658799999999998), ("SOLAR_SALT", "viscosity", 350, 2.3364749999999956),
    ("SOLAR_SALT", "specific_heat", 200, 1.4774), ("SOLAR_SALT", "specific_heat", 350, 1.5032),
])
def test_all_migrated_salt_correlations_match_legacy_values(mcp_workflow, alias, prop, temperature, expected):
    profile = next(p for p in catalog("molten_salt.json")["profiles"] if p["alias"] == alias)
    fid = profile["formulas"][prop]
    table = next(t for t in profile["data_tables"] if t["id"] == fid.split(".", 1)[1])
    result = mcp_workflow(scene(fid, table), {"query": temperature})
    assert result["final_outputs"] == {"answer": pytest.approx(expected)}
    assert result["results"][0]["unit"] == table["output_unit"]


def test_new_salt_coefficients_and_names_only_require_json_changes(mcp_workflow):
    profile = catalog("molten_salt.json")["profiles"][0]
    table = deepcopy(profile["data_tables"][0])
    table.update(id="unfamiliar_material", terms=[{"coefficient": 2, "power": 1}], divisor=4)
    result = mcp_workflow(scene(profile["formulas"]["density"], table), {"query": 200})
    assert result["final_outputs"] == {"answer": 100}


@pytest.mark.parametrize("fid,table_id,value,expected", [
    ("sizing.sgs_sizing", "sgs_power_scale", 75.33, 80),
    ("sizing.heater_sizing", "heater_power_scale", 77.25, 80),
    ("sizing.transformer_sizing", "transformer_capacities", 80, 90),
    ("sizing.transformer_sizing", "transformer_capacities", 121, 120),
    ("sizing.salt_mass_roundup", "salt_mass_scale", 22.3, 30),
])
def test_discrete_equipment_sizing_uses_json_tables(mcp_workflow, fid, table_id, value, expected):
    table = next(t for t in catalog("equipment_catalog.json")["data_tables"] if t["id"] == table_id)
    assert mcp_workflow(scene(fid, table), {"query": value})["final_outputs"] == {"answer": expected}


@pytest.mark.parametrize("identifier,value,expected", [
    ("heater_unit_cost", 99, 40), ("heater_unit_cost", 100, 38), ("heater_unit_cost", 200, 35),
    ("thermal_storage_unit_cost", 9999, 1.2), ("thermal_storage_unit_cost", 10000, 1.1),
    ("thermal_storage_unit_cost", 20000, 1.0), ("sgs_unit_cost", 249, 35),
    ("sgs_unit_cost", 250, 32), ("sgs_unit_cost", 350, 30),
])
def test_all_legacy_cost_tables_execute_from_json(mcp_workflow, identifier, value, expected):
    table = next(t for t in catalog("equipment_catalog.json")["data_tables"] if t["id"] == identifier)
    result = mcp_workflow(scene("cost." + identifier, table), {"query": value})
    assert result["final_outputs"] == {"answer": expected}


def test_power_factor_and_standard_capacities_are_explicit_json_inputs(mcp_workflow):
    data = catalog("equipment_catalog.json")
    factor = next(p for p in data["parameters"] if p["name"] == "heat_pump_power_factor")
    table = next(t for t in data["data_tables"] if t["id"] == "transformer_capacities")
    pipeline = scene("sizing.transformer_sizing", table)
    pipeline["required_inputs"] = [
        {"name": "power", "unit": "MW", "description": "有功功率"},
        {"name": factor["name"], "description": factor["description"], "unit": factor["unit"],
         "kind": "constant", "default_value": factor["value"]},
    ]
    pipeline["steps"].insert(0, {"step_id": "capacity", "formula_id": "electrical.apparent_capacity",
        "input_map": {"power": "power", "power_factor": factor["name"]}, "output_map": {"capacity": "query"}})
    result = mcp_workflow(pipeline, {"power": 80})
    assert result["final_outputs"]["answer"] == 120
    # 同一算法更改 JSON 功率因数，无设备或场景专用代码。
    pipeline["required_inputs"][1]["default_value"] = 1
    assert mcp_workflow(pipeline, {"power": 80})["final_outputs"]["answer"] == 90


def test_correlations_survive_restart_with_saved_coefficients_and_confirmation(mcp_workflow):
    profile = catalog("molten_salt.json")["profiles"][0]
    table = profile["data_tables"][0]
    mcp_workflow(scene(profile["formulas"]["density"], table), {"query": 350})
    script = '''
import json
from server import mcp_server as mcp
def call(name, **kwargs):
    return json.loads(getattr(mcp, name)(**kwargs))
catalog = next(s for s in call("list_scenarios") if s["id"] == "migration_fixture_1")
assert catalog["definition"]["data_tables"][0]["terms"][0]["coefficient"] == 0.0003602
session = "migration_fixture_1"
assert call("execute_calculation", session_id=session)["security_block"]
call("confirm_scenario", session_id=session, confirmed=True)
call("inspect_and_validate_parameters", session_id=session)
call("confirm_parameters", session_id=session, confirmed=True)
value = call("execute_calculation", session_id=session)["result"]["final_outputs"]["answer"]
assert abs(value - 1818.8895) < 1e-8
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=os.environ.copy(),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("value,status", [(350, 200), (0, 400)])
def test_correlation_preview_does_not_replace_formal_result(mcp_workflow, value, status):
    from starlette.testclient import TestClient
    from server.web_app import app
    profile = catalog("molten_salt.json")["profiles"][0]
    table = next(t for t in profile["data_tables"] if t["id"] == "hitec_viscosity")
    mcp_workflow(scene(profile["formulas"]["viscosity"], table), {"query": 350})
    client = TestClient(app)
    before = client.get("/api/session/migration_fixture_1").json()
    response = client.post("/api/preview_calculation", json={"pipeline": before["pipeline"], "parameters": {"query": value}})
    assert response.status_code == status, response.text
    assert client.get("/api/session/migration_fixture_1").json() == before
