            // ─── Constants ────────────────────────────────────────────────────────────────
            const QUESTIONS_PER_KPI = 5;
            const ROLEPLAY_EVERY = 7; // show a mini roleplay every N KPIs

            // ─── State ────────────────────────────────────────────────────────────────────
            let allKpis = []; // all KPIs for the user's event (in order)
            let sessionQueue = []; // KPIs for this session (same as allKpis initially)
            let sessionIdx = 0; // current position in sessionQueue
            let sessionData = null; // current KPI's Groq response {vocab,concept,questions}
            let vocabList = [];
            let vocabIdx = 0;
            let qShown = []; // 5 questions chosen for this KPI
            let missed = []; // questions answered wrong this round
            let qIdx = 0; // which of the 5 we're on
            let qAnswered = false;
            let chunkKpis = []; // KPIs studied in the current chunk of ROLEPLAY_EVERY

            // Session tracking
            let currentEventId = "";
            let currentEvent = null;
            let currentLearnMode = "standard";
            let sessionId = null;
            let sessionStartTime = null;
            let sessionQAnswered = 0;
            let sessionQCorrect = 0;
            let sessionVocabTotal = 0;
            let sessionVocabCorrect = 0;
            let sessionRoleplayScore = null;
            let sessionArAnswers = []; // Track active-recall answers
            let preMasteryMap = {};
            let analyticsData = null;
            let isReviewMode = false;
            let savedConcepts = [];
            let savedNotes = [];
            let isActiveRecallMode = false;

            // ─── DOM helpers ──────────────────────────────────────────────────────────────
            const $ = (id) => document.getElementById(id);
            const viewHome = $("view-home");
            const viewSession = $("view-session");

            // ─── Auth ─────────────────────────────────────────────────────────────────────
            requireAuth().then((user) => {
                if (user) {
                    initTopbar(user);
                    initLearn();
                    // show admin panel if admin
                    try {
                        const adminPanel = document.getElementById('admin-tools-panel');
                        if (adminPanel) {
                            adminPanel.classList.toggle('hidden', !isAdminEmail(user && user.email));
                        }
                    } catch (e) {}
                }
            });

            // ─── Init: load event + KPIs ──────────────────────────────────────────────────
            async function initLearn() {
                let savedName = "";
                try {
                    savedName = localStorage.getItem("ct_selected_event") || "";
                } catch (e) {}

                try {
                    const res = await apiFetch("/api/kpis");
                    const data = await res.json();
                    const events = data.events || [];
                    const kpis = data.kpis || [];

                    const ev =
                        events.find((e) => e.name === savedName) ||
                        events[0] ||
                        null;
                    if (!ev) {
                        $("event-header-name").textContent =
                            "No event found — go through the opening screen first.";
                        return;
                    }

                    const color = clusterColor(ev.cluster || "");
                    $("event-header-card").style.setProperty(
                        "--ev-color",
                        color,
                    );
                    $("event-header-name").textContent = ev.name;
                    $("event-header-cluster").textContent = ev.cluster || "";

                    currentEventId = ev.id || "";
                    allKpis = kpis.filter((k) => k.event === ev.id);

                    const btn = $("start-btn");
                    if (allKpis.length) {
                        btn.textContent = `Start Learning — ${allKpis.length} KPIs`;
                        btn.disabled = false;
                    } else {
                        btn.textContent =
                            "No KPIs available for this event yet";
                    }

                    // Load mastery dashboard asynchronously (non-blocking)
                    initMasteryDashboard(currentEventId);

                    // Wire mode buttons
                    const modeButtons = document.querySelectorAll('.mode-btn');
                    modeButtons.forEach(btn => {
                        btn.addEventListener('click', () => {
                            modeButtons.forEach(b => b.classList.remove('active'));
                            btn.classList.add('active');
                        });
                    });
                } catch (e) {
                    $("event-header-name").textContent =
                        "Failed to load — please refresh.";
                }
            }

            $("start-btn").addEventListener("click", () => {
                if (!allKpis.length) return;
                startSession();
            });

            // ─── Session start ────────────────────────────────────────────────────────────
            function startSession() {
                sessionQueue = [...allKpis];
                sessionIdx = 0;
                chunkKpis = [];
                isReviewMode = false;
                sessionQAnswered = 0;
                sessionQCorrect = 0;
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

                // Start server session record (non-blocking)
                apiFetch("/api/learn/session/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        event_id: currentEventId,
                        session_type: "full",
                    }),
                })
                    .then((r) => r.json())
                    .then((d) => {
                        sessionId = d.session_id || null;
                    })
                    .catch(() => {});

                currentLearnMode = 'standard';
                // Check which mode button is active
                const modeBtn = document.querySelector('.mode-btn.active');
                if (modeBtn && modeBtn.dataset.learnMode) {
                    currentLearnMode = modeBtn.dataset.learnMode;
                }
                isActiveRecallMode = currentLearnMode === 'activeRecall';

                viewHome.style.display = "none";
                viewSession.style.display = "block";
                document.querySelector(".phase-pills").style.visibility =
                    "visible";

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
                const cached = getQBank(kpi.code);
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
                        saveQBank(kpi.code, data);
                        sessionData = data;
                    } catch (e) {
                        showError("Network error: " + e.message);
                        return;
                    }
                }

                if (isActiveRecallMode) {
                    startActiveRecall(kpi);
                } else {
                    startVocab(kpi);
                }
            }

            // ─── Active Recall flow ───────────────────────────────────────────────────
            function startActiveRecall(kpi) {
                // populate active recall UI
                $("ar-code").textContent = kpi.code;
                $("ar-kpi-text").textContent = kpi.text;
                $("active-recall-text").value = "";
                $("active-recall-model").style.display = "none";
                $("active-recall-reveal").style.display = "none";
                $("active-recall-submit").disabled = false;
                showState("active-recall");

                // wire up submit/reveal
                $("active-recall-submit").onclick = () => {
                    const answer = $("active-recall-text").value.trim();
                    // Record AR answer to session state
                    sessionArAnswers.push({
                        kpi_code: kpi.code,
                        kpi_text: kpi.text,
                        answer: answer,
                        timestamp: new Date().toISOString(),
                    });
                    $("active-recall-submit").disabled = true;
                    $("active-recall-reveal").style.display = "";
                };

                $("active-recall-reveal").onclick = () => {
                    // reveal model answer from sessionData.concept
                    const c = sessionData?.concept || {};
                    $("ar-model-answer").textContent = c.explanation || "";
                    const bulletsEl = $("ar-model-bullets");
                    bulletsEl.innerHTML = "";
                    (c.bullets || []).forEach(b => {
                        const li = document.createElement('li'); li.textContent = b; bulletsEl.appendChild(li);
                    });
                    $("active-recall-model").style.display = "block";
                    // after reveal, let user continue to concept/questions
                    // show the understand button below concept when they click it
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

                showState("concept");
            }

            $("understand-btn").addEventListener("click", () => {
                setPhase("concept", "done");
                startQuestions(currentKpi());
            });

            // ─── QUESTIONS phase ──────────────────────────────────────────────────────────
            function startQuestions(kpi) {
                setPhase("questions", "active");
                missed = []; // reset retry queue for this KPI
                const all = sessionData.questions || [];
                const done = getCorrectQs();
                const available = all.filter((q) => !done.has(q.id));

                if (!available.length) {
                    // All questions for this KPI mastered — skip straight to next
                    kpiDone();
                    return;
                }

                qShown = shuffle(available).slice(0, QUESTIONS_PER_KPI);
                qIdx = 0;
                $("qs-total").textContent = qShown.length;
                showQuestion();
                showState("questions");
            }

            function showQuestion() {
                const q = qShown[qIdx];
                $("qs-current").textContent = qIdx + 1;
                $("question-text").textContent = q.text;
                $("result-panel").style.display = "none";
                $("next-q-btn").style.display = "none";
                qAnswered = false;

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

            function handleQAnswer(chosen, q) {
                if (qAnswered) return;
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

                const ok = chosen === q.correct;
                if (ok) sessionQCorrect++;
                // Persist to localStorage (fast, offline)
                // Persist to localStorage (fast, offline)
                if (ok) saveCorrectQ(q.id);
                // Track wrong answers for end-of-set retry
                if (!ok) missed.push(q);
                // Persist to Supabase (cross-device, permanent)
                const sbId = q.id || "";
                if (sbId) {
                    const kpi = isReviewMode ? null : currentKpi();
                    apiFetch("/api/learn/answer", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            question_id: sbId,
                            correct: ok,
                            kpi_code: q.kpi_code || (kpi ? kpi.code : ""),
                            cluster: q.cluster || (kpi ? kpi.cluster : ""),
                            deca_cluster:
                                q.deca_cluster ||
                                (kpi ? kpi.deca_cluster || "" : ""),
                            event_id:
                                q.event_id || (kpi ? kpi.event || "" : ""),
                        }),
                    }).catch(() => {}); // fire-and-forget
                }

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

                if (chunkKpis.length >= ROLEPLAY_EVERY) {
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
            function showDone() {
                $("progress-fill").style.width = "100%";
                endSession().then(showSummary);
            }
            $("done-restart").addEventListener("click", startSession);
            $("done-home").addEventListener("click", () => {
                viewSession.style.display = "none";
                viewHome.style.display = "block";
            });

            // ─── Exit ─────────────────────────────────────────────────────────────────────
            $("session-exit").addEventListener("click", () => {
                if (
                    !confirm(
                        "Exit session? Your question mastery is already saved.",
                    )
                )
                    return;
                if (sessionStartTime) {
                    endSession().catch(() => {});
                    sessionStartTime = null;
                }
                viewSession.style.display = "none";
                viewHome.style.display = "";
                initMasteryDashboard(currentEventId);
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
            function getQBank(code) {
                try {
                    return JSON.parse(localStorage.getItem("ct_qb_" + code));
                } catch (e) {
                    return null;
                }
            }
            function saveQBank(code, data) {
                try {
                    localStorage.setItem("ct_qb_" + code, JSON.stringify(data));
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

                // Populate top dashboard summary
                const dashSummary = $("dashboard-summary");
                if (dashSummary) {
                    dashSummary.style.display = "flex";
                    $("dash-mastery").textContent = avgMastery + "%";
                    $("dash-due").textContent = dueCount;
                    $("dash-streak").textContent = streak;
                }

                $("m-mastery").textContent = avgMastery + "%";
                $("m-mastery-bar").style.width = avgMastery + "%";
                $("m-streak").textContent = streak;
                $("m-mastered").textContent = masteredKpis;
                $("m-due").textContent = dueCount;
                $("mastery-summary-row").style.display = "grid";

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
                            `<span class="weak-kpi-text">${escHtml(k.kpi_code || "")}</span>` +
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
                    $("due-count").textContent = dueCount;
                    $("review-btn").style.display = "";
                } else {
                    $("review-btn").style.display = "none";
                }
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

            // ─── Save concept handler ─────────────────────────────────────────────────
            (function wireSaveConcept() {
                document.addEventListener('DOMContentLoaded', () => {
                    const btn = document.getElementById('save-concept-btn');
                    if (!btn) return;
                    btn.addEventListener('click', () => {
                        try {
                            const code = (document.getElementById('concept-code')||{}).textContent || '';
                            const title = (document.getElementById('concept-kpi-text')||{}).textContent || '';
                            const summary = (document.getElementById('concept-summary')||{}).textContent || '';
                            const text = (document.getElementById('concept-explanation')||{}).textContent || '';
                            const bulletsEls = document.querySelectorAll('#concept-bullets li');
                            const bullets = [];
                            bulletsEls.forEach(li => bullets.push(li.textContent || ''));
                            const saved = JSON.parse(localStorage.getItem('ct_saved_concepts') || '[]');
                            saved.unshift({ code, title, summary, text, bullets, saved_at: Date.now() });
                            localStorage.setItem('ct_saved_concepts', JSON.stringify(saved.slice(0,200)));
                            // quick feedback
                            setOpeningStatus && setOpeningStatus('Concept saved locally.', 'info', 2000);
                        } catch (e) {
                            // ignore
                        }
                    });
                });
            })();

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

                // Start server session record (non-blocking)
                apiFetch("/api/learn/session/start", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        event_id: currentEventId,
                        session_type: "review",
                    }),
                })
                    .then((r) => r.json())
                    .then((d) => {
                        sessionId = d.session_id || null;
                    })
                    .catch(() => {});

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
                const duration = Math.round(
                    (Date.now() - sessionStartTime) / 1000,
                );
                const kpisStudied = isReviewMode ? 0 : sessionIdx;

                if (sessionId) {
                    try {
                        await apiFetch("/api/learn/session/end", {
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
                            }),
                        });
                    } catch (e) {}
                }

                // Refresh analytics for the summary panel
                try {
                    const url =
                        "/api/learn/analytics" +
                        (currentEventId
                            ? "?event_id=" + encodeURIComponent(currentEventId)
                            : "");
                    const r = await apiFetch(url);
                    if (r.ok) analyticsData = await r.json();
                } catch (e) {}
            }

            function showSummary() {
                const acc =
                    sessionQAnswered > 0
                        ? Math.round((sessionQCorrect / sessionQAnswered) * 100)
                        : 0;
                const duration = sessionStartTime
                    ? Math.round((Date.now() - sessionStartTime) / 1000)
                    : 0;
                const minutes = Math.round(duration / 60);
                const kpisStudied = isReviewMode ? 0 : sessionIdx;

                $("sum-accuracy").textContent = acc + "%";
                $("sum-q-breakdown").textContent =
                    sessionQCorrect + " / " + sessionQAnswered + " correct";
                $("sum-time").textContent = minutes + "m";
                $("sum-kpis").textContent = kpisStudied || qShown.length;
                $("sum-vocab-line").textContent = isReviewMode
                    ? "review session"
                    : sessionVocabTotal > 0
                      ? sessionVocabCorrect +
                        "/" +
                        sessionVocabTotal +
                        " vocab correct"
                      : "vocab cards";

                const streak = analyticsData
                    ? (analyticsData.summary || {}).streak_days || 0
                    : 0;
                $("sum-streak").textContent = streak;

                // KPI gain rows (only for full sessions, not review)
                const gainsContainer = $("sum-kpi-gains");
                gainsContainer.innerHTML = "";
                const gainsLabel = $("sum-gains-label");

                if (
                    !isReviewMode &&
                    analyticsData &&
                    analyticsData.kpi_mastery &&
                    sessionIdx > 0
                ) {
                    gainsLabel.style.display = "";
                    const studied = sessionQueue.slice(0, sessionIdx);
                    studied.forEach((kpi) => {
                        const newMastery = analyticsData.kpi_mastery.find(
                            (m) => m.kpi_code === kpi.code,
                        );
                        const newScore = newMastery
                            ? Math.round(newMastery.mastery_score || 0)
                            : 0;
                        const oldScore = Math.round(
                            preMasteryMap[kpi.code] || 0,
                        );
                        const delta = newScore - oldScore;
                        const row = document.createElement("div");
                        row.className = "kpi-gain-row";
                        row.innerHTML =
                            `<span class="kpi-gain-code">${escHtml(kpi.code)}</span>` +
                            `<div class="kpi-gain-track"><div class="kpi-gain-fill" style="width:${newScore}%"></div></div>` +
                            `<span class="kpi-gain-pct">${newScore}%</span>` +
                            `<span class="kpi-gain-delta ${delta > 0 ? "pos" : delta < 0 ? "neg" : ""}">${delta > 0 ? "+" : ""}${delta}%</span>`;
                        gainsContainer.appendChild(row);
                    });
                } else {
                    gainsLabel.style.display = "none";
                }

                showState("summary");
            }

            // ─── Summary button wiring ────────────────────────────────────────────────────────────────────────────
            const reviewBtn = $("review-btn");
            if (reviewBtn) {
                reviewBtn.addEventListener("click", startReview);
            }

            $("sum-go-home").addEventListener("click", () => {
                viewSession.style.display = "none";
                viewHome.style.display = "";
                initMasteryDashboard(currentEventId);
            });

            $("sum-study-again").addEventListener("click", () => {
                if (!allKpis.length) return;
                startSession();
            });
