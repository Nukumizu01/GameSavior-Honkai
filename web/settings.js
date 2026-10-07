const state = {
  config: null,
  schema: null,
  values: {},
  selectedGroupKey: null,
};

const $ = (selector) => document.querySelector(selector);

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function goToLogin() {
  window.location.replace("/login");
}

async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) {
    goToLogin();
    throw new Error("登录已失效，请重新登录");
  }
  const text = await response.text();
  let data = {};
  if (text) {
    try { data = JSON.parse(text); } catch { data = { detail: text }; }
  }
  if (!response.ok) throw new Error(data.detail || `请求失败（${response.status}）`);
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[char]));
}

function fieldId(key) {
  return `script-setting-${key}`;
}

function renderField(field, values) {
  const value = values[field.key] ?? field.default;
  const id = fieldId(field.key);
  if (field.type === "boolean") {
    return `
      <label class="setting-toggle">
        <span>
          <strong>${escapeHtml(field.label)}</strong>
          ${field.description ? `<small>${escapeHtml(field.description)}</small>` : ""}
        </span>
        <input id="${id}" data-setting-key="${escapeHtml(field.key)}" data-setting-type="boolean" type="checkbox" ${value ? "checked" : ""} />
      </label>
    `;
  }
  if (field.type === "select") {
    const options = (field.options || []).map((option) => `
      <option value="${escapeHtml(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>
        ${escapeHtml(option.label)}
      </option>
    `).join("");
    return `
      <label class="setting-field">
        <span>${escapeHtml(field.label)}</span>
        <select id="${id}" data-setting-key="${escapeHtml(field.key)}" data-setting-type="select">${options}</select>
        ${field.description ? `<small>${escapeHtml(field.description)}</small>` : ""}
      </label>
    `;
  }
  return `
    <label class="setting-field">
      <span>${escapeHtml(field.label)}</span>
      <input id="${id}" data-setting-key="${escapeHtml(field.key)}" data-setting-type="${escapeHtml(field.type)}"
        type="${field.type === "number" ? "number" : "text"}" value="${escapeHtml(value)}" />
      ${field.description ? `<small>${escapeHtml(field.description)}</small>` : ""}
    </label>
  `;
}

function groupByKey(key) {
  return (state.schema?.groups || []).find((group) => group.key === key)
    || state.schema?.groups?.[0]
    || null;
}

function syncVisibleValues() {
  document.querySelectorAll("[data-setting-key]").forEach((element) => {
    const key = element.dataset.settingKey;
    state.values[key] = element.dataset.settingType === "boolean"
      ? element.checked
      : element.value;
  });
}

function renderSettingsDirectory() {
  const directory = $("#settings-directory");
  directory.innerHTML = (state.schema.groups || []).map((group, index) => `
    <button
      class="settings-nav-item ${group.key === state.selectedGroupKey ? "active" : ""}"
      type="button"
      data-settings-group="${escapeHtml(group.key)}"
      aria-current="${group.key === state.selectedGroupKey ? "page" : "false"}"
    >
      <span class="settings-nav-index">${String(index + 1).padStart(2, "0")}</span>
      <span>${escapeHtml(group.title)}</span>
    </button>
  `).join("");
}

function renderSelectedGroup() {
  const overrides = state.config?.script_settings?.config_overrides || {};
  const group = groupByKey(state.selectedGroupKey);
  if (!group) {
    $("#script-settings-groups").innerHTML = `<div class="empty-state">没有可用的脚本设置分类</div>`;
    return;
  }
  const html = `
    <section class="settings-group">
      <div class="settings-group-heading">
        <div>
          <p class="eyebrow">${escapeHtml(group.key)}</p>
          <h3>${escapeHtml(group.title)}</h3>
        </div>
        <span class="muted">${escapeHtml(group.description || "")}</span>
      </div>
      <div class="settings-field-grid">
        ${(group.fields || []).map((field) => renderField(field, state.values)).join("")}
      </div>
    </section>
  `;
  $("#script-settings-groups").innerHTML = html;
}

function selectGroup(key, updateHash = true) {
  const group = groupByKey(key);
  if (!group) return;
  syncVisibleValues();
  state.selectedGroupKey = group.key;
  renderSettingsDirectory();
  renderSelectedGroup();
  if (updateHash) {
    window.history.replaceState(null, "", `#${encodeURIComponent(group.key)}`);
  }
}

function renderSettings() {
  const overrides = state.config?.script_settings?.config_overrides || {};
  state.values = {};
  for (const group of state.schema.groups || []) {
    for (const field of group.fields || []) {
      state.values[field.key] = overrides[field.key] ?? field.default;
    }
  }
  const requestedGroup = decodeURIComponent(window.location.hash.slice(1));
  state.selectedGroupKey = groupByKey(requestedGroup)?.key || state.schema.groups?.[0]?.key;
  renderSettingsDirectory();
  renderSelectedGroup();
  $("#settings-state").textContent = "已读取";
}

function schedulePayload() {
  return {
    enabled: Boolean(state.config.enabled),
    timezone: state.config.timezone,
    schedule_cron: state.config.schedule_cron,
    timeout_seconds: state.config.timeout_seconds,
    max_retries: state.config.max_retries,
    retry_delay_seconds: state.config.retry_delay_seconds,
    task_options: state.config.custom_task_options || {},
    screenshot_policy: state.config.screenshot_policy,
  };
}

function collectOverrides() {
  syncVisibleValues();
  const values = {};
  for (const group of state.schema.groups || []) {
    for (const field of group.fields || []) {
      const raw = state.values[field.key];
      if (field.type === "boolean") {
        values[field.key] = Boolean(raw);
      } else if (field.type === "number") {
        const numeric = Number(raw);
        if (!Number.isFinite(numeric)) throw new Error(`${field.key} 不是有效数字`);
        values[field.key] = numeric;
      } else {
        values[field.key] = String(raw ?? "");
      }
    }
  }
  return values;
}

function buildScriptSettings(overrides) {
  const old = state.config.script_settings || {};
  return {
    cloud_game_enabled: overrides.cloud_game_enable ?? old.cloud_game_enabled ?? true,
    browser_headless_enabled: overrides.browser_headless_enable ?? old.browser_headless_enabled ?? true,
    browser_headless_restart_on_not_logged_in:
      overrides.browser_headless_restart_on_not_logged_in
      ?? old.browser_headless_restart_on_not_logged_in
      ?? false,
    after_finish: overrides.after_finish ?? old.after_finish ?? "Exit",
    log_level: overrides.log_level ?? old.log_level ?? "INFO",
    config_overrides: overrides,
  };
}

async function load() {
  try {
    const [config, schema] = await Promise.all([
      api("/games/starrail/config"),
      api("/games/starrail/script-schema"),
    ]);
    state.config = config;
    state.schema = schema;
    renderSettings();
  } catch (error) {
    $("#settings-state").textContent = "读取失败";
    $("#script-settings-groups").innerHTML =
      `<div class="empty-state">${escapeHtml(error.message || "脚本设置读取失败")}</div>`;
    throw error;
  }
}

$("#script-settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    const overrides = collectOverrides();
    await api("/games/starrail/config", {
      method: "PUT",
      body: JSON.stringify({
        ...schedulePayload(),
        script_settings: buildScriptSettings(overrides),
      }),
    });
    await load();
    showToast("脚本设置已保存，新任务会使用最新配置");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#reset-settings-btn").addEventListener("click", () => {
  if (!window.confirm("恢复本页默认值并保存吗？")) return;
  const group = groupByKey(state.selectedGroupKey);
  for (const field of group?.fields || []) state.values[field.key] = field.default;
  renderSelectedGroup();
  showToast("已恢复当前分类默认值，请点击保存");
});

$("#settings-nav-toggle").addEventListener("click", () => {
  const toggle = $("#settings-nav-toggle");
  const expanded = toggle.getAttribute("aria-expanded") === "true";
  toggle.setAttribute("aria-expanded", String(!expanded));
  $("#settings-directory").classList.toggle("is-collapsed", expanded);
});

$("#settings-directory").addEventListener("click", (event) => {
  const button = event.target.closest("[data-settings-group]");
  if (button) selectGroup(button.dataset.settingsGroup);
});

window.addEventListener("hashchange", () => {
  const requestedGroup = decodeURIComponent(window.location.hash.slice(1));
  selectGroup(requestedGroup, false);
});

$("#logout-btn").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); } catch {}
  goToLogin();
});

load().catch((error) => {
  $("#settings-state").textContent = "读取失败";
  $("#script-settings-groups").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
});
