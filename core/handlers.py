"""经验算子的静态白名单；JSON 只能按名称引用，不能导入或执行代码。"""

import math
from dataclasses import dataclass
from typing import Callable

from iapws import IAPWS95

from constants.equipment_catalog import snap_heater_power, snap_sgs_power, snap_transformer_capacity
from core.types import Pin, units_match


@dataclass(frozen=True)
class Handler:
    function: Callable[[dict[str, float]], dict[str, float]]
    inputs: dict[str, str]
    outputs: dict[str, str]


_handlers: dict[str, Handler] = {}


def register_handler(name: str, *, inputs: dict[str, str], outputs: dict[str, str]):
    def register(function):
        if name in _handlers:
            raise ValueError(f"处理函数 {name} 已存在")
        _handlers[name] = Handler(function, inputs, outputs)
        return function
    return register


def get_handler(name: str, inputs: list[Pin], outputs: list[Pin]):
    if name not in _handlers:
        raise ValueError(f"未注册的处理函数：{name}")
    handler = _handlers[name]
    for pins, expected in ((inputs, handler.inputs), (outputs, handler.outputs)):
        actual = {pin.name: pin.unit for pin in pins}
        if set(actual) != set(expected) or any(not units_match(actual[key], unit) for key, unit in expected.items()):
            raise ValueError(f"处理函数 {name} 的引脚名称或单位与 JSON 定义不一致")
    return handler.function


@register_handler("iapws95.steam_enthalpy", inputs={"steam_pressure": "MPa", "steam_temperature": "℃"}, outputs={"steam_enthalpy": "kJ/kg"})
def steam_enthalpy(inputs):
    pressure = inputs["steam_pressure"] * 10.0 / 10.0
    temperature = inputs["steam_temperature"]
    # 饱和点沿用干饱和蒸汽查表；不再拦截汽相边界以外的输入。
    if 0 < pressure < IAPWS95.Pc:
        try:
            saturation = IAPWS95(P=pressure, x=1.0)
        except NotImplementedError:
            # 饱和查表的定义域小于 P,T 状态方程；继续求实际请求的状态。
            saturation = None
        if saturation is not None and abs(temperature - (saturation.T - 273.15)) <= 0.01:
            return {"steam_enthalpy": float(saturation.h)}
    state = IAPWS95(P=pressure, T=temperature + 273.15)
    return {"steam_enthalpy": float(state.h)}


@register_handler("iapws95.water_enthalpy", inputs={"feedwater_pressure": "MPa", "feedwater_temperature": "℃"}, outputs={"feedwater_enthalpy": "kJ/kg"})
def water_enthalpy(inputs):
    pressure = inputs["feedwater_pressure"] * 10.0 / 10.0
    state = IAPWS95(P=pressure, T=inputs["feedwater_temperature"] + 273.15)
    return {"feedwater_enthalpy": float(state.h)}


@register_handler("sizing.sgs_power", inputs={"sgs_power": "MW"}, outputs={"sgs_sizing_mw": "MW"})
def sgs_power(inputs):
    return {"sgs_sizing_mw": snap_sgs_power(inputs["sgs_power"])}


@register_handler("sizing.heater_power", inputs={"electric_heater_power": "MW"}, outputs={"heater_sizing_mw": "MW"})
def heater_power(inputs):
    return {"heater_sizing_mw": snap_heater_power(inputs["electric_heater_power"])}


@register_handler("sizing.transformer_capacity", inputs={"heater_sizing_mw": "MW"}, outputs={"transformer_capacity_mva": "MVA"})
def transformer_capacity(inputs):
    return {"transformer_capacity_mva": snap_transformer_capacity(inputs["heater_sizing_mw"], power_factor=1.0)}


@register_handler("sizing.salt_mass_roundup", inputs={"salt_mass": "t"}, outputs={"salt_mass_tons": "t"})
def salt_mass_roundup(inputs):
    return {"salt_mass_tons": math.ceil(inputs["salt_mass"] / 10.0) * 10.0}
