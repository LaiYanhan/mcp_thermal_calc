"""
设备选型档位与阶梯造价常量规则 (Equipment Catalog & Stepped Cost Matrix)
"""

import math
from typing import List


# ===================== 设备离散规格档位表 =====================

# 变压器国家标准容量序列 (MVA)
# [6.3, 8, 10, 12.5, 16, 20, 25, 31.5, 40, 50, 63, 90, 120] MVA
STANDARD_TRANSFORMER_CAPACITIES_MVA: List[float] = [
    6.3, 8.0, 10.0, 12.5, 16.0, 20.0, 25.0, 31.5, 40.0, 50.0, 63.0, 90.0, 120.0
]


def snap_transformer_capacity(power_mw: float, power_factor: float = 1.0) -> float:
    """
    根据用电功率向上选型匹配标准变压器容量 (MVA)
    电加热器方案功率因数按 1.0，热泵方案功率因数按 0.85
    """
    required_mva = power_mw / power_factor
    for cap in STANDARD_TRANSFORMER_CAPACITIES_MVA:
        if required_mva <= cap:
            return cap
    # 若超出单台最大容量 120 MVA，支持多台组合（向上取整至 120 的倍数或最大档位）
    return math.ceil(required_mva / 120.0) * 120.0


def snap_sgs_power(power_mw: float) -> float:
    """
    SGS换热功率向上整定至 5 的倍数 (MW)
    """
    return math.ceil(power_mw / 5.0) * 5.0


def snap_heater_power(power_mw: float) -> float:
    """
    电加热器功率向上整定至 5 的倍数 (MW)
    """
    return math.ceil(power_mw / 5.0) * 5.0


# ===================== 阶梯造价单价规则 (万元/单位) =====================

def calc_heater_unit_cost(heater_power_mw: float) -> float:
    """
    电加热器单位造价 (万元/MW)
    <100MW: 40万/MW; <200MW: 38万/MW; >=200MW: 35万/MW
    """
    if heater_power_mw < 100.0:
        return 40.0
    elif heater_power_mw < 200.0:
        return 38.0
    else:
        return 35.0


def calc_thermal_storage_unit_cost(salt_mass_t: float) -> float:
    """
    储热系统单位造价 (万元/t 熔盐)
    <10000t: 1.2万/t; <20000t: 1.1万/t; >=20000t: 1.0万/t
    """
    if salt_mass_t < 10000.0:
        return 1.2
    elif salt_mass_t < 20000.0:
        return 1.1
    else:
        return 1.0


def calc_sgs_unit_cost(sgs_power_mw: float) -> float:
    """
    SGS换热系统单位造价 (万元/MW)
    <250MW: 35万/MW; <350MW: 32万/MW; >=350MW: 30万/MW
    """
    if sgs_power_mw < 250.0:
        return 35.0
    elif sgs_power_mw < 350.0:
        return 32.0
    else:
        return 30.0


# 电气系统单位造价基准 (万元/MVA)
ELECTRICAL_SYSTEM_UNIT_COST_PER_MVA: float = 12.0
