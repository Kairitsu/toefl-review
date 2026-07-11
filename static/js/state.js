/** Shared application state and static labels (no DOM). */

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
  reportFilter: "all",
  reportSelectedIndex: 0,
  practiceHistory: [],
  viewedSession: null,
  practiceSavedSessionId: null,
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


export {
  TYPE_NAMES,
  TYPE_SECTIONS,
  IMPORT_TYPES,
  READING_CHOICE_RAW_FIELDS,
  BUILD_SENTENCE_RAW_FIELDS,
  COMPLETE_WORDS_RAW_FIELDS,
  COMPLETE_WORDS_SOURCE_FIELDS,
  state,
};
