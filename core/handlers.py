"""经验算子的静态白名单；JSON 只能按名称引用，不能导入或执行代码。"""

from dataclasses import dataclass, field
from typing import Callable

from iapws import IAPWS95

from core.types import Pin, units_match
from core.data_tables import fixed_step, discrete, piecewise, correlation


@dataclass(frozen=True)
class Handler:
    function: Callable[..., dict[str, float]]
    inputs: dict[str, str]
    outputs: dict[str, str]
    data_inputs: dict[str, str] = field(default_factory=dict)


_handlers: dict[str, Handler] = {}


def register_handler(name: str, *, inputs: dict[str, str], outputs: dict[str, str]):
    def register(function):
        if name in _handlers:
            raise ValueError(f"处理函数 {name} 已存在")
        _handlers[name] = Handler(function, inputs, outputs)
        return function
    return register


def get_handler(name: str, inputs: list[Pin], outputs: list[Pin], data_inputs=None):
    if name not in _handlers:
        raise ValueError(f"未注册的处理函数：{name}")
    handler = _handlers[name]
    for pins, expected in ((inputs, handler.inputs), (outputs, handler.outputs)):
        actual = {pin.name: pin.unit for pin in pins}
        if set(actual) != set(expected) or any(unit != "*" and not units_match(actual[key], unit) for key, unit in expected.items()):
            raise ValueError(f"处理函数 {name} 的引脚名称或单位与 JSON 定义不一致")
    ports = data_inputs or []
    if len(ports) != len(handler.data_inputs) or {port["name"]: port["rule_type"] for port in ports} != handler.data_inputs:
        raise ValueError(f"处理函数 {name} 的数据端口与 JSON 定义不一致")
    if ports:
        port = ports[0]
        if not units_match(inputs[0].unit, port["input_unit"]) or not units_match(outputs[0].unit, port["output_unit"]):
            raise ValueError(f"处理函数 {name} 的数据端口单位与数值引脚不一致")
    return handler.function


_handlers["data.fixed_step"] = Handler(fixed_step, {"value": "*"}, {"result": "*"}, {"table": "fixed_step"})
_handlers["data.discrete"] = Handler(discrete, {"value": "*"}, {"result": "*"}, {"table": "discrete"})
_handlers["data.piecewise"] = Handler(piecewise, {"value": "*"}, {"result": "*"}, {"table": "piecewise"})
_handlers["data.correlation"] = Handler(correlation, {"value": "*"}, {"result": "*"}, {"table": "correlation"})


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
