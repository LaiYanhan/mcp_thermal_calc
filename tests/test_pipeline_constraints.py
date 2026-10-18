"""通用引擎按声明校验，不根据业务变量名推断规则。"""

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from core.formula import AlgebraicFormula, FormulaRegistry
from core.pipeline import Pipeline, pipeline_registry
from core.types import FormulaMetadata, FormulaType, Pin
from core.storage import record_path, write_json
from server.web_app import app


def sum_pipeline(names=("salt_hot_temperature", "salt_cold_temperature")):
    registry = FormulaRegistry()
    registry.register(AlgebraicFormula(FormulaMetadata(
        id="test.sum", name="两数相加", category="test", description="", notes="",
        formula_type=FormulaType.ALGEBRAIC,
        inputs=[Pin("a", "/", "数值甲"), Pin("b", "/", "数值乙")],
        outputs=[Pin("result", "/", "和")]), "result = a + b"))
    data = {"id": "sum_scene", "name": "加法场景", "required_inputs": [
        {"name": names[0], "unit": "/", "description": "数值甲", "default_value": 1},
        {"name": names[1], "unit": "/", "description": "数值乙", "default_value": 2}],
        "steps": [{"step_id": "sum", "formula_id": "test.sum", "input_map": {"a": names[0], "b": names[1]},
                   "output_map": {"result": "answer"}}]}
    return data, registry


def test_business_input_names_do_not_enable_implicit_validation():
    data, registry = sum_pipeline()
    assert Pipeline.from_dict(data).execute({}, registry).final_outputs == {"answer": 3}


def test_declared_constraints_work_for_arbitrary_names_and_roundtrip():
    data, registry = sum_pipeline(("upper", "lower"))
    data["input_constraints"] = [{"variable": "upper", "greater_than": "lower", "message": "上限必须大于下限"},
                                 {"variable": "upper", "min_value": 0, "max_value": 10}]
    pipeline = Pipeline.from_dict(Pipeline.from_dict(data).to_dict())
    with pytest.raises(ValueError, match="上限必须大于下限"):
        pipeline.inspect_inputs({}, registry)
    assert pipeline.execute({"upper": 3}, registry).final_outputs == {"answer": 5}
    with pytest.raises(ValueError):
        pipeline.inspect_inputs({"upper": 11}, registry)


@pytest.mark.parametrize("identifier", ["scenario_electric_heater_salt_steam", "scenario_industrial_heat_pump_steam"])
def test_real_pipelines_declare_temperature_order(identifier):
    pipeline = Pipeline.from_dict(pipeline_registry.get(identifier).to_dict())
    with pytest.raises(ValueError, match="高温熔盐温度必须大于低温熔盐温度"):
        pipeline.inspect_inputs({"salt_hot_temperature": 190, "salt_cold_temperature": 190})
    assert pipeline.execute({}).results


def test_legacy_salt_definition_keeps_validation_without_mutating_source():
    data = pipeline_registry.get("scenario_electric_heater_salt_steam").to_dict()
    data.pop("input_constraints", None)
    data["salt_profile"] = "HITEC"
    pipeline = Pipeline.from_dict(data)
    assert "salt_profile" not in pipeline.to_dict()
    assert pipeline.to_dict()["input_constraints"]
    assert "input_constraints" not in data
    with pytest.raises(ValueError):
        pipeline.inspect_inputs({"salt_hot_temperature": 600})


def test_renamed_inputs_keep_declared_rules_and_results():
    original = pipeline_registry.get("scenario_electric_heater_salt_steam")
    data = original.to_dict()
    renamed = {pin["name"]: f"parameter_{index}" for index, pin in enumerate(data["required_inputs"])}
    for pin in data["required_inputs"]:
        pin["name"] = renamed[pin["name"]]
    for step in data["steps"]:
        step["input_map"] = {pin: renamed.get(source, source) for pin, source in step["input_map"].items()}
    for constraint in data["input_constraints"]:
        constraint["variable"] = renamed[constraint["variable"]]
        if constraint["greater_than"] is not None:
            constraint["greater_than"] = renamed[constraint["greater_than"]]
    pipeline = Pipeline.from_dict(data)
    assert pipeline.execute({}).final_outputs == original.execute({}).final_outputs
    with pytest.raises(ValueError):
        pipeline.inspect_inputs({renamed["salt_hot_temperature"]: 190})
    with pytest.raises(ValueError):
        pipeline.inspect_inputs({renamed["salt_hot_temperature"]: 600})


@pytest.mark.parametrize("damage", ["missing", "unit"])
def test_invalid_constraint_reference_is_rejected(damage):
    data, registry = sum_pipeline(("upper", "lower"))
    data["input_constraints"] = [{"variable": "upper", "greater_than": "lower"}]
    if damage == "missing":
        data["input_constraints"][0]["greater_than"] = "absent"
    else:
        data["required_inputs"][1]["unit"] = "MW"
    pipeline = Pipeline.from_dict(data)
    assert any(error["code"] == "constraint" for error in pipeline.validate(registry)["errors"])
    with pytest.raises(ValueError):
        pipeline.inspect_inputs({}, registry)


def test_missing_compared_input_is_reported_as_missing():
    data, registry = sum_pipeline(("upper", "lower"))
    data["required_inputs"][1].pop("default_value")
    data["input_constraints"] = [{"variable": "upper", "greater_than": "lower"}]
    result = Pipeline.from_dict(data).inspect_inputs({}, registry)
    assert result["is_complete"] is False
    assert result["missing_inputs"][0]["name"] == "lower"


@pytest.mark.parametrize("identifier", ["scenario_electric_heater_salt_steam", "scenario_industrial_heat_pump_steam"])
def test_web_save_confirm_and_calculate_preserves_constraints(identifier):
    client = TestClient(app)
    base = "/api/session/constraint_web"
    view = client.get(base + "?pipeline=" + identifier + "&reset=1").json()
    data = view["pipeline"]
    constraints = deepcopy(data["input_constraints"])
    assert constraints
    data["layout"] = {"step:step_1_steam_enthalpy": {"left": 123, "top": 234}}
    assert client.post(base + "/pipeline", json=data).status_code == 200
    assert client.post(base + "/confirm_scenario", json={"confirmed": True}).status_code == 200
    assert client.post(base + "/parameters", json={"parameters": {"salt_hot_temperature": 190}}).status_code == 400
    assert client.post(base + "/parameters", json={"parameters": {}}).status_code == 200
    assert client.post(base + "/confirm_parameters", json={"confirmed": True}).status_code == 200
    response = client.post(base + "/calculate")
    assert response.status_code == 200, response.text
    assert len(response.json()["result"]["results"]) == len(data["steps"])
    assert client.get(base).json()["pipeline"]["input_constraints"] == constraints


def test_old_session_constraints_survive_restart():
    data = pipeline_registry.get("scenario_electric_heater_salt_steam").to_dict()
    data.pop("input_constraints")
    data["salt_profile"] = "HITEC"
    write_json(record_path("sessions", "legacy_constraints"), {
        "session_id": "legacy_constraints", "pipeline_data": data,
        "scenario_id": data["id"], "provided_parameters": {"salt_hot_temperature": 600},
    })
    script = """
import pipelines
from core.state_machine import WorkflowManager
manager = WorkflowManager()
view = manager.get_session_view('legacy_constraints')
assert view['pipeline']['input_constraints']
assert 'salt_profile' not in view['pipeline']
manager.confirm_scenario('legacy_constraints', True)
try:
    manager.inspect_parameters('legacy_constraints')
except ValueError:
    print('LEGACY_CONSTRAINT_PRESERVED')
else:
    raise AssertionError('Legacy input constraints were lost')
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                            env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "LEGACY_CONSTRAINT_PRESERVED" in result.stdout


def test_restricted_python_template_accepts_constraint_declarations():
    from core.extensions import parse_definition
    source = '''
from core.pipeline import Pipeline, PipelineStep, pipeline_registry
from core.types import Pin, InputConstraint
pipeline = Pipeline(id="template", name="模板", category="test", description="", notes="",
    required_inputs=[Pin("upper", "/", "上限"), Pin("lower", "/", "下限")],
    steps=[PipelineStep(step_id="sum", formula_id="test.sum", input_map={"a": "upper", "b": "lower"}, output_map={"result": "answer"})],
    input_constraints=[InputConstraint(variable="upper", greater_than="lower")])
pipeline_registry.register(pipeline)
'''
    pipeline = parse_definition(source, "pipeline")
    _, registry = sum_pipeline()
    with pytest.raises(ValueError):
        pipeline.inspect_inputs({"upper": 1, "lower": 2}, registry)
    assert pipeline.execute({"upper": 3, "lower": 2}, registry).final_outputs == {"answer": 5}
