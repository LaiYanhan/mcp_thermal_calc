"""
Core type definitions for thermal calculation and sizing system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field


class FormulaType(str, Enum):
    """公式计算类型"""
    ALGEBRAIC = "algebraic"  # 纯代数解析公式，基于 SymPy 自动双向求解
    EMPIRICAL = "empirical"  # 经验/物性黑盒函数（如 IAPWS-IF97 物性查表、设备离散选型查表）


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

    def validate(self, value: float) -> None:
        """校验数值是否在合理物理区间内"""
        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"参数 '{self.description}' ({self.name}) 数值 {value} 小于合理下限 {self.min_value} {self.unit}")
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"参数 '{self.description}' ({self.name}) 数值 {value} 超过合理上限 {self.max_value} {self.unit}")


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
    inputs: List[Pin]  # 输入引脚列表
    outputs: List[Pin]  # 输出引脚列表
    expression: Optional[str] = None  # 代数表达式（仅 ALGEBRAIC 类型使用，如 "P = m * dh / 3600"）
    is_bidirectional: bool = True  # 是否支持双向逆推


class PipelineStep(BaseModel):
    """
    计算管道中的单个步骤节点
    """
    step_id: str = Field(..., description="步骤唯一标识")
    formula_id: str = Field(..., description="引用的原子公式ID")
    input_map: Dict[str, str] = Field(..., description="引脚映射：公式入参 Pin -> 管道全局变量名或固定值")
    output_map: Dict[str, str] = Field(..., description="引脚映射：公式出参 Pin -> 管道全局变量名")
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
    sizing_summary: Dict[str, Any] = Field(default_factory=dict, description="主要设备选型汇总")
    economic_summary: Dict[str, Any] = Field(default_factory=dict, description="经济收益初测汇总")
