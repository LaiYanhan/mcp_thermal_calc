"""熔盐场景的参数约束及旧工程定义转换。"""

from dataclasses import asdict

from constants.molten_salt import SALT_PROFILES
from core.types import InputConstraint


def salt_temperature_constraints(profile_name=None):
    constraints = [InputConstraint(
        variable="salt_hot_temperature", greater_than="salt_cold_temperature",
        message="高温熔盐温度必须大于低温熔盐温度",
    )]
    if profile_name:
        if profile_name not in SALT_PROFILES:
            raise ValueError("未知的储热介质")
        profile = SALT_PROFILES[profile_name]
        constraints.extend(InputConstraint(
            variable=name, min_value=profile.min_temp_c, max_value=profile.max_temp_c,
            message=f"{profile.name} 温度必须在 {profile.min_temp_c}–{profile.max_temp_c} ℃ 内",
        ) for name in ("salt_hot_temperature", "salt_cold_temperature"))
    return constraints


def migrate_legacy_constraints(data):
    """仅转换带旧 salt_profile 字段的工程；新定义只使用显式约束。"""
    if "salt_profile" not in data:
        return data
    profile_name = data.pop("salt_profile")
    if "input_constraints" not in data:
        inputs = {pin["name"] for pin in data.get("required_inputs", [])}
        data["input_constraints"] = [
            asdict(constraint) for constraint in salt_temperature_constraints(profile_name)
            if constraint.variable in inputs and
            (constraint.greater_than is None or constraint.greater_than in inputs)
        ]
    return data
