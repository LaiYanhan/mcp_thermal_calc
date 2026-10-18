"""经验算子的静态白名单；JSON 只能按名称引用，不能导入或执行代码。"""

import math
from typing import Callable

from iapws import IAPWS95

from constants.equipment_catalog import snap_heater_power, snap_sgs_power, snap_transformer_capacity


_handlers: dict[str, Callable[[dict[str, float]], dict[str, float]]] = {}


def register_handler(name: str):
    def register(function):
        if name in _handlers:
            raise ValueError(f"处理函数 {name} 已存在")
        _handlers[name] = function
        return function
    return register


def get_handler(name: str):
    if name not in _handlers:
        raise ValueError(f"未注册的处理函数：{name}")
    return _handlers[name]


@register_handler("iapws95.steam_enthalpy")
def steam_enthalpy(inputs):
    pressure = inputs["steam_pressure"] * 10.0 / 10.0
    temperature = inputs["steam_temperature"]
    # 饱和点沿用干饱和蒸汽查表；不再拦截汽相边界以外的输入。
    if 0 < pressure < IAPWS95.Pc:
        saturation = IAPWS95(P=pressure, x=1.0)
        if abs(temperature - (saturation.T - 273.15)) <= 0.01:
            return {"steam_enthalpy": float(saturation.h)}
    state = IAPWS95(P=pressure, T=temperature + 273.15)
    return {"steam_enthalpy": float(state.h)}


@register_handler("iapws95.water_enthalpy")
def water_enthalpy(inputs):
    pressure = inputs["feedwater_pressure"] * 10.0 / 10.0
    state = IAPWS95(P=pressure, T=inputs["feedwater_temperature"] + 273.15)
    return {"feedwater_enthalpy": float(state.h)}


@register_handler("sizing.sgs_power")
def sgs_power(inputs):
    return {"sgs_sizing_mw": snap_sgs_power(inputs["sgs_power"])}


@register_handler("sizing.heater_power")
def heater_power(inputs):
    return {"heater_sizing_mw": snap_heater_power(inputs["electric_heater_power"])}


@register_handler("sizing.transformer_capacity")
def transformer_capacity(inputs):
    return {"transformer_capacity_mva": snap_transformer_capacity(inputs["heater_sizing_mw"], power_factor=1.0)}


@register_handler("sizing.salt_mass_roundup")
def salt_mass_roundup(inputs):
    return {"salt_mass_tons": math.ceil(inputs["salt_mass"] / 10.0) * 10.0}
