"""Constants for the HACS AI Export integration."""

from __future__ import annotations

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "hacs_ai_export"
NAME = "HACS AI Export"

SERVICE_GENERATE_CONTEXT = "generate_context"

SECTION_DEVICES = "devices"
SECTION_ENTITIES = "entities"
SECTION_ENTITY_ATTRIBUTES = "entity_attributes"
SECTION_SERVICES = "services"
SECTION_ACTIONS = "actions"
SECTION_POSSIBLE_VALUES = "possible_values"

SECTIONS_ALL = (
    SECTION_DEVICES,
    SECTION_ENTITIES,
    SECTION_ENTITY_ATTRIBUTES,
    SECTION_SERVICES,
    SECTION_ACTIONS,
    SECTION_POSSIBLE_VALUES,
)

DEFAULT_SECTIONS = (
    SECTION_DEVICES,
    SECTION_ENTITIES,
    SECTION_ENTITY_ATTRIBUTES,
    SECTION_SERVICES,
    SECTION_POSSIBLE_VALUES,
)
