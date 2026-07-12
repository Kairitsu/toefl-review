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

import {
  questionFormHtml,
  collectQuestionForm,
  changeFormType,
  saveQuestion,
  validationHtml,
  confirmationBanner,
  defaultData,
  normalizeFormQuestion,
  errorHtml,
  progressHtml,
} from "./import_view.js";


const render = (...args) => app.render(...args);
const navigate = (...args) => app.navigate(...args);

async function loadLibrary() {
  const params = new URLSearchParams();
  Object.entries(state.filters).forEach(([key, value]) => {
    if (value) params.set(key === "q" ? "q" : key, value);
  });
  try {
    const questions = await api(`/api/questions?${params}`);
    state.library = questions.items || [];
  } catch (error) {
    state.library = [];
    toast(error.message || "加载题库失败");
  }
  render();
}

function formatTime(iso) {
  if (!iso) return "未练习";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

function renderLibrary() {
  const f = state.filters;
  $("app").innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>题库</h1>
          <p class="subtle">共 ${state.library.length} 道题 · 筛选、排序、练习与管理</p>
        </div>
        <button class="btn primary" type="button" data-action="navigate" data-arg="import">导入新题</button>
      </div>
      <section class="panel">
        <div class="filters">
          <select data-action="updateFilter" data-filter-key="type" data-value-from="this" aria-label="题型筛选">
            <option value="">全部题型</option>
            ${Object.entries(TYPE_NAMES)
              .map(([value, label]) => `<option value="${value}" ${f.type === value ? "selected" : ""}>${label}</option>`)
              .join("")}
          </select>
          <select data-action="updateFilter" data-filter-key="sort" data-value-from="this" aria-label="排序">
            <option value="created" ${f.sort === "created" ? "selected" : ""}>按创建时间</option>
            <option value="error_rate" ${f.sort === "error_rate" ? "selected" : ""}>按错误率排序</option>
            <option value="recent_practice" ${f.sort === "recent_practice" ? "selected" : ""}>按最近练习时间</option>
          </select>
          <input value="${attr(f.q)}" data-action="debouncedSearch" data-value-from="this" placeholder="搜索题干或文章" aria-label="搜索" />
        </div>
        <div class="question-list">
          ${
            state.library.length
              ? state.library.map((q) => questionCardHtml(q)).join("")
              : `<div class="empty">暂无题目。先从导入页添加一道错题。</div>`
          }
        </div>
      </section>
    </div>
  `;
}

function renderPracticeSelect() {
  const f = state.filters;
  const selCount = state.librarySelected.size;
  $("app").innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>选择练习题目</h1>
          <p class="subtle">共 ${state.library.length} 道题 · 勾选后点击「开始练习」</p>
        </div>
        <button class="btn" type="button" data-action="navigate" data-arg="practice">返回练习</button>
      </div>
      <section class="panel">
        <div class="filters">
          <select data-action="updateFilter" data-filter-key="type" data-value-from="this" aria-label="题型筛选">
            <option value="">全部题型</option>
            ${Object.entries(TYPE_NAMES)
              .map(([value, label]) => `<option value="${value}" ${f.type === value ? "selected" : ""}>${label}</option>`)
              .join("")}
          </select>
          <select data-action="updateFilter" data-filter-key="sort" data-value-from="this" aria-label="排序">
            <option value="created" ${f.sort === "created" ? "selected" : ""}>按创建时间</option>
            <option value="error_rate" ${f.sort === "error_rate" ? "selected" : ""}>按错误率排序</option>
            <option value="recent_practice" ${f.sort === "recent_practice" ? "selected" : ""}>按最近练习时间</option>
          </select>
          <input value="${attr(f.q)}" data-action="debouncedSearch" data-value-from="this" placeholder="搜索题干或文章" aria-label="搜索" />
        </div>
        <div class="question-list">
          ${
            state.library.length
              ? state.library.map((q) => questionCardHtml(q, true)).join("")
              : `<div class="empty">暂无题目。先从导入页添加题目。</div>`
          }
        </div>
      </section>
      <div class="selection-bar" id="selection-bar" ${selCount ? "" : "hidden"}>
        <span id="selection-count">已选 ${selCount} 道</span>
        <div class="selection-actions">
          <button class="btn" type="button" data-action="clearLibrarySelection">取消</button>
          <button class="btn primary" type="button" data-action="startPracticeFromSelection">开始练习</button>
        </div>
      </div>
    </div>
  `;
}

function questionCardHtml(q, selectable = false) {
  const stats = q.stats || {};
  const errorRate = Number(stats.errorRate || 0);
  const highError = (stats.attempts || 0) >= 2 && errorRate >= 50;
  const snippet =
    q.type === "complete_words" ? q.data?.passageText || "" : q.prompt || q.article || q.data?.completeSentence || "";
  const titleHtml =
    q.type === "build_sentence"
      ? `<h3 style="margin-top:10px">${escapeHtml(truncate(q.prompt || "写作造句题", 80))}</h3>`
      : q.type === "complete_words"
        ? `<h3 style="margin-top:10px">阅读填词题</h3>`
        : `<h3 style="margin-top:10px">${escapeHtml(q.title || "未命名题目")}</h3>`;
  const selected = state.librarySelected.has(q.id);
  const selectHtml = selectable
    ? `<label class="card-select"><input type="checkbox" ${selected ? "checked" : ""} data-action="toggleLibrarySelect" data-arg="${q.id}" /></label>`
    : "";
  const actionsHtml = selectable
    ? ""
    : `<div class="card-actions">
         <button class="btn small primary" type="button" data-action="practiceQuestion" data-arg="${q.id}">练习</button>
         <button class="btn small" type="button" data-action="editQuestion" data-arg="${q.id}">编辑</button>
         <button class="btn small danger" type="button" data-action="deleteQuestion" data-arg="${q.id}">删除</button>
       </div>`;
  return `
    <article class="question-card ${highError ? "high-error" : ""} ${selected ? "selected" : ""}" data-id="${q.id}">
      <div class="question-card-head">
        ${selectHtml}
        <div>
          <div class="card-meta">
            <span class="type-badge">${TYPE_NAMES[q.type] || q.type}</span>
            ${highError ? `<span class="pill bad">高错误率 ${errorRate}%</span>` : ""}
          </div>
          ${titleHtml}
          <p class="subtle">${escapeHtml(truncate(snippet, 140))}</p>
          <div class="metrics">
            <span class="metric">做过 ${stats.attempts || 0}</span>
            <span class="metric">做对 ${stats.correct || 0}</span>
            <span class="metric">做错 ${stats.incorrect || 0}</span>
            <span class="metric ${highError ? "hot" : ""}">重复错误率 ${errorRate}%</span>
            <span class="metric">最近 ${escapeHtml(formatTime(stats.lastPracticedAt || q.lastPracticedAt))}</span>
          </div>
        </div>
        ${actionsHtml}
      </div>
    </article>
  `;
}

function truncate(value, max) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

let searchTimer = null;
function debouncedSearch(value) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => updateFilter("q", value), 250);
}

async function updateFilter(key, value) {
  state.filters[key] = value;
  await loadLibrary();
}

function toggleLibrarySelect(id) {
  id = Number(id);
  if (state.librarySelected.has(id)) {
    state.librarySelected.delete(id);
  } else {
    state.librarySelected.add(id);
  }
  const count = state.librarySelected.size;
  const bar = document.getElementById("selection-bar");
  if (bar) bar.hidden = count === 0;
  const label = document.getElementById("selection-count");
  if (label) label.textContent = `已选 ${count} 道`;
  const card = document.querySelector(`.question-card[data-id="${id}"]`);
  if (card) card.classList.toggle("selected", state.librarySelected.has(id));
}

function clearLibrarySelection() {
  state.librarySelected = new Set();
  render();
}

function startPracticeFromSelection() {
  const ids = [...state.librarySelected];
  if (!ids.length) return;
  const idSet = new Set(ids);
  const questions = state.library.filter((q) => idSet.has(q.id));
  if (!questions.length) return;
  state.practiceQuestions = questions;
  state.practiceSessionIndex = 0;
  state.practiceFinished = false;
  state.practiceTarget = questions.length;
  state.librarySelected = new Set();
  if (app.actions.goToQuestion) app.actions.goToQuestion(0);
}

async function editQuestion(id) {
  const question = await api(`/api/questions/${id}`);
  state.editQuestion = question;
  setView("edit");
  render();
}

function renderEdit() {
  const q = state.editQuestion;
  $("app").innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>编辑题目</h1>
          <p class="subtle">保存时会重新校验题目结构，防止字段损坏。</p>
        </div>
        <button class="btn" type="button" data-action="navigate" data-arg="library">返回题库</button>
      </div>
      <section class="panel">
        ${validationHtml(state.formValidation)}
        ${questionFormHtml(q, "edit")}
        <div class="toolbar actions">
          <button class="btn primary" type="button" data-action="saveQuestion" data-arg="edit">保存修改</button>
          <button class="btn" type="button" data-action="navigate" data-arg="library">取消</button>
        </div>
      </section>
    </div>
  `;
}

async function deleteQuestion(id) {
  if (!confirm("确认删除这道题？历史练习记录也会一起删除。")) return;
  await api(`/api/questions/${id}`, { method: "DELETE" });
  toast("题目已删除");
  await loadLibrary();
}

/* ===================== Practice ===================== */


export {
  loadLibrary,
  formatTime,
  renderLibrary,
  renderPracticeSelect,
  questionCardHtml,
  truncate,
  debouncedSearch,
  updateFilter,
  toggleLibrarySelect,
  clearLibrarySelection,
  startPracticeFromSelection,
  editQuestion,
  renderEdit,
  deleteQuestion,
};
