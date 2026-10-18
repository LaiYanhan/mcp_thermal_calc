"""JSON 重构在引擎、MCP 和会话 API 边界的回归。"""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.formula import FormulaRegistry
from core.pipeline import pipeline_registry


def test_pipeline_accepts_finite_inputs_outside_display_ranges():
    pipeline = pipeline_registry.get("scenario_electric_heater_salt_steam")
    result = pipeline.execute({"steam_mass_flow": -100, "salt_hot_temperature": 600})
    assert result.final_outputs["theoretical_power"] == pytest.approx(-75.332706178838, abs=0.01)
    assert result.final_outputs["salt_mass"] < 0
    assert pipeline.inspect_inputs({"salt_hot_temperature": 100})["is_complete"]


def test_json_formula_discovery_supports_forward_and_reverse_solving(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "功率_power.json").write_text(json.dumps({
        "id": "test.power", "name": "功率", "category": "thermal", "formula_type": "algebraic",
        "expression": "power = mass * enthalpy / 3600",
        "inputs": [{"name": "mass", "unit": "t/h", "description": "流量"},
                   {"name": "enthalpy", "unit": "kJ/kg", "description": "焓差"}],
        "outputs": [{"name": "power", "unit": "MW", "description": "功率"}],
    }), encoding="utf-8")
    registry = FormulaRegistry()
    registry.load_directory(nested)
    formula = registry.get("test.power")
    assert formula.execute({"mass": 100, "enthalpy": 2712}) == {"power": pytest.approx(75.33333333333333)}
    assert formula.solve({"power": 75.33333333333333, "enthalpy": 2712}, "mass") == pytest.approx(100)


@pytest.mark.parametrize("identifier", ["scenario_electric_heater_salt_steam", "scenario_industrial_heat_pump_steam"])
def test_every_json_pipeline_output_matches_pre_refactor_baseline(identifier):
    # 迁移前 fedcccb 的默认工况输出，由旧引擎捕获；不是由新公式重算的期望值。
    baseline = json.loads((Path(__file__).parent / "fixtures" / "baseline_outputs.json").read_text(encoding="utf-8"))
    assert pipeline_registry.get(identifier).execute({}).final_outputs == baseline[identifier]


def test_mcp_registers_structured_json_formula_without_granting_calculation_permission():
    from server import mcp_server
    definition = {
        "id": "test.double", "name": "输入翻倍", "category": "thermal", "formula_type": "algebraic",
        "expression": "y = 2 * x", "inputs": [{"name": "x", "unit": "MW", "description": "输入"}],
        "outputs": [{"name": "y", "unit": "MW", "description": "输出"}],
    }
    result = json.loads(mcp_server.register_new_formula(definition, "输入翻倍_double.json", True))
    assert result["status"] == "SUCCESS"
    assert json.loads(mcp_server.execute_calculation("json_registration"))["security_block"]


def test_json_registrations_survive_restart_and_still_require_confirmation():
    from server import mcp_server
    formula = {
        "id": "test.persisted", "name": "翻倍", "category": "thermal", "formula_type": "algebraic",
        "expression": "y = 2 * x", "inputs": [{"name": "x", "unit": "MW", "description": "输入"}],
        "outputs": [{"name": "y", "unit": "MW", "description": "输出"}],
    }
    assert json.loads(mcp_server.register_new_formula(formula, "翻倍_persisted.json", True))["status"] == "SUCCESS"
    pipeline = {
        "id": "test_persisted", "name": "持久化场景",
        "required_inputs": [{"name": "x", "unit": "MW", "description": "输入", "default_value": 3}],
        "steps": [{"step_id": "double", "formula_id": "test.persisted", "input_map": {"x": "x"}, "output_map": {"y": "answer"}}],
    }
    assert json.loads(mcp_server.register_new_pipeline(pipeline, "test_persisted.json", True))["status"] == "SUCCESS"
    script = """
import core.catalog
from core.state_machine import WorkflowManager, StateTransitionError
manager = WorkflowManager()
manager.propose_existing_scenario('fresh', 'test_persisted', 'restart fixture', {})
try:
    manager.execute_calculation('fresh')
except StateTransitionError:
    pass
else:
    raise AssertionError('Registration bypassed authorization')
manager.confirm_scenario('fresh', True)
manager.inspect_parameters('fresh')
manager.confirm_parameters('fresh', True)
assert manager.execute_calculation('fresh')['result']['final_outputs'] == {'answer': 6}
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                            env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("damage", ["extra", "type", "handler", "expression", "pin"])
def test_strict_json_registration_rejects_invalid_definitions_without_changing_catalog(damage):
    from server import mcp_server
    from core.formula import default_formula_registry
    definition = {
        "id": "test.invalid", "name": "测试", "category": "thermal", "formula_type": "algebraic",
        "expression": "y = 2 * x", "inputs": [{"name": "x", "unit": "MW", "description": "输入"}],
        "outputs": [{"name": "y", "unit": "MW", "description": "输出"}],
    }
    if damage == "extra":
        definition["python_code"] = "print('unexpected')"
    elif damage == "type":
        definition["inputs"][0]["default_value"] = True
    elif damage == "handler":
        definition.update(formula_type="empirical", handler="os.system", expression=None, is_bidirectional=False)
    elif damage == "expression":
        definition["expression"] = "y = __import__('os').system('bad')"
    else:
        definition["inputs"][0]["name"] = "not_x"
    before = mcp_server.list_formulas()
    assert "error" in json.loads(mcp_server.register_new_formula(definition, "测试_invalid.json", True))
    assert mcp_server.list_formulas() == before
    with pytest.raises(KeyError):
        default_formula_registry.get("test.invalid")


def test_json_resolution_never_executes_python_files(tmp_path):
    path = tmp_path / "untrusted.py"
    marker = tmp_path / "executed"
    path.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        pipeline_registry.resolve(str(path))
    assert not marker.exists()


@pytest.mark.parametrize("damage", ["input", "output", "unit"])
def test_empirical_json_must_match_handler_pin_contract(damage):
    definition = {
        "id": "test.handler_contract", "name": "规格整定", "category": "sizing", "formula_type": "empirical",
        "handler": "sizing.sgs_power",
        "inputs": [{"name": "sgs_power", "unit": "MW", "description": "需求功率"}],
        "outputs": [{"name": "sgs_sizing_mw", "unit": "MW", "description": "选型规格"}],
    }
    if damage == "unit":
        definition["inputs"][0]["unit"] = "kW"
    else:
        definition["inputs" if damage == "input" else "outputs"][0]["name"] = "wrong_pin"
    with pytest.raises(ValueError, match="处理函数"):
        FormulaRegistry().save_definition(definition)


def test_external_json_pipeline_can_be_resolved_by_id_after_file_selection(tmp_path):
    from core.pipeline import PipelineRegistry
    definition = pipeline_registry.get("scenario_electric_heater_salt_steam").to_dict()
    definition["id"] = "external_json_scene"
    path = tmp_path / "external.json"
    path.write_text(json.dumps(definition), encoding="utf-8")
    registry = PipelineRegistry()
    selected = registry.resolve(str(path))
    assert registry.get(selected.id).execute({}).final_outputs == selected.execute({}).final_outputs


def test_low_pressure_steam_uses_pt_state_when_saturation_lookup_is_unavailable():
    from core.formula import default_formula_registry
    result = default_formula_registry.get("thermal.steam_enthalpy").execute({
        "steam_pressure": 0.0001, "steam_temperature": 200,
    })
    assert result["steam_enthalpy"] == pytest.approx(2880.0499937995432)
