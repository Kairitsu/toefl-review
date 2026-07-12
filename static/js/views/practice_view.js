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
  formatTime,
  truncate,
  questionCardHtml,
  loadLibrary,
  renderLibrary,
} from "./library_view.js";
import {
  countTemplateBlanksClient,
  normalizeTemplateClient,
} from "./import_view.js";


const render = (...args) => app.render(...args);
const navigate = (...args) => app.navigate(...args);

async function refreshPracticeTotal() {
  try {
    const data = await api("/api/questions");
    state.practiceTotal = (data.items || []).length;
  } catch {
    state.practiceTotal = 0;
  }
}

function examBarHtml(q) {
  const section = TYPE_SECTIONS[q?.type] || "Practice";
  const total = state.practiceQuestions.length || 1;
  const index = Number(state.practiceSessionIndex) || 0;
  const progressLabel = `第 ${index + 1} / ${total} 题`;
  const submitted = Boolean(state.practiceResult && !state.practiceResult.error);
  const atLast = index >= total - 1;
  const atFirst = index <= 0;
  const nextLabel = atLast ? (submitted ? "完成" : "结束") : "下一题";
  return `
    <header class="exam-bar">
      <div class="exam-bar-inner">
        <div class="exam-meta">
          <span class="section-label">${escapeHtml(section)}</span>
          <span class="divider">|</span>
          <span class="q-progress">${progressLabel}</span>
          ${submitted ? `<span class="pill ${state.practiceResult.isCorrect ? "ok" : "bad"}" style="margin-left:6px">${state.practiceResult.isCorrect ? "Correct" : "Incorrect"}</span>` : ""}
        </div>
        <div class="exam-actions">
          <button type="button" class="btn exam" data-action="exitPractice">退出</button>
          <button type="button" class="btn exam" data-action="prevQuestion" ${atFirst ? "disabled" : ""}>上一题</button>
          <button type="button" class="btn exam solid" data-action="nextQuestion">${nextLabel}</button>
        </div>
      </div>
    </header>
  `;
}

function renderPractice() {
  const q = state.practiceQuestion;

  if (state.practiceFinished) {
    setPracticeModeClass(false);
    const total = state.practiceQuestions.length || 0;
    const correct = state.practiceQuestions.filter((q) => q._result?.isCorrect).length;
    const wrong = total - correct;
    const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
    const viewingHistory = Boolean(state.viewedSession);
    const reportTitle = viewingHistory
      ? `练习记录 · ${formatSessionTime(state.viewedSession.createdAt)}`
      : "本轮学习报告";
    if (total === 0) {
      $("app").innerHTML = `
        <div class="page">
          <div class="practice-home">
            <section class="panel practice-summary">
              <h1>练习完成</h1>
              <p class="subtle">本轮没有练习记录。</p>
              <div class="toolbar" style="justify-content:center;margin-top:18px;flex-wrap:wrap">
                <button class="btn primary" type="button" data-action="restartPractice">再来一轮</button>
                <button class="btn" type="button" data-action="navigate" data-arg="practice_history">查看记录列表</button>
                <button class="btn" type="button" data-action="exitPractice">返回首页</button>
              </div>
            </section>
          </div>
        </div>
      `;
      return;
    }
    const items = filteredReportItems();
    const selectedIndex = Math.min(state.reportSelectedIndex, total - 1);
    const selectedQ = state.practiceQuestions[selectedIndex];
    $("app").innerHTML = `
      <div class="page report-page">
        <div class="report-head">
          <h1>${escapeHtml(reportTitle)}</h1>
          ${reportStatsHtml(total, correct, wrong, pct)}
          ${reportFilterHtml()}
        </div>
        <div class="report-layout">
          ${reportListHtml(items, selectedIndex)}
          ${reportDetailHtml(selectedQ, selectedIndex)}
        </div>
        <div class="toolbar" style="justify-content:center;margin-top:18px;flex-wrap:wrap">
          ${viewingHistory ? "" : `<button class="btn primary" type="button" data-action="restartPractice">再来一轮</button>`}
          <button class="btn ${viewingHistory ? "primary" : ""}" type="button" data-action="redoCurrentSession">重新练习本轮</button>
          <button class="btn" type="button" data-action="navigate" data-arg="practice_history">查看记录列表</button>
          <button class="btn" type="button" data-action="exitPractice">返回首页</button>
        </div>
      </div>
    `;
    return;
  }

  if (!q) {
    setPracticeModeClass(false);
    const target = state.practiceTarget || 0;
    const presets = [5, 10, 15, 20];
    const maxNum = state.practiceTotal || 999;
    $("app").innerHTML = `
      <div class="page">
        <div class="practice-home">
          <section class="panel">
            <h1>开始练习</h1>
            <p class="subtle">选择题数后开始练习，或从题库中勾选指定题目练习。</p>
            <div class="target-row">
              <span class="target-label">题数</span>
              <div class="segmented">
                ${presets
                  .map(
                    (n) =>
                      `<button type="button" class="practice-target-btn ${target === n ? "active" : ""}" data-target="${n}" data-action="setPracticeTarget" data-arg="${n}">${n}</button>`,
                  )
                  .join("")}
              </div>
              <input type="number" class="target-input" id="practice-target-input" min="1" max="${maxNum}" value="${presets.includes(target) ? "" : target}" placeholder="自定义" data-action="setPracticeTargetFromInput" />
            </div>
            ${
              state.practiceResult?.error
                ? `<div class="status error">${escapeHtml(state.practiceResult.error)}</div>`
                : `<div class="status soft-info">题库中约有 ${state.practiceTotal || 0} 道题可供练习。</div>`
            }
            <div class="toolbar" style="justify-content:center;margin-top:18px;flex-wrap:wrap">
              <button class="btn primary" type="button" data-action="nextPractice">开始练习</button>
              <button class="btn" type="button" data-action="navigate" data-arg="practice_select">从题库选择</button>
              <button class="btn" type="button" data-action="navigate" data-arg="practice_history">练习记录</button>
            </div>
          </section>
        </div>
      </div>
    `;
    return;
  }

  setPracticeModeClass(true);
  $("app").innerHTML = `
    <div class="exam-shell">
      ${examBarHtml(q)}
      <div class="exam-body centered">
        <div class="exam-canvas ${q.type === "reading_choice" ? "wide" : ""}">
          ${practiceQuestionHtml(q)}
          ${state.practiceResult ? resultHtml(q, state.practiceResult) : ""}
        </div>
      </div>
    </div>
  `;

  // Restore complete-words answers after re-render
  if (q.type === "complete_words" && !state.practiceResult) {
    initCompleteLetterInputs();
  }

  if (q.type === "reading_choice" && !state.practiceResult) {
    document.querySelectorAll('input[name="reading-choice"]').forEach((input) => {
      input.addEventListener("change", () => {
        state.selectedChoice = input.value;
        document.querySelectorAll(".option").forEach((el) => el.classList.remove("selected"));
        input.closest(".option")?.classList.add("selected");
      });
    });
  }
}

function setPracticeMode(mode) {
  state.practiceMode = mode;
  state.practiceQuestion = null;
  state.practiceQuestions = [];
  state.practiceResult = null;
  state.practiceFinished = false;
  setPracticeModeClass(false);
  renderPractice();
}

function showPracticeHelp() {
  toast("点击词块填入空位；再点空位可撤回。阅读题点选选项后提交。");
}

function exitPractice() {
  state.practiceQuestion = null;
  state.practiceQuestions = [];
  state.practiceResult = null;
  state.practiceFinished = false;
  state.practiceSessionIndex = 0;
  state.reportFilter = "all";
  state.reportSelectedIndex = 0;
  state.viewedSession = null;
  state.practiceSavedSessionId = null;
  setPracticeModeClass(false);
  renderPractice();
}

function restartPractice() {
  state.practiceFinished = false;
  state.practiceQuestion = null;
  state.practiceQuestions = [];
  state.practiceResult = null;
  state.practiceSessionIndex = 0;
  state.reportFilter = "all";
  state.reportSelectedIndex = 0;
  state.viewedSession = null;
  state.practiceSavedSessionId = null;
  nextPractice();
}

function stripResult(q) {
  if (!q) return q;
  return {
    id: q.id,
    type: q.type,
    title: q.title || "",
    article: q.article || "",
    prompt: q.prompt || "",
    explanation: q.explanation || "",
    data: q.data,
  };
}

async function saveCurrentSession() {
  const qs = state.practiceQuestions;
  if (!qs || !qs.length) return;
  const items = qs.map((q) => ({
    question: stripResult(q),
    answer: (q._result && q._result.answer) || {},
    is_correct: Boolean(q._result && q._result.isCorrect),
    detail: (q._result && q._result.detail) || {},
  }));
  const correct = qs.filter((q) => q._result && q._result.isCorrect).length;
  const total = qs.length;
  const wrong = total - correct;
  const accuracy = total > 0 ? correct / total : 0;
  try {
    const data = await api("/api/practice/sessions", {
      method: "POST",
      body: JSON.stringify({ total, correct, wrong, accuracy, items }),
    });
    state.practiceSavedSessionId = data.id;
  } catch (error) {
    toast("练习记录保存失败：" + (error.message || "未知错误"));
  }
}

function setPracticeTarget(n) {
  state.practiceTarget = n;
  document.querySelectorAll(".practice-target-btn").forEach((btn) => {
    btn.classList.toggle("active", parseInt(btn.dataset.target, 10) === n);
  });
  const input = document.getElementById("practice-target-input");
  if (input) input.value = "";
}

function setPracticeTargetFromInput() {
  const input = document.getElementById("practice-target-input");
  if (!input) return;
  let val = parseInt(input.value, 10);
  if (isNaN(val) || val < 1) {
    toast("请输入有效的题数");
    input.value = "";
    return;
  }
  if (state.practiceTotal > 0 && val > state.practiceTotal) {
    val = state.practiceTotal;
    input.value = val;
    toast(`题库共有 ${state.practiceTotal} 道题，已调整为 ${val}`);
  }
  state.practiceTarget = val;
  document.querySelectorAll(".practice-target-btn").forEach((btn) => {
    btn.classList.toggle("active", parseInt(btn.dataset.target, 10) === val);
  });
}

async function nextPractice() {
  try {
    if (!state.practiceTotal) await refreshPracticeTotal();
    const target = Math.max(1, state.practiceTarget || 10);
    const data = await api(`/api/practice/next?mode=${encodeURIComponent(state.practiceMode)}&count=${target}`);
    const items = data.items || (data.id ? [data] : []);
    if (!items.length) {
      state.practiceQuestion = null;
      state.practiceQuestions = [];
      state.practiceResult = { error: "没有符合条件的题目" };
      state.practiceFinished = false;
      setPracticeModeClass(false);
      renderPractice();
      return;
    }
    state.practiceQuestions = items;
    state.practiceSessionIndex = 0;
    state.practiceFinished = false;
    goToQuestion(0);
  } catch (error) {
    state.practiceQuestion = null;
    state.practiceQuestions = [];
    state.practiceResult = { error: error.message };
    state.practiceFinished = false;
    setPracticeModeClass(false);
    renderPractice();
  }
}

function nextQuestion() {
  const total = state.practiceQuestions.length;
  const index = Number(state.practiceSessionIndex) || 0;
  if (index >= total - 1) {
    state.practiceFinished = true;
    state.practiceQuestion = null;
    state.practiceResult = null;
    state.reportFilter = "all";
    state.reportSelectedIndex = 0;
    setPracticeModeClass(false);
    renderPractice();
    if (!state.viewedSession && !state.practiceSavedSessionId && total > 0) {
      saveCurrentSession();
    }
    return;
  }
  goToQuestion(index + 1);
}

function prevQuestion() {
  const index = Number(state.practiceSessionIndex) || 0;
  if (index > 0) goToQuestion(index - 1);
}

function goToQuestion(index) {
  const q = state.practiceQuestions[index];
  if (!q) return;
  state.practiceSessionIndex = index;
  state.practiceQuestion = q;
  state.practiceResult = q._result || null;
  state.selectedChoice = "";
  state.completeAnswers = {};
  state.activeBlankIndex = 0;
  if (q.type === "build_sentence") {
    state.buildOrderIndices = Array.from({ length: countPracticeBlanks(q) }, () => null);
  }
  setView("practice");
  render();
}

async function practiceQuestion(id) {
  const question = await api(`/api/questions/${id}`);
  if (!state.practiceTotal) await refreshPracticeTotal();
  state.practiceQuestions = [question];
  state.practiceSessionIndex = 0;
  state.practiceFinished = false;
  goToQuestion(0);
}

function practiceQuestionHtml(q) {
  if (q.type === "reading_choice") return readingPracticeHtml(q);
  if (q.type === "build_sentence") return buildPracticeHtml(q);
  return completePracticeHtml(q);
}

function readingPracticeHtml(q) {
  const submitted = Boolean(state.practiceResult && !state.practiceResult.error);
  const detail = state.practiceResult?.detail || {};
  const selected = state.selectedChoice || detail.selected || "";
  const correctAnswer = detail.correctAnswer;

  return `
    <div class="reading-layout">
      <div class="reading-passage">
        <div class="passage-label">Passage</div>
        <h2>${escapeHtml(q.title || "Reading Passage")}</h2>
        <div class="article-box">${escapeHtml(q.article)}</div>
      </div>
      <div class="reading-divider" aria-hidden="true"></div>
      <div class="reading-question">
        <div class="q-label">Question</div>
        <h3>${escapeHtml(q.prompt)}</h3>
        <div class="options" role="radiogroup" aria-label="选项">
          ${(q.data.options || [])
            .map((option) => {
              const isSelected = selected === option.key;
              let extra = isSelected ? "selected" : "";
              if (submitted) {
                if (option.key === correctAnswer) extra += " correct-option";
                else if (isSelected && option.key !== correctAnswer) extra += " wrong-option";
              }
              return `
                <label class="option ${extra.trim()}">
                  <input type="radio" name="reading-choice" value="${attr(option.key)}" ${isSelected ? "checked" : ""} ${submitted ? "disabled" : ""} />
                  <span class="option-key">${escapeHtml(option.key)}</span>
                  <span class="option-text">${escapeHtml(option.text)}</span>
                </label>
              `;
            })
            .join("")}
        </div>
        ${
          submitted
            ? ""
            : `<button class="btn primary" type="button" data-action="submitPractice" style="align-self:flex-start;min-width:120px">提交答案</button>`
        }
      </div>
    </div>
  `;
}

function countPracticeBlanks(q) {
  const template = normalizeTemplateClient(q.data?.sentenceTemplate || "");
  const count = countTemplateBlanksClient(template);
  return count || q.data?.correctOrder?.length || q.data?.wordBank?.length || 0;
}

function estimateBlankWidth(word) {
  if (!word) return "";
  const ch = Math.max(4, Math.min(22, String(word).length + 1));
  return `style="min-width:${ch * 0.62}em"`;
}

function buildPracticeHtml(q) {
  const data = q.data || {};
  const wordBank = data.wordBank || [];
  const used = new Set(state.buildOrderIndices.filter((item) => item !== null).map(String));
  const submitted = Boolean(state.practiceResult && !state.practiceResult.error);
  const positions = state.practiceResult?.detail?.positions || [];

  // Ensure active blank points to first empty if current is filled
  if (!submitted) {
    if (
      state.activeBlankIndex == null ||
      state.activeBlankIndex < 0 ||
      state.activeBlankIndex >= state.buildOrderIndices.length ||
      state.buildOrderIndices[state.activeBlankIndex] !== null
    ) {
      const firstEmpty = state.buildOrderIndices.findIndex((item) => item === null);
      state.activeBlankIndex = firstEmpty >= 0 ? firstEmpty : 0;
    }
  }

  return `
    <p class="bs-prompt">${escapeHtml(q.prompt || "使用待选词完成句子。")}</p>
    ${submitted ? "" : `<p class="bs-hint">点击下方词块填入空位 · 再次点击空位可撤回 · 也支持拖拽词块到空位</p>`}
    <div class="bs-sentence-card">
      <div class="bs-section-label">题目详情</div>
      <div class="bs-sentence" aria-label="句子填空">
        ${renderInteractiveSentence(data.sentenceTemplate || "", wordBank, submitted, positions)}
      </div>
    </div>
    <div class="word-bank-section">
      <div class="word-bank-head">
        <h3>待选词</h3>
        <p class="subtle">${submitted ? "本题已提交" : "选择词块填入当前高亮空位"}</p>
      </div>
      <div class="word-bank">
        ${wordBank
          .map((word, index) => {
            const isUsed = used.has(String(index));
            return `<button type="button" class="word-token ${isUsed ? "used" : ""}" draggable="${submitted || isUsed ? "false" : "true"}" data-action-dragstart="dragWord" data-arg="${index}" data-action="fillWord" data-arg="${index}" ${submitted || isUsed ? "disabled" : ""}>${escapeHtml(word)}</button>`;
          })
          .join("")}
      </div>
    </div>
    ${
      submitted
        ? ""
        : `<div class="bs-actions">
            <button class="btn" type="button" data-action="resetBuildAnswer">重置</button>
            <button class="btn primary" type="button" data-action="submitPractice">提交答案</button>
          </div>`
    }
  `;
}

function renderInteractiveSentence(template, wordBank, submitted, positions) {
  const parts = [];
  const regex = /\{\{\s*(?:blank|\d+)\s*\}\}|_{2,}/gi;
  let last = 0;
  let blankIndex = 0;
  let match;
  const source = normalizeTemplateClient(template);

  while ((match = regex.exec(source))) {
    if (match.index > last) {
      parts.push(renderFixedText(source.slice(last, match.index)));
    }

    const tokenIndex = state.buildOrderIndices[blankIndex];
    const filled = tokenIndex !== null && tokenIndex !== undefined;
    const word = filled ? wordBank[tokenIndex] : "";
    const isActive = !submitted && state.activeBlankIndex === blankIndex;
    let cls = "sentence-blank";
    if (filled) cls += " filled";
    else cls += " empty";
    if (isActive) cls += " active";
    if (submitted && positions[blankIndex]) {
      cls += positions[blankIndex].correct ? " correct" : " wrong";
    }

    const widthAttr = estimateBlankWidth(word || positions[blankIndex]?.expected || "______");
    const label = filled ? escapeHtml(word) : "&nbsp;";
    parts.push(
      `<button type="button" class="${cls}" ${widthAttr} data-action-dragover="prevent" data-action-drop="dropWord" data-arg="${blankIndex}" data-action="onBlankClick" data-arg="${blankIndex}" ${submitted ? "disabled" : ""} aria-label="填空位置 ${blankIndex + 1}">${label}</button>`,
    );
    blankIndex += 1;
    last = regex.lastIndex;
  }

  if (last < source.length) {
    parts.push(renderFixedText(source.slice(last)));
  }

  // Fallback: no template blanks — render pure blank line of slots
  if (blankIndex === 0 && state.buildOrderIndices.length) {
    return state.buildOrderIndices
      .map((tokenIndex, i) => {
        const filled = tokenIndex !== null;
        const word = filled ? wordBank[tokenIndex] : "";
        const isActive = !submitted && state.activeBlankIndex === i;
        let cls = "sentence-blank" + (filled ? " filled" : " empty") + (isActive ? " active" : "");
        if (submitted && positions[i]) cls += positions[i].correct ? " correct" : " wrong";
        return `<button type="button" class="${cls}" data-action-dragover="prevent" data-action-drop="dropWord" data-arg="${i}" data-action="onBlankClick" data-arg="${i}" ${submitted ? "disabled" : ""}>${filled ? escapeHtml(word) : "&nbsp;"}</button>`;
      })
      .join("");
  }

  return parts.join("");
}

function renderFixedText(text) {
  const value = String(text || "");
  if (!value) return "";
  // Keep multi-word fixed phrases (e.g. "during the") as one visual unit when possible
  const trimmed = value.replace(/\s+/g, " ");
  if (/^[A-Za-z][A-Za-z' -]*[A-Za-z]$/.test(trimmed.trim()) && trimmed.trim().includes(" ")) {
    return `<span class="bs-fixed bs-fixed-phrase">${escapeHtml(trimmed)}</span>`;
  }
  return escapeHtml(value)
    .split(/(\s+)/)
    .filter((chunk) => chunk.length)
    .map((chunk) => {
      if (/^\s+$/.test(chunk)) return `<span class="bs-fixed-space">${chunk === " " ? "\u00A0" : chunk}</span>`;
      return `<span class="bs-fixed">${chunk}</span>`;
    })
    .join("");
}

function onBlankClick(slotIndex) {
  if (state.practiceResult && !state.practiceResult.error) return;
  if (state.buildOrderIndices[slotIndex] !== null) {
    state.buildOrderIndices[slotIndex] = null;
    state.activeBlankIndex = slotIndex;
  } else {
    state.activeBlankIndex = slotIndex;
  }
  renderPractice();
}

function fillWord(index) {
  if (state.practiceResult && !state.practiceResult.error) return;
  if (state.buildOrderIndices.includes(index)) return;

  let slot = state.activeBlankIndex;
  if (slot == null || slot < 0 || state.buildOrderIndices[slot] !== null) {
    slot = state.buildOrderIndices.findIndex((item) => item === null);
  }
  if (slot < 0) return;

  state.buildOrderIndices[slot] = index;
  const nextEmpty = state.buildOrderIndices.findIndex((item) => item === null);
  state.activeBlankIndex = nextEmpty >= 0 ? nextEmpty : slot;
  renderPractice();
}

function clearSlot(slotIndex) {
  state.buildOrderIndices[slotIndex] = null;
  state.activeBlankIndex = slotIndex;
  renderPractice();
}

function resetBuildAnswer() {
  state.buildOrderIndices = state.buildOrderIndices.map(() => null);
  state.activeBlankIndex = 0;
  state.practiceResult = null;
  renderPractice();
}

function dragWord(event, index) {
  if (state.buildOrderIndices.includes(index)) {
    event.preventDefault();
    return;
  }
  event.dataTransfer.setData("text/plain", String(index));
  event.dataTransfer.effectAllowed = "move";
}

function dropWord(event, slotIndex) {
  event.preventDefault();
  if (state.practiceResult && !state.practiceResult.error) return;
  const index = Number(event.dataTransfer.getData("text/plain"));
  if (Number.isNaN(index)) return;
  const oldSlot = state.buildOrderIndices.indexOf(index);
  if (oldSlot >= 0) state.buildOrderIndices[oldSlot] = null;
  state.buildOrderIndices[slotIndex] = index;
  const nextEmpty = state.buildOrderIndices.findIndex((item) => item === null);
  state.activeBlankIndex = nextEmpty >= 0 ? nextEmpty : slotIndex;
  renderPractice();
}

function completePracticeHtml(q) {
  const submitted = Boolean(state.practiceResult && !state.practiceResult.error);
  return `
    <div class="cw-wrap">
      <div class="cw-card">
        <p class="cw-kicker">Complete the Words</p>
        <h2 class="cw-title">${escapeHtml(q.prompt || "Fill in the missing letters in the paragraph")}</h2>
        <p class="cw-hint">在空格中补全缺失的字母。只填后半部分，不要重复填写前缀。</p>
        <div class="cw-passage">${renderCompletePassage(q, submitted)}</div>
        ${
          submitted
            ? ""
            : `<div class="cw-actions">
                <button class="btn primary" type="button" data-action="submitPractice">提交答案</button>
              </div>`
        }
      </div>
    </div>
  `;
}

function renderCompletePassage(q, submitted) {
  const passage = q.data?.passageText || "";
  const blanksMeta = Object.fromEntries((q.data?.blanks || []).map((b) => [String(b.id), b]));
  const resultBlanks = Object.fromEntries(
    (state.practiceResult?.detail?.blanks || []).map((b) => [String(b.id), b]),
  );
  const parts = [];
  let last = 0;
  const regex = /\[\[\s*([A-Za-z0-9_-]+)\s*\]\]/g;
  let match;
  while ((match = regex.exec(passage))) {
    // Text before marker may already include prefix letters (civiliza[[1]])
    parts.push(escapeHtml(passage.slice(last, match.index)));
    const id = match[1];
    const meta = blanksMeta[id] || {};
    const result = resultBlanks[id];
    const slotCount = completeBlankSlotCount(meta, result);
    let cls = "";
    let value = state.completeAnswers[id] ?? "";
    if (submitted && result) {
      cls = result.correct ? "blank-ok" : "blank-bad";
      value = result.actual || value;
    }
    parts.push(
      `<span
        class="inline-blank cw-letter-blank ${cls}"
        data-complete-id="${attr(id)}"
        data-slot-count="${attr(slotCount)}"
        role="group"
        aria-label="空格 ${attr(id)} 缺失字母"
      >
        ${completeLetterInputsHtml(id, value, slotCount, submitted, cls)}
      </span>`,
    );
    last = regex.lastIndex;
  }
  parts.push(escapeHtml(passage.slice(last)));
  return parts.join("");
}

function completeBlankSlotCount(meta = {}, result = null) {
  const explicit = Number(meta.blankLength || meta.blankCount || meta.length || 0);
  if (Number.isFinite(explicit) && explicit > 0) return Math.min(32, Math.max(1, Math.round(explicit)));
  const value = String(meta.answer || result?.expected || result?.actual || "");
  if (value) return Math.min(32, Math.max(1, value.length));
  return 4;
}

function completeLetterInputsHtml(id, value, slotCount, submitted, cls = "") {
  const chars = cleanCompleteLetters(value);
  const count = Math.max(1, Number(slotCount) || chars.length || 1);
  return Array.from({ length: count })
    .map(
      (_, index) => `
        <input
          data-complete-id="${attr(id)}"
          data-complete-letter="${index}"
          maxlength="1"
          inputmode="text"
          autocomplete="off"
          spellcheck="false"
          value="${attr(chars[index] || "")}"
          ${submitted ? "disabled" : ""}
          class="cw-letter-cell ${cls}"
          aria-label="空格 ${attr(id)} 第 ${index + 1} 个字母"
        />
      `,
    )
    .join("");
}

function cleanCompleteLetters(value) {
  return Array.from(String(value || "").replace(/[^A-Za-z]/g, ""));
}

function completeLetterGroupInputs(id) {
  return Array.from(document.querySelectorAll(".cw-letter-cell[data-complete-id]"))
    .filter((input) => input.dataset.completeId === String(id))
    .sort((a, b) => Number(a.dataset.completeLetter || 0) - Number(b.dataset.completeLetter || 0));
}

function updateCompleteAnswerFromCells(id) {
  const value = completeLetterGroupInputs(id)
    .map((input) => input.value || "")
    .join("");
  state.completeAnswers[id] = value;
  return value;
}

function collectCompleteWordAnswers() {
  const answers = {};
  document.querySelectorAll(".cw-letter-blank[data-complete-id]").forEach((wrap) => {
    const id = wrap.dataset.completeId;
    answers[id] = updateCompleteAnswerFromCells(id);
  });
  return answers;
}

function focusCompleteLetter(input, select = true) {
  if (!input || input.disabled) return;
  input.focus();
  if (select) input.select();
}

function fillCompleteLetterCells(startInput, chars) {
  const clean = cleanCompleteLetters(chars);
  const group = completeLetterGroupInputs(startInput.dataset.completeId);
  const startIndex = Number(startInput.dataset.completeLetter || 0);
  if (!clean.length) {
    startInput.value = "";
    updateCompleteAnswerFromCells(startInput.dataset.completeId);
    return;
  }
  clean.forEach((char, offset) => {
    const target = group[startIndex + offset];
    if (target) target.value = char;
  });
  updateCompleteAnswerFromCells(startInput.dataset.completeId);
  const next = group[Math.min(startIndex + clean.length, group.length - 1)];
  focusCompleteLetter(next, false);
}

function handleCompleteLetterInput(event) {
  fillCompleteLetterCells(event.currentTarget, event.currentTarget.value);
}

function handleCompleteLetterPaste(event) {
  event.preventDefault();
  const text = event.clipboardData?.getData("text") || "";
  fillCompleteLetterCells(event.currentTarget, text);
}

function handleCompleteLetterKeydown(event) {
  const input = event.currentTarget;
  const group = completeLetterGroupInputs(input.dataset.completeId);
  const index = Number(input.dataset.completeLetter || 0);
  if (event.key === "Backspace") {
    event.preventDefault();
    if (input.value) {
      input.value = "";
      updateCompleteAnswerFromCells(input.dataset.completeId);
      return;
    }
    const previous = group[index - 1];
    if (previous) focusCompleteLetter(previous);
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    focusCompleteLetter(group[index - 1] || input);
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    focusCompleteLetter(group[index + 1] || input);
  }
}

function initCompleteLetterInputs() {
  document.querySelectorAll(".cw-letter-cell[data-complete-id]").forEach((input) => {
    const id = input.dataset.completeId;
    const index = Number(input.dataset.completeLetter || 0);
    const chars = cleanCompleteLetters(state.completeAnswers[id] || "");
    input.value = chars[index] || input.value || "";
    input.addEventListener("focus", () => input.select());
    input.addEventListener("click", () => input.select());
    input.addEventListener("input", handleCompleteLetterInput);
    input.addEventListener("paste", handleCompleteLetterPaste);
    input.addEventListener("keydown", handleCompleteLetterKeydown);
  });
}

async function submitPractice() {
  const q = state.practiceQuestion;
  if (!q) return;
  let answer = {};
  if (q.type === "reading_choice") {
    answer.choice =
      document.querySelector('input[name="reading-choice"]:checked')?.value || state.selectedChoice || "";
    state.selectedChoice = answer.choice;
    if (!answer.choice) {
      toast("请先选择一个选项");
      return;
    }
  }
  if (q.type === "build_sentence") {
    answer.order = state.buildOrderIndices.map((index) => (index === null ? "" : q.data.wordBank[index]));
  }
  if (q.type === "complete_words") {
    answer.blanks = collectCompleteWordAnswers();
  }
  try {
    const result = await api(`/api/questions/${q.id}/attempts`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    });
    state.practiceResult = result;
    state.practiceQuestion._result = result;
    state.practiceQuestion._result.answer = answer;
    state.practiceQuestion.stats = result.stats;
    renderPractice();
    // Scroll result into view
    requestAnimationFrame(() => {
      document.querySelector(".result-card")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  } catch (error) {
    state.practiceResult = { error: error.message };
    renderPractice();
  }
}

function resultHtml(q, result) {
  if (result.error) return `<div class="status error" style="margin-top:18px">${escapeHtml(result.error)}</div>`;
  const ok = Boolean(result.isCorrect);
  return `
    <div class="result-card ${ok ? "is-correct" : "is-wrong"}">
      <div class="result-banner">
        <span>${ok ? "回答正确" : "回答错误"}</span>
        <span style="font-weight:600;font-size:13px;opacity:0.85">${escapeHtml(TYPE_NAMES[q.type] || "")}</span>
      </div>
      <div class="result-body">
        <div class="result-stats">
          <div class="stat-tile"><span class="label">做过</span><span class="value">${result.stats.attempts}</span></div>
          <div class="stat-tile"><span class="label">做对</span><span class="value">${result.stats.correct}</span></div>
          <div class="stat-tile"><span class="label">做错</span><span class="value">${result.stats.incorrect}</span></div>
          <div class="stat-tile"><span class="label">重复错误率</span><span class="value">${result.stats.errorRate}%</span></div>
        </div>
        ${answerReviewHtml(q, result.detail)}
        <div class="result-block">
          <h3>解析</h3>
          <p class="article-box">${escapeHtml(q.explanation || "暂无解析。")}</p>
        </div>
        <div class="toolbar">
          <button class="btn primary" type="button" data-action="nextQuestion">${(Number(state.practiceSessionIndex) || 0) >= state.practiceQuestions.length - 1 ? "完成" : "下一题"}</button>
          <button class="btn" type="button" data-action="prevQuestion" ${(Number(state.practiceSessionIndex) || 0) <= 0 ? "disabled" : ""}>上一题</button>
          <button class="btn" type="button" data-action="retryCurrent">再练一次</button>
          <button class="btn ghost" type="button" data-action="exitPractice">退出练习</button>
        </div>
      </div>
    </div>
  `;
}

function answerReviewHtml(q, detail) {
  if (q.type === "reading_choice") {
    return `
      <div class="result-block">
        <h3>答案</h3>
        <div class="answer-line"><span class="k">我的答案</span><span class="v">${escapeHtml(detail.selected || "未选择")}</span></div>
        <div class="answer-line"><span class="k">正确答案</span><span class="v">${escapeHtml(detail.correctAnswer)}</span></div>
      </div>
    `;
  }
  if (q.type === "build_sentence") {
    const mine =
      detail.submittedSentence ||
      (detail.submitted || []).filter(Boolean).join(" ") ||
      "（未完成）";
    const correct =
      detail.completeSentence ||
      q.data?.completeSentence ||
      (detail.correctOrder || []).join(" ") ||
      (q.data?.correctOrder || []).join(" ");
    return `
      <div class="result-block">
        <h3>答案</h3>
        <div class="answer-line"><span class="k">我的答案</span><span class="v">${escapeHtml(mine)}</span></div>
        <div class="answer-line"><span class="k">正确答案</span><span class="v">${escapeHtml(correct)}</span></div>
        <div class="blank-feedback">
          ${(detail.positions || [])
            .map(
              (item) =>
                `<div class="item ${item.correct ? "correct" : "wrong"}">第 ${item.index} 空：${escapeHtml(item.actual || "未填")} → ${escapeHtml(item.expected)}</div>`,
            )
            .join("")}
        </div>
      </div>
    `;
  }
  return `
    <div class="result-block">
      <h3>逐空结果</h3>
      <div class="blank-feedback">
        ${(detail.blanks || [])
          .map((blank) => {
            const prefix = blank.prefix || "";
            const mine = blank.actual || "未填";
            const expected = blank.expected || "";
            const full = blank.fullWord || (prefix && expected ? prefix + expected : "");
            return `<div class="item ${blank.correct ? "correct" : "wrong"}">
              第 ${escapeHtml(blank.id)} 空：
              <strong>${escapeHtml(prefix)}</strong><em>${escapeHtml(mine)}</em>
              → 正确 <strong>${escapeHtml(prefix)}${escapeHtml(expected)}</strong>
              ${full ? `（${escapeHtml(full)}）` : ""}
            </div>`;
          })
          .join("")}
      </div>
    </div>
    ${
      detail.completePassage
        ? `<div class="result-block">
            <h3>完整正确短文</h3>
            <p class="article-box">${escapeHtml(detail.completePassage)}</p>
          </div>`
        : ""
    }
    ${
      detail.submittedPassage
        ? `<div class="result-block">
            <h3>我的短文</h3>
            <p class="article-box">${escapeHtml(detail.submittedPassage)}</p>
          </div>`
        : ""
    }
  `;
}

function retryCurrent() {
  const q = state.practiceQuestion;
  if (!q) return;
  q._result = null;
  state.practiceResult = null;
  state.selectedChoice = "";
  state.completeAnswers = {};
  state.activeBlankIndex = 0;
  if (q.type === "build_sentence") {
    state.buildOrderIndices = Array.from({ length: countPracticeBlanks(q) }, () => null);
  }
  renderPractice();
}

/* ===================== Practice report ===================== */

function filteredReportItems() {
  const filter = state.reportFilter || "all";
  return state.practiceQuestions
    .map((q, i) => ({ q, originalIndex: i }))
    .filter(({ q }) => {
      const ok = Boolean(q._result?.isCorrect);
      if (filter === "correct") return ok;
      if (filter === "wrong") return !ok;
      return true;
    });
}

function reportStatsHtml(total, correct, wrong, pct) {
  const ringTone = pct >= 80 ? "ok" : pct >= 50 ? "warn" : "bad";
  return `
    <div class="report-stats">
      <div class="report-stat"><span class="label">总题数</span><span class="value">${total}</span></div>
      <div class="report-stat ok"><span class="label">答对</span><span class="value">${correct}</span></div>
      <div class="report-stat bad"><span class="label">答错</span><span class="value">${wrong}</span></div>
      <div class="report-stat ${ringTone}"><span class="label">正确率</span><span class="value">${pct}%</span></div>
    </div>
  `;
}

function reportFilterHtml() {
  const f = state.reportFilter || "all";
  const tabs = [["all", "全部"], ["correct", "答对"], ["wrong", "答错"]];
  return `
    <div class="report-filter" role="tablist">
      ${tabs
        .map(
          ([key, label]) =>
            `<button type="button" class="report-filter-btn ${f === key ? "active" : ""}" data-action="setReportFilter" data-arg="${key}">${label}</button>`,
        )
        .join("")}
    </div>
  `;
}

function reportListItemStatus(q) {
  if (!q._result) return { cls: "unanswered", label: "未作答" };
  return q._result.isCorrect ? { cls: "correct", label: "答对" } : { cls: "wrong", label: "答错" };
}

function reportListHtml(items, selectedIndex) {
  if (!items.length) {
    return `<aside class="report-list"><p class="empty">没有符合条件的题目。</p></aside>`;
  }
  return `
    <aside class="report-list">
      ${items
        .map(({ q, originalIndex }) => {
          const status = reportListItemStatus(q);
          const isActive = originalIndex === selectedIndex;
          const preview = (q.title || q.prompt || "题目").replace(/\s+/g, " ").trim();
          return `
            <button type="button" class="report-list-item ${status.cls} ${isActive ? "active" : ""}" data-action="selectReportQuestion" data-arg="${originalIndex}">
              <span class="report-item-no">${originalIndex + 1}</span>
              <span class="report-item-body">
                <span class="report-item-type">${escapeHtml(TYPE_NAMES[q.type] || q.type)}</span>
                <span class="report-item-title">${escapeHtml(preview.slice(0, 36))}</span>
              </span>
              <span class="report-item-status ${status.cls}">${status.label}</span>
            </button>
          `;
        })
        .join("")}
    </aside>
  `;
}

function questionOriginalHtml(q, detail) {
  if (q.type === "reading_choice") {
    const correctKey = detail?.correctAnswer;
    const selectedKey = detail?.selected;
    return `
      <div class="result-block">
        <h3>原题</h3>
        ${q.title ? `<p class="report-q-title">${escapeHtml(q.title)}</p>` : ""}
        ${q.article ? `<p class="article-box">${escapeHtml(q.article)}</p>` : ""}
        <p class="report-q-prompt">${escapeHtml(q.prompt || "")}</p>
        <div class="report-options">
          ${(q.data?.options || [])
            .map((opt) => {
              const tags = [];
              if (opt.key === correctKey) tags.push("is-correct");
              if (selectedKey && opt.key === selectedKey && opt.key !== correctKey) tags.push("is-wrong");
              return `
                <div class="report-option ${tags.join(" ")}">
                  <span class="option-key">${escapeHtml(opt.key)}</span>
                  <span class="option-text">${escapeHtml(opt.text)}</span>
                  ${opt.key === correctKey ? `<span class="report-option-mark correct">正确答案</span>` : ""}
                  ${selectedKey && opt.key === selectedKey && opt.key !== correctKey ? `<span class="report-option-mark wrong">你的选择</span>` : ""}
                </div>
              `;
            })
            .join("")}
        </div>
      </div>
    `;
  }
  if (q.type === "build_sentence") {
    const template = q.data?.sentenceTemplate || "";
    const display = template.replace(/\{\{\s*(?:blank|\d+)\s*\}\}|_{2,}/gi, "＿＿＿＿");
    return `
      <div class="result-block">
        <h3>原题</h3>
        <p class="report-q-prompt">${escapeHtml(q.prompt || "使用待选词完成句子。")}</p>
        <div class="report-field-label">题目详情</div>
        <div class="report-template">${escapeHtml(display)}</div>
        ${(q.data?.wordBank || []).length
          ? `<div class="report-field-label">待选词</div><div class="report-wordbank">
              ${q.data.wordBank.map((w) => `<span class="word-token" disabled>${escapeHtml(w)}</span>`).join("")}
            </div>`
          : ""}
      </div>
    `;
  }
  const passage = q.data?.passageText || "";
  const display = passage.replace(/\[\[\s*[A-Za-z0-9_-]+\s*\]\]/g, "＿＿");
  return `
    <div class="result-block">
      <h3>原题</h3>
      <p class="report-q-prompt">${escapeHtml(q.prompt || "补全短文中缺失的字母。")}</p>
      <p class="article-box">${escapeHtml(display)}</p>
    </div>
  `;
}

function reportDetailHtml(q, index) {
  if (!q) return `<section class="report-detail"><p class="subtle">选择左侧题目查看详情。</p></section>`;
  const result = q._result;
  const answered = Boolean(result && !result.error);
  const ok = Boolean(result?.isCorrect);
  const status = !answered ? { cls: "unanswered", label: "未作答" } : ok ? { cls: "correct", label: "答对" } : { cls: "wrong", label: "答错" };
  return `
    <section class="report-detail">
      <div class="report-detail-head">
        <span class="report-detail-no">第 ${index + 1} 题</span>
        <span class="type-badge">${escapeHtml(TYPE_NAMES[q.type] || q.type)}</span>
        <span class="report-detail-status ${status.cls}">${status.label}</span>
      </div>
      ${questionOriginalHtml(q, result?.detail)}
      ${answered && result?.detail ? answerReviewHtml(q, result.detail) : `<div class="result-block"><h3>答案</h3><p class="subtle">本题未提交答案。</p></div>`}
      <div class="result-block">
        <h3>解析</h3>
        <p class="article-box">${escapeHtml(q.explanation || "暂无解析。")}</p>
      </div>
    </section>
  `;
}

function setReportFilter(filter) {
  state.reportFilter = filter;
  const items = filteredReportItems();
  if (items.length && !items.some((it) => it.originalIndex === state.reportSelectedIndex)) {
    state.reportSelectedIndex = items[0].originalIndex;
  }
  renderPractice();
}

function selectReportQuestion(index) {
  state.reportSelectedIndex = index;
  renderPractice();
  requestAnimationFrame(() => {
    const detail = document.querySelector(".report-detail");
    if (detail && window.matchMedia("(max-width: 860px)").matches) {
      detail.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

/* ===================== Practice history ===================== */

async function loadPracticeHistory() {
  try {
    const data = await api("/api/practice/sessions");
    state.practiceHistory = data.items || [];
  } catch (error) {
    state.practiceHistory = [];
    toast("加载练习记录失败：" + (error.message || "未知错误"));
  }
  renderPracticeHistory();
}

function formatSessionTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderPracticeHistory() {
  const items = state.practiceHistory || [];
  if (!items.length) {
    $("app").innerHTML = `
      <div class="page practice-history-page">
        <div class="page-head">
          <h1>练习记录</h1>
          <button class="btn" type="button" data-action="navigate" data-arg="practice">返回练习首页</button>
        </div>
        <div class="history-empty">
          <p>还没有练习记录。</p>
          <p class="subtle">完成一轮练习后，会自动保存到这里。</p>
        </div>
      </div>
    `;
    return;
  }
  $("app").innerHTML = `
    <div class="page practice-history-page">
      <div class="page-head">
        <h1>练习记录</h1>
        <button class="btn" type="button" data-action="navigate" data-arg="practice">返回练习首页</button>
      </div>
      <div class="history-list">
        ${items
          .map((it) => {
            const pct = Math.round((Number(it.accuracy) || 0) * 100);
            const ringTone = pct >= 80 ? "ok" : pct >= 50 ? "warn" : "bad";
            return `
              <button type="button" class="history-item" data-action="openPracticeSession" data-arg="${it.id}">
                <div class="history-item-main">
                  <span class="history-item-time">${escapeHtml(formatSessionTime(it.created_at))}</span>
                  <span class="history-item-meta">
                    <span class="chip">${it.total} 题</span>
                    <span class="chip ok">对 ${it.correct}</span>
                    <span class="chip bad">错 ${it.wrong}</span>
                  </span>
                </div>
                <span class="history-item-accuracy ${ringTone}">${pct}%</span>
              </button>
            `;
          })
          .join("")}
      </div>
    </div>
  `;
}

async function openPracticeSession(id) {
  try {
    const data = await api(`/api/practice/sessions/${id}`);
    state.practiceQuestions = (data.items || []).map((it) => ({
      ...it.question,
      _result: {
        isCorrect: Boolean(it.is_correct),
        detail: it.detail || {},
        answer: it.answer || {},
      },
    }));
    state.viewedSession = { id: data.id, createdAt: data.created_at };
    state.practiceFinished = true;
    state.practiceSessionIndex = 0;
    state.practiceQuestion = null;
    state.practiceResult = null;
    state.reportFilter = "all";
    state.reportSelectedIndex = 0;
    state.practiceSavedSessionId = null;
    setView("practice");
    setPracticeModeClass(false);
    render();
  } catch (error) {
    toast("加载练习记录失败：" + (error.message || "未知错误"));
  }
}

function redoCurrentSession() {
  if (!state.practiceQuestions.length) return;
  state.practiceQuestions = state.practiceQuestions.map((q) => stripResult(q));
  state.practiceSessionIndex = 0;
  state.practiceFinished = false;
  state.practiceQuestion = null;
  state.practiceResult = null;
  state.viewedSession = null;
  state.practiceSavedSessionId = null;
  state.reportFilter = "all";
  state.reportSelectedIndex = 0;
  state.selectedChoice = "";
  state.completeAnswers = {};
  state.activeBlankIndex = 0;
  state.buildOrderIndices = [];
  goToQuestion(0);
}

/* ===================== Settings ===================== */


export {
  refreshPracticeTotal,
  examBarHtml,
  renderPractice,
  setPracticeMode,
  showPracticeHelp,
  exitPractice,
  restartPractice,
  stripResult,
  saveCurrentSession,
  setPracticeTarget,
  setPracticeTargetFromInput,
  nextPractice,
  nextQuestion,
  prevQuestion,
  goToQuestion,
  practiceQuestion,
  practiceQuestionHtml,
  readingPracticeHtml,
  countPracticeBlanks,
  estimateBlankWidth,
  buildPracticeHtml,
  renderInteractiveSentence,
  renderFixedText,
  onBlankClick,
  fillWord,
  clearSlot,
  resetBuildAnswer,
  dragWord,
  dropWord,
  completePracticeHtml,
  renderCompletePassage,
  completeBlankSlotCount,
  completeLetterInputsHtml,
  cleanCompleteLetters,
  completeLetterGroupInputs,
  updateCompleteAnswerFromCells,
  collectCompleteWordAnswers,
  focusCompleteLetter,
  fillCompleteLetterCells,
  handleCompleteLetterInput,
  handleCompleteLetterPaste,
  handleCompleteLetterKeydown,
  initCompleteLetterInputs,
  submitPractice,
  resultHtml,
  answerReviewHtml,
  retryCurrent,
  filteredReportItems,
  reportStatsHtml,
  reportFilterHtml,
  reportListItemStatus,
  reportListHtml,
  questionOriginalHtml,
  reportDetailHtml,
  setReportFilter,
  selectReportQuestion,
  loadPracticeHistory,
  formatSessionTime,
  renderPracticeHistory,
  openPracticeSession,
  redoCurrentSession,
};
