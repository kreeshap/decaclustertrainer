(function () {
  const MODE_STORAGE_KEY = "ct_practice_mode";
  const FILTER_STORAGE_KEY = "ct_practice_question_filter";
  const SESSION_LENGTH_STORAGE_KEY = "ct_practice_session_length";
  const TIMED_MODE_STORAGE_KEY = "ct_practice_timed_mode";
  const REVIEW_MODE_STORAGE_KEY = "ct_practice_review_mode";
  const DAILY_LIMIT = 3;
  const QUESTION_SECONDS = 60;

  const MODE_LABELS = {
    adaptive: "Adaptive",
    mixed: "Mixed",
    daily: "Daily",
    random: "Random",
  };

  const FILTER_LABELS = {
    all: "All",
    recognition: "Recognition",
    application: "Application",
  };

  const state = {
    currentEventId: "",
    currentEventName: "",
    currentEventCluster: "",
    analytics: null,
    practiceMode: "adaptive",
    questionFilter: "all",
    sessionLength: "10",
    timedMode: false,
    reviewMode: true,
    allQuestions: [],
    queue: [],
    cursor: 0,
    currentQuestion: null,
    selectedChoice: null,
    answerLocked: false,
    questionStartAt: 0,
    firstSelectionAt: null,
    answerChangeCount: 0,
    retryRound: 0,
    missed: [],
    hadMisses: false,
    sessionId: null,
    sessionStartAt: null,
    sessionTimerId: null,
    sessionDurationLimitSeconds: 0,
    sessionRemainingSeconds: 0,
    reviewEntries: [],
    currentBenchmark: null,
    benchmarkCache: new Map(),
    engineBias: {
      recognitionBoost: 0,
      applicationBoost: 0,
      applicationPenalty: 0,
      recognitionPenalty: 0,
    },
    stats: {
      answered: 0,
      correct: 0,
      recognitionAnswered: 0,
      recognitionCorrect: 0,
      applicationAnswered: 0,
      applicationCorrect: 0,
      totalResponseMs: 0,
    },
  };

  const $ = (id) => document.getElementById(id);

  const el = {
    home: $("practice-home"),
    session: $("practice-session"),
    summary: $("practice-summary"),
    status: $("practice-status"),
    focus: $("practice-focus"),
    start: $("start-practice-btn"),
    refresh: $("refresh-practice-btn"),
    masteryRing: $("practice-mastery-ring"),
    heroTitle: $("practice-hero-title"),
    heroSubtitle: $("practice-hero-subtitle"),
    eventName: $("practice-event-name"),
    eventCluster: $("practice-event-cluster"),
    dueCount: $("practice-due-count"),
    avgMastery: $("practice-avg-mastery"),
    accuracy: $("practice-accuracy"),
    estimatedTime: $("practice-estimated-time"),
    overviewDue: $("practice-overview-due"),
    overviewTime: $("practice-overview-time"),
    overviewMastery: $("practice-overview-mastery"),
    overviewAccuracy: $("practice-overview-accuracy"),
    overviewStreak: $("practice-overview-streak"),
    sessionLengthLabel: $("practice-session-length-label"),
    modeLabel: $("practice-mode-label"),
    heroMastery: $("practice-hero-mastery"),
    recentSessionTitle: $("practice-recent-session-title"),
    recentSessionSubtitle: $("practice-recent-session-subtitle"),
    recentAccuracy: $("practice-recent-accuracy"),
    recentAnswered: $("practice-recent-answered"),
    recentCorrect: $("practice-recent-correct"),
    recentDuration: $("practice-recent-duration"),
    focusList: $("practice-focus-list"),
    focusEmpty: $("practice-focus-empty"),
    sessionTitle: $("practice-session-title"),
    progressCurrent: $("practice-progress-current"),
    progressTotal: $("practice-progress-total"),
    progressFill: $("practice-progress-fill"),
    questionType: $("practice-question-type"),
    questionStem: $("practice-question-stem"),
    choiceList: $("practice-choice-list"),
    checkBtn: $("practice-check-btn"),
    nextBtn: $("practice-next-btn"),
    exitBtn: $("exit-session-btn"),
    feedback: $("practice-feedback"),
    feedbackKicker: $("practice-feedback-kicker"),
    feedbackCopy: $("practice-feedback-copy"),
    feedbackExplanation: $("practice-feedback-explanation"),
    feedbackAnswer: $("practice-feedback-answer"),
    feedbackDistractors: $("practice-feedback-distractors"),
    qualityBadge: $("practice-quality-badge"),
    benchmarkBadge: $("practice-benchmark-badge"),
    benchmarkCopy: $("practice-benchmark-copy"),
    benchmarkAccuracy: $("practice-benchmark-accuracy"),
    benchmarkSpeed: $("practice-benchmark-speed"),
    benchmarkAttempts: $("practice-benchmark-attempts"),
    benchmarkQuality: $("practice-benchmark-quality"),
    reportToggle: $("practice-report-toggle"),
    reportPanel: $("practice-report-panel"),
    reportReason: $("practice-report-reason"),
    reportDetails: $("practice-report-details"),
    reportSubmit: $("practice-report-submit"),
    reportCancel: $("practice-report-cancel"),
    reportStatus: $("practice-report-status"),
    viewQuestionBtn: $("practice-view-question-btn"),
    questionViewer: $("practice-question-viewer"),
    questionViewerClose: $("practice-question-viewer-close"),
    questionViewerType: $("practice-question-viewer-type"),
    questionViewerKpi: $("practice-question-viewer-kpi"),
    questionViewerCluster: $("practice-question-viewer-cluster"),
    questionViewerStem: $("practice-question-viewer-stem"),
    questionViewerExplanation: $("practice-question-viewer-explanation"),
    questionViewerAnswer: $("practice-question-viewer-answer"),
    questionViewerDistractors: $("practice-question-viewer-distractors"),
    trackingBadge: $("practice-tracking-badge"),
    trackingAccuracy: $("practice-tracking-accuracy"),
    trackingAnswered: $("practice-tracking-answered"),
    trackingCorrect: $("practice-tracking-correct"),
    trackingMastered: $("practice-tracking-mastered"),
    trackingDue: $("practice-tracking-due"),
    trackingStreak: $("practice-tracking-streak"),
    trackingMastery: $("practice-tracking-mastery"),
    trackingFill: $("practice-tracking-fill"),
    trackingNote: $("practice-tracking-note"),
    historyCount: $("practice-history-count"),
    historyList: $("practice-history-list"),
    sessionLengthSelect: $("practice-session-length"),
    timedButtons: Array.from(document.querySelectorAll("[data-session-timed]")),
    reviewToggle: $("practice-review-toggle"),
    sessionTimer: $("practice-session-timer"),
    intelSummary: $("practice-intel-summary"),
    intelChoice: $("practice-intel-choice"),
    intelState: $("practice-intel-state"),
    intelSplit: $("practice-intel-split"),
    intelNext: $("practice-intel-next"),
    modeButtons: Array.from(document.querySelectorAll("[data-practice-mode]")),
    filterButtons: Array.from(document.querySelectorAll("[data-question-filter]")),
    summaryNote: $("practice-summary-note"),
    summaryAccuracy: $("practice-summary-accuracy"),
    summaryCorrect: $("practice-summary-correct"),
    summaryAverage: $("practice-summary-average"),
    summaryAnswered: $("practice-summary-answered"),
    summaryRecognition: $("practice-summary-recognition"),
    summaryRecognitionDetail: $("practice-summary-recognition-detail"),
    summaryApplication: $("practice-summary-application"),
    summaryApplicationDetail: $("practice-summary-application-detail"),
    summaryRetries: $("practice-summary-retries"),
    reviewPanel: $("practice-review-panel"),
    reviewCount: $("practice-review-count"),
    reviewList: $("practice-review-list"),
    summaryRetake: $("practice-summary-retake"),
    summaryHome: $("practice-summary-home"),
  };

  function escHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function showView(view) {
    const views = [el.home, el.session, el.summary];
    views.forEach((node) => {
      if (!node) return;
      node.classList.toggle("is-hidden", node !== view);
    });
  }

  function setStatus(message) {
    if (el.status) el.status.textContent = message;
  }

  function setSessionTitle(message) {
    if (el.sessionTitle) el.sessionTitle.textContent = message;
  }

  function setFocus(message) {
    if (el.focus) el.focus.textContent = message;
  }

  function formatSeconds(ms) {
    return `${(ms / 1000).toFixed(1)}s`;
  }

  function formatDurationSeconds(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    if (total < 60) {
      return `${total}s`;
    }
    const minutes = Math.floor(total / 60);
    const remainder = total % 60;
    if (!remainder) {
      return `${minutes} min`;
    }
    return `${minutes}m ${remainder}s`;
  }

  function formatDateLabel(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(date);
  }

  function formatSignedPct(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "--";
    const rounded = Math.round(numeric);
    return `${rounded > 0 ? "+" : ""}${rounded}%`;
  }

  function formatPct(value, fallback = "--") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
    return `${Math.round(Number(value))}%`;
  }

  function average(values) {
    if (!values.length) return 0;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function readStoredValue(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value !== null ? value : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function writeStoredValue(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (error) {
      // Ignore storage failures and fall back to in-memory state.
    }
  }

  function normalizeChoiceFilter(value) {
    if (value === "recognition" || value === "application") return value;
    return "all";
  }

  function normalizeMode(value) {
    if (value === "mixed" || value === "daily" || value === "random") return value;
    return "adaptive";
  }

  function normalizeSessionLength(value) {
    const raw = String(value || "10").trim();
    if (raw === "all") return "all";
    const parsed = Number.parseInt(raw, 10);
    if (Number.isFinite(parsed) && parsed > 0) {
      return String(Math.min(Math.max(parsed, 5), 50));
    }
    return "10";
  }

  function normalizeBoolean(value, fallback = false) {
    if (value === true || value === "true" || value === "1") return true;
    if (value === false || value === "false" || value === "0") return false;
    return fallback;
  }

  function hashSeed(value) {
    let hash = 2166136261;
    for (let i = 0; i < value.length; i += 1) {
      hash ^= value.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function seededRandom(seed) {
    let value = hashSeed(seed) || 1;
    return function next() {
      value = (value * 1664525 + 1013904223) >>> 0;
      return value / 0x100000000;
    };
  }

  function seededShuffle(list, seed) {
    const copy = list.slice();
    const rand = seededRandom(seed);
    for (let i = copy.length - 1; i > 0; i -= 1) {
      const j = Math.floor(rand() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  }

  function dedupeQuestions(questions) {
    const seen = new Map();
    questions.forEach((question) => {
      if (!question) return;
      const key = question.id
        || `${question.kpi_code || ""}|${question.question_type || "recognition"}|${question.text || ""}`;
      if (!seen.has(key)) {
        seen.set(key, question);
      }
    });
    return Array.from(seen.values());
  }

  function filterQuestionsByType(questions) {
    if (state.questionFilter === "recognition") {
      return questions.filter((question) => (question.question_type || "recognition") !== "application");
    }
    if (state.questionFilter === "application") {
      return questions.filter((question) => (question.question_type || "recognition") === "application");
    }
    return questions;
  }

  function getPracticeModeLabel(mode = state.practiceMode) {
    return MODE_LABELS[mode] || MODE_LABELS.adaptive;
  }

  function getQuestionFilterLabel(filter = state.questionFilter) {
    return FILTER_LABELS[filter] || FILTER_LABELS.all;
  }

  function getPracticeSeed() {
    const datePart = new Date().toISOString().slice(0, 10);
    return `${state.currentEventId || "event"}:${datePart}`;
  }

  function interleaveQuestionTypes(questions) {
    const recognition = questions.filter((question) => (question.question_type || "recognition") !== "application");
    const application = questions.filter((question) => (question.question_type || "recognition") === "application");
    const mixed = [];
    let takeApplication = application.length >= recognition.length;

    while (recognition.length || application.length) {
      if ((takeApplication && application.length) || !recognition.length) {
        mixed.push(application.shift());
      } else {
        mixed.push(recognition.shift());
      }
      takeApplication = !takeApplication;
    }

    return mixed;
  }

  function balanceMixedMode(questions) {
    const adaptive = buildAdaptiveQueue(questions);
    return interleaveQuestionTypes(adaptive);
  }

  function buildAdaptiveQueue(questions) {
    return questions
      .slice()
      .sort((a, b) => scoreQuestion(a) - scoreQuestion(b));
  }

  function buildPracticeQueue(questions, options = {}) {
    const allowDailyLimit = options.allowDailyLimit !== false;
    const filtered = filterQuestionsByType(dedupeQuestions(questions));
    const seed = getPracticeSeed();

    if (!filtered.length) {
      return [];
    }

    if (state.practiceMode === "random") {
      return seededShuffle(filtered, `${seed}:random`);
    }

    if (state.practiceMode === "daily") {
      const shuffled = seededShuffle(buildAdaptiveQueue(filtered), `${seed}:daily`);
      return allowDailyLimit ? shuffled.slice(0, Math.min(DAILY_LIMIT, shuffled.length)) : shuffled;
    }

    if (state.practiceMode === "mixed") {
      return balanceMixedMode(filtered);
    }

    return buildAdaptiveQueue(filtered);
  }

  function getSessionLengthLimit(totalQuestions = state.allQuestions.length) {
    if (state.sessionLength === "all") {
      return totalQuestions;
    }
    const parsed = Number.parseInt(state.sessionLength, 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return Math.min(10, totalQuestions);
    }
    return Math.min(parsed, totalQuestions);
  }

  function getSessionDurationSeconds() {
    if (!state.timedMode) return 0;
    const limit = getSessionLengthLimit(state.allQuestions.length) || state.allQuestions.length || 1;
    return Math.max(60, limit * QUESTION_SECONDS);
  }

  function clearSessionTimer() {
    if (state.sessionTimerId) {
      window.clearInterval(state.sessionTimerId);
      state.sessionTimerId = null;
    }
  }

  function renderSessionTimer() {
    if (!el.sessionTimer) return;
    if (!state.timedMode) {
      el.sessionTimer.textContent = "Untimed";
      renderSessionIntelligence();
      return;
    }
    const remaining = Math.max(0, state.sessionRemainingSeconds);
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    el.sessionTimer.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    renderSessionIntelligence();
  }

  function startSessionTimer() {
    clearSessionTimer();
    state.sessionDurationLimitSeconds = getSessionDurationSeconds();
    state.sessionRemainingSeconds = state.sessionDurationLimitSeconds;
    renderSessionTimer();
    if (!state.timedMode || state.sessionDurationLimitSeconds <= 0) return;
    state.sessionTimerId = window.setInterval(() => {
      if (state.sessionRemainingSeconds <= 0) {
        clearSessionTimer();
        setStatus("Timed session ended.");
        finishSession();
        return;
      }
      state.sessionRemainingSeconds -= 1;
      renderSessionTimer();
    }, 1000);
  }

  function updateSessionSettingsUI() {
    if (el.sessionLengthSelect) {
      el.sessionLengthSelect.value = state.sessionLength;
    }
    if (el.timedButtons.length) {
      el.timedButtons.forEach((button) => {
        const isActive = normalizeBoolean(button.dataset.sessionTimed, false) === state.timedMode;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
    }
    if (el.reviewToggle) {
      el.reviewToggle.classList.toggle("active", state.reviewMode);
      el.reviewToggle.textContent = state.reviewMode ? "Review On" : "Review Off";
      el.reviewToggle.setAttribute("aria-pressed", String(state.reviewMode));
    }
    renderSessionTimer();
  }

  function setSessionLength(value) {
    state.sessionLength = normalizeSessionLength(value);
    writeStoredValue(SESSION_LENGTH_STORAGE_KEY, state.sessionLength);
    updateSessionSettingsUI();
    renderHomeStats();
  }

  function setTimedMode(value) {
    state.timedMode = normalizeBoolean(value, false);
    writeStoredValue(TIMED_MODE_STORAGE_KEY, state.timedMode ? "true" : "false");
    updateSessionSettingsUI();
  }

  function setReviewMode(value) {
    state.reviewMode = normalizeBoolean(value, true);
    writeStoredValue(REVIEW_MODE_STORAGE_KEY, state.reviewMode ? "true" : "false");
    updateSessionSettingsUI();
  }

  function syncFilterControls() {
    if (el.modeButtons.length) {
      el.modeButtons.forEach((button) => {
        const isActive = (button.dataset.practiceMode || "") === state.practiceMode;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
    }
    if (el.filterButtons.length) {
      el.filterButtons.forEach((button) => {
        const isActive = (button.dataset.questionFilter || "") === state.questionFilter;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
    }
  }

  function setPracticeMode(mode) {
    state.practiceMode = normalizeMode(mode);
    writeStoredValue(MODE_STORAGE_KEY, state.practiceMode);
    syncFilterControls();
  }

  function setQuestionFilter(filter) {
    state.questionFilter = normalizeChoiceFilter(filter);
    writeStoredValue(FILTER_STORAGE_KEY, state.questionFilter);
    syncFilterControls();
  }

  function uniqueKpis(questions) {
    return Array.from(
      new Set(
        questions
          .map((q) => q.kpi_code || "")
          .filter(Boolean),
      ),
    );
  }

  function shuffle(list) {
    const copy = list.slice();
    for (let i = copy.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  }

  function masteryForQuestion(question) {
    const row = (state.analytics?.kpi_mastery || []).find(
      (item) => item.kpi_code === question.kpi_code,
    );
    return Number(row?.mastery_score ?? 50);
  }

  function typeAccuracy(type) {
    const row = state.analytics?.question_type_breakdown?.[type];
    return row ? Number(row.accuracy ?? 50) : 50;
  }

  function questionQualityState(question) {
    return question?.quality_state || {};
  }

  function getBenchmarkData(question) {
    return question?.benchmark || questionQualityState(question).benchmark || null;
  }

  function mcqQuality(question) {
    return questionQualityState(question).mcq_quality || null;
  }

  function mcqQualityLabel(score) {
    if (score >= 85) return "Strong";
    if (score >= 70) return "Usable";
    if (score >= 55) return "Fair";
    return "Weak";
  }

  function mcqQualityClass(score) {
    if (score >= 85) return "is-strong";
    if (score >= 70) return "is-usable";
    if (score >= 55) return "is-weak";
    return "";
  }

  function scoreQuestion(question) {
    let score = masteryForQuestion(question);
    const type = question.question_type || "recognition";
    const recogAccuracy = typeAccuracy("recognition");
    const appAccuracy = typeAccuracy("application");

    if (type === "application") {
      score += state.engineBias.applicationPenalty;
      score -= state.engineBias.applicationBoost;
      if (appAccuracy + 5 < recogAccuracy) {
        score -= 12;
      }
    } else {
      score += state.engineBias.recognitionPenalty;
      score -= state.engineBias.recognitionBoost;
      if (recogAccuracy + 5 < appAccuracy) {
        score -= 12;
      }
    }

    const srsAccuracy = Number(question.srs?.accuracy ?? 0);
    if (srsAccuracy > 0) {
      score -= Math.max(0, 60 - srsAccuracy) * 0.2;
    }

    if ((state.analytics?.weak_kpis || []).some((kpi) => kpi.kpi_code === question.kpi_code)) {
      score -= 10;
    }

    const quality = mcqQuality(question);
    if (quality && typeof quality.score === "number") {
      if (quality.score < 45) {
        score += 16;
      } else if (quality.score < 60) {
        score += 8;
      } else if (quality.score >= 85) {
        score -= 4;
      }
    }

    return score + Math.random() * 3;
  }

  function rebalanceUpcomingQuestions() {
    if (!state.queue.length) return;
    const prefix = state.queue.slice(0, state.cursor + 1);
    const remaining = state.queue.slice(state.cursor + 1);
    state.queue = prefix.concat(buildPracticeQueue(remaining, { allowDailyLimit: false }));
  }

  function applyEngineHints(queueActions) {
    if (!Array.isArray(queueActions) || !queueActions.length) return;
    if (queueActions.includes("increase_recognition_weight")) {
      state.engineBias.recognitionBoost += 10;
      state.engineBias.applicationPenalty += 4;
    }
    if (queueActions.includes("defer_application_questions")) {
      state.engineBias.applicationPenalty += 14;
    }
    rebalanceUpcomingQuestions();
  }

  function renderHomeStats() {
    const masteryRows = state.analytics?.kpi_mastery || [];
    const avgMastery = masteryRows.length
      ? average(masteryRows.map((row) => Number(row.mastery_score ?? 0)))
      : 0;

    const recog = state.analytics?.question_type_breakdown?.recognition || null;
    const app = state.analytics?.question_type_breakdown?.application || null;
    const accuracyValues = [];
    if (recog) accuracyValues.push(Number(recog.accuracy ?? 0));
    if (app) accuracyValues.push(Number(app.accuracy ?? 0));
    const currentAccuracy = accuracyValues.length ? average(accuracyValues) : null;

    if (el.avgMastery) el.avgMastery.textContent = formatPct(avgMastery, "--");
    if (el.accuracy) el.accuracy.textContent = formatPct(currentAccuracy, "--");
    if (el.dueCount) el.dueCount.textContent = String(state.allQuestions.length);
    if (el.start) {
      const lengthLabel = state.sessionLength === "all"
        ? "All Questions"
        : `${state.sessionLength} Questions`;
      el.start.textContent = state.allQuestions.length
        ? `Start ${lengthLabel}`
        : "No Questions Available";
    }
    renderSessionIntelligence();
  }

  function renderHomeFocus() {
    const recog = state.analytics?.question_type_breakdown?.recognition || null;
    const app = state.analytics?.question_type_breakdown?.application || null;
    const recogAcc = recog ? Number(recog.accuracy ?? 0) : null;
    const appAcc = app ? Number(app.accuracy ?? 0) : null;
    const weakKpi = (state.analytics?.weak_kpis || [])[0];
    const modeLabel = getPracticeModeLabel();
    const filterLabel = getQuestionFilterLabel();

    if (weakKpi && typeof weakKpi.kpi_code === "string") {
      setFocus(`${modeLabel} · ${filterLabel} · Next focus: ${weakKpi.kpi_code}`);
      return;
    }

    if (recogAcc !== null && appAcc !== null) {
      if (appAcc + 5 < recogAcc) {
        setFocus(`${modeLabel} · ${filterLabel} · Focus: application scenarios`);
        return;
      }
      if (recogAcc + 5 < appAcc) {
        setFocus(`${modeLabel} · ${filterLabel} · Focus: recognition recall`);
        return;
      }
    }

    setFocus(`${modeLabel} · ${filterLabel} · Balanced practice`);
  }

  function renderRecentSessionCard() {
    if (!el.recentSessionTitle && !el.recentSessionSubtitle) return;

    const sessions = state.analytics?.recent_sessions || [];
    const recent = sessions[0] || null;

    if (!recent) {
      if (el.recentSessionTitle) el.recentSessionTitle.textContent = "No session yet";
      if (el.recentSessionSubtitle) el.recentSessionSubtitle.textContent = "Start a practice run to populate this card.";
      if (el.recentAccuracy) el.recentAccuracy.textContent = "--";
      if (el.recentAnswered) el.recentAnswered.textContent = "--";
      if (el.recentCorrect) el.recentCorrect.textContent = "--";
      if (el.recentDuration) el.recentDuration.textContent = "--";
      return;
    }

    const answered = Number(recent.questions_answered ?? 0);
    const correct = Number(recent.questions_correct ?? 0);
    const accuracy = answered ? Math.round((correct / answered) * 100) : 0;
    const duration = formatDurationSeconds(recent.duration_seconds || 0);
    const started = formatDateLabel(recent.started_at);
    const title = recent.session_type
      ? recent.session_type.replaceAll("_", " ")
      : "Latest practice session";

    if (el.recentSessionTitle) el.recentSessionTitle.textContent = title;
    if (el.recentSessionSubtitle) {
      el.recentSessionSubtitle.textContent = started
        ? `${started} · ${duration}`
        : `${duration} total`;
    }
    if (el.recentAccuracy) el.recentAccuracy.textContent = `${accuracy}%`;
    if (el.recentAnswered) el.recentAnswered.textContent = String(answered);
    if (el.recentCorrect) el.recentCorrect.textContent = String(correct);
    if (el.recentDuration) el.recentDuration.textContent = duration;
  }

  function renderHomeStats() {
    const summary = state.analytics?.summary || {};
    const masteryRows = state.analytics?.kpi_mastery || [];
    const avgMastery = Number(summary.avg_mastery ?? (
      masteryRows.length
        ? average(masteryRows.map((row) => Number(row.mastery_score ?? 0)))
        : 0
    ));

    const recog = state.analytics?.question_type_breakdown?.recognition || null;
    const app = state.analytics?.question_type_breakdown?.application || null;
    const accuracyValues = [];
    if (recog) accuracyValues.push(Number(recog.accuracy ?? 0));
    if (app) accuracyValues.push(Number(app.accuracy ?? 0));
    const currentAccuracy = accuracyValues.length ? average(accuracyValues) : null;
    const dueCount = Number(summary.questions_due ?? 0) || state.allQuestions.length || 0;
    const streak = Number(summary.streak_days ?? 0);
    const estimatedTimeLabel = formatDurationSeconds(getSessionLengthLimit(state.allQuestions.length) * QUESTION_SECONDS);
    const masteryLabel = formatPct(avgMastery, "--");
    const accuracyLabel = formatPct(currentAccuracy, "--");
    const lengthLabel = state.sessionLength === "all"
      ? "All available"
      : `${state.sessionLength} questions`;

    if (el.avgMastery) el.avgMastery.textContent = masteryLabel;
    if (el.accuracy) el.accuracy.textContent = accuracyLabel;
    if (el.dueCount) el.dueCount.textContent = String(dueCount);
    if (el.estimatedTime) el.estimatedTime.textContent = estimatedTimeLabel;
    if (el.overviewDue) el.overviewDue.textContent = String(dueCount);
    if (el.overviewTime) el.overviewTime.textContent = estimatedTimeLabel;
    if (el.overviewMastery) el.overviewMastery.textContent = masteryLabel;
    if (el.overviewAccuracy) el.overviewAccuracy.textContent = accuracyLabel;
    if (el.overviewStreak) el.overviewStreak.textContent = streak ? `${streak} days` : "0 days";
    if (el.heroMastery) el.heroMastery.textContent = masteryLabel;
    if (el.sessionLengthLabel) el.sessionLengthLabel.textContent = lengthLabel;
    if (el.modeLabel) el.modeLabel.textContent = getPracticeModeLabel();
    if (el.start) {
      el.start.textContent = dueCount ? `Start ${lengthLabel}` : "No Questions Available";
    }
    if (el.heroTitle) {
      el.heroTitle.textContent = state.currentEventName || "Continue Practice";
    }
    if (el.heroSubtitle) {
      const modeLabel = getPracticeModeLabel();
      const filterLabel = getQuestionFilterLabel();
      const summaryParts = [
        `${dueCount} questions`,
        modeLabel,
        filterLabel,
        estimatedTimeLabel,
      ].filter(Boolean);
      el.heroSubtitle.textContent = dueCount
        ? summaryParts.join(" | ")
        : "No due questions are loaded yet. Refresh data or choose another event in Settings.";
    }
    if (el.masteryRing) {
      el.masteryRing.style.setProperty("--ring-progress", Math.max(0, Math.min(100, Math.round(avgMastery || 0))));
    }
    renderRecentSessionCard();
    renderProgressTracking();
    renderQuestionHistory();
    renderSessionIntelligence();
  }

  function renderHomeFocus() {
    const weakKpis = (state.analytics?.weak_kpis || []).slice(0, 4);
    const summary = state.analytics?.summary || {};
    const recog = state.analytics?.question_type_breakdown?.recognition || null;
    const app = state.analytics?.question_type_breakdown?.application || null;
    const recogAcc = recog ? Number(recog.accuracy ?? 0) : null;
    const appAcc = app ? Number(app.accuracy ?? 0) : null;
    const modeLabel = getPracticeModeLabel();
    const filterLabel = getQuestionFilterLabel();
    const emptyText = state.currentEventId
      ? "No weak spots yet. Keep answering and the focus map will fill itself in."
      : "Choose an event in Settings to generate focus areas.";

    if (el.focusList) {
      el.focusList.innerHTML = "";
      if (!weakKpis.length) {
        if (el.focusEmpty) {
          el.focusEmpty.hidden = false;
          el.focusEmpty.textContent = emptyText;
        }
      } else {
        weakKpis.forEach((row) => {
          const score = Number(row.mastery_score ?? row.avg_mastery ?? 0);
          const bar = Math.max(8, 100 - score);
          const item = document.createElement("div");
          item.className = "focus-item";
          item.innerHTML = `
            <div class="focus-item-top">
              <span>${escHtml(row.kpi_code || "Focus KPI")}</span>
              <span>${Math.round(score)}%</span>
            </div>
            <div class="focus-item-bar">
              <div class="focus-item-fill" style="width: ${bar}%"></div>
            </div>
            <div class="focus-item-meta">${escHtml(row.kpi_text || row.cluster || "Weakest current area")}</div>
          `;
          el.focusList.appendChild(item);
        });
        if (el.focusEmpty) {
          el.focusEmpty.hidden = true;
          el.focusEmpty.textContent = "";
        }
      }
    }

    let focusMessage = `${modeLabel} · ${filterLabel} · Balanced practice`;
    if (weakKpis[0] && typeof weakKpis[0].kpi_code === "string") {
      focusMessage = `${modeLabel} · ${filterLabel} · Next focus: ${weakKpis[0].kpi_code}`;
    } else if (recogAcc !== null && appAcc !== null) {
      if (appAcc + 5 < recogAcc) {
        focusMessage = `${modeLabel} · ${filterLabel} · Focus: application scenarios`;
      } else if (recogAcc + 5 < appAcc) {
        focusMessage = `${modeLabel} · ${filterLabel} · Focus: recognition recall`;
      }
    } else if (summary.mastered_kpis) {
      focusMessage = `${modeLabel} · ${filterLabel} · ${summary.mastered_kpis} mastered KPI(s)`;
    }

    setFocus(focusMessage);
  }

  function renderProgressTracking() {
    const progress = state.analytics?.progress || {};
    const summary = state.analytics?.summary || {};
    const mastery = Number(progress.avg_mastery ?? summary.avg_mastery ?? 0);
    const answered = Number(progress.questions_answered ?? summary.total_questions_answered ?? 0);
    const correct = Number(progress.questions_correct ?? 0);
    const mastered = Number(progress.mastered_kpis ?? summary.mastered_kpis ?? 0);
    const due = Number(progress.questions_due ?? summary.questions_due ?? 0);
    const streak = Number(progress.streak_days ?? summary.streak_days ?? 0);
    const accuracy = Number(progress.accuracy_pct ?? (answered ? (correct / Math.max(answered, 1)) * 100 : 0));
    const recentResponse = Number(progress.avg_recent_response_ms ?? 0);

    if (el.trackingBadge) {
      el.trackingBadge.textContent = answered
        ? `${answered} answer${answered === 1 ? "" : "s"} tracked`
        : "Tracking";
    }
    if (el.trackingAccuracy) el.trackingAccuracy.textContent = `${Math.round(accuracy)}%`;
    if (el.trackingAnswered) el.trackingAnswered.textContent = String(answered);
    if (el.trackingCorrect) el.trackingCorrect.textContent = String(correct);
    if (el.trackingMastered) el.trackingMastered.textContent = String(mastered);
    if (el.trackingDue) el.trackingDue.textContent = String(due);
    if (el.trackingStreak) el.trackingStreak.textContent = streak ? `${streak} days` : "0 days";
    if (el.trackingMastery) el.trackingMastery.textContent = `${Math.round(mastery)}%`;
    if (el.trackingFill) el.trackingFill.style.width = `${Math.max(0, Math.min(100, mastery))}%`;
    if (el.trackingNote) {
      const avgLabel = recentResponse ? `${formatDurationSeconds(recentResponse)} recent average` : "No timed data yet";
      el.trackingNote.textContent = `You have answered ${answered} question${answered === 1 ? "" : "s"} with ${Math.round(accuracy)}% accuracy. ${avgLabel}.`;
    }
  }

  function renderQuestionHistory() {
    if (!el.historyList || !el.historyCount) return;

    const history = state.analytics?.question_history || [];
    el.historyCount.textContent = history.length
      ? `${history.length} entr${history.length === 1 ? "y" : "ies"}`
      : "0 entries";
    el.historyList.innerHTML = "";

    if (!history.length) {
      const empty = document.createElement("div");
      empty.className = "history-item";
      empty.innerHTML = `
        <div class="history-item-title">No history yet</div>
        <div class="history-item-copy">Your answered questions will appear here once you begin practicing.</div>
      `;
      el.historyList.appendChild(empty);
      return;
    }

    history.slice(0, 12).forEach((item) => {
      const row = document.createElement("div");
      row.className = `history-item ${item.correct ? "is-correct" : "is-missed"}`;
      const title = item.kpi_code || item.question_text || "Question";
      const answeredAt = item.answered_at ? new Date(item.answered_at).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }) : "Recently";
      row.innerHTML = `
        <div class="history-item-head">
          <div class="history-item-title">${escHtml(title)}</div>
          <div class="history-item-meta">${escHtml(item.question_type || "recognition")} · ${escHtml(answeredAt)}</div>
        </div>
        <div class="history-item-copy">
          <strong>${item.correct ? "Correct" : "Missed"}</strong> · ${escHtml(item.response_time_label || "--")} response · ${escHtml(item.time_to_first_label || "--")} first pick
        </div>
        <div class="history-item-copy">${escHtml(item.question_text || item.kpi_text || "Question text unavailable.")}</div>
      `;
      el.historyList.appendChild(row);
    });
  }

  function appendLiveQuestionHistory(question, correct, responseTimeMs) {
    if (!state.analytics) state.analytics = {};
    if (!Array.isArray(state.analytics.question_history)) {
      state.analytics.question_history = [];
    }
    if (!state.analytics.progress) {
      state.analytics.progress = {};
    }

    const entry = {
      question_id: question?.id || "",
      question_text: question?.text || "",
      kpi_code: question?.kpi_code || "",
      kpi_text: question?.kpi_text || "",
      question_type: question?.question_type || "recognition",
      correct: Boolean(correct),
      response_time_ms: Math.max(0, Math.round(responseTimeMs || 0)),
      response_time_label: formatDurationSeconds(responseTimeMs || 0),
      time_to_first_ms: state.firstSelectionAt
        ? Math.max(1, Math.round(state.firstSelectionAt - state.questionStartAt))
        : null,
      time_to_first_label: state.firstSelectionAt
        ? formatDurationSeconds(state.firstSelectionAt - state.questionStartAt)
        : "--",
      answer_change_count: state.answerChangeCount,
      instant_confidence: null,
      answered_at: new Date().toISOString(),
      session_id: state.sessionId || "",
      event_id: state.currentEventId || "",
    };

    state.analytics.question_history = [
      entry,
      ...state.analytics.question_history,
    ].slice(0, 50);

    const progress = state.analytics.progress;
    progress.questions_answered = state.stats.answered;
    progress.questions_correct = state.stats.correct;
    progress.accuracy_pct = state.stats.answered
      ? Math.round((state.stats.correct / state.stats.answered) * 1000) / 10
      : 0;
    progress.avg_recent_response_ms = state.stats.answered
      ? Math.round(state.stats.totalResponseMs / state.stats.answered)
      : 0;
    progress.history_count = state.analytics.question_history.length;
  }

  function getQuestionBenchmarkKey(question) {
    return question?.id || `${question?.kpi_code || ""}:${question?.question_type || "recognition"}`;
  }

  function benchmarkSummaryText(benchmark) {
    if (!benchmark) return "Benchmark data not captured for this item yet.";
    const accuracy = Number(benchmark.accuracy_pct ?? 0);
    const pace = Number(benchmark.pace_vs_baseline_pct ?? 0);
    const paceLabel = pace === 0
      ? "about on pace with baseline"
      : pace > 0
        ? `${Math.round(pace)}% slower than baseline`
        : `${Math.abs(Math.round(pace))}% faster than baseline`;
    return `Accuracy ${Math.round(accuracy)}%. ${paceLabel}.`;
  }

  function renderQuestionBenchmark(benchmark, question = state.currentQuestion) {
    state.currentBenchmark = benchmark || null;
    const qualityScore = question ? Number(mcqQuality(question)?.score ?? 0) : 0;

    if (el.benchmarkBadge) {
      el.benchmarkBadge.textContent = benchmark?.benchmark_label || "Benchmark --";
      el.benchmarkBadge.className = `quality-pill ${benchmark?.benchmark_class || ""}`.trim();
    }
    if (el.benchmarkCopy) {
      el.benchmarkCopy.textContent = benchmark?.summary || "Benchmark data will appear after the question is answered.";
    }
    if (el.benchmarkAccuracy) {
      el.benchmarkAccuracy.textContent = benchmark?.accuracy_pct === undefined || benchmark?.accuracy_pct === null
        ? "--"
        : `${Math.round(Number(benchmark.accuracy_pct))}%`;
    }
    if (el.benchmarkSpeed) {
      el.benchmarkSpeed.textContent = benchmark?.pace_vs_baseline_pct === undefined || benchmark?.pace_vs_baseline_pct === null
        ? "--"
        : formatSignedPct(benchmark.pace_vs_baseline_pct);
    }
    if (el.benchmarkAttempts) {
      el.benchmarkAttempts.textContent = benchmark?.attempts ? String(benchmark.attempts) : "--";
    }
    if (el.benchmarkQuality) {
      el.benchmarkQuality.textContent = qualityScore ? `${Math.round(qualityScore)}%` : "--";
    }
  }

  async function loadQuestionBenchmark(question = state.currentQuestion) {
    if (!question?.id) {
      renderQuestionBenchmark(null, question);
      return null;
    }
    const key = getQuestionBenchmarkKey(question);
    if (state.benchmarkCache.has(key)) {
      const cached = state.benchmarkCache.get(key);
      renderQuestionBenchmark(cached, question);
      return cached;
    }
    try {
      const res = await apiFetch(`/api/learn/question-benchmark?question_id=${encodeURIComponent(question.id)}`);
      if (!res.ok) throw new Error("Benchmark request failed");
      const data = await res.json().catch(() => ({}));
      const benchmark = data.benchmark || null;
      state.benchmarkCache.set(key, benchmark);
      renderQuestionBenchmark(benchmark, question);
      return benchmark;
    } catch (error) {
      renderQuestionBenchmark(null, question);
      return null;
    }
  }

  function toggleReportPanel(forceOpen = null) {
    if (!el.reportPanel) return;
    const shouldOpen = forceOpen === null ? el.reportPanel.classList.contains("is-hidden") : forceOpen;
    el.reportPanel.classList.toggle("is-hidden", !shouldOpen);
    if (shouldOpen && el.reportDetails) {
      window.setTimeout(() => el.reportDetails.focus(), 0);
    }
  }

  function resetReportPanel() {
    if (el.reportReason) el.reportReason.value = "ambiguous";
    if (el.reportDetails) el.reportDetails.value = "";
    if (el.reportStatus) el.reportStatus.textContent = "";
    if (el.reportPanel) el.reportPanel.classList.add("is-hidden");
  }

  async function submitQuestionReport() {
    const question = state.currentQuestion;
    if (!question?.id) return;
    if (el.reportSubmit) el.reportSubmit.disabled = true;
    if (el.reportStatus) el.reportStatus.textContent = "Submitting report...";

    try {
      const res = await apiFetch("/api/learn/question-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_id: question.id,
          reason: el.reportReason?.value || "ambiguous",
          details: (el.reportDetails?.value || "").trim(),
          benchmark: state.currentBenchmark || null,
        }),
      });
      if (!res.ok) throw new Error("Report request failed");
      if (el.reportStatus) el.reportStatus.textContent = "Report submitted. Thanks for flagging this item.";
      setStatus("Report submitted. Thanks for flagging this question.");
      resetReportPanel();
    } catch (error) {
      if (el.reportStatus) el.reportStatus.textContent = "We could not submit the report right now.";
    } finally {
      if (el.reportSubmit) el.reportSubmit.disabled = false;
    }
  }

  function buildViewerModel(source = state.currentQuestion) {
    const question = source && source.text ? source : state.currentQuestion;
    const reveal = question?.answer_reveal || questionQualityState(question || {})?.answer_reveal || {};
    const distractors = Array.isArray(reveal.distractors)
      ? reveal.distractors
      : Array.isArray(questionQualityState(question || {})?.distractor_quality)
        ? questionQualityState(question || {}).distractor_quality
        : [];
    const isReviewItem = Boolean(source && (source.correct_text || source.chosen_text || source.benchmark_summary));
    const locked = Boolean(state.answerLocked || isReviewItem || source?.correct_text || source?.chosen_text);
    return {
      question_id: source?.question_id || question?.id || "",
      kpi_code: source?.kpi_code || question?.kpi_code || "",
      kpi_text: source?.kpi_text || question?.kpi_text || "",
      cluster: source?.cluster || question?.cluster || "",
      question_type: source?.question_type || question?.question_type || "recognition",
      stem: source?.question_text || question?.text || "Question",
      explanation: locked
        ? (source?.explanation || question?.explanation || "No explanation was provided for this question yet.")
        : "Answer the question to unlock the explanation.",
      answerText: locked
        ? (source?.correct_text || reveal.correct_choice || (question?.choices || [])[Number(question?.correct ?? source?.correct_index ?? 0)] || "Unavailable")
        : "Answer reveal is available after you check your response.",
      chosenText: source?.chosen_text || (locked && source?.chosen_text ? source.chosen_text : ""),
      benchmarkSummary: source?.benchmark_summary || benchmarkSummaryText(state.currentBenchmark || getBenchmarkData(question || source)),
      distractors: locked ? distractors : [],
      locked,
    };
  }

  function renderQuestionViewer(source = state.currentQuestion) {
    const model = buildViewerModel(source);
    if (el.questionViewerType) {
      el.questionViewerType.textContent = model.question_type === "application" ? "Application Scenario" : "Recognition";
    }
    if (el.questionViewerKpi) {
      el.questionViewerKpi.textContent = model.kpi_code || "KPI unavailable";
    }
    if (el.questionViewerCluster) {
      el.questionViewerCluster.textContent = model.cluster || "No cluster";
    }
    if (el.questionViewerStem) {
      el.questionViewerStem.textContent = model.stem;
    }
    if (el.questionViewerExplanation) {
      el.questionViewerExplanation.textContent = model.explanation;
    }
    if (el.questionViewerAnswer) {
      const chosenLine = model.chosenText ? `You chose: ${model.chosenText}\n` : "";
      const benchmarkLine = model.benchmarkSummary ? `${model.benchmarkSummary}\n` : "";
      el.questionViewerAnswer.textContent = `${chosenLine}${benchmarkLine}${model.answerText}`;
    }
    if (el.questionViewerDistractors) {
      el.questionViewerDistractors.innerHTML = "";
      if (!model.locked) {
        const note = document.createElement("div");
        note.className = "question-viewer-distractor";
        note.innerHTML = `
          <div class="question-viewer-distractor-top">
            <strong>Locked</strong>
            <span class="question-viewer-distractor-score">Check answer first</span>
          </div>
          <div class="question-viewer-distractor-note">The explanation and distractor breakdown appear after you submit an answer.</div>
        `;
        el.questionViewerDistractors.appendChild(note);
      } else if (!model.distractors.length) {
        const note = document.createElement("div");
        note.className = "question-viewer-distractor";
        note.innerHTML = `
          <div class="question-viewer-distractor-top">
            <strong>No distractor data</strong>
            <span class="question-viewer-distractor-score">Unavailable</span>
          </div>
          <div class="question-viewer-distractor-note">This question was not captured with distractor metadata yet.</div>
        `;
        el.questionViewerDistractors.appendChild(note);
      } else {
        model.distractors.forEach((item, index) => {
          const row = document.createElement("div");
          row.className = "question-viewer-distractor";
          const score = Number(item.plausibility ?? item.score ?? 0);
          const title = item.choice || item.text || `Option ${index + 1}`;
          row.innerHTML = `
            <div class="question-viewer-distractor-top">
              <strong>${escHtml(title)}</strong>
              <span class="question-viewer-distractor-score">${Math.round(score)}% plausible</span>
            </div>
            <div class="question-viewer-distractor-note">${escHtml(item.why_it_isnt_right || "This distractor is weaker than the keyed answer.")}</div>
          `;
          el.questionViewerDistractors.appendChild(row);
        });
      }
    }
  }

  function openQuestionViewer(source = state.currentQuestion) {
    if (!el.questionViewer) return;
    renderQuestionViewer(source);
    el.questionViewer.classList.remove("is-hidden");
    el.questionViewer.setAttribute("aria-hidden", "false");
  }

  function closeQuestionViewer() {
    if (!el.questionViewer) return;
    el.questionViewer.classList.add("is-hidden");
    el.questionViewer.setAttribute("aria-hidden", "true");
  }

  function adaptiveNextQuestion() {
    if (!state.queue.length) return null;
    return state.queue[Math.min(state.cursor, state.queue.length - 1)] || state.queue[0] || null;
  }

  function renderSessionIntelligence() {
    const nextQuestion = state.currentQuestion || adaptiveNextQuestion();
    const nextType = nextQuestion ? (nextQuestion.question_type || "recognition") : "recognition";
    const queueRemaining = Math.max(0, state.queue.length - state.cursor);
    const split = state.stats.answered
      ? `${state.stats.recognitionCorrect}/${state.stats.recognitionAnswered || 0} recog · ${state.stats.applicationCorrect}/${state.stats.applicationAnswered || 0} app`
      : "No answers yet";

    if (el.intelChoice) {
      const quality = nextQuestion ? mcqQuality(nextQuestion) : null;
      const qualityLabel = quality ? `${mcqQualityLabel(quality.score)} · ${Math.round(quality.score)}%` : "No quality score yet";
      const typeLabel = nextType === "application" ? "Application" : "Recognition";
      el.intelChoice.textContent = `${typeLabel} next · ${qualityLabel}`;
    }

    if (el.intelSummary) {
      const modeLabel = getPracticeModeLabel();
      const timerLabel = state.timedMode
        ? `${Math.max(0, state.sessionRemainingSeconds)}s left`
        : "Untimed";
      el.intelSummary.textContent = `${modeLabel} · ${timerLabel}`;
    }

    if (el.intelState) {
      const timerLabel = state.timedMode
        ? `${Math.max(0, state.sessionRemainingSeconds)}s left`
        : "Untimed";
      el.intelState.textContent = `${queueRemaining} left · ${timerLabel}`;
    }

    if (el.intelSplit) {
      el.intelSplit.textContent = split;
    }

    if (el.intelNext) {
      if (state.reviewMode) {
        el.intelNext.textContent = "Review will capture each answer and explanation.";
      } else if (state.hadMisses) {
        el.intelNext.textContent = "Misses are being replayed for reinforcement.";
      } else {
        const weakKpi = (state.analytics?.weak_kpis || [])[0];
        el.intelNext.textContent = weakKpi
          ? `Focus next: ${weakKpi.kpi_code}`
          : "Balanced practice with adaptive reordering.";
      }
    }
  }

  async function hydratePrefs() {
    try {
      const meRes = await apiFetch("/auth/me");
      const meData = await meRes.json().catch(() => ({}));
      UserPrefs.hydrateFromProfile(meData.user || meData);
    } catch (error) {
      // Cache remains the fallback.
    }
  }

  async function loadQuestionsForKpis(kpiCodes) {
    const codes = Array.from(new Set(kpiCodes.filter(Boolean)));
    if (!codes.length) return [];

    const responses = await Promise.all(
      codes.map(async (code) => {
        try {
          const res = await apiFetch(
            `/api/learn/questions?kpi_code=${encodeURIComponent(code)}&event_id=${encodeURIComponent(UserPrefs.getEventId())}`,
          );
          if (!res.ok) return [];
          const data = await res.json();
          return Array.isArray(data.questions) ? data.questions : [];
        } catch (error) {
          return [];
        }
      }),
    );

    const byId = new Map();
    responses.flat().forEach((question) => {
      if (question && question.id) byId.set(question.id, question);
    });
    return Array.from(byId.values());
  }

  function collectSupportKpiCodes(limit = 6) {
    const codes = [];
    const pushCode = (code) => {
      const value = String(code || "").trim();
      if (!value || codes.includes(value)) return;
      codes.push(value);
    };

    (state.analytics?.weak_kpis || []).slice(0, 4).forEach((row) => pushCode(row.kpi_code));
    if (state.practiceMode === "mixed" || state.practiceMode === "random") {
      (state.analytics?.strong_kpis || []).slice(0, 2).forEach((row) => pushCode(row.kpi_code));
    }
    if (!codes.length && Array.isArray(state.analytics?.kpi_mastery)) {
      state.analytics.kpi_mastery
        .slice()
        .sort((a, b) => Number(a.mastery_score ?? 0) - Number(b.mastery_score ?? 0))
        .slice(0, 6)
        .forEach((row) => pushCode(row.kpi_code));
    }

    return codes.slice(0, limit);
  }

  function buildSessionQueue(sourceQuestions) {
    const combined = buildPracticeQueue(sourceQuestions);
    if (!combined.length) return [];
    return combined;
  }

  async function loadPracticeBank() {
    syncFilterControls();
    setStatus(
      `Loading your event and practice bank in ${getPracticeModeLabel()} mode with ${getQuestionFilterLabel().toLowerCase()} filter...`,
    );

    const eventId = UserPrefs.getEventId();
    const eventName = UserPrefs.getEventName();
    const eventCluster = UserPrefs.getCluster();
    state.currentEventId = eventId || "";
    state.currentEventName = eventName || "";
    state.currentEventCluster = eventCluster || "";

    if (el.eventName) el.eventName.textContent = eventName || "No event selected";
    if (el.eventCluster) el.eventCluster.textContent = eventCluster || "Choose one in Settings";

    if (!eventId) {
      state.analytics = null;
      state.allQuestions = [];
      state.queue = [];
      renderHomeStats();
      renderHomeFocus();
      setStatus("No event is selected yet. Open Settings to choose one first.");
      if (el.start) el.start.disabled = true;
      return;
    }

    const analyticsUrl = `/api/learn/analytics?event_id=${encodeURIComponent(eventId)}`;
    const dueUrl = `/api/learn/due?event_id=${encodeURIComponent(eventId)}&limit=120`;

    let analytics = null;
    let dueQuestions = [];

    try {
      const [analyticsRes, dueRes] = await Promise.all([
        apiFetch(analyticsUrl),
        apiFetch(dueUrl),
      ]);

      if (analyticsRes.ok) {
        analytics = await analyticsRes.json();
      }

      if (dueRes.ok) {
        const dueData = await dueRes.json();
        dueQuestions = Array.isArray(dueData.questions) ? dueData.questions : [];
      }
    } catch (error) {
      setStatus(`Could not load practice data: ${error.message}`);
      if (el.start) el.start.disabled = true;
      return;
    }

    state.analytics = analytics || null;

    let supportQuestions = [];
    const supportCodes = collectSupportKpiCodes(state.practiceMode === "adaptive" ? 4 : 6);
    if (supportCodes.length) {
      supportQuestions = await loadQuestionsForKpis(supportCodes);
    }

    if (!dueQuestions.length && !supportQuestions.length) {
      try {
        const res = await apiFetch(`/api/kpis?event_id=${encodeURIComponent(eventId)}`);
        if (res.ok) {
          const data = await res.json();
          const codes = Array.isArray(data.kpis)
            ? data.kpis.slice(0, 3).map((kpi) => kpi.code).filter(Boolean)
            : [];
          supportQuestions = await loadQuestionsForKpis(codes);
        }
      } catch (error) {
        // Ignore fallback failure.
      }
    }

    const sourceQuestions = dedupeQuestions([...dueQuestions, ...supportQuestions]);
    state.allQuestions = buildSessionQueue(sourceQuestions);
    state.queue = state.allQuestions.slice();
    renderHomeStats();
    renderHomeFocus();

    if (el.start) el.start.disabled = !state.allQuestions.length;
    if (state.allQuestions.length) {
      setStatus(
        `Loaded ${state.allQuestions.length} practice questions. ${getPracticeModeLabel()} mode is ready with a ${getQuestionFilterLabel().toLowerCase()} filter.`,
      );
    } else {
      setStatus("No practice questions are available for this event yet.");
    }
  }

  async function startServerSession() {
    if (!state.currentEventId) return;
    try {
      const res = await apiFetch("/api/learn/session/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_id: state.currentEventId,
          session_type: `practice_questions_${state.practiceMode}_${state.timedMode ? "timed" : "untimed"}_${state.reviewMode ? "review" : "standard"}`,
        }),
      });
      const data = await res.json().catch(() => ({}));
      state.sessionId = data.session_id || null;
    } catch (error) {
      state.sessionId = null;
    }
  }

  function resetSessionState() {
    clearSessionTimer();
    state.cursor = 0;
    state.currentQuestion = null;
    state.selectedChoice = null;
    state.answerLocked = false;
    state.questionStartAt = 0;
    state.firstSelectionAt = null;
    state.answerChangeCount = 0;
    state.retryRound = 0;
    state.missed = [];
    state.hadMisses = false;
    state.sessionId = null;
    state.sessionStartAt = Date.now();
    state.sessionDurationLimitSeconds = 0;
    state.sessionRemainingSeconds = 0;
    state.reviewEntries = [];
    state.engineBias = {
      recognitionBoost: 0,
      applicationBoost: 0,
      applicationPenalty: 0,
      recognitionPenalty: 0,
    };
    state.stats = {
      answered: 0,
      correct: 0,
      recognitionAnswered: 0,
      recognitionCorrect: 0,
      applicationAnswered: 0,
      applicationCorrect: 0,
      totalResponseMs: 0,
    };
  }

  function showSessionQuestion(question) {
    state.currentQuestion = question;
    question._attemptId = (window.crypto && typeof window.crypto.randomUUID === "function")
      ? window.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    state.selectedChoice = null;
    state.answerLocked = false;
    state.questionStartAt = Date.now();
    state.firstSelectionAt = null;
    state.answerChangeCount = 0;

    if (el.progressCurrent) el.progressCurrent.textContent = String(state.cursor + 1);
    if (el.progressTotal) el.progressTotal.textContent = String(state.queue.length);
    if (el.progressFill) {
      const pct = state.queue.length
        ? ((state.cursor) / Math.max(state.queue.length - 1, 1)) * 100
        : 0;
      el.progressFill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    }

    if (el.questionType) {
      el.questionType.textContent = question.question_type === "application"
        ? "Application Scenario"
        : "Recognition";
    }

    if (el.questionStem) el.questionStem.textContent = question.text || "";
    if (el.choiceList) {
      el.choiceList.innerHTML = "";
      const letters = ["A", "B", "C", "D"];
      (question.choices || []).forEach((choice, index) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "choice-btn";
        btn.innerHTML = `<span class="choice-letter">${letters[index] || index + 1}.</span><span class="choice-text">${escHtml(choice)}</span>`;
        btn.addEventListener("click", () => handleChoicePick(index));
        el.choiceList.appendChild(btn);
      });
    }

    if (el.feedback) el.feedback.hidden = true;
    if (el.feedbackAnswer) el.feedbackAnswer.textContent = "";
    if (el.feedbackDistractors) el.feedbackDistractors.innerHTML = "";
    if (el.qualityBadge) {
      el.qualityBadge.textContent = "Quality --";
      el.qualityBadge.className = "quality-pill";
    }
    renderSessionTimer();
    if (el.checkBtn) {
      el.checkBtn.disabled = true;
      el.checkBtn.textContent = "Check Answer";
    }
    if (el.nextBtn) el.nextBtn.hidden = true;
    if (el.viewQuestionBtn) {
      el.viewQuestionBtn.disabled = !question;
    }
    state.currentBenchmark = null;
    renderQuestionBenchmark(null, question);
    resetReportPanel();
    renderSessionIntelligence();
    loadQuestionBenchmark(question);
  }

  function renderQuestion() {
    if (!state.queue.length) {
      finishSession();
      return;
    }

    if (state.cursor >= state.queue.length) {
      if (state.missed.length && state.retryRound < 1) {
        state.retryRound += 1;
        state.queue = buildPracticeQueue(state.missed, { allowDailyLimit: false });
        state.missed = [];
        state.cursor = 0;
        setStatus(`Retry loop active. We are replaying the ${state.queue.length} questions you missed.`);
        showSessionQuestion(state.queue[state.cursor]);
        return;
      }

      finishSession();
      return;
    }

    showSessionQuestion(state.queue[state.cursor]);
    renderSessionIntelligence();
  }

  function handleChoicePick(index) {
    if (state.answerLocked) return;

    if (state.selectedChoice !== null && state.selectedChoice !== index) {
      state.answerChangeCount += 1;
    }

    state.selectedChoice = index;
    if (state.firstSelectionAt === null) {
      state.firstSelectionAt = Date.now();
    }

    const buttons = Array.from(el.choiceList?.querySelectorAll(".choice-btn") || []);
    buttons.forEach((button, btnIndex) => {
      button.classList.toggle("selected", btnIndex === index);
    });

    if (el.checkBtn) el.checkBtn.disabled = false;
  }

  function lockQuestion(correctIndex, chosenIndex) {
    const buttons = Array.from(el.choiceList?.querySelectorAll(".choice-btn") || []);
    buttons.forEach((button, btnIndex) => {
      button.disabled = true;
      button.classList.remove("selected");
      if (btnIndex === correctIndex) button.classList.add("correct");
      if (btnIndex === chosenIndex && chosenIndex !== correctIndex) button.classList.add("wrong");
    });
  }

  function updateStats(question, correct, responseTimeMs) {
    state.stats.answered += 1;
    state.stats.totalResponseMs += responseTimeMs;
    if (correct) state.stats.correct += 1;

    if ((question.question_type || "recognition") === "application") {
      state.stats.applicationAnswered += 1;
      if (correct) state.stats.applicationCorrect += 1;
    } else {
      state.stats.recognitionAnswered += 1;
      if (correct) state.stats.recognitionCorrect += 1;
    }
    renderSessionIntelligence();
  }

  function renderFeedback(question, correct, chosenIndex) {
    const choiceText = (question.choices || [])[chosenIndex] || "your answer";
    const correctText = (question.choices || [])[question.correct] || "the correct answer";
    const quality = mcqQuality(question);
    const qualityScore = quality && typeof quality.score === "number" ? quality.score : null;
    const reveal = question.answer_reveal || questionQualityState(question).answer_reveal || {};
    const distractors = (reveal.distractors || questionQualityState(question).distractor_quality || [])
      .filter((item) => item && (item.role ? item.role === "distractor" : true));

    if (el.feedback) {
      el.feedback.hidden = false;
      el.feedbackKicker.textContent = correct ? "Correct" : "Not quite";
      el.feedbackCopy.textContent = correct
        ? `You chose ${choiceText}.`
        : `You chose ${choiceText}. The correct answer is ${correctText}.`;
      el.feedbackExplanation.textContent = question.explanation || "No explanation was provided for this question yet.";
      if (el.feedbackAnswer) {
        el.feedbackAnswer.textContent = `Correct answer: ${reveal.correct_choice || correctText}`;
      }
      if (el.qualityBadge && qualityScore !== null) {
        const qualityClass = mcqQualityClass(qualityScore);
        el.qualityBadge.className = `quality-pill ${qualityClass}`.trim();
        el.qualityBadge.textContent = `${mcqQualityLabel(qualityScore)} MCQ · ${Math.round(qualityScore)}%`;
      } else if (el.qualityBadge) {
        el.qualityBadge.className = "quality-pill";
        el.qualityBadge.textContent = "Quality --";
      }
      if (el.feedbackDistractors) {
        el.feedbackDistractors.innerHTML = "";
        if (!distractors.length) {
          const empty = document.createElement("div");
          empty.className = "feedback-distractor-note";
          empty.textContent = "No distractor metadata is available yet.";
          el.feedbackDistractors.appendChild(empty);
        } else {
          distractors.forEach((item, index) => {
            const row = document.createElement("div");
            row.className = "feedback-distractor-row";
            const score = Number(item.plausibility ?? item.score ?? 0);
            const choice = item.choice || (question.choices || [])[item.index] || `Option ${index + 1}`;
            row.innerHTML =
              `<div class="feedback-distractor-top"><span>${escHtml(choice)}</span>` +
              `<span class="feedback-distractor-score">${Math.round(score)}% plausible</span></div>` +
              `<div class="feedback-distractor-note">${escHtml(item.why_it_isnt_right || "This distractor is weaker than the keyed answer.")}</div>`;
            el.feedbackDistractors.appendChild(row);
          });
        }
      }
    }
  }

  function recordReviewEntry(question, correct, chosenIndex, responseTimeMs) {
    if (!state.reviewMode) return;
    state.reviewEntries.push({
      question_id: question.id || "",
      kpi_code: question.kpi_code || "",
      question_text: question.text || "",
      question_type: question.question_type || "recognition",
      chosen_index: chosenIndex,
      chosen_text: (question.choices || [])[chosenIndex] || "",
      correct_index: Number(question.correct ?? 0),
      correct_text: (question.choices || [])[Number(question.correct ?? 0)] || "",
      correct,
      response_time_ms: Math.max(1, Math.round(responseTimeMs)),
      explanation: question.explanation || "",
      benchmark_summary: benchmarkSummaryText(state.currentBenchmark || getBenchmarkData(question)),
    });
  }

  async function submitAnswer(question, selectedIndex, responseTimeMs) {
    if (!question.id) return false;

    try {
      const res = await apiFetch("/api/learn/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question_id: question.id,
          attempt_id: question._attemptId,
          kpi_code: question.kpi_code || "",
          question_type: question.question_type || "recognition",
          selected_index: selectedIndex,
          response_time_ms: Math.max(1, Math.round(responseTimeMs)),
          time_to_first_ms: state.firstSelectionAt
            ? Math.max(1, Math.round(state.firstSelectionAt - state.questionStartAt))
            : null,
          answer_change_count: state.answerChangeCount,
          session_id: state.sessionId || "",
          cluster: question.cluster || "",
          deca_cluster: question.deca_cluster || "",
          event_id: question.event_id || state.currentEventId || "",
        }),
      });
      if (!res.ok) return false;
      const data = await res.json().catch(() => ({}));
      applyEngineHints(data.queue_actions || []);
      return true;
    } catch (error) {
      return false;
    }
  }

  async function handleCheckAnswer() {
    if (state.answerLocked || state.selectedChoice === null || !state.currentQuestion) return;

    state.answerLocked = true;
    if (el.checkBtn) {
      el.checkBtn.disabled = true;
      el.checkBtn.textContent = "Answered";
    }

    const question = state.currentQuestion;
    const chosenIndex = state.selectedChoice;
    const correct = chosenIndex === Number(question.correct ?? 0);
    const responseTimeMs = Date.now() - state.questionStartAt;

    lockQuestion(Number(question.correct ?? 0), chosenIndex);
    updateStats(question, correct, responseTimeMs);
    if (!correct) {
      state.missed.push(question);
      state.hadMisses = true;
    }
    recordReviewEntry(question, correct, chosenIndex, responseTimeMs);
    appendLiveQuestionHistory(question, correct, responseTimeMs);
    renderFeedback(question, correct, chosenIndex);
    const persisted = await submitAnswer(question, chosenIndex, responseTimeMs);
    if (!persisted) {
      window.alert("Your answer could not be saved. Check your connection, then reload and try again before continuing.");
      return;
    }
    state.benchmarkCache.delete(getQuestionBenchmarkKey(question));
    const benchmark = await loadQuestionBenchmark(question);
    if (state.reviewEntries.length) {
      state.reviewEntries[state.reviewEntries.length - 1].benchmark_summary = benchmarkSummaryText(
        benchmark || getBenchmarkData(question),
      );
    }
    renderProgressTracking();
    renderQuestionHistory();
    renderSessionIntelligence();

    if (el.nextBtn) {
      el.nextBtn.hidden = false;
      el.nextBtn.textContent = state.cursor + 1 >= state.queue.length ? "Finish Session" : "Next Question";
    }
  }

  function advanceQuestion() {
    if (!state.answerLocked) return;
    state.cursor += 1;
    if (el.progressFill) {
      const pct = state.queue.length
        ? (state.cursor / Math.max(state.queue.length, 1)) * 100
        : 0;
      el.progressFill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    }

    if (state.cursor >= state.queue.length) {
      if (state.missed.length && state.retryRound < 1) {
        state.retryRound += 1;
        state.queue = buildPracticeQueue(state.missed, { allowDailyLimit: false });
        state.missed = [];
        state.cursor = 0;
        setStatus(`Missed-question replay engaged. You have ${state.queue.length} question(s) to try again.`);
        renderSessionIntelligence();
      }
    }

    if (state.cursor >= state.queue.length && !state.missed.length) {
      clearSessionTimer();
      finishSession();
      return;
    }

    renderQuestion();
  }

  async function finalizeServerSession() {
    const durationSeconds = state.sessionStartAt
      ? Math.round((Date.now() - state.sessionStartAt) / 1000)
      : 0;

    if (!state.sessionId) return;

    const response = await apiFetch("/api/learn/session/end", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: state.sessionId,
          kpis_studied: uniqueKpis(state.allQuestions).length,
          questions_answered: state.stats.answered,
          questions_correct: state.stats.correct,
          vocab_total: 0,
          vocab_correct: 0,
          duration_seconds: durationSeconds,
          ar_answers: state.reviewMode ? state.reviewEntries : [],
        }),
      });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.error || "Session persistence failed");
    }
    return response.json();
  }

  function buildSummaryNote() {
    const recogAcc = state.stats.recognitionAnswered
      ? Math.round((state.stats.recognitionCorrect / state.stats.recognitionAnswered) * 100)
      : null;
    const appAcc = state.stats.applicationAnswered
      ? Math.round((state.stats.applicationCorrect / state.stats.applicationAnswered) * 100)
      : null;

    if (recogAcc !== null && appAcc !== null) {
      if (appAcc + 5 < recogAcc) {
        return "Application is trailing recognition, so the engine prioritized scenario questions and replayed misses once.";
      }
      if (recogAcc + 5 < appAcc) {
        return "Recognition is lagging behind application, so the session will keep pulling recall items earlier next time.";
      }
    }

    if (state.hadMisses) {
      return "The learning feedback loop replayed missed items before ending, so you get a clean second look.";
    }

    if (state.reviewMode) {
      return "Review mode captured each question so the learning feedback loop can show your choice, the keyed answer, and the explanation.";
    }

    return "Solid run. The practice set finished cleanly with a feedback loop and updated session metrics.";
  }

  function renderReviewSummary() {
    if (!el.reviewPanel || !el.reviewList || !el.reviewCount) return;

    el.reviewPanel.style.display = state.reviewMode ? "" : "none";
    el.reviewList.innerHTML = "";
    el.reviewCount.textContent = state.reviewMode
      ? `${state.reviewEntries.length} reviewed`
      : "Review off";

    if (!state.reviewMode) return;

    if (!state.reviewEntries.length) {
      const empty = document.createElement("div");
      empty.className = "review-item";
      empty.innerHTML = `
        <div class="review-item-title">No review items captured</div>
        <div class="review-item-explanation">This session finished without recorded review entries.</div>
      `;
      el.reviewList.appendChild(empty);
      return;
    }

    state.reviewEntries.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "review-item";
      row.innerHTML = `
        <div class="review-item-head">
          <div class="review-item-title">${escHtml(item.kpi_code || `Question ${index + 1}`)}</div>
          <div class="review-item-meta">${escHtml(item.question_type || "recognition")} · ${item.correct ? "Correct" : "Missed"} · ${Math.round(item.response_time_ms / 1000)}s</div>
        </div>
        <div class="review-item-answer">You chose: ${escHtml(item.chosen_text || "No answer")}</div>
        <div class="review-item-answer">Correct answer: ${escHtml(item.correct_text || "Unavailable")}</div>
        <div class="review-item-explanation">${escHtml(item.explanation || "No explanation was provided.")}</div>
        <div class="review-item-explanation">${escHtml(item.benchmark_summary || "Benchmark data not captured for this item yet.")}</div>
      `;
      el.reviewList.appendChild(row);
    });
  }

  function renderSummary() {
    const durationSeconds = state.sessionStartAt
      ? Math.round((Date.now() - state.sessionStartAt) / 1000)
      : 0;
    const avgResponse = state.stats.answered
      ? state.stats.totalResponseMs / state.stats.answered
      : 0;
    const accuracy = state.stats.answered
      ? Math.round((state.stats.correct / state.stats.answered) * 100)
      : 0;
    const recogAcc = state.stats.recognitionAnswered
      ? Math.round((state.stats.recognitionCorrect / state.stats.recognitionAnswered) * 100)
      : 0;
    const appAcc = state.stats.applicationAnswered
      ? Math.round((state.stats.applicationCorrect / state.stats.applicationAnswered) * 100)
      : 0;

    if (el.summaryAccuracy) el.summaryAccuracy.textContent = `${accuracy}%`;
    if (el.summaryCorrect) el.summaryCorrect.textContent = `${state.stats.correct} / ${state.stats.answered}`;
    if (el.summaryAverage) el.summaryAverage.textContent = formatSeconds(avgResponse);
    if (el.summaryAnswered) el.summaryAnswered.textContent = String(state.stats.answered);
    if (el.summaryRecognition) el.summaryRecognition.textContent = `${recogAcc}%`;
    if (el.summaryRecognitionDetail) {
      el.summaryRecognitionDetail.textContent =
        `${state.stats.recognitionCorrect}/${state.stats.recognitionAnswered} correct`;
    }
    if (el.summaryApplication) el.summaryApplication.textContent = `${appAcc}%`;
    if (el.summaryApplicationDetail) {
      el.summaryApplicationDetail.textContent =
        `${state.stats.applicationCorrect}/${state.stats.applicationAnswered} correct`;
    }
    if (el.summaryRetries) el.summaryRetries.textContent = String(state.retryRound);
    if (el.summaryNote) el.summaryNote.textContent = buildSummaryNote();
    renderReviewSummary();

    const uniqueCount = uniqueKpis(state.allQuestions).length;
    if (el.sessionTitle) el.sessionTitle.textContent = `${uniqueCount} KPI practice questions`;
    if (el.progressCurrent) el.progressCurrent.textContent = String(Math.min(state.queue.length, state.cursor));
    if (el.progressTotal) el.progressTotal.textContent = String(state.queue.length);
    if (el.progressFill) el.progressFill.style.width = "100%";
    renderSessionTimer();

    setStatus(`Session finished in ${Math.max(1, durationSeconds)} second(s).`);
  }

  async function finishSession() {
    if (state._finishing) return;
    state._finishing = true;
    try {
      clearSessionTimer();
      const savedSession = await finalizeServerSession();
      if (savedSession) {
        state.stats.answered = Number(savedSession.questions_answered ?? state.stats.answered);
        state.stats.correct = Number(savedSession.questions_correct ?? state.stats.correct);
      }
      renderSummary();
      showView(el.summary);
    } catch (error) {
      setStatus("Your session could not be saved. Check your connection and retry before leaving.");
      window.alert("Your session could not be saved. Check your connection and retry before leaving.");
    } finally {
      state._finishing = false;
    }
  }

  async function beginSession() {
    if (!state.allQuestions.length) {
      setStatus("There are no practice questions to start yet.");
      return;
    }

    resetSessionState();
    const builtQueue = buildPracticeQueue(state.allQuestions);
    state.queue = builtQueue.slice(0, getSessionLengthLimit(builtQueue.length));
    showView(el.session);
    setSessionTitle(`${state.currentEventName || "Current event"} · ${getPracticeModeLabel()} practice`);
    if (el.progressTotal) el.progressTotal.textContent = String(state.queue.length);
    setStatus(
      `${state.reviewMode ? "Review mode on. " : ""}${state.timedMode ? "Timed session started. " : "Untimed session started. "}Practice started with ${state.queue.length} question(s).`,
    );
    await startServerSession();
    if (!state.sessionId) {
      setStatus("The study session could not be saved. Check your connection and try again.");
      showView(el.home);
      return;
    }
    startSessionTimer();
    renderSessionIntelligence();
    renderQuestion();
  }

  async function initPractice() {
    state.practiceMode = normalizeMode(readStoredValue(MODE_STORAGE_KEY, state.practiceMode));
    state.questionFilter = normalizeChoiceFilter(readStoredValue(FILTER_STORAGE_KEY, state.questionFilter));
    state.sessionLength = normalizeSessionLength(readStoredValue(SESSION_LENGTH_STORAGE_KEY, state.sessionLength));
    state.timedMode = normalizeBoolean(readStoredValue(TIMED_MODE_STORAGE_KEY, state.timedMode ? "true" : "false"), false);
    state.reviewMode = normalizeBoolean(readStoredValue(REVIEW_MODE_STORAGE_KEY, state.reviewMode ? "true" : "false"), true);
    syncFilterControls();
    updateSessionSettingsUI();

    await hydratePrefs();

    if (el.sessionLengthSelect) {
      el.sessionLengthSelect.addEventListener("change", () => {
        setSessionLength(el.sessionLengthSelect.value);
      });
    }
    if (el.timedButtons.length) {
      el.timedButtons.forEach((button) => {
        button.addEventListener("click", () => {
          setTimedMode(normalizeBoolean(button.dataset.sessionTimed, false));
        });
      });
    }
    if (el.reviewToggle) {
      el.reviewToggle.addEventListener("click", () => {
        setReviewMode(!state.reviewMode);
      });
    }
    if (el.reportToggle) {
      el.reportToggle.addEventListener("click", () => {
        toggleReportPanel();
      });
    }
    if (el.reportCancel) {
      el.reportCancel.addEventListener("click", () => {
        resetReportPanel();
      });
    }
    if (el.reportSubmit) {
      el.reportSubmit.addEventListener("click", submitQuestionReport);
    }

    if (el.modeButtons.length) {
      el.modeButtons.forEach((button) => {
        button.addEventListener("click", () => {
          setPracticeMode(button.dataset.practiceMode || "adaptive");
          loadPracticeBank();
        });
      });
    }
    if (el.filterButtons.length) {
      el.filterButtons.forEach((button) => {
        button.addEventListener("click", () => {
          setQuestionFilter(button.dataset.questionFilter || "all");
          loadPracticeBank();
        });
      });
    }

    if (el.start) {
      el.start.addEventListener("click", beginSession);
    }
    if (el.refresh) {
      el.refresh.addEventListener("click", loadPracticeBank);
    }
    if (el.exitBtn) {
      el.exitBtn.addEventListener("click", async () => {
        await finishSession();
      });
    }
    if (el.checkBtn) {
      el.checkBtn.addEventListener("click", handleCheckAnswer);
    }
    if (el.nextBtn) {
      el.nextBtn.addEventListener("click", advanceQuestion);
    }
    if (el.viewQuestionBtn) {
      el.viewQuestionBtn.addEventListener("click", () => {
        openQuestionViewer(state.currentQuestion);
      });
    }
    if (el.questionViewerClose) {
      el.questionViewerClose.addEventListener("click", closeQuestionViewer);
    }
    if (el.questionViewer) {
      el.questionViewer.addEventListener("click", (event) => {
        if (event.target === el.questionViewer) {
          closeQuestionViewer();
        }
      });
    }
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeQuestionViewer();
      }
    });
    if (el.summaryRetake) {
      el.summaryRetake.addEventListener("click", beginSession);
    }
    if (el.summaryHome) {
      el.summaryHome.addEventListener("click", () => {
        showView(el.home);
        loadPracticeBank();
      });
    }

    await loadPracticeBank();
  }

  renderReviewSummary = function renderReviewSummaryOverride() {
    if (!el.reviewPanel || !el.reviewList || !el.reviewCount) return;

    el.reviewPanel.style.display = state.reviewMode ? "" : "none";
    el.reviewList.innerHTML = "";
    el.reviewCount.textContent = state.reviewMode
      ? `${state.reviewEntries.length} reviewed`
      : "Review off";

    if (!state.reviewMode) return;

    if (!state.reviewEntries.length) {
      const empty = document.createElement("div");
      empty.className = "review-item";
      empty.innerHTML = `
        <div class="review-item-title">No review items captured</div>
        <div class="review-item-explanation">This session finished without recorded review entries.</div>
      `;
      el.reviewList.appendChild(empty);
      return;
    }

    state.reviewEntries.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "review-item";
      row.style.cursor = "pointer";
      row.innerHTML = `
        <div class="review-item-head">
          <div class="review-item-head-copy">
            <div class="review-item-title">${escHtml(item.kpi_code || `Question ${index + 1}`)}</div>
            <div class="review-item-meta">${escHtml(item.question_type || "recognition")} | ${item.correct ? "Correct" : "Missed"} | ${Math.round(item.response_time_ms / 1000)}s</div>
          </div>
          <button class="ghost-btn review-view-btn" type="button">Open Viewer</button>
        </div>
        <div class="review-item-answer">You chose: ${escHtml(item.chosen_text || "No answer")}</div>
        <div class="review-item-answer">Correct answer: ${escHtml(item.correct_text || "Unavailable")}</div>
        <div class="review-item-explanation">${escHtml(item.explanation || "No explanation was provided.")}</div>
        <div class="review-item-explanation">${escHtml(item.benchmark_summary || "Benchmark data not captured for this item yet.")}</div>
      `;
      row.addEventListener("click", (event) => {
        if (event.target instanceof HTMLElement && event.target.closest(".review-view-btn")) return;
        openQuestionViewer(item);
      });
      row.querySelector(".review-view-btn")?.addEventListener("click", (event) => {
        event.stopPropagation();
        openQuestionViewer(item);
      });
      el.reviewList.appendChild(row);
    });
  };

  requireAuth().then((user) => {
    if (!user) return;
    initTopbar(user);
    initPractice();
  });
})();
