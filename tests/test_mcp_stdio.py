"""Exercise the actual MCP subprocess, wire schemas and workflow guards."""

import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]


def test_stdio_workflow(tmp_path):
    async def exercise():
        # The test supplies fixture confirmations; never open a user's browser.
        launcher = (
            "import runpy,sys,webbrowser,socket; from pathlib import Path; "
            "sys.path.insert(0,str(Path(sys.argv[1]).parents[1])); "
            "import server.web_app as web; "
            "sock=socket.socket(); sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]; sock.close(); "
            "start=web.ensure_web_server_running; web.ensure_web_server_running=lambda: start(port=port); "
            "webbrowser.open=lambda *a,**k: False; "
            "runpy.run_path(sys.argv[1],run_name='__main__')"
        )
        server = StdioServerParameters(
            command=sys.executable,
            args=["-c", launcher, str(ROOT / "server/mcp_server.py")],
            cwd=str(tmp_path),
            env={**os.environ, "THERMAL_CALC_DATA_DIR": str(tmp_path),
                 "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=30) as client:
                initialized = await client.initialize()
                assert initialized.server_info.name == "thermal-calc-sizing-engine"
                catalog = await client.list_tools()
                names = {tool.name for tool in catalog.tools}
                assert {"list_scenarios", "list_formulas", "match_or_propose_scenario",
                        "confirm_scenario", "inspect_and_validate_parameters",
                        "confirm_parameters", "execute_calculation", "solve_atomic_formula",
                        "register_new_formula", "register_new_pipeline",
                        "open_pipeline_editor"} <= names
                formula_schema = next(tool.input_schema for tool in catalog.tools if tool.name == "register_new_formula")
                assert "formula_definition" in formula_schema["properties"]
                assert "formula_code" not in formula_schema["properties"]

                async def call(name, **arguments):
                    result = await client.call_tool(name, arguments)
                    assert not result.is_error, result
                    return json.loads(next(item.text for item in result.content if item.type == "text"))

                scenarios = await call("list_scenarios")
                assert {"scenario_electric_heater_salt_steam", "scenario_industrial_heat_pump_steam"} <= {
                    scenario["id"] for scenario in scenarios
                }
                assert await call("list_formulas")
                registered = await call("register_new_formula", formula_definition={
                    "id": "test.stdio", "name": "恒等映射", "category": "thermal", "formula_type": "algebraic",
                    "expression": "y = x", "inputs": [{"name": "x", "unit": "MW", "description": "输入"}],
                    "outputs": [{"name": "y", "unit": "MW", "description": "输出"}],
                }, filename="恒等映射_stdio.json", human_approved=True)
                assert registered["status"] == "SUCCESS"
                registered_pipeline = await call("register_new_pipeline", pipeline_definition={
                    "id": "test_stdio", "name": "结构化 JSON 场景", "required_inputs": [
                        {"name": "source", "unit": "MW", "description": "输入", "default_value": 3}],
                    "steps": [{"step_id": "identity", "formula_id": "test.stdio",
                               "input_map": {"x": "source"}, "output_map": {"y": "answer"}}],
                }, pipeline_filename="test_stdio.json", human_approved=True)
                assert registered_pipeline["status"] == "SUCCESS"
                session = "stdio-regression"
                blocked = await call("execute_calculation", session_id=session)
                assert blocked["security_block"] is True
                proposed = await call(
                    "match_or_propose_scenario", session_id=session,
                    user_requirements="Automated regression fixture with default inputs",
                    scenario_id="scenario_electric_heater_salt_steam",
                )
                assert proposed["status"] == "SCENARIO_PROPOSED"
                assert (await call("confirm_scenario", session_id=session, confirmed=True))["status"] == "SCENARIO_CONFIRMED"
                inspected = await call("inspect_and_validate_parameters", session_id=session)
                assert inspected["is_complete"] is True
                switched = await call("open_pipeline_editor", session_id=session, stage=2)
                assert switched["status"] == "SUCCESS", switched
                assert switched["stage"] == 2
                assert (await call("execute_calculation", session_id=session))["security_block"] is True
                assert (await call("confirm_parameters", session_id=session, confirmed=True))["status"] == "PARAMETERS_CONFIRMED"
                calculated = await call("execute_calculation", session_id=session)
                assert calculated["status"] == "CALCULATED"
                assert calculated["result"]["final_outputs"]["sgs_power"] > 0
                assert calculated["result"]["results"]

    asyncio.run(asyncio.wait_for(exercise(), timeout=60))
