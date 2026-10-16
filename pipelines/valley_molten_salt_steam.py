"""
向前兼容重定向模块：
原 valley_molten_salt_steam.py 已按方案 B 规范重命名为 electric_heater_salt_steam.py。
请优先使用 pipelines.electric_heater_salt_steam。
"""

from pipelines.electric_heater_salt_steam import (
    ELECTRIC_HEATER_SALT_STEAM_REQUIRED_INPUTS,
    ELECTRIC_HEATER_SALT_STEAM_STEPS,
    electric_heater_salt_steam_pipeline,
    VALLEY_SALT_STEAM_REQUIRED_INPUTS,
    VALLEY_SALT_STEAM_STEPS,
    valley_molten_salt_steam_pipeline,
)

__all__ = [
    "ELECTRIC_HEATER_SALT_STEAM_REQUIRED_INPUTS",
    "ELECTRIC_HEATER_SALT_STEAM_STEPS",
    "electric_heater_salt_steam_pipeline",
    "VALLEY_SALT_STEAM_REQUIRED_INPUTS",
    "VALLEY_SALT_STEAM_STEPS",
    "valley_molten_salt_steam_pipeline",
]
