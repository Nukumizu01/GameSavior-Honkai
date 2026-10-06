const state = {
  dashboard: null,
  tasks: [],
  config: null,
  selectedTask: null,
  refreshTimer: null,
  qrTimer: null,
  qrUpdatedAt: null,
  loginSwitch: null,
};

const $ = (selector) => document.querySelector(selector);

const statusLabels = {
  queued: "排队中",
  claimed: "已领取",
  running: "运行中",
  succeeded: "成功",
  failed: "失败",
  timeout: "超时",
  cancelled: "已取消",
};

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3200);
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

function goToLogin() {
  window.location.replace("/login");
  if (state.refreshTimer) window.clearInterval(state.refreshTimer);
  if (state.qrTimer) window.clearInterval(state.qrTimer);
}

function formatDate(value) {
  if (!value) return "暂无";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function scheduleToTime(cron) {
  if (!cron) return "04:20";
  const parts = cron.trim().split(/\s+/);
  if (parts.length < 2) return "04:20";
  return `${String(parts[1]).padStart(2, "0")}:${String(parts[0]).padStart(2, "0")}`;
}

function timeToCron(time) {
  const [hour, minute] = time.split(":");
  return `${Number(minute)} ${Number(hour)} * * *`;
}

function renderDashboard() {
  const data = state.dashboard || { games: [], workers: [] };
  const workers = data.workers || [];
  const worker = workers.find((item) => item.worker_type === "starrail") || workers[0];
  const starrail = (data.games || []).find((item) => item.game === "starrail");

  $("#api-status").textContent = "在线";
  $("#worker-status").textContent = worker?.status === "online" ? "在线" : (worker?.status || "离线");
  $("#worker-dot").className = `status-dot ${worker?.status === "online" ? "online" : "offline"}`;
  $("#enabled-games").textContent = starrail?.enabled ? "崩铁" : "无";
  $("#last-sync").textContent = `同步于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;

  if (!worker) {
    $("#worker-detail").innerHTML = '<span class="muted">尚未注册 Worker</span>';
  } else {
    $("#worker-detail").innerHTML = `
      <div class="worker-line"><span>名称</span><strong>${escapeHtml(worker.name || worker.worker_key)}</strong></div>
      <div class="worker-line"><span>状态</span><strong>${escapeHtml(worker.status || "unknown")}</strong></div>
      <div class="worker-line"><span>最后心跳</span><strong>${escapeHtml(formatDate(worker.last_heartbeat_at))}</strong></div>
      <div class="worker-line"><span>版本</span><strong>${escapeHtml(worker.version || "未提供")}</strong></div>
    `;
  }
}

function renderLoginStatus(qr = null) {
  const status = state.loginSwitch?.status;
  let label = "状态未知";
  if (status === "pending") label = "切换中";
  else if (status === "error") label = "切换失败";
  else if (state.loginSwitch?.qr_notification_status === "sent") label = "已发飞书";
  else if (state.loginSwitch?.qr_notification_status === "failed") label = "飞书发送失败";
  else if (qr?.available) label = "待扫码";
  else if (status === "ready_for_scan") label = "请扫码";
  else if (status === "idle") label = "未检测到二维码";
  $("#starrail-login-status").textContent = label;
}

function renderTasks() {
  const list = $("#task-list");
  const empty = $("#task-empty");
  if (!state.tasks.length) {
    list.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  list.innerHTML = state.tasks.map((task) => {
    const status = task.status || "unknown";
    const canCancel = ["queued", "claimed", "running"].includes(status);
    const canRetry = ["failed", "timeout", "cancelled"].includes(status);
    return `
      <article class="task-card">
        <div class="task-main">
          <div class="task-title">
            <strong>崩铁日常 #${task.id}</strong>
            <span class="badge badge-${escapeHtml(status)}">${statusLabels[status] || escapeHtml(status)}</span>
          </div>
          <div class="task-meta">
            <span>来源：${escapeHtml(task.source || "unknown")}</span>
            <span>计划：${escapeHtml(formatDate(task.scheduled_for))}</span>
            <span>创建：${escapeHtml(formatDate(task.created_at))}</span>
          </div>
        </div>
        <div class="task-actions">
          <button class="secondary-button task-detail-btn" data-id="${task.id}">详情</button>
          ${canCancel ? `<button class="secondary-button task-cancel-btn" data-id="${task.id}">取消</button>` : ""}
          ${canRetry ? `<button class="secondary-button task-retry-btn" data-id="${task.id}">重试</button>` : ""}
        </div>
      </article>
    `;
  }).join("");
}

function renderConfig() {
  if (!state.config) return;
  $("#schedule-time").value = scheduleToTime(state.config.schedule_cron);
  $("#timezone").value = state.config.timezone || "Asia/Shanghai";
  $("#timeout-minutes").value = Math.round((state.config.timeout_seconds || 3600) / 60);
  $("#max-retries").value = state.config.max_retries ?? 1;
  $("#retry-delay").value = Math.round((state.config.retry_delay_seconds || 600) / 60);
  $("#screenshot-policy").value = state.config.screenshot_policy || "failure_only";
  $("#schedule-enabled").checked = Boolean(state.config.enabled);
  $("#config-state").textContent = "已读取";
}

function collectConfigPayload() {
  return {
    enabled: $("#schedule-enabled").checked,
    timezone: $("#timezone").value,
    schedule_cron: timeToCron($("#schedule-time").value),
    timeout_seconds: Number($("#timeout-minutes").value) * 60,
    max_retries: Number($("#max-retries").value),
    retry_delay_seconds: Number($("#retry-delay").value) * 60,
    task_options: state.config?.custom_task_options || {},
    script_settings: state.config?.script_settings || {},
    screenshot_policy: $("#screenshot-policy").value,
  };
}

async function saveConfig(successMessage) {
  await api("/games/starrail/config", {
    method: "PUT",
    body: JSON.stringify(collectConfigPayload()),
  });
  showToast(successMessage);
  await loadData();
}

function renderQrStatus(qr) {
  const panel = $("#qrcode-panel");
  const image = $("#qrcode-image");
  const requestedAt = state.loginSwitch?.requested_at
    ? new Date(state.loginSwitch.requested_at).getTime()
    : 0;
  const qrUpdatedAt = qr?.updated_at ? new Date(qr.updated_at).getTime() : 0;
  const isOlderThanSwitchRequest = requestedAt && qrUpdatedAt && qrUpdatedAt <= requestedAt;
  renderLoginStatus(isOlderThanSwitchRequest ? { available: false } : qr);
  if (!qr?.available || isOlderThanSwitchRequest) {
    panel.hidden = true;
    state.qrUpdatedAt = null;
    return;
  }
  panel.hidden = false;
  $("#qrcode-state").textContent = qr.age_seconds > 240 ? "可能已过期" : "可扫码";
  $("#qrcode-updated").textContent = `生成于 ${formatDate(qr.updated_at)}，已存在 ${qr.age_seconds} 秒。`;
  if (state.qrUpdatedAt !== qr.updated_at) {
    state.qrUpdatedAt = qr.updated_at;
    image.src = `/api/v1/starrail/login-qr?ts=${encodeURIComponent(qr.updated_at)}`;
  }
}

function renderEvents(events) {
  const list = $("#event-list");
  if (!events.length) {
    list.innerHTML = '<div class="empty-state">暂时没有日志事件</div>';
    return;
  }
  list.innerHTML = events.map((event) => `
    <div class="event-item event-${escapeHtml(event.level || "info")}">
      <div class="event-meta">
        <span>${escapeHtml(event.stage || event.event_type || "event")}</span>
        <span>${escapeHtml(formatDate(event.created_at))}</span>
      </div>
      <div class="event-message">${escapeHtml(event.message || "")}</div>
    </div>
  `).join("");
}

function renderTaskDetail(task, runs, events, selectedRun = null) {
  $("#detail-title").textContent = `崩铁日常 #${task.id}`;
  const run = selectedRun || runs[runs.length - 1];
  $("#detail-summary").innerHTML = `
    <div class="summary-cell"><span>任务状态</span><strong>${escapeHtml(statusLabels[task.status] || task.status)}</strong></div>
    <div class="summary-cell"><span>运行状态</span><strong>${escapeHtml(run?.status || "未开始")}</strong></div>
    <div class="summary-cell"><span>Worker</span><strong>${escapeHtml(run?.worker_id ? `节点 ${run.worker_id}` : "未分配")}</strong></div>
  `;
  $("#log-state").textContent = `${events.length} 条事件`;
  renderEvents(events);
}

function renderArtifacts(runId, artifacts) {
  const list = $("#artifact-list");
  if (!artifacts.length) {
    $("#artifact-state").textContent = "暂无附件";
    list.innerHTML = '<div class="empty-state">本次运行没有上传截图或完整日志附件。</div>';
    return;
  }
  $("#artifact-state").textContent = `${artifacts.length} 个附件`;
  list.innerHTML = artifacts.map((artifact) => {
    const url = `/api/v1/runs/${runId}/artifacts/${artifact.id}/content`;
    const isImage = (artifact.mime_type || "").startsWith("image/")
      || /\.(png|jpe?g|webp)$/i.test(artifact.storage_path || "");
    const size = artifact.size_bytes ? `${Math.ceil(artifact.size_bytes / 1024)} KB` : "未知大小";
    return `
      <div class="artifact-item">
        <strong>${escapeHtml(artifact.kind || "附件")}</strong>
        <span class="artifact-meta">${escapeHtml(size)} · ${escapeHtml(formatDate(artifact.created_at))}</span>
        ${isImage
          ? `<a href="${url}" target="_blank" rel="noreferrer"><img class="artifact-preview" src="${url}" alt="运行截图" /></a>`
          : `<a class="artifact-link" href="${url}" target="_blank" rel="noreferrer">查看完整日志</a>`}
      </div>
    `;
  }).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[char]));
}

async function loadData() {
  const [dashboard, tasks, config, qr, loginSwitch] = await Promise.all([
    api("/dashboard"),
    api("/tasks?game=starrail&limit=50"),
    api("/games/starrail/config"),
    api("/starrail/login-qr/status"),
    api("/starrail/login-switch/status"),
  ]);
  state.dashboard = dashboard;
  state.tasks = tasks.tasks || [];
  state.config = config;
  state.loginSwitch = loginSwitch;
  renderDashboard();
  renderTasks();
  renderConfig();
  renderQrStatus(qr);
}

async function loadQrStatus() {
  try {
    const [qr, loginSwitch] = await Promise.all([
      api("/starrail/login-qr/status"),
      api("/starrail/login-switch/status"),
    ]);
    state.loginSwitch = loginSwitch;
    renderQrStatus(qr);
  } catch {
    // The normal dashboard request handles expired sessions.
  }
}

async function switchStarrailLogin() {
  if (!window.confirm("切换后会清除服务器保存的当前崩铁登录状态，需要重新扫码。确认继续吗？")) return;
  const button = $("#switch-login-btn");
  button.disabled = true;
  try {
    const result = await api("/starrail/login-switch", { method: "POST" });
    state.loginSwitch = result;
    renderQrStatus({ available: false });
    showToast("已请求切换登录，等待 Worker 清理旧账号");
    await loadQrStatus();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function sendCurrentQrToFeishu() {
  const button = $("#send-qr-feishu-btn");
  button.disabled = true;
  try {
    const result = await api("/notifications/test-login-qr", { method: "POST" });
    showToast(result.ok ? "二维码已发送到飞书" : (result.detail || "二维码发送失败"), !result.ok);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function openTaskDetail(taskId) {
  $("#detail-dialog").showModal();
  $("#event-list").innerHTML = '<div class="loading-state">读取日志中</div>';
  $("#artifact-list").innerHTML = '<div class="loading-state">读取附件中</div>';
  try {
    const detail = await api(`/tasks/${taskId}`);
    const run = detail.runs?.[detail.runs.length - 1];
    const events = run ? (await api(`/runs/${run.id}/events`)).events || [] : [];
    const artifacts = run ? (await api(`/runs/${run.id}/artifacts`)).artifacts || [] : [];
    renderTaskDetail(detail.task, detail.runs || [], events);
    renderArtifacts(run?.id, artifacts);
  } catch (error) {
    $("#event-list").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    $("#artifact-list").innerHTML = "";
  }
}

async function openRunDetail(runId) {
  $("#detail-dialog").showModal();
  $("#event-list").innerHTML = '<div class="loading-state">读取日志中</div>';
  $("#artifact-list").innerHTML = '<div class="loading-state">读取附件中</div>';
  try {
    const runResult = await api(`/runs/${runId}`);
    const run = runResult.run;
    const [detail, eventResult, artifactResult] = await Promise.all([
      api(`/tasks/${run.task_id}`),
      api(`/runs/${run.id}/events`),
      api(`/runs/${run.id}/artifacts`),
    ]);
    renderTaskDetail(detail.task, detail.runs || [], eventResult.events || [], run);
    renderArtifacts(run.id, artifactResult.artifacts || []);
  } catch (error) {
    $("#event-list").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    $("#artifact-list").innerHTML = "";
  }
}

async function cancelTask(taskId) {
  if (!window.confirm(`确认取消任务 #${taskId}？`)) return;
  try {
    await api(`/tasks/${taskId}/cancel`, { method: "POST" });
    showToast("任务已取消");
    await loadData();
  } catch (error) { showToast(error.message, true); }
}

async function retryTask(taskId) {
  try {
    await api(`/tasks/${taskId}/retry`, { method: "POST" });
    showToast("已创建重试任务");
    await loadData();
  } catch (error) { showToast(error.message, true); }
}

$("#logout-btn").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); } catch {}
  goToLogin();
});

$("#refresh-btn").addEventListener("click", async () => {
  try { await loadData(); showToast("数据已刷新"); } catch (error) { showToast(error.message, true); }
});

$("#new-task-btn").addEventListener("click", () => $("#task-dialog").showModal());
$("#close-detail-btn").addEventListener("click", () => $("#detail-dialog").close());

$("#confirm-task-btn").addEventListener("click", async (event) => {
  event.preventDefault();
  try {
    await api("/tasks", {
      method: "POST",
      body: JSON.stringify({ game: "starrail", source: $("#task-source").value, options: {} }),
    });
    $("#task-dialog").close();
    showToast("任务已创建");
    await loadData();
  } catch (error) { showToast(error.message, true); }
});

$("#task-list").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const taskId = button.dataset.id;
  if (button.classList.contains("task-detail-btn")) openTaskDetail(taskId);
  if (button.classList.contains("task-cancel-btn")) cancelTask(taskId);
  if (button.classList.contains("task-retry-btn")) retryTask(taskId);
});

$("#config-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await saveConfig("运行设置已保存");
  } catch (error) { showToast(error.message, true); }
});

$("#feishu-test-btn").addEventListener("click", async () => {
  try {
    const result = await api("/notifications/test", { method: "POST" });
    showToast(result.ok ? "飞书通知发送成功" : "飞书通知发送失败", !result.ok);
  } catch (error) { showToast(error.message, true); }
});

$("#switch-login-btn").addEventListener("click", switchStarrailLogin);
$("#send-qr-feishu-btn").addEventListener("click", sendCurrentQrToFeishu);

async function start() {
  try {
    await api("/auth/me");
    await loadData();
    const runMatch = window.location.pathname.match(/^\/runs\/(\d+)\/?$/);
    if (runMatch) await openRunDetail(runMatch[1]);
    state.refreshTimer = window.setInterval(() => loadData().catch(() => {}), 15000);
    state.qrTimer = window.setInterval(loadQrStatus, 3000);
  } catch (error) {
    if (!error.message.includes("登录已失效")) goToLogin();
  }
}

start();
