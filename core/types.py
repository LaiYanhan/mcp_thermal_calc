"""
Core type definitions for thermal calculation and sizing system.
"""

from dataclasses import dataclass, field
import math
import re
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field


class FormulaType(str, Enum):
    """公式计算类型"""
    ALGEBRAIC = "algebraic"  # 纯代数解析公式，基于 SymPy 自动双向求解
    EMPIRICAL = "empirical"  # 经验/物性黑盒函数（如 IAPWS-95 物性查表、设备离散选型查表）


@dataclass
class Pin:
    """
    公式引脚定义（输入或输出参数）
    """
    name: str  # 变量符号/英文字段名，如 steam_pressure
    unit: str  # 物理单位，如 MPa, ℃, t/h, MW, MWh, kJ/kg
    description: str  # 详细中文说明与物理含义，如 "蒸汽工作压力"
    min_value: Optional[float] = None  # 合理物理下限
    max_value: Optional[float] = None  # 合理物理上限
    default_value: Optional[float] = None  # 默认基准值（若有）
    kind: str = "input"  # input 工况输入 / constant 工程常量

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", self.name):
            raise ValueError("引脚标识必须以英文字母开头，仅包含字母、数字和下划线")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError(f"引脚 {self.name} 缺少单位，无量纲请填写 /")
        if self.kind not in ("input", "constant"):
            raise ValueError("引脚种类必须是 input 或 constant")
        for value in (self.min_value, self.max_value):
            if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError("引脚范围必须为有限数值")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("引脚下限不能大于上限")
        if self.default_value is not None:
            self.validate(self.default_value)

    def validate(self, value: float) -> None:
        """校验数值是否在合理物理区间内"""
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"参数 '{self.description}' ({self.name}) 必须为有限数值")
        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"参数 '{self.description}' ({self.name}) 数值 {value} 小于合理下限 {self.min_value} {self.unit}")
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"参数 '{self.description}' ({self.name}) 数值 {value} 超过合理上限 {self.max_value} {self.unit}")


def units_match(left: str, right: str) -> bool:
    """同量纲同倍率的常见书写别名；不同倍率必须显式转换。"""
    aliases = {"MWt": "MW", "MWe": "MW", "MWht": "MWh", "°C": "℃",
               "kJ/(kg·K)": "kJ/(kg·℃)", "1": "/"}
    return aliases.get(left, left) == aliases.get(right, right)


@dataclass
class FormulaMetadata:
    """
    公式元数据定义
    """
    id: str  # 全局唯一标识，如 "thermal.sgs_power"
    name: str  # 中文公式名，如 "SGS换热功率计算"
    category: str  # 业务分类：thermal (热工), sizing (选型), operation (运行/经济)
    description: str  # 物理逻辑解释
    notes: str  # 工程注意事项（如温区限制、夹点、时长对齐等）
    formula_type: FormulaType  # 公式类型
    inputs: List[Pin]  # 默认求解方向的输入引脚
    outputs: List[Pin]  # 默认求解方向的输出引脚
    expression: Optional[str] = None  # 代数表达式（仅 ALGEBRAIC 类型使用，如 "P = m * dh / 3600"）
    is_bidirectional: bool = True  # 是否支持双向逆推


class PipelineStep(BaseModel):
    """
    计算管道中的单个步骤节点
    """
    step_id: str = Field(..., description="步骤唯一标识")
    formula_id: str = Field(..., description="引用的原子公式ID")
    solve_target: Optional[str] = Field(None, description="本节点待求的公式变量；省略时沿用公式默认输出，其余变量全部作为已知量")
    input_map: Dict[str, str] = Field(..., description="当前已知引脚 -> 来源变量名（场景输入、常量或其他步骤输出）")
    output_map: Dict[str, str] = Field(..., description="当前待求引脚 -> 本步骤产出的管道变量名")
    description: str = Field("", description="本步骤的业务场景说明")


class StepExecutionRecord(BaseModel):
    """
    单步执行明细记录
    """
    step_id: str
    formula_id: str
    formula_name: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    notes: str = ""


class FormulaOutput(BaseModel):
    """一个步骤实际产出的成果，包括继续供下游使用的中间结果。"""
    step_id: str
    formula_id: str
    formula_name: str
    pin: str
    variable: str
    description: str
    unit: str
    value: float


class PipelineExecutionResult(BaseModel):
    """
    管道最终执行产物
    """
    pipeline_id: str
    pipeline_name: str
    scenario_description: str
    initial_inputs: Dict[str, Any]
    final_outputs: Dict[str, Any]
    step_records: List[StepExecutionRecord]
    results: List[FormulaOutput] = Field(default_factory=list, description="全部步骤的公式输出，不含外部输入及常量")
