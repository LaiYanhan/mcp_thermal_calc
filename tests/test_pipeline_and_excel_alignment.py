"""
Regression tests comparing pipeline outputs directly with 《输入输出2.xlsx》 calculations.
"""

import pytest
import formulas
import pipelines
from core.pipeline import pipeline_registry
from core.formula import default_formula_registry


def test_valley_salt_steam_pipeline_excel_alignment():
    """
    全流程端到端回归测试：严格对比参考 Excel 《输入输出2.xlsx》工作表【计算】与【选型】。
    
    工况输入：
      蒸汽压力 1.5 MPa, 温度 200 ℃, 流量 100 t/h
      给水压力 0.1 MPa, 温度 20 ℃
      供汽时长 8 h, 谷电时长 8 h, 运行天数 330 d
      电加热效率 0.985, SGS换热效率 0.99, 储热效率 0.99
      HITEC 熔盐: 高温 390 ℃, 低温 190 ℃, 比热 1.42 kJ/(kg·K), 冗余 1.10
    """
    pipeline = pipeline_registry.get("scenario_valley_salt_steam")
    result = pipeline.execute({}, default_formula_registry)
    ctx = result.final_outputs

    # 1. 蒸汽与给水焓值对比
    # Excel D3: 2795.98 kJ/kg
    assert abs(ctx["steam_enthalpy"] - 2796.0) < 0.5
    # Excel D4: 84.01 kJ/kg
    assert abs(ctx["feedwater_enthalpy"] - 84.0) < 0.5
    # 焓差
    assert abs(ctx["enthalpy_diff"] - 2712.0) < 0.5

    # 2. SGS 功率对比
    # Excel D5: 75.33 MW (100 * (2795.98 - 84.01) / 3600)
    assert abs(ctx["sgs_power"] - 75.33) < 0.1

    # 3. 制热量 / 供汽吸热量对比
    # Excel D6: 608.75 MWh (75.33 * 8 / 0.99)
    assert abs(ctx["steam_heat_supply"] - 608.75) < 1.0

    # 4. 电加热器功率对比
    # Excel D7: 77.25 MW (608.75 / 8 / 0.985)
    assert abs(ctx["electric_heater_power"] - 77.25) < 0.2

    # 5. 储热容量对比
    # Excel D8: 614.90 MWh (608.75 / 0.99)
    assert abs(ctx["thermal_storage_capacity"] - 614.90) < 1.0

    # 6. 熔盐量对比
    # Excel 选型!D9: ROUNDUP(614.90 * 3600 / 1.42 / (390 - 190) * 1.1, -1) = 8580 t
    assert abs(ctx["salt_mass"] - 8578.8) < 5.0
    assert ctx["salt_mass_tons"] == 8580.0

    # 7. 选型结果对比
    # 电加热器 80 MW, SGS 80 MW, 变压器 90 MVA
    assert result.sizing_summary["heater_sizing_mw"] == 80.0
    assert result.sizing_summary["sgs_sizing_mw"] == 80.0
    assert result.sizing_summary["transformer_capacity_mva"] == 90.0
    assert result.sizing_summary["salt_mass_tons"] == 8580.0

    # 8. 年用电量与供汽量
    # Excel 计算!D9: 年用电量 20394 万kWh (77.25 * 8 * 330 / 10)
    assert abs(ctx["annual_power_wan_kwh"] - 20394.0) < 50.0
    # Excel 计算!D10: 年供汽量 26.4 万t (100 * 8 * 330 / 10000)
    assert abs(ctx["annual_steam_wan_tons"] - 26.4) < 0.01

    print("All numbers match Excel within high engineering precision!")
