/* HACS AI Export menu injector.
 *
 * This is intentionally best-effort and targets HA config views.
 */
(() => {
  const DOMAIN = "hacs_ai_export";
  const SERVICE = "generate_context";
  const ITEM_ATTR = "data-hacs-ai-export-item";
  const ITEM_SEPARATOR_ATTR = "data-hacs-ai-export-separator";
  const ITEM_LABEL = "Export selected for AI";
  // mdi-content-copy
  const ITEM_ICON_PATH =
    "M19,21H8V7H19M19,3H8C6.89,3 6,3.89 6,5V7H5C3.89,7 3,7.89 3,9V21A2,2 0 0,0 5,23H16C17.11,23 18,22.11 18,21V19H19A2,2 0 0,0 21,17V5C21,3.89 20.11,3 19,3Z";

  const ENTITY_ID_RE = /^[a-z0-9_]+\.[a-z0-9_]+$/;
  const HEX32_RE = /^[a-f0-9]{32}$/i;
  const ULID_RE = /^[0-9A-HJKMNP-TV-Z]{26}$/i;
  const BULK_ACTION_MARKERS = [
    "enable selected",
    "disable selected",
    "hide selected",
    "unhide selected",
    "delete selected",
    "recreate entity ids of selected",
  ];

  const MENU_ITEM_TAGS = [
    "ha-dropdown-item",
    "ha-md-menu-item",
    "ha-list-item",
    "mwc-list-item",
  ];

  const collectRoots = () => {
    const roots = new Set([document]);
    const queue = [document.documentElement];
    while (queue.length) {
      const node = queue.pop();
      if (!node || !node.querySelectorAll) continue;
      const children = node.querySelectorAll("*");
      for (const child of children) {
        if (child.shadowRoot) {
          roots.add(child.shadowRoot);
          queue.push(child.shadowRoot);
        }
      }
    }
    return [...roots];
  };

  const queryAllDeep = (selector) => {
    const results = [];
    for (const root of collectRoots()) {
      results.push(...root.querySelectorAll(selector));
    }
    return results;
  };

  const notify = (message) => {
    const main = document
      .querySelector("home-assistant")
      ?.shadowRoot?.querySelector("home-assistant-main");
    if (main && typeof main.showToast === "function") {
      main.showToast(message);
      return;
    }
    const eventTarget = document.querySelector("home-assistant") || window;
    eventTarget.dispatchEvent(
      new CustomEvent("hass-notification", {
        detail: { message },
        bubbles: true,
        composed: true,
      }),
    );
  };

  const closeMenuForElement = (element) => {
    const dropdown = element?.closest?.("ha-dropdown");
    if (dropdown) {
      try {
        if (typeof dropdown.hide === "function") dropdown.hide();
      } catch (_err) {
        // ignore
      }
      try {
        if (typeof dropdown.close === "function") dropdown.close();
      } catch (_err) {
        // ignore
      }
      try {
        if ("open" in dropdown) dropdown.open = false;
      } catch (_err) {
        // ignore
      }
      dropdown.removeAttribute("open");
    }
  };

  const getHass = () => document.querySelector("home-assistant")?.hass;

  const getViewType = () => {
    const path = window.location.pathname;
    if (path.includes("/config/entities")) return "entity";
    if (path.includes("/config/devices")) return "device";
    if (path.includes("/config/areas")) return "area";
    return null;
  };

  const idMatches = (kind, value) => {
    if (!value || typeof value !== "string") return false;
    if (kind === "entity") return ENTITY_ID_RE.test(value);
    if (kind === "device" || kind === "area") {
      return ULID_RE.test(value) || HEX32_RE.test(value);
    }
    return false;
  };

  const getConfigHostsForKind = (kind) => {
    if (kind === "entity") {
      return queryAllDeep("ha-config-entities,ha-config-entities-dashboard");
    }
    if (kind === "device") {
      return queryAllDeep("ha-config-devices,ha-config-devices-dashboard");
    }
    if (kind === "area") {
      return queryAllDeep("ha-config-areas,ha-config-areas-dashboard");
    }
    return [];
  };

  const mapSelectedToRows = (selectedIds, table) => {
    if (!Array.isArray(selectedIds) || !table) return [];
    const rows = Array.isArray(table._filteredData)
      ? table._filteredData
      : Array.isArray(table.data)
        ? table.data
        : [];
    const idKey = typeof table.id === "string" && table.id ? table.id : "id";
    const selected = new Set(selectedIds.map((id) => String(id)));
    return rows.filter((row) => {
      if (!row || typeof row !== "object") return false;
      const rowId = row[idKey];
      return rowId != null && selected.has(String(rowId));
    });
  };

  const extractIdsFromRow = (kind, row, out) => {
    if (!row || typeof row !== "object") return;
    if (kind === "entity") {
      const candidates = [row.entity_id, row.entityId, row.id, row.entity?.entity_id];
      for (const candidate of candidates) {
        if (idMatches(kind, candidate)) out.add(candidate);
      }
      return;
    }
    if (kind === "device") {
      const candidates = [row.device_id, row.deviceId, row.id];
      for (const candidate of candidates) {
        if (idMatches(kind, candidate)) out.add(candidate);
      }
      return;
    }
    if (kind === "area") {
      const candidates = [row.area_id, row.areaId, row.id];
      for (const candidate of candidates) {
        if (idMatches(kind, candidate)) out.add(candidate);
      }
    }
  };

  const collectFromTableSelection = (kind, out) => {
    const hosts = getConfigHostsForKind(kind);
    for (const host of hosts) {
      const selected = Array.isArray(host?._selected) ? host._selected : [];
      const table = host?._dataTable;

      // If selected values are already direct IDs (rare but possible), use them.
      for (const selectedId of selected) {
        if (idMatches(kind, selectedId)) out.add(selectedId);
      }

      for (const row of mapSelectedToRows(selected, table)) {
        extractIdsFromRow(kind, row, out);
      }

      // Fallback to checked rows from the data table state.
      const checkedRows = Array.isArray(table?._checkedRows) ? table._checkedRows : [];
      for (const row of mapSelectedToRows(checkedRows, table)) {
        extractIdsFromRow(kind, row, out);
      }
    }
  };

  const extractIdsFromValue = (value, kind, out, seen, depth = 0) => {
    if (!value || depth > 4) return;
    if (typeof value === "string") {
      if (idMatches(kind, value)) out.add(value);
      return;
    }
    if (Array.isArray(value) || value instanceof Set) {
      for (const item of value) extractIdsFromValue(item, kind, out, seen, depth + 1);
      return;
    }
    if (typeof value !== "object") return;
    if (seen.has(value)) return;
    seen.add(value);

    const idKeys =
      kind === "entity"
        ? ["entity_id", "entityId", "id"]
        : kind === "device"
          ? ["device_id", "deviceId", "id"]
          : ["area_id", "areaId", "id"];

    for (const key of idKeys) {
      const candidate = value[key];
      if (typeof candidate === "string" && idMatches(kind, candidate)) out.add(candidate);
    }

    for (const [key, nestedValue] of Object.entries(value)) {
      const lowered = key.toLowerCase();
      if (
        lowered.includes("selected")
        || lowered.includes("selection")
        || lowered.endsWith("ids")
        || lowered.includes("items")
        || lowered.includes("rows")
      ) {
        extractIdsFromValue(nestedValue, kind, out, seen, depth + 1);
      }
    }
  };

  const collectFromRows = (kind, out) => {
    const rows = queryAllDeep(
      "[aria-selected='true'], tr[selected], ha-data-table-row[selected]",
    );
    const attrNames = [
      "data-row-id",
      "data-id",
      "data-entity-id",
      "data-device-id",
      "data-area-id",
      "entity-id",
      "device-id",
      "area-id",
      "row-id",
      "id",
    ];
    for (const row of rows) {
      for (const attrName of attrNames) {
        const value = row.getAttribute(attrName);
        if (idMatches(kind, value)) out.add(value);
      }
      for (const value of Object.values(row.dataset || {})) {
        if (idMatches(kind, value)) out.add(value);
      }
      const text = row.textContent || "";
      const tokens = text.split(/\s+/);
      for (const token of tokens) {
        const candidate = token.trim();
        if (idMatches(kind, candidate)) out.add(candidate);
      }
    }
  };

  const collectSelectedIds = (kind) => {
    const ids = new Set();
    collectFromTableSelection(kind, ids);

    const seen = new WeakSet();
    const hosts = queryAllDeep(
      "ha-config-entities,ha-config-entities-dashboard,"
        + "ha-config-devices,ha-config-devices-dashboard,"
        + "ha-config-areas,ha-config-areas-dashboard,ha-panel-config",
    );

    for (const host of hosts) {
      extractIdsFromValue(host, kind, ids, seen);
    }
    collectFromRows(kind, ids);
    return [...ids];
  };

  const callExportService = async (kind, ids) => {
    const hass = getHass();
    if (!hass) {
      notify("Home Assistant context is not available.");
      return;
    }
    if (!ids.length) {
      notify("No selected rows detected.");
      return;
    }

    const serviceData = {
      sections: [
        "devices",
        "entities",
        "entity_attributes",
        "services",
        "possible_values",
      ],
      create_notification: true,
      output_format: "yaml",
    };
    if (kind === "entity") serviceData.entity_id = ids;
    if (kind === "device") serviceData.device_ids = ids;
    if (kind === "area") serviceData.area_ids = ids;

    try {
      // Use websocket call_service with return_response when possible.
      const result = await hass.connection.sendMessagePromise({
        type: "call_service",
        domain: DOMAIN,
        service: SERVICE,
        service_data: serviceData,
        return_response: true,
      });
      const response = result?.response || result?.result?.response;
      const text = response?.text;
      if (text) {
        if (navigator.clipboard?.writeText) {
          try {
            await navigator.clipboard.writeText(text);
            notify("AI context copied to clipboard.");
            return;
          } catch (_err) {
            notify("Generated context, but clipboard access was blocked.");
            return;
          }
        }
        notify("Generated context, but clipboard is unavailable.");
        return;
      }
      notify("Generated context, but no text was returned.");
      return;
    } catch (_err) {
      // Fall back to classic service call without response body.
      await hass.callService(DOMAIN, SERVICE, serviceData);
      notify("Started context export. Open Notifications to copy the result.");
    }
  };

  const createMenuIcon = (slotName) => {
    const icon = document.createElement("ha-svg-icon");
    if (slotName) icon.slot = slotName;
    icon.setAttribute("path", ITEM_ICON_PATH);
    return icon;
  };

  const createSeparator = () => {
    const separator = document.createElement("wa-divider");
    separator.setAttribute("role", "separator");
    separator.setAttribute("orientation", "horizontal");
    separator.setAttribute(ITEM_SEPARATOR_ATTR, "1");
    return separator;
  };

  const createActionMenuItem = (container) => {
    const preferredTag = container?.querySelector?.(MENU_ITEM_TAGS.join(","))
      ?.tagName?.toLowerCase();

    if (preferredTag === "ha-dropdown-item" || (!preferredTag && customElements.get("ha-dropdown-item"))) {
      const item = document.createElement("ha-dropdown-item");
      item.setAttribute(ITEM_ATTR, "1");
      item.setAttribute("value", "hacs_ai_export_copy_context");
      item.setAttribute("variant", "default");
      item.setAttribute("size", "medium");
      item.setAttribute("type", "normal");
      item.appendChild(createMenuIcon("icon"));
      item.appendChild(document.createTextNode(ITEM_LABEL));
      return item;
    }

    if (
      (preferredTag === "ha-md-menu-item" || (!preferredTag && customElements.get("ha-md-menu-item")))
    ) {
      const item = document.createElement("ha-md-menu-item");
      item.setAttribute(ITEM_ATTR, "1");
      item.appendChild(createMenuIcon("start"));
      const headline = document.createElement("div");
      headline.slot = "headline";
      headline.textContent = ITEM_LABEL;
      item.appendChild(headline);
      return item;
    }

    if (
      preferredTag === "ha-list-item"
      || (!preferredTag && customElements.get("ha-list-item"))
    ) {
      const item = document.createElement("ha-list-item");
      item.setAttribute(ITEM_ATTR, "1");
      item.appendChild(createMenuIcon("start"));
      item.appendChild(document.createTextNode(ITEM_LABEL));
      return item;
    }

    if (
      preferredTag === "mwc-list-item"
      || (!preferredTag && customElements.get("mwc-list-item"))
    ) {
      const item = document.createElement("mwc-list-item");
      item.setAttribute(ITEM_ATTR, "1");
      item.textContent = ITEM_LABEL;
      return item;
    }

    const fallback = document.createElement("button");
    fallback.type = "button";
    fallback.setAttribute(ITEM_ATTR, "1");
    fallback.textContent = ITEM_LABEL;
    fallback.style.padding = "10px 16px";
    fallback.style.textAlign = "left";
    fallback.style.width = "100%";
    fallback.style.border = "none";
    fallback.style.background = "transparent";
    fallback.style.color = "var(--primary-text-color)";
    fallback.style.cursor = "pointer";
    return fallback;
  };

  const isInTableRow = (element) =>
    Boolean(
      element?.closest(
        "tr,[role='row'],ha-data-table-row,.mdc-data-table__row,.MuiDataGrid-row",
      ),
    );

  const hasMenuItems = (element) =>
    element?.querySelector?.(MENU_ITEM_TAGS.join(",")) != null;

  const getMenuTexts = (container) =>
    Array.from(container.querySelectorAll(MENU_ITEM_TAGS.join(",")))
      .map((item) => (item.textContent || "").trim().toLowerCase())
      .filter(Boolean);

  const isLikelyBulkActionMenu = (container) => {
    const texts = getMenuTexts(container);
    if (!texts.length) return false;
    return texts.some((text) =>
      BULK_ACTION_MARKERS.some((marker) => text.includes(marker)),
    );
  };

  const findMenuContainer = (element) =>
    element.closest(
      "ha-dropdown,ha-button-menu,[role='menu'],ha-md-menu,mwc-menu,mwc-list,.mdc-list",
    )
    || element.parentElement;

  const ensureMenuAction = (container) => {
    if (!container || container.querySelector(`[${ITEM_ATTR}]`)) return;
    const item = createActionMenuItem(container);
    item.addEventListener("click", async (event) => {
      event.preventDefault();
      const kind = getViewType();
      if (!kind) {
        notify("This action is only available in Entities/Devices/Areas views.");
        closeMenuForElement(item);
        return;
      }
      closeMenuForElement(item);
      const ids = collectSelectedIds(kind);
      await callExportService(kind, ids);
    });

    // Keep this action visually separated from the destructive Delete action.
    const deleteItem = Array.from(container.querySelectorAll(MENU_ITEM_TAGS.join(",")))
      .find((menuItem) =>
        (menuItem.textContent || "").trim().toLowerCase().includes("delete selected"),
      );

    if (deleteItem) {
      const prev = deleteItem.previousElementSibling;
      const prevIsDivider = prev?.tagName?.toLowerCase?.() === "wa-divider";

      if (prevIsDivider) {
        container.insertBefore(item, prev);
      } else {
        container.insertBefore(item, deleteItem);
        container.insertBefore(createSeparator(), deleteItem);
      }
      return;
    }

    container.appendChild(item);
  };

  const collectTargets = () => {
    const targets = new Set();
    const kind = getViewType();
    if (!kind) return targets;

    for (const host of queryAllDeep("ha-button-menu")) {
      if (isInTableRow(host) || !hasMenuItems(host) || !isLikelyBulkActionMenu(host)) {
        continue;
      }
      targets.add(host);
    }

    for (const container of queryAllDeep(
      "ha-dropdown,[role='menu'],ha-md-menu,mwc-menu,mwc-list,.mdc-list",
    )) {
      if (
        isInTableRow(container)
        || !hasMenuItems(container)
        || !isLikelyBulkActionMenu(container)
      ) {
        continue;
      }
      targets.add(container);
    }

    for (const item of queryAllDeep(MENU_ITEM_TAGS.join(","))) {
      const container = findMenuContainer(item);
      if (
        !container
        || isInTableRow(container)
        || !hasMenuItems(container)
        || !isLikelyBulkActionMenu(container)
      ) {
        continue;
      }
      targets.add(container);
    }

    return targets;
  };

  const injectMenuItem = () => {
    for (const container of collectTargets()) {
      ensureMenuAction(container);
    }
  };

  const scheduleInject = () => {
    setTimeout(injectMenuItem, 0);
    setTimeout(injectMenuItem, 120);
    setTimeout(injectMenuItem, 320);
  };

  const start = () => {
    injectMenuItem();
    // Inject when users open menus/navigation changes, avoiding continuous
    // mutation of Lit-managed DOM trees.
    window.addEventListener("click", () => {
      scheduleInject();
    }, true);
    window.addEventListener("location-changed", () => {
      scheduleInject();
    });
  };

  if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
