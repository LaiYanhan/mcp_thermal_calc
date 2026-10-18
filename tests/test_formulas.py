"""
Unit tests for atomic formulas and bidirectional SymPy solving.
"""

import pytest
import core.catalog
from core.formula import default_formula_registry


def test_iapws_water_steam_enthalpy():
    """测试水蒸气与给水比焓查表计算精度（对齐 Excel 计算表 D3/D4）"""
    steam_f = default_formula_registry.get("thermal.steam_enthalpy")
    res_steam = steam_f.execute({"steam_pressure": 1.5, "steam_temperature": 200.0})
    # Excel 值为 2795.98 kJ/kg
    assert abs(res_steam["steam_enthalpy"] - 2796.0) < 0.5

    water_f = default_formula_registry.get("thermal.water_enthalpy")
    res_water = water_f.execute({"feedwater_pressure": 0.1, "feedwater_temperature": 20.0})
    # Excel 值为 84.01 kJ/kg
    assert abs(res_water["feedwater_enthalpy"] - 84.0) < 0.5


def test_algebraic_bidirectional_solving():
    """测试代数公式的正向与逆向自动解析求解"""
    theo_f = default_formula_registry.get("thermal.theoretical_power")
    # 正向: 已知流量 100 t/h, 焓差 2712.0 kJ/kg, 求理论产汽功率
    fwd = theo_f.execute({"steam_mass_flow": 100.0, "enthalpy_diff": 2712.0})
    expected_mw = 100.0 * 2712.0 / 3600.0
    assert abs(fwd["theoretical_power"] - expected_mw) < 1e-4

    # 逆向 1: 已知目标功率 75.3333 MW, 焓差 2712.0 kJ/kg, 反求蒸汽流量
    rev_flow = theo_f.solve({"theoretical_power": expected_mw, "enthalpy_diff": 2712.0}, "steam_mass_flow")
    assert abs(rev_flow - 100.0) < 1e-4

    # 逆向 2: 已知理论功率，经换热效率求SGS功率
    sgs_f = default_formula_registry.get("thermal.sgs_power")
    sgs_res = sgs_f.execute({"theoretical_power": expected_mw, "heat_exchanger_efficiency": 0.99})
    assert abs(sgs_res["sgs_power"] - expected_mw / 0.99) < 1e-4

    # 逆向 3: 已知SGS功率与效率，反求理论产汽功率
    rev_theo = sgs_f.solve({"sgs_power": sgs_res["sgs_power"], "heat_exchanger_efficiency": 0.99}, "theoretical_power")
    assert abs(rev_theo - expected_mw) < 1e-4

def test_discrete_equipment_sizing():
    """测试离散选型原子公式"""
    sgs_sizing_f = default_formula_registry.get("sizing.sgs_sizing")
    res = sgs_sizing_f.execute({"sgs_power": 75.33})
    assert res["sgs_sizing_mw"] == 80.0

    heater_sizing_f = default_formula_registry.get("sizing.heater_sizing")
    res_heater = heater_sizing_f.execute({"electric_heater_power": 77.25})
    assert res_heater["heater_sizing_mw"] == 80.0

    tf_sizing_f = default_formula_registry.get("sizing.transformer_sizing")
    res_tf = tf_sizing_f.execute({"heater_sizing_mw": 80.0})
    # 80 MW 向上匹配最接近的标准容量档位为 90 MVA
    assert res_tf["transformer_capacity_mva"] == 90.0
