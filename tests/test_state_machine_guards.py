"""
Tests for state machine workflow and human-in-the-loop interruption guards.
"""

import pytest
import formulas
import pipelines
from core.state_machine import WorkflowManager, WorkflowState, StateTransitionError


def test_state_machine_hard_guards():
    """验证安全守卫：未经人工确认，坚决拒绝执行计算"""
    sm = WorkflowManager()
    session_id = "test_guard_001"

    # 1. 初始状态下直接请求计算 -> 必须被拦截抛出异常
    with pytest.raises(StateTransitionError) as exc_info:
        sm.execute_calculation(session_id)
    assert "未经人工确认授权" in str(exc_info.value)

    # 2. 提议场景，状态变为 SCENARIO_PROPOSED
    sm.propose_existing_scenario(
        session_id=session_id,
        scenario_id="scenario_valley_salt_steam",
        user_requirements="需要供汽100t/h",
        initial_inputs={"steam_mass_flow": 100.0},
    )
    # 场景未确认前，请求计算 -> 依然必须被拦截
    with pytest.raises(StateTransitionError):
        sm.execute_calculation(session_id)

    # 3. 人工确认场景
    sm.confirm_scenario(session_id=session_id, confirmed=True)
    # 状态变为 SCENARIO_CONFIRMED，但参数未检查、未确认前 -> 依然被拦截
    with pytest.raises(StateTransitionError):
        sm.execute_calculation(session_id)

    # 4. 检查参数，状态变为 PARAMETERS_INSPECTED
    insp = sm.inspect_parameters(session_id=session_id)
    assert insp["is_complete"] is True
    # 参数未获人工最终确认前 -> 依然被拦截
    with pytest.raises(StateTransitionError):
        sm.execute_calculation(session_id)

    # 5. 人工确认参数
    sm.confirm_parameters(session_id=session_id, confirmed=True)
    # 此时状态为 PARAMETERS_CONFIRMED，正式授权计算

    # 6. 执行计算 -> 顺利通过，状态流转为 CALCULATED
    calc_res = sm.execute_calculation(session_id=session_id)
    assert calc_res["status"] == WorkflowState.CALCULATED.value
    assert "result" in calc_res
    assert calc_res["result"]["final_outputs"]["salt_mass_tons"] == 8580.0


def test_state_machine_rejection_flow():
    """验证人工打回修改流程（图2修改态）"""
    sm = WorkflowManager()
    session_id = "test_reject_001"

    sm.propose_existing_scenario(
        session_id=session_id,
        scenario_id="scenario_valley_salt_steam",
        user_requirements="需要供汽",
        initial_inputs={},
    )
    # 人类打回场景
    rej_res = sm.confirm_scenario(session_id=session_id, confirmed=False, feedback="参数不对，不是这个场景")
    assert rej_res["status"] == WorkflowState.MODIFICATION_REQUESTED.value
    assert rej_res["action_required"] == "AI_MODIFY_SCENARIO"
