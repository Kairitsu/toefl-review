import {
  TYPE_NAMES,
  TYPE_SECTIONS,
  IMPORT_TYPES,
  READING_CHOICE_RAW_FIELDS,
  BUILD_SENTENCE_RAW_FIELDS,
  COMPLETE_WORDS_RAW_FIELDS,
  COMPLETE_WORDS_SOURCE_FIELDS,
  state,
} from "../state.js";
import { escapeHtml, attr, lines, delimitedList } from "../utils.js";
import { $, toast, setPracticeModeClass, setView, updateAuthChrome } from "../ui.js";
import { api } from "../api.js";
import { app } from "../core.js";


const render = (...args) => app.render(...args);
const navigate = (...args) => app.navigate(...args);

async function loadSettings() {
  try {
    const [settings, authSettings] = await Promise.all([
      api("/api/settings"),
      api("/api/settings/auth"),
    ]);
    state.settings = settings;
    state.authSettings = authSettings;
  } catch (error) {
    state.settings = { error: error.message };
  }
  render();
}

function renderSettings() {
  const s = state.settings || {};
  const testResult = state.settingsTestResult;
  const draft = state.settingsDraft || {};
  const baseUrl = draft.baseUrl ?? s.baseUrl ?? "";
  const model = draft.model ?? s.model ?? "";
  const customParams = draft.customParams ?? s.customParams ?? "{}";
  const clearApiKey = Boolean(draft.clearApiKey);
  const hasDraftApiKey = Boolean(state.settingsDraftApiKey);
  const configured = Boolean(s.apiKeyConfigured) || hasDraftApiKey;
  const apiKeyStatus = hasDraftApiKey ? "已填写，尚未保存" : s.apiKeyConfigured ? "已配置" : "未配置";

  const authCfg = state.authSettings || {};
  const authDraft = state.authDraft || {};
  const authError = state.authError;

  $("app").innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>LLM API 设置</h1>
          <p class="subtle">兼容 OpenAI Chat Completions 格式。API Key 不会明文回显。</p>
        </div>
        <span class="config-status ${configured ? "ok" : "warn"}">
          <span class="config-dot"></span>
          API Key：${escapeHtml(apiKeyStatus)}
        </span>
      </div>
      <section class="panel settings-grid">
        ${s.error ? `<div class="status error">${escapeHtml(s.error)}</div>` : ""}
        <form autocomplete="off" data-action="saveSettings" data-submit="1">
          <input type="text" name="username" autocomplete="username" value="llm-api-key" hidden />
          <div class="field">
            <label>API Key</label>
            <input id="setting-api-key" type="password" autocomplete="new-password" placeholder="${hasDraftApiKey ? "已临时保存，保存设置时会使用" : s.apiKeyConfigured ? "••••••••  留空表示不覆盖" : "填写 API Key"}" />
            <label class="check-row"><input id="setting-clear-key" type="checkbox" ${clearApiKey ? "checked" : ""} /> 清除已配置的 API Key</label>
          </div>
          <div class="field">
            <label>Base URL 或完整请求 URL</label>
            <input id="setting-base-url" value="${attr(baseUrl)}" placeholder="例如 https://example.com/v1 或 https://example.com/v1/chat/completions" />
          </div>
          <div class="field">
            <label>模型名称</label>
            <input id="setting-model" value="${attr(model)}" placeholder="由你的服务商决定" />
          </div>
          <div class="field">
            <label>可选自定义参数 JSON</label>
            <textarea id="setting-custom" placeholder='例如 {"temperature":0,"max_tokens":2000}'>${escapeHtml(customParams)}</textarea>
          </div>
          ${
            testResult
              ? `<div class="status ${testResult.ok ? "ok" : "error"}">${escapeHtml(testResult.message)}${testResult.details?.length ? `<br>${testResult.details.map(escapeHtml).join("<br>")}` : ""}</div>`
              : ""
          }
          <div class="toolbar actions">
            <button class="btn primary" type="submit">保存设置</button>
            <button class="btn" type="button" data-action="testSettings" ${state.settingsTesting ? "disabled" : ""}>
              ${state.settingsTesting ? "测试中..." : "测试连接"}
            </button>
          </div>
        </form>
      </section>
      <section class="panel settings-grid">
        <div class="page-head" style="margin-bottom:0">
          <div>
            <h2 style="font-size:1.1rem;margin:0">访问认证</h2>
            <p class="subtle">配置用户名和密码后，访问本系统需先登录。</p>
          </div>
          <span class="config-status ${authCfg.configured ? "ok" : "warn"}">
            <span class="config-dot"></span>
            登录认证：${authCfg.configured ? "已启用" : "未启用"}
          </span>
        </div>
        ${authError ? `<div class="status error">${escapeHtml(authError)}</div>` : ""}
        <form autocomplete="off" data-action="saveAuthSettings" data-submit="1">
          <div class="field">
            <label>用户名</label>
            <input id="auth-username" value="${attr(authDraft.username ?? authCfg.username ?? "")}" placeholder="设置登录用户名" autocomplete="off" />
          </div>
          <div class="field">
            <label>新密码</label>
            <input id="auth-password" type="password" autocomplete="new-password"
              placeholder="${authCfg.configured ? "留空表示不修改密码（需同时填写用户名）" : "设置登录密码"}" />
          </div>
          <label class="check-row"><input id="auth-clear" type="checkbox" ${authDraft.clearAuth ? "checked" : ""} /> 清除登录认证（恢复开放访问）</label>
          <div class="toolbar actions">
            <button class="btn primary" type="submit">保存认证设置</button>
          </div>
        </form>
      </section>
    </div>
  `;
}

function collectSettingsPayload() {
  const typedApiKey = $("setting-api-key").value;
  if (typedApiKey) state.settingsDraftApiKey = typedApiKey;
  state.settingsDraft = {
    clearApiKey: $("setting-clear-key").checked,
    baseUrl: $("setting-base-url").value,
    model: $("setting-model").value,
    customParams: $("setting-custom").value,
  };
  if (state.settingsDraft.clearApiKey) state.settingsDraftApiKey = "";
  return {
    apiKey: typedApiKey || state.settingsDraftApiKey,
    clearApiKey: state.settingsDraft.clearApiKey,
    baseUrl: state.settingsDraft.baseUrl,
    model: state.settingsDraft.model,
    customParams: state.settingsDraft.customParams,
  };
}

async function saveSettings() {
  try {
    await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(collectSettingsPayload()),
    });
    state.settingsTestResult = null;
    state.settingsDraft = null;
    state.settingsDraftApiKey = "";
    toast("设置已保存");
    await loadSettings();
  } catch (error) {
    state.settings = {
      ...(state.settings || {}),
      error: `${error.message}${error.data?.details ? "：" + error.data.details.join("；") : ""}`,
    };
    renderSettings();
  }
}

async function testSettings() {
  const payload = collectSettingsPayload();
  state.settingsTesting = true;
  state.settingsTestResult = null;
  renderSettings();
  try {
    const result = await api("/api/settings/test", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const preview = result.responsePreview ? `，响应：${result.responsePreview}` : "";
    state.settingsTestResult = {
      ok: true,
      message: `连接成功，HTTP ${result.status}，耗时 ${result.latencyMs}ms${preview}`,
    };
  } catch (error) {
    state.settingsTestResult = {
      ok: false,
      message: error.message || "连接测试失败",
      details: error.data?.details || [],
    };
  } finally {
    state.settingsTesting = false;
    renderSettings();
  }
}

async function saveAuthSettings() {
  const username = $("auth-username").value;
  const password = $("auth-password").value;
  const clearAuth = $("auth-clear").checked;
  state.authDraft = { username, clearAuth };
  state.authError = null;
  if (!clearAuth && !password) {
    state.authError = "请填写新密码";
    renderSettings();
    return;
  }
  try {
    const body = clearAuth ? { clearAuth: true } : { username, password };
    const result = await api("/api/settings/auth", { method: "POST", body: JSON.stringify(body) });
    state.authSettings = result;
    state.authDraft = null;
    toast(clearAuth ? "已清除登录认证" : "认证设置已保存");
    state.auth = await api("/api/auth/status");
    renderSettings();
  } catch (error) {
    state.authError = `${error.message}${error.data?.details ? "：" + error.data.details.join("；") : ""}`;
    renderSettings();
  }
}


export {
  loadSettings,
  renderSettings,
  collectSettingsPayload,
  saveSettings,
  testSettings,
  saveAuthSettings,
};
