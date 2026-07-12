/** JSON API client (same-origin fetch). */
import { state } from './state.js';
import { setView } from './ui.js';
import { app } from './core.js';

function looksLikeHtml(text) {
  const sample = String(text || "").trim().slice(0, 200).toLowerCase();
  return (
    sample.startsWith("<!doctype") ||
    sample.startsWith("<html") ||
    sample.includes("<body") ||
    sample.includes("internal server error") && sample.includes("<")
  );
}

/**
 * Parse API response body safely.
 * Never treat raw HTML / non-JSON bodies as the user-visible error message.
 */
function parseResponseBody(text, response) {
  const raw = text == null ? "" : String(text);
  if (!raw.trim()) {
    return {
      error: response.status >= 500 ? "服务器解析失败，请查看服务日志" : response.statusText || "请求失败",
      details: response.status >= 500 ? ["服务器返回了空响应"] : [],
    };
  }
  try {
    const data = JSON.parse(raw);
    if (data && typeof data === "object") return data;
    return { error: "服务器返回了非对象 JSON", details: [] };
  } catch {
    if (looksLikeHtml(raw) || response.status >= 500) {
      return {
        error: "服务器解析失败，请查看服务日志",
        details: ["服务器返回了非 JSON 错误页，完整内容未展示"],
      };
    }
    // Non-HTML, non-JSON: keep a short snippet only
    const snippet = raw.replace(/\s+/g, " ").trim().slice(0, 120);
    return {
      error: snippet || response.statusText || "请求失败",
      details: ["响应不是有效 JSON"],
    };
  }
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  const data = parseResponseBody(text, response);
  if (!response.ok) {
    if (response.status === 401 && state.view !== "login") {
      state.auth = { authRequired: true, authed: false };
      setView("login");
      if (app.render) app.render();
    }
    const error = new Error(data.error || response.statusText || "请求失败");
    error.data = data;
    error.status = response.status;
    throw error;
  }
  return data;
}



export { api, parseResponseBody, looksLikeHtml };
