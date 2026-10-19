"""测试使用独立数据目录，避免修改工程师保存的会话和算子。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
import pytest

# 注册内置目录时也隔离持久化加载，避免本机自定义算子影响回归基准。
_cache = Path(__file__).resolve().parents[1] / ".pytest_cache"
_cache.mkdir(exist_ok=True)
with TemporaryDirectory(prefix="thermal-bootstrap-", dir=_cache) as _bootstrap:
    _previous = os.environ.get("THERMAL_CALC_DATA_DIR")
    os.environ["THERMAL_CALC_DATA_DIR"] = _bootstrap
    try:
        import core.catalog
    finally:
        if _previous is None:
            os.environ.pop("THERMAL_CALC_DATA_DIR", None)
        else:
            os.environ["THERMAL_CALC_DATA_DIR"] = _previous
from core.formula import default_formula_registry
from core.pipeline import pipeline_registry
from core.state_machine import workflow_manager


@pytest.fixture
def tmp_path():
    cache = Path(__file__).resolve().parents[1] / ".pytest_cache"
    cache.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="thermal-tests-", dir=cache) as directory:
        yield Path(directory)


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("THERMAL_CALC_DATA_DIR", str(tmp_path))
    assets = tmp_path / "assets"
    for category in ("formulas", "pipelines"):
        source = Path(__file__).resolve().parents[1] / category
        for path in source.rglob("*.json"):
            target = assets / category / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    monkeypatch.setenv("THERMAL_CALC_ASSET_DIR", str(assets))
    original_formulas = deepcopy(default_formula_registry._formulas)
    original_pipelines = deepcopy(pipeline_registry._pipelines)
    original_sessions = deepcopy(workflow_manager._sessions)
    workflow_manager._sessions.clear()
    yield
    default_formula_registry._formulas = original_formulas
    pipeline_registry._pipelines = original_pipelines
    workflow_manager._sessions = original_sessions


@pytest.fixture
def mcp_workflow(monkeypatch):
    """通过公开 MCP 注册与确认执行迁移样例，只阻止打开浏览器。"""
    import json
    from server import mcp_server as mcp
    monkeypatch.setattr(mcp, "editor_link", lambda *args: "http://localhost/fixture")
    monkeypatch.setattr(mcp.webbrowser, "open", lambda *args: False)
    sequence = 0

    def run(pipeline, parameters):
        nonlocal sequence
        sequence += 1
        pipeline = deepcopy(pipeline)
        pipeline["id"] = f"migration_fixture_{sequence}"
        session = pipeline["id"]

        def call(name, **kwargs):
            return json.loads(getattr(mcp, name)(**kwargs))

        saved = call("register_new_pipeline", pipeline_definition=pipeline,
                     pipeline_filename=session + ".json", human_approved=True)
        assert saved.get("status") == "SUCCESS", saved
        proposed = call("match_or_propose_scenario", session_id=session, user_requirements="自动化迁移验收样例",
                        scenario_id=session, initial_inputs=parameters)
        assert proposed.get("status") == "SCENARIO_PROPOSED", proposed
        assert call("execute_calculation", session_id=session)["security_block"]
        call("confirm_scenario", session_id=session, confirmed=True)
        inspection = call("inspect_and_validate_parameters", session_id=session)
        assert inspection.get("is_complete"), inspection
        call("confirm_parameters", session_id=session, confirmed=True)
        result = call("execute_calculation", session_id=session)
        assert result.get("status") == "CALCULATED", result
        return result["result"]
    return run
