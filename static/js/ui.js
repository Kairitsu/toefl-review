/** DOM helpers and chrome updates. */
import { state } from './state.js';

const $ = (id) => document.getElementById(id);


function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    node.hidden = true;
  }, 2600);
}


function setPracticeModeClass(active) {
  document.body.classList.toggle("practice-mode", Boolean(active));
}

function setView(view) {
  state.view = view;
  state.formValidation = null;
  document.querySelectorAll(".top-nav-btn").forEach((button) => {
    if (button.id === "logout-btn") return;
    button.classList.toggle("active", button.dataset.view === view);
  });
  // Full exam immersion only while answering a question
  setPracticeModeClass(view === "practice" && Boolean(state.practiceQuestion));
}

function updateAuthChrome() {
  const logoutBtn = document.getElementById("logout-btn");
  const authed = state.auth && state.auth.authRequired && state.auth.authed;
  document.body.classList.toggle("login-mode", state.view === "login");
  if (logoutBtn) logoutBtn.hidden = !authed;
}



export { $, toast, setPracticeModeClass, setView, updateAuthChrome };
