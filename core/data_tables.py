"""场景内工程数据契约与通用取值规则，不包含业务名称或设备默认值。"""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext
from bisect import bisect_left, bisect_right
import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
from core.types import units_match


class DataDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DataPortDefinition(DataDefinition):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    rule_type: Literal["fixed_step", "discrete", "piecewise", "correlation"]
    input_unit: str = Field(min_length=1)
    output_unit: str = Field(min_length=1)


class TableDefinition(DataDefinition):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    description: str
    input_unit: str = Field(min_length=1)
    output_unit: str = Field(min_length=1)


class QuantizationTable(TableDefinition):
    mode: Literal["ceil", "floor", "nearest"]

    @model_validator(mode="after")
    def check_units(self) -> Self:
        if not units_match(self.input_unit, self.output_unit):
            raise ValueError("整定的输入与输出单位必须一致")
        return self


class FixedStepTable(QuantizationTable):
    rule_type: Literal["fixed_step"]
    step: FiniteFloat = Field(gt=0)


class DiscreteTable(QuantizationTable):
    rule_type: Literal["discrete"]
    levels: list[FiniteFloat] = Field(min_length=1)

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if any(left >= right for left, right in zip(self.levels, self.levels[1:])):
            raise ValueError("档位必须严格递增")
        return self


class TableRow(DataDefinition):
    threshold: FiniteFloat
    value: FiniteFloat


class PiecewiseTable(TableDefinition):
    rule_type: Literal["piecewise"]
    rows: list[TableRow] = Field(min_length=1)

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if any(left.threshold >= right.threshold for left, right in zip(self.rows, self.rows[1:])):
            raise ValueError("分段阈值必须严格递增")
        return self


class CorrelationTerm(DataDefinition):
    coefficient: FiniteFloat
    power: FiniteFloat


class CorrelationTable(TableDefinition):
    rule_type: Literal["correlation"]
    terms: list[CorrelationTerm] = Field(min_length=1)
    divisor: FiniteFloat = 1

    @model_validator(mode="after")
    def check_divisor(self) -> Self:
        if self.divisor == 0:
            raise ValueError("关联式除数不能为零")
        return self


DataTable = Annotated[FixedStepTable | DiscreteTable | PiecewiseTable | CorrelationTable, Field(discriminator="rule_type")]


def fixed_step(inputs: dict[str, float], data: dict[str, FixedStepTable]) -> dict[str, float]:
    table = data["table"]
    # JSON 十进制刻度不通过二进制浮点相除，避免 0.3/0.1 向上多进一档。
    with localcontext() as context:
        context.prec = 700
        step = Decimal(str(table.step))
        rounding = {"ceil": ROUND_CEILING, "floor": ROUND_FLOOR, "nearest": ROUND_HALF_UP}[table.mode]
        value = (Decimal(str(inputs["value"])) / step).to_integral_value(rounding=rounding) * step
    return {"result": float(value)}


def discrete(inputs: dict[str, float], data: dict[str, DiscreteTable]) -> dict[str, float]:
    table = data["table"]
    levels, value = table.levels, inputs["value"]
    if table.mode == "ceil":
        index = min(bisect_left(levels, value), len(levels) - 1)
    elif table.mode == "floor":
        index = max(bisect_right(levels, value) - 1, 0)
    else:
        upper = min(bisect_left(levels, value), len(levels) - 1)
        lower = max(upper - 1, 0)
        with localcontext() as context:
            context.prec = 700
            query = Decimal(str(value))
            index = min((lower, upper), key=lambda i: (abs(Decimal(str(levels[i])) - query), -abs(levels[i])))
    return {"result": levels[index]}


def piecewise(inputs: dict[str, float], data: dict[str, PiecewiseTable]) -> dict[str, float]:
    rows = data["table"].rows
    index = max(bisect_right([row.threshold for row in rows], inputs["value"]) - 1, 0)
    return {"result": rows[index].value}


def correlation(inputs: dict[str, float], data: dict[str, CorrelationTable]) -> dict[str, float]:
    table = data["table"]
    value = sum(term.coefficient * math.pow(inputs["value"], term.power) for term in table.terms) / table.divisor
    return {"result": value}
