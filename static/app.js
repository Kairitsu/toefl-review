const TYPE_NAMES = {
  reading_choice: "阅读选择题",
  build_sentence: "写作造句题",
  complete_words: "阅读填词题",
};

const TYPE_SECTIONS = {
  reading_choice: "Reading",
  build_sentence: "Writing",
  complete_words: "Reading",
};

const IMPORT_TYPES = ["reading_choice", "build_sentence", "complete_words"];

const READING_CHOICE_RAW_FIELDS = [
  { key: "title", label: "标题", placeholder: "可选，便于 LLM 识别题目主题" },
  { key: "article", label: "文章", placeholder: "阅读文章原文" },
  { key: "question", label: "问题", placeholder: "题干或问题" },
  {
    key: "options",
    label: "选项",
    placeholder: "可直接粘贴：\nA. ...\nB. ...\nC. ...\nD. ...",
  },
  { key: "correctAnswer", label: "正确答案", placeholder: "A / B / C / D，或粘贴完整选项文本" },
  { key: "analysis", label: "解析", placeholder: "题目解析（可选）" },
];

const BUILD_SENTENCE_RAW_FIELDS = [
  { key: "questioner", label: "提问者", placeholder: "例如：What impressed you about the team's presentation yesterday?" },
  {
    key: "sentenceTemplate",
    label: "句子模板",
    placeholder: "空位用下划线或 {{blank}}；固定词原样保留",
  },
  { key: "wordBank", label: "词库", placeholder: "词或词组之间用逗号隔开，例如：presentation, entire, their, public speaking" },
  {
    key: "correctAnswer",
    label: "正确答案",
    placeholder: "完整正确句子，或按空位顺序写词块（逗号分隔）",
  },
  { key: "analysis", label: "解析", placeholder: "题目解析或排序依据" },
];

const COMPLETE_WORDS_RAW_FIELDS = [
  {
    key: "passage",
    label: "原始短文",
    placeholder:
      "LLM 解析后回填的规范短文，例如：\nthey were limited by the ne__ for a double coincidence of wants.",
  },
  {
    key: "answers",
    label: "答案",
    placeholder: "按空格出现顺序填写，每行一个",
  },
  { key: "analysis", label: "解析", placeholder: "题目解析（可选）" },
];

const COMPLETE_WORDS_SOURCE_FIELDS = [
  {
    key: "passage",
    label: "题目/原始短文",
    placeholder:
      "粘贴原始题目材料，例如：\nTrade in the ancient Middle East played a crucial role in the development of civilizations. Merchants exchanged goods such as textiles, spices, and met _ _ _ across vast dis _ _ _ _ _ _.",
  },
  {
    key: "answers",
    label: "答案",
    placeholder: "可带序号，例如：\n1、als\n2、tances",
  },
  { key: "analysis", label: "解析（可选）", placeholder: "原始解析，可留空" },
];

const state = {
  view: "import",
  importRaw: "",
  importDraft: null,
  importValidation: null,
  importError: null,
  importLoading: false,
  importTypeHint: "reading_choice",
  readingChoiceRawFields: { title: "", article: "", question: "", options: "", correctAnswer: "", analysis: "" },
  completeWordsRawFields: { passage: "", answers: "", analysis: "" },
  completeWordsFields: { passage: "", answers: "", analysis: "" },
  library: [],
  librarySelected: new Set(),
  filters: { type: "", sort: "created", q: "" },
  editQuestion: null,
  formValidation: null,
  practiceMode: "random",
  practiceQuestion: null,
  practiceQuestions: [],
  practiceResult: null,
  practiceSessionIndex: 0,
  practiceSessionCorrect: 0,
  practiceTotal: 0,
  practiceTarget: 10,
  practiceFinished: false,
  buildOrderIndices: [],
  activeBlankIndex: 0,
  selectedChoice: "",
  completeAnswers: {},
  settings: null,
  settingsTesting: false,
  settingsTestResult: null,
  settingsDraft: null,
  settingsDraftApiKey: "",
  auth: null,
  authLoading: false,
  authError: null,
  authSettings: null,
  authDraft: null,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function attr(value) {
  return escapeHtml(value).replaceAll("\n", "&#10;");
}

function lines(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function delimitedList(value) {
  return String(value || "")
    .split(/[\n,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    node.hidden = true;
  }, 2600);
}

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
      render();
    }
    const error = new Error(data.error || response.statusText);
    error.data = data;
    error.status = response.status;
    throw error;
  }
  return data;
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

async function navigate(view) {
  if (view !== "practice") {
    // Leaving practice clears immersion chrome, keeps question cached for return
  }
  setView(view);
  render();
  if (view === "library" || view === "practice_select") await loadLibrary();
  if (view === "settings") await loadSettings();
  if (view === "practice" && !state.practiceQuestion) {
    await refreshPracticeTotal();
    render();
  }
}

function validationHtml(validation) {
  if (!validation) return "";
  const blocks = [];
  if (validation.errors?.length) {
    blocks.push(`<div class="status error">${validation.errors.map(escapeHtml).join("<br>")}</div>`);
  }
  if (validation.warnings?.length) {
    blocks.push(`<div class="status warn">${validation.warnings.map(escapeHtml).join("<br>")}</div>`);
  }
  if (validation.ok) {
    blocks.push(`<div class="status ok">结构校验通过，可以保存。</div>`);
  }
  return blocks.join("");
}

function errorHtml(error) {
  if (!error) return "";
  const details = error.details?.length ? `<br>${error.details.map(escapeHtml).join("<br>")}` : "";
  return `<div class="status error">${escapeHtml(error.message || error.error || "操作失败")}${details}</div>`;
}

function progressHtml(active, message) {
  if (!active) return "";
  return `
    <div class="parse-progress" role="status" aria-live="polite">
      <div class="parse-progress-head">
        <strong>${escapeHtml(message || "正在解析")}</strong>
        <span>请等待 LLM 返回结果</span>
      </div>
      <div class="progress-track"><div class="progress-bar"></div></div>
    </div>
  `;
}

function defaultData(type) {
  if (type === "reading_choice") {
    return {
      options: [
        { key: "A", text: "" },
        { key: "B", text: "" },
        { key: "C", text: "" },
        { key: "D", text: "" },
      ],
      correctAnswer: "",
    };
  }
  if (type === "build_sentence") {
    return { sentenceTemplate: "", wordBank: [], correctOrder: [], completeSentence: "" };
  }
  return {
    passageText: "",
    blanks: [{ id: "1", prefix: "", answer: "", fullWord: "", note: "", confirmed: false }],
  };
}

function normalizeFormQuestion(question = {}) {
  const type = question.type || "reading_choice";
  return {
    type,
    title: question.title || "",
    article: question.article || "",
    prompt: question.prompt || "",
    explanation: question.explanation || "",
    needsConfirmation: Boolean(question.needsConfirmation),
    data: { ...defaultData(type), ...(question.data || {}) },
  };
}

function emptyImportQuestion() {
  const type = normalizeImportType(state.importTypeHint);
  return normalizeFormQuestion({ type, data: defaultData(type) });
}

function normalizeImportType(type) {
  return IMPORT_TYPES.includes(type) ? type : "reading_choice";
}

function emptyReadingChoiceRawFields() {
  return Object.fromEntries(READING_CHOICE_RAW_FIELDS.map((field) => [field.key, ""]));
}

function parseReadingChoiceRawFields(rawValue) {
  const fields = emptyReadingChoiceRawFields();
  const rawText = String(rawValue || "");
  if (!rawText.trim()) return fields;

  const labels = Object.fromEntries(READING_CHOICE_RAW_FIELDS.map((field) => [field.label, field.key]));
  labels["题目"] = "title";
  labels["原始题目"] = "title";
  labels["阅读标题"] = "title";
  labels["原文"] = "article";
  labels["阅读文章"] = "article";
  labels["短文"] = "article";
  labels["passage"] = "article";
  labels["article"] = "article";
  labels["题干"] = "question";
  labels["question"] = "question";
  labels["prompt"] = "question";
  labels["选项列表"] = "options";
  labels["options"] = "options";
  labels["答案"] = "correctAnswer";
  labels["correct answer"] = "correctAnswer";
  labels["answer"] = "correctAnswer";
  labels["分析"] = "analysis";
  labels["explanation"] = "analysis";

  const labelNames = Object.keys(labels).sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(?:^|\\n)\\s*(${labelNames.map(escapeRegExp).join("|")})\\s*[：:]\\s*`, "gi");
  const matches = [...rawText.matchAll(pattern)];
  if (!matches.length) {
    fields.article = rawText.trim();
    return fields;
  }

  matches.forEach((match, index) => {
    const key = labels[match[1].toLowerCase()] || labels[match[1]];
    if (!key) return;
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : rawText.length;
    fields[key] = rawText.slice(start, end).trim();
  });
  return fields;
}

function readingChoiceRawTableHtml(fields, parseDisabled) {
  return `
    <div class="structured-raw-wrap">
      <table class="structured-raw-table">
        <tbody>
          ${READING_CHOICE_RAW_FIELDS.map(
            (field) => `
              <tr>
                <th scope="row">${escapeHtml(field.label)}</th>
                <td>
                  <textarea
                    id="reading-raw-${field.key}"
                    class="structured-raw-input reading-raw-input reading-raw-${field.key}"
                    ${parseDisabled}
                    oninput="onReadingChoiceRawInput()"
                    placeholder="${attr(field.placeholder)}"
                  >${escapeHtml(fields[field.key] || "")}</textarea>
                </td>
              </tr>
            `,
          ).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function emptyBuildSentenceRawFields() {
  return Object.fromEntries(BUILD_SENTENCE_RAW_FIELDS.map((field) => [field.key, ""]));
}

function parseBuildSentenceRawFields(rawValue) {
  const fields = emptyBuildSentenceRawFields();
  const rawText = String(rawValue || "");
  if (!rawText.trim()) return fields;

  const labels = Object.fromEntries(BUILD_SENTENCE_RAW_FIELDS.map((field) => [field.label, field.key]));
  // Also accept common aliases used in paste text
  labels["模板"] = "sentenceTemplate";
  labels["问题"] = "questioner";
  labels["正确顺序"] = "correctAnswer";
  labels["完整句子"] = "correctAnswer";
  const pattern = /(?:^|\n)\s*(提问者|问题|句子模板|模板|词库|正确答案|正确顺序|完整句子|解析)\s*[：:]\s*/g;
  const matches = [...rawText.matchAll(pattern)];
  if (!matches.length) {
    fields.questioner = rawText.trim();
    return fields;
  }

  matches.forEach((match, index) => {
    const key = labels[match[1]];
    if (!key) return;
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : rawText.length;
    fields[key] = rawText.slice(start, end).trim();
  });
  return fields;
}

function buildSentenceRawTableHtml(rawValue, parseDisabled) {
  const fields = parseBuildSentenceRawFields(rawValue);
  return `
    <div class="structured-raw-wrap">
      <table class="structured-raw-table">
        <tbody>
          ${BUILD_SENTENCE_RAW_FIELDS.map(
            (field) => `
              <tr>
                <th scope="row">${escapeHtml(field.label)}</th>
                <td>
                  <textarea
                    id="build-raw-${field.key}"
                    class="structured-raw-input"
                    ${parseDisabled}
                    placeholder="${attr(field.placeholder)}"
                  >${escapeHtml(fields[field.key])}</textarea>
                </td>
              </tr>
            `,
          ).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function parseCompleteWordsRawFields(rawValue) {
  const fields = Object.fromEntries(COMPLETE_WORDS_RAW_FIELDS.map((f) => [f.key, ""]));
  const rawText = String(rawValue || "");
  if (!rawText.trim()) return fields;
  const labels = Object.fromEntries(COMPLETE_WORDS_RAW_FIELDS.map((f) => [f.label, f.key]));
  labels["文章"] = "passage";
  labels["原文"] = "passage";
  labels["短文"] = "passage";
  labels["题目"] = "passage";
  labels["题目/原始短文"] = "passage";
  labels["正确答案"] = "answers";
  labels["答案列表"] = "answers";
  labels["解析（可选）"] = "analysis";
  // Keep 标题/题型 as skip labels so they don't pollute passage when pasting old formats
  // Longest labels first so「原始短文」wins over「短文」
  const labelNames = Object.keys(labels).concat(["题型", "标题"]).sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(?:^|\\n)\\s*(${labelNames.map(escapeRegExp).join("|")})\\s*[：:]\\s*`, "g");
  const matches = [...rawText.matchAll(pattern)];
  if (!matches.length) {
    fields.passage = rawText.trim();
    return fields;
  }
  matches.forEach((match, index) => {
    const key = labels[match[1]];
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : rawText.length;
    const value = rawText.slice(start, end).trim();
    if (!key) return; // skip 题型/标题
    fields[key] = value;
  });
  return fields;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function completeWordsRawInputHtml(fields, parseDisabled) {
  return `
    <div class="structured-raw-wrap">
      <table class="structured-raw-table">
        <tbody>
          ${COMPLETE_WORDS_SOURCE_FIELDS.map(
            (field) => `
              <tr>
                <th scope="row">${escapeHtml(field.label)}</th>
                <td>
                  <textarea
                    id="complete-source-${field.key}"
                    class="structured-raw-input complete-source-input complete-source-${field.key}"
                    ${parseDisabled}
                    oninput="onCompleteWordsRawInput()"
                    placeholder="${attr(field.placeholder)}"
                  >${escapeHtml(fields[field.key] || "")}</textarea>
                </td>
              </tr>
            `,
          ).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function completeWordsStructuredFieldsHtml(fields, parseDisabled) {
  return `
    <div class="complete-field-stack">
      ${COMPLETE_WORDS_RAW_FIELDS.map(
        (field) => `
          <div class="field complete-edit-field">
            <label for="complete-raw-${field.key}">${escapeHtml(field.label)}</label>
            <textarea
              id="complete-raw-${field.key}"
              class="complete-structured-input complete-structured-${field.key}"
              ${parseDisabled}
              oninput="onCompleteWordsImportInput()"
              placeholder="${attr(field.placeholder)}"
            >${escapeHtml(fields[field.key] || "")}</textarea>
          </div>
        `,
      ).join("")}
    </div>
  `;
}

/** Parse answers: numbered lines, plain lines, or comma-separated. */
function parseCompleteAnswersClient(text) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  const numbered = [];
  for (const line of raw.split(/\r?\n/)) {
    const m = line.match(/^\s*(?:(\d+)[\.\)、:：]\s*|\-\s+|\*\s+)(.+?)\s*$/);
    if (m) {
      numbered.push({ index: m[1] ? Number(m[1]) : numbered.length + 1, value: m[2].trim() });
    }
  }
  if (numbered.length) {
    numbered.sort((a, b) => a.index - b.index);
    return numbered.map((item) => item.value).filter(Boolean);
  }
  return raw
    .split(/[\n,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function hasCompleteWordBlank(text) {
  return /([A-Za-z]+)((?:[ \t]*_){2,})/.test(String(text || ""));
}

/**
 * Core client rule: scan underscore blanks in order, match answers in order.
 * Never invent blanks for complete words without underscores.
 */
function buildCompleteWordsFromFields(passage, answersText) {
  const source = String(passage || "");
  const answers = parseCompleteAnswersClient(answersText);
  const blanks = [];
  const errors = [];
  let counter = 0;
  const passageText = source.replace(/([A-Za-z]+)((?:[ \t]*_){2,})/g, (_match, prefix, blankMark) => {
    counter += 1;
    const id = String(counter);
    const blankLength = (blankMark.match(/_/g) || []).length;
    blanks.push({ id, prefix, answer: "", fullWord: "", blankLength });
    return `${prefix}[[${id}]]`;
  });

  if (!blanks.length) {
    errors.push("没有识别到任何下划线空格（需要类似 ne__ / met _ _ _ 的残缺词）");
    return { passageText: source, blanks: [], errors, answers };
  }

  if (answers.length && answers.length !== blanks.length) {
    errors.push(
      `空格数量和答案数量不一致：识别到 ${blanks.length} 个下划线空格，但提供了 ${answers.length} 个答案`,
    );
    return { passageText, blanks, errors, answers };
  }

  const matched = blanks.map((blank, index) => {
    const value = answers[index] || "";
    const prefix = blank.prefix || "";
    let answer = "";
    let fullWord = "";
    if (value) {
      if (prefix && value.toLowerCase().startsWith(prefix.toLowerCase()) && value.length > prefix.length) {
        fullWord = value;
        answer = value.slice(prefix.length);
      } else if (prefix) {
        answer = value;
        fullWord = prefix + value;
      } else {
        answer = value;
        fullWord = value;
      }
    }
    if (fullWord && prefix && !fullWord.toLowerCase().startsWith(prefix.toLowerCase())) {
      errors.push(`空格 ${blank.id}：完整词“${fullWord}”不以前缀“${prefix}”开头`);
    }
    return {
      id: blank.id,
      prefix,
      answer,
      fullWord,
      note: "",
      confirmed: Boolean(answer && fullWord),
    };
  });

  return { passageText, blanks: matched, errors, answers };
}

function onCompleteWordsImportInput() {
  if (state.importTypeHint !== "complete_words") return;
  const fields = collectCompleteWordsRawFields();
  state.completeWordsFields = fields;
  const built = buildCompleteWordsFromFields(fields.passage, fields.answers);
  const hasContent = Boolean(String(fields.passage || "").trim() || String(fields.answers || "").trim());
  if (!hasContent) {
    state.importDraft = null;
    state.importValidation = null;
  } else {
    state.importDraft = {
      type: "complete_words",
      title: "",
      article: built.passageText,
      prompt: "Fill in the missing letters in the paragraph",
      explanation: fields.analysis || "",
      needsConfirmation: false,
      data: {
        passageText: built.passageText,
        blanks: built.blanks,
      },
    };
    state.importValidation = {
      ok: built.errors.length === 0 && built.blanks.length > 0 && built.blanks.every((b) => b.answer),
      errors: built.errors,
      warnings: [],
    };
  }
  // Re-render only the preview panel to keep caret position in textareas
  const preview = $("complete-import-preview");
  if (preview) {
    preview.innerHTML = completeWordsImportPreviewHtml(state.importDraft, state.importValidation, fields.analysis);
  } else {
    renderImport();
    return;
  }
  const canSave = Boolean(state.importValidation?.ok);
  const saveBtn = $("complete-import-save");
  if (saveBtn) saveBtn.disabled = !canSave;
}

function completeWordsImportPreviewHtml(draft, validation, analysisText) {
  if (!draft || draft.type !== "complete_words") {
    return `<div class="status soft-info">填写短文和答案后，这里会显示解析预览。</div>`;
  }
  const data = draft.data || {};
  const blanks = data.blanks || [];
  const errors = validation?.errors || [];
  const errorBlock =
    errors.length > 0
      ? `<div class="status error">${errors.map(escapeHtml).join("<br>")}</div>`
      : "";

  const explanation = analysisText ?? draft.explanation ?? "";
  return `
    ${errorBlock}
    <div class="field" style="margin-top:${errorBlock ? "12px" : "0"}">
      <label>短文预览</label>
      ${completePassagePreviewHtml(data.passageText || "", blanks, true)}
    </div>
    <div class="field">
      <label>解析</label>
      <div class="article-box" style="min-height:auto">${escapeHtml(explanation || "（未填写）")}</div>
    </div>
  `;
}

function hasReadingChoiceRawContent(fields) {
  return READING_CHOICE_RAW_FIELDS.some((field) => String(fields?.[field.key] || "").trim());
}

function currentReadingChoiceRawFields(rawValue = state.importRaw) {
  const current = state.readingChoiceRawFields || emptyReadingChoiceRawFields();
  if (hasReadingChoiceRawContent(current)) return current;
  return parseReadingChoiceRawFields(rawValue);
}

function rawImportInputHtml(rawValue, parseDisabled) {
  if (state.importTypeHint === "reading_choice") {
    const fields = currentReadingChoiceRawFields(rawValue);
    state.readingChoiceRawFields = fields;
    return readingChoiceRawTableHtml(fields, parseDisabled);
  }
  if (state.importTypeHint === "build_sentence") {
    return buildSentenceRawTableHtml(rawValue, parseDisabled);
  }
  if (state.importTypeHint === "complete_words") {
    return completeWordsRawInputHtml(state.completeWordsRawFields, parseDisabled);
  }
  return `<textarea id="rawText" class="raw-input" ${parseDisabled} placeholder="粘贴题干、文章、选项、答案、解析。格式可以乱，保存前会先预览。">${escapeHtml(rawValue)}</textarea>`;
}

function collectReadingChoiceRawFields() {
  return Object.fromEntries(
    READING_CHOICE_RAW_FIELDS.map((field) => [field.key, $(`reading-raw-${field.key}`)?.value || ""]),
  );
}

function serializeReadingChoiceRaw(fields) {
  const hasContent = READING_CHOICE_RAW_FIELDS.some((field) => String(fields[field.key] || "").trim());
  if (!hasContent) return "";
  return READING_CHOICE_RAW_FIELDS.map((field) => `${field.label}：\n${String(fields[field.key] || "").trim()}`).join("\n\n");
}

function collectBuildSentenceRawFields() {
  return Object.fromEntries(
    BUILD_SENTENCE_RAW_FIELDS.map((field) => [field.key, $(`build-raw-${field.key}`)?.value || ""]),
  );
}

function serializeBuildSentenceRaw(fields) {
  const hasContent = BUILD_SENTENCE_RAW_FIELDS.some((field) => String(fields[field.key] || "").trim());
  if (!hasContent) return "";
  return BUILD_SENTENCE_RAW_FIELDS.map((field) => `${field.label}：\n${String(fields[field.key] || "").trim()}`).join("\n\n");
}

function collectCompleteWordsRawFields() {
  return Object.fromEntries(
    COMPLETE_WORDS_RAW_FIELDS.map((field) => [field.key, $(`complete-raw-${field.key}`)?.value || ""]),
  );
}

function collectCompleteWordsSourceFields() {
  return Object.fromEntries(
    COMPLETE_WORDS_SOURCE_FIELDS.map((field) => [field.key, $(`complete-source-${field.key}`)?.value || ""]),
  );
}

function serializeCompleteWordsRaw(fields) {
  const hasContent = COMPLETE_WORDS_RAW_FIELDS.some((field) => String(fields[field.key] || "").trim());
  if (!hasContent) return "";
  return COMPLETE_WORDS_RAW_FIELDS.map((field) => `${field.label}：\n${String(fields[field.key] || "").trim()}`).join("\n\n");
}

function serializeCompleteWordsSourceRaw(fields) {
  const hasContent = COMPLETE_WORDS_SOURCE_FIELDS.some((field) => String(fields[field.key] || "").trim());
  if (!hasContent) return "";
  return COMPLETE_WORDS_SOURCE_FIELDS.map((field) => `${field.label}：\n${String(fields[field.key] || "").trim()}`).join("\n\n");
}

function collectImportRaw(rawType = state.importTypeHint) {
  if (rawType === "reading_choice") {
    const raw = serializeReadingChoiceRaw(collectReadingChoiceRawFields());
    if (String(raw).trim()) return raw;
    return state.importRaw || "";
  }
  if (rawType === "build_sentence") {
    return serializeBuildSentenceRaw(collectBuildSentenceRawFields());
  }
  if (rawType === "complete_words") {
    const sourceRaw = serializeCompleteWordsSourceRaw(collectCompleteWordsSourceFields());
    if (String(sourceRaw).trim()) return sourceRaw;
    return state.importRaw || "";
  }
  return $("rawText")?.value || state.importRaw || "";
}

function confirmationBanner(question) {
  if (!question?.needsConfirmation) return "";
  return `<div class="status warn">部分字段可能不完整（如答案缺失），请仔细核对后再保存。</div>`;
}

function hasCompleteWordsFieldContent(fields) {
  return COMPLETE_WORDS_RAW_FIELDS.some((field) => String(fields?.[field.key] || "").trim());
}

function hasCompleteWordsSourceContent(fields) {
  return COMPLETE_WORDS_SOURCE_FIELDS.some((field) => String(fields?.[field.key] || "").trim());
}

function onReadingChoiceRawInput() {
  if (state.importTypeHint !== "reading_choice") return;
  state.readingChoiceRawFields = collectReadingChoiceRawFields();
  state.importRaw = serializeReadingChoiceRaw(state.readingChoiceRawFields);
}

function onCompleteWordsRawInput() {
  if (state.importTypeHint !== "complete_words") return;
  state.completeWordsRawFields = collectCompleteWordsSourceFields();
  state.importRaw = serializeCompleteWordsSourceRaw(state.completeWordsRawFields);
}

function renderImport() {
  // Simplified dedicated flow for reading fill-in (complete_words)
  if (state.importTypeHint === "complete_words") {
    renderCompleteWordsImport();
    return;
  }

  const draft = state.importDraft ? normalizeFormQuestion(state.importDraft) : emptyImportQuestion();
  const rawValue = state.importRaw || "";
  const parseDisabled = state.importLoading ? "disabled" : "";
  const hasDraft = Boolean(state.importDraft);
  $("app").innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>导入错题</h1>
        </div>
        <button class="btn" type="button" onclick="navigate('settings')">LLM 设置</button>
      </div>
      <div class="grid two-col">
        <section class="workbench">
          <div class="workbench-head">
            <div>
              <strong>粘贴工作台</strong>
            </div>
            <span class="type-badge">${TYPE_NAMES[normalizeImportType(state.importTypeHint)]}</span>
          </div>
          <div class="workbench-body">
            <div class="field">
              <label for="typeHint">题型</label>
              <select id="typeHint" ${parseDisabled} onchange="setImportTypeHint(this.value)">
                <option value="reading_choice" ${state.importTypeHint === "reading_choice" ? "selected" : ""}>阅读选择题</option>
                <option value="build_sentence" ${state.importTypeHint === "build_sentence" ? "selected" : ""}>写作造句题</option>
                <option value="complete_words" ${state.importTypeHint === "complete_words" ? "selected" : ""}>阅读填词题</option>
              </select>
            </div>
            <div class="field">
              <label for="${
                state.importTypeHint === "reading_choice"
                  ? "reading-raw-title"
                  : state.importTypeHint === "build_sentence"
                    ? "build-raw-questioner"
                    : "rawText"
              }">原始题目</label>
              ${rawImportInputHtml(rawValue, parseDisabled)}
            </div>
            ${progressHtml(state.importLoading, "正在调用 LLM 解析题目")}
            ${errorHtml(state.importError)}
            <div class="toolbar actions">
              <button class="btn primary" type="button" onclick="parseImport()" ${parseDisabled}>
                ${state.importLoading ? "解析中..." : "调用 LLM 解析"}
              </button>
              <button class="btn" type="button" onclick="clearImport()" ${parseDisabled}>清空</button>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>解析预览</h2>
          </div>
          ${hasDraft ? confirmationBanner(draft) : `<div class="status soft-info">解析后会按题型展示结构化字段，可在此直接修改。</div>`}
          ${validationHtml(state.importValidation)}
          ${questionFormHtml(draft, "import")}
          <div class="toolbar actions">
            <button class="btn primary" type="button" onclick="saveQuestion('import')" ${hasDraft ? "" : "disabled"}>保存进题库</button>
          </div>
        </section>
      </div>
    </div>
  `;
}

function completeWordsDraftToFields(draft, fallbackRaw = "") {
  /** Write parse draft back into structured fields so preview/save stay in sync. */
  const existing = parseCompleteWordsRawFields(fallbackRaw);
  const data = draft?.data || {};
  const blanks = Array.isArray(data.blanks) ? data.blanks : [];
  const source = String(data.passageText || draft?.article || "").trim();
  let passage = source.replace(/([A-Za-z]*)\[\[\s*([A-Za-z0-9_-]+)\s*\]\]/g, (_, prefix, id) => {
    const blank = blanks.find((b) => String(b.id) === String(id)) || {};
    const p = prefix || blank.prefix || "";
    const n = Math.max(2, Number(blank.blankLength || 0) || String(blank.answer || "").length || 2);
    return `${p}${"_".repeat(n)}`;
  });
  if (!passage) passage = String(existing.passage || "").trim();
  const normalizedAnswers = blanks.map((b) => b.answer || b.fullWord || "").filter(Boolean);
  const answers = normalizedAnswers.length
    ? normalizedAnswers.join("\n")
    : parseCompleteAnswersClient(existing.answers).join("\n");
  const analysis = String(draft?.explanation || existing.analysis || "").trim();
  return { passage, answers, analysis };
}

function currentCompleteWordsFields(rawValue = state.importRaw) {
  const current = state.completeWordsFields || { passage: "", answers: "", analysis: "" };
  if (hasCompleteWordsFieldContent(current)) return current;
  if (state.importDraft?.type === "complete_words") return completeWordsDraftToFields(state.importDraft, rawValue);
  return { passage: "", answers: "", analysis: "" };
}

function currentCompleteWordsRawFields(rawValue = state.importRaw) {
  const current = state.completeWordsRawFields || { passage: "", answers: "", analysis: "" };
  if (hasCompleteWordsSourceContent(current)) return current;
  const fromRaw = parseCompleteWordsRawFields(rawValue);
  return {
    passage: fromRaw.passage || "",
    answers: fromRaw.answers || "",
    analysis: fromRaw.analysis || "",
  };
}

function renderCompleteWordsImport() {
  const rawValue = state.importRaw || "";
  const rawFields = currentCompleteWordsRawFields(rawValue);
  state.completeWordsRawFields = rawFields;
  const fields = currentCompleteWordsFields(rawValue);
  state.completeWordsFields = fields;
  const parseDisabled = state.importLoading ? "disabled" : "";
  // Keep draft in sync with current fields (local underscore rules are source of truth)
  const built = buildCompleteWordsFromFields(fields.passage, fields.answers);
  const hasInput = Boolean(String(fields.passage || "").trim() || String(fields.answers || "").trim());
  if (hasInput) {
    state.importDraft = {
      type: "complete_words",
      title: "",
      article: built.passageText,
      prompt: "Fill in the missing letters in the paragraph",
      explanation: fields.analysis || "",
      needsConfirmation: false,
      data: { passageText: built.passageText, blanks: built.blanks },
    };
    state.importValidation = {
      ok: built.errors.length === 0 && built.blanks.length > 0 && built.blanks.every((b) => b.answer),
      errors: built.errors,
      warnings: [],
    };
  } else if (!state.importLoading) {
    state.importDraft = null;
    state.importValidation = null;
  }
  const canSave = Boolean(state.importValidation?.ok);
  $("app").innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>导入错题</h1>
        </div>
        <button class="btn" type="button" onclick="navigate('settings')">LLM 设置</button>
      </div>
      <div class="grid two-col">
        <section class="workbench">
          <div class="workbench-head">
            <div>
              <strong>阅读填词题</strong>
            </div>
            <span class="type-badge">阅读填词题</span>
          </div>
          <div class="workbench-body">
            <div class="field">
              <label for="typeHint">题型</label>
              <select id="typeHint" ${parseDisabled} onchange="setImportTypeHint(this.value)">
                <option value="reading_choice" ${state.importTypeHint === "reading_choice" ? "selected" : ""}>阅读选择题</option>
                <option value="build_sentence" ${state.importTypeHint === "build_sentence" ? "selected" : ""}>写作造句题</option>
                <option value="complete_words" selected>阅读填词题</option>
              </select>
            </div>
            <div class="field">
              <label>原始题目</label>
              ${completeWordsRawInputHtml(rawFields, parseDisabled)}
            </div>
            ${progressHtml(state.importLoading, "正在调用 LLM 解析题目")}
            ${errorHtml(state.importError)}
            <div class="toolbar actions">
              <button class="btn primary" type="button" onclick="parseImport()" ${parseDisabled}>
                ${state.importLoading ? "解析中..." : "调用 LLM 解析"}
              </button>
              <button class="btn" type="button" onclick="clearImport()" ${parseDisabled}>清空</button>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>结构化编辑</h2>
          </div>
          ${completeWordsStructuredFieldsHtml(fields, parseDisabled)}
          <div class="toolbar complete-ops">
            <button type="button" class="btn small" onclick="detectCompleteWordsFromPassage()" ${parseDisabled}>从短文识别空格</button>
            <button type="button" class="btn small" onclick="syncCompleteWordsFullWords()" ${parseDisabled}>自动拼接完整词</button>
          </div>
          <div class="complete-preview-section">
            <div class="panel-title compact">
              <h2>解析预览</h2>
            </div>
            <div id="complete-import-preview">
              ${completeWordsImportPreviewHtml(state.importDraft, state.importValidation, fields.analysis)}
            </div>
          </div>
          <div class="toolbar actions">
            <button id="complete-import-save" class="btn primary" type="button" onclick="saveCompleteWordsImport()" ${canSave && !state.importLoading ? "" : "disabled"}>保存题目</button>
          </div>
        </section>
      </div>
    </div>
  `;
}

/** Scan passage underscores + match answers; refresh preview. No blank table. */
function detectCompleteWordsFromPassage() {
  state.importRaw = collectImportRaw("complete_words");
  const fields = collectCompleteWordsRawFields();
  const built = buildCompleteWordsFromFields(fields.passage, fields.answers);
  if (!String(fields.passage || "").trim()) {
    toast("请先填写原始短文");
    return;
  }
  if (!built.blanks.length) {
    toast("未在短文中找到下划线空格（如 ne__ / met _ _ _）");
    onCompleteWordsImportInput();
    return;
  }
  onCompleteWordsImportInput();
  toast(`已从短文识别 ${built.blanks.length} 个空格`);
}

/** Ensure each blank fullWord = prefix + answer; refresh preview. */
function syncCompleteWordsFullWords() {
  state.importRaw = collectImportRaw("complete_words");
  const fields = collectCompleteWordsRawFields();
  const built = buildCompleteWordsFromFields(fields.passage, fields.answers);
  if (!built.blanks.length) {
    toast("请先识别空格");
    return;
  }
  // rebuild answers as missing letters so full words stay prefix+answer
  const synced = built.blanks.map((b) => {
    const prefix = b.prefix || "";
    let answer = b.answer || "";
    let fullWord = b.fullWord || "";
    if (prefix && answer) fullWord = prefix + answer;
    else if (prefix && fullWord && fullWord.toLowerCase().startsWith(prefix.toLowerCase())) {
      answer = fullWord.slice(prefix.length);
      fullWord = prefix + answer;
    }
    return { ...b, answer, fullWord, confirmed: Boolean(answer && fullWord) };
  });
  if (state.importDraft?.data) {
    state.importDraft.data.blanks = synced;
    state.importDraft.data.passageText = built.passageText;
  }
  onCompleteWordsImportInput();
  toast("已根据前缀 + 缺失字母拼接完整词");
}

async function saveCompleteWordsImport() {
  state.importRaw = collectImportRaw("complete_words");
  const fields = collectCompleteWordsRawFields();
  state.completeWordsFields = fields;
  const built = buildCompleteWordsFromFields(fields.passage, fields.answers);
  const extraErrors = [];
  if (!String(fields.passage || "").trim()) extraErrors.push("请填写原始短文");
  if (!built.blanks.length && !built.errors.length) {
    extraErrors.push("没有识别到任何下划线空格（需要类似 ne__ / met _ _ _ 的残缺词）");
  }
  if (built.blanks.length && !built.answers.length) {
    extraErrors.push("请填写答案");
  }
  if (built.blanks.some((b) => !b.answer) && built.answers.length === built.blanks.length) {
    // already handled by apply
  }
  if (built.blanks.length && built.answers.length === built.blanks.length) {
    built.blanks.forEach((b) => {
      if (!b.answer) extraErrors.push(`空格 ${b.id} 缺少缺失字母`);
    });
  }
  const errors = [...built.errors, ...extraErrors];
  const question = {
    type: "complete_words",
    title: "",
    article: built.passageText,
    prompt: "Fill in the missing letters in the paragraph",
    explanation: fields.analysis || "",
    needsConfirmation: false,
    data: {
      passageText: built.passageText,
      blanks: built.blanks,
    },
  };
  state.importDraft = question;
  state.importValidation = { ok: errors.length === 0, errors, warnings: [] };
  if (errors.length) {
    state.importError = null;
    renderCompleteWordsImport();
    toast("无法保存：请先修正错误");
    return;
  }
  try {
    const saved = await api("/api/questions", {
      method: "POST",
      body: JSON.stringify(question),
    });
    state.importDraft = null;
    state.importRaw = "";
    state.completeWordsRawFields = { passage: "", answers: "", analysis: "" };
    state.completeWordsFields = { passage: "", answers: "", analysis: "" };
    state.importValidation = null;
    state.importError = null;
    await navigate("library");
    toast(`已保存：${TYPE_NAMES[saved.type] || "阅读填词题"}`);
  } catch (error) {
    const validation = error.data?.validation || { errors: [error.message] };
    state.importValidation = {
      ok: false,
      errors: validation.errors || [error.message],
      warnings: [],
    };
    state.importError = null;
    renderCompleteWordsImport();
  }
}

function setImportTypeHint(value) {
  const previousType = normalizeImportType(state.importTypeHint);
  state.importRaw = collectImportRaw(state.importTypeHint);
  state.importTypeHint = normalizeImportType(value);
  if (state.importTypeHint === "reading_choice" && previousType !== "reading_choice") {
    state.readingChoiceRawFields = parseReadingChoiceRawFields(state.importRaw);
  }
  if (!state.importDraft) state.importValidation = null;
  renderImport();
}

async function parseImport() {
  state.importTypeHint = normalizeImportType($("typeHint")?.value || state.importTypeHint);
  state.importRaw = collectImportRaw(state.importTypeHint);
  if (state.importTypeHint === "reading_choice") {
    state.readingChoiceRawFields = collectReadingChoiceRawFields();
    state.importRaw = serializeReadingChoiceRaw(state.readingChoiceRawFields);
  }
  if (state.importTypeHint === "complete_words") {
    state.completeWordsRawFields = collectCompleteWordsSourceFields();
    state.importRaw = serializeCompleteWordsSourceRaw(state.completeWordsRawFields);
    state.completeWordsFields = { passage: "", answers: "", analysis: "" };
  }
  state.importError = null;
  state.importDraft = null;
  state.importValidation = null;
  state.importLoading = true;
  renderImport();
  try {
    const data = await api("/api/import/parse", {
      method: "POST",
      body: JSON.stringify({ rawText: state.importRaw, typeHint: state.importTypeHint }),
    });
    state.importRaw = data.rawText || state.importRaw;
    state.importDraft = data.draft;
    state.importValidation = data.validation;
    // Keep complete_words on dedicated flow and sync labeled fields from draft
    if (data.draft?.type === "complete_words") {
      state.importTypeHint = "complete_words";
      state.completeWordsFields = completeWordsDraftToFields(data.draft, state.importRaw);
    }
    toast("解析完成，请预览确认");
  } catch (error) {
    state.importError = { message: error.message, details: error.data?.details || [] };
    if (error.data?.rawText) state.importRaw = error.data.rawText;
  } finally {
    state.importLoading = false;
  }
  renderImport();
}

function clearImport() {
  state.importRaw = "";
  state.importDraft = null;
  state.importValidation = null;
  state.importError = null;
  state.importLoading = false;
  state.readingChoiceRawFields = { title: "", article: "", question: "", options: "", correctAnswer: "", analysis: "" };
  state.completeWordsRawFields = { passage: "", answers: "", analysis: "" };
  state.completeWordsFields = { passage: "", answers: "", analysis: "" };
  renderImport();
}

function buildImportSummaryHtml(q) {
  if (!q || q.type !== "build_sentence") return "";
  const data = q.data || {};
  const blanks = countTemplateBlanksClient(data.sentenceTemplate);
  const order = data.correctOrder || [];
  const bank = data.wordBank || [];
  return `
    <div class="build-summary">
      <div class="build-summary-row"><span class="k">提问者</span><span class="v">${escapeHtml(q.prompt || "—")}</span></div>
      <div class="build-summary-row"><span class="k">句子模板</span><span class="v">${templatePreviewHtml(data.sentenceTemplate || "")}</span></div>
      <div class="build-summary-row"><span class="k">空位数</span><span class="v">${blanks} 个 · 正确顺序 ${order.length} 项 · 词库 ${bank.length} 个</span></div>
      <div class="build-summary-row">
        <span class="k">词库</span>
        <span class="v"><div class="build-summary-chips">${bank.map((w) => `<span>${escapeHtml(w)}</span>`).join("") || "—"}</div></span>
      </div>
      <div class="build-summary-row">
        <span class="k">正确顺序</span>
        <span class="v"><div class="build-summary-chips">${order.map((w, i) => `<span>${i + 1}. ${escapeHtml(w)}</span>`).join("") || "—"}</div></span>
      </div>
      <div class="build-summary-row"><span class="k">完整句子</span><span class="v">${escapeHtml(data.completeSentence || "—")}</span></div>
    </div>
  `;
}

function questionFormHtml(question, scope) {
  const q = normalizeFormQuestion(question);
  return `
    <div class="field">
      <label>题型</label>
      <select id="${scope}-type" onchange="changeFormType('${scope}')">
        ${Object.entries(TYPE_NAMES)
          .map(([value, label]) => `<option value="${value}" ${q.type === value ? "selected" : ""}>${label}</option>`)
          .join("")}
      </select>
    </div>
    ${
      q.type === "build_sentence" || q.type === "complete_words"
        ? ""
        : `<div class="field">
            <label>标题</label>
            <input id="${scope}-title" value="${attr(q.title)}" placeholder="可选，便于检索" />
          </div>`
    }
    ${scope === "import" && q.type === "build_sentence" && (q.prompt || q.data?.sentenceTemplate) ? buildImportSummaryHtml(q) : ""}
    ${scope === "import" && q.type === "complete_words" && (q.data?.passageText || q.data?.blanks?.length) ? completeImportSummaryHtml(q) : ""}
    ${q.type === "reading_choice" ? readingFormHtml(q, scope) : ""}
    ${q.type === "build_sentence" ? buildFormHtml(q, scope) : ""}
    ${q.type === "complete_words" ? completeFormHtml(q, scope) : ""}
    <div class="field">
      <label>解析</label>
      <textarea id="${scope}-explanation" placeholder="可选">${escapeHtml(q.explanation)}</textarea>
    </div>
  `;
}

function readingFormHtml(q, scope) {
  const data = { ...defaultData("reading_choice"), ...q.data };
  const options = data.options?.length === 4 ? data.options : defaultData("reading_choice").options;
  return `
    <div class="field">
      <label>文章</label>
      <textarea id="${scope}-article" placeholder="阅读文章">${escapeHtml(q.article)}</textarea>
    </div>
    <div class="field">
      <label>问题</label>
      <textarea id="${scope}-prompt" placeholder="题干或问题">${escapeHtml(q.prompt)}</textarea>
    </div>
    ${options
      .map(
        (option, index) => `
          <div class="field">
            <label>选项 ${String.fromCharCode(65 + index)}</label>
            <input id="${scope}-option-${index}" value="${attr(option.text)}" />
          </div>
        `,
      )
      .join("")}
    <div class="field">
      <label>正确答案</label>
      <select id="${scope}-correct">
        <option value="">需要人工确认</option>
        ${["A", "B", "C", "D"].map((key) => `<option value="${key}" ${data.correctAnswer === key ? "selected" : ""}>${key}</option>`).join("")}
      </select>
    </div>
  `;
}

function countTemplateBlanksClient(template) {
  return (String(template || "").match(/\{\{\s*(?:blank|\d+)\s*\}\}|_{2,}/gi) || []).length;
}

function normalizeTemplateClient(template) {
  return String(template || "")
    .replace(/\{\{\s*(?:blank|\d+)\s*\}\}/gi, "{{blank}}")
    .replace(/_{2,}/g, "{{blank}}")
    .replace(/[ \t]+/g, " ")
    .trim();
}

function templatePreviewHtml(template) {
  const source = String(template || "");
  if (!source.trim()) {
    return `<div class="status warn">尚未识别句子模板。请填写模板，或提供完整正确答案与词库以便推导。</div>`;
  }
  const html = escapeHtml(source)
    .replace(/\{\{\s*(?:blank|\d+)\s*\}\}|_{2,}/gi, '<span class="tpl-blank-mark">____</span>')
    .replace(/\n/g, "<br>");
  const blanks = countTemplateBlanksClient(source);
  return `
    <div class="template-preview">
      <div class="template-preview-label">模板预览 · ${blanks} 个空位</div>
      <div class="template-preview-body">${html}</div>
    </div>
  `;
}

function buildFormHtml(q, scope) {
  const data = { ...defaultData("build_sentence"), ...q.data };
  const blankCount = countTemplateBlanksClient(data.sentenceTemplate);
  const orderCount = (data.correctOrder || []).length;
  const mismatch =
    blankCount && orderCount && blankCount !== orderCount
      ? `<div class="status error">空位数（${blankCount}）与正确顺序数量（${orderCount}）不一致，保存前请修正。</div>`
      : "";
  return `
    <div class="field">
      <label>提问者问题 / 对话提示</label>
      <textarea id="${scope}-prompt" placeholder="例如：What impressed you about the team's presentation yesterday?">${escapeHtml(q.prompt)}</textarea>
    </div>
    <div class="field">
      <label>句子模板 <span class="field-hint">空位用 ____ 或 {{blank}}；固定词原样保留</span></label>
      <textarea id="${scope}-sentence-template" placeholder="空位用 ____ 或 {{blank}}；固定词原样保留">${escapeHtml(data.sentenceTemplate)}</textarea>
      ${templatePreviewHtml(data.sentenceTemplate)}
    </div>
    <div class="field">
      <label>词库 <span class="field-hint">逗号隔开；可多于空位数，但不要放入固定文本</span></label>
      <textarea id="${scope}-word-bank" placeholder="例如：presentation, entire, their, exceptional, public speaking, were, skills">${escapeHtml((data.wordBank || []).join(", "))}</textarea>
    </div>
    <div class="field">
      <label>正确填入顺序 <span class="field-hint">从左到右，每个空一个词块，数量必须等于空位数</span></label>
      <textarea id="${scope}-correct-order" placeholder="例如：their, public speaking, skills, were, exceptional, entire, presentation">${escapeHtml((data.correctOrder || []).join(", "))}</textarea>
      <p class="field-example">当前：空位 ${blankCount || 0} 个 · 正确顺序 ${orderCount || 0} 项</p>
      ${mismatch}
    </div>
    <div class="field">
      <label>完整正确句子</label>
      <input id="${scope}-complete-sentence" value="${attr(data.completeSentence || "")}" />
    </div>
  `;
}

function completeImportSummaryHtml(q) {
  // Import page uses dedicated completeWordsImportPreviewHtml instead
  return "";
}

function completePassagePreviewHtml(passage, blanks, readonly = false) {
  const meta = Object.fromEntries((blanks || []).map((b) => [String(b.id), b]));
  const source = String(passage || "");
  if (!source.trim()) return `<span class="subtle">暂无短文</span>`;

  // Underscore form preview: only mark underscore tokens
  if (hasCompleteWordBlank(source) && !/\[\[[^\]]+\]\]/.test(source)) {
    let i = 0;
    const html = escapeHtml(source).replace(/([A-Za-z]+)((?:[ \t]*_){2,})/g, (_, prefix, blankMark) => {
      i += 1;
      const blank = (blanks || [])[i - 1] || {};
      const ans = blank.answer || "";
      const underscores = "_".repeat(Math.max(2, (blankMark.match(/_/g) || []).length));
      return `${escapeHtml(prefix)}<span class="cw-preview-blank" title="${attr((blank.prefix || prefix) + (ans || ""))}">${escapeHtml(ans || underscores)}</span>`;
    });
    return `<div class="cw-passage preview">${html}</div>`;
  }

  const parts = [];
  let last = 0;
  const regex = /\[\[\s*([A-Za-z0-9_-]+)\s*\]\]/g;
  let match;
  let n = 0;
  while ((match = regex.exec(source))) {
    parts.push(escapeHtml(source.slice(last, match.index)));
    const id = match[1];
    const blank = meta[id] || {};
    const ans = blank.answer || "";
    const width = Math.max(2.5, Math.min(10, (ans.length || 4) + 1.2));
    n += 1;
    if (readonly) {
      parts.push(
        `<span class="cw-preview-blank" title="${attr((blank.prefix || "") + (blank.answer || ""))}">${escapeHtml(ans || "____")}</span>`,
      );
    } else {
      parts.push(
        `<span class="inline-blank"><input data-complete-id="${attr(id)}" style="width:${width}em" value="" autocomplete="off" spellcheck="false" /></span>`,
      );
    }
    last = regex.lastIndex;
  }
  parts.push(escapeHtml(source.slice(last)));
  if (!n) {
    return `<div class="cw-passage preview">${escapeHtml(source)}</div>`;
  }
  return `<div class="cw-passage preview">${parts.join("")}</div>`;
}

function completeFormHtml(q, scope) {
  // Library edit: passage preview only; blanks kept in hidden JSON for save
  const data = { ...defaultData("complete_words"), ...q.data };
  const blanks = data.blanks || [];
  return `
    <div class="field">
      <label>短文预览</label>
      <div class="cw-preview-panel">
        ${completePassagePreviewHtml(data.passageText || "", blanks, true)}
      </div>
      <input type="hidden" id="${scope}-passage" value="${attr(data.passageText || "")}" />
      <input type="hidden" id="${scope}-prompt" value="${attr(q.prompt || "Fill in the missing letters in the paragraph")}" />
      <input type="hidden" id="${scope}-blanks-json" value="${attr(JSON.stringify(blanks))}" />
    </div>
  `;
}

function changeFormType(scope) {
  const current = collectQuestionForm(scope, true);
  current.type = $(`${scope}-type`).value;
  current.data = defaultData(current.type);
  if (scope === "import") state.importDraft = current;
  if (scope === "edit") state.editQuestion = { ...state.editQuestion, ...current };
  state.formValidation = null;
  render();
}

function collectQuestionForm(scope, tolerant = false) {
  const type = $(`${scope}-type`)?.value || "reading_choice";
  const question = {
    type,
    title: type === "build_sentence" || type === "complete_words" ? "" : $(`${scope}-title`)?.value || "",
    article: "",
    prompt: "",
    explanation: $(`${scope}-explanation`)?.value || "",
    needsConfirmation: false,
    data: {},
  };

  if (type === "reading_choice") {
    question.article = $(`${scope}-article`)?.value || "";
    question.prompt = $(`${scope}-prompt`)?.value || "";
    question.data = {
      options: [0, 1, 2, 3].map((index) => ({
        key: String.fromCharCode(65 + index),
        text: $(`${scope}-option-${index}`)?.value || "",
      })),
      correctAnswer: $(`${scope}-correct`)?.value || "",
    };
    question.needsConfirmation = !question.data.correctAnswer;
  }

  if (type === "build_sentence") {
    question.prompt = $(`${scope}-prompt`)?.value || "";
    question.data = {
      sentenceTemplate: $(`${scope}-sentence-template`)?.value || "",
      wordBank: delimitedList($(`${scope}-word-bank`)?.value || ""),
      correctOrder: delimitedList($(`${scope}-correct-order`)?.value || ""),
      completeSentence: $(`${scope}-complete-sentence`)?.value || "",
    };
    question.needsConfirmation = question.data.correctOrder.length === 0;
  }

  if (type === "complete_words") {
    let passageText = $(`${scope}-passage`)?.value || "";
    let blanks = [];
    try {
      const raw = $(`${scope}-blanks-json`)?.value || "[]";
      blanks = JSON.parse(raw);
      if (!Array.isArray(blanks)) blanks = [];
    } catch {
      blanks = [];
    }
    // Client-side normalize underscores → markers if needed before save
    if (/_{2,}/.test(passageText) && !/\[\[[^\]]+\]\]/.test(passageText)) {
      const built = buildCompleteWordsFromFields(
        passageText,
        blanks.map((b) => b.answer || b.fullWord || "").join("\n"),
      );
      passageText = built.passageText;
      blanks = built.blanks;
    } else {
      blanks = blanks.map((blank, index) => {
        const prefix = blank.prefix || "";
        let answer = blank.answer || "";
        let fullWord = blank.fullWord || "";
        if (prefix && answer && answer.toLowerCase().startsWith(prefix.toLowerCase()) && answer.length > prefix.length) {
          fullWord = answer;
          answer = answer.slice(prefix.length);
        } else if (prefix && answer && !fullWord) {
          fullWord = prefix + answer;
        } else if (prefix && fullWord && !answer && fullWord.toLowerCase().startsWith(prefix.toLowerCase())) {
          answer = fullWord.slice(prefix.length);
        }
        return {
          id: blank.id || String(index + 1),
          prefix,
          answer,
          fullWord,
          blankLength: Number(blank.blankLength || blank.blankCount || blank.length || answer.length || 0),
          note: "",
          confirmed: Boolean(answer && fullWord),
        };
      });
    }
    question.data = { passageText, blanks };
    question.article = passageText;
    question.title = "";
    question.prompt = $(`${scope}-prompt`)?.value || "Fill in the missing letters in the paragraph";
    question.needsConfirmation = false;
  }

  if (!tolerant) return question;
  return question;
}

function isEmptyBuildQuestion(question) {
  const data = question.data || {};
  return (
    !String(question.prompt || "").trim() &&
    !String(question.explanation || "").trim() &&
    !String(data.sentenceTemplate || "").trim() &&
    !String(data.completeSentence || "").trim() &&
    !(data.wordBank || []).length &&
    !(data.correctOrder || []).length
  );
}

async function saveQuestion(scope) {
  const question = collectQuestionForm(scope);
  if (scope === "import" && question.type === "build_sentence" && isEmptyBuildQuestion(question)) {
    const rawText = collectImportRaw("build_sentence");
    if (rawText.trim()) {
      await parseImport();
      toast("已解析到预览，请确认后再保存");
      return;
    }
  }
  const isEdit = scope === "edit";
  if (scope === "import") state.importDraft = question;
  if (isEdit) state.editQuestion = { ...state.editQuestion, ...question };
  try {
    const saved = await api(isEdit ? `/api/questions/${state.editQuestion.id}` : "/api/questions", {
      method: isEdit ? "PUT" : "POST",
      body: JSON.stringify(question),
    });
    state.formValidation = null;
    state.importValidation = null;
    if (isEdit) {
      state.editQuestion = null;
      await navigate("library");
      toast("题目已更新");
    } else {
      state.importDraft = null;
      state.importRaw = "";
      await navigate("library");
      toast(`已保存：${saved.title || TYPE_NAMES[saved.type] || "题目"}`);
    }
  } catch (error) {
    const validation = error.data?.validation || { errors: [error.message] };
    if (scope === "import") state.importValidation = validation;
    state.formValidation = validation;
    render();
  }
}

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
        <button class="btn primary" type="button" onclick="navigate('import')">导入新题</button>
      </div>
      <section class="panel">
        <div class="filters">
          <select onchange="updateFilter('type', this.value)" aria-label="题型筛选">
            <option value="">全部题型</option>
            ${Object.entries(TYPE_NAMES)
              .map(([value, label]) => `<option value="${value}" ${f.type === value ? "selected" : ""}>${label}</option>`)
              .join("")}
          </select>
          <select onchange="updateFilter('sort', this.value)" aria-label="排序">
            <option value="created" ${f.sort === "created" ? "selected" : ""}>按创建时间</option>
            <option value="error_rate" ${f.sort === "error_rate" ? "selected" : ""}>按错误率排序</option>
            <option value="recent_practice" ${f.sort === "recent_practice" ? "selected" : ""}>按最近练习时间</option>
          </select>
          <input value="${attr(f.q)}" oninput="debouncedSearch(this.value)" placeholder="搜索题干或文章" aria-label="搜索" />
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
        <button class="btn" type="button" onclick="navigate('practice')">返回练习</button>
      </div>
      <section class="panel">
        <div class="filters">
          <select onchange="updateFilter('type', this.value)" aria-label="题型筛选">
            <option value="">全部题型</option>
            ${Object.entries(TYPE_NAMES)
              .map(([value, label]) => `<option value="${value}" ${f.type === value ? "selected" : ""}>${label}</option>`)
              .join("")}
          </select>
          <select onchange="updateFilter('sort', this.value)" aria-label="排序">
            <option value="created" ${f.sort === "created" ? "selected" : ""}>按创建时间</option>
            <option value="error_rate" ${f.sort === "error_rate" ? "selected" : ""}>按错误率排序</option>
            <option value="recent_practice" ${f.sort === "recent_practice" ? "selected" : ""}>按最近练习时间</option>
          </select>
          <input value="${attr(f.q)}" oninput="debouncedSearch(this.value)" placeholder="搜索题干或文章" aria-label="搜索" />
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
          <button class="btn" type="button" onclick="clearLibrarySelection()">取消</button>
          <button class="btn primary" type="button" onclick="startPracticeFromSelection()">开始练习</button>
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
    ? `<label class="card-select"><input type="checkbox" ${selected ? "checked" : ""} onchange="toggleLibrarySelect(${q.id})" /></label>`
    : "";
  const actionsHtml = selectable
    ? ""
    : `<div class="card-actions">
         <button class="btn small primary" type="button" onclick="practiceQuestion(${q.id})">练习</button>
         <button class="btn small" type="button" onclick="editQuestion(${q.id})">编辑</button>
         <button class="btn small danger" type="button" onclick="deleteQuestion(${q.id})">删除</button>
       </div>`;
  return `
    <article class="question-card ${highError ? "high-error" : ""} ${selected ? "selected" : ""}" data-id="${q.id}">
      <div class="question-card-head">
        ${selectHtml}
        <div>
          <div class="card-meta">
            <span class="type-badge">${TYPE_NAMES[q.type] || q.type}</span>
            ${highError ? `<span class="pill bad">高错误率 ${errorRate}%</span>` : ""}
            ${q.needsConfirmation ? `<span class="pill warn">待确认</span>` : ""}
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
  goToQuestion(0);
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
        <button class="btn" type="button" onclick="navigate('library')">返回题库</button>
      </div>
      <section class="panel">
        ${validationHtml(state.formValidation)}
        ${questionFormHtml(q, "edit")}
        <div class="toolbar actions">
          <button class="btn primary" type="button" onclick="saveQuestion('edit')">保存修改</button>
          <button class="btn" type="button" onclick="navigate('library')">取消</button>
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
          <button type="button" class="btn exam" onclick="exitPractice()">退出</button>
          <button type="button" class="btn exam" onclick="prevQuestion()" ${atFirst ? "disabled" : ""}>上一题</button>
          <button type="button" class="btn exam solid" onclick="nextQuestion()">${nextLabel}</button>
        </div>
      </div>
    </header>
  `;
}

function renderPractice() {
  const q = state.practiceQuestion;

  if (state.practiceFinished) {
    setPracticeModeClass(false);
    const answered = state.practiceQuestions.length || 0;
    const correct = state.practiceQuestions.filter((q) => q._result?.isCorrect).length;
    const pct = answered > 0 ? Math.round((correct / answered) * 100) : 0;
    $("app").innerHTML = `
      <div class="page">
        <div class="practice-home">
          <section class="panel practice-summary">
            <h1>练习完成</h1>
            <div class="summary-ring ${pct >= 80 ? "ok" : pct >= 50 ? "warn" : "bad"}">
              <span class="summary-pct">${pct}%</span>
            </div>
            <p class="subtle">本次共练习 ${answered} 道题，答对 ${correct} 道。</p>
            <div class="toolbar" style="justify-content:center;margin-top:18px">
              <button class="btn primary" type="button" onclick="restartPractice()">再来一轮</button>
              <button class="btn" type="button" onclick="exitPractice()">返回首页</button>
            </div>
          </section>
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
                      `<button type="button" class="practice-target-btn ${target === n ? "active" : ""}" data-target="${n}" onclick="setPracticeTarget(${n})">${n}</button>`,
                  )
                  .join("")}
              </div>
              <input type="number" class="target-input" id="practice-target-input" min="1" max="${maxNum}" value="${presets.includes(target) ? "" : target}" placeholder="自定义" onchange="setPracticeTargetFromInput()" />
            </div>
            ${
              state.practiceResult?.error
                ? `<div class="status error">${escapeHtml(state.practiceResult.error)}</div>`
                : `<div class="status soft-info">题库中约有 ${state.practiceTotal || 0} 道题可供练习。</div>`
            }
            <div class="toolbar" style="justify-content:center;margin-top:18px">
              <button class="btn primary" type="button" onclick="nextPractice()">开始练习</button>
              <button class="btn" type="button" onclick="navigate('practice_select')">从题库选择</button>
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
  setPracticeModeClass(false);
  renderPractice();
}

function restartPractice() {
  state.practiceFinished = false;
  state.practiceQuestion = null;
  state.practiceQuestions = [];
  state.practiceResult = null;
  state.practiceSessionIndex = 0;
  nextPractice();
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
    setPracticeModeClass(false);
    renderPractice();
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
            : `<button class="btn primary" type="button" onclick="submitPractice()" style="align-self:flex-start;min-width:120px">提交答案</button>`
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
    <p class="bs-prompt">${escapeHtml(q.prompt || "Build a sentence using the word bank.")}</p>
    ${submitted ? "" : `<p class="bs-hint">点击下方词块填入空位 · 再次点击空位可撤回 · 也支持拖拽词块到空位</p>`}
    <div class="bs-sentence-card">
      <div class="bs-sentence" aria-label="句子填空">
        ${renderInteractiveSentence(data.sentenceTemplate || "", wordBank, submitted, positions)}
      </div>
    </div>
    <div class="word-bank-section">
      <div class="word-bank-head">
        <h3>Word Bank</h3>
        <p class="subtle">${submitted ? "本题已提交" : "选择词块填入当前高亮空位"}</p>
      </div>
      <div class="word-bank">
        ${wordBank
          .map((word, index) => {
            const isUsed = used.has(String(index));
            return `<button type="button" class="word-token ${isUsed ? "used" : ""}" draggable="${submitted || isUsed ? "false" : "true"}" ondragstart="dragWord(event, ${index})" onclick="fillWord(${index})" ${submitted || isUsed ? "disabled" : ""}>${escapeHtml(word)}</button>`;
          })
          .join("")}
      </div>
    </div>
    ${
      submitted
        ? ""
        : `<div class="bs-actions">
            <button class="btn" type="button" onclick="resetBuildAnswer()">重置</button>
            <button class="btn primary" type="button" onclick="submitPractice()">提交答案</button>
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
      `<button type="button" class="${cls}" ${widthAttr} ondragover="event.preventDefault()" ondrop="dropWord(event, ${blankIndex})" onclick="onBlankClick(${blankIndex})" ${submitted ? "disabled" : ""} aria-label="填空位置 ${blankIndex + 1}">${label}</button>`,
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
        return `<button type="button" class="${cls}" ondragover="event.preventDefault()" ondrop="dropWord(event, ${i})" onclick="onBlankClick(${i})" ${submitted ? "disabled" : ""}>${filled ? escapeHtml(word) : "&nbsp;"}</button>`;
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
                <button class="btn primary" type="button" onclick="submitPractice()">提交答案</button>
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
          <button class="btn primary" type="button" onclick="nextQuestion()">${(Number(state.practiceSessionIndex) || 0) >= state.practiceQuestions.length - 1 ? "完成" : "下一题"}</button>
          <button class="btn" type="button" onclick="prevQuestion()" ${(Number(state.practiceSessionIndex) || 0) <= 0 ? "disabled" : ""}>上一题</button>
          <button class="btn" type="button" onclick="retryCurrent()">再练一次</button>
          <button class="btn ghost" type="button" onclick="exitPractice()">退出练习</button>
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

/* ===================== Settings ===================== */

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
        <form autocomplete="off" onsubmit="event.preventDefault(); saveSettings()">
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
            <button class="btn" type="button" onclick="testSettings()" ${state.settingsTesting ? "disabled" : ""}>
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
        <form autocomplete="off" onsubmit="event.preventDefault(); saveAuthSettings()">
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

function render() {
  updateAuthChrome();
  if (state.view === "login") return renderLogin();
  if (state.view === "import") return renderImport();
  if (state.view === "library") return renderLibrary();
  if (state.view === "practice_select") return renderPracticeSelect();
  if (state.view === "edit") return renderEdit();
  if (state.view === "practice") return renderPractice();
  if (state.view === "settings") return renderSettings();
}

/* ===================== Auth ===================== */

function renderLogin() {
  const err = state.authError;
  $("app").innerHTML = `
    <div class="login-page">
      <form class="login-card" autocomplete="on" onsubmit="event.preventDefault(); login()">
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

document.querySelectorAll(".top-nav-btn").forEach((button) => {
  if (button.id === "logout-btn") return;
  button.addEventListener("click", () => navigate(button.dataset.view));
});

window.navigate = navigate;
window.setImportTypeHint = setImportTypeHint;
window.parseImport = parseImport;
window.clearImport = clearImport;
window.changeFormType = changeFormType;
window.saveQuestion = saveQuestion;
window.saveCompleteWordsImport = saveCompleteWordsImport;
window.onReadingChoiceRawInput = onReadingChoiceRawInput;
window.onCompleteWordsRawInput = onCompleteWordsRawInput;
window.onCompleteWordsImportInput = onCompleteWordsImportInput;
window.detectCompleteWordsFromPassage = detectCompleteWordsFromPassage;
window.syncCompleteWordsFullWords = syncCompleteWordsFullWords;
window.updateFilter = updateFilter;
window.debouncedSearch = debouncedSearch;
window.toggleLibrarySelect = toggleLibrarySelect;
window.clearLibrarySelection = clearLibrarySelection;
window.startPracticeFromSelection = startPracticeFromSelection;
window.editQuestion = editQuestion;
window.deleteQuestion = deleteQuestion;
window.practiceQuestion = practiceQuestion;
window.setPracticeMode = setPracticeMode;
window.setPracticeTarget = setPracticeTarget;
window.setPracticeTargetFromInput = setPracticeTargetFromInput;
window.exitPractice = exitPractice;
window.restartPractice = restartPractice;
window.nextPractice = nextPractice;
window.nextQuestion = nextQuestion;
window.prevQuestion = prevQuestion;
window.submitPractice = submitPractice;
window.fillWord = fillWord;
window.clearSlot = clearSlot;
window.onBlankClick = onBlankClick;
window.resetBuildAnswer = resetBuildAnswer;
window.dragWord = dragWord;
window.dropWord = dropWord;
window.retryCurrent = retryCurrent;
window.showPracticeHelp = showPracticeHelp;
window.saveSettings = saveSettings;
window.testSettings = testSettings;
window.saveAuthSettings = saveAuthSettings;
window.login = login;
window.logout = logout;
window.state = state;

initApp();

render();
