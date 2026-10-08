<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const path = ref(window.location.pathname)
const isMobile = ref(window.matchMedia('(max-width: 767px)').matches)
const isStandalone = ref(window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true)
const installPrompt = ref(null)
const route = computed(() => path.value === '/login' ? 'login' : path.value === '/settings' ? 'settings' : 'dashboard')
const runId = computed(() => path.value.match(/^\/runs\/(\d+)\/?$/)?.[1] || null)
const state = reactive({
  dashboard: { games: [], workers: [] }, tasks: [], config: null, qr: { available: false }, loginSwitch: { status: 'idle' },
  pagination: { page: 1, pageSize: 10, total: 0, totalPages: 1 }, loading: false, settings: null,
})
const detail = reactive({ visible: false, task: null, run: null, events: [], artifacts: [], loading: false })
const taskDialog = ref(false)
const taskSource = ref('manual')
const loginForm = reactive({ username: '', password: '' })
const loginLoading = ref(false)
const settingsGroup = ref('')
const settingsValues = reactive({})
const settingsSaving = ref(false)
let refreshTimer
let qrTimer
let mobileMediaQuery
let appInstalledMediaQuery

const statusLabels = { queued: '排队中', claimed: '已领取', running: '运行中', succeeded: '成功', failed: '失败', timeout: '超时', cancelled: '已取消' }
const worker = computed(() => state.dashboard.workers?.find((item) => item.worker_type === 'starrail') || state.dashboard.workers?.[0])
const starrail = computed(() => state.dashboard.games?.find((item) => item.game === 'starrail'))
const selectedGroup = computed(() => state.settings?.groups?.find((group) => group.key === settingsGroup.value) || state.settings?.groups?.[0])

function normalizeConfig(config) {
  return {
    ...config,
    schedule_time: scheduleToTime(config.schedule_cron),
    timeout_minutes: Math.round((config.timeout_seconds || 3600) / 60),
    retry_delay_minutes: Math.round((config.retry_delay_seconds || 600) / 60),
  }
}

function navigate(target) {
  if (target === path.value) return
  window.history.pushState({}, '', target)
  path.value = target
}

function goLogin() {
  if (path.value !== '/login') navigate('/login')
}

async function api(endpoint, options = {}) {
  const response = await fetch(`/api/v1${endpoint}`, { credentials: 'include', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options })
  if (response.status === 401) { goLogin(); throw new Error('登录已失效，请重新登录') }
  const text = await response.text()
  let data = {}
  if (text) { try { data = JSON.parse(text) } catch { data = { detail: text } } }
  if (!response.ok) throw new Error(data.detail || `请求失败（${response.status}）`)
  return data
}

function formatDate(value) {
  if (!value) return '暂无'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
function scheduleToTime(cron) {
  const parts = (cron || '').trim().split(/\s+/)
  return parts.length >= 2 ? `${String(parts[1]).padStart(2, '0')}:${String(parts[0]).padStart(2, '0')}` : '04:20'
}
function timeToCron(time) {
  const [hour, minute] = (time || '04:20').split(':')
  return `${Number(minute)} ${Number(hour)} * * *`
}
function notify(message, type = 'success') { ElMessage({ message, type }) }
function captureInstallPrompt(event) { event.preventDefault(); installPrompt.value = event }
function onAppInstalled() { isStandalone.value = true; installPrompt.value = null }
async function installApp() {
  if (installPrompt.value) {
    const prompt = installPrompt.value
    installPrompt.value = null
    await prompt.prompt()
    return
  }
  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) && !isStandalone.value
  const message = isIos ? '在 Safari 中打开分享菜单，选择“添加到主屏幕”。' : '打开浏览器菜单，选择“安装应用”或“添加到主屏幕”。'
  await ElMessageBox.alert(message, '安装 Game Savior', { confirmButtonText: '知道了' })
}

async function loadDashboard() {
  state.loading = true
  try {
    const [dashboard, tasks, config, qr, loginSwitch] = await Promise.all([
      api('/dashboard'), api(`/tasks?game=starrail&page=${state.pagination.page}&page_size=${state.pagination.pageSize}`),
      api('/games/starrail/config'), api('/starrail/login-qr/status'), api('/starrail/login-switch/status'),
    ])
    state.dashboard = dashboard; state.tasks = tasks.tasks || []; state.config = normalizeConfig(config); state.qr = qr; state.loginSwitch = loginSwitch
    state.pagination = { page: tasks.page || 1, pageSize: tasks.page_size || 10, total: tasks.total || 0, totalPages: tasks.total_pages || 1 }
  } catch (error) { if (!error.message.includes('登录已失效')) notify(error.message, 'error') } finally { state.loading = false }
}
async function loadQr() {
  try { const [qr, loginSwitch] = await Promise.all([api('/starrail/login-qr/status'), api('/starrail/login-switch/status')]); state.qr = qr; state.loginSwitch = loginSwitch } catch {}
}
async function checkSession() {
  try { await api('/auth/me'); if (route.value === 'login') navigate('/dashboard'); else if (route.value === 'dashboard') { await loadDashboard(); if (runId.value) await openRunById(runId.value) } } catch { if (route.value !== 'login') goLogin() }
}

async function login() {
  loginLoading.value = true
  try { await api('/auth/login', { method: 'POST', body: JSON.stringify(loginForm) }); notify('登录成功'); navigate('/dashboard') }
  catch (error) { notify(error.message || '登录失败，请稍后重试', 'error') } finally { loginLoading.value = false }
}
async function logout() { try { await api('/auth/logout', { method: 'POST' }) } catch {} navigate('/login') }
async function createTask() {
  try { await api('/tasks', { method: 'POST', body: JSON.stringify({ game: 'starrail', source: taskSource.value, options: {} }) }); taskDialog.value = false; notify('任务已创建'); await loadDashboard() }
  catch (error) { notify(error.message, 'error') }
}
async function cancelTask(task) {
  try { await ElMessageBox.confirm(`确认取消任务 #${task.id}？`, '取消任务', { type: 'warning' }); await api(`/tasks/${task.id}/cancel`, { method: 'POST' }); notify('任务已取消'); await loadDashboard() } catch (error) { if (error !== 'cancel' && error !== 'close') notify(error.message, 'error') }
}
async function retryTask(task) {
  try { await api(`/tasks/${task.id}/retry`, { method: 'POST' }); notify('已创建重试任务'); await loadDashboard() } catch (error) { notify(error.message, 'error') }
}
async function switchLogin() {
  try { await ElMessageBox.confirm('切换后会清除服务器保存的当前崩铁登录状态，需要重新扫码。确认继续吗？', '切换登录', { type: 'warning' }); await api('/starrail/login-switch', { method: 'POST' }); notify('已请求切换登录，等待 Worker 清理旧账号'); await loadQr() }
  catch (error) { if (error !== 'cancel' && error !== 'close') notify(error.message, 'error') }
}
async function testFeishu() { try { const result = await api('/notifications/test', { method: 'POST' }); notify(result.ok ? '飞书通知发送成功' : '飞书通知发送失败', result.ok ? 'success' : 'error') } catch (error) { notify(error.message, 'error') } }
async function sendQr() { try { const result = await api('/notifications/test-login-qr', { method: 'POST' }); notify(result.ok ? '二维码已发送到飞书' : (result.detail || '二维码发送失败'), result.ok ? 'success' : 'error') } catch (error) { notify(error.message, 'error') } }

async function openTask(taskId) {
  detail.visible = true; detail.loading = true; detail.events = []; detail.artifacts = []
  try {
    const result = await api(`/tasks/${taskId}`); detail.task = result.task; detail.run = result.runs?.[result.runs.length - 1] || null
    if (detail.run) { const [events, artifacts] = await Promise.all([api(`/runs/${detail.run.id}/events`), api(`/runs/${detail.run.id}/artifacts`)]); detail.events = events.events || []; detail.artifacts = artifacts.artifacts || [] }
  } catch (error) { notify(error.message, 'error') } finally { detail.loading = false }
}
async function openRun(run) { await openTask(run.task_id); if (detail.task) detail.run = run }
async function openRunById(id) {
  try { const result = await api(`/runs/${id}`); await openRun(result.run) } catch (error) { notify(error.message, 'error') }
}

function initSettings(config, schema) {
  state.settings = schema; Object.keys(settingsValues).forEach((key) => delete settingsValues[key])
  const overrides = config.script_settings?.config_overrides || {}
  for (const group of schema.groups || []) for (const field of group.fields || []) settingsValues[field.key] = overrides[field.key] ?? field.default
  settingsGroup.value = schema.groups?.[0]?.key || ''
}
async function loadSettings() {
  try { const [config, schema] = await Promise.all([api('/games/starrail/config'), api('/games/starrail/script-schema')]); state.config = normalizeConfig(config); initSettings(config, schema) }
  catch (error) { notify(error.message, 'error') }
}
function schedulePayload() {
  return { enabled: Boolean(state.config.enabled), timezone: state.config.timezone, schedule_cron: state.config.schedule_cron, timeout_seconds: state.config.timeout_seconds, max_retries: state.config.max_retries, retry_delay_seconds: state.config.retry_delay_seconds, task_options: state.config.custom_task_options || {}, screenshot_policy: state.config.screenshot_policy }
}
function scriptPayload() {
  const old = state.config.script_settings || {}
  return { cloud_game_enabled: settingsValues.cloud_game_enable ?? old.cloud_game_enabled ?? true, browser_headless_enabled: settingsValues.browser_headless_enable ?? old.browser_headless_enabled ?? true, browser_headless_restart_on_not_logged_in: settingsValues.browser_headless_restart_on_not_logged_in ?? old.browser_headless_restart_on_not_logged_in ?? false, after_finish: settingsValues.after_finish ?? old.after_finish ?? 'Exit', log_level: settingsValues.log_level ?? old.log_level ?? 'INFO', config_overrides: { ...settingsValues } }
}
async function saveSettings() {
  settingsSaving.value = true
  try { await api('/games/starrail/config', { method: 'PUT', body: JSON.stringify({ ...schedulePayload(), script_settings: scriptPayload() }) }); await loadSettings(); notify('脚本设置已保存，新任务会使用最新配置') }
  catch (error) { notify(error.message, 'error') } finally { settingsSaving.value = false }
}
async function saveSchedule() {
  try { await api('/games/starrail/config', { method: 'PUT', body: JSON.stringify({ ...schedulePayload(), schedule_cron: timeToCron(state.config.schedule_time), timeout_seconds: Number(state.config.timeout_minutes) * 60, retry_delay_seconds: Number(state.config.retry_delay_minutes) * 60 }) }); notify('运行设置已保存'); await loadDashboard() }
  catch (error) { notify(error.message, 'error') }
}
function resetGroup() { for (const field of selectedGroup.value?.fields || []) settingsValues[field.key] = field.default; notify('已恢复当前分类默认值，请点击保存') }

function navigateFromMenu(key) { navigate(key === 'settings' ? '/settings' : '/dashboard') }
function onPopState() { path.value = window.location.pathname; checkSession() }
function onMobileChange(event) { isMobile.value = event.matches }
watch(route, async (value) => { if (value === 'settings') await loadSettings(); else if (value === 'dashboard') await loadDashboard() })
onMounted(async () => { mobileMediaQuery = window.matchMedia('(max-width: 767px)'); mobileMediaQuery.addEventListener('change', onMobileChange); appInstalledMediaQuery = window.matchMedia('(display-mode: standalone)'); appInstalledMediaQuery.addEventListener('change', onAppInstalled); window.addEventListener('beforeinstallprompt', captureInstallPrompt); window.addEventListener('appinstalled', onAppInstalled); window.addEventListener('popstate', onPopState); await checkSession(); refreshTimer = window.setInterval(() => route.value === 'dashboard' && loadDashboard(), 15000); qrTimer = window.setInterval(() => route.value === 'dashboard' && loadQr(), 3000) })
onBeforeUnmount(() => { window.removeEventListener('popstate', onPopState); window.removeEventListener('beforeinstallprompt', captureInstallPrompt); window.removeEventListener('appinstalled', onAppInstalled); mobileMediaQuery?.removeEventListener('change', onMobileChange); appInstalledMediaQuery?.removeEventListener('change', onAppInstalled); clearInterval(refreshTimer); clearInterval(qrTimer) })
</script>

<template>
  <el-config-provider>
    <div v-if="route === 'login'" class="login-page">
      <el-card class="login-card" shadow="never">
        <p class="eyebrow">PRIVATE CONSOLE</p><h1>登录控制台</h1>
        <p class="muted login-copy">登录后管理云端日常任务、运行日志和定时设置。</p>
        <el-form :model="loginForm" label-position="top" @submit.prevent="login">
          <el-form-item label="用户名"><el-input v-model="loginForm.username" autocomplete="username" autofocus /></el-form-item>
          <el-form-item label="密码"><el-input v-model="loginForm.password" type="password" show-password autocomplete="current-password" @keyup.enter="login" /></el-form-item>
          <el-button type="primary" native-type="submit" :loading="loginLoading" class="full-width">登录</el-button>
        </el-form>
      </el-card>
    </div>

    <el-container v-else :class="['app-shell', { 'is-mobile': isMobile }]">
      <el-header class="topbar"><div><p class="eyebrow">GAME SAVIOR</p><h1>{{ route === 'settings' ? '脚本设置' : '云端日常控制台' }}</h1></div><div class="topbar-actions"><span class="muted sync-status">{{ route === 'dashboard' ? `同步于 ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}` : 'MARCH7THASSISTANT' }}</span><el-button v-if="!isStandalone" text @click="installApp">安装到桌面</el-button><el-button text @click="logout">退出</el-button></div></el-header>
      <el-container>
        <el-aside width="210px" class="sidebar"><p class="sidebar-title">NAVIGATION</p><el-menu :mode="isMobile ? 'horizontal' : 'vertical'" :default-active="route" @select="navigateFromMenu"><el-menu-item index="dashboard">控制台</el-menu-item><el-menu-item index="settings">脚本设置</el-menu-item></el-menu></el-aside>
        <el-main class="main-content">
          <template v-if="route === 'dashboard'">
            <el-row :gutter="12" class="status-strip"><el-col :xs="12" :sm="12" :md="6"><div class="status-item"><span class="status-dot online" /><div><span class="status-label">API</span><strong>在线</strong></div></div></el-col><el-col :xs="12" :sm="12" :md="6"><div class="status-item"><span :class="['status-dot', worker?.status === 'online' ? 'online' : 'offline']" /><div><span class="status-label">崩铁 Worker</span><strong>{{ worker?.status === 'online' ? '在线' : (worker?.status || '离线') }}</strong></div></div></el-col><el-col :xs="12" :sm="12" :md="6"><div class="status-item"><span class="status-dot accent" /><div><span class="status-label">启用游戏</span><strong>{{ starrail?.enabled ? '崩铁' : '无' }}</strong></div></div></el-col><el-col :xs="12" :sm="12" :md="6"><div class="status-item"><span class="status-dot accent" /><div><span class="status-label">崩铁登录</span><strong>{{ state.qr.available ? '待扫码' : (state.loginSwitch.status === 'pending' ? '切换中' : '未检测到二维码') }}</strong></div></div></el-col></el-row>
            <div class="action-row"><el-button type="primary" @click="taskDialog = true">＋ 运行崩铁日常</el-button><el-button @click="switchLogin">切换崩铁登录</el-button><el-button @click="testFeishu">测试飞书通知</el-button><el-button :loading="state.loading" @click="loadDashboard">刷新</el-button></div>
            <el-row :gutter="20" class="page-grid"><el-col :xs="24" :lg="16"><el-card v-if="state.qr.available" class="panel" shadow="never"><template #header><div class="panel-heading"><span>崩铁登录二维码</span><el-tag type="warning">待扫码</el-tag></div></template><div class="qr-content"><img :src="`/api/v1/starrail/login-qr?ts=${encodeURIComponent(state.qr.updated_at)}`" alt="崩铁云游戏登录二维码" /><div><p>扫码后服务器会保存登录状态，后续任务会自动复用。</p><p class="muted">生成于 {{ formatDate(state.qr.updated_at) }}，已存在 {{ state.qr.age_seconds }} 秒。</p><el-button class="qr-send" @click="sendQr">发送二维码到飞书</el-button></div></div></el-card><div class="section-heading"><div><p class="eyebrow">TASK CENTER</p><h2>任务</h2></div></div><el-card shadow="never"><el-table :data="state.tasks" v-loading="state.loading" empty-text="还没有运行记录"><el-table-column label="任务" min-width="190"><template #default="{ row }"><strong>崩铁日常 #{{ row.id }}</strong><div class="muted table-meta">{{ row.source || 'unknown' }} · {{ formatDate(row.created_at) }}</div></template></el-table-column><el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="['succeeded'].includes(row.status) ? 'success' : ['failed', 'timeout'].includes(row.status) ? 'danger' : ['running', 'claimed'].includes(row.status) ? 'warning' : 'info'">{{ statusLabels[row.status] || row.status }}</el-tag></template></el-table-column><el-table-column label="计划时间" min-width="150"><template #default="{ row }">{{ formatDate(row.scheduled_for) }}</template></el-table-column><el-table-column label="操作" width="220" :fixed="isMobile ? false : 'right'"><template #default="{ row }"><el-button link type="primary" @click="openTask(row.id)">详情</el-button><el-button v-if="['queued', 'claimed', 'running'].includes(row.status)" link type="danger" @click="cancelTask(row)">取消</el-button><el-button v-if="['failed', 'timeout', 'cancelled'].includes(row.status)" link type="warning" @click="retryTask(row)">重试</el-button></template></el-table-column></el-table><div v-if="state.pagination.totalPages > 1" class="pagination"><span class="muted">共 {{ state.pagination.total }} 条</span><el-pagination background layout="prev, pager, next" :current-page="state.pagination.page" :page-size="state.pagination.pageSize" :total="state.pagination.total" @current-change="(page) => { state.pagination.page = page; loadDashboard() }" /></div></el-card></el-col><el-col :xs="24" :lg="8"><el-card class="panel" shadow="never"><template #header><div class="panel-heading"><span>崩铁运行设置</span><el-tag type="success">{{ state.config ? '已读取' : '读取中' }}</el-tag></div></template><el-form v-if="state.config" label-position="top" @submit.prevent="saveSchedule"><el-form-item label="每日时间"><el-time-picker v-model="state.config.schedule_time" format="HH:mm" value-format="HH:mm" /></el-form-item><el-form-item label="时区"><el-select v-model="state.config.timezone"><el-option label="Asia/Shanghai" value="Asia/Shanghai" /><el-option label="Asia/Singapore" value="Asia/Singapore" /><el-option label="UTC" value="UTC" /></el-select></el-form-item><el-form-item label="超时（分钟）"><el-input-number v-model="state.config.timeout_minutes" :min="1" :max="360" /></el-form-item><el-form-item label="失败重试次数"><el-input-number v-model="state.config.max_retries" :min="0" :max="5" /></el-form-item><el-form-item label="重试间隔（分钟）"><el-input-number v-model="state.config.retry_delay_minutes" :min="1" :max="1440" /></el-form-item><el-form-item label="截图策略"><el-select v-model="state.config.screenshot_policy"><el-option label="仅失败时" value="failure_only" /><el-option label="全部保存" value="all" /><el-option label="不保存" value="none" /></el-select></el-form-item><el-form-item label="启用每日自动运行"><el-switch v-model="state.config.enabled" /></el-form-item><el-button native-type="submit" class="full-width">保存运行设置</el-button></el-form></el-card><el-card class="panel" shadow="never"><template #header>执行节点</template><el-descriptions v-if="worker" :column="1" border><el-descriptions-item label="名称">{{ worker.name || worker.worker_key }}</el-descriptions-item><el-descriptions-item label="状态">{{ worker.status || 'unknown' }}</el-descriptions-item><el-descriptions-item label="最后心跳">{{ formatDate(worker.last_heartbeat_at) }}</el-descriptions-item><el-descriptions-item label="版本">{{ worker.version || '未提供' }}</el-descriptions-item></el-descriptions><span v-else class="muted">尚未注册 Worker</span></el-card></el-col></el-row>
          </template>
          <template v-else><div class="settings-toolbar"><div><p class="eyebrow">MARCH7THASSISTANT</p><h2>崩铁脚本设置</h2><p class="muted">设置会在下一次任务启动时应用到 Worker。</p></div><div class="settings-actions"><el-button @click="resetGroup">恢复当前分类默认值</el-button><el-button type="primary" :loading="settingsSaving" @click="saveSettings">保存设置</el-button></div></div><el-row :gutter="18" v-if="state.settings" class="settings-layout"><el-col :xs="24" :md="6"><el-menu :default-active="settingsGroup" @select="(key) => settingsGroup = key"><el-menu-item v-for="group in state.settings.groups" :key="group.key" :index="group.key">{{ group.title }}</el-menu-item></el-menu></el-col><el-col :xs="24" :md="18"><el-card shadow="never"><template #header><div class="panel-heading"><span>{{ selectedGroup?.title }}</span><span class="muted">{{ selectedGroup?.description }}</span></div></template><el-form label-position="top" class="settings-form"><el-row :gutter="16"><el-col v-for="field in selectedGroup?.fields || []" :key="field.key" :xs="24" :sm="12"><el-form-item :label="field.label"><el-switch v-if="field.type === 'boolean'" v-model="settingsValues[field.key]" /><el-select v-else-if="field.type === 'select'" v-model="settingsValues[field.key]"><el-option v-for="option in field.options || []" :key="option.value" :label="option.label" :value="option.value" /></el-select><el-input-number v-else-if="field.type === 'number'" v-model="settingsValues[field.key]" /><el-input v-else v-model="settingsValues[field.key]" /><small v-if="field.description" class="muted">{{ field.description }}</small></el-form-item></el-col></el-row></el-form></el-card></el-col></el-row></template>
        </el-main>
      </el-container>
    </el-container>

    <el-dialog v-model="taskDialog" title="运行崩铁日常" width="420px"><el-form label-position="top"><el-form-item label="任务来源"><el-select v-model="taskSource"><el-option label="手动运行" value="manual" /><el-option label="测试运行" value="manual_test" /></el-select></el-form-item></el-form><template #footer><el-button @click="taskDialog = false">取消</el-button><el-button type="primary" @click="createTask">创建任务</el-button></template></el-dialog>
    <el-dialog v-model="detail.visible" :title="detail.task ? `崩铁日常 #${detail.task.id}` : '任务详情'" width="min(94vw, 780px)"><el-skeleton v-if="detail.loading" :rows="5" animated /><template v-else-if="detail.task"><el-descriptions :column="3" border><el-descriptions-item label="任务状态">{{ statusLabels[detail.task.status] || detail.task.status }}</el-descriptions-item><el-descriptions-item label="运行状态">{{ detail.run?.status || '未开始' }}</el-descriptions-item><el-descriptions-item label="Worker">{{ detail.run?.worker_id ? `节点 ${detail.run.worker_id}` : '未分配' }}</el-descriptions-item></el-descriptions><h3 class="detail-heading">运行日志 <span class="muted">{{ detail.events.length }} 条事件</span></h3><el-timeline v-if="detail.events.length"><el-timeline-item v-for="event in detail.events" :key="event.id" :timestamp="formatDate(event.created_at)" :type="event.level === 'error' ? 'danger' : event.level === 'warning' ? 'warning' : 'primary'">{{ event.message }}</el-timeline-item></el-timeline><el-empty v-else description="暂时没有日志事件" /><h3 class="detail-heading">附件</h3><el-empty v-if="!detail.artifacts.length" description="本次运行没有附件" /><div v-for="artifact in detail.artifacts" :key="artifact.id" class="artifact-row"><strong>{{ artifact.kind || '附件' }}</strong><span class="muted">{{ artifact.size_bytes ? `${Math.ceil(artifact.size_bytes / 1024)} KB` : '未知大小' }}</span><a :href="`/api/v1/runs/${detail.run?.id}/artifacts/${artifact.id}/content`" target="_blank">查看</a></div></template></el-dialog>
  </el-config-provider>
</template>
