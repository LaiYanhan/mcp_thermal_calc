"""
Pipelines package exports and automatic registration.
"""

import pipelines.electric_heater_salt_steam  # noqa: F401
import pipelines.industrial_heat_pump_steam  # noqa: F401
from core.pipeline import pipeline_registry

pipeline_registry.load_saved()

__all__ = ["pipeline_registry"]
