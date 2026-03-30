"""Set up the HACS AI Export integration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DOMAINS, CONF_ENTITY_ID
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DEFAULT_SECTIONS,
    DOMAIN,
    LOGGER,
    SECTIONS_ALL,
    SERVICE_GENERATE_CONTEXT,
)
from .exporter import ExportRequest, async_generate_export

CONF_SECTIONS = "sections"
CONF_DEVICE_IDS = "device_ids"
CONF_AREA_IDS = "area_ids"
CONF_LABEL_IDS = "label_ids"
CONF_CREATE_NOTIFICATION = "create_notification"
CONF_OUTPUT_FORMAT = "output_format"
CONF_INCLUDE_DISABLED_ENTITIES = "include_disabled_entities"
CONF_MAX_ENTITIES = "max_entities"
CONF_MAX_SERVICES = "max_services"

OUTPUT_FORMAT_MARKDOWN = "markdown"
OUTPUT_FORMAT_JSON = "json"
OUTPUT_FORMAT_YAML = "yaml"
FRONTEND_MENU_JS_PATH = f"/{DOMAIN}/menu.js"

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SECTIONS, default=list(DEFAULT_SECTIONS)): vol.All(
            cv.ensure_list,
            [vol.In(SECTIONS_ALL)],
        ),
        vol.Optional(CONF_ENTITY_ID): cv.entity_ids,
        vol.Optional(CONF_DEVICE_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_AREA_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_LABEL_IDS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_DOMAINS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_INCLUDE_DISABLED_ENTITIES, default=False): cv.boolean,
        vol.Optional(CONF_CREATE_NOTIFICATION, default=True): cv.boolean,
        vol.Optional(CONF_OUTPUT_FORMAT, default=OUTPUT_FORMAT_YAML): vol.In(
            (OUTPUT_FORMAT_YAML, OUTPUT_FORMAT_JSON, OUTPUT_FORMAT_MARKDOWN)
        ),
        vol.Optional(CONF_MAX_ENTITIES, default=500): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=5000),
        ),
        vol.Optional(CONF_MAX_SERVICES, default=500): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=5000),
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration from yaml."""
    del config
    hass.data.setdefault(
        DOMAIN,
        {
            "entry_ids": set(),
            "service_unsub": None,
            "frontend_registered": False,
        },
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Set up HACS AI Export from a config entry."""
    domain_data: dict[str, Any] = hass.data.setdefault(
        DOMAIN,
        {
            "entry_ids": set(),
            "service_unsub": None,
            "frontend_registered": False,
        },
    )
    entry_ids: set[str] = domain_data["entry_ids"]
    entry_ids.add(entry.entry_id)

    if not domain_data["frontend_registered"]:
        await _async_register_frontend_menu_js(hass)
        domain_data["frontend_registered"] = True

    if domain_data["service_unsub"] is None:
        domain_data["service_unsub"] = _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Unload a config entry."""
    domain_data: dict[str, Any] = hass.data.get(DOMAIN, {})
    entry_ids: set[str] = domain_data.get("entry_ids", set())
    entry_ids.discard(entry.entry_id)
    if not entry_ids:
        remove_services: Callable[[], None] | None = domain_data.get("service_unsub")
        if remove_services is not None:
            remove_services()
        hass.data.pop(DOMAIN, None)
    return True


def _async_register_services(hass: HomeAssistant) -> Callable[[], None]:
    """Register integration services."""

    async def handle_generate_context(call: ServiceCall) -> ServiceResponse:
        """Generate AI-formatted Home Assistant context."""
        normalized_domains = _normalize_domains(call.data.get(CONF_DOMAINS, []))
        request = ExportRequest(
            sections=tuple(call.data[CONF_SECTIONS]),
            entity_ids=tuple(call.data.get(CONF_ENTITY_ID, [])),
            device_ids=tuple(call.data.get(CONF_DEVICE_IDS, [])),
            area_ids=tuple(call.data.get(CONF_AREA_IDS, [])),
            label_ids=tuple(call.data.get(CONF_LABEL_IDS, [])),
            domains=normalized_domains,
            include_disabled_entities=bool(call.data[CONF_INCLUDE_DISABLED_ENTITIES]),
            output_format=str(call.data[CONF_OUTPUT_FORMAT]),
            max_entities=int(call.data[CONF_MAX_ENTITIES]),
            max_services=int(call.data[CONF_MAX_SERVICES]),
        )

        result = await async_generate_export(hass, request)

        return {
            "text": result.text,
            "payload": result.payload,
            "summary": result.summary,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_CONTEXT,
        handle_generate_context,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    def remove_services() -> None:
        """Remove registered services."""
        if hass.services.has_service(DOMAIN, SERVICE_GENERATE_CONTEXT):
            hass.services.async_remove(DOMAIN, SERVICE_GENERATE_CONTEXT)

    return remove_services


async def _async_register_frontend_menu_js(hass: HomeAssistant) -> None:
    """Expose and register frontend JS that injects menu action in HA views."""
    if hass.http is None:
        LOGGER.debug("HTTP component not available; skipping frontend menu injection.")
        return

    static_dir = Path(__file__).parent / "frontend"
    js_file = static_dir / "menu.js"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_MENU_JS_PATH,
                str(js_file),
                cache_headers=False,
            )
        ]
    )
    try:
        frontend.add_extra_js_url(hass, FRONTEND_MENU_JS_PATH)
    except Exception:  # pragma: no cover - depends on frontend runtime wiring
        LOGGER.debug("Frontend module injection could not be enabled.", exc_info=True)


def _normalize_domains(raw: Any) -> tuple[str, ...]:
    """Normalize domains input from service data."""
    items: list[str] = []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = [str(item) for item in raw]
    else:
        values = []

    for value in values:
        for token in value.split(","):
            domain = token.strip().lower()
            if domain:
                items.append(domain)
    return tuple(dict.fromkeys(items))
