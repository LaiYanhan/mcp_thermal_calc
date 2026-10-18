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
            "import runpy,sys,webbrowser; "
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

                async def call(name, **arguments):
                    result = await client.call_tool(name, arguments)
                    assert not result.is_error, result
                    return json.loads(next(item.text for item in result.content if item.type == "text"))

                scenarios = await call("list_scenarios")
                assert {"scenario_electric_heater_salt_steam", "scenario_industrial_heat_pump_steam"} <= {
                    scenario["id"] for scenario in scenarios
                }
                assert await call("list_formulas")
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
                assert switched["status"] == "SUCCESS"
                assert switched["stage"] == 2
                assert (await call("execute_calculation", session_id=session))["security_block"] is True
                assert (await call("confirm_parameters", session_id=session, confirmed=True))["status"] == "PARAMETERS_CONFIRMED"
                calculated = await call("execute_calculation", session_id=session)
                assert calculated["status"] == "CALCULATED"
                assert calculated["result"]["final_outputs"]["sgs_power"] > 0
                assert calculated["result"]["results"]

    asyncio.run(asyncio.wait_for(exercise(), timeout=60))
