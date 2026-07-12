/**
 * App bootstrap: view router, event delegation (data-action), init.
 * Zero build step — loaded as <script type="module">.
 */
import { state } from './state.js';
import { app, registerActions } from './core.js';
import { escapeHtml } from './utils.js';
import { $, toast, setPracticeModeClass, setView, updateAuthChrome } from './ui.js';
import { api } from './api.js';

import * as importView from './views/import_view.js';
import * as libraryView from './views/library_view.js';
import * as practiceView from './views/practice_view.js';
import * as settingsView from './views/settings_view.js';

async function navigate(view) {
  if (view !== "practice") {
    // Leaving practice clears immersion chrome, keeps question cached for return
  }
  setView(view);
  render();
  if (view === "library" || view === "practice_select") await libraryView.loadLibrary();
  if (view === "settings") await settingsView.loadSettings();
  if (view === "practice_history") await practiceView.loadPracticeHistory();
  if (view === "practice" && !state.practiceQuestion) {
    await practiceView.refreshPracticeTotal();
    render();
  }
}



function render() {
  updateAuthChrome();
  if (state.view === "login") return renderLogin();
  if (state.view === "import") return importView.renderImport();
  if (state.view === "library") return libraryView.renderLibrary();
  if (state.view === "practice_select") return libraryView.renderPracticeSelect();
  if (state.view === "edit") return libraryView.renderEdit();
  if (state.view === "practice") return practiceView.renderPractice();
  if (state.view === "practice_history") return practiceView.renderPracticeHistory();
  if (state.view === "settings") return settingsView.renderSettings();
}

/* ===================== Auth ===================== */

function renderLogin() {
  const err = state.authError;
  $("app").innerHTML = `
    <div class="login-page">
      <form class="login-card" autocomplete="on" data-action="login" data-submit="1">
        <div class="login-brand">
          <span class="brand-mark">TR</span>
          <strong>TOEFL Review</strong>
        </div>
        <h1>登录</h1>
        ${err ? `<div class="status error">${escapeHtml(err)}</div>` : ""}
        <div class="field">
          <label>用户名</label>
          <input id="login-username" type="text" autocomplete="username" autofocus />
        </div>
        <div class="field">
          <label>密码</label>
          <input id="login-password" type="password" autocomplete="current-password" />
        </div>
        <div class="toolbar actions">
          <button class="btn primary" type="submit" ${state.authLoading ? "disabled" : ""}>
            ${state.authLoading ? "登录中..." : "登录"}
          </button>
        </div>
      </form>
    </div>
  `;
}

async function login() {
  const username = $("login-username").value;
  const password = $("login-password").value;
  state.authLoading = true;
  state.authError = null;
  renderLogin();
  try {
    await api("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) });
    state.auth = { authRequired: true, authed: true, username };
    state.authLoading = false;
    navigate("import");
  } catch (error) {
    state.authLoading = false;
    state.authError = error.message || "登录失败";
    renderLogin();
  }
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {}
  state.auth = { authRequired: true, authed: false };
  setView("login");
  render();
}



async function initApp() {
  try {
    state.auth = await api("/api/auth/status");
  } catch {
    state.auth = { authRequired: false, authed: true };
  }
  if (state.auth.authRequired && !state.auth.authed) {
    setView("login");
    render();
  } else {
    navigate("import");
  }
}



// Bind registry so view modules can call render/navigate without circular imports
app.render = render;
app.navigate = navigate;

// ---- Event delegation (replaces inline onclick / onchange / oninput / drag) ----
const ACTIONS = {
  ...Object.fromEntries(Object.entries(importView).filter(([, v]) => typeof v === 'function')),
  ...Object.fromEntries(Object.entries(libraryView).filter(([, v]) => typeof v === 'function')),
  ...Object.fromEntries(Object.entries(practiceView).filter(([, v]) => typeof v === 'function')),
  ...Object.fromEntries(Object.entries(settingsView).filter(([, v]) => typeof v === 'function')),
  navigate,
  login,
  logout,
  render,
};

registerActions(ACTIONS);

function argOf(el) {
  const raw = el.getAttribute('data-arg');
  if (raw == null || raw === '') return undefined;
  if (/^-?\d+$/.test(raw)) return Number(raw);
  return raw;
}

function dispatchAction(el, event) {
  const name = el.getAttribute('data-action');
  if (!name) return false;
  const fn = app.actions[name] || ACTIONS[name];
  if (typeof fn !== 'function') {
    console.warn('Unknown data-action:', name);
    return false;
  }
  if (el.getAttribute('data-prevent') === '1') event.preventDefault();

  const filterKey = el.getAttribute('data-filter-key');
  if (filterKey != null) {
    fn(filterKey, el.value);
    return true;
  }
  if (el.getAttribute('data-value-from') === 'this') {
    fn(el.value);
    return true;
  }
  const arg = argOf(el);
  if (arg !== undefined) fn(arg);
  else fn();
  return true;
}

function closestAction(target, attr = 'data-action') {
  return target && target.closest ? target.closest(`[${attr}]`) : null;
}

/**
 * Native <select> opens its option list on click/mousedown. If we run a
 * data-action on click that re-renders the page (e.g. setImportTypeHint →
 * renderImport), the select node is destroyed and the menu vanishes immediately.
 * Same for checkboxes: their state is driven by change, not click.
 * Clicks on selects must be ignored; only the change event may dispatch.
 */
function shouldIgnoreClickAction(el) {
  return Boolean(
    el &&
      (el.matches('select[data-action]') ||
        el.matches('input[type="checkbox"][data-action]') ||
        el.matches('input[type="radio"][data-action]')),
  );
}

document.addEventListener('click', (event) => {
  const el = closestAction(event.target, 'data-action');
  if (!el) return;
  if (shouldIgnoreClickAction(el)) return;
  dispatchAction(el, event);
});

document.addEventListener('change', (event) => {
  const el = closestAction(event.target, 'data-action');
  if (!el) return;
  dispatchAction(el, event);
});

document.addEventListener('input', (event) => {
  const el = closestAction(event.target, 'data-action');
  if (!el) return;
  const name = el.getAttribute('data-action');
  if (['onReadingChoiceRawInput', 'onCompleteWordsRawInput', 'debouncedSearch'].includes(name)) {
    dispatchAction(el, event);
  }
});

document.addEventListener('dragstart', (event) => {
  const el = closestAction(event.target, 'data-action-dragstart');
  if (!el) return;
  const fn = ACTIONS.dragWord;
  if (fn) fn(event, argOf(el));
});

document.addEventListener('dragover', (event) => {
  const el = closestAction(event.target, 'data-action-dragover');
  if (el) event.preventDefault();
});

document.addEventListener('drop', (event) => {
  const el = closestAction(event.target, 'data-action-drop');
  if (!el) return;
  const fn = ACTIONS.dropWord;
  if (fn) fn(event, argOf(el));
});


document.addEventListener('submit', (event) => {
  const el = closestAction(event.target, 'data-action');
  if (!el || el.getAttribute('data-submit') !== '1') return;
  event.preventDefault();
  dispatchAction(el, event);
});

// Top nav
document.querySelectorAll('.top-nav-btn').forEach((button) => {
  if (button.id === 'logout-btn') return;
  button.addEventListener('click', () => navigate(button.dataset.view));
});

const logoutBtn = document.getElementById('logout-btn');
if (logoutBtn) {
  logoutBtn.addEventListener('click', () => logout());
}

initApp();
