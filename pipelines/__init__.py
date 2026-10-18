"""
Pipelines package exports and automatic registration.
"""

import formulas  # noqa: F401
from core.pipeline import pipeline_registry
from pipelines.validation import migrate_legacy_constraints

pipeline_registry.register_definition_migration(migrate_legacy_constraints)

import pipelines.electric_heater_salt_steam  # noqa: F401
import pipelines.industrial_heat_pump_steam  # noqa: F401

pipeline_registry.load_saved()

__all__ = ["pipeline_registry"]
