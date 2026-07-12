import {
  TYPE_NAMES,
  TYPE_SECTIONS,
  IMPORT_TYPES,
  READING_CHOICE_RAW_FIELDS,
  BUILD_SENTENCE_RAW_FIELDS,
  COMPLETE_WORDS_SOURCE_FIELDS,
  state,
} from "../state.js";
import { escapeHtml, attr, lines, delimitedList } from "../utils.js";
import { $, toast, setPracticeModeClass, setView, updateAuthChrome } from "../ui.js";
import { api } from "../api.js";
import { app } from "../core.js";


const render = (...args) => app.render(...args);
const navigate = (...args) => app.navigate(...args);

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
  const legacy = { question: "", options: "" };
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
    const value = rawText.slice(start, end).trim();
    if (key === "question" || key === "options") legacy[key] = value;
    else fields[key] = value;
  });
  if (!fields.questionAndOptions) {
    fields.questionAndOptions = [legacy.question, legacy.options].filter(Boolean).join("\n\n");
  }
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
                    data-action="onReadingChoiceRawInput"
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
  labels["题目详情"] = "sentenceTemplate";
  labels["模板"] = "sentenceTemplate";
  labels["问题"] = "questioner";
  labels["待选词"] = "wordBank";
  labels["正确顺序"] = "correctAnswer";
  labels["完整句子"] = "correctAnswer";
  const pattern = /(?:^|\n)\s*(提问者|问题|题目详情|句子模板|模板|待选词|词库|正确答案|正确顺序|完整句子|解析)\s*[：:]\s*/g;
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

function buildSentenceRawTableHtmlFromFields(fields, parseDisabled) {
  const data = fields || emptyBuildSentenceRawFields();
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
                  >${escapeHtml(data[field.key] || "")}</textarea>
                </td>
              </tr>
            `,
          ).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function buildSentenceRawTableHtml(rawValue, parseDisabled) {
  return buildSentenceRawTableHtmlFromFields(parseBuildSentenceRawFields(rawValue), parseDisabled);
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
                    data-action="onCompleteWordsRawInput"
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
    // Prefer in-memory fields so switching away and back keeps the user's paste.
    const fields =
      state.buildSentenceRawFields && Object.values(state.buildSentenceRawFields).some((v) => String(v || "").trim())
        ? state.buildSentenceRawFields
        : parseBuildSentenceRawFields(rawValue);
    state.buildSentenceRawFields = fields;
    return buildSentenceRawTableHtmlFromFields(fields, parseDisabled);
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

function collectCompleteWordsSourceFields() {
  return Object.fromEntries(
    COMPLETE_WORDS_SOURCE_FIELDS.map((field) => [field.key, $(`complete-source-${field.key}`)?.value || ""]),
  );
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
  const draft = state.importDraft ? normalizeFormQuestion(state.importDraft) : emptyImportQuestion();
  const rawValue = state.importRaw || "";
  const parseDisabled = state.importLoading ? "disabled" : "";
  const hasDraft = Boolean(state.importDraft);
  const compactBuildPreview = hasDraft && draft.type === "build_sentence";
  const compactReadingPreview = hasDraft && draft.type === "reading_choice";
  const compactImportPreview = compactBuildPreview || compactReadingPreview;
  const readingSaveBlocked = compactReadingPreview && state.importValidation && !state.importValidation.ok;
  const rawLabelFor =
    state.importTypeHint === "reading_choice"
      ? "reading-raw-title"
      : state.importTypeHint === "build_sentence"
        ? "build-raw-questioner"
        : state.importTypeHint === "complete_words"
          ? "complete-source-passage"
          : "rawText";
  $("app").innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>导入错题</h1>
        </div>
        <button class="btn" type="button" data-action="navigate" data-arg="settings">LLM 设置</button>
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
              <select id="typeHint" ${parseDisabled} data-action="setImportTypeHint" data-value-from="this">
                <option value="reading_choice" ${state.importTypeHint === "reading_choice" ? "selected" : ""}>阅读选择题</option>
                <option value="build_sentence" ${state.importTypeHint === "build_sentence" ? "selected" : ""}>写作造句题</option>
                <option value="complete_words" ${state.importTypeHint === "complete_words" ? "selected" : ""}>阅读填词题</option>
              </select>
            </div>
            <div class="field">
              <label for="${rawLabelFor}">原始题目</label>
              ${rawImportInputHtml(rawValue, parseDisabled)}
            </div>
            ${progressHtml(state.importLoading, "正在解析题目")}
            ${errorHtml(state.importError)}
            <div class="toolbar actions">
              <button class="btn primary" type="button" data-action="parseImport" ${parseDisabled}>
                ${state.importLoading ? "正在解析题目" : "解析题目"}
              </button>
              <button class="btn" type="button" data-action="clearImport" ${parseDisabled}>清空</button>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>解析预览</h2>
          </div>
          ${
            compactImportPreview
              ? ""
              : hasDraft
              ? confirmationBanner(draft)
              : state.importTypeHint === "build_sentence" || state.importTypeHint === "reading_choice"
                ? `<div class="status soft-info">解析后将在此显示紧凑预览；如需修改，请编辑左侧原始题目后重新解析。</div>`
                : `<div class="status soft-info">解析后会按题型展示结构化字段，可在此直接修改。</div>`
          }
          ${compactImportPreview && state.importValidation?.ok ? "" : validationHtml(state.importValidation)}
          ${questionFormHtml(draft, "import")}
          <div class="toolbar actions">
            <button class="btn primary" type="button" data-action="saveQuestion" data-arg="import" ${hasDraft && !readingSaveBlocked ? "" : "disabled"}>保存进题库</button>
          </div>
        </section>
      </div>
    </div>
  `;
}

function setImportTypeHint(value) {
  const previousType = normalizeImportType(state.importTypeHint);
  const nextType = normalizeImportType(value);
  // change-only path: ignore no-ops so opening the native select never rebuilds DOM
  if (!nextType || nextType === previousType) return;

  // Persist the type the user is leaving so switching back restores their paste.
  if (previousType === "reading_choice") {
    state.readingChoiceRawFields = collectReadingChoiceRawFields();
  } else if (previousType === "complete_words") {
    state.completeWordsRawFields = collectCompleteWordsSourceFields();
  } else if (previousType === "build_sentence") {
    state.buildSentenceRawFields = collectBuildSentenceRawFields();
  }
  state.importRawByType = state.importRawByType || {};
  state.importRawByType[previousType] = collectImportRaw(previousType);

  state.importTypeHint = nextType;
  // Prefer type-scoped raw snapshot; never clobber structured fields with another type's text.
  if (state.importRawByType[nextType]) {
    state.importRaw = state.importRawByType[nextType];
  }
  if (nextType === "build_sentence" && !state.buildSentenceRawFields) {
    state.buildSentenceRawFields = parseBuildSentenceRawFields(state.importRawByType.build_sentence || "");
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
    // Snapshot fields before loading re-render so error paths never lose the paste.
    state.completeWordsRawFields = collectCompleteWordsSourceFields();
    state.importRaw = serializeCompleteWordsSourceRaw(state.completeWordsRawFields);
  }
  // Preserve left-side input across the loading re-render and any error path.
  const preservedRaw = state.importRaw;
  const preservedCompleteFields = state.completeWordsRawFields
    ? { ...state.completeWordsRawFields }
    : null;
  const preservedReadingFields = state.readingChoiceRawFields
    ? { ...state.readingChoiceRawFields }
    : null;
  const preservedBuildFields = state.buildSentenceRawFields
    ? { ...state.buildSentenceRawFields }
    : null;

  state.importError = null;
  state.importDraft = null;
  state.importValidation = null;
  state.importLoading = true;
  renderImport();
  try {
    const data = await api("/api/import/parse", {
      method: "POST",
      body: JSON.stringify({ rawText: preservedRaw, typeHint: state.importTypeHint }),
    });
    // Preserve the user's left-side raw input; only adopt server-echoed text if present
    state.importRaw = data.rawText || preservedRaw;
    state.importDraft = data.draft;
    state.importValidation = data.validation;
    toast("解析完成，请预览确认");
  } catch (error) {
    const details = Array.isArray(error.data?.details) ? error.data.details : [];
    // Never surface raw HTML / huge server bodies — api.js already sanitizes.
    const message =
      (error.data && error.data.error) ||
      error.message ||
      "服务器解析失败，请查看服务日志";
    state.importError = { message: String(message).slice(0, 200), details: details.map(String).slice(0, 10) };
    // Restore all left-side inputs exactly as the user left them
    state.importRaw = (error.data && error.data.rawText) || preservedRaw;
    if (preservedCompleteFields) state.completeWordsRawFields = preservedCompleteFields;
    if (preservedReadingFields) state.readingChoiceRawFields = preservedReadingFields;
    if (preservedBuildFields) state.buildSentenceRawFields = preservedBuildFields;
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
  state.readingChoiceRawFields = { title: "", article: "", questionAndOptions: "", correctAnswer: "", analysis: "" };
  state.buildSentenceRawFields = emptyBuildSentenceRawFields();
  state.completeWordsRawFields = { passage: "", answers: "", analysis: "" };
  state.completeWordsFields = { passage: "", answers: "", analysis: "" };
  state.importRawByType = { reading_choice: "", build_sentence: "", complete_words: "" };
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
      <div class="build-summary-row"><span class="k">题目详情</span><span class="v">${templatePreviewHtml(data.sentenceTemplate || "", false)}</span></div>
      <div class="build-summary-row"><span class="k">空位数</span><span class="v">${blanks} 个</span></div>
      <div class="build-summary-row">
        <span class="k">待选词</span>
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

function readingImportPreviewHtml(q) {
  if (!q || q.type !== "reading_choice") return "";
  const data = q.data || {};
  const options = Array.isArray(data.options) ? data.options : [];
  return `
    <div class="reading-import-preview">
      <div class="reading-preview-section reading-preview-title">
        <div class="reading-preview-label">标题</div>
        <h3>${escapeHtml(q.title || "—")}</h3>
      </div>
      <div class="reading-preview-section">
        <div class="reading-preview-label">阅读文章</div>
        <div class="reading-preview-article">${escapeHtml(q.article || "—")}</div>
      </div>
      <div class="reading-preview-question-block">
        <div class="reading-preview-label">问题</div>
        <div class="reading-preview-question">${escapeHtml(q.prompt || "—")}</div>
        <div class="reading-preview-options">
          ${["A", "B", "C", "D"].map((key) => {
            const option = options.find((item) => String(item?.key || "").toUpperCase() === key);
            return `
              <div class="reading-preview-option">
                <span class="option-key">${key}</span>
                <span class="option-text">${escapeHtml(option?.text || "—")}</span>
              </div>
            `;
          }).join("")}
        </div>
      </div>
      <div class="reading-preview-answer">
        <span class="reading-preview-label">正确答案</span>
        <strong>${escapeHtml(data.correctAnswer || "—")}</strong>
      </div>
      ${q.explanation ? `
        <div class="reading-preview-explanation">
          <div class="reading-preview-label">解析</div>
          <div>${escapeHtml(q.explanation)}</div>
        </div>
      ` : ""}
    </div>
  `;
}

function questionFormHtml(question, scope) {
  const q = normalizeFormQuestion(question);
  if (scope === "import" && q.type === "reading_choice") {
    return state.importDraft ? readingImportPreviewHtml(q) : "";
  }
  // The import preview is intentionally read-only for build_sentence. Editing
  // happens in the structured source table on the left, followed by re-parse.
  if (scope === "import" && q.type === "build_sentence") {
    return state.importDraft ? buildImportSummaryHtml(q) : "";
  }
  return `
    <div class="field">
      <label>题型</label>
      <select id="${scope}-type" data-action="changeFormType" data-arg="${scope}">
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

function templatePreviewHtml(template, showLabel = true) {
  const source = String(template || "");
  if (!source.trim()) {
    return `<div class="status warn">尚未识别题目详情。请在左侧补充题目详情，或提供完整正确答案与待选词后重新解析。</div>`;
  }
  const html = escapeHtml(source)
    .replace(/\{\{\s*(?:blank|\d+)\s*\}\}|_{2,}/gi, '<span class="tpl-blank-mark">____</span>')
    .replace(/\n/g, "<br>");
  const blanks = countTemplateBlanksClient(source);
  return `
    <div class="template-preview">
      ${showLabel ? `<div class="template-preview-label">题目详情预览 · ${blanks} 个空位</div>` : ""}
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
      <label>题目详情 <span class="field-hint">空位用 ____ 或 {{blank}}；固定词原样保留</span></label>
      <textarea id="${scope}-sentence-template" placeholder="空位用 ____ 或 {{blank}}；固定词原样保留">${escapeHtml(data.sentenceTemplate)}</textarea>
      ${templatePreviewHtml(data.sentenceTemplate)}
    </div>
    <div class="field">
      <label>待选词 <span class="field-hint">逗号隔开；可多于空位数，但不要放入固定文本</span></label>
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
  const nextType = $(`${scope}-type`)?.value;
  const currentDraft =
    scope === "import" ? state.importDraft : scope === "edit" ? state.editQuestion : null;
  // Avoid full re-render when the select value did not actually change
  if (currentDraft && currentDraft.type === nextType) return;

  const current = collectQuestionForm(scope, true);
  current.type = nextType;
  current.data = defaultData(current.type);
  if (scope === "import") state.importDraft = current;
  if (scope === "edit") state.editQuestion = { ...state.editQuestion, ...current };
  state.formValidation = null;
  render();
}

function collectQuestionForm(scope, tolerant = false) {
  if (
    scope === "import" &&
    (state.importDraft?.type === "reading_choice" || state.importDraft?.type === "build_sentence")
  ) {
    // Read-only import previews save the normalized LLM/local parser draft
    // directly; editing happens in the structured source table on the left.
    return normalizeFormQuestion(state.importDraft);
  }
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
  // Parse-time warnings stay on the import page. Clicking save explicitly
  // confirms a valid draft; the backend enforces the same invariant again.
  question.needsConfirmation = false;
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


export {
  validationHtml,
  errorHtml,
  progressHtml,
  defaultData,
  normalizeFormQuestion,
  emptyImportQuestion,
  normalizeImportType,
  emptyReadingChoiceRawFields,
  parseReadingChoiceRawFields,
  readingChoiceRawTableHtml,
  emptyBuildSentenceRawFields,
  parseBuildSentenceRawFields,
  buildSentenceRawTableHtml,
  escapeRegExp,
  completeWordsRawInputHtml,
  buildSentenceRawTableHtmlFromFields,
  parseCompleteAnswersClient,
  hasCompleteWordBlank,
  buildCompleteWordsFromFields,
  hasReadingChoiceRawContent,
  currentReadingChoiceRawFields,
  rawImportInputHtml,
  collectReadingChoiceRawFields,
  serializeReadingChoiceRaw,
  collectBuildSentenceRawFields,
  serializeBuildSentenceRaw,
  collectCompleteWordsSourceFields,
  serializeCompleteWordsSourceRaw,
  collectImportRaw,
  confirmationBanner,
  onReadingChoiceRawInput,
  onCompleteWordsRawInput,
  renderImport,
  setImportTypeHint,
  parseImport,
  clearImport,
  buildImportSummaryHtml,
  readingImportPreviewHtml,
  questionFormHtml,
  readingFormHtml,
  countTemplateBlanksClient,
  normalizeTemplateClient,
  templatePreviewHtml,
  buildFormHtml,
  completeImportSummaryHtml,
  completePassagePreviewHtml,
  completeFormHtml,
  changeFormType,
  collectQuestionForm,
  isEmptyBuildQuestion,
  saveQuestion,
};
