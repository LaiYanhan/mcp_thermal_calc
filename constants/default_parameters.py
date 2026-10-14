"""
默认工程基准参数表 (Default Engineering Baseline Parameters)
数据严格对齐《研究资料/参考excel/输入输出2.xlsx》工作表【输入】及工程常规基准。
当用户在场景对话中未明确给出特定数值时，系统自动调用本配置作为基准值并提示用户确认。
"""

from typing import Any, Dict


# 谷电熔盐储热供蒸汽基准工况默认参数字典
DEFAULT_VALLEY_SALT_STEAM_PARAMS: Dict[str, Dict[str, Any]] = {
    "steam_pressure": {
        "value": 1.5,
        "unit": "MPa",
        "description": "蒸汽工作表压/绝对压力（默认 1.5 MPa，参考输入表第2行）",
        "min_value": 0.1,
        "max_value": 25.0,
    },
    "steam_temperature": {
        "value": 200.0,
        "unit": "℃",
        "description": "蒸汽供汽温度（默认 200 ℃，参考输入表第3行）",
        "min_value": 100.0,
        "max_value": 600.0,
    },
    "steam_mass_flow": {
        "value": 100.0,
        "unit": "t/h",
        "description": "额定蒸汽流量（默认 100 t/h，参考输入表第4行）",
        "min_value": 0.1,
        "max_value": 2000.0,
    },
    "feedwater_pressure": {
        "value": 0.1,
        "unit": "MPa",
        "description": "锅炉/换热器给水压力（默认 0.1 MPa，参考输入表第5行）",
        "min_value": 0.05,
        "max_value": 25.0,
    },
    "feedwater_temperature": {
        "value": 20.0,
        "unit": "℃",
        "description": "给水温度（默认 20 ℃，参考输入表第6行）",
        "min_value": 5.0,
        "max_value": 150.0,
    },
    "steam_supply_hours": {
        "value": 8.0,
        "unit": "h",
        "description": "每日连续供汽时长（默认 8 h，参考输入表第7行）",
        "min_value": 1.0,
        "max_value": 24.0,
    },
    "valley_electricity_hours": {
        "value": 8.0,
        "unit": "h",
        "description": "每日谷电蓄热时长（默认 8 h，参考输入表第8行，图1批注强调与供汽时长解耦）",
        "min_value": 1.0,
        "max_value": 24.0,
    },
    "annual_operating_days": {
        "value": 330.0,
        "unit": "d",
        "description": "年有效运行天数（默认 330 天，参考输入表第9行）",
        "min_value": 50.0,
        "max_value": 365.0,
    },
    "electric_heater_efficiency": {
        "value": 0.985,
        "unit": "/",
        "description": "电加热器电热转换综合效率（默认 0.985，参考输入表第10行）",
        "min_value": 0.80,
        "max_value": 1.00,
    },
    "heat_exchanger_efficiency": {
        "value": 0.99,
        "unit": "/",
        "description": "SGS换热器换热综合效率（默认 0.99，参考输入表第13行）",
        "min_value": 0.80,
        "max_value": 1.00,
    },
    "thermal_storage_efficiency": {
        "value": 0.99,
        "unit": "/",
        "description": "熔盐储热罐保温与储热效率（默认 0.99，参考输入表第14行）",
        "min_value": 0.80,
        "max_value": 1.00,
    },
    "salt_hot_temperature": {
        "value": 390.0,
        "unit": "℃",
        "description": "储热高温熔盐温度（HITEC盐默认 390 ℃，参考选型表第6行）",
        "min_value": 180.0,
        "max_value": 600.0,
    },
    "salt_cold_temperature": {
        "value": 190.0,
        "unit": "℃",
        "description": "储热低温熔盐温度（HITEC盐默认 190 ℃，参考选型表第7行）",
        "min_value": 150.0,
        "max_value": 450.0,
    },
    "salt_specific_heat": {
        "value": 1.42,
        "unit": "kJ/(kg·℃)",
        "description": "熔盐平均比热容（HITEC盐基准值 1.42 kJ/(kg·℃)，参考选型表第8行）",
        "min_value": 1.0,
        "max_value": 2.5,
    },
    "salt_safety_margin": {
        "value": 1.10,
        "unit": "/",
        "description": "熔盐设计安全冗余系数（参考选型表D9公式中 *1.1 系数）",
        "min_value": 1.0,
        "max_value": 1.5,
    },
    "valley_electricity_price": {
        "value": 0.30,
        "unit": "元/kWh",
        "description": "当地低谷电价（元/度，典型工业低谷电价 0.25~0.35 元/度）",
        "min_value": -0.1,  # 允许部分负电价补贴
        "max_value": 2.0,
    },
    "steam_market_price": {
        "value": 180.0,
        "unit": "元/t",
        "description": "当地工业蒸汽市售价格（元/吨，典型 150~220 元/吨）",
        "min_value": 50.0,
        "max_value": 600.0,
    },
}
