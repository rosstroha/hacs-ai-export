"""Data export utilities for AI-ready Home Assistant context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any

import yaml
from homeassistant.const import CONF_DOMAIN, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_get_all_descriptions

from .const import (
    SECTION_ACTIONS,
    SECTION_DEVICES,
    SECTION_ENTITIES,
    SECTION_ENTITY_ATTRIBUTES,
    SECTION_POSSIBLE_VALUES,
    SECTION_SERVICES,
)

KNOWN_POSSIBLE_VALUE_ATTRS = (
    "options",
    "preset_modes",
    "hvac_modes",
    "fan_modes",
    "swing_modes",
    "effect_list",
    "source_list",
    "sound_mode_list",
    "operation_list",
    "modes",
    "available_modes",
)


@dataclass(slots=True, frozen=True)
class ExportRequest:
    """Normalized export request data."""

    sections: tuple[str, ...]
    entity_ids: tuple[str, ...]
    device_ids: tuple[str, ...]
    area_ids: tuple[str, ...]
    label_ids: tuple[str, ...]
    domains: tuple[str, ...]
    include_disabled_entities: bool
    output_format: str
    max_entities: int
    max_services: int


@dataclass(slots=True, frozen=True)
class ExportResult:
    """Export output."""

    text: str
    payload: dict[str, Any]
    summary: dict[str, Any]


async def async_generate_export(
    hass: HomeAssistant,
    request: ExportRequest,
) -> ExportResult:
    """Generate an AI-context export from the user's selected sections."""
    sections = set(request.sections)
    normalized_domains = {
        domain.lower().strip() for domain in request.domains if domain.strip()
    }
    selected_device_ids = set(request.device_ids)
    selected_entity_ids = set(request.entity_ids)
    selected_area_ids = set(request.area_ids)
    selected_label_ids = set(request.label_ids)
    has_entity_scope_filter = bool(
        selected_entity_ids
        or selected_device_ids
        or selected_area_ids
        or selected_label_ids
    )

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    area_registry = ar.async_get(hass)

    devices_data: list[dict[str, Any]] = []
    if SECTION_DEVICES in sections:
        devices_data = _collect_devices(
            device_registry=device_registry,
            area_registry=area_registry,
            selected_device_ids=selected_device_ids,
            selected_area_ids=selected_area_ids,
            selected_label_ids=selected_label_ids,
            normalized_domains=normalized_domains,
            entity_registry=entity_registry,
        )

    should_collect_entities = (
        SECTION_ENTITIES in sections
        or SECTION_ENTITY_ATTRIBUTES in sections
        or SECTION_POSSIBLE_VALUES in sections
        or (
            (SECTION_SERVICES in sections or SECTION_ACTIONS in sections)
            and not normalized_domains
            and has_entity_scope_filter
        )
    )
    entities_data: list[dict[str, Any]] = []
    if should_collect_entities:
        entities_data = _collect_entities(
            hass=hass,
            device_registry=device_registry,
            entity_registry=entity_registry,
            area_registry=area_registry,
            selected_entity_ids=selected_entity_ids,
            selected_device_ids=selected_device_ids,
            selected_area_ids=selected_area_ids,
            selected_label_ids=selected_label_ids,
            normalized_domains=normalized_domains,
            include_disabled_entities=request.include_disabled_entities,
            include_attributes=SECTION_ENTITY_ATTRIBUTES in sections,
            include_possible_values=SECTION_POSSIBLE_VALUES in sections,
            max_entities=request.max_entities,
        )

    services_data: list[dict[str, Any]] = []
    actions_data: list[dict[str, Any]] = []
    if SECTION_SERVICES in sections or SECTION_ACTIONS in sections:
        services_data = await _collect_services(
            hass=hass,
            normalized_domains=normalized_domains,
            entities_data=entities_data,
            max_services=request.max_services,
            use_entity_domains=has_entity_scope_filter and not normalized_domains,
        )
        if SECTION_ACTIONS in sections:
            actions_data = [
                {
                    "action": f"{service['domain']}.{service['service']}",
                    "targetable": service["target"],
                    "description": service.get("description"),
                }
                for service in services_data
            ]

    payload: dict[str, Any] = {
        "meta": {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "format_version": 1,
            "selected_sections": sorted(sections),
        },
        "selection": {
            "entity_ids": sorted(selected_entity_ids),
            "device_ids": sorted(selected_device_ids),
            "area_ids": sorted(selected_area_ids),
            "label_ids": sorted(selected_label_ids),
            "domains": sorted(normalized_domains),
            "include_disabled_entities": request.include_disabled_entities,
        },
    }

    if SECTION_DEVICES in sections:
        payload["devices"] = devices_data
    if (
        SECTION_ENTITIES in sections
        or SECTION_ENTITY_ATTRIBUTES in sections
        or SECTION_POSSIBLE_VALUES in sections
    ):
        payload["entities"] = entities_data
    if SECTION_SERVICES in sections:
        payload["services"] = services_data
    if SECTION_ACTIONS in sections:
        payload["actions"] = actions_data

    text = _format_output_text(payload=payload, output_format=request.output_format)
    summary = {
        "sections": sorted(sections),
        "device_count": len(devices_data),
        "entity_count": len(entities_data),
        "service_count": len(services_data),
        "action_count": len(actions_data),
        "format": request.output_format,
    }
    return ExportResult(text=text, payload=payload, summary=summary)


def _collect_devices(
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
    selected_device_ids: set[str],
    selected_area_ids: set[str],
    selected_label_ids: set[str],
    normalized_domains: set[str],
    entity_registry: er.EntityRegistry,
) -> list[dict[str, Any]]:
    """Collect device metadata."""
    result: list[dict[str, Any]] = []
    for device in device_registry.devices.values():
        if selected_device_ids and device.id not in selected_device_ids:
            continue
        if selected_area_ids and device.area_id not in selected_area_ids:
            continue
        if selected_label_ids and not _device_matches_labels(
            device=device,
            selected_label_ids=selected_label_ids,
            area_registry=area_registry,
        ):
            continue
        if normalized_domains and not _device_matches_domains(
            device_id=device.id,
            normalized_domains=normalized_domains,
            entity_registry=entity_registry,
        ):
            continue
        area_name = None
        if device.area_id is not None:
            area = area_registry.async_get_area(device.area_id)
            area_name = area.name if area else None
        result.append(
            {
                "device_id": device.id,
                "name": device.name_by_user or device.name,
                "manufacturer": device.manufacturer,
                "model": device.model,
                "sw_version": device.sw_version,
                "hw_version": device.hw_version,
                "area_id": device.area_id,
                "area_name": area_name,
                "labels": sorted(device.labels),
                "identifiers": sorted(
                    f"{key}:{value}" for key, value in device.identifiers
                ),
                "connections": sorted(
                    f"{key}:{value}" for key, value in device.connections
                ),
            }
        )
    return sorted(result, key=lambda item: (item.get("name") or "", item["device_id"]))


def _collect_entities(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    area_registry: ar.AreaRegistry,
    selected_entity_ids: set[str],
    selected_device_ids: set[str],
    selected_area_ids: set[str],
    selected_label_ids: set[str],
    normalized_domains: set[str],
    include_disabled_entities: bool,
    include_attributes: bool,
    include_possible_values: bool,
    max_entities: int,
) -> list[dict[str, Any]]:
    """Collect entity metadata and runtime state."""
    result: list[dict[str, Any]] = []
    for entity in entity_registry.entities.values():
        resolved_area_id = _resolve_entity_area_id(
            entity=entity,
            device_registry=device_registry,
        )
        if selected_entity_ids and entity.entity_id not in selected_entity_ids:
            continue
        if selected_device_ids and entity.device_id not in selected_device_ids:
            continue
        if selected_area_ids and not (
            resolved_area_id and resolved_area_id in selected_area_ids
        ):
            continue
        if selected_label_ids and not _entity_matches_labels(
            entity=entity,
            resolved_area_id=resolved_area_id,
            selected_label_ids=selected_label_ids,
            device_registry=device_registry,
            area_registry=area_registry,
        ):
            continue
        if normalized_domains and entity.domain not in normalized_domains:
            continue
        if not include_disabled_entities and entity.disabled_by is not None:
            continue

        state = hass.states.get(entity.entity_id)
        entry: dict[str, Any] = {
            "entity_id": entity.entity_id,
            "domain": entity.domain,
            "name": entity.name or entity.original_name,
            "device_id": entity.device_id,
            "area_id": resolved_area_id,
            "area_name": _resolve_area_name(area_registry, resolved_area_id),
            "labels": sorted(entity.labels),
            "state": state.state if state else None,
            "state_is_reliable": bool(
                state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
            ),
            "unit_of_measurement": state.attributes.get("unit_of_measurement")
            if state
            else None,
        }

        if include_attributes and state:
            entry["attributes"] = _json_safe_dict(state.attributes)
        if include_possible_values and state:
            possible_values = _extract_possible_values(state.attributes)
            if possible_values:
                entry["possible_values"] = possible_values

        result.append(entry)
        if len(result) >= max_entities:
            break

    return sorted(result, key=lambda item: item["entity_id"])


async def _collect_services(
    hass: HomeAssistant,
    normalized_domains: set[str],
    entities_data: Sequence[Mapping[str, Any]],
    max_services: int,
    use_entity_domains: bool,
) -> list[dict[str, Any]]:
    """Collect services and action metadata."""
    descriptions = await async_get_all_descriptions(hass)
    services = hass.services.async_services()
    candidate_domains = set(normalized_domains)
    if not candidate_domains and use_entity_domains:
        candidate_domains.update(
            entity[CONF_DOMAIN]
            for entity in entities_data
            if isinstance(entity.get(CONF_DOMAIN), str)
        )

    result: list[dict[str, Any]] = []
    for domain, domain_services in services.items():
        if candidate_domains and domain not in candidate_domains:
            continue

        domain_descriptions = descriptions.get(domain, {})
        for service_name, service in domain_services.items():
            service_description = domain_descriptions.get(service_name, {})
            fields = service_description.get("fields", {})
            result.append(
                {
                    "domain": domain,
                    "service": service_name,
                    "target": _json_safe_dict(service_description.get("target", {})),
                    "description": _json_safe_value(
                        service_description.get("description")
                    ),
                    "fields": _json_safe_dict(fields),
                    "supports_response": _json_safe_value(
                        getattr(service, "supports_response", "none")
                    ),
                }
            )
            if len(result) >= max_services:
                return sorted(
                    result,
                    key=lambda item: (item["domain"], item["service"]),
                )

    return sorted(result, key=lambda item: (item["domain"], item["service"]))


def _resolve_area_name(
    area_registry: ar.AreaRegistry,
    area_id: str | None,
) -> str | None:
    """Resolve area ID to area name."""
    if area_id is None:
        return None
    area = area_registry.async_get_area(area_id)
    return area.name if area else None


def _resolve_entity_area_id(
    entity: er.RegistryEntry,
    device_registry: dr.DeviceRegistry,
) -> str | None:
    """Resolve area, falling back to the linked device area."""
    if entity.area_id is not None:
        return entity.area_id
    if entity.device_id is None:
        return None
    device = device_registry.async_get(entity.device_id)
    return device.area_id if device else None


def _device_matches_domains(
    device_id: str,
    normalized_domains: set[str],
    entity_registry: er.EntityRegistry,
) -> bool:
    """Check whether a device has entities in selected domains."""
    for entity in entity_registry.entities.values():
        if entity.device_id == device_id and entity.domain in normalized_domains:
            return True
    return False


def _device_matches_labels(
    device: dr.DeviceEntry,
    selected_label_ids: set[str],
    area_registry: ar.AreaRegistry,
) -> bool:
    """Check whether a device matches label filters."""
    if selected_label_ids.intersection(device.labels):
        return True
    if device.area_id is None:
        return False
    area = area_registry.async_get_area(device.area_id)
    return bool(area and selected_label_ids.intersection(area.labels))


def _entity_matches_labels(
    entity: er.RegistryEntry,
    resolved_area_id: str | None,
    selected_label_ids: set[str],
    device_registry: dr.DeviceRegistry,
    area_registry: ar.AreaRegistry,
) -> bool:
    """Check whether an entity matches label filters."""
    if selected_label_ids.intersection(entity.labels):
        return True
    if entity.device_id is not None:
        device = device_registry.async_get(entity.device_id)
        if device and selected_label_ids.intersection(device.labels):
            return True
    if resolved_area_id is not None:
        area = area_registry.async_get_area(resolved_area_id)
        if area and selected_label_ids.intersection(area.labels):
            return True
    return False


def _extract_possible_values(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Extract likely value spaces from entity attributes."""
    output: dict[str, Any] = {}
    for key in KNOWN_POSSIBLE_VALUE_ATTRS:
        value = attributes.get(key)
        if isinstance(value, list) and value:
            output[key] = value

    min_value = attributes.get("min")
    max_value = attributes.get("max")
    step = attributes.get("step")
    if min_value is not None and max_value is not None:
        output["numeric_range"] = {
            "min": min_value,
            "max": max_value,
            "step": step,
        }
    return output


def _json_safe_dict(input_data: Mapping[str, Any]) -> dict[str, Any]:
    """Convert any value to JSON-safe primitives."""
    output: dict[str, Any] = {}
    for key, value in input_data.items():
        output[str(key)] = _json_safe_value(value)
    return output


def _json_safe_value(value: Any) -> Any:
    """Convert a value to a JSON-safe value."""
    if isinstance(value, str):
        return str(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return _json_safe_dict(value)
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    return str(value)


def _format_output_text(payload: dict[str, Any], output_format: str) -> str:
    """Format payload into the requested output format."""
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "yaml":
        return yaml.safe_dump(
            payload,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=False,
        )
    return yaml.safe_dump(
        payload,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=False,
    )
