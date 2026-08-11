            // ─── Constants ────────────────────────────────────────────────────────────────
            const QUESTIONS_PER_KPI = 5;
            const ROLEPLAY_EVERY = 7; // show a mini roleplay every N KPIs (standard/tdm only)

            // ─── State ────────────────────────────────────────────────────────────────────
            let allKpis = []; // all KPIs for the user's event (in order)
            let sessionQueue = []; // KPIs for this session (same as allKpis initially)
            let sessionIdx = 0; // current position in sessionQueue
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
            let currentLearnMode = "standard"; // 'standard'|'examOnly'|'activeRecall'|'principles'
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
            let isActiveRecallMode = false;
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

                const matches = allKpis.filter((k) => {
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
                    row.innerHTML =
                        `<strong>${escHtml(kpi.code || "")}</strong>` +
                        `<span>${escHtml(kpi.text || "")}</span>` +
                        `<small>${escHtml(kpi.cluster || "")} · ${escHtml((kpi.learning_status || "unstarted").replace("_", " "))}</small>`;
                    row.addEventListener("click", () => focusSessionOnKpi(kpi));
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
                    empty.textContent = "Start a session to generate your next steps.";
                    list.appendChild(empty);
                    return;
                }

                source.forEach((item) => {
                    const btn = document.createElement("button");
                    btn.type = "button";
                    btn.className = "study-row";
                    btn.innerHTML =
                        `<span class="study-row-code">${escHtml(item.code || "")}</span>` +
                        `<span class="study-row-text">` +
                            `<strong>${escHtml(item.text || "")}</strong>` +
                        `</span>` +
                        `<span class="study-row-score">Learn</span>`;
                    btn.addEventListener("click", () => focusSessionOnKpi(item.code));
                    list.appendChild(btn);
                });
            }

            function renderLearnHome() {
                const startBtn = $("start-btn");
                if (startBtn) {
                    startBtn.textContent = allKpis.length
                        ? "Start Learning"
                        : "No topics available yet";
                    startBtn.disabled = !allKpis.length;
                }

                const dashSummary = $("dashboard-summary");
                if (dashSummary) {
                    dashSummary.style.display = "flex";
                    const sum = analyticsData && analyticsData.summary ? analyticsData.summary : null;
                    const mastery = sum ? Math.round(Number(sum.avg_mastery || 0)) : 0;
                    const due = Number(sum?.questions_due ?? kpiGroups.due.length ?? 0);
                    const streak = Number(sum?.streak_days || 0);
                    const mastered = Number(sum?.mastered_kpis || 0);
                    const learnedLabel = allKpis.length ? `${Math.min(100, Math.round((mastered / allKpis.length) * 100))}%` : "--";
                    $("dash-mastery").textContent = mastery ? `${mastery}%` : learnedLabel;
                    $("dash-due").textContent = due;
                    $("dash-streak").textContent = streak ? `${streak}d` : "0d";
                }

                renderRecommendedPath();
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
                        btn.textContent = "No topics available yet";
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
                // Wire all mode buttons
                const modeButtons = document.querySelectorAll('.mode-btn');
                modeButtons.forEach(btn => {
                    btn.addEventListener('click', () => {
                        modeButtons.forEach(b => b.classList.remove('active'));
                        btn.classList.add('active');
                    });
                });

                // For principles events, default to principles mode and hide roleplay-related modes
                if (eventType === 'principles') {
                    modeButtons.forEach(b => {
                        const mode = b.dataset.learnMode;
                        if (mode === 'principles') {
                            b.classList.add('active');
                        } else if (mode === 'standard' || mode === 'teamDecision') {
                            b.classList.remove('active');
                        }
                    });
                    // Activate principles mode by default
                    const principlesBtn = document.querySelector('[data-learn-mode="principles"]');
                    if (principlesBtn) {
                        modeButtons.forEach(b => b.classList.remove('active'));
                        principlesBtn.classList.add('active');
                    }
                } else if (eventType === 'exam') {
                    // Exam events: default to examOnly
                    const examBtn = document.querySelector('[data-learn-mode="examOnly"]');
                    if (examBtn) {
                        modeButtons.forEach(b => b.classList.remove('active'));
                        examBtn.classList.add('active');
                    }
                }
                // tdm/series/operations: standard mode is fine as default
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

                // Determine learn mode from active button, falling back to event type
                const modeBtn = document.querySelector('.mode-btn.active');
                currentLearnMode = (modeBtn && modeBtn.dataset.learnMode) || 'standard';

                // Override with event type if no explicit mode chosen
                if (currentLearnMode === 'standard') {
                    if (currentEventType === 'principles') currentLearnMode = 'principles';
                    else if (currentEventType === 'exam') currentLearnMode = 'examOnly';
                }

                isActiveRecallMode = currentLearnMode === 'activeRecall';

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
                updateProgress();
                qAnswered = false;
                sessionData = null;

                $("loading-kpi-text").textContent = kpi.code + " — " + kpi.text;
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
                        const data = await res.json();
                        if (!res.ok || data.error) {
                            showError(data.error || "Groq failed.");
                            return;
                        }

                        // Preserve server UUID; fall back to local id for offline cache
                        (data.questions || []).forEach((q, i) => {
                            if (!q.id) q.id = kpi.code + "_" + i;
                        });
                        saveQBank(kpi.event, kpi.code, data);
                        sessionData = data;
                    } catch (e) {
                        showError("Network error: " + e.message);
                        return;
                    }
                }

                if (isActiveRecallMode) {
                    startActiveRecall(kpi);
                } else if (currentLearnMode === 'examOnly') {
                    // Exam Only: skip vocab and concept, go straight to questions
                    setPhase("vocab", "done");
                    setPhase("concept", "done");
                    startQuestions(kpi);
                } else if (currentLearnMode === 'principles') {
                    // Principles: vocab → concept → application question only (no roleplay)
                    startVocab(kpi);
                } else {
                    // Standard / TDM: full flow (vocab → concept → questions → roleplay every 7)
                    startVocab(kpi);
                }
            }

            // ─── Active Recall flow ───────────────────────────────────────────────────
            function startActiveRecall(kpi) {
                $("ar-code").textContent = kpi.code;
                $("ar-kpi-text").textContent = kpi.text;
                $("active-recall-text").value = "";
                $("active-recall-model").style.display = "none";
                $("active-recall-reveal").style.display = "none";
                $("active-recall-submit").disabled = false;

                // Remove any old continue button
                const oldContinue = document.getElementById("ar-continue-btn");
                if (oldContinue) oldContinue.remove();

                showState("active-recall");

                $("active-recall-submit").onclick = () => {
                    const answer = $("active-recall-text").value.trim();
                    sessionArAnswers.push({
                        kpi_code: kpi.code,
                        kpi_text: kpi.text,
                        answer,
                        timestamp: new Date().toISOString(),
                    });
                    $("active-recall-submit").disabled = true;
                    $("active-recall-reveal").style.display = "";
                };

                $("active-recall-reveal").onclick = () => {
                    const c = sessionData?.concept || {};
                    $("ar-model-answer").textContent = c.explanation || "";
                    const bulletsEl = $("ar-model-bullets");
                    bulletsEl.innerHTML = "";
                    (c.bullets || []).forEach(b => {
                        const li = document.createElement("li");
                        li.textContent = b;
                        bulletsEl.appendChild(li);
                    });
                    $("active-recall-model").style.display = "block";
                    $("active-recall-reveal").style.display = "none";

                    // Add a continue button after reveal
                    const btn = document.createElement("button");
                    btn.id = "ar-continue-btn";
                    btn.className = "understand-btn";
                    btn.style.marginTop = "16px";
                    btn.textContent = "Continue to Questions →";
                    btn.onclick = () => {
                        btn.remove();
                        setPhase("concept", "done");
                        startQuestions(kpi);
                    };
                    $("active-recall-model").insertAdjacentElement("afterend", btn);
                };
            }

            // ─── VOCAB phase ──────────────────────────────────────────────────────────────
            function startVocab(kpi) {
                vocabList = sessionData.vocab || [];
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
                $("vocab-term").textContent = card.term;

                // Build 4 choices: 1 correct + 3 distractors from other vocab
                const others = vocabList.filter((_, i) => i !== vocabIdx);
                const distractors = shuffle(others).slice(0, 3);
                const choices = shuffle([
                    { text: card.definition, correct: true },
                    ...distractors.map((d) => ({
                        text: d.definition,
                        correct: false,
                    })),
                ]);

                const grid = $("vocab-grid");
                grid.innerHTML = "";
                choices.forEach((c, i) => {
                    const btn = document.createElement("button");
                    btn.className = "vchoice";
                    btn.type = "button";
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
                    // Find which button has the correct definition — re-derive from vocabList
                    const correctDef = vocabList[vocabIdx]?.definition || "";
                    allBtns.forEach((b) => {
                        if (
                            b.querySelector("span:last-child")?.textContent ===
                            correctDef
                        )
                            b.classList.add("correct");
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

            // ─── CONCEPT phase ────────────────────────────────────────────────────────────
            function startConcept(kpi) {
                setPhase("concept", "active");
                const c = sessionData.concept || {};

                $("concept-code").textContent = kpi.code;
                $("concept-cluster").textContent = kpi.cluster;
                $("concept-kpi-text").textContent = kpi.text;
                $("concept-summary").textContent = c.summary || "";
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

                // ── Concept check — locks "I understand" until answered ───────────────────
                // One question testing the core idea. Just enough to verify engagement.
                // If the model didn't generate one (older cache), fall through silently.
                const check = c.concept_check;
                const understandBtn = $("understand-btn");
                const checkContainer = $("concept-check-container");

                // Clear any leftover check from a previous KPI
                if (checkContainer) checkContainer.innerHTML = "";
                understandBtn.disabled = false;
                understandBtn.textContent = "I understand →";

                if (check && check.question && check.choices && check.choices.length === 4) {
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

                // Separate recognition from application questions
                const all = sessionData.questions || [];
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
                    // Standard / TDM / activeRecall — with adaptive weighting
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
                $("result-label").textContent = ok ? "Correct!" : "Incorrect";
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
                        qShown = shuffle(missed);
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
            function kpiDone() {
                chunkKpis.push(currentKpi());
                sessionIdx++;

                // Roleplay only for standard/TDM modes
                const roleplayEnabled = (currentLearnMode === 'standard' || currentLearnMode === 'teamDecision');
                if (roleplayEnabled && chunkKpis.length >= ROLEPLAY_EVERY) {
                    startRoleplay();
                } else {
                    loadCurrentKpi();
                }
            }

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

            // ─── State machine ────────────────────────────────────────────────────────────
            const ALL_STATES = [
                "loading",
                "error",
                "vocab",
                "active-recall",
                "concept",
                "questions",
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
                    return JSON.parse(localStorage.getItem(`ct_qb_${eventId}_${code}`));
                } catch (e) {
                    return null;
                }
            }
            function saveQBank(eventId, code, data) {
                try {
                    localStorage.setItem(`ct_qb_${eventId}_${code}`, JSON.stringify(data));
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
                const avgMastery = sum.avg_mastery || 0;
                const masteredKpis = sum.mastered_kpis || 0;
                const dueCount = sum.questions_due || 0;
                const streak = sum.streak_days || 0;
                const hasActivity = !!(
                    avgMastery > 0 ||
                    masteredKpis > 0 ||
                    dueCount > 0 ||
                    streak > 0
                );

                // Populate top dashboard summary
                const dashSummary = $("dashboard-summary");
                if (dashSummary) {
                    dashSummary.style.display = hasActivity ? "flex" : "none";
                    if (hasActivity) {
                        $("dash-mastery").textContent = avgMastery + "%";
                        $("dash-due").textContent = dueCount;
                        $("dash-streak").textContent = streak;
                    }
                }

                $("m-mastery").textContent = avgMastery + "%";
                $("m-mastery-bar").style.width = avgMastery + "%";
                $("m-streak").textContent = streak;
                $("m-mastered").textContent = masteredKpis;
                $("m-due").textContent = dueCount;
                $("mastery-summary-row").style.display = hasActivity ? "grid" : "none";

                // ── Question type breakdown ───────────────────────────────────────────
                const qtd = data.question_type_breakdown || {};
                const recog = qtd.recognition;
                const app = qtd.application;
                if (recog && app && (recog.total > 0 || app.total > 0)) {
                    let typeBreakdownEl = $("type-breakdown-section");
                    if (!typeBreakdownEl) {
                        typeBreakdownEl = document.createElement("div");
                        typeBreakdownEl.id = "type-breakdown-section";
                        typeBreakdownEl.style.cssText = "display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap;";
                        const masteryRow = $("mastery-summary-row");
                        if (masteryRow && masteryRow.parentNode) {
                            masteryRow.parentNode.insertBefore(typeBreakdownEl, masteryRow.nextSibling);
                        }
                    }
                    typeBreakdownEl.innerHTML = "";
                    const makeTypeCard = (label, acc, total) => {
                        const color = acc >= 80 ? "var(--green)" : acc >= 60 ? "var(--yellow)" : "var(--red)";
                        return `<div style="flex:1;min-width:110px;padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:rgba(17,41,41,0.3)">
                            <div style="font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:3px">${label}</div>
                            <div style="font-size:1.3rem;font-weight:900;font-family:'Barlow Condensed',sans-serif;color:${color}">${acc}%</div>
                            <div style="font-size:0.68rem;color:var(--muted)">${total} attempts</div>
                        </div>`;
                    };
                    if (recog.total > 0) typeBreakdownEl.innerHTML += makeTypeCard("Recognition", Math.round(recog.accuracy), recog.total);
                    if (app.total > 0) typeBreakdownEl.innerHTML += makeTypeCard("Application", Math.round(app.accuracy), app.total);
                    typeBreakdownEl.style.display = "flex";
                }

                // Cluster breakdown bars
                const clusterBreakdown = data.cluster_breakdown || [];
                if (clusterBreakdown.length) {
                    const container = $("cluster-bars");
                    container.innerHTML = "";
                    clusterBreakdown.forEach((c) => {
                        const pct = Math.round(c.avg_mastery || 0);
                        const color =
                            pct >= 80
                                ? "var(--green)"
                                : pct >= 50
                                  ? "var(--cyan)"
                                  : "var(--yellow)";
                        const row = document.createElement("div");
                        row.className = "cluster-bar-row";
                        row.innerHTML =
                            `<span class="cluster-bar-name">${escHtml(c.cluster)}</span>` +
                            `<div class="cluster-bar-track"><div class="cluster-bar-fill" style="width:${pct}%;background:${color}"></div></div>` +
                            `<span class="cluster-bar-pct">${pct}%</span>`;
                        container.appendChild(row);
                    });
                    $("cluster-breakdown-section").style.display = "";
                }

                // Weak KPIs
                const weak = data.weak_kpis || [];
                if (weak.length) {
                    const container = $("weak-kpis-list");
                    container.innerHTML = "";
                    weak.forEach((k) => {
                        const score = Math.round(k.mastery_score || 0);
                        const row = document.createElement("div");
                        row.className = "weak-kpi-row";
                        row.innerHTML =
                            `<span class="weak-kpi-code">${escHtml(k.kpi_code || "")}</span>` +
                            `<span class="weak-kpi-text">${escHtml(k.kpi_text || k.kpi_code || "")}</span>` +
                            `<span class="weak-kpi-score">${score}%</span>`;
                        container.appendChild(row);
                    });
                    $("weak-kpis-section").style.display = "";
                }

                // Activity heatmap
                const daily = data.daily_activity || [];
                if (daily.length) {
                    renderHeatmap(daily);
                    $("heatmap-section").style.display = "";
                }

                // Review button
                if (dueCount > 0) {
                    // template uses id="due-summary-count" and id="review-summary-btn"
                    const dueCntEl = $("due-summary-count") || $("due-count");
                    if (dueCntEl) dueCntEl.textContent = dueCount;
                    const reviewBtnEl = $("review-summary-btn") || $("review-btn");
                    if (reviewBtnEl) reviewBtnEl.style.display = "";
                } else {
                    const reviewBtnEl = $("review-summary-btn") || $("review-btn");
                    if (reviewBtnEl) reviewBtnEl.style.display = "none";
                }

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
                const kpisStudied = isReviewMode ? 0 : sessionIdx;

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
                const kpisStudied = isReviewMode ? 0 : sessionIdx;

                $("sum-accuracy").textContent = acc + "%";
                $("sum-q-breakdown").textContent = sessionQCorrect + " / " + sessionQAnswered + " correct";
                $("sum-time").textContent = minutes + "m";
                $("sum-kpis").textContent = kpisStudied || qShown.length;
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
                if (!isReviewMode && analyticsData && analyticsData.kpi_mastery && sessionIdx > 0) {
                    gainsLabel.style.display = "";
                    // Also show next review recommendation for weakest KPI
                    const studied = sessionQueue.slice(0, sessionIdx);
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
