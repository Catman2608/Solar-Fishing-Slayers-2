const APP_VERSION = "2026.11.1";
const BETA_VERSION = "0";
const DEVELOPER = "Catman2608";

// Expose for Python version check via evaluate_js
window.APP_VERSION = APP_VERSION;
window.BETA_VERSION = BETA_VERSION;
window.DEVELOPER = DEVELOPER;

const validHexColor = /^#([0-9A-F]{3}|[0-9A-F]{6})$/i;

let applyingSettings = false;

window.addEventListener("pywebviewready", async () => {
    // Initialize controls before loading so config values and their previews
    // are applied once, in a deterministic order.
    if (document.readyState === "loading") {
        await new Promise((resolve) => {
            document.addEventListener("DOMContentLoaded", resolve, { once: true });
        });
    }
    // Load the editable settings file after the UI controls are ready.
    await loadStartupSettings();
});

document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
        selectTab(button.dataset.tab);
    });
});

function _pyApi() {
    return window.pywebview && window.pywebview.api ? window.pywebview.api : null;
}

/**
 * Get the Python backend's app version, beta version, developer name.
 * Calls the Api.get_python_version_info method exposed by pywebview.
 * @returns {Promise<{app_version: any, beta_version: any, developer: string|null, error?: string}>}
 */
async function getPythonVersionInfo() {
    const api = _pyApi();
    if (!api || typeof api.get_python_version_info !== "function") {
        return {
            app_version: null,
            beta_version: null,
            developer: null,
            error: "Python API not available"
        };
    }
    try {
        const info = await api.get_python_version_info();
        if (info && typeof info === "object") {
            return {
                app_version: info.app_version ?? null,
                beta_version: info.beta_version ?? null,
                developer: info.developer ?? null,
            };
        }
        return {
            app_version: null,
            beta_version: null,
            developer: null,
            error: "Unexpected response from Python"
        };
    } catch (e) {
        return {
            app_version: null,
            beta_version: null,
            developer: null,
            error: String(e)
        };
    }
}

// Expose for any callers that need it
window.getPythonVersionInfo = getPythonVersionInfo;


async function detectRoblox() {
    const api = _pyApi();
    if (!api || typeof api.detect_roblox !== "function") {
        setStatus("Detect Roblox not available");
        return;
    }
    try {
        const info = await api.detect_roblox();
        if (info && typeof info.left !== "undefined") {
            setStatus(`Roblox: left=${info.left}, top=${info.top}, width=${info.width}, height=${info.height}`);
        }
    } catch (e) {
        setStatus("Error detecting Roblox window");
        console.error(e);
    }
}

async function closeWindow() {
    const api = _pyApi();
    if (!api || typeof api.close_window !== "function") {
        return;
    }
    await api.close_window();
}

async function minimizeWindow() {
    const api = _pyApi();
    if (!api || typeof api.minimize_window !== "function") {
        return;
    }
    await api.minimize_window();
}

async function rebindHotkeys(key) {
    const api = _pyApi();
    if (!api || typeof api.rebind_hotkeys !== "function") {
        return;
    }
    await api.rebind_hotkeys(key);
}

function applyHotkey(key, value) {
    const input = document.getElementById(key);
    const button = document.getElementById(key + "_btn");
    if (!input || !button) {
        return;
    }

    input.value = String(value);
    button.textContent = String(value).toUpperCase();
}

window.applyHotkey = applyHotkey;

function syncHotkeyButtons() {
    ["start_key", "area_selector_key", "stop_key"].forEach((key) => {
        const input = document.getElementById(key);
        if (input) {
            applyHotkey(key, input.value);
        }
    });
}

function setStatus(message) {
    const status = document.getElementById("status_label");

    if (!status) {
        return;
    }

    status.textContent = message;
}

function isRangeControl(element) {
    return Boolean(element) && (element.type === "range" || element.classList.contains("range-input"));
}

function syncSliderFromText(slider) {
    if (!slider) {
        return;
    }
    const textInput = document.getElementById(slider.dataset.target || "");
    if (!textInput) {
        return;
    }
    const value = parseFloat(textInput.value);
    if (Number.isNaN(value)) {
        return;
    }
    const min = parseFloat(slider.min);
    const max = parseFloat(slider.max);
    const clamped = Math.min(Math.max(value, min), max);
    slider.value = clamped;
}

function syncAllSliders() {
    document.querySelectorAll(".range-input").forEach(syncSliderFromText);
}

function setupSliders() {
    document.querySelectorAll(".range-input").forEach((slider) => {
        const targetId = slider.dataset.target;
        const textInput = document.getElementById(targetId);

        if (!textInput) {
            return;
        }

        // Slider → text
        slider.addEventListener("input", () => {
            textInput.value = slider.value;
        });

        // Text → slider
        textInput.addEventListener("input", () => {
            syncSliderFromText(slider);
        });

        syncSliderFromText(slider);
    });
}

function collectSettings() {
    const settings = {};

    document.querySelectorAll(
        "input[id], select[id], textarea[id]"
    ).forEach((element) => {
        if (!element.id || element.id.startsWith("_") || element.id.endsWith("_slider")) {
            return;
        }
        if (isRangeControl(element)) {
            return;
        }
        if (element.type === "checkbox") {
            settings[element.id] = element.checked;
        } else {
            settings[element.id] = element.value;
        }
    });

    return settings;
}

function isBlankSetting(value) {
    return value === undefined || value === null || (typeof value === "string" && value.trim() === "");
}

function settingIsChecked(value) {
    if (typeof value === "string") {
        return ["on", "true", "1", "yes"].includes(value.trim().toLowerCase());
    }
    return value === true || value === 1;
}

function fieldDefault(element) {
    if (!element) {
        return null;
    }
    if (element.type === "checkbox") {
        return Boolean(element.defaultChecked);
    }
    if (element.tagName === "SELECT") {
        const selected = element.querySelector("option[selected]");
        if (selected) {
            return selected.value;
        }
        if (element.options && element.options.length) {
            return element.options[0].value;
        }
        return "";
    }
    if (element.defaultValue !== undefined && String(element.defaultValue).trim() !== "") {
        return element.defaultValue;
    }
    if (element.placeholder && String(element.placeholder).trim() !== "") {
        return element.placeholder;
    }
    return null;
}

function fillBlankSettings(settings) {
    const filled = {};
    if (settings && typeof settings === "object") {
        Object.entries(settings).forEach(([key, value]) => {
            if (!key || key.startsWith("_") || key === "global_settings") {
                return;
            }
            if (isBlankSetting(value)) {
                return;
            }
            filled[key] = value;
        });
    }

    document.querySelectorAll("input[id], select[id], textarea[id]").forEach((element) => {
        const id = element.id;
        if (!id || id.startsWith("_") || id.endsWith("_slider") || isRangeControl(element)) {
            return;
        }
        if (!isBlankSetting(filled[id])) {
            return;
        }
        const fallback = fieldDefault(element);
        if (fallback === null || fallback === undefined) {
            return;
        }
        filled[id] = fallback;
    });

    return filled;
}

function collectSettingsData() {
    return fillBlankSettings(collectSettings());
}

async function saveSettings() {
    const api = _pyApi();
    if (!api || typeof api.save_settings !== "function") {
        setStatus("Settings save is unavailable");
        return false;
    }

    try {
        const result = await api.save_settings(collectSettingsData());
        if (result && result.success === false) {
            throw new Error(result.error || "Unable to save settings");
        }
        setStatus("Settings saved");
        return true;
    } catch (error) {
        console.error(error);
        setStatus("Error saving settings: " + error);
        return false;
    }
}

function resetFieldsToDefaults() {
    document.querySelectorAll("input[id], select[id], textarea[id]").forEach((element) => {
        if (!element.id || element.id.startsWith("_") || element.id.endsWith("_slider") || isRangeControl(element)) {
            return;
        }
        const fallback = fieldDefault(element);
        if (element.type === "checkbox") {
            element.checked = Boolean(fallback);
        } else if (fallback !== null && fallback !== undefined) {
            element.value = fallback;
        } else {
            element.value = "";
        }
        if (element.dataset.slider) {
            const slider = document.getElementById(element.dataset.slider);
            if (slider) {
                slider.value = element.value;
            }
        }
    });
}

function applySettings(settings, replace) {
    if (!settings || typeof settings !== "object") {
        return;
    }

    if (replace) {
        resetFieldsToDefaults();
    }

    Object.entries(settings).forEach(([id, value]) => {
        try {
            if (!id || id === "global_settings" || id.startsWith("_") || id.endsWith("_slider")) {
                return;
            }
            if (isBlankSetting(value)) {
                return;
            }

            const element = document.getElementById(id);

            if (!element || isRangeControl(element)) {
                return;
            }

            if (element.type === "checkbox") {
                element.checked = settingIsChecked(value);
            } else {
                element.value = value;
            }
        } catch (error) {
            // Skip a single setting that fails to load.
        }
    });

    syncAllSliders();

    applyingSettings = true;
    try {
        document.querySelectorAll("input[id], select[id], textarea[id]").forEach((element) => {
            if (!element.id || element.id.startsWith("_")) {
                return;
            }
            element.dispatchEvent(new Event("change", { bubbles: true }));
        });
    } finally {
        applyingSettings = false;
    }

    syncHotkeyButtons();
    updateColorPreviews();
    updateAccentColor();
    if (typeof updateOtherAutomation === "function") updateOtherAutomation();
    if (typeof updateFriendAreaVisibility === "function") updateFriendAreaVisibility();
    if (typeof syncModeTabs === "function") {
        syncModeTabs(activeSidebarTab());
    }
}

let loadingSettings = false;

async function loadStartupSettings() {
    await loadSettings();
}

function unwrapSettings(loaded) {
    if (!loaded || typeof loaded !== "object") {
        return {};
    }
    if (loaded.settings && typeof loaded.settings === "object" && !Array.isArray(loaded.settings)) {
        return loaded.settings;
    }
    const copy = {};
    Object.entries(loaded).forEach(([key, value]) => {
        if (!key || key.startsWith("_") || key === "global_settings" || key === "success" || key === "settings" || key === "config_name") {
            return;
        }
        copy[key] = value;
    });
    return copy;
}

function paintColorInput(input, raw) {
    if (!input) {
        return;
    }
    // Only force the value when explicitly loading a config / setting a raw value.
    // Never rewrite the value on keystrokes so the user can freely delete and retype.
    if (raw !== undefined && raw !== null && String(raw).trim() !== "") {
        input.value = String(raw).trim();
    }
    const value = normalizeHexColor(input.value);
    if (!value) {
        // Invalid or incomplete hex — clear colored styles so text stays readable while editing.
        input.style.removeProperty("background");
        input.style.removeProperty("background-color");
        input.style.removeProperty("color");
        input.style.removeProperty("border");
        return;
    }
    // Apply preview styles only. Do not touch input.value (keeps 3-digit hex as typed).
    input.style.setProperty("background", value, "important");
    input.style.setProperty("background-color", value, "important");
    input.style.color = hexBrightness(value) > 170 ? "#111827" : "#ffffff";
    input.style.border = "none";
}

function paintConfigColors(settings) {
    document.querySelectorAll("input.color-stripe, input[id$='_color']").forEach((input) => {
        const raw = settings && Object.prototype.hasOwnProperty.call(settings, input.id) ? settings[input.id] : undefined;
        paintColorInput(input, raw);
    });
}

const FISHING_TABS = ["cast", "shake", "minigame"];
const OTHER_TAB = "other_automation";

function selectTab(tabId) {
    document.querySelectorAll(".tab-button").forEach((btn) => {
        btn.classList.remove("active");
    });
    document.querySelectorAll(".tab-content").forEach((tab) => {
        tab.classList.remove("active");
    });

    const button = document.querySelector('.tab-button[data-tab="' + tabId + '"]');
    const selectedTab = document.getElementById(tabId);
    if (button) {
        button.classList.add("active");
    }
    if (selectedTab) {
        selectedTab.classList.add("active");
    }
}

function activeSidebarTab() {
    const active = document.querySelector(".tab-button.active");
    return active && active.dataset.tab ? active.dataset.tab : "main";
}

function syncModeTabs(activeTab) {
    FISHING_TABS.forEach((tabId) => {
        const button = document.querySelector('.tab-button[data-tab="' + tabId + '"]');
        if (button) button.hidden = false;
    });
    const AutomationButton = document.querySelector('.tab-button[data-tab="' + OTHER_TAB + '"]');
    if (AutomationButton) AutomationButton.hidden = false;

    selectTab(activeTab || activeSidebarTab());
}

syncModeTabs(activeSidebarTab());

async function loadSettings() {
    if (loadingSettings) {
        return;
    }

    loadingSettings = true;
    const api = _pyApi();

    try {
        if (!api || typeof api.load_settings !== "function") {
            throw new Error("Settings loading is unavailable");
        }

        const loaded = await api.load_settings();
        if (!loaded || typeof loaded !== "object") {
            throw new Error("Unexpected response while loading settings");
        }
        if (loaded.success === false) {
            throw new Error(loaded.error || "Unable to load settings");
        }
        const applied = unwrapSettings(loaded);

        ensureAllColorGroups(applied);
        applySettings(fillBlankSettings(applied), true);
        paintConfigColors(applied);
        setStatus("Settings loaded");
    } catch (error) {
        console.error(error);
        setStatus("Error loading settings: " + error);
    } finally {
        loadingSettings = false;
    }
}

function updateFriendAreaVisibility() {
    const detection = (document.getElementById("detection_method") || {}).value || "friend_area";
    const restart = (document.getElementById("restart_method") || {}).value || "friend_area";
    const needsFriend = detection === "friend_area" || restart === "friend_area";
    const container = document.getElementById("friends-colors-container");
    if (container) container.hidden = !needsFriend;
    // Also hide the count input's parent section if needed, but container is enough
}

function updateOtherAutomation() {
    const panels = [
        "auto-appraisal-panel",
        "auto-treasure-appraisal-panel",
        "auto-enchant-panel",
        "auto-angler-panel",
    ];
    panels.forEach((id) => {
        const panel = document.getElementById(id);
        if (panel) panel.hidden = false;
    });
}

document.addEventListener("DOMContentLoaded", () => {
    setupSliders();
    bindColorPreviewInputs();
    initColorGroups();
    applySettings(fillBlankSettings({}));
    updateAccentColor();
    updateOtherAutomation();
    updateFriendAreaVisibility();

});

async function testLogging() {
    await pywebview.api.test_logging();
}

function normalizeHexColor(hex) {
    hex = String(hex || "").trim();
    if (/^[0-9A-F]{6}$/i.test(hex)) {
        hex = "#" + hex;
    }
    if (!validHexColor.test(hex)) {
        return "";
    }
    if (hex.length === 4) {
        hex = "#" + hex
            .slice(1)
            .split("")
            .map(char => char + char)
            .join("");
    }
    return hex;
}

function updateColorPreview(input) {
    paintColorInput(input);
}

function resetColor(id) {
    const input = document.getElementById(id);
    if (!input) {
        return;
    }
    input.value = input.placeholder || "";
    updateColorPreview(input);
    updateAccentColor();
}

async function pickColor(id) {
    const api = _pyApi();
    if (api && typeof api.start_eyedropper === "function") {
        try {
            await api.start_eyedropper(id);
            return;
        } catch (error) {
            // Fall through to the browser picker.
        }
    }
    const picker = document.createElement("input");
    picker.type = "color";
    const current = document.getElementById(id);
    const hex = normalizeHexColor(current && (current.value || current.placeholder));
    if (hex) {
        picker.value = hex;
    }
    picker.addEventListener("input", () => {
        if (!current) {
            return;
        }
        current.value = picker.value.toUpperCase();
        updateColorPreview(current);
        updateAccentColor();
    });
    picker.click();
}

const COLOR_GROUPS = {
    bar: {
        label: "Bar",
        baseColorId: "bar_color",
        baseTolId: "bar_tolerance",
        containerId: "bar-colors-container",
        countId: "bar_color_count",
        defaultColor: "#F1F1F1",
        defaultTolerance: "8"
    },
    arrow: {
        label: "Arrow",
        baseColorId: "arrow_color",
        baseTolId: "arrow_tolerance",
        containerId: "arrow-colors-container",
        countId: "arrow_color_count",
        defaultColor: "#848587",
        defaultTolerance: "8"
    },
    fish: {
        label: "Fish",
        baseColorId: "fish_color",
        baseTolId: "fish_tolerance",
        containerId: "fish-colors-container",
        countId: "fish_color_count",
        defaultColor: "#434B5B",
        defaultTolerance: "4"
    },
    friends: {
        label: "Friend Area",
        baseColorId: "friends_color",
        baseTolId: "friends_tolerance",
        containerId: "friends-colors-container",
        countId: "friends_color_count",
        defaultColor: "#9BFF9B",
        defaultTolerance: "4"
    },
    green_cast: {
        label: "Green Cast",
        baseColorId: "green_cast_color",
        baseTolId: "green_cast_tolerance",
        containerId: "green_cast-colors-container",
        countId: "green_cast_color_count",
        defaultColor: "#64a04c",
        defaultTolerance: "16"
    },
    white_cast: {
        label: "White Cast",
        baseColorId: "white_cast_color",
        baseTolId: "white_cast_tolerance",
        containerId: "white_cast-colors-container",
        countId: "white_cast_color_count",
        defaultColor: "#d4d3ca",
        defaultTolerance: "20"
    },
    shake: {
        label: "Shake",
        baseColorId: "shake_color",
        baseTolId: "shake_tolerance",
        containerId: "shake-colors-container",
        countId: "shake_color_count",
        defaultColor: "#FFFFFF",
        defaultTolerance: "5"
    },
    sovereign_recharge: {
        label: "Sovereign Recharge",
        baseColorId: "sovereign_recharge_color",
        baseTolId: "sovereign_recharge_tolerance",
        containerId: "sovereign_recharge-colors-container",
        countId: "sovereign_recharge_color_count",
        defaultColor: "#d994ff",
        defaultTolerance: "5"
    }
};

function getColorGroupById(id) {
    if (!id) return null;
    for (const key of Object.keys(COLOR_GROUPS)) {
        const group = COLOR_GROUPS[key];
        if (id === group.baseColorId || id.startsWith(group.baseColorId + "_")) {
            return { key, group };
        }
    }
    return null;
}

function getColorId(group, index) {
    return index === 1 ? group.baseColorId : `${group.baseColorId}_${index}`;
}

function getTolId(group, index) {
    return index === 1 ? group.baseTolId : `${group.baseTolId}_${index}`;
}

async function addColor(id) {
    const found = getColorGroupById(id);
    if (!found) return;
    const { group } = found;
    const container = document.getElementById(group.containerId);
    if (!container) return;

    const currentCount = container.querySelectorAll(".color-option").length;
    const newIndex = currentCount + 1;
    const newOption = createColorOption(group, newIndex);
    container.appendChild(newOption);
    updateColorCount(group);
    updateColorButtons(group);
    bindColorPreviewInputs();
    updateColorPreviews();
}

async function removeColor(id) {
    const found = getColorGroupById(id);
    if (!found) return;
    const { group } = found;
    const container = document.getElementById(group.containerId);
    if (!container) return;

    const options = container.querySelectorAll(".color-option");
    if (options.length <= 1) {
        return;
    }

    const input = document.getElementById(id);
    if (!input) return;
    const option = input.closest(".color-option");
    if (option) {
        option.remove();
    }

    reindexColors(group);
    updateColorCount(group);
    updateColorButtons(group);
    bindColorPreviewInputs();
    updateColorPreviews();
}

function createColorOption(group, index) {
    const div = document.createElement("div");
    div.className = "color-option";
    div.dataset.index = index;

    const colorId = getColorId(group, index);
    const tolId = getTolId(group, index);

    div.innerHTML = `
        <p>${group.label}</p>
        <input id="${colorId}" class="color-stripe" type="text" placeholder="${group.defaultColor}" spellcheck="false">
        <p>Tolerance</p>
        <input id="${tolId}" class="tolerance-input" type="number" placeholder="${group.defaultTolerance}">
        <button class="color-icon-btn" type="button" onclick="pickColor('${colorId}')" title="Pick color" aria-label="Pick color">
            <svg class="icon" aria-hidden="true"><use href="#i-picker"></use></svg>
        </button>
        <button class="color-icon-btn" type="button" onclick="resetColor('${colorId}')" title="Reset color" aria-label="Reset color">
            <svg class="icon" aria-hidden="true"><use href="#i-reset"></use></svg>
        </button>
        <button class="color-icon-btn add-color-btn" type="button" onclick="addColor('${colorId}')" title="Add color" aria-label="Add color" style="display: none;">
            <svg class="icon" aria-hidden="true"><use href="#i-add"></use></svg>
        </button>
        <button class="color-icon-btn remove-color-btn" type="button" onclick="removeColor('${colorId}')" title="Remove color" aria-label="Remove color">
            <svg class="icon" aria-hidden="true"><use href="#i-close"></use></svg>
        </button>
    `;
    return div;
}

function reindexColors(group) {
    const container = document.getElementById(group.containerId);
    if (!container) return;
    const options = Array.from(container.querySelectorAll(".color-option"));
    options.forEach((option, i) => {
        const index = i + 1;
        option.dataset.index = index;
        const colorInput = option.querySelector(".color-stripe");
        const tolInput = option.querySelector(".tolerance-input");
        const buttons = option.querySelectorAll(".color-icon-btn");

        const colorId = getColorId(group, index);
        const tolId = getTolId(group, index);

        if (colorInput) {
            colorInput.id = colorId;
        }
        if (tolInput) {
            tolInput.id = tolId;
        }

        if (buttons.length >= 4) {
            buttons[0].setAttribute("onclick", `pickColor('${colorId}')`);
            buttons[1].setAttribute("onclick", `resetColor('${colorId}')`);
            buttons[2].setAttribute("onclick", `addColor('${colorId}')`);
            buttons[3].setAttribute("onclick", `removeColor('${colorId}')`);
        }
    });
}

function updateColorCount(group) {
    const container = document.getElementById(group.containerId);
    const countInput = document.getElementById(group.countId);
    if (container && countInput) {
        const count = container.querySelectorAll(".color-option").length;
        countInput.value = String(count);
    }
}

function updateColorButtons(group) {
    const container = document.getElementById(group.containerId);
    if (!container) return;
    const options = container.querySelectorAll(".color-option");
    const single = options.length <= 1;
    options.forEach((option, i) => {
        const addBtn = option.querySelector(".add-color-btn");
        if (addBtn) {
            addBtn.style.display = (i === options.length - 1) ? "" : "none";
        }
        // Hide delete when there is only one color — it does nothing.
        const removeBtn = option.querySelector(".remove-color-btn")
            || option.querySelector("button[onclick^='removeColor']");
        if (removeBtn) {
            removeBtn.style.display = single ? "none" : "";
        }
    });
}

function ensureColorGroup(group, count) {
    const container = document.getElementById(group.containerId);
    if (!container) return;
    count = Math.max(1, parseInt(count, 10) || 1);
    container.innerHTML = "";
    for (let i = 1; i <= count; i++) {
        container.appendChild(createColorOption(group, i));
    }
    updateColorCount(group);
    updateColorButtons(group);
    bindColorPreviewInputs();
}

function ensureAllColorGroups(settings) {
    Object.values(COLOR_GROUPS).forEach((group) => {
        const count = settings && settings[group.countId];
        ensureColorGroup(group, count);
    });
}

function initColorGroups() {
    Object.values(COLOR_GROUPS).forEach((group) => {
        updateColorButtons(group);
    });
}

function getColorPreviewInputs() {
    return document.querySelectorAll("input.color-stripe, input[id$='_color']");
}

function updateColorPreviews() {
    getColorPreviewInputs().forEach(updateColorPreview);
}

function bindColorPreviewInputs() {
    getColorPreviewInputs().forEach(input => {
        if (input.dataset.colorPreviewBound === "true") {
            return;
        }
        input.dataset.colorPreviewBound = "true";
        // Intentionally no "input" listener — live updates interfere with backspace + retyping.
        // Preview + accent update only after the user finishes editing (change fires on blur).
        input.addEventListener("change", () => {
            updateColorPreview(input);
            if (!applyingSettings) updateAccentColor();
        });
        updateColorPreview(input);
    });
}

function hexBrightness(hex) {
    hex = normalizeHexColor(hex);
    if (!hex) {
        return 0;
    }
    const r = parseInt(hex.substr(1,2), 16);
    const g = parseInt(hex.substr(3,2), 16);
    const b = parseInt(hex.substr(5,2), 16);
    return (
        0.2126 * r +
        0.7152 * g +
        0.0722 * b
    );
}

function updateAccentColor() {
    // Sample from bar color inputs: bar_color, bar_color_2, bar_color_3, ...
    // Falls back to fish_color then arrow_color if no valid bar colors exist.
    const barColors = [];
    const first = document.getElementById("bar_color");
    if (first) barColors.push(first);
    
    // Find any additional bar color inputs (bar_color_2, bar_color_3, ...)
    let i = 2;
    while (true) {
        const el = document.getElementById(`bar_color_${i}`);
        if (!el) break;
        barColors.push(el);
        i++;
    }

    const getVal = (el) => el ? (el.value || el.placeholder || "").trim() : "";
    const fishElement = document.getElementById("fish_color");
    const arrowElement = document.getElementById("arrow_color");

    const normalizedBar = barColors
        .map(el => normalizeHexColor(getVal(el)))
        .filter(Boolean);
    const normalizedFish = normalizeHexColor(getVal(fishElement));
    const normalizedArrow = normalizeHexColor(getVal(arrowElement));

    // Helper: is a color too neutral (white/gray/black)?
    function isTooNeutral(hex) {
        if (!hex) return true;
        const brightness = hexBrightness(hex);
        const { r, g, b } = hexToRgb(hex);
        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        const isGray = (max - min) < 30;
        const isWhite = brightness > 235;
        const isBlack = brightness < 15;
        return isWhite || isBlack || isGray;
    }

    // Filter to only "usable" bar colors
    const usable = normalizedBar.filter(hex => !isTooNeutral(hex));

    let leftGradient = "#3b82f6";
    let rightGradient = "#3b82f6";
    let accentColor = "#3b82f6";
    let isGradient = false;

    if (usable.length >= 2) {
        // Two or more usable bar colors → gradient using first two
        leftGradient = usable[0];
        rightGradient = usable[1];
        accentColor = usable[0];
        isGradient = true;
    } else if (usable.length === 1) {
        // Only one usable bar color → static
        leftGradient = usable[0];
        rightGradient = usable[0];
        accentColor = usable[0];
    } else if (!isTooNeutral(normalizedFish)) {
        // Fallback to fish color
        leftGradient = normalizedFish;
        rightGradient = normalizedFish;
        accentColor = normalizedFish;
    } else if (!isTooNeutral(normalizedArrow)) {
        // Fallback to arrow color
        leftGradient = normalizedArrow;
        rightGradient = normalizedArrow;
        accentColor = normalizedArrow;
    } else {
        // Ultimate fallback
        leftGradient = "#3b82f6";
        rightGradient = "#3b82f6";
        accentColor = "#3b82f6";
    }

    // Apply CSS variables
    document.documentElement.style.setProperty("--left-gradient", leftGradient);
    document.documentElement.style.setProperty("--right-gradient", rightGradient);
    document.documentElement.style.setProperty("--accent-color", accentColor);

    // Glow version – use left color if gradient, otherwise the static color
    const glowBase = isGradient ? leftGradient : accentColor;
    const r = parseInt(glowBase.substr(1, 2), 16);
    const g = parseInt(glowBase.substr(3, 2), 16);
    const b = parseInt(glowBase.substr(5, 2), 16);
    document.documentElement.style.setProperty("--accent-glow", `rgba(${r}, ${g}, ${b}, 0.4)`);
    document.documentElement.style.setProperty("--focus-glow", `rgba(${r}, ${g}, ${b}, 0.28)`);
    document.documentElement.style.setProperty("--focus-ring", `rgba(${r}, ${g}, ${b}, 0.75)`);
    document.documentElement.style.setProperty("--border-soft", `rgba(${r}, ${g}, ${b}, 0.3)`);
    document.documentElement.style.setProperty("--border-medium", `rgba(${r}, ${g}, ${b}, 0.25)`);
    document.documentElement.style.setProperty("--border-strong", `rgba(${r}, ${g}, ${b}, 0.35)`);
    document.documentElement.style.setProperty("--scrollbar-thumb", accentColor);
    document.documentElement.style.setProperty("--scrollbar-thumb-hover", rightGradient);

    // Update button text contrast
    updateButtonContrast();
}

function hexToRgb(hex) {
    hex = hex.replace("#", "");
    if (hex.length === 3) {
        hex = hex.split("").map(c => c + c).join("");
    }
    const num = parseInt(hex, 16);
    return {
        r: (num >> 16) & 255,
        g: (num >> 8) & 255,
        b: num & 255
    };
}
function getBrightness(hex) {
    const { r, g, b } = hexToRgb(hex);
    return (r * 299 + g * 587 + b * 114) / 1000;
}

function updateButtonContrast() {
    const left =
        getComputedStyle(document.documentElement)
        .getPropertyValue("--left-gradient")
        .trim();
    const right =
        getComputedStyle(document.documentElement)
        .getPropertyValue("--right-gradient")
        .trim();
    const leftBrightness = getBrightness(normalizeHexColor(left) || "#3b82f6");
    const rightBrightness = getBrightness(normalizeHexColor(right) || "#ff8a5c");
    const average = (leftBrightness + rightBrightness) / 2;
    const textColor = average > 170 ? "#111827" : "white";
    document.documentElement.style.setProperty("--button-text", textColor);
}

async function selectRatio(target) {
    const fieldId = target && target.id ? target.id : String(target || "");
    const api = _pyApi();
    if (!api || typeof api.select_ratio !== "function") {
        return;
    }
    try {
        await api.select_ratio(fieldId);
    } catch (error) {
        console.error(error);
    }
}


/* =========================
   BOTTOM BANNER
   ========================= */

let _bannerConfirmHandler = null;
let _bannerCancelHandler = null;

function hideBanner() {
    const banner = document.getElementById("bottom-banner");
    if (banner) banner.classList.add("hidden");
    _bannerConfirmHandler = null;
    _bannerCancelHandler = null;
}

function showBanner() {
    const banner = document.getElementById("bottom-banner");
    if (banner) banner.classList.remove("hidden");
}

function showUpdateBanner(options = {}) {
    const title = document.getElementById("banner-title");
    const notice = document.getElementById("banner-notice");
    const dialogue = document.getElementById("banner-dialogue");
    const actions = document.getElementById("banner-actions");

    const titleText = options.title || "Update Available";
    const noticeText = options.notice || "A new version of Solar Fishing Slayers 2 is available. Choose an option below.";

    if (title) title.textContent = titleText;
    if (notice) notice.textContent = noticeText;
    if (dialogue) dialogue.classList.add("hidden");

    _bannerConfirmHandler = options.onConfirm || null;
    _bannerCancelHandler = options.onCancel || null;

    if (actions) {
        if (options.buttons && Array.isArray(options.buttons)) {
            actions.innerHTML = options.buttons.map((btn, i) => {
                const cls = btn.class || "btn-secondary";
                const label = btn.label || "OK";
                return `<button type="button" class="${cls}" data-banner-btn="${i}">${label}</button>`;
            }).join("");
            actions.querySelectorAll("[data-banner-btn]").forEach((el) => {
                const idx = Number(el.getAttribute("data-banner-btn"));
                const btn = options.buttons[idx];
                el.addEventListener("click", () => {
                    if (typeof btn.onClick === "function") {
                        btn.onClick();
                    }
                    hideBanner();
                });
            });
        } else {
            actions.innerHTML = `
                <button type="button" class="btn-ghost" id="banner-cancel-btn">Cancel</button>
                <button type="button" class="btn-primary" id="banner-confirm-btn">Confirm</button>
            `;
            const cancelBtn = document.getElementById("banner-cancel-btn");
            const confirmBtn = document.getElementById("banner-confirm-btn");
            if (cancelBtn) {
                cancelBtn.addEventListener("click", () => {
                    if (typeof _bannerCancelHandler === "function") _bannerCancelHandler();
                    hideBanner();
                });
            }
            if (confirmBtn) {
                confirmBtn.addEventListener("click", () => {
                    if (typeof _bannerConfirmHandler === "function") _bannerConfirmHandler();
                    hideBanner();
                });
            }
        }
    }

    showBanner();
}

function showDialogueBanner(options = {}) {
    const title = document.getElementById("banner-title");
    const notice = document.getElementById("banner-notice");
    const dialogue = document.getElementById("banner-dialogue");
    const input = document.getElementById("banner-input");
    const actions = document.getElementById("banner-actions");

    const titleText = options.title || "Dialogue";
    const noticeText = options.notice || "Enter a value and confirm.";
    const placeholder = options.placeholder || "Enter a value...";

    if (title) title.textContent = titleText;
    if (notice) notice.textContent = noticeText;
    if (dialogue) dialogue.classList.remove("hidden");
    if (input) {
        input.value = options.value || "";
        input.placeholder = placeholder;
        setTimeout(() => input.focus(), 50);
    }

    _bannerConfirmHandler = options.onConfirm || null;
    _bannerCancelHandler = options.onCancel || null;

    if (actions) {
        actions.innerHTML = `
            <button type="button" class="btn-ghost" id="banner-cancel-btn">Cancel</button>
            <button type="button" class="btn-primary" id="banner-confirm-btn">Confirm</button>
        `;
        const cancelBtn = document.getElementById("banner-cancel-btn");
        const confirmBtn = document.getElementById("banner-confirm-btn");
        if (cancelBtn) {
            cancelBtn.addEventListener("click", () => {
                if (typeof _bannerCancelHandler === "function") _bannerCancelHandler();
                hideBanner();
            });
        }
        if (confirmBtn) {
            confirmBtn.addEventListener("click", () => {
                const value = input ? input.value.trim() : "";
                if (typeof _bannerConfirmHandler === "function") {
                    _bannerConfirmHandler(value);
                }
                hideBanner();
            });
        }
    }

    showBanner();
}

function confirmDialogue() {
    const input = document.getElementById("banner-input");
    const value = input ? input.value.trim() : "";
    if (typeof _bannerConfirmHandler === "function") {
        _bannerConfirmHandler(value);
    }
    hideBanner();
}

/**
 * Custom bottom-banner replacement for window.alert / window.confirm.
 * Returns a Promise that resolves to true/false (askyesno) or null (ok).
 * Called from Python via evaluate_js; result is delivered by calling
 * pywebview.api.message_box_result(...).
 */
function showMessageBoxBanner(message, type = "ok") {
    const safeMessage = String(message || "").replace(/\\n/g, "\n");
    const title = type === "askyesno" ? "Confirm" : "Notice";

    return new Promise((resolve) => {
        const finish = (value) => {
            resolve(value);
            try {
                if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.message_box_result === "function") {
                    window.pywebview.api.message_box_result(value);
                }
            } catch (e) {
                console.error(e);
            }
        };

        if (type === "askyesno") {
            showUpdateBanner({
                title: title,
                notice: safeMessage,
                buttons: [
                    { label: "No", class: "btn-ghost", onClick: () => finish(false) },
                    { label: "Yes", class: "btn-primary", onClick: () => finish(true) }
                ]
            });
        } else {
            showUpdateBanner({
                title: title,
                notice: safeMessage,
                buttons: [
                    { label: "OK", class: "btn-primary", onClick: () => finish(null) }
                ]
            });
        }
    });
}
