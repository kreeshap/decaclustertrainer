            /* ──────────────────────────────────────────────────────────────
       SIDEBAR NAVIGATION
    ────────────────────────────────────────────────────────────── */
            function navTo(e, id) {
                e.preventDefault();
                const el = document.getElementById(id);
                if (el)
                    el.scrollIntoView({ behavior: "smooth", block: "start" });
                document
                    .querySelectorAll(".sidebar-item")
                    .forEach((i) => i.classList.remove("active"));
                e.currentTarget.classList.add("active");
            }

            /* ──────────────────────────────────────────────────────────────
       SECTION SEARCH FILTER
    ────────────────────────────────────────────────────────────── */
            document
                .getElementById("settings-search")
                .addEventListener("input", function () {
                    const q = this.value.toLowerCase();
                    document
                        .querySelectorAll(".settings-section")
                        .forEach((sec) => {
                            sec.style.display = sec.textContent
                                .toLowerCase()
                                .includes(q)
                                ? ""
                                : "none";
                        });
                });

            /* ──────────────────────────────────────────────────────────────
       SKELETON HELPERS
    ────────────────────────────────────────────────────────────── */
            function clearSkeletons() {
                // Remove .skeleton from inputs / selects / toggles / theme pills
                document
                    .querySelectorAll(".skeleton")
                    .forEach((el) => el.classList.remove("skeleton"));
                // Remove inline skel-block placeholders
                document
                    .querySelectorAll(".skel-block")
                    .forEach((el) => el.remove());
            }

            /* ──────────────────────────────────────────────────────────────
       INITIALS HELPER
    ────────────────────────────────────────────────────────────── */
            function getInitials(name) {
                const parts = (name || "").trim().split(/\s+/).filter(Boolean);
                return (
                    parts
                        .map((p) => p[0])
                        .join("")
                        .toUpperCase()
                        .slice(0, 2) || "?"
                );
            }

            /* ──────────────────────────────────────────────────────────────
       AVATAR LIVE PREVIEW  (updates as user types name)
    ────────────────────────────────────────────────────────────── */
            document
                .getElementById("input-name")
                .addEventListener("input", function () {
                    const name = this.value;
                    document.getElementById(
                        "display-name-preview",
                    ).textContent = name || "Your Name";
                    document.getElementById("avatar-initials").textContent =
                        getInitials(name);
                });

            /* ──────────────────────────────────────────────────────────────
       EMAIL CHANGE INLINE FORM
    ────────────────────────────────────────────────────────────── */
            function toggleEmailForm() {
                document
                    .getElementById("email-change-form")
                    .classList.toggle("open");
            }

            async function sendEmailVerification() {
                const newEmail = document
                    .getElementById("input-new-email")
                    .value.trim();
                if (!newEmail) {
                    ErrorManager.show(
                        "Please enter a new email address.",
                        "error",
                    );
                    return;
                }
                const btn = document.getElementById("btn-send-verification");
                const ok = await doSave(btn, async () => {
                    const res = await apiFetch("/auth/change-email", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ email: newEmail }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to send verification email.",
                            "error",
                        );
                        return false;
                    }
                    ErrorManager.show(
                        "Verification email sent! Check your inbox.",
                        "success",
                    );
                    return true;
                });
                if (ok) {
                    document
                        .getElementById("email-change-form")
                        .classList.remove("open");
                    document.getElementById("input-new-email").value = "";
                }
            }

            /* ──────────────────────────────────────────────────────────────
       SAVE PROFILE
    ────────────────────────────────────────────────────────────── */
            async function saveProfile() {
                const btn = document.getElementById("btn-save-profile");
                const name = document.getElementById("input-name").value.trim();
                if (!name) {
                    ErrorManager.show("Display name cannot be empty.", "error");
                    return;
                }
                await doSave(btn, async () => {
                    const res = await apiFetch("/auth/profile", {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ display_name: name }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to save profile.",
                            "error",
                        );
                        return false;
                    }
                    // Update every name-bearing element without a page reload
                    document.getElementById(
                        "display-name-preview",
                    ).textContent = name;
                    const topbarEl = document.getElementById("topbar-name");
                    if (topbarEl) topbarEl.textContent = name;
                    const parts = name.trim().split(" ").filter(Boolean);
                    const initials = parts
                        .map((p) => p[0])
                        .join("")
                        .toUpperCase()
                        .slice(0, 2);
                    document.getElementById("avatar-initials").textContent =
                        initials || "?";
                    ErrorManager.show("Profile saved.", "success");
                    return true;
                });
            }

            /* ──────────────────────────────────────────────────────────────
       COMPETITION LEVEL
    ────────────────────────────────────────────────────────────── */
            function setComp(el) {
                // Only update the visual selection — label updates on save
                document
                    .querySelectorAll(".comp-opt")
                    .forEach((o) => o.classList.remove("selected"));
                el.classList.add("selected");
            }

            async function saveComp() {
                const sel = document.querySelector(".comp-opt.selected");
                if (!sel) return;
                const btn = document.getElementById("btn-save-comp");
                await doSave(btn, async () => {
                    const res = await apiFetch("/auth/profile", {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            competition_tier: sel.dataset.level,
                        }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to save competition level.",
                            "error",
                        );
                        return false;
                    }
                    // Update label only after a successful save
                    const level = sel.dataset.level;
                    const display =
                        level === "icdc"
                            ? "ICDC"
                            : level.charAt(0).toUpperCase() + level.slice(1);
                    document.getElementById("comp-current-label").textContent =
                        "Currently set to: " + display;
                    return true;
                });
            }

            /* ──────────────────────────────────────────────────────────────
       PASSWORD CHANGE + STRENGTH INDICATOR
    ────────────────────────────────────────────────────────────── */
            function togglePasswordForm() {
                const form = document.getElementById("password-change-form");
                form.classList.toggle("open");
            }

            function pwScore(pw) {
                let s = 0;
                if (pw.length >= 6) s++;
                if (pw.length >= 10) s++;
                if (/[A-Z]/.test(pw) && /[0-9]/.test(pw)) s++;
                if (/[^A-Za-z0-9]/.test(pw)) s++;
                return s;
            }

            function updatePwStrength(pw) {
                const score = pw.length === 0 ? 0 : pwScore(pw);
                const labels = ["", "Weak", "Fair", "Good", "Strong"];
                const cls = ["", "s1", "s2", "s3", "s4"];
                for (let i = 1; i <= 4; i++) {
                    const seg = document.getElementById("pw-s" + i);
                    seg.className =
                        "pw-seg" + (i <= score ? " " + cls[score] : "");
                }
                document.getElementById("pw-strength-label").textContent =
                    score > 0 ? labels[score] : "";
            }

            async function changePassword() {
                const newPw =
                    document.getElementById("input-new-password").value;
                const confirmPw = document.getElementById(
                    "input-confirm-password",
                ).value;
                if (!newPw) {
                    ErrorManager.show("Please enter a new password.", "error");
                    return;
                }
                if (newPw.length < 8) {
                    ErrorManager.show(
                        "Password must be at least 8 characters.",
                        "error",
                    );
                    return;
                }
                if (newPw !== confirmPw) {
                    ErrorManager.show("Passwords do not match.", "error");
                    return;
                }
                const btn = document.getElementById("btn-update-password");
                const ok = await doSave(btn, async () => {
                    const res = await apiFetch("/auth/change-password", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ new_password: newPw }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to update password.",
                            "error",
                        );
                        return false;
                    }
                    ErrorManager.show(
                        "Password updated successfully.",
                        "success",
                    );
                    return true;
                });
                if (ok) {
                    document
                        .getElementById("password-change-form")
                        .classList.remove("open");
                    document.getElementById("input-new-password").value = "";
                    document.getElementById("input-confirm-password").value =
                        "";
                    updatePwStrength("");
                }
            }

            /* ──────────────────────────────────────────────────────────────
       TOGGLE HELPERS
    ────────────────────────────────────────────────────────────── */
            // Local-only toggle (login notifications — localStorage)
            function toggleLocalPref(btn, labelId, storageKey) {
                btn.classList.toggle("on");
                const isOn = btn.classList.contains("on");
                document.getElementById(labelId).textContent = isOn
                    ? "On"
                    : "Off";
                localStorage.setItem("ct_" + storageKey, isOn ? "1" : "0");
            }

            // UI-only toggle (no save — requires explicit save button)
            function toggleUI(btn, labelId) {
                btn.classList.toggle("on");
                const isOn = btn.classList.contains("on");
                document.getElementById(labelId).textContent = isOn
                    ? "On"
                    : "Off";
            }

            // Set toggle state from loaded data
            function setToggle(btnId, labelId, value) {
                const btn = document.getElementById(btnId);
                const lbl = document.getElementById(labelId);
                const on = !!value;
                if (btn) btn.classList.toggle("on", on);
                if (lbl) lbl.textContent = on ? "On" : "Off";
            }

            /* ──────────────────────────────────────────────────────────────
       SIGN OUT ALL DEVICES
    ────────────────────────────────────────────────────────────── */
            async function signOutAll() {
                const btn = document.getElementById("btn-signout-all");
                await doSave(btn, async () => {
                    const res = await apiFetch("/auth/signout-all", {
                        method: "POST",
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to sign out other sessions.",
                            "error",
                        );
                        return false;
                    }
                    ErrorManager.show(
                        "All other sessions have been signed out.",
                        "success",
                    );
                    return true;
                });
            }

            /* ──────────────────────────────────────────────────────────────
       NOTIFICATIONS — removed
    ────────────────────────────────────────────────────────────── */

            /* ──────────────────────────────────────────────────────────────
       EVENT SELECTION  (cluster → event picker)
    ────────────────────────────────────────────────────────────── */
            (function initEventSelection() {
                const clusterSel = document.getElementById("select-deca-cluster");
                const eventSel = document.getElementById("select-deca-event");
                if (!clusterSel || !eventSel) return;

                // Populate cluster dropdown from CLUSTERS constant (clusters.js)
                if (typeof CLUSTERS !== "undefined") {
                    CLUSTERS.forEach((c) => {
                        if (!c.events || !c.events.length) return;
                        const opt = document.createElement("option");
                        opt.value = c.name;
                        opt.textContent = c.name;
                        clusterSel.appendChild(opt);
                    });
                }

                function populateEvents(clusterName) {
                    eventSel.innerHTML = "";
                    if (!clusterName || typeof CLUSTERS === "undefined") {
                        eventSel.disabled = true;
                        const opt = document.createElement("option");
                        opt.value = "";
                        opt.textContent = "— Select a cluster first —";
                        eventSel.appendChild(opt);
                        return;
                    }
                    const cluster = CLUSTERS.find((c) => c.name === clusterName);
                    if (!cluster || !cluster.events.length) {
                        eventSel.disabled = true;
                        return;
                    }
                    eventSel.disabled = false;
                    const placeholder = document.createElement("option");
                    placeholder.value = "";
                    placeholder.textContent = "— Select an event —";
                    eventSel.appendChild(placeholder);
                    cluster.events.forEach((ev) => {
                        // events are objects { name, type } — extract the name
                        const evName = (typeof ev === "string") ? ev : ev.name;
                        const opt = document.createElement("option");
                        opt.value = evName;
                        opt.textContent = evName;
                        eventSel.appendChild(opt);
                    });
                }

                clusterSel.addEventListener("change", () => {
                    populateEvents(clusterSel.value);
                });

                // Initial state: dropdowns will be populated by loadSettings() from the server profile
            })();

            async function saveEventSelection() {
                const clusterSel = document.getElementById("select-deca-cluster");
                const eventSel = document.getElementById("select-deca-event");
                const btn = document.getElementById("btn-save-event");
                const eventName = eventSel ? eventSel.value : "";
                if (!eventName) {
                    ErrorManager.show("Please select a cluster and event first.", "error");
                    return;
                }
                await doSave(btn, async () => {
                    const clusterName = clusterSel ? clusterSel.value : "";
                    // UserPrefs.setEvent owns all event writes — server first, cache on confirm
                    const eventId = (typeof getEventIdByName === "function")
                        ? getEventIdByName(eventName)
                        : eventName.toLowerCase().replace(/ /g, "_");
                    const result = await UserPrefs.setEvent(
                        eventId,
                        eventName,
                        clusterName,
                    );
                    if (!result) {
                        ErrorManager.show("Failed to save event selection.", "error");
                        return false;
                    }
                    const lbl = document.getElementById("event-current-label");
                    if (lbl) lbl.textContent = "Currently studying: " + eventName;
                    return true;
                });
            }

            /* ──────────────────────────────────────────────────────────────
       RESET ALL PROGRESS
    ────────────────────────────────────────────────────────────── */
            async function resetProgress() {
                if (!confirm("Reset all progress? This will wipe your session history, scores, and KPI records. This cannot be undone.")) {
                    return;
                }
                const btn = document.getElementById("btn-reset-progress");
                const orig = btn.textContent;
                btn.textContent = "Resetting…";
                btn.disabled = true;
                try {
                    const res = await apiFetch("/auth/progress", { method: "DELETE" });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to reset progress.",
                            "error",
                        );
                    } else {
                        // Also clear local caches
                        try {
                            const keysToRemove = [];
                            for (let i = 0; i < localStorage.length; i++) {
                                const k = localStorage.key(i);
                                if (k && (k.startsWith("ct_qb_") || k.startsWith("ct_correct_qs"))) {
                                    keysToRemove.push(k);
                                }
                            }
                            keysToRemove.forEach((k) => localStorage.removeItem(k));
                        } catch (e) {}
                        ErrorManager.show("All progress has been reset.", "success");
                    }
                } catch (err) {
                    ErrorManager.show("Network error. Please try again.", "error");
                } finally {
                    btn.textContent = orig;
                    btn.disabled = false;
                }
            }

            /* ──────────────────────────────────────────────────────────────
       THEME  (saves immediately on click + applies to page)
    ────────────────────────────────────────────────────────────── */
            function applyTheme(theme) {
                const root = document.documentElement;
                // Remove any existing theme class
                root.classList.remove("theme-light", "theme-dark", "theme-system");

                let effective = theme;
                if (theme === "system") {
                    effective = window.matchMedia("(prefers-color-scheme: light)").matches
                        ? "light"
                        : "dark";
                }

                if (effective === "light") {
                    root.classList.add("theme-light");
                    root.style.colorScheme = "light";
                } else {
                    root.classList.add("theme-dark");
                    root.style.colorScheme = "dark";
                }
            }

            async function selectTheme(el) {
                document
                    .querySelectorAll(".theme-opt")
                    .forEach((o) => o.classList.remove("selected"));
                el.classList.add("selected");
                const theme = el.dataset.theme;

                // Apply immediately so user sees the change
                applyTheme(theme);

                try {
                    const res = await apiFetch("/auth/profile", {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ theme }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to save theme.",
                            "error",
                        );
                    } else {
                        ErrorManager.show("Theme saved.", "success");
                        // Persist for next page load
                        try { localStorage.setItem("ct_theme", theme); } catch(e) {}
                    }
                } catch (err) {
                    ErrorManager.show("Could not save theme.", "error");
                }
            }

            /* ──────────────────────────────────────────────────────────────
       STUDY GOALS  (NEW)
    ────────────────────────────────────────────────────────────── */
            async function saveStudyGoals() {
                const btn = document.getElementById("btn-save-goals");
                const mins = parseInt(
                    document.getElementById("input-study-minutes").value,
                    10,
                );
                const kpis = parseInt(
                    document.getElementById("input-study-kpis").value,
                    10,
                );
                if (isNaN(mins) || mins < 1) {
                    ErrorManager.show(
                        "Please enter a valid daily study goal.",
                        "error",
                    );
                    return;
                }
                if (isNaN(kpis) || kpis < 1) {
                    ErrorManager.show(
                        "Please enter a valid KPI target.",
                        "error",
                    );
                    return;
                }
                await doSave(btn, async () => {
                    const res = await apiFetch("/auth/profile", {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            study_goal_minutes: mins,
                            study_goal_kpis: kpis,
                        }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to save study goals.",
                            "error",
                        );
                        return false;
                    }
                    return true;
                });
            }

            /* ──────────────────────────────────────────────────────────────
       PRIVACY  (NEW)
    ────────────────────────────────────────────────────────────── */
            async function savePrivacy() {
                const btn = document.getElementById("btn-save-privacy");
                await doSave(btn, async () => {
                    const payload = {
                        privacy_track_progress: document
                            .getElementById("toggle-privacy-track")
                            .classList.contains("on"),
                    };
                    const res = await apiFetch("/auth/profile", {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to save privacy settings.",
                            "error",
                        );
                        return false;
                    }
                    return true;
                });
            }

            /* ──────────────────────────────────────────────────────────────
       EXPORT DATA
    ────────────────────────────────────────────────────────────── */
            async function exportData() {
                const btn = document.getElementById("btn-export");
                const orig = btn.textContent;
                btn.textContent = "Exporting…";
                btn.disabled = true;
                try {
                    const res = await apiFetch("/auth/export", {
                        method: "GET",
                    });
                    if (!res.ok) {
                        const data = await res.json().catch(() => ({}));
                        ErrorManager.show(
                            data.detail || "Export failed.",
                            "error",
                        );
                        return;
                    }
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "cluster-trainer-data.json";
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                    ErrorManager.show("Export downloaded.", "success");
                } catch (err) {
                    ErrorManager.show(
                        "Export failed. Please try again.",
                        "error",
                    );
                } finally {
                    btn.textContent = orig;
                    btn.disabled = false;
                }
            }

            /* ──────────────────────────────────────────────────────────────
       DELETE ACCOUNT MODAL
    ────────────────────────────────────────────────────────────── */
            function openDeleteModal() {
                const confirmInput = document.getElementById(
                    "delete-confirm-input",
                );
                const confirmBtn =
                    document.getElementById("btn-confirm-delete");
                confirmInput.value = "";
                confirmBtn.disabled = true;
                document.getElementById("delete-modal").classList.add("open");
                confirmInput.focus();
            }

            function closeDeleteModal() {
                document
                    .getElementById("delete-modal")
                    .classList.remove("open");
            }

            function checkDeleteConfirm() {
                const val = document.getElementById(
                    "delete-confirm-input",
                ).value;
                const btn = document.getElementById("btn-confirm-delete");
                btn.disabled = val !== "DELETE";
            }

            // Close modal on overlay click
            document
                .getElementById("delete-modal")
                .addEventListener("click", function (e) {
                    if (e.target === this) closeDeleteModal();
                });

            async function confirmDelete() {
                const btn = document.getElementById("btn-confirm-delete");
                const origText = btn.textContent;
                btn.textContent = "Deleting…";
                btn.disabled = true;
                try {
                    const res = await apiFetch("/auth/account", {
                        method: "DELETE",
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to delete account.",
                            "error",
                        );
                        btn.textContent = origText;
                        btn.disabled = false;
                        closeDeleteModal();
                    } else {
                        Auth.clear();
                        window.location.href = "/";
                    }
                } catch (err) {
                    ErrorManager.show(
                        "Network error. Please try again.",
                        "error",
                    );
                    btn.textContent = origText;
                    btn.disabled = false;
                }
            }

            /* ──────────────────────────────────────────────────────────────
       UTILITY: doSave
       Wraps a save fn: shows "Saving…" → on success shows "Saved!" briefly.
       fn must return true (success) or false (error).
    ────────────────────────────────────────────────────────────── */
            async function doSave(btn, fn) {
                const orig = btn.textContent;
                btn.textContent = "Saving…";
                btn.disabled = true;
                let ok = false;
                try {
                    ok = !!(await fn());
                } catch (err) {
                    ErrorManager.show("An unexpected error occurred.", "error");
                }
                if (ok) {
                    btn.textContent = "Saved!";
                    btn.disabled = false;
                    setTimeout(() => {
                        if (btn.textContent === "Saved!")
                            btn.textContent = orig;
                    }, 1800);
                } else {
                    btn.textContent = orig;
                    btn.disabled = false;
                }
                return ok;
            }

            /* ──────────────────────────────────────────────────────────────
       LOAD SETTINGS  — fetches /auth/me and populates all fields
    ────────────────────────────────────────────────────────────── */
            async function loadSettings() {
                try {
                    const res = await apiFetch("/auth/me");
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        ErrorManager.show(
                            data.detail || "Failed to load settings.",
                            "error",
                        );
                        clearSkeletons();
                        return;
                    }
                    const u = data.user || data;

                    // ── Profile ──────────────────────────────────────────────
                    const name = u.display_name || "";
                    const email = u.email || "";
                    document.getElementById("input-name").value = name;
                    document.getElementById("input-email").value = email;
                    document.getElementById(
                        "display-name-preview",
                    ).textContent = name || "Your Name";
                    document.getElementById("email-preview").textContent =
                        email;

                    const circle = document.getElementById("avatar-circle");
                    circle.classList.remove("is-loading");
                    document.getElementById("avatar-initials").textContent =
                        getInitials(name);

                    // ── Competition ───────────────────────────────────────────
                    const tier = (
                        u.competition_tier || "districts"
                    ).toLowerCase();
                    const tierEl = document.querySelector(
                        '.comp-opt[data-level="' + tier + '"]',
                    );
                    if (tierEl) {
                        // Visual selection only — label is set from the saved value
                        document.querySelectorAll(".comp-opt").forEach((o) => o.classList.remove("selected"));
                        tierEl.classList.add("selected");
                        const display = tier === "icdc" ? "ICDC" : tier.charAt(0).toUpperCase() + tier.slice(1);
                        document.getElementById("comp-current-label").textContent = "Currently set to: " + display;
                    }

                    // ── Theme ─────────────────────────────────────────────────────
                    const theme = u.theme || "dark";
                    document.querySelectorAll(".theme-opt").forEach((el) => {
                        el.classList.toggle(
                            "selected",
                            el.dataset.theme === theme,
                        );
                    });
                    // Apply theme to the page immediately on load
                    applyTheme(theme);
                    try { localStorage.setItem("ct_theme", theme); } catch(e) {}

                    // ── Study goals ───────────────────────────────────────────
                    if (u.study_goal_minutes != null)
                        document.getElementById("input-study-minutes").value =
                            u.study_goal_minutes;
                    if (u.study_goal_kpis != null)
                        document.getElementById("input-study-kpis").value =
                            u.study_goal_kpis;

                    // ── Privacy ───────────────────────────────────────────────
                    const priv = u.privacy || {};
                    setToggle(
                        "toggle-privacy-track",
                        "lbl-privacy-track",
                        priv.track_progress !== false,
                    );

                    // ── Event / Cluster (server is source of truth) ───────────
                    // hydrateFromProfile syncs cache from the confirmed server value.
                    // It will not overwrite cache if the server has no value yet.
                    UserPrefs.hydrateFromProfile(u);

                    // Populate the dropdowns from the now-reliable cache
                    const resolvedEvent   = UserPrefs.getEvent();
                    const resolvedCluster = UserPrefs.getCluster() || (() => {
                        // Derive cluster from event name if profile didn't store it
                        if (resolvedEvent && typeof CLUSTERS !== "undefined") {
                            const found = CLUSTERS.find(c =>
                                c.events.some(ev => (typeof ev === "string" ? ev : ev.name) === resolvedEvent)
                            );
                            return found ? found.name : "";
                        }
                        return "";
                    })();

                    if (resolvedCluster || resolvedEvent) {
                        const clusterSel = document.getElementById("select-deca-cluster");
                        const eventSel   = document.getElementById("select-deca-event");
                        if (clusterSel && resolvedCluster) {
                            clusterSel.value = resolvedCluster;
                            if (eventSel && typeof CLUSTERS !== "undefined") {
                                const cluster = CLUSTERS.find(c => c.name === resolvedCluster);
                                if (cluster) {
                                    eventSel.innerHTML = "";
                                    const ph = document.createElement("option");
                                    ph.value = ""; ph.textContent = "— Select an event —";
                                    eventSel.appendChild(ph);
                                    cluster.events.forEach(ev => {
                                        const evName = (typeof ev === "string") ? ev : ev.name;
                                        const opt = document.createElement("option");
                                        opt.value = evName; opt.textContent = evName;
                                        eventSel.appendChild(opt);
                                    });
                                    eventSel.disabled = false;
                                    if (resolvedEvent) eventSel.value = resolvedEvent;
                                }
                            }
                        }
                        const lbl = document.getElementById("event-current-label");
                        if (lbl && resolvedEvent) lbl.textContent = "Currently studying: " + resolvedEvent;
                    }

                    // ── Local-only prefs (login notifications) ────────────────
                    const savedLoginNotif =
                        localStorage.getItem("ct_login_notif");
                    if (savedLoginNotif !== null) {
                        setToggle(
                            "toggle-login-notif",
                            "login-notif-label",
                            savedLoginNotif === "1",
                        );
                    }
                    // ── Remove all skeleton states ────────────────────────────
                    clearSkeletons();
                } catch (err) {
                    ErrorManager.show("Could not connect to server.", "error");
                    clearSkeletons();
                }
            }

            /* ──────────────────────────────────────────────────────────────
       AUTH INIT
    ────────────────────────────────────────────────────────────── */
            requireAuth().then(async (user) => {
                if (!user) return;
                initTopbar(user);
                await loadSettings();
            });
