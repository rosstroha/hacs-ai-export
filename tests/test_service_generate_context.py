from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
import yaml

import custom_components.hacs_ai_export as integration_module
from custom_components.hacs_ai_export.const import (
    DOMAIN,
    SECTION_DEVICES,
    SECTION_ENTITIES,
    SECTION_ENTITY_ATTRIBUTES,
    SECTION_POSSIBLE_VALUES,
    SECTION_SERVICES,
    SERVICE_GENERATE_CONTEXT,
)
from custom_components.hacs_ai_export.exporter import ExportResult


async def _create_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return hass.config_entries.async_entries(DOMAIN)[0]


async def test_generate_context_returns_response_payload(hass):
    await _create_entry(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GENERATE_CONTEXT,
        {
            "sections": [SECTION_SERVICES],
            "output_format": "json",
            "create_notification": False,
            "max_services": 50,
        },
        blocking=True,
        return_response=True,
    )

    assert "text" in response
    assert "payload" in response
    assert "summary" in response
    assert response["summary"]["service_count"] > 0
    assert "services" in response["payload"]


async def test_generate_context_returns_plain_yaml_text(hass):
    await _create_entry(hass)

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GENERATE_CONTEXT,
        {
            "sections": [SECTION_SERVICES],
            "output_format": "yaml",
            "create_notification": False,
            "max_services": 20,
        },
        blocking=True,
        return_response=True,
    )

    text = response["text"]
    assert isinstance(text, str)
    assert not text.startswith("# Home Assistant AI Context Export")

    parsed = yaml.safe_load(text)
    assert isinstance(parsed, dict)
    assert "meta" in parsed
    assert "selection" in parsed
    assert "services" in parsed


async def test_generate_context_normalizes_domains(monkeypatch, hass):
    await _create_entry(hass)
    captured = {}

    async def _fake_generate_export(_hass, request):
        captured["domains"] = request.domains
        return ExportResult(
            text="{}",
            payload={},
            summary={
                "sections": [],
                "device_count": 0,
                "entity_count": 0,
                "service_count": 0,
                "action_count": 0,
                "format": "json",
            },
        )

    monkeypatch.setattr(
        integration_module,
        "async_generate_export",
        _fake_generate_export,
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_GENERATE_CONTEXT,
        {
            "sections": [SECTION_SERVICES],
            "domains": "light, switch,climate",
            "output_format": "json",
            "create_notification": False,
        },
        blocking=True,
        return_response=True,
    )

    assert captured["domains"] == ("light", "switch", "climate")


async def test_generate_context_filters_entities_and_includes_possible_values(hass):
    entry = await _create_entry(hass)

    area_registry = ar.async_get(hass)
    kitchen = area_registry.async_create("Kitchen")

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "device-1")},
        name="Kitchen Light Device",
    )
    device_registry.async_update_device(device_entry.id, area_id=kitchen.id)

    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get_or_create(
        "light",
        DOMAIN,
        "kitchen_main",
        suggested_object_id="kitchen_main",
        device_id=device_entry.id,
    )
    hass.states.async_set(
        entity_entry.entity_id,
        "on",
        {"options": ["on", "off"], "brightness": 150, "supported_features": 1},
    )

    second_entity_entry = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        "garage_aux",
        suggested_object_id="garage_aux",
    )
    hass.states.async_set(second_entity_entry.entity_id, "off", {})

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GENERATE_CONTEXT,
        {
            "sections": [
                SECTION_ENTITIES,
                SECTION_ENTITY_ATTRIBUTES,
                SECTION_POSSIBLE_VALUES,
                SECTION_DEVICES,
            ],
            "entity_id": [entity_entry.entity_id],
            "output_format": "json",
            "create_notification": False,
        },
        blocking=True,
        return_response=True,
    )

    payload = response["payload"]
    entities = payload["entities"]
    assert len(entities) == 1
    assert entities[0]["entity_id"] == entity_entry.entity_id
    assert entities[0]["possible_values"]["options"] == ["on", "off"]
    assert entities[0]["attributes"]["brightness"] == 150
    assert any(
        device["device_id"] == device_entry.id for device in payload["devices"]
    )


async def test_generate_context_filters_by_labels(hass):
    entry = await _create_entry(hass)

    label_registry = lr.async_get(hass)
    label = label_registry.async_create("AI Export Label")

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "device-labeled")},
        name="Labeled Device",
    )
    device_registry.async_update_device(device_entry.id, labels={label.label_id})

    entity_registry = er.async_get(hass)
    labeled_entity = entity_registry.async_get_or_create(
        "light",
        DOMAIN,
        "labeled_light",
        suggested_object_id="labeled_light",
        device_id=device_entry.id,
    )
    hass.states.async_set(labeled_entity.entity_id, "on", {})

    unlabeled_entity = entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        "unlabeled_switch",
        suggested_object_id="unlabeled_switch",
    )
    hass.states.async_set(unlabeled_entity.entity_id, "off", {})

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GENERATE_CONTEXT,
        {
            "sections": [SECTION_ENTITIES, SECTION_DEVICES],
            "label_ids": [label.label_id],
            "output_format": "json",
            "create_notification": False,
        },
        blocking=True,
        return_response=True,
    )

    payload = response["payload"]
    entity_ids = {item["entity_id"] for item in payload["entities"]}
    device_ids = {item["device_id"] for item in payload["devices"]}

    assert labeled_entity.entity_id in entity_ids
    assert unlabeled_entity.entity_id not in entity_ids
    assert device_entry.id in device_ids
