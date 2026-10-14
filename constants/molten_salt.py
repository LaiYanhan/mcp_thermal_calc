"""
熔盐热物理特性基准与状态方程 (Molten Salt Thermophysical Properties)
数据对齐《研究资料/参考excel/输入输出2.xlsx》工作表【熔盐参数】。
包含 HITEC 熔盐与太阳盐（Solar Salt）的工作温区、密度、导热系数、粘度与比热容计算方程。
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class MoltenSaltProfile:
    """熔盐特性配置"""
    name: str  # 熔盐中文名
    alias: str  # 英文标识
    composition: str  # 组分说明
    min_temp_c: float  # 工作温度下限 (℃)
    max_temp_c: float  # 工作温度上限 (℃)
    default_hot_temp: float  # 典型高温 (℃)
    default_cold_temp: float  # 典型低温 (℃)

    def calc_density(self, temp_c: float) -> float:
        """密度 (kg/m3)"""
        raise NotImplementedError

    def calc_thermal_conductivity(self, temp_c: float) -> float:
        """导热系数 (kcal/(m·h·℃))"""
        raise NotImplementedError

    def calc_viscosity(self, temp_c: float) -> float:
        """粘度 ((kg·s)/m2)"""
        raise NotImplementedError

    def calc_specific_heat(self, temp_c: float) -> float:
        """比热容 (kJ/(kg·℃))"""
        raise NotImplementedError


class HitecSalt(MoltenSaltProfile):
    """
    HITEC 熔盐 (53% KNO3 + 40% NaNO2 + 7% NaNO3 三元共晶盐)
    适用中温温区 190~400℃。
    """
    def __init__(self):
        super().__init__(
            name="HITEC熔盐",
            alias="HITEC",
            composition="53% KNO3 + 40% NaNO2 + 7% NaNO3",
            min_temp_c=190.0,
            max_temp_c=400.0,
            default_hot_temp=390.0,
            default_cold_temp=190.0,
        )

    def calc_density(self, temp_c: float) -> float:
        # 参考公式：0.0003602*T^2 - 0.9721*T + 2115
        return 0.0003602 * (temp_c ** 2) - 0.9721 * temp_c + 2115.0

    def calc_thermal_conductivity(self, temp_c: float) -> float:
        # 参考公式：3.283*10^-9*T^3 - 4.02*10^-6*T^2 + 0.00104*T + 0.3015
        return (
            3.283e-9 * (temp_c ** 3)
            - 4.02e-6 * (temp_c ** 2)
            + 0.00104 * temp_c
            + 0.3015
        )

    def calc_viscosity(self, temp_c: float) -> float:
        # 参考公式：5.771*10^7*T^-3.001 + 0.9426
        return 5.771e7 * (temp_c ** -3.001) + 0.9426

    def calc_specific_heat(self, temp_c: float) -> float:
        # 参考选型表基准定值：1.42 kJ/(kg·℃)
        return 1.42


class SolarSalt(MoltenSaltProfile):
    """
    太阳盐 (60% NaNO3 + 40% KNO3 二元混合盐)
    适用高温温区 290~565℃。
    """
    def __init__(self):
        super().__init__(
            name="太阳盐",
            alias="SOLAR_SALT",
            composition="60% NaNO3 + 40% KNO3",
            min_temp_c=290.0,
            max_temp_c=565.0,
            default_hot_temp=565.0,
            default_cold_temp=290.0,
        )

    def calc_density(self, temp_c: float) -> float:
        # 参考公式：2090 - 0.636*T
        return 2090.0 - 0.636 * temp_c

    def calc_thermal_conductivity(self, temp_c: float) -> float:
        # 参考公式：0.443 + 1.9*T/10^4
        return 0.443 + 1.9e-4 * temp_c

    def calc_viscosity(self, temp_c: float) -> float:
        # 参考公式：22.714 - 0.12*T + 2.281*T^2/10^4 - 1.474*T^3/10^7
        return (
            22.714
            - 0.12 * temp_c
            + 2.281e-4 * (temp_c ** 2)
            - 1.474e-7 * (temp_c ** 3)
        )

    def calc_specific_heat(self, temp_c: float) -> float:
        # 参考公式：(1443 + 0.172*T) / 1000
        return (1443.0 + 0.172 * temp_c) / 1000.0


SALT_PROFILES: Dict[str, MoltenSaltProfile] = {
    "HITEC": HitecSalt(),
    "HITEC熔盐": HitecSalt(),
    "SOLAR_SALT": SolarSalt(),
    "太阳盐": SolarSalt(),
}


def get_salt_profile(name_or_alias: str) -> MoltenSaltProfile:
    """根据名称获取熔盐物性配置，默认返回 HITEC 熔盐"""
    normalized = name_or_alias.strip()
    if normalized in SALT_PROFILES:
        return SALT_PROFILES[normalized]
    return SALT_PROFILES["HITEC"]
