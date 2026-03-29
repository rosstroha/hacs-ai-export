# HACS AI Export

`hacs_ai_export` is a Home Assistant custom integration for exporting your HA setup
into AI-friendly context text.

It is designed for users who want to build automations with AI tools without
manually typing device/entity/service details.

## What it exports

You can select one or more sections per export:

- Devices
- Entities
- Entity attributes
- Services
- Actions (service-call style actions)
- Possible entity values/states (when discoverable from attributes)

The export includes filtering options for entities, devices, areas, and domains.

## Installation

### HACS (Custom Repository)

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository.
3. Install **HACS AI Export**.
4. Restart Home Assistant.
5. Add the integration from **Settings -> Devices & Services -> Add Integration**.

### Manual

Copy `custom_components/hacs_ai_export` into your HA config directory under
`custom_components/`, then restart Home Assistant and add the integration.

## Usage

Use the service:

- `hacs_ai_export.generate_context`

From **Developer Tools -> Actions**, you get menu selectors for:

- `sections` (multi-select)
- `entity_id` (multi-select)
- `device_ids` (multi-select)
- `area_ids` (multi-select)
- `label_ids` (multi-select)
- `domains` (optional text filter)

Optional controls:

- Include disabled entities
- Output format (`markdown` or `json`)
- Safety limits (`max_entities`, `max_services`)
- Persistent notification after generation

The service response includes:

- `text`: Copy-ready AI context
- `payload`: Structured object
- `summary`: Counts and section list

## Example prompt flow

1. Call `hacs_ai_export.generate_context`.
2. Copy `text` from the service response.
3. Paste into an AI chat with a request like:
   "Create a Home Assistant automation YAML using only these entities/services."

## Using Entity/Device/Area Views

If you select rows in Home Assistant's Entity/Device/Area views, you can use labels
to drive exports:

1. Select rows in the view.
2. Use **Add label** (like your screenshot flow).
3. Call `hacs_ai_export.generate_context` with `label_ids` set to that label.
4. Copy the returned `text`.

The integration also injects an upper-right bulk action menu item in these views:

- `Export selected for AI`

This action exports currently selected rows and attempts to copy the AI context to
your clipboard automatically.
