"""
Regression tests comparing pipeline outputs with engineering calculations.
"""

import pytest
import core.catalog
from core.pipeline import pipeline_registry
from core.formula import default_formula_registry


def test_valley_salt_steam_pipeline_engineering_alignment():
    """
    全流程端到端回归测试：严格依据物理与工程逻辑核算。
    
    工况输入：
      蒸汽压力 1.5 MPa, 温度 200 ℃, 流量 100 t/h
      给水压力 0.1 MPa, 温度 20 ℃
      供汽时长 8 h, 谷电时长 8 h, 运行天数 330 d
      电加热效率 0.985, SGS换热效率 0.99, 储热效率 0.99
      HITEC 熔盐: 高温 390 ℃, 低温 190 ℃, 比热 1.42 kJ/(kg·K), 冗余 1.10
    """
    pipeline = pipeline_registry.get("scenario_electric_heater_salt_steam")
    result = pipeline.execute({}, default_formula_registry)
    ctx = result.final_outputs

    # 1. 蒸汽与给水焓值对比
    assert abs(ctx["steam_enthalpy"] - 2796.0) < 0.5
    assert abs(ctx["feedwater_enthalpy"] - 84.0) < 0.5
    assert abs(ctx["enthalpy_diff"] - 2712.0) < 0.5

    # 2. 理论产汽功率与 SGS 实际换热功率对比
    # 理论产汽功率 = 100 * 2712 / 3600 = 75.33 MW
    assert abs(ctx["theoretical_power"] - 75.33) < 0.1
    # SGS实际换热功率 = 75.33 / 0.99 = 76.09 MW
    assert abs(ctx["sgs_power"] - 76.09) < 0.1

    # 3. 供汽期总吸热量（功率转能量）
    # 608.75 MWh (76.09 * 8)
    assert abs(ctx["steam_heat_supply"] - 608.75) < 1.0

    # 4. 储热容量对比
    # 614.90 MWh (608.75 / 0.99)
    assert abs(ctx["thermal_storage_capacity"] - 614.90) < 1.0

    # 5. 电加热器功率对比
    # 78.03 MW (614.90 / 8 / 0.985)
    assert abs(ctx["electric_heater_power"] - 78.03) < 0.2

    # 6. 熔盐量对比
    assert abs(ctx["salt_mass"] - 8574.0) < 10.0
    assert ctx["salt_mass_tons"] == 8580.0

    # 7. 选型结果对比
    # 熔盐采购整定 8580 t
    assert result.final_outputs["salt_mass_tons"] == 8580.0

    # 8. 年用电量与供汽量
    # 年用电量约 20600 万kWh (78.03 * 8 * 330 / 10)
    assert abs(ctx["annual_power_wan_kwh"] - 20600.0) < 100.0
    # 年供汽量 26.4 万t (100 * 8 * 330 / 10000)
    assert abs(ctx["annual_steam_wan_tons"] - 26.4) < 0.01
