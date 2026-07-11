/** JSON API client (same-origin fetch). */
import { state } from './state.js';
import { setView } from './ui.js';
import { app } from './core.js';

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: text || response.statusText };
  }
  if (!response.ok) {
    if (response.status === 401 && state.view !== "login") {
      state.auth = { authRequired: true, authed: false };
      setView("login");
      if (app.render) app.render();
    }
    const error = new Error(data.error || response.statusText);
    error.data = data;
    error.status = response.status;
    throw error;
  }
  return data;
}



export { api };
