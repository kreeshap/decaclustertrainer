let currentReview = null;
let selectedArchetype = "";
let refreshTimer = null;
let currentLessonAudit = null;
let currentQuestionImport = null;
let latestQuestionDocument = null;
let currentKnowledgeItem = null;
let currentCorpusQuestion = null;
let currentCorpusDocumentId = "";
let activeQuestionFilter = "needs_review";
let activeQuestionCluster = "";
let activeCorpusView = "overview";
let corpusRefreshTimer = null;
const lessonAuditScores = {};
const $ = (id) => document.getElementById(id);

function escHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showMessage(message, error = false) {
  $("ops-message").textContent = message || "";
  $("ops-message").style.color = error ? "#f87171" : "var(--cyan)";
}

async function readJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `Request failed (${response.status})`);
  return data;
}

function renderDashboard(data) {
  const summary = data.classification || {};
  const generated = data.generated_content || {};
  $("ops-classified").textContent = summary.classified ?? 0;
  $("ops-total").textContent = summary.total ?? 0;
  $("ops-remaining").textContent = summary.remaining ?? 0;
  $("ops-review-count").textContent = summary.needs_review ?? 0;
  $("ops-failed-count").textContent = data.failed_processing ?? 0;
  $("ops-progress-fill").style.width = `${summary.total ? Math.round((summary.classified / summary.total) * 100) : 0}%`;
  $("generated-ready").textContent = generated.ready ?? 0;
  $("generated-total").textContent = generated.total ?? 0;
  $("generated-percent").textContent = `${generated.percentage ?? 0}%`;
  $("generated-progress-fill").style.width = `${generated.percentage ?? 0}%`;
  const batch = data.latest_batch;
  $("batch-id").textContent = batch ? `Batch ${String(batch.id).slice(0, 8)}` : "No batches yet";
  $("batch-status").textContent = batch?.status || "";
  $("batch-processed").textContent = batch?.processed_count ?? 0;
  $("batch-approved").textContent = batch?.auto_approved_count ?? 0;
  $("batch-review").textContent = batch?.needs_review_count ?? 0;
  $("batch-failed").textContent = batch?.failed_count ?? 0;
  clearTimeout(refreshTimer);
  if (batch && ["queued", "processing"].includes(batch.status)) refreshTimer = window.setTimeout(loadDashboard, 5000);
}

async function loadDashboard() {
  try {
    renderDashboard(await readJson(await apiFetch("/api/admin/content-operations")));
    await loadLessonAuditDashboard();
    await loadQuestionImports();
    await loadCorpusDashboard();
    await loadCorpusDocuments();
    await loadSources();
  } catch (error) { showMessage(error.message, true); }
}

async function loadSources() {
  const search = $("source-search").value.trim();
  const data = await readJson(await apiFetch(`/api/admin/sources${search ? `?search=${encodeURIComponent(search)}` : ""}`));
  $("sources-stats").textContent = `${data.total} sources · ${data.linked_multiple_kpis} multi-KPI · ${data.needs_locating} need locating`;
  $("sources-list").innerHTML = data.sources.map((source) => `<article class="source-card" data-source-id="${escHtml(source.id)}">
    <h3>${escHtml(source.title || source.raw_citation)}</h3>
    <p>${escHtml([source.authors, source.edition, source.publication_year].filter(Boolean).join(" · "))}</p>
    <p>${source.question_count} questions · ${source.kpi_count} KPIs · ${source.document_count} uploaded exams</p>
    <p>KPIs: ${escHtml(source.kpis.join(", ") || "None mapped")}<br>Pages: ${escHtml(source.pages.join(", ") || "Not specified")}</p>
    <div class="source-card-actions">
      <button class="text-action source-search-web" type="button" data-query="${escHtml(source.search_query)}">Search Web</button>
      ${source.url ? `<a class="text-action" href="${escHtml(source.url)}" target="_blank" rel="noopener noreferrer">Visit source</a>` : ""}
      <input class="source-url" value="${escHtml(source.url || "")}" placeholder="Paste legitimate source URL">
      <select class="source-status">${["unreviewed","located","accessible","paywalled","physical","unavailable","do_not_use"].map((status) => `<option value="${status}" ${status === source.status ? "selected" : ""}>${status.replaceAll("_", " ")}</option>`).join("")}</select>
      <button class="primary-action source-save" type="button">Save</button>
    </div></article>`).join("") || "<p>No sources found.</p>";
}

async function saveSource(card) {
  try {
    await readJson(await apiFetch(`/api/admin/sources/${encodeURIComponent(card.dataset.sourceId)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: card.querySelector(".source-url").value, status: card.querySelector(".source-status").value }) }));
    await loadSources();
  } catch (error) { showMessage(error.message, true); }
}

async function loadQuestionImports() {
  const data = await readJson(await apiFetch("/api/admin/question-imports"));
  $("question-import-pending").textContent = data.pending || 0;
  latestQuestionDocument = data.documents?.[0] || null;
  $("kpi-knowledge-pending").textContent = data.knowledge_pending || 0;
  const statuses = data.status_breakdown || {};
  const statusLabels = { all: "All", verified: "Verified", needs_review: "Needs review", unassigned: "Unassigned", possible_duplicates: "Possible duplicates" };
  $("question-status-filters").innerHTML = Object.entries(statusLabels).map(([key, label]) => `<button type="button" class="corpus-filter ${activeQuestionFilter === key ? "active" : ""}" data-question-filter="${key}">${label} <strong>${statuses[key] || 0}</strong></button>`).join("");
  $("question-cluster-breakdown").innerHTML = Object.entries(data.cluster_breakdown || {}).map(([cluster, count]) => `<button type="button" class="corpus-filter ${activeQuestionCluster === cluster ? "active" : ""}" data-question-cluster="${escHtml(cluster)}">${escHtml(cluster)} <strong>${count}</strong></button>`).join("");
  if (!latestQuestionDocument) return;
  const doc = latestQuestionDocument;
  $("question-import-summary").textContent = `${doc.filename}: ${doc.detected_count} detected · ${statuses.verified || 0} verified · ${statuses.needs_review || 0} awaiting review · ${statuses.unassigned || 0} unassigned · ${statuses.possible_duplicates || 0} possible duplicates`;
}

function showCorpusView(view) {
  activeCorpusView = view;
  document.querySelectorAll("[data-corpus-panel]").forEach((panel) => {
    const inView = String(panel.dataset.corpusPanel || "").split(/\s+/).includes(view);
    if (!inView) panel.hidden = true;
    else if (!panel.hasAttribute("data-corpus-conditional")) panel.hidden = false;
  });
  document.querySelectorAll("[data-corpus-view]").forEach((button) => button.classList.toggle("active", button.dataset.corpusView === view));
  if (["exams", "roleplays"].includes(view)) {
    const type = view === "exams" ? "exam" : "roleplay";
    $("corpus-content-type").value = type;
    $("corpus-upload-kicker").textContent = type === "exam" ? "Exam reference upload" : "Roleplay / case study upload";
    $("corpus-upload-heading").textContent = type === "exam" ? "Upload exam PDF" : "Upload roleplay / case study PDF";
    document.querySelectorAll(".roleplay-only").forEach((field) => { field.hidden = type !== "roleplay"; });
    document.querySelectorAll(".exam-only").forEach((field) => { field.hidden = type !== "exam"; });
  }
  sessionStorage.setItem("ct_corpus_view", view);
}

function corpusCoverageBlock(title, values) {
  const entries = Object.entries(values || {});
  return `<article class="source-card"><h3>${escHtml(title)}</h3>${entries.length ? entries.map(([key, value]) => `<p><strong>${escHtml(key)}</strong> · ${value.documents} documents · ${value.items} items</p>`).join("") : "<p>No verified benchmark material yet.</p>"}</article>`;
}

async function loadCorpusDashboard() {
  const data = await readJson(await apiFetch("/api/admin/practice-corpus/dashboard"));
  $("corpus-documents").textContent = data.summary.documents || 0;
  $("corpus-verified").textContent = data.summary.verified_documents || 0;
  $("corpus-questions").textContent = data.summary.verified_questions || 0;
  $("corpus-roleplays").textContent = data.summary.verified_roleplays || 0;
  const exam = data.exam_style_profile || {}, roleplay = data.roleplay_style_profile || {};
  $("corpus-coverage").innerHTML = corpusCoverageBlock("Exam coverage by cluster", data.exams_by_cluster) + corpusCoverageBlock("Roleplay coverage by event", data.roleplays_by_event) +
    `<article class="source-card"><h3>Measured exam profile</h3><p>${exam.sample_size || 0} items · ${Math.round(100 * (exam.scenario_rate || 0))}% scenarios · ${Math.round(100 * (exam.calculation_rate || 0))}% calculations · ${exam.mean_stem_words || 0} mean stem words</p></article>` +
    `<article class="source-card"><h3>Measured roleplay profile</h3><p>${roleplay.sample_size || 0} scenarios · ${roleplay.mean_scenario_words || 0} mean scenario words · ${roleplay.mean_assigned_pis || 0} mean PIs · ${roleplay.mean_judge_questions || 0} mean judge questions</p></article>`;
  $("corpus-readiness").innerHTML = (data.readiness || []).map((row) => `<article class="source-card"><h3>${escHtml(row.event_code || row.cluster || "Corpus")} ${escHtml(row.content_type)}</h3><p>${row.documents} documents · ${row.items} verified items · ${row.years_represented} years · ${row.competition_levels} levels</p><p><strong>${row.status === "generator_ready" ? "READY" : "INSUFFICIENT"}</strong>${row.reasons?.length ? ` · ${escHtml(row.reasons.join(" "))}` : ""}</p></article>`).join("") || "<p>No event-specific readiness can be calculated yet.</p>";
  const quality = data.quality || {};
  $("corpus-quality").innerHTML = `<article class="source-card quality-metric-grid">
    ${[["Verified documents", `${quality.verified_documents_pct || 0}%`],["Verified items", `${quality.verified_items_pct || 0}%`],["Official sources", `${quality.official_source_pct || 0}%`],["Duplicate-adjusted", quality.duplicate_adjusted_documents || 0],["Years", quality.years_represented || 0],["Events", quality.events_represented || 0],["Instructional areas", quality.instructional_areas_represented || 0],["Answer-key coverage", `${quality.answer_key_coverage_pct || 0}%`],["Explicit PI labels", `${quality.explicit_pi_label_pct || 0}%`],["Benchmark eligible", `${quality.benchmark_eligible_pct || 0}%`],["Student publishable", `${quality.student_publishable_pct || 0}%`],["Gold references", `${quality.gold_exam_items || 0} exam · ${quality.gold_roleplays || 0} roleplay`]].map(([label,value]) => `<div><span>${escHtml(label)}</span><strong>${escHtml(value)}</strong></div>`).join("")}
  </article>`;
  const pilot = data.pilot_report || {};
  $("corpus-pilot-report").innerHTML = `<article class="source-card"><h3>${pilot.audited_documents || 0} documents fully audited</h3><p>Document audit coverage: ${pilot.document_detection_pct || 0}% · Item-count accuracy: ${pilot.item_count_accuracy_pct == null ? "Awaiting expected counts" : `${pilot.item_count_accuracy_pct}%`} · Silent corruption: ${pilot.silent_data_corruption || 0}</p><p>${Object.entries(pilot.failure_counts || {}).map(([code,count]) => `${escHtml(code)} · ${count}`).join(" | ") || "No parser failures recorded yet."}</p></article>`;
}

async function loadCorpusDocuments() {
  const data = await readJson(await apiFetch("/api/admin/practice-corpus"));
  const documents = data.documents || [];
  const pending = documents.filter((doc) => doc.processing_state !== "verified_reference" || (doc.item_counts?.pending || 0) > 0);
  const attempts = data.parse_attempts || [];
  const parsing = attempts.filter((attempt) => attempt.status === "parsing");
  const pendingExamItems = pending.filter((doc) => doc.content_type === "exam").reduce((total, doc) => total + (doc.item_counts?.pending || 0), 0);
  const pendingRoleplays = pending.filter((doc) => doc.content_type === "roleplay" && (doc.item_counts?.pending || doc.processing_state !== "verified_reference")).length;
  $("corpus-parsing-count").textContent = parsing.length;
  $("corpus-document-review-count").textContent = pending.filter((doc) => doc.processing_state !== "verified_reference").length;
  $("corpus-exam-review-count").textContent = pendingExamItems;
  $("corpus-roleplay-review-count").textContent = pendingRoleplays;
  $("corpus-review-list").innerHTML = pending.map((doc) => `<article class="source-card corpus-document" data-document-id="${escHtml(doc.id)}">
    <h3>${escHtml(doc.title)}</h3>
    <div class="corpus-status-row"><span class="corpus-status-pill">${escHtml(doc.content_type)}</span><span class="corpus-status-pill">${escHtml(doc.processing_state.replaceAll("_", " "))}</span><span>${doc.item_counts?.pending || 0} of ${doc.item_counts?.total || 0} items awaiting review</span></div>
    <p>${escHtml(doc.original_filename)}</p>
    <p>${doc.duplicate_of ? "⚠ Likely duplicate of another corpus document." : "No exact normalized-text duplicate detected."}</p>
    <p><strong>Review priority: ${escHtml(doc.review_priority || "normal")}</strong> · ${escHtml((doc.review_flags || []).join(", ") || "No deterministic flags")}</p>
    <details><summary>Field confidence</summary><pre>${escHtml(JSON.stringify(doc.field_confidence || {}, null, 2))}</pre></details>
    <label>Confirmed title<input class="corpus-title" value="${escHtml(doc.title)}"></label>
    <label>Year<input class="corpus-year" value="${escHtml(doc.competitive_year || "")}"></label>
    ${doc.content_type === "exam" ? `<label>Career cluster<input class="corpus-cluster" value="${escHtml(doc.cluster || "")}"></label>` : ""}
    ${doc.content_type === "roleplay" ? `<label>Event code<input class="corpus-events" value="${escHtml((doc.event_codes || []).join(", "))}"></label>` : ""}
    <label>Competition level<select class="corpus-level">${["district","association","icdc","practice_sample"].map((value) => `<option value="${value}" ${value === doc.competition_level ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>
    ${doc.content_type === "roleplay" ? `<label>Instructional area<input class="corpus-area" value="${escHtml(doc.instructional_area || "")}"></label>` : ""}
    ${doc.content_type === "roleplay" ? `<label>Rights<select class="corpus-rights">${["unknown","reference_only","owned","licensed_for_student_use","public_domain","do_not_use"].map((value) => `<option value="${value}" ${value === doc.rights_status ? "selected" : ""}>${value.replaceAll("_", " ")}</option>`).join("")}</select></label>` : ""}
    <label><input class="corpus-official" type="checkbox" ${doc.official_deca ? "checked" : ""}> Official DECA</label>
    <label><input class="corpus-benchmark" type="checkbox"> Benchmark eligible</label>
    <label><input class="corpus-publishable" type="checkbox"> Student publishable</label>
    ${doc.content_type === "roleplay" ? `<label><input class="corpus-gold" type="checkbox"> Gold reference</label>` : ""}
    ${doc.content_type === "roleplay" ? `<label class="audit-notes">Structured roleplay JSON<textarea class="corpus-roleplay-json" rows="12">${escHtml(JSON.stringify(doc.structured_roleplay || {}, null, 2))}</textarea></label>` : ""}
    <div class="corpus-document-actions">
      ${doc.processing_state !== "verified_reference" ? `<button class="primary-action corpus-verify" type="button">Verify document</button>` : ""}
      ${doc.content_type === "exam" && (doc.item_counts?.pending || 0) ? `<button class="text-action corpus-review-exam" type="button">Review ${doc.item_counts.pending} exam items</button>` : ""}
    </div>
    <fieldset class="pilot-audit-box"><legend>Pilot PDF comparison</legend>
      <label>Expected item count<input class="pilot-expected-count" type="number" min="0"></label>
      <label>Failure category<select class="pilot-failure-code"><option value="">No failure</option>${["exam_choice_split","exam_answer_key_mismatch","exam_multiline_stem","header_contamination","roleplay_pi_detection","roleplay_section_boundary","roleplay_judge_question_split","metadata_year_unknown","metadata_event_unknown","metadata_competition_level_unknown","table_or_special_format","page_break_split","other"].map((code) => `<option value="${code}">${code.replaceAll("_", " ")}</option>`).join("")}</select></label>
      <label>Failure detail<input class="pilot-failure-detail"></label>
      <label><input class="pilot-silent-corruption" type="checkbox"> Silent data corruption found</label>
      <button class="text-action corpus-pilot-audit" type="button">Record pilot audit</button>
    </fieldset>
  </article>`).join("") || "<p>No exams or roleplays need review.</p>";
  const documentNames = Object.fromEntries(documents.map((doc) => [doc.id, doc.original_filename]));
  const attemptRows = attempts.map((attempt) => ({ status: attempt.status, when: attempt.started_at, title: attempt.original_filename,
    detail: attempt.status === "failed" ? `${attempt.stage}: ${attempt.error_message || "Unknown parsing error"}` : `${attempt.item_count || 0} items · ${attempt.stage.replaceAll("_", " ")}` }));
  const failureRows = (data.parser_failures || []).map((failure) => ({ status: failure.resolved ? "resolved" : "failed", when: failure.created_at,
    title: documentNames[failure.document_id] || "Removed document", detail: `${failure.failure_code.replaceAll("_", " ")}${failure.detail ? `: ${failure.detail}` : ""}` }));
  const logRows = [...attemptRows, ...failureRows].sort((a, b) => String(b.when).localeCompare(String(a.when))).slice(0, 100);
  $("corpus-parse-log").innerHTML = logRows.map((row) => `<div class="corpus-log-row ${row.status === "failed" ? "failed" : ""}"><strong>${escHtml(row.title)}</strong><span>${escHtml(row.status.toUpperCase())} · ${escHtml(row.detail)}</span><small>${escHtml(row.when ? new Date(row.when).toLocaleString() : "")}</small></div>`).join("") || "<div class=\"corpus-log-row\"><span>No parsing activity yet.</span></div>";
  clearTimeout(corpusRefreshTimer);
  if (parsing.length) corpusRefreshTimer = window.setTimeout(() => Promise.all([loadCorpusDocuments(), loadCorpusDashboard()]), 3000);
}

async function uploadCorpus(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = true;
  form.classList.add("corpus-upload-busy");
  $("corpus-upload-status").textContent = `Parsing ${form.querySelector('[name="file"]').files[0]?.name || "PDF"}…`;
  showMessage("Storing the private PDF and extracting corpus structure…");
  try {
    const data = await readJson(await apiFetch("/api/admin/practice-corpus", { method: "POST", body: new FormData(form) }));
    $("corpus-upload-status").textContent = data.likely_duplicate ? "Parsed with a likely-duplicate warning; reviewer confirmation required." : "Parsed successfully; metadata and rights require review.";
    form.reset();
    $("corpus-content-type").value = activeCorpusView === "roleplays" ? "roleplay" : "exam";
    await Promise.all([loadCorpusDocuments(), loadCorpusDashboard()]);
  } catch (error) {
    $("corpus-upload-status").textContent = `Parsing failed: ${error.message}`;
    showMessage(error.message, true);
    await loadCorpusDocuments().catch(() => {});
  } finally {
    submit.disabled = false;
    form.classList.remove("corpus-upload-busy");
  }
}

async function verifyCorpus(card) {
  const events = (card.querySelector(".corpus-events")?.value || "").split(",").map((value) => value.trim().toUpperCase()).filter(Boolean);
  const metadata = { title: card.querySelector(".corpus-title").value, competitive_year: card.querySelector(".corpus-year").value,
    cluster: card.querySelector(".corpus-cluster")?.value || "", event_codes: events,
    competition_level: card.querySelector(".corpus-level").value, instructional_area: card.querySelector(".corpus-area")?.value || "",
    official_deca: card.querySelector(".corpus-official").checked };
  let structuredRoleplay = null;
  if (card.querySelector(".corpus-roleplay-json")) {
    try { structuredRoleplay = JSON.parse(card.querySelector(".corpus-roleplay-json").value); }
    catch { showMessage("Structured roleplay must be valid JSON.", true); return; }
  }
  try {
    await readJson(await apiFetch(`/api/admin/practice-corpus/${encodeURIComponent(card.dataset.documentId)}/verify`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmed_metadata: metadata, structured_roleplay: structuredRoleplay, gold_reference: card.querySelector(".corpus-gold")?.checked === true, rights_status: card.querySelector(".corpus-rights")?.value || "licensed_for_student_use", benchmark_eligible: card.querySelector(".corpus-benchmark").checked, student_publishable: card.querySelector(".corpus-publishable").checked }) }));
    await Promise.all([loadCorpusDocuments(), loadCorpusDashboard()]);
  } catch (error) { showMessage(error.message, true); }
}

async function recordPilotAudit(card) {
  const code = card.querySelector(".pilot-failure-code").value;
  const failures = code ? [{ failure_code: code, item_type: card.querySelector(".corpus-roleplay-json") ? "roleplay" : "document", detail: card.querySelector(".pilot-failure-detail").value }] : [];
  try {
    await readJson(await apiFetch(`/api/admin/practice-corpus/${encodeURIComponent(card.dataset.documentId)}/pilot-audit`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        expected_item_count: Number(card.querySelector(".pilot-expected-count").value || 0) || null,
        silent_data_corruption: card.querySelector(".pilot-silent-corruption").checked,
        failures,
        checklist: { pdf_compared: true },
      }),
    }));
    showMessage("Pilot audit recorded."); await Promise.all([loadCorpusDocuments(), loadCorpusDashboard()]);
  } catch (error) { showMessage(error.message, true); }
}

async function loadNextCorpusQuestion(documentId = "") {
  try {
    if (documentId) currentCorpusDocumentId = documentId;
    showCorpusView("review");
    const selectedDocumentId = documentId || currentCorpusDocumentId;
    const data = await readJson(await apiFetch(`/api/admin/practice-corpus/questions/review-next${selectedDocumentId ? `?document_id=${encodeURIComponent(selectedDocumentId)}` : ""}`));
    currentCorpusQuestion = data.question;
    $("corpus-question-review").hidden = !data.question;
    if (!data.question) { currentCorpusDocumentId = ""; showMessage("All extracted exam items in this exam are reviewed."); await loadCorpusDocuments(); return; }
    $("corpus-question-meta").textContent = `Question ${data.question.question_number} · Page ${data.question.page_number || "?"}`;
    $("corpus-question-stem").value = data.question.stem || "";
    document.querySelectorAll("[data-corpus-choice]").forEach((input) => {
      input.value = (data.question.choices || [])[Number(input.dataset.corpusChoice)] || "";
    });
    $("corpus-question-answer").value = Number.isInteger(data.question.official_answer) ? String(data.question.official_answer) : "";
    $("corpus-question-pi").value = data.question.pi_code || "";
    $("corpus-question-area").value = data.question.instructional_area || "";
    $("corpus-question-demand").value = data.question.cognitive_demand || "";
    $("corpus-question-gold").checked = data.question.gold_reference === true;
    $("corpus-question-flags").textContent = `${(data.question.review_flags || []).join(" · ") || "No deterministic flags"}\n${JSON.stringify(data.question.field_confidence || {}, null, 2)}`;
  } catch (error) { showMessage(error.message, true); }
}

async function verifyCorpusQuestion() {
  if (!currentCorpusQuestion) return;
  const answer = $("corpus-question-answer").value;
  const choices = [...document.querySelectorAll("[data-corpus-choice]")].map((input) => input.value.trim());
  if (!$("corpus-question-stem").value.trim() || choices.some((choice) => !choice)) {
    showMessage("Enter the question stem and all four answer choices.", true); return;
  }
  try {
    await readJson(await apiFetch(`/api/admin/practice-corpus/questions/${encodeURIComponent(currentCorpusQuestion.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stem: $("corpus-question-stem").value.trim(), choices, official_answer: answer === "" ? null : Number(answer), pi_code: $("corpus-question-pi").value, instructional_area: $("corpus-question-area").value, cognitive_demand: $("corpus-question-demand").value, gold_reference: $("corpus-question-gold").checked }) }));
    await loadNextCorpusQuestion(currentCorpusDocumentId); await loadCorpusDashboard();
  } catch (error) { showMessage(error.message, true); }
}

async function loadNextKnowledgeItem() {
  try {
    const data = await readJson(await apiFetch("/api/admin/kpi-knowledge/review-next"));
    currentKnowledgeItem = data.item;
    $("kpi-knowledge-review").hidden = !data.item;
    if (!data.item) { showMessage("The Learn enrichment inbox is clear."); return; }
    $("kpi-knowledge-meta").textContent = `${data.item.deca_cluster} · ${data.item.kpi_cluster}`;
    $("kpi-knowledge-title").textContent = `${data.item.kpi_code} · ${data.item.knowledge_type.replaceAll("_", " ")}`;
    $("kpi-knowledge-content").value = data.item.content;
    $("kpi-knowledge-importance").value = data.item.importance;
    $("kpi-deca-evidence").textContent = JSON.stringify(data.item.deca_evidence || data.item.source_references || [], null, 2);
    $("kpi-factual-evidence").value = JSON.stringify(data.item.factual_evidence || [], null, 2);
    $("kpi-verification-class").value = data.item.verification_class || "time_sensitive";
    $("kpi-reverify-after").value = data.item.reverify_after || "";
    document.querySelectorAll("[data-knowledge-check]").forEach((input) => { input.checked = false; });
  } catch (error) { showMessage(error.message, true); }
}

async function reviewKnowledgeItem(action) {
  if (!currentKnowledgeItem) return;
  try {
    let factualEvidence = [];
    if (action === "approve") {
      try { factualEvidence = JSON.parse($("kpi-factual-evidence").value); }
      catch { throw new Error("Factual evidence must be a valid JSON array."); }
    }
    const reviewChecklist = Object.fromEntries([...document.querySelectorAll("[data-knowledge-check]")].map((input) => [input.dataset.knowledgeCheck, input.checked]));
    await readJson(await apiFetch(`/api/admin/kpi-knowledge/${encodeURIComponent(currentKnowledgeItem.id)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, content: $("kpi-knowledge-content").value, importance: $("kpi-knowledge-importance").value, factual_evidence: factualEvidence, review_checklist: reviewChecklist, verification_class: $("kpi-verification-class").value, reverify_after: $("kpi-reverify-after").value }),
    }));
    await loadNextKnowledgeItem(); await loadQuestionImports();
  } catch (error) { showMessage(error.message, true); }
}

async function uploadQuestionPdf(event) {
  event.preventDefault();
  showMessage("Parsing questions and answer keys…");
  try {
    const data = await readJson(await apiFetch("/api/admin/question-imports", { method: "POST", body: new FormData(event.currentTarget) }));
    showMessage(`${data.document.detected_count} questions detected. ${data.document.review_count} need attention.`);
    await loadQuestionImports();
  } catch (error) { showMessage(error.message, true); }
}

function renderQuestionImport(item, document) {
  currentQuestionImport = item;
  $("question-import-review").hidden = !item;
  if (!item) { showMessage("The question import review inbox is clear."); return; }
  $("question-import-review-meta").textContent = `${document.filename} · Question ${item.question_number} · Page ${item.page_number || "?"}`;
  $("question-import-review-stem").textContent = item.question_text;
  $("question-import-review-choices").innerHTML = (item.choices || []).map((choice) => `<li>${escHtml(choice)}</li>`).join("");
  $("question-import-review-reasons").textContent = (item.review_reasons || []).map((reason) => reason.replaceAll("_", " ")).join(" · ");
  $("question-import-kpi").value = item.kpi_code || "";
  $("question-import-answer").value = Number.isInteger(item.correct_index) ? String(item.correct_index) : "";
  $("question-import-explanation").value = item.explanation || "";
}

async function loadNextQuestionImport() {
  try {
    showCorpusView("review");
    if (activeQuestionFilter === "verified") { showMessage("Verified items are read-only in this queue."); return; }
    const query = new URLSearchParams({ filter: activeQuestionFilter || "needs_review" });
    if (activeQuestionCluster) query.set("cluster", activeQuestionCluster);
    const data = await readJson(await apiFetch(`/api/admin/question-imports/review-next?${query}`));
    renderQuestionImport(data.item, data.document || {});
    if (!data.item) showMessage("No reviewable items match this filter.");
  } catch (error) { showMessage(error.message, true); }
}

async function reviewQuestionImport(action) {
  if (!currentQuestionImport) return;
  const payload = action === "skip" ? { action } : { action: "approve", kpi_code: $("question-import-kpi").value, correct_index: $("question-import-answer").value, explanation: $("question-import-explanation").value };
  try {
    await readJson(await apiFetch(`/api/admin/question-imports/${encodeURIComponent(currentQuestionImport.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
    await loadNextQuestionImport(); await loadQuestionImports();
  } catch (error) { showMessage(error.message, true); }
}

async function approveReadyImports() {
  if (!latestQuestionDocument) return;
  try {
    const data = await readJson(await apiFetch(`/api/admin/question-imports/${encodeURIComponent(latestQuestionDocument.id)}/approve-ready`, { method: "POST" }));
    showMessage(`${data.imported} clean questions added to Practice Mode${data.failures.length ? `; ${data.failures.length} need attention` : ""}.`, Boolean(data.failures.length));
    await loadQuestionImports();
  } catch (error) { showMessage(error.message, true); }
}

async function generateOriginalQuestions(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = { career_cluster: form.get("career_cluster"), kpi_code: form.get("kpi_code"), count: Number(form.get("count") || 3) };
  showMessage("Generating and independently reviewing original questions…");
  try {
    const data = await readJson(await apiFetch("/api/admin/questions/generate-original", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
    $("question-style-summary").textContent = `Profile: ${data.style_profile.corpus_size} references · ${data.style_profile.scenario_percentage}% scenarios · ${data.style_profile.average_stem_words} average stem words`;
    showMessage(`${data.generated} original questions approved${data.rejected.length ? `; ${data.rejected.length} rejected by quality checks` : ""}.`);
  } catch (error) { showMessage(error.message, true); }
}

const AUDIT_CRITERIA = [
  ["mission_clarity", "Mission made sense immediately"],
  ["choice_matters", "First choice meaningfully affected teaching"],
  ["vocabulary_quality", "Vocabulary was useful, not filler"],
  ["learning_value", "Lesson taught reasoning, not definitions alone"],
  ["difficulty_progression", "Final questions increased cognitive difficulty"],
  ["pacing_quality", "Pacing stayed focused and usable"],
];

async function loadLessonAuditDashboard() {
  const data = await readJson(await apiFetch("/api/admin/content-audits"));
  $("lesson-audit-pending").textContent = data.pending || 0;
  $("lesson-generation-failures").textContent = data.generation_failures || 0;
  const batch = data.latest_batch;
  $("lesson-audit-batch").textContent = batch ? `Audit ${String(batch.id).slice(0, 8)} · ${batch.processed_count}/${batch.requested_count}` : "No audit batches yet";
  $("lesson-audit-status").textContent = batch?.status || "";
  if (batch && ["queued", "processing"].includes(batch.status)) {
    clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(loadDashboard, 5000);
  }
}

async function startLessonAudit() {
  const button = $("start-lesson-audit");
  button.disabled = true;
  showMessage("Building a balanced 20-KPI lesson audit…");
  try {
    const data = await readJson(await apiFetch("/api/admin/content-audits/process", { method: "POST" }));
    showMessage(data.queued ? `${data.queued} lessons queued. You can leave this page.` : data.message);
    await loadDashboard();
  } catch (error) { showMessage(error.message, true); }
  finally { button.disabled = false; }
}

function appendPreviewSection(parent, title, body) {
  if (!body) return;
  const heading = document.createElement("h3");
  heading.textContent = title;
  const textNode = document.createElement("p");
  textNode.textContent = body;
  parent.append(heading, textNode);
}

function renderLessonAudit(item) {
  currentLessonAudit = item;
  Object.keys(lessonAuditScores).forEach((key) => delete lessonAuditScores[key]);
  if (!item) {
    $("lesson-audit-review").hidden = true;
    showMessage("The lesson audit inbox is clear.");
    return;
  }
  $("lesson-audit-review").hidden = false;
  $("lesson-audit-meta").textContent = `${item.complexity} · ${String(item.skill_type).replaceAll("_", " ")}`;
  $("lesson-audit-title").textContent = `${item.kpi?.code || item.kpi_id} — ${item.kpi?.name || "Lesson preview"}`;
  const lesson = item.generated_lesson || {};
  const preview = $("lesson-audit-preview");
  preview.innerHTML = "";
  appendPreviewSection(preview, lesson.mission?.title || "Mission", lesson.mission?.brief);
  appendPreviewSection(preview, "First move", lesson.mission?.opening_interaction?.question);
  (lesson.learning_blocks || []).forEach((block) => appendPreviewSection(preview, block.title || "Learn", block.body));
  appendPreviewSection(preview, "Concept", lesson.concept?.explanation);
  appendPreviewSection(preview, "Scenario", lesson.realistic_example?.story);
  (lesson.practice_questions || []).forEach((question, index) => appendPreviewSection(preview, question.stage_label || ["Check", "Apply", "DECA Challenge"][index], question.text));
  const scores = $("lesson-audit-scores");
  scores.innerHTML = "";
  AUDIT_CRITERIA.forEach(([field, label]) => {
    const row = document.createElement("div");
    row.className = "audit-score-row";
    const name = document.createElement("span");
    name.textContent = label;
    row.appendChild(name);
    for (let score = 1; score <= 5; score++) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = score;
      button.addEventListener("click", () => {
        lessonAuditScores[field] = score;
        row.querySelectorAll("button").forEach((candidate) => candidate.classList.toggle("selected", candidate === button));
      });
      row.appendChild(button);
    }
    scores.appendChild(row);
  });
  $("lesson-audit-notes").value = "";
  window.scrollTo({ top: $("lesson-audit-review").offsetTop - 70, behavior: "smooth" });
}

async function loadNextLessonAudit() {
  try {
    const data = await readJson(await apiFetch("/api/admin/content-audits/review-next"));
    renderLessonAudit(data.item);
  } catch (error) { showMessage(error.message, true); }
}

async function saveLessonAudit() {
  if (!currentLessonAudit) return;
  if (AUDIT_CRITERIA.some(([field]) => !lessonAuditScores[field])) {
    showMessage("Score all six criteria before continuing.", true);
    return;
  }
  try {
    await readJson(await apiFetch(`/api/admin/content-audits/${encodeURIComponent(currentLessonAudit.id)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...lessonAuditScores, notes: $("lesson-audit-notes").value }),
    }));
    await loadNextLessonAudit();
    await loadLessonAuditDashboard();
  } catch (error) { showMessage(error.message, true); }
}

async function startBatch() {
  const button = $("process-kpis");
  button.disabled = true;
  showMessage("Queuing the next classification batch…");
  try {
    const data = await readJson(await apiFetch("/api/admin/content-operations/process", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ limit: 20 }),
    }));
    showMessage(data.queued ? `${data.queued} KPIs queued. You can leave this page.` : data.message);
    await loadDashboard();
  } catch (error) { showMessage(error.message, true); }
  finally { button.disabled = false; }
}

async function retryFailed() {
  showMessage("Queuing failed classifications…");
  try {
    const data = await readJson(await apiFetch("/api/admin/content-operations/retry-failed", { method: "POST" }));
    showMessage(data.queued ? `${data.queued} failed KPIs queued again.` : "No failed classifications to retry.");
    await loadDashboard();
  } catch (error) { showMessage(error.message, true); }
}

function chooseOption(archetype) {
  selectedArchetype = archetype;
  document.querySelectorAll(".review-option").forEach((button) => {
    button.classList.toggle("selected", button.dataset.archetype === archetype);
  });
}

function renderReview(item, remaining) {
  currentReview = item;
  selectedArchetype = item?.primary_archetype || "";
  if (!item) {
    $("review-panel").hidden = true;
    showMessage("The classification review inbox is clear.");
    loadDashboard();
    return;
  }
  $("review-panel").hidden = false;
  $("review-remaining").textContent = `${remaining} need review`;
  $("review-code").textContent = item.kpi?.code || item.kpi_id;
  $("review-name").textContent = item.kpi?.name || "Unnamed KPI";
  $("review-meta").textContent = [item.kpi?.cluster, item.kpi?.instructional_area].filter(Boolean).join(" • ");
  const fields = [["Skill", item.skill_type], ["Complexity", item.complexity], ["Archetype", item.primary_archetype], ["Learner action", item.learner_action], ["DECA action", item.deca_action], ["Certainty", item.certainty]];
  $("classification-grid").innerHTML = fields.map(([label, value]) => `<div><strong>${escHtml(String(value || "—").replaceAll("_", " "))}</strong><span>${escHtml(label)}</span></div>`).join("");
  const reviewer = item.reviewer_result || {};
  const disagreements = item.deterministic_check?.disagreements || [];
  $("review-reason").textContent = reviewer.reason || item.ambiguity_reason || (disagreements.length ? `Classifier and deterministic check disagree on ${disagreements.join(", ")}.` : item.classification_reason);
  const options = [item.primary_archetype, reviewer.recommended_archetype, item.alternative_archetype, item.deterministic_check?.primary_archetype]
    .filter((value, index, values) => value && values.indexOf(value) === index).slice(0, 2);
  $("review-options").innerHTML = "";
  options.forEach((option, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "review-option" + (option === selectedArchetype ? " selected" : "");
    button.dataset.archetype = option;
    button.textContent = `${index + 1}. ${option.replaceAll("_", " ")}`;
    button.addEventListener("click", () => chooseOption(option));
    $("review-options").appendChild(button);
  });
  window.scrollTo({ top: $("review-panel").offsetTop - 70, behavior: "smooth" });
}

async function loadNextReview() {
  try {
    const data = await readJson(await apiFetch("/api/admin/content-operations/review-next"));
    renderReview(data.item, data.remaining || 0);
  } catch (error) { showMessage(error.message, true); }
}

async function saveReview(action) {
  if (!currentReview) return;
  try {
    await readJson(await apiFetch(`/api/admin/content-operations/review/${encodeURIComponent(currentReview.kpi_id)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, primary_archetype: action === "approve" && selectedArchetype !== currentReview.primary_archetype ? selectedArchetype : "" }),
    }));
    await loadNextReview();
  } catch (error) { showMessage(error.message, true); }
}

function showAdminTab(tabName) {
  const valid = ["overview", "study", "questions", "sources"];
  const selected = valid.includes(tabName) ? tabName : "overview";
  document.querySelectorAll("[data-admin-group]").forEach((panel) => {
    panel.classList.toggle("admin-tab-hidden", panel.dataset.adminGroup !== selected);
  });
  document.querySelectorAll("[data-admin-tab]").forEach((button) => {
    const active = button.dataset.adminTab === selected;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  sessionStorage.setItem("ct_admin_active_tab", selected);
  window.scrollTo({ top: 0, behavior: "instant" });
}

document.querySelectorAll("[data-admin-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    showAdminTab(button.dataset.adminTab);
    if (button.dataset.adminTab === "questions") showCorpusView(activeCorpusView);
  });
});
showAdminTab(sessionStorage.getItem("ct_admin_active_tab") || "overview");
document.querySelectorAll("[data-corpus-view]").forEach((button) => button.addEventListener("click", () => showCorpusView(button.dataset.corpusView)));
showCorpusView(sessionStorage.getItem("ct_corpus_view") || "overview");

$("process-kpis").addEventListener("click", startBatch);
$("retry-failed").addEventListener("click", retryFailed);
$("review-items").addEventListener("click", loadNextReview);
$("approve-review").addEventListener("click", () => saveReview("approve"));
$("skip-review").addEventListener("click", () => saveReview("skip"));
$("close-review").addEventListener("click", () => { $("review-panel").hidden = true; });
$("start-lesson-audit").addEventListener("click", startLessonAudit);
$("review-lesson-audits").addEventListener("click", loadNextLessonAudit);
$("save-lesson-audit").addEventListener("click", saveLessonAudit);
$("close-lesson-audit").addEventListener("click", () => { $("lesson-audit-review").hidden = true; });
$("question-import-form").addEventListener("submit", uploadQuestionPdf);
$("corpus-upload-form").addEventListener("submit", uploadCorpus);
$("corpus-review-list").addEventListener("click", (event) => {
  const button = event.target.closest(".corpus-verify");
  if (button) verifyCorpus(button.closest(".corpus-document"));
  const auditButton = event.target.closest(".corpus-pilot-audit");
  if (auditButton) recordPilotAudit(auditButton.closest(".corpus-document"));
  const reviewExam = event.target.closest(".corpus-review-exam");
  if (reviewExam) loadNextCorpusQuestion(reviewExam.closest(".corpus-document").dataset.documentId);
});
$("question-status-filters").addEventListener("click", (event) => {
  const button = event.target.closest("[data-question-filter]");
  if (!button) return;
  activeQuestionFilter = button.dataset.questionFilter;
  loadQuestionImports();
  if (activeQuestionFilter !== "verified") loadNextQuestionImport();
});
$("question-cluster-breakdown").addEventListener("click", (event) => {
  const button = event.target.closest("[data-question-cluster]");
  if (!button) return;
  activeQuestionCluster = activeQuestionCluster === button.dataset.questionCluster ? "" : button.dataset.questionCluster;
  loadQuestionImports();
  loadNextQuestionImport();
});
$("view-corpus-readiness").addEventListener("click", () => $("corpus-readiness").scrollIntoView({ behavior: "smooth", block: "start" }));
$("verify-corpus-question").addEventListener("click", verifyCorpusQuestion);
$("close-corpus-question").addEventListener("click", () => { $("corpus-question-review").hidden = true; });
$("review-question-imports").addEventListener("click", loadNextQuestionImport);
$("import-reviewed-question").addEventListener("click", () => reviewQuestionImport("approve"));
$("skip-import-question").addEventListener("click", () => reviewQuestionImport("skip"));
$("close-question-import-review").addEventListener("click", () => { $("question-import-review").hidden = true; });
$("review-kpi-knowledge").addEventListener("click", loadNextKnowledgeItem);
$("approve-kpi-knowledge").addEventListener("click", () => reviewKnowledgeItem("approve"));
$("ignore-kpi-knowledge").addEventListener("click", () => reviewKnowledgeItem("ignore"));
$("close-kpi-knowledge").addEventListener("click", () => { $("kpi-knowledge-review").hidden = true; });
$("source-search").addEventListener("input", () => { window.clearTimeout($("source-search")._timer); $("source-search")._timer = window.setTimeout(loadSources, 250); });
$("sources-list").addEventListener("click", (event) => {
  const searchButton = event.target.closest(".source-search-web");
  if (searchButton) window.open(`https://www.google.com/search?q=${encodeURIComponent(searchButton.dataset.query)}`, "_blank", "noopener,noreferrer");
  const saveButton = event.target.closest(".source-save");
  if (saveButton) saveSource(saveButton.closest(".source-card"));
});
document.addEventListener("keydown", (event) => {
  if ($("review-panel").hidden || !currentReview) return;
  if (event.key.toLowerCase() === "a") saveReview("approve");
  if (event.key.toLowerCase() === "s") saveReview("skip");
  if (["1", "2"].includes(event.key)) {
    const option = document.querySelectorAll(".review-option")[Number(event.key) - 1];
    if (option) chooseOption(option.dataset.archetype);
  }
});

requireAuth().then((user) => {
  if (!user) return;
  initTopbar(user);
  loadDashboard();
});
