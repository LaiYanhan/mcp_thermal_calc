"""公式及管道的严格 JSON 契约；不接受 Python 构造式模板。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, TypeAdapter

from core.types import PipelineStep
from core.data_tables import DataPortDefinition, DataTable


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PinDefinition(Definition):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    unit: str = Field(min_length=1)
    description: str
    min_value: FiniteFloat | None = None
    max_value: FiniteFloat | None = None
    default_value: FiniteFloat | None = None
    kind: Literal["input", "constant"] = "input"


class FormulaDefinitionBase(Definition):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.]*$")
    name: str = Field(min_length=1)
    category: str
    description: str = ""
    notes: str = ""
    inputs: list[PinDefinition] = Field(min_length=1)
    outputs: list[PinDefinition] = Field(min_length=1)


class AlgebraicDefinition(FormulaDefinitionBase):
    formula_type: Literal["algebraic"]
    expression: str = Field(min_length=1)
    handler: None = None
    is_bidirectional: Literal[True] = True
    data_inputs: list[DataPortDefinition] = Field(default_factory=list, max_length=0)


class EmpiricalDefinition(FormulaDefinitionBase):
    formula_type: Literal["empirical"]
    handler: str = Field(min_length=1)
    expression: None = None
    is_bidirectional: Literal[False] = False
    data_inputs: list[DataPortDefinition] = Field(default_factory=list)


FormulaDefinition = Annotated[AlgebraicDefinition | EmpiricalDefinition, Field(discriminator="formula_type")]
formula_definition_adapter = TypeAdapter(FormulaDefinition)


class StepDefinition(PipelineStep):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConstraintDefinition(Definition):
    variable: str
    min_value: FiniteFloat | None = None
    max_value: FiniteFloat | None = None
    greater_than: str | None = None
    message: str = ""


class PipelineDefinition(Definition):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    name: str = Field(min_length=1)
    category: str = "custom"
    description: str = ""
    notes: str = ""
    required_inputs: list[PinDefinition]
    steps: list[StepDefinition] = Field(min_length=1)
    layout: dict[str, dict[str, FiniteFloat]] = Field(default_factory=dict)
    input_constraints: list[ConstraintDefinition] = Field(default_factory=list)
    data_tables: list[DataTable] = Field(default_factory=list)
