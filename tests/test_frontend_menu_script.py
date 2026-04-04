from pathlib import Path
import re


def _load_menu_script() -> str:
    script_path = Path(__file__).resolve().parent.parent / "custom_components" / "hacs_ai_export" / "frontend" / "menu.js"
    return script_path.read_text(encoding="utf-8")


def test_more_info_menu_variant_detection_present():
    script = _load_menu_script()
    assert "const isLikelyMoreInfoMenu = (container) => {" in script
    assert 'text.includes("related")' in script
    assert 'text.includes("details")' in script
    assert 'text.includes("device info")' in script
    assert 'text.includes("service info")' in script
    assert (
        "if (!isInsideMoreInfoDialog(container) && !isLikelyMoreInfoMenu(container)) return;"
        in script
    )


def test_more_info_menu_click_uses_field_selection_dialog():
    script = _load_menu_script()
    assert "const MORE_INFO_ITEM_LABEL = \"Export entity for AI\";" in script
    assert "const selectedFields = await promptEntityFieldSelection();" in script
    assert "await callExportService(\"entity\", [entityId], selectedFields);" in script
    assert "closeMoreInfoDialog(container);" in script


def test_more_info_reinjection_hook_present():
    script = _load_menu_script()
    pattern = re.compile(
        r"window\.addEventListener\(\"hass-more-info\",\s*\(\)\s*=>\s*\{\s*scheduleInject\(\);\s*\}\);"
    )
    assert pattern.search(script)
