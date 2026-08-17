            // ─── Constants ────────────────────────────────────────────────────────────────
            const QUESTIONS_PER_KPI = 3;
            const LESSON_VERSION = 4;
            const ROLEPLAY_EVERY = 7; // show a mini roleplay every N KPIs (standard/tdm only)

            // ─── State ────────────────────────────────────────────────────────────────────
            let allKpis = []; // all KPIs for the user's event (in order)
            let curriculumKpis = []; // full event curriculum, including lessons still being prepared
            let curriculumExpanded = false;
            let sessionQueue = []; // KPIs for this session (same as allKpis initially)
            let sessionIdx = 0; // current position in sessionQueue
            let completedKpiCodes = new Set();
            let kpiLoadToken = 0;
            let kpiQuestionStart = 0;
            let kpiCorrectStart = 0;
            let lastKpiMastery = null;
            let kpiFirstPassAnswered = 0;
            let kpiFirstPassCorrect = 0;
            let sessionData = null; // current KPI's Groq response {vocab,concept,questions}
            let vocabList = [];
            let vocabIdx = 0;
            let qShown = []; // questions chosen for this KPI
            let missed = []; // questions answered wrong this round
            let qIdx = 0; // which question we're on
            let qAnswered = false;
            let chunkKpis = []; // KPIs studied in the current chunk of ROLEPLAY_EVERY

            // Session tracking
            let currentEventId = "";
            let currentEventName = "";
            let currentEventType = "series"; // 'exam'|'tdm'|'series'|'principles'|'operations'
            let currentEvent = null;
            let currentLearnMode = "standard"; // 'standard'|'examOnly'|'principles'
            let sessionId = null;
            let sessionStartTime = null;
            let sessionQAnswered = 0;
            let sessionQCorrect = 0;
            let sessionRecogAnswered = 0; // recognition questions answered
            let sessionRecogCorrect = 0;
            let sessionAppAnswered = 0;   // application questions answered
            let sessionAppCorrect = 0;
            let sessionVocabTotal = 0;
            let sessionVocabCorrect = 0;
            let sessionRoleplayScore = null;
            let sessionArAnswers = [];
            let preMasteryMap = {};
            let analyticsData = null;
            let isReviewMode = false;
            let kpiGroups = { unstarted: [], due: [], in_progress: [], mastered: [] };

            // ─── Per-question timing state (reset in showQuestion) ────────────────────────
            let _qStartTime         = 0;   // ms timestamp when question was rendered
            let _qFirstClickTime    = null; // ms timestamp of first answer click
            let _qAnswerChangeCount = 0;   // number of times the chosen answer changed
            let _qLastChoice        = null; // index of most-recently clicked choice

            // ─── DOM helpers ──────────────────────────────────────────────────────────────
            const $ = (id) => document.getElementById(id);
            const viewHome = $("view-home");
            const viewSession = $("view-session");

            function showLearnTab(name, options = {}) {
                const selected = ["today", "curriculum", "progress"].includes(name) ? name : "today";
                document.querySelectorAll("[data-learn-tab]").forEach((button) => {
                    const active = button.dataset.learnTab === selected;
                    button.classList.toggle("active", active);
                    button.setAttribute("aria-selected", String(active));
                });
                document.querySelectorAll("[data-learn-panel]").forEach((panel) => {
                    panel.hidden = panel.dataset.learnPanel !== selected;
                });
                if (options.remember !== false) sessionStorage.setItem("ct_learn_active_tab", selected);
            }

            document.querySelectorAll("[data-learn-tab]").forEach((button) => {
                button.addEventListener("click", () => showLearnTab(button.dataset.learnTab));
            });
            showLearnTab(sessionStorage.getItem("ct_learn_active_tab") || "today", { remember: false });

            function createAttemptId() {
                if (window.crypto && typeof window.crypto.randomUUID === "function") {
                    return window.crypto.randomUUID();
                }
                return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
            }

            function findKpiByCode(code) {
                return allKpis.find((k) => k.code === code) || null;
            }

            function focusSessionOnKpi(kpiOrCode) {
                const code = typeof kpiOrCode === "string"
                    ? kpiOrCode
                    : (kpiOrCode && kpiOrCode.code) || "";
                if (!code) return;
                startSession(code);
            }

            function renderSearchResults(query) {
                const panel = $("search-results");
                if (!panel) return;

                const q = String(query || "").trim().toLowerCase();
                if (!q) {
                    panel.innerHTML = "";
                    panel.classList.add("hidden");
                    return;
                }

                const matches = curriculumKpis.filter((k) => {
                    const haystack = [
                        k.code,
                        k.text,
                        k.cluster,
                        k.standard,
                        k.deca_cluster,
                    ]
                        .filter(Boolean)
                        .join(" ")
                        .toLowerCase();
                    return haystack.includes(q);
                });

                panel.innerHTML = "";
                panel.classList.remove("hidden");

                if (!matches.length) {
                    const empty = document.createElement("div");
                    empty.className = "search-empty";
                    empty.textContent = "No matches yet. Try a broader topic or a KPI code.";
                    panel.appendChild(empty);
                    return;
                }

                matches.slice(0, 8).forEach((kpi) => {
                    const row = document.createElement("button");
                    row.type = "button";
                    row.className = "search-row";
                    const ready = !!findKpiByCode(kpi.code);
                    row.innerHTML =
                        `<strong>${escHtml(kpi.code || "")}</strong>` +
                        `<span>${escHtml(kpi.text || "")}</span>` +
                        `<small>${escHtml(kpi.cluster || "")} · ${ready ? escHtml((findKpiByCode(kpi.code).learning_status || "not learned").replace("_", " ")) : "lesson being prepared"}</small>`;
                    row.disabled = !ready;
                    if (ready) row.addEventListener("click", () => focusSessionOnKpi(kpi));
                    panel.appendChild(row);
                });
            }

            function renderRecommendedPath() {
                const list = $("learning-path-list");
                if (!list) return;

                const source = [];
                const seen = new Set();
                [
                    ...(kpiGroups.unstarted || []),
                    ...(kpiGroups.due || []),
                    ...(kpiGroups.in_progress || []),
                    ...allKpis,
                ].forEach((kpi) => {
                    const code = kpi.kpi_code || kpi.code || "";
                    if (!code || seen.has(code) || source.length >= 3) return;
                    seen.add(code);
                    source.push({
                        code,
                        text: kpi.kpi_text || kpi.text || code,
                    });
                });

                list.innerHTML = "";
                if (!source.length) {
                    const empty = document.createElement("div");
                    empty.className = "empty-state";
                    empty.textContent = "Study material for this event is still being prepared.";
                    list.appendChild(empty);
                    return;
                }

                source.forEach((item, index) => {
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "study-row" + (index === 0 ? " primary" : "");
                    btn.innerHTML =
                        `<span class="study-row-code">${escHtml(item.code || "")}</span>` +
                        `<span class="study-row-text">` +
                            `<strong>${escHtml(item.text || "")}</strong>` +
                            `<small>${escHtml(findKpiByCode(item.code)?.cluster || "")} · Standard · ~4 min</small>` +
                        `</span>` +
                        `<span class="study-row-score">${index === 0 ? "Learn next" : "Up next"}</span>`;
                    btn.addEventListener("click", () => focusSessionOnKpi(item.code));
                    list.appendChild(btn);
                });
            }

            function renderCurriculum() {
                const container = $("curriculum-list");
                if (!container) return;
                const readyByCode = new Map(allKpis.map((kpi) => [kpi.code, kpi]));
                const groups = new Map();
                curriculumKpis.forEach((kpi) => {
                    const name = kpi.cluster || "Other";
                    if (!groups.has(name)) groups.set(name, []);
                    groups.get(name).push(kpi);
                });
                const entries = [...groups.entries()];
                container.innerHTML = entries.slice(0, curriculumExpanded ? entries.length : 6).map(([name, kpis]) => {
                    const learned = kpis.filter((kpi) => readyByCode.get(kpi.code)?.current_lesson_completed).length;
                    const rows = kpis.map((kpi) => {
                        const ready = readyByCode.get(kpi.code);
                        const learnedNow = !!ready?.current_lesson_completed;
                        const history = ready?.previous_activity ? `<small>Previous performance: ${Math.round(ready.mastery_score || 0)}% · not completed in current Learn Mode</small>` : "";
                        return `<button type="button" class="curriculum-kpi" data-curriculum-code="${escHtml(kpi.code)}" ${ready ? "" : "disabled"}><i>${learnedNow ? "✓" : "○"}</i><span><strong>${escHtml(kpi.code)} · ${escHtml(kpi.text)}</strong>${history || `<small>${ready ? (learnedNow ? "Learned" : "Not learned") : "Lesson being prepared"}</small>`}</span></button>`;
                    }).join("");
                    return `<details class="curriculum-group"><summary><span>${escHtml(name)}</span><strong>${learned} / ${kpis.length}</strong></summary><div>${rows}</div></details>`;
                }).join("") || `<p class="empty-state">Curriculum data is being prepared.</p>`;
                container.querySelectorAll("[data-curriculum-code]:not([disabled])").forEach((button) => button.addEventListener("click", () => focusSessionOnKpi(button.dataset.curriculumCode)));
                $("curriculum-toggle").textContent = curriculumExpanded ? "Show less" : "Show all";
            }

            function renderReview() {
                const due = kpiGroups.due || [];
                const section = $("review-section");
                section.hidden = !due.length;
                section.closest("[data-learn-panel]")?.classList.toggle("no-review", !due.length);
                if (!due.length) return;
                $("due-summary-count").textContent = due.length;
                $("review-kpi-list").innerHTML = due.slice(0,5).map((kpi) => `<div class="review-kpi-row"><div><strong>${escHtml(kpi.code)} · ${escHtml(kpi.text)}</strong><span>${Math.round(kpi.mastery_score || 0)}% mastery · previously learned · review recommended</span></div><button type="button" data-review-code="${escHtml(kpi.code)}">Review</button></div>`).join("");
                $("review-kpi-list").querySelectorAll("[data-review-code]").forEach((button) => button.addEventListener("click", startReview));
            }

            function renderLearnHome() {
                const startBtn = $("start-btn");
                if (startBtn) {
                    startBtn.textContent = allKpis.length
                        ? "Start Learning"
                        : "Content is being prepared";
                    startBtn.disabled = !allKpis.length;
                }

                const sum = analyticsData?.summary || {};
                const learned = Number(sum.completed_kpis ?? kpiGroups.mastered.length ?? 0);
                const total = Number(sum.total_kpis_available || curriculumKpis.length || 0);
                const coverage = total ? (100 * learned / total) : 0;
                $("learn-event-name").textContent = currentEventName || "Your event";
                $("learned-count").textContent = `${learned} / ${total} KPIs learned`;
                $("coverage-percent").textContent = `${coverage < 1 && coverage > 0 ? "<1" : Math.round(coverage)}% of event content`;
                $("coverage-fill").style.width = `${Math.min(100, coverage)}%`;
                $("learned-mastery").textContent = learned && Number(sum.avg_mastery) ? `${Math.round(sum.avg_mastery)}%` : "No data";
                $("dash-due").textContent = Number(sum.questions_due || 0);
                renderRecommendedPath();
                renderCurriculum();
                renderReview();
                const preparing = !allKpis.length;
                $("content-preparation-state").hidden = !preparing;
                $("learning-path-panel").hidden = preparing;
                if (preparing) $("preparation-event-name").textContent = `We're preparing lessons for ${currentEventName}.`;
            }

            // ─── Auth ─────────────────────────────────────────────────────────────────────
            requireAuth().then((user) => {
                if (user) {
                    initTopbar(user);
                    initLearn();
                }
            });

            // ─── Init: load event + KPIs ──────────────────────────────────────────────────
            async function initLearn() {
                // Server is source of truth. Fetch profile, hydrate cache, then read cache.
                try {
                    const meRes = await apiFetch("/auth/me");
                    const meData = await meRes.json().catch(() => ({}));
                    UserPrefs.hydrateFromProfile(meData.user || meData);
                } catch(e) {
                    // Network failed — fall through to whatever is already cached
                }
                // Always work with the slug. Name is for display only.
                const savedEventId = UserPrefs.getEventId();
                const savedEventName = UserPrefs.getEventName();
                const resolveEventSlug = (value) => {
                    const raw = String(value || "").trim();
                    if (!raw) return "";
                    const mapped = getEventIdByName(raw);
                    return isSupportedBetaEventId(mapped) ? mapped : "";
                };
                const eventIdForApi = resolveEventSlug(savedEventId || savedEventName);

                if (!eventIdForApi) {
                    ErrorManager.show("Choose an event in Settings before starting Learn Mode.", "error");
                    return;
                }

                try {
                    const res = await apiFetch("/api/kpis?event_id=" + encodeURIComponent(eventIdForApi));
                    const data = await res.json();
                    const events = data.events || [];
                    const kpis = data.kpis || [];

                    // Match by slug — no name-based fallback, no events[0]
                    const ev = events.find((e) => e.id === eventIdForApi) || null;
                    if (!ev) {
                        ErrorManager.show("Your saved event is unavailable. Choose it again in Settings.", "error");
                        return;
                    }

                    currentEventId = ev.id || "";
                    currentEventName = ev.name || "";
                    // event type is derived from name (clusters.js is keyed on name — display logic only)
                    currentEventType = (typeof getEventType === "function")
                        ? getEventType(ev.name || "")
                        : "series";
                    // KPIs from server are already scoped to this event — no client-side filter needed
                    allKpis = kpis;
                    curriculumKpis = data.curriculum || kpis;
                    kpiGroups = {
                        unstarted: data.unstarted || [],
                        due: data.due || [],
                        in_progress: data.in_progress || [],
                        mastered: data.mastered || [],
                    };

                    const btn = $("start-btn");
                    if (allKpis.length) {
                        btn.textContent = "Start Learning";
                        btn.disabled = false;
                    } else {
                        btn.textContent = "Content is being prepared";
                        btn.disabled = true;
                    }

                    // Show/hide mode buttons based on event type
                    _updateModeButtonsForEventType(currentEventType);

                    const searchInput = $("learn-search");
                    if (searchInput && !searchInput.dataset.wired) {
                        searchInput.dataset.wired = "1";
                        searchInput.addEventListener("input", (e) => {
                            renderSearchResults(e.target.value);
                        });
                    }

                    renderLearnHome();

                    // Load mastery dashboard asynchronously (non-blocking)
                    initMasteryDashboard(currentEventId);

                    // Wire mode buttons
                    const modeButtons = document.querySelectorAll('.mode-btn');
                    modeButtons.forEach(btn => {
                        btn.addEventListener('click', () => {
                            modeButtons.forEach(b => b.classList.remove('active'));
                            btn.classList.add('active');
                            renderLearnHome();
                        });
                    });
                } catch (e) {
                    ErrorManager.show("Learn Mode failed to load. Please refresh.", "error");
                }
            }

            $("start-btn").addEventListener("click", () => {
                if (!allKpis.length) return;
                startSession();
            });

            // ─── Mode button visibility based on event type ───────────────────────────────
            function _updateModeButtonsForEventType(eventType) {
                const modeButtons = document.querySelectorAll('.mode-btn');
                const standardBtn = document.querySelector('[data-learn-mode="standard"]');
                modeButtons.forEach((button) => button.classList.remove('active'));
                if (standardBtn) standardBtn.classList.add('active');
            }

            // ─── Session start ────────────────────────────────────────────────────────────
            async function startSession(focusCode = "") {
                const focused = focusCode
                    ? findKpiByCode(focusCode)
                    : null;
                sessionQueue = focused
                    ? [focused, ...allKpis.filter((kpi) => kpi.code !== focused.code)]
                    : [...allKpis];
                sessionIdx = 0;
                completedKpiCodes = new Set();
                kpiLoadToken++;
                chunkKpis = [];
                isReviewMode = false;
                sessionQAnswered = 0;
                sessionQCorrect = 0;
                sessionRecogAnswered = 0;
                sessionRecogCorrect = 0;
                sessionAppAnswered = 0;
                sessionAppCorrect = 0;
                sessionVocabTotal = 0;
                sessionVocabCorrect = 0;
                sessionRoleplayScore = null;
                sessionArAnswers = [];
                sessionStartTime = Date.now();
                sessionId = null;

                // Capture pre-session mastery snapshot
                preMasteryMap = {};
                if (analyticsData && analyticsData.kpi_mastery) {
                    analyticsData.kpi_mastery.forEach((m) => {
                        preMasteryMap[m.kpi_code] = m.mastery_score || 0;
                    });
                }

                // Learn Content is the stable default. Advanced modes may opt in later.
                const modeBtn = document.querySelector('.mode-btn.active');
                currentLearnMode = (modeBtn && modeBtn.dataset.learnMode) || 'standard';

                try {
                    const response = await apiFetch("/api/learn/session/start", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({event_id: currentEventId, session_type: currentLearnMode}),
                    });
                    const data = await response.json().catch(() => ({}));
                    sessionId = response.ok ? data.session_id || null : null;
                } catch (error) {
                    sessionId = null;
                }
                if (!sessionId) {
                    showError("The study session could not be saved. Check your connection and try again.");
                    return;
                }

                viewHome.style.display = "none";
                viewSession.style.display = "block";
                $("skip-kpi-btn").style.display = "";
                document.querySelector(".phase-pills").style.visibility = "visible";

                $("prog-total").textContent = sessionQueue.length;
                updateProgress();
                loadCurrentKpi();
            }

            // ─── Progress bar ─────────────────────────────────────────────────────────────
            function updateProgress() {
                $("prog-current").textContent = sessionIdx + 1;
                $("progress-fill").style.width =
                    Math.round((sessionIdx / sessionQueue.length) * 100) + "%";
                const kpi = sessionQueue[sessionIdx];
                if (kpi) $("sess-cluster-name").textContent = kpi.cluster || "";
            }

            // ─── Load current KPI ─────────────────────────────────────────────────────────
            async function loadCurrentKpi() {
                if (sessionIdx >= sessionQueue.length) {
                    showDone();
                    return;
                }

                const kpi = sessionQueue[sessionIdx];
                const loadToken = ++kpiLoadToken;
                $("skip-kpi-btn").style.display = "";
                updateProgress();
                qAnswered = false;
                sessionData = null;
                kpiQuestionStart = sessionQAnswered;
                kpiCorrectStart = sessionQCorrect;
                lastKpiMastery = null;
                kpiFirstPassAnswered = 0;
                kpiFirstPassCorrect = 0;

                $("loading-kpi-text").textContent = kpi.code + " — " + kpi.text;
                setPhase("mission", "pending");
                setPhase("vocab", "pending");
                showState("loading");

                // Check local cache first
                const cached = getQBank(kpi.event, kpi.code);
                if (cached) {
                    sessionData = cached;
                } else {
                    try {
                        const res = await apiFetch("/api/learn/generate", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                code: kpi.code,
                                text: kpi.text,
                                cluster: kpi.cluster,
                                standard: kpi.standard,
                                deca_cluster: kpi.deca_cluster || "",
                                event_id: kpi.event || "",
                            }),
                        });
                        const data = await readJsonOrThrow(res, "Lesson generation failed");
                        if (loadToken !== kpiLoadToken) return;

                        // Preserve server UUID; fall back to local id for offline cache
                        (data.questions || []).forEach((q, i) => {
                            if (!q.id) q.id = kpi.code + "_" + i;
                        });
                        saveQBank(kpi.event, kpi.code, data);
                        sessionData = data;
                        localStorage.removeItem(`ct_lesson_failures_${kpi.event}_${kpi.code}`);
                        $("error-skip-btn").classList.remove("prominent");
                    } catch (e) {
                        if (loadToken !== kpiLoadToken) return;
                        const failureKey = `ct_lesson_failures_${kpi.event}_${kpi.code}`;
                        const failureCount = Number(localStorage.getItem(failureKey) || 0) + 1;
                        localStorage.setItem(failureKey, String(failureCount));
                        $("error-skip-btn").classList.toggle("prominent", failureCount >= 2);
                        showError("We couldn't load this lesson right now. Your progress is safe.");
                        return;
                    }
                }

                if (loadToken !== kpiLoadToken) return;

                if (currentLearnMode === 'examOnly') {
                    // Exam Only: skip vocab and concept, go straight to questions
                    setPhase("vocab", "done");
                    setPhase("concept", "done");
                    startQuestions(kpi);
                } else if (currentLearnMode === 'principles') {
                    // Principles: vocab → concept → application question only (no roleplay)
                    startMission(kpi);
                } else {
                    // Standard / TDM: full flow (vocab → concept → questions → roleplay every 7)
                    startMission(kpi);
                }
            }

            function startMission(kpi) {
                const mission = sessionData.mission || {};
                const interaction = mission.opening_interaction || {};
                const plan = sessionData.instructional_plan || {};
                setPhase("mission", "active");
                $("mission-archetype").textContent = String(plan.primary_archetype || "business mission").replaceAll("_", " ");
                $("mission-title").textContent = mission.title || `Solve the ${kpi.code} challenge`;
                $("mission-brief").textContent = mission.brief || sessionData.hook || kpi.text;
                $("mission-question").textContent = interaction.question || "What would you do first?";
                $("mission-reveal").hidden = true;
                const choices = $("mission-choices");
                choices.innerHTML = "";
                (interaction.choices || []).forEach((choice, index) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "mission-choice";
                    button.textContent = choice;
                    button.addEventListener("click", () => {
                        choices.querySelectorAll("button").forEach((item, itemIndex) => {
                            item.disabled = true;
                            if (itemIndex === interaction.correct) item.classList.add("correct");
                            else if (itemIndex === index) item.classList.add("wrong");
                        });
                        const tailored = Array.isArray(interaction.choice_feedback)
                            ? interaction.choice_feedback[index]
                            : "";
                        $("mission-explanation").textContent = tailored || interaction.explanation || "Now inspect the business reasoning behind the decision.";
                        $("mission-aha").textContent = interaction.aha || "This is why the strongest business choice depends on evidence, not instinct alone.";
                        $("mission-reveal").hidden = false;
                    });
                    choices.appendChild(button);
                });
                showState("mission");
            }

            $("mission-continue").addEventListener("click", () => {
                setPhase("mission", "done");
                startVocab(currentKpi());
            });
            $("browse-kpis-btn").addEventListener("click", () => {
                curriculumExpanded = true;
                renderCurriculum();
                showLearnTab("curriculum");
                $("curriculum-section").scrollIntoView({behavior: "smooth", block: "start"});
            });
            $("curriculum-toggle").addEventListener("click", () => {
                curriculumExpanded = !curriculumExpanded;
                renderCurriculum();
            });

            // ─── VOCAB phase ──────────────────────────────────────────────────────────────
            function startVocab(kpi) {
                const complexity = sessionData.lesson_design?.complexity || "standard";
                const vocabLimit = { quick: 3, standard: 4, deep: 5 }[complexity] || 4;
                vocabList = (sessionData.vocab || []).slice(0, vocabLimit);
                vocabIdx = 0;
                setPhase("vocab", "active");

                if (!vocabList.length) {
                    startConcept(kpi);
                    return;
                }
                $("vocab-total").textContent = vocabList.length;
                showVocabCard(kpi);
                showState("vocab");
            }

            function showVocabCard(kpi) {
                $("vocab-idx").textContent = vocabIdx + 1;
                const card = vocabList[vocabIdx];
                const definitionFirst = vocabIdx % 2 === 1;
                $("vocab-card-label").textContent = definitionFirst ? "Definition" : "Term";
                $("vocab-choose-label").textContent = definitionFirst
                    ? "Choose the matching term"
                    : "Choose the correct definition";
                $("vocab-term").textContent = definitionFirst ? card.definition : card.term;

                // Build 4 choices: 1 correct + 3 distractors from other vocab
                const others = vocabList.filter((_, i) => i !== vocabIdx);
                const distractors = shuffle(others).slice(0, 3);
                const choices = shuffle([
                    { text: definitionFirst ? card.term : card.definition, correct: true },
                    ...distractors.map((d) => ({
                        text: definitionFirst ? d.term : d.definition,
                        correct: false,
                    })),
                ]);

                const grid = $("vocab-grid");
                grid.innerHTML = "";
                choices.forEach((c, i) => {
                    const btn = document.createElement("button");
                    btn.className = "vchoice";
                    btn.type = "button";
                    btn.dataset.correct = c.correct ? "1" : "0";
                    btn.innerHTML = `<span class="vchoice-num">${i + 1}</span><span>${escHtml(c.text)}</span>`;
                    btn.addEventListener("click", () =>
                        handleVocabAnswer(btn, c.correct, choices, kpi),
                    );
                    grid.appendChild(btn);
                });
            }

            function handleVocabAnswer(btn, isCorrect, choices, kpi) {
                sessionVocabTotal++;
                if (isCorrect) sessionVocabCorrect++;
                const allBtns = $("vocab-grid").querySelectorAll(".vchoice");
                allBtns.forEach((b) => (b.disabled = true));

                if (isCorrect) {
                    btn.classList.add("correct");
                    setTimeout(() => advanceVocab(kpi), 700);
                } else {
                    btn.classList.add("wrong");
                    // Highlight the correct one
                    const correctIdx = choices.findIndex((c) => c.correct);
                    allBtns[correctIdx].classList.add("correct");
                    // Dim the rest
                    allBtns.forEach((b, i) => {
                        if (b !== btn && i !== correctIdx)
                            b.classList.add("neutral");
                    });
                    setTimeout(() => advanceVocab(kpi), 1300);
                }
            }

            $("vocab-skip").addEventListener("click", () => {
                sessionVocabTotal++; // skip counts as missed
                // Show the correct answer briefly then move on
                const allBtns = $("vocab-grid").querySelectorAll(".vchoice");
                allBtns.forEach((b) => (b.disabled = true));
                if (allBtns[0]) {
                    allBtns.forEach((b) => {
                        if (b.dataset.correct === "1") b.classList.add("correct");
                        else b.classList.add("neutral");
                    });
                }
                setTimeout(() => advanceVocab(currentKpi()), 1100);
            });

            function advanceVocab(kpi) {
                vocabIdx++;
                if (vocabIdx >= vocabList.length) {
                    setPhase("vocab", "done");
                    startConcept(kpi);
                } else {
                    showVocabCard(kpi);
                }
            }

            function currentKpi() {
                return sessionQueue[sessionIdx];
            }

            function clearNode(id) {
                const el = $(id);
                if (el) el.innerHTML = "";
                return el;
            }

            async function readJsonOrThrow(response, fallbackMessage) {
                const text = await response.text();
                let data = {};
                try {
                    data = text ? JSON.parse(text) : {};
                } catch (error) {
                    const looksHtml = text.trim().startsWith("<");
                    throw new Error(
                        looksHtml
                            ? `${fallbackMessage || "Request failed"} (server returned HTML, HTTP ${response.status})`
                            : `${fallbackMessage || "Request failed"} (invalid JSON, HTTP ${response.status})`,
                    );
                }
                if (!response.ok || data.error) {
                    throw new Error(data.detail || data.error || `${fallbackMessage || "Request failed"} (HTTP ${response.status})`);
                }
                return data;
            }

            function renderLessonDesign(data) {
                const row = clearNode("lesson-design-row");
                if (!row) return;
                const design = data.lesson_design || {};
                const plan = data.instructional_plan || {};
                const chips = [
                    plan.primary_archetype ? String(plan.primary_archetype).replaceAll("_", " ") : "",
                    plan.learner_action ? `you ${plan.learner_action}` : "",
                    design.complexity ? `${design.complexity} KPI` : "",
                    design.skill_type ? String(design.skill_type).replace("_", " ") : "",
                    design.target_minutes ? `~${design.target_minutes} min` : "",
                ].filter(Boolean);
                chips.forEach((text) => {
                    const chip = document.createElement("span");
                    chip.className = "lesson-design-chip";
                    chip.textContent = text;
                    row.appendChild(chip);
                });
            }

            function renderLearningBlocks(blocks) {
                const wrap = clearNode("learning-blocks");
                if (!wrap) return;
                let revealed = 0;
                const cards = [];
                (blocks || []).forEach((block, index) => {
                    const card = document.createElement("div");
                    card.className = "learning-block" + (index > 0 ? " lesson-block-locked" : "");
                    card.innerHTML =
                        `<div class="learning-block-type">${escHtml(String(block.type || "concept reveal").replaceAll("_", " "))}</div>` +
                        `<div class="learning-block-title">${escHtml(block.title || "")}</div>` +
                        `<div class="learning-block-body">${escHtml(block.body || "")}</div>`;
                    wrap.appendChild(card);
                    cards.push(card);
                });
                if (cards.length > 1) {
                    const reveal = document.createElement("button");
                    reveal.type = "button";
                    reveal.className = "lesson-reveal-btn";
                    reveal.textContent = "Reveal next insight →";
                    reveal.addEventListener("click", () => {
                        revealed++;
                        cards[revealed]?.classList.remove("lesson-block-locked");
                        if (revealed + 1 >= cards.length) reveal.remove();
                    });
                    wrap.appendChild(reveal);
                }
            }

            function renderRealisticExample(example) {
                const wrap = clearNode("realistic-example");
                if (!wrap || !example) return;
                const flow = Array.isArray(example.flow) ? example.flow : [];
                wrap.innerHTML =
                    `<div class="lesson-section-label">See it happen</div>` +
                    `<div class="lesson-example-story">${escHtml(example.story || "")}</div>` +
                    `<div class="lesson-flow">${flow.map((step) => `<span>${escHtml(step)}</span>`).join("<b>→</b>")}</div>`;
            }

            function renderKeyTakeaways(takeaways) {
                const wrap = clearNode("key-takeaways");
                if (!wrap || !Array.isArray(takeaways) || !takeaways.length) return;
                wrap.innerHTML = `<div class="lesson-section-label">Remember this</div>`;
                const list = document.createElement("ul");
                takeaways.forEach((item) => {
                    const li = document.createElement("li");
                    li.textContent = item;
                    list.appendChild(li);
                });
                wrap.appendChild(list);
            }

            function renderMiniRoleplay(roleplay) {
                const wrap = clearNode("mini-roleplay");
                if (!wrap || !roleplay || !Array.isArray(roleplay.decisions) || !roleplay.decisions.length) return;
                let step = 0;
                const renderStep = () => {
                    const decision = roleplay.decisions[step];
                    wrap.innerHTML =
                        `<div class="lesson-section-label">Mini roleplay</div>` +
                        `<div class="mini-roleplay-meta">${escHtml(roleplay.role || "Your role")}</div>` +
                        `<div class="mini-roleplay-setup">${escHtml(step === 0 ? roleplay.setup || "" : decision.situation || "")}</div>` +
                        `<div class="mini-roleplay-question">${escHtml(decision.question || "What should you do?")}</div>`;
                    const choices = document.createElement("div");
                    choices.className = "mini-roleplay-choices";
                    (decision.choices || []).forEach((choice, index) => {
                        const btn = document.createElement("button");
                        btn.type = "button";
                        btn.className = "mini-roleplay-choice";
                        btn.textContent = choice;
                        btn.addEventListener("click", () => {
                            choices.querySelectorAll("button").forEach((b, i) => {
                                b.disabled = true;
                                if (i === decision.correct) b.classList.add("correct");
                                else if (i === index) b.classList.add("wrong");
                            });
                            const feedback = document.createElement("div");
                            feedback.className = "mini-roleplay-feedback";
                            feedback.innerHTML =
                                `<strong>${index === decision.correct ? "Good call." : "Not quite."}</strong> ` +
                                `${escHtml(decision.explanation || "")}` +
                                `<div>${escHtml(decision.consequence || "")}</div>`;
                            wrap.appendChild(feedback);
                            const next = document.createElement("button");
                            next.type = "button";
                            next.className = "mini-roleplay-next";
                            const last = step + 1 >= roleplay.decisions.length;
                            next.textContent = last ? "Finish mini roleplay" : "Next decision";
                            next.addEventListener("click", () => {
                                if (last) {
                                    wrap.innerHTML += `<div class="mini-roleplay-why">${escHtml(roleplay.why_it_matters || "")}</div>`;
                                    next.remove();
                                    return;
                                }
                                step++;
                                renderStep();
                            });
                            wrap.appendChild(next);
                        });
                        choices.appendChild(btn);
                    });
                    wrap.appendChild(choices);
                };
                renderStep();
            }

            // ─── CONCEPT phase ────────────────────────────────────────────────────────────
            function startConcept(kpi) {
                setPhase("concept", "active");
                const c = sessionData.concept || {};
                const complexity = sessionData.lesson_design?.complexity || "standard";

                $("concept-code").textContent = kpi.code;
                $("concept-cluster").textContent = kpi.cluster;
                $("concept-kpi-text").textContent = kpi.text;
                $("concept-summary").textContent = c.summary || "";
                if ($("lesson-hook")) $("lesson-hook").textContent = sessionData.hook || "";
                renderLessonDesign(sessionData || {});
                renderLearningBlocks(sessionData.learning_blocks || []);
                $("concept-explanation").textContent = c.explanation || "";

                const bullets = $("concept-bullets");
                bullets.innerHTML = "";
                (c.bullets || []).forEach((b) => {
                    const li = document.createElement("li");
                    li.textContent = b;
                    bullets.appendChild(li);
                });

                const tbody = $("concept-table-body");
                tbody.innerHTML = "";
                (c.table || []).forEach((row) => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `<td>${escHtml(row.term || "")}</td><td>${escHtml(row.definition || "")}</td>`;
                    tbody.appendChild(tr);
                });
                renderRealisticExample(complexity === "quick" ? null : sessionData.realistic_example);
                renderMiniRoleplay(complexity === "quick" ? null : sessionData.mini_roleplay);
                renderKeyTakeaways(sessionData.key_takeaways);

                // ── Concept check — locks "I understand" until answered ───────────────────
                // One question testing the core idea. Just enough to verify engagement.
                // If the model didn't generate one (older cache), fall through silently.
                const check = complexity === "quick"
                    ? null
                    : sessionData.interactive_check || c.concept_check;
                const understandBtn = $("understand-btn");
                const checkContainer = $("concept-check-container");

                // Clear any leftover check from a previous KPI
                if (checkContainer) checkContainer.innerHTML = "";
                understandBtn.disabled = false;
                understandBtn.textContent = "I understand →";

                if (check && check.question && check.choices && check.choices.length >= 3) {
                    understandBtn.disabled = true;
                    understandBtn.textContent = "Answer the question below to continue →";

                    const qEl = document.createElement("div");
                    qEl.className = "concept-check-question";
                    qEl.innerHTML = `<p class="concept-check-prompt">${escHtml(check.question)}</p>`;

                    const choicesEl = document.createElement("div");
                    choicesEl.className = "concept-check-choices";
                    const letters = ["A", "B", "C", "D"];
                    let checkAnswered = false;

                    check.choices.forEach((choice, i) => {
                        const btn = document.createElement("button");
                        btn.className = "choice-btn";
                        btn.type = "button";
                        btn.innerHTML = `<span class="choice-letter">${letters[i]}.</span>${escHtml(choice)}`;
                        btn.addEventListener("click", () => {
                            if (checkAnswered) return;
                            checkAnswered = true;

                            // Show correct/wrong immediately
                            choicesEl.querySelectorAll(".choice-btn").forEach((b, j) => {
                                b.disabled = true;
                                if (j === check.correct) b.classList.add("correct");
                                else if (j === i && i !== check.correct) b.classList.add("wrong");
                                else b.classList.add("neutral");
                            });

                            const feedbackEl = document.createElement("p");
                            feedbackEl.className = "concept-check-feedback";
                            const correct = i === check.correct;
                            feedbackEl.style.color = correct ? "var(--green)" : "var(--yellow)";
                            feedbackEl.textContent = correct
                                ? "✓ " + (check.explanation || "Correct!")
                                : "✗ " + (check.explanation || "Not quite — see above.");
                            qEl.appendChild(feedbackEl);

                            // Unlock continue regardless of right/wrong —
                            // wrong answer already showed the correct one
                            understandBtn.disabled = false;
                            understandBtn.textContent = "I understand →";
                        });
                        choicesEl.appendChild(btn);
                    });

                    qEl.appendChild(choicesEl);
                    if (checkContainer) checkContainer.appendChild(qEl);
                }

                showState("concept");
            }

            $("understand-btn").addEventListener("click", () => {
                setPhase("concept", "done");
                startQuestions(currentKpi());
            });

            // ─── QUESTIONS phase ──────────────────────────────────────────────────────────
            // Per-KPI adaptive state — updated from engine response after each answer
            let _kpiQueueActions = [];  // e.g. ["increase_recognition_weight", "defer_application_questions"]

            function startQuestions(kpi) {
                setPhase("questions", "active");
                missed = [];

                // Prefer the app-owned final 3-question challenge when present.
                const all = sessionData.questions || [];
                const practiceQuestions = (sessionData.practice_questions || [])
                    .map((q, index) => ({
                        ...q,
                        stage_label: q.stage_label || ["Check", "Apply", "DECA Challenge"][index] || "Practice",
                    }));
                if (practiceQuestions.length >= 3) {
                    const complexity = sessionData.lesson_design?.complexity || "standard";
                    const shapedQuestions = complexity === "quick"
                        ? [practiceQuestions[0], practiceQuestions[2]]
                        : practiceQuestions.slice(0, 3);
                    qShown = shapedQuestions.filter(q => !getCorrectQs().has(q.id));
                    if (!qShown.length) { kpiDone(); return; }
                    qIdx = 0;
                    $("qs-total").textContent = qShown.length;
                    showQuestion();
                    showState("questions");
                    return;
                }

                // Backward-compatible fallback for older cached lessons.
                const recognition = all.filter(q => (q.question_type || "recognition") === "recognition");
                const application = all.filter(q => q.question_type === "application");

                const done = getCorrectQs();
                const availableRecognition = recognition.filter(q => !done.has(q.id));
                const availableApplication = application.filter(q => !done.has(q.id));

                if (currentLearnMode === 'principles') {
                    if (!availableApplication.length) { kpiDone(); return; }
                    qShown = [availableApplication[0]];

                } else if (currentLearnMode === 'examOnly') {
                    if (!availableRecognition.length) { kpiDone(); return; }
                    qShown = shuffle(availableRecognition).slice(0, QUESTIONS_PER_KPI);

                } else {
                    // Standard / TDM — with adaptive weighting
                    if (!availableRecognition.length && !availableApplication.length) { kpiDone(); return; }

                    // Default: 5 recognition + 1 application
                    let recogCount = QUESTIONS_PER_KPI;
                    let includeApplication = availableApplication.length > 0;

                    // ── Apply queue_actions from the adaptive engine ──────────────────────
                    // "increase_recognition_weight": student may be pattern-matching
                    //   → show all available recognition, push application to end
                    // "defer_application_questions": signal too noisy for application
                    //   → skip application entirely this round
                    if (_kpiQueueActions.includes("defer_application_questions")) {
                        includeApplication = false;
                    } else if (_kpiQueueActions.includes("increase_recognition_weight")) {
                        recogCount = Math.min(availableRecognition.length, QUESTIONS_PER_KPI + 2);
                    }

                    // ── Adaptive weighting from mastery split ─────────────────────────────
                    // If recognition mastery is high but application is low, flip the ratio:
                    // show fewer recognition (they're solid) and prioritise the application Q.
                    // analyticsData is loaded async on session start from /api/learn/analytics.
                    const kpiMastery = analyticsData && analyticsData.kpi_mastery
                        ? analyticsData.kpi_mastery.find(m => m.kpi_code === kpi.code)
                        : null;
                    if (kpiMastery) {
                        const recogM = kpiMastery.recognition_mastery ?? kpiMastery.mastery_score ?? 0;
                        const appM   = kpiMastery.application_mastery ?? 0;
                        if (recogM > 0.75 && appM < 0.50 && includeApplication) {
                            // Strong on recognition, weak on application
                            // → trim recognition, ensure application leads
                            recogCount = Math.max(2, Math.floor(QUESTIONS_PER_KPI / 2));
                        }
                    }

                    const recognitionToShow = shuffle(availableRecognition).slice(0, recogCount);
                    qShown = [
                        ...recognitionToShow,
                        ...(includeApplication && availableApplication.length ? [availableApplication[0]] : []),
                    ];
                }

                if (!qShown.length) { kpiDone(); return; }
                qIdx = 0;
                $("qs-total").textContent = qShown.length;
                showQuestion();
                showState("questions");
            }

            function showQuestion() {
                const q = qShown[qIdx];
                q._attemptId = createAttemptId();
                $("qs-current").textContent = qIdx + 1;
                $("result-panel").style.display = "none";
                $("next-q-btn").style.display = "none";
                qAnswered = false;

                // Reset per-question timing state
                _qStartTime         = Date.now();
                _qFirstClickTime    = null;
                _qAnswerChangeCount = 0;
                _qLastChoice        = null;

                // Show question type badge for application questions
                const questionBox = $("question-text").parentElement;
                let badge = questionBox.querySelector(".q-type-badge");
                if (q.question_type === "application") {
                    if (!badge) {
                        badge = document.createElement("div");
                        badge.className = "q-type-badge q-type-application";
                        questionBox.insertBefore(badge, questionBox.firstChild);
                    }
                    badge.textContent = "📋 Application Scenario";
                } else {
                    if (badge) badge.remove();
                }

                if ($("question-stage")) {
                    const labels = ["Check", "Apply", "DECA Challenge"];
                    const stage = q.stage_label || labels[qIdx] || "";
                    $("question-stage").textContent = stage;
                    questionBox.classList.toggle("boss-question", stage === "DECA Challenge");
                }
                $("question-text").textContent = q.text;

                const list = $("choices-list");
                list.innerHTML = "";
                const letters = ["A", "B", "C", "D"];
                (q.choices || []).forEach((choice, i) => {
                    const btn = document.createElement("button");
                    btn.className = "choice-btn";
                    btn.type = "button";
                    btn.innerHTML = `<span class="choice-letter">${letters[i]}.</span>${escHtml(choice)}`;
                    btn.addEventListener("click", () => handleQAnswer(i, q));
                    list.appendChild(btn);
                });
            }

            async function handleQAnswer(chosen, q) {
                if (qAnswered) return;
                if (_qFirstClickTime === null) _qFirstClickTime = Date.now();
                qAnswered = true;
                sessionQAnswered++;

                const btns = $("choices-list").querySelectorAll(".choice-btn");
                btns.forEach((b, i) => {
                    b.disabled = true;
                    if (i === q.correct) b.classList.add("correct");
                    else if (i === chosen && chosen !== q.correct)
                        b.classList.add("wrong");
                    else b.classList.add("neutral");
                });

                let ok = chosen === q.correct;
                if (!q._isRetry) {
                    kpiFirstPassAnswered++;
                    if (ok) kpiFirstPassCorrect++;
                }
                // Persist to Supabase (cross-device, permanent)
                const sbId = q.id || "";
                if (!sbId) {
                    showError("This question has no persistent ID and cannot be answered safely. Reload the lesson.");
                    return;
                }
                {
                    const kpi = isReviewMode ? null : currentKpi();
                    try {
                        const saved = await apiFetch("/api/learn/answer", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                question_id: sbId,
                                attempt_id: q._attemptId,
                                selected_index: chosen,
                                response_time_ms: Math.max(1, Date.now() - _qStartTime),
                                time_to_first_ms: _qFirstClickTime
                                    ? Math.max(1, _qFirstClickTime - _qStartTime)
                                    : null,
                                answer_change_count: _qAnswerChangeCount,
                                question_type: q.question_type || "recognition",
                                session_id: sessionId || "",
                                kpi_code: q.kpi_code || (kpi ? kpi.code : ""),
                                cluster: q.cluster || (kpi ? kpi.cluster : ""),
                                deca_cluster: q.deca_cluster || (kpi ? kpi.deca_cluster || "" : ""),
                                event_id: q.event_id || (kpi ? kpi.event || "" : ""),
                            }),
                        });
                        if (!saved.ok) {
                            showError("Your answer could not be saved. Reload and try again before continuing.");
                            return;
                        }
                        const savedAnswer = await saved.json();
                        ok = Boolean(savedAnswer.correct);
                        const serverMastery = savedAnswer.mastery_score ?? savedAnswer.mastery;
                        if (Number.isFinite(Number(serverMastery))) {
                            lastKpiMastery = Number(serverMastery) <= 1
                                ? Math.round(Number(serverMastery) * 100)
                                : Math.round(Number(serverMastery));
                        }
                    } catch (error) {
                        showError("Your answer could not be saved. Check your connection, then reload and try again.");
                        return;
                    }
                }

                if (ok) sessionQCorrect++;
                if ((q.question_type || "recognition") === "application") {
                    sessionAppAnswered++;
                    if (ok) sessionAppCorrect++;
                } else {
                    sessionRecogAnswered++;
                    if (ok) sessionRecogCorrect++;
                }
                if (ok) saveCorrectQ(q.id);
                if (!ok) missed.push(q);

                const banner = $("result-banner");
                banner.className =
                    "result-banner " + (ok ? "correct" : "wrong");
                $("result-icon").textContent = ok ? "✓" : "✗";
                $("result-label").textContent = ok ? "Strong decision" : "Reconsider the evidence";
                $("explanation-box").textContent = q.explanation || "";
                $("result-panel").style.display = "block";

                const isLast = qIdx + 1 >= qShown.length;
                const nextBtn = $("next-q-btn");
                nextBtn.textContent = isLast
                    ? "Finish KPI →"
                    : "Next Question →";
                nextBtn.style.display = "block";
            }

            $("next-q-btn").addEventListener("click", () => {
                qIdx++;
                if (qIdx >= qShown.length) {
                    // If any were missed, replay them before finishing
                    if (missed.length > 0) {
                        qShown = shuffle(missed).map((question) => ({ ...question, _isRetry: true }));
                        missed = [];
                        qIdx = 0;
                        $("qs-total").textContent = qShown.length;
                        const banner = document.createElement("div");
                        banner.style.cssText = "text-align:center;padding:8px;color:var(--yellow);font-weight:600;margin-bottom:8px;";
                        banner.textContent = `Let's retry the ${qShown.length} question${qShown.length > 1 ? "s" : ""} you missed.`;
                        const qTextEl = $("question-text");
                        qTextEl.parentNode.insertBefore(banner, qTextEl);
                        setTimeout(() => banner.remove(), 3000);
                        showQuestion();
                        return;
                    }
                    if (isReviewMode) {
                        $("progress-fill").style.width = "100%";
                        endSession().then(showSummary);
                    } else {
                        setPhase("questions", "done");
                        kpiDone();
                    }
                } else {
                    if (isReviewMode) {
                        const pct = Math.round((qIdx / qShown.length) * 100);
                        $("progress-fill").style.width = pct + "%";
                        $("prog-current").textContent = qIdx + 1;
                    }
                    showQuestion();
                }
            });

            // ─── KPI done — advance or trigger roleplay ───────────────────────────────────
            async function kpiDone() {
                const completedKpi = currentKpi();
                try {
                    const completion = await apiFetch(`/api/learn/kpis/${encodeURIComponent(completedKpi.code)}/complete`, {
                        method: "POST",
                        headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({event_id: currentEventId}),
                    });
                    if (!completion.ok) throw new Error("Lesson completion could not be saved");
                    completedKpi.current_lesson_completed = true;
                } catch (error) {
                    showError("Your lesson was completed, but its curriculum progress could not be saved. Please retry.");
                    return;
                }
                chunkKpis.push(completedKpi);
                completedKpiCodes.add(completedKpi.code);
                sessionIdx++;

                const attempts = kpiFirstPassAnswered;
                const correct = kpiFirstPassCorrect;
                const accuracy = attempts ? Math.round((correct / attempts) * 100) : 100;
                const priorMastery = Number(preMasteryMap[completedKpi.code]);
                const readiness = lastKpiMastery ?? (Number.isFinite(priorMastery) ? Math.round(priorMastery) : accuracy);
                const plan = sessionData.instructional_plan || {};
                $("kpi-feedback-title").textContent = completedKpi.code + " — " + completedKpi.text;
                $("kpi-feedback-accuracy").textContent = attempts ? accuracy + "%" : "—";
                $("kpi-feedback-mastery").textContent = readiness + "%";
                $("kpi-feedback-readiness").textContent = accuracy === 100
                    ? "Strong initial understanding"
                    : accuracy >= 67
                        ? "Developing — one targeted review will sharpen it"
                        : "Needs another review";
                const retryNote = correct < attempts
                    ? " You needed a retry, so we'll bring this KPI back later."
                    : " You handled each question correctly on the first try.";
                $("kpi-feedback-deca").textContent = `For DECA, be ready to ${plan.deca_action || "apply this idea"} and support the choice with business evidence.${retryNote}`;
                $("skip-kpi-btn").style.display = "none";
                showState("kpi-feedback");
            }

            $("kpi-feedback-next").addEventListener("click", () => {
                const roleplayEnabled = currentLearnMode === 'teamDecision';
                if (roleplayEnabled && chunkKpis.length >= ROLEPLAY_EVERY) {
                    startRoleplay();
                } else {
                    loadCurrentKpi();
                }
            });

            // ─── ROLEPLAY phase ───────────────────────────────────────────────────────────
            async function startRoleplay() {
                // Show KPI chips
                const chips = $("roleplay-kpi-chips");
                chips.innerHTML = "";
                chunkKpis.forEach((k) => {
                    const span = document.createElement("span");
                    span.className = "roleplay-kpi-chip";
                    span.textContent = k.code;
                    chips.appendChild(span);
                });

                $("roleplay-scenario-text").textContent =
                    "Generating your scenario…";
                $("roleplay-role-tag").textContent = "";
                $("roleplay-textarea").value = "";
                updateWordCount();
                $("roleplay-submit").disabled = true;
                showState("roleplay");

                try {
                    const res = await apiFetch("/api/learn/roleplay-prompt", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            event_id: currentEventId,
                            kpis: chunkKpis.map((k) => ({
                                code: k.code,
                                text: k.text,
                                cluster: k.cluster,
                            })),
                        }),
                    });
                    const data = await res.json();
                    if (!res.ok || data.error) {
                        $("roleplay-scenario-text").textContent =
                            "Could not load scenario. Try typing a general DECA finance roleplay response.";
                    } else {
                        $("roleplay-scenario-text").textContent =
                            data.scenario || "";
                        $("roleplay-role-tag").textContent = data.role
                            ? "Your role: " + data.role
                            : "";
                    }
                } catch (e) {
                    $("roleplay-scenario-text").textContent =
                        "Network error loading scenario. Write a general response about the KPIs above.";
                }
            }

            $("roleplay-textarea").addEventListener("input", updateWordCount);

            function updateWordCount() {
                const words = (
                    $("roleplay-textarea").value.trim().match(/\S+/g) || []
                ).length;
                const el = $("roleplay-word-count");
                el.textContent = words + " words";
                el.className =
                    "roleplay-word-count" + (words >= 80 ? " ok" : "");
                $("roleplay-submit").disabled = words < 30;
            }

            $("roleplay-submit").addEventListener("click", submitRoleplay);

            async function submitRoleplay() {
                const responseText = $("roleplay-textarea").value.trim();
                const scenario = $("roleplay-scenario-text").textContent;
                showState("grading");

                try {
                    const res = await apiFetch("/api/learn/grade", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            event_id: currentEventId,
                            session_id: sessionId,
                            scenario,
                            response: responseText,
                            kpis: chunkKpis.map((k) => ({
                                code: k.code,
                                text: k.text,
                            })),
                        }),
                    });
                    const data = await res.json();
                    if (!res.ok || data.error) {
                        showError(
                            "Grading failed: " +
                                (data.error || "Unknown error"),
                        );
                        return;
                    }
                    showGradeResult(data);
                } catch (e) {
                    showError("Network error during grading: " + e.message);
                }
            }

            function showGradeResult(data) {
                sessionRoleplayScore = data.score || null;
                const score = data.score || 0;
                const circle = $("grade-circle");
                circle.textContent = score;
                circle.className =
                    "grade-circle " +
                    (score >= 8 ? "high" : score >= 5 ? "mid" : "low");

                $("grade-letter").textContent = data.grade || "—";
                $("grade-overall-inline").textContent = data.overall || "";

                const makeList = (ulId, items) => {
                    const ul = $(ulId);
                    ul.innerHTML = "";
                    (items || []).forEach((item) => {
                        const li = document.createElement("li");
                        li.textContent = item;
                        ul.appendChild(li);
                    });
                };
                makeList("grade-strengths", data.strengths || []);
                makeList("grade-improvements", data.improvements || []);

                const covList = $("kpi-coverage-list");
                covList.innerHTML = "";
                (data.kpi_coverage || []).forEach((cov) => {
                    const row = document.createElement("div");
                    row.className = "kpi-cov-row";
                    row.innerHTML =
                        `<span class="kpi-cov-code ${cov.addressed ? "yes" : "no"}">${escHtml(cov.code || "")} ${cov.addressed ? "✓" : "✗"}</span>` +
                        `<span class="kpi-cov-note">${escHtml(cov.note || "")}</span>`;
                    covList.appendChild(row);
                });

                showState("grade-result");
            }

            $("grade-continue").addEventListener("click", () => {
                chunkKpis = []; // reset chunk
                if (sessionIdx >= sessionQueue.length) {
                    showDone();
                } else {
                    loadCurrentKpi();
                }
            });

            // ─── Done ─────────────────────────────────────────────────────────────────────
            async function showDone() {
                $("skip-kpi-btn").style.display = "none";
                $("progress-fill").style.width = "100%";
                try {
                    await endSession();
                    showSummary();
                } catch (error) {
                    showError("Your session could not be saved. Check your connection and try again.");
                }
            }
            $("done-restart").addEventListener("click", startSession);
            $("done-home").addEventListener("click", () => {
                viewSession.style.display = "none";
                viewHome.style.display = "block";
                renderLearnHome();
            });

            // ─── Exit ─────────────────────────────────────────────────────────────────────
            $("session-exit").addEventListener("click", async () => {
                if (
                    !confirm(
                        "Exit session? Your question mastery is already saved.",
                    )
                )
                    return;
                if (sessionStartTime) {
                    try {
                        await endSession();
                    } catch (error) {
                        showError("Your session could not be saved, so it remains open. Please retry.");
                        return;
                    }
                    sessionStartTime = null;
                }
                viewSession.style.display = "none";
                viewHome.style.display = "";
                initMasteryDashboard(currentEventId);
                renderLearnHome();
            });

            // ─── Error ────────────────────────────────────────────────────────────────────
            function showError(msg) {
                $("error-msg").textContent = msg;
                showState("error");
            }
            $("retry-btn").addEventListener("click", loadCurrentKpi);
            $("error-skip-btn").addEventListener("click", skipCurrentKpi);

            // ─── State machine ────────────────────────────────────────────────────────────
            const ALL_STATES = [
                "loading",
                "error",
                "mission",
                "vocab",
                "concept",
                "questions",
                "kpi-feedback",
                "roleplay",
                "grading",
                "grade-result",
                "summary",
                "done",
            ];

            function showState(name) {
                ALL_STATES.forEach((s) => {
                    const el = $("state-" + s);
                    if (el) el.style.display = s === name ? "block" : "none";
                });
            }

            function setPhase(name, status) {
                // status: 'pending' | 'active' | 'done'
                const pill = $("pp-" + name);
                if (!pill) return;
                pill.className =
                    "phase-pill" +
                    (status === "active"
                        ? " active"
                        : status === "done"
                          ? " done"
                          : "");
            }

            // ─── Question bank (localStorage) ─────────────────────────────────────────────
            function getQBank(eventId, code) {
                try {
                    const cached = JSON.parse(localStorage.getItem(`ct_qb_${eventId}_${code}`));
                    return cached && cached.lesson_version === LESSON_VERSION ? cached : null;
                } catch (e) {
                    return null;
                }
            }

            function skipCurrentKpi() {
                if (isReviewMode || sessionIdx >= sessionQueue.length) return;
                kpiLoadToken++;
                sessionIdx++;
                setPhase("mission", "pending");
                setPhase("vocab", "pending");
                setPhase("concept", "pending");
                setPhase("questions", "pending");
                loadCurrentKpi();
            }

            $("skip-kpi-btn").addEventListener("click", skipCurrentKpi);
            function saveQBank(eventId, code, data) {
                try {
                    localStorage.setItem(`ct_qb_${eventId}_${code}`, JSON.stringify({...data, lesson_version: LESSON_VERSION}));
                } catch (e) {}
            }
            function getCorrectQs() {
                try {
                    return new Set(
                        JSON.parse(
                            localStorage.getItem("ct_correct_qs") || "[]",
                        ),
                    );
                } catch (e) {
                    return new Set();
                }
            }
            function saveCorrectQ(id) {
                const s = getCorrectQs();
                s.add(id);
                try {
                    localStorage.setItem(
                        "ct_correct_qs",
                        JSON.stringify([...s]),
                    );
                } catch (e) {}
            }

            // ─── Utilities ────────────────────────────────────────────────────────────────
            function shuffle(arr) {
                const a = [...arr];
                for (let i = a.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [a[i], a[j]] = [a[j], a[i]];
                }
                return a;
            }

            function escHtml(s) {
                return String(s)
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;");
            }

            // ─── Mastery Dashboard ────────────────────────────────────────────────────────────────────────────────
            async function initMasteryDashboard(eventId) {
                try {
                    const url =
                        "/api/learn/analytics" +
                        (eventId
                            ? "?event_id=" + encodeURIComponent(eventId)
                            : "");
                    const res = await apiFetch(url);
                    if (!res.ok) return;
                    const data = await res.json();
                    analyticsData = data;
                    renderMasteryDashboard(data);
                } catch (e) {
                    // non-critical — silently ignore
                }
            }

            function renderMasteryDashboard(data) {
                const sum = data.summary || {};
                const learned = Number(sum.completed_kpis || 0);
                const avgMastery = Number(sum.avg_mastery || 0);
                $("m-mastery").textContent = learned && avgMastery ? `${Math.round(avgMastery)}%` : "No data";
                $("mastery-context").textContent = learned ? `Based on ${learned} completed Learn KPI${learned === 1 ? "" : "s"}.` : "Complete a current Learn lesson to begin measuring retention.";
                const qtd = data.question_type_breakdown || {};
                const recog = qtd.recognition;
                const app = qtd.application;
                const cards = [];
                if (learned && recog?.total) cards.push(`<div><span>Recognition</span><strong>${Math.round(recog.accuracy)}%</strong><small>${recog.total} attempts</small></div>`);
                if (learned && app?.total) cards.push(`<div><span>Application</span><strong>${Math.round(app.accuracy)}%</strong><small>${app.total} attempts</small></div>`);
                $("type-breakdown-section").innerHTML = cards.join("");

                renderLearnHome();
            }

            function renderHeatmap(daily) {
                const container = $("activity-heatmap");
                container.innerHTML = "";
                const dateMap = {};
                daily.forEach((d) => {
                    dateMap[d.activity_date] =
                        (d.questions_answered || 0) + (d.kpis_studied || 0);
                });
                const today = new Date();
                for (let i = 29; i >= 0; i--) {
                    const d = new Date(today);
                    d.setDate(d.getDate() - i);
                    const iso = d.toISOString().slice(0, 10);
                    const val = dateMap[iso] || 0;
                    const cell = document.createElement("div");
                    cell.className =
                        "hmap-day" +
                        (val >= 20
                            ? " high"
                            : val >= 5
                              ? " mid"
                              : val > 0
                                ? " low"
                                : "");
                    cell.title = iso + ": " + val + " activities";
                    container.appendChild(cell);
                }
            }

            // ─── Review Mode ────────────────────────────────────────────────────────────────────────────────────
            async function startReview() {
                isReviewMode = true;
                $("skip-kpi-btn").style.display = "none";
                sessionQAnswered = 0;
                sessionQCorrect = 0;
                sessionVocabTotal = 0;
                sessionVocabCorrect = 0;
                sessionRoleplayScore = null;
                sessionStartTime = Date.now();
                sessionId = null;

                viewHome.style.display = "none";
                viewSession.style.display = "block";

                // Hide phase pills in review mode
                const pillsEl = document.querySelector(".phase-pills");
                if (pillsEl) pillsEl.style.visibility = "hidden";

                $("sess-cluster-name").textContent = "Review Mode";
                $("loading-kpi-text").textContent =
                    "Loading due questions\u2026";
                showState("loading");

                try {
                    const response = await apiFetch("/api/learn/session/start", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({event_id: currentEventId, session_type: "review"}),
                    });
                    const data = await response.json().catch(() => ({}));
                    sessionId = response.ok ? data.session_id || null : null;
                } catch (error) {
                    sessionId = null;
                }
                if (!sessionId) {
                    showError("The review session could not be saved. Check your connection and try again.");
                    return;
                }

                try {
                    const url =
                        "/api/learn/due" +
                        (currentEventId
                            ? "?event_id=" + encodeURIComponent(currentEventId)
                            : "");
                    const res = await apiFetch(url);
                    if (!res.ok) throw new Error("HTTP " + res.status);
                    const data = await res.json();
                    qShown = shuffle(data.questions || []);
                } catch (e) {
                    showError("Could not load review questions: " + e.message);
                    return;
                }

                if (!qShown.length) {
                    showError(
                        "No questions are due for review right now. Great job keeping up!",
                    );
                    return;
                }

                qIdx = 0;
                $("prog-total").textContent = qShown.length;
                $("prog-current").textContent = "1";
                $("progress-fill").style.width = "0%";
                $("qs-total").textContent = qShown.length;
                showQuestion();
                showState("questions");
            }

            // ─── Session end + post-session analytics ────────────────────────────────────────────────────
            async function endSession() {
                if (!sessionStartTime) return;
                const duration = Math.round((Date.now() - sessionStartTime) / 1000);
                const kpisStudied = isReviewMode ? 0 : completedKpiCodes.size;

                if (sessionId) {
                    const response = await apiFetch("/api/learn/session/end", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            session_id: sessionId,
                            kpis_studied: kpisStudied,
                            questions_answered: sessionQAnswered,
                            questions_correct: sessionQCorrect,
                            vocab_total: sessionVocabTotal,
                            vocab_correct: sessionVocabCorrect,
                            roleplay_score: sessionRoleplayScore,
                            duration_seconds: duration,
                            ar_answers: sessionArAnswers,
                            recog_answered: sessionRecogAnswered,
                            recog_correct: sessionRecogCorrect,
                            app_answered: sessionAppAnswered,
                            app_correct: sessionAppCorrect,
                            learn_mode: currentLearnMode,
                        }),
                    });
                    if (!response.ok) {
                        const detail = await response.json().catch(() => ({}));
                        throw new Error(detail.error || "Session persistence failed");
                    }
                    const savedSession = await response.json();
                    sessionQAnswered = Number(savedSession.questions_answered ?? sessionQAnswered);
                    sessionQCorrect = Number(savedSession.questions_correct ?? sessionQCorrect);
                }

                // Refresh analytics
                try {
                    const url = "/api/learn/analytics" +
                        (currentEventId ? "?event_id=" + encodeURIComponent(currentEventId) : "");
                    const r = await apiFetch(url);
                    if (r.ok) analyticsData = await r.json();
                } catch (e) {}
            }

            function showSummary() {
                const acc = sessionQAnswered > 0
                    ? Math.round((sessionQCorrect / sessionQAnswered) * 100) : 0;
                const duration = sessionStartTime
                    ? Math.round((Date.now() - sessionStartTime) / 1000) : 0;
                const minutes = Math.round(duration / 60);
                const kpisStudied = isReviewMode ? 0 : completedKpiCodes.size;

                $("sum-accuracy").textContent = acc + "%";
                $("sum-q-breakdown").textContent = sessionQCorrect + " / " + sessionQAnswered + " correct";
                $("sum-time").textContent = minutes + "m";
                $("sum-kpis").textContent = kpisStudied;
                $("sum-vocab-line").textContent = isReviewMode
                    ? "review session"
                    : sessionVocabTotal > 0
                        ? sessionVocabCorrect + "/" + sessionVocabTotal + " vocab correct"
                        : "vocab cards";

                const streak = analyticsData ? (analyticsData.summary || {}).streak_days || 0 : 0;
                $("sum-streak").textContent = streak;

                // ── Recognition vs Application accuracy breakdown ──────────────────────
                const gainsContainer = $("sum-kpi-gains");
                gainsContainer.innerHTML = "";
                const gainsLabel = $("sum-gains-label");

                if (sessionRecogAnswered > 0 || sessionAppAnswered > 0) {
                    const recogAcc = sessionRecogAnswered > 0
                        ? Math.round(sessionRecogCorrect / sessionRecogAnswered * 100) : null;
                    const appAcc = sessionAppAnswered > 0
                        ? Math.round(sessionAppCorrect / sessionAppAnswered * 100) : null;

                    const typeRow = document.createElement("div");
                    typeRow.style.cssText = "display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap;";
                    if (recogAcc !== null) {
                        typeRow.innerHTML += `<div style="flex:1;min-width:120px;padding:10px 14px;border:1px solid var(--border);border-radius:8px;background:rgba(17,41,41,0.3)">
                            <div style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Recognition</div>
                            <div style="font-size:1.4rem;font-weight:900;font-family:'Barlow Condensed',sans-serif;color:var(--white)">${recogAcc}%</div>
                            <div style="font-size:0.72rem;color:var(--muted)">${sessionRecogCorrect}/${sessionRecogAnswered} correct</div>
                        </div>`;
                    }
                    if (appAcc !== null) {
                        typeRow.innerHTML += `<div style="flex:1;min-width:120px;padding:10px 14px;border:1px solid var(--border);border-radius:8px;background:rgba(17,41,41,0.3)">
                            <div style="font-size:0.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Application</div>
                            <div style="font-size:1.4rem;font-weight:900;font-family:'Barlow Condensed',sans-serif;color:${appAcc >= 70 ? 'var(--green)' : 'var(--yellow)'}">${appAcc}%</div>
                            <div style="font-size:0.72rem;color:var(--muted)">${sessionAppCorrect}/${sessionAppAnswered} correct</div>
                        </div>`;
                    }
                    gainsContainer.appendChild(typeRow);
                }

                // ── Per-KPI mastery gains ─────────────────────────────────────────────
                if (!isReviewMode && analyticsData && analyticsData.kpi_mastery && completedKpiCodes.size > 0) {
                    gainsLabel.style.display = "";
                    // Also show next review recommendation for weakest KPI
                    const studied = sessionQueue.filter((kpi) => completedKpiCodes.has(kpi.code));
                    let weakestKpi = null, weakestScore = 101;
                    studied.forEach((kpi) => {
                        const newMastery = analyticsData.kpi_mastery.find(m => m.kpi_code === kpi.code);
                        const newScore = newMastery ? Math.round(newMastery.mastery_score || 0) : 0;
                        const oldScore = Math.round(preMasteryMap[kpi.code] || 0);
                        const delta = newScore - oldScore;
                        const row = document.createElement("div");
                        row.className = "kpi-gain-row";
                        row.innerHTML =
                            `<span class="kpi-gain-code">${escHtml(kpi.code)}</span>` +
                            `<div class="kpi-gain-track"><div class="kpi-gain-fill" style="width:${newScore}%"></div></div>` +
                            `<span class="kpi-gain-pct">${newScore}%</span>` +
                            `<span class="kpi-gain-delta ${delta > 0 ? "pos" : delta < 0 ? "neg" : ""}">${delta > 0 ? "+" : ""}${delta}%</span>`;
                        gainsContainer.appendChild(row);
                        if (newScore < weakestScore) { weakestScore = newScore; weakestKpi = kpi; }
                    });

                    // Next review hint for weakest KPI
                    if (weakestKpi && weakestScore < 80) {
                        const hint = document.createElement("div");
                        hint.style.cssText = "margin-top:12px;padding:10px 14px;border:1px solid var(--border2);border-radius:8px;font-size:0.82rem;color:var(--muted);";
                        hint.innerHTML = `📅 <strong style="color:var(--white)">${escHtml(weakestKpi.code)}</strong> needs more work (${weakestScore}% mastery). It's scheduled for review via spaced repetition.`;
                        gainsContainer.appendChild(hint);
                    }
                } else {
                    gainsLabel.style.display = "none";
                }

                showState("summary");
            }

            // ─── Summary button wiring ────────────────────────────────────────────────────────────────────────────
            // Wire all possible review button IDs (template uses review-summary-btn)
            ["review-btn", "review-summary-btn"].forEach(id => {
                const btn = $(id);
                if (btn) btn.addEventListener("click", startReview);
            });

            $("sum-go-home").addEventListener("click", () => {
                viewSession.style.display = "none";
                viewHome.style.display = "";
                initMasteryDashboard(currentEventId);
                renderLearnHome();
            });

            $("sum-study-again").addEventListener("click", () => {
                if (!allKpis.length) return;
                startSession();
            });
