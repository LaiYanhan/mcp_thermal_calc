"""
设备选型档位与阶梯造价常量规则 (Equipment Catalog & Stepped Cost Matrix)
数据对齐《研究资料/参考excel/输入输出2.xlsx》工作表【设备型号】、【选型】、【造价】。
"""

import math
from typing import List, Tuple


# ===================== 设备离散规格档位表 =====================

# 变压器国家标准容量序列 (MVA)
# 参考《设备型号》第3列及《选型!D11》IFS条件：
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
    参考《设备型号》备注：“SGS功率根据实际计算值向上取整至5的倍数”
    """
    return math.ceil(power_mw / 5.0) * 5.0


def snap_heater_power(power_mw: float) -> float:
    """
    电加热器功率向上整定 (MW)
    参考《设备型号》备注：“电加热器功率范围5-30MW，每5MW为1个型号”，大容量工程按 5MW 步长向上整定
    在《选型!D2》中采用 ROUNDUP(计算!D7, -1) 或 5MW 步长整定
    """
    return math.ceil(power_mw / 5.0) * 5.0


# ===================== 阶梯造价单价规则 (万元/单位) =====================

def calc_heater_unit_cost(heater_power_mw: float) -> float:
    """
    电加热器单位造价 (万元/MW)
    参考《造价》第3行公式：
    IF(选型!D2 < 100, 40, IF(选型!D2 < 200, 38, 35))
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
    参考《造价》第4行公式：
    根据盐量确定，1万吨以下取 1.2，2万吨以下取 1.1，2万吨以上取 1.0
    IF(选型!D9 < 10000, 1.2, IF(选型!D9 < 20000, 1.1, 1.0))
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
    参考《造价》第5行公式：
    IF(选型!D10 < 250, 35, IF(选型!D10 < 350, 32, 30))
    """
    if sgs_power_mw < 250.0:
        return 35.0
    elif sgs_power_mw < 350.0:
        return 32.0
    else:
        return 30.0


# 电气系统单位造价基准 (万元/MVA 或 万元/MW)
# 参考《造价》第6行：12 万元/MW
ELECTRICAL_SYSTEM_UNIT_COST_PER_MVA: float = 12.0
