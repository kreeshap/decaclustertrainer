let currentReview = null;
let selectedArchetype = "";
let refreshTimer = null;
const $ = (id) => document.getElementById(id);

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
  $("ops-classified").textContent = summary.classified ?? 0;
  $("ops-total").textContent = summary.total ?? 0;
  $("ops-remaining").textContent = summary.remaining ?? 0;
  $("ops-review-count").textContent = summary.needs_review ?? 0;
  $("ops-failed-count").textContent = data.failed_processing ?? 0;
  $("ops-progress-fill").style.width = `${summary.total ? Math.round((summary.classified / summary.total) * 100) : 0}%`;
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

$("process-kpis").addEventListener("click", startBatch);
$("retry-failed").addEventListener("click", retryFailed);
$("review-items").addEventListener("click", loadNextReview);
$("approve-review").addEventListener("click", () => saveReview("approve"));
$("skip-review").addEventListener("click", () => saveReview("skip"));
$("close-review").addEventListener("click", () => { $("review-panel").hidden = true; });
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
