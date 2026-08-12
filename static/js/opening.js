            const DISPLAY_NAME = (() => {
                try {
                    return (
                        localStorage.getItem("displayName") || "Competitor"
                    ).split(" ")[0];
                } catch (error) {
                    return "Competitor";
                }
            })();

            const TIERS = ["Districts", "SCDC", "ICDC"];

            const STORAGE_KEYS = {
                competitionTier: "ct_competitionTier",
            };

            let openingLoadError = false;
            let openingStatusTimer = null;

            function getSavedTier() {
                try {
                    return (
                        localStorage.getItem(STORAGE_KEYS.competitionTier) ||
                        null
                    );
                } catch (error) {
                    return null;
                }
            }

            async function setSavedTier(tier) {
                try {
                    if (tier) {
                        localStorage.setItem(
                            STORAGE_KEYS.competitionTier,
                            tier,
                        );
                    }
                } catch (error) {
                    // ignore storage errors
                }
                const token = getStoredAuthToken();
                if (!token || !tier) return true;
                try {
                    const response = await fetch("/auth/profile", {
                        method: "PUT",
                        headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`},
                        credentials: "same-origin",
                        body: JSON.stringify({competition_tier: tier.toLowerCase()}),
                    });
                    return response.ok;
                } catch (error) {
                    return false;
                }
            }

            async function saveUserLocation(stateCode, subdivisionId, status) {
                const token = getStoredAuthToken();
                if (!token) return true;
                try {
                    const response = await fetch("/auth/profile", {
                        method: "PUT",
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${token}`,
                        },
                        credentials: "same-origin",
                        body: JSON.stringify({
                            state_code: stateCode,
                            deca_subdivision_id: subdivisionId || null,
                            subdivision_status: status,
                        }),
                    });
                    if (!response.ok) return false;
                    const data = await response.json().catch(() => null);
                    if (data?.user) OPENING_STATE.user = data.user;
                    return true;
                } catch (error) {
                    return false;
                }
            }

            const OPENING_STATE = {
                source: null,
                user: null,
                skipCluster: false,
                clusterObj: null,
                selectedCluster: null,
                selectedStateCode: "",
            };

            function getOpeningSource() {
                try {
                    const raw = sessionStorage.getItem("ct_opening_intro");
                    if (!raw) return null;
                    const data = JSON.parse(raw);
                    return data?.source || null;
                } catch (error) {
                    return null;
                }
            }

            function getStoredAuthToken() {
                return (
                    localStorage.getItem("ct_token") ||
                    sessionStorage.getItem("ct_token") ||
                    null
                );
            }

            async function fetchCurrentUser() {
                const token = getStoredAuthToken();
                if (!token) return null;

                try {
                    const res = await fetch("/auth/me", {
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${token}`,
                        },
                        credentials: "same-origin",
                    });
                    if (!res.ok) return null;
                    const payload = await res.json().catch(() => null);
                    return payload?.user || null;
                } catch (error) {
                    openingLoadError = true;
                    return null;
                }
            }

            // findClusterByName, findClusterByEvent, clusterColor are now in /static/js/clusters.js

            async function saveUserCluster(clusterName) {
                const token = getStoredAuthToken();
                if (!token) return false;

                try {
                    const res = await fetch("/auth/profile", {
                        method: "PUT",
                        headers: {
                            "Content-Type": "application/json",
                            Authorization: `Bearer ${token}`,
                        },
                        credentials: "same-origin",
                        body: JSON.stringify({ default_cluster: clusterName }),
                    });
                    if (!res.ok) return false;
                    const data = await res.json().catch(() => null);
                    if (!data?.user) return false;
                    OPENING_STATE.user = data.user;
                    OPENING_STATE.clusterObj =
                        findClusterByName(data.user.default_cluster) ||
                        OPENING_STATE.clusterObj;
                    return true;
                } catch (error) {
                    return false;
                }
            }

            // Save both cluster and event to the profile (fire-and-forget — doesn't block the UI)
            // NOTE: kept for saveUserCluster backward compat only. Event writes go through UserPrefs.setEvent().
            async function saveUserEvent(clusterName, eventName) {
                // Delegate entirely to UserPrefs — it owns this write path
                const eventId = getEventIdByName(eventName);
                await UserPrefs.setEvent(
                    eventId,
                    eventName,
                    clusterName,
                );
            }

            async function initOpeningContext() {
                OPENING_STATE.source = getOpeningSource();
                OPENING_STATE.user = await fetchCurrentUser();
                if (OPENING_STATE.user) {
                    if (OPENING_STATE.user.competition_tier) {
                        try {
                            localStorage.setItem(STORAGE_KEYS.competitionTier,
                                OPENING_STATE.user.competition_tier.toUpperCase() === "SCDC" || OPENING_STATE.user.competition_tier.toUpperCase() === "ICDC"
                                    ? OPENING_STATE.user.competition_tier.toUpperCase()
                                    : "Districts");
                        } catch (error) {}
                    }
                    OPENING_STATE.clusterObj =
                        findClusterByName(OPENING_STATE.user.default_cluster || "") ||
                        null;
                    // For sign-in users, skip cluster selection if user exists
                    // For sign-up users, only skip if they have a saved cluster
                    if (typeof isSupportedBetaEventId === "function" && isSupportedBetaEventId(OPENING_STATE.user.default_event_id || OPENING_STATE.user.default_event)) {
                        OPENING_STATE.skipCluster = true;
                    }
                }
            }

            // CLUSTERS is loaded from /static/js/clusters.js

            // ── PARTICLES ─────────────────────────────────────────────────────────────────
            const canvas = document.getElementById("particle-canvas");
            const ctx = canvas.getContext("2d");
            let particles = [];

            function resizeCanvas() {
                canvas.width = window.innerWidth;
                canvas.height = window.innerHeight;
            }
            resizeCanvas();
            window.addEventListener("resize", resizeCanvas);

            function spawnShards(x, y) {
                const count = 32;
                for (let i = 0; i < count; i++) {
                    const angle =
                        (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
                    const speed = 5 + Math.random() * 16;
                    // mix white and cyan shards
                    const isCyan = Math.random() > 0.55;
                    particles.push({
                        x,
                        y,
                        vx: Math.cos(angle) * speed,
                        vy: Math.sin(angle) * speed,
                        size: 3 + Math.random() * 9,
                        rot: Math.random() * Math.PI * 2,
                        rotV: (Math.random() - 0.5) * 0.25,
                        life: 1,
                        color: isCyan ? "#00c2e0" : "#f0fafa",
                    });
                }
            }

            function animParticles() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                particles = particles.filter((p) => p.life > 0);
                for (const p of particles) {
                    p.x += p.vx;
                    p.y += p.vy;
                    p.vy += 0.45;
                    p.vx *= 0.97;
                    p.life -= 0.032;
                    p.rot += p.rotV;
                    ctx.save();
                    ctx.globalAlpha = Math.max(0, p.life);
                    ctx.translate(p.x, p.y);
                    ctx.rotate(p.rot);
                    ctx.fillStyle = p.color;
                    ctx.fillRect(
                        -p.size / 2,
                        -p.size / 2,
                        p.size,
                        p.size * 0.55,
                    );
                    ctx.restore();
                }
                requestAnimationFrame(animParticles);
            }
            animParticles();

            // ── PHASE HELPERS ──────────────────────────────────────────────────────────────
            let phaseNavigationVersion = 0;
            let phaseTransitionTimer = null;

            function activatePhase(el) {
                // Every phase is a full-screen state; never allow two to remain active.
                document.querySelectorAll(".phase.active").forEach((phase) => {
                    if (phase !== el) phase.classList.remove("active");
                });
                el.classList.add("active");
            }

            function deactivatePhase(el) {
                el.classList.remove("active");
            }

            function transitionPhase(from, to, delay = 0) {
                const version = ++phaseNavigationVersion;
                window.clearTimeout(phaseTransitionTimer);
                deactivatePhase(from);
                phaseTransitionTimer = window.setTimeout(() => {
                    if (version !== phaseNavigationVersion) return;
                    activatePhase(to);
                }, delay);
                return version;
            }

            function setOpeningStatus(message, kind = "info", duration = 3000) {
                const el = document.getElementById("opening-status");
                if (!el) return;

                window.clearTimeout(openingStatusTimer);
                el.textContent = message || "";
                el.dataset.kind = kind;
                el.classList.toggle("hidden", !message);
                el.classList.add("show");

                if (message && duration > 0) {
                    openingStatusTimer = window.setTimeout(() => {
                        el.classList.remove("show");
                        window.setTimeout(
                            () => el.classList.add("hidden"),
                            200,
                        );
                    }, duration);
                }
            }

            function renderSkeletonList(listEl, count = 3, compact = false) {
                if (!listEl) return;
                listEl.innerHTML = "";
                listEl.setAttribute("aria-busy", "true");
                listEl.classList.add("opening-skeleton");
                for (let i = 0; i < count; i++) {
                    const item = document.createElement("div");
                    item.className = compact
                        ? "skeleton-item sm"
                        : "skeleton-item";
                    listEl.appendChild(item);
                }
            }

            function clearSkeletonList(listEl) {
                if (!listEl) return;
                listEl.removeAttribute("aria-busy");
                listEl.classList.remove("opening-skeleton");
            }

            // ── BUILD CLUSTER GRID ────────────────────────────────────────────────────────
            const gridEl = document.getElementById("cluster-grid");
            CLUSTERS.forEach((c, i) => {
                const eventCount = c.events.length;
                const card = document.createElement("div");
                card.className = "cluster-card";
                card.style.setProperty("--accent", c.color);
                card.style.setProperty("--glow", c.glow);
                card.innerHTML = `
    <div class="cluster-name">${c.name}</div>
    <div class="cluster-count">${eventCount} ${eventCount === 1 ? "event" : "events"}</div>
  `;
                card.addEventListener("click", () => openCluster(i));
                gridEl.appendChild(card);
            });

            // ── PHASE REFERENCES ──────────────────────────────────────────────────────────
            const phExplode = document.getElementById("phase-explode");
            const phBrand = document.getElementById("phase-brand");
            const phGrid = document.getElementById("phase-grid");
            const phEvents = document.getElementById("phase-events");
            const phLevel = document.getElementById("phase-level");
            const phState = document.getElementById("phase-state");
            const phSubdivision = document.getElementById("phase-subdivision");
            const phSubdivisionHelp = document.getElementById("phase-subdivision-help");
            const phWelcome = document.getElementById("phase-welcome");

            const welcomeToEl = document.getElementById("welcome-to");
            const brandFallEl = document.getElementById("brand-fall");
            const welcomeSubEl = document.getElementById("welcome-sub");

            // ── SEQUENCE ───────────────────────────────────────────────────────────────────
            function startSequence() {
                const cx = window.innerWidth / 2;
                const cy = window.innerHeight / 2;

                // Spawn shards during orb burst
                setTimeout(() => spawnShards(cx, cy), 190);
                setTimeout(() => spawnShards(cx + 8, cy - 8), 270);
                setTimeout(() => spawnShards(cx - 8, cy + 8), 340);

                // Switch to brand phase
                setTimeout(() => {
                    deactivatePhase(phExplode);

                    setTimeout(() => {
                        activatePhase(phBrand);

                        // Stagger: welcome-to fades in first
                        welcomeToEl.style.transition = "opacity 800ms ease";
                        welcomeToEl.style.opacity = "0";
                        setTimeout(() => {
                            welcomeToEl.style.opacity = "1";
                        }, 100);

                        // Brand drops down
                        brandFallEl.style.transition = "none";
                        brandFallEl.style.transform = "translateY(-110px)";
                        brandFallEl.style.opacity = "0";
                        setTimeout(() => {
                            brandFallEl.style.transition =
                                "transform 1000ms cubic-bezier(0.22,1,0.36,1), opacity 700ms ease";
                            brandFallEl.style.transform = "translateY(0)";
                            brandFallEl.style.opacity = "1";
                        }, 300);

                        // Hold → fade to grid or welcome
                        setTimeout(() => {
                            deactivatePhase(phBrand);
                            setTimeout(() => {
                                if (OPENING_STATE.skipCluster) {
                                    showWelcome(
                                        OPENING_STATE.clusterObj || CLUSTERS[0],
                                        phBrand,
                                        null,
                                        { returning: true },
                                    );
                                } else {
                                    activatePhase(phGrid);
                                }
                            }, 800);
                        }, 3500);
                    }, 680);
                }, 0);
            }

                // ── OPEN CLUSTER ───────────────────────────────────────────────────────────────
            async function openCluster(index) {
                const cluster = CLUSTERS[index];

                if (OPENING_STATE.user && !OPENING_STATE.user.default_cluster) {
                    await saveUserCluster(cluster.name);
                }

                if (cluster.events.length === 0) {
                    openLevelSelection(cluster, phGrid);
                    return;
                }

                document.getElementById("events-title").textContent =
                    cluster.name;
                document.getElementById("events-title").style.color =
                    cluster.color;
                document.getElementById("events-accent-bar").style.background =
                    cluster.color;
                document.body.style.setProperty(
                    "--active-accent",
                    cluster.color,
                );

                const list = document.getElementById("events-list");
                renderSkeletonList(
                    list,
                    Math.min(Math.max(cluster.events.length, 3), 5),
                );
                window.setTimeout(() => {
                    clearSkeletonList(list);
                    list.innerHTML = "";
                    cluster.events.forEach((ev) => {
                        // events are objects { name, type } — extract the name
                        const evName = (typeof ev === "string") ? ev : ev.name;
                        const item = document.createElement("div");
                        item.type = "button";
                        item.className = "event-item";
                        item.textContent = evName;
                        item.style.setProperty(
                            "--active-accent",
                            cluster.color,
                        );
                        item.addEventListener("click", async () => {
                            const selectionVersion = phaseNavigationVersion;
                            const evSlug = getEventIdByName(evName);
                            const saved = await UserPrefs.setEvent(evSlug, evName, cluster.name);
                            if (
                                saved &&
                                selectionVersion === phaseNavigationVersion &&
                                phEvents.classList.contains("active")
                            ) {
                                openLevelSelection(cluster, phEvents);
                            }
                        });
                        list.appendChild(item);
                    });
                }, 140);

                transitionPhase(phGrid, phEvents);
            }

            function openLevelSelection(cluster, fromPhase) {
                const currentTier = getSavedTier();
                OPENING_STATE.selectedCluster = cluster;

                document.getElementById("level-title").textContent =
                    "Competition Tier";
                document.getElementById("level-accent-bar").style.background =
                    cluster.color;
                document.body.style.setProperty(
                    "--active-accent",
                    cluster.color,
                );

                const list = document.getElementById("level-list");
                list.style.pointerEvents = "auto";
                transitionPhase(fromPhase, phLevel);
                list.innerHTML = "";
                TIERS.forEach((tier) => {
                    const item = document.createElement("button");
                    item.type = "button";
                    item.className = "event-item";
                    item.textContent =
                        tier + (tier === currentTier ? " ✓" : "");
                    item.style.setProperty("--active-accent", cluster.color);
                    const chooseTier = async () => {
                        const selectionVersion = phaseNavigationVersion;
                        item.disabled = true;
                        const saved = await setSavedTier(tier);
                        item.disabled = false;
                        if (
                            saved &&
                            selectionVersion === phaseNavigationVersion &&
                            phLevel.classList.contains("active")
                        ) {
                            openStateSelection(cluster, phLevel);
                        }
                    };
                    item.addEventListener("click", chooseTier);
                    list.appendChild(item);
                });
            }

            function openStateSelection(cluster, fromPhase) {
                document.getElementById("state-accent-bar").style.background =
                    cluster.color;
                document.body.style.setProperty(
                    "--active-accent",
                    cluster.color,
                );

                const list = document.getElementById("state-list");
                list.innerHTML = "";
                DECA_LOCATION_CONFIG.states.forEach((state) => {
                    const item = document.createElement("button");
                    item.type = "button";
                    item.className = "event-item";
                    item.disabled = !state.isActive;
                    item.innerHTML = state.isActive
                        ? `<span class="event-item-main">${state.name}</span>`
                        : `<span class="event-item-main">${state.name}</span><span class="event-item-meta">More states will be added later</span>`;
                    item.style.setProperty("--active-accent", cluster.color);
                    if (state.isActive) {
                        item.addEventListener("click", () => {
                            OPENING_STATE.selectedStateCode = state.code;
                            openSubdivisionSelection(cluster, state, phState);
                        });
                    }
                    list.appendChild(item);
                });

                transitionPhase(fromPhase, phState);
            }

            function openSubdivisionSelection(cluster, state, fromPhase) {
                const label = state.subdivisionLabel || "District";
                document.getElementById("subdivision-title").textContent =
                    `Which DECA ${label} are you in?`;
                document.getElementById("subdivision-subtitle").textContent =
                    `Not sure? Your conference date or location might help.`;
                document.getElementById("subdivision-accent-bar").style.background =
                    cluster.color;
                document.body.style.setProperty(
                    "--active-accent",
                    cluster.color,
                );

                const list = document.getElementById("subdivision-list");
                list.innerHTML = "";
                getDecaSubdivisions(state.code).forEach((subdivision) => {
                    const item = document.createElement("button");
                    item.type = "button";
                    item.className = "event-item";
                    item.innerHTML =
                        `<span class="event-item-main">${subdivision.displayName}</span>` +
                        `<span class="event-item-meta">${subdivisionConferenceLine(subdivision.id)}</span>`;
                    item.style.setProperty("--active-accent", cluster.color);
                    item.addEventListener("click", async () => {
                        const selectionVersion = phaseNavigationVersion;
                        item.disabled = true;
                        const saved = await saveUserLocation(
                            state.code,
                            subdivision.id,
                            "user_selected",
                        );
                        item.disabled = false;
                        if (
                            saved &&
                            selectionVersion === phaseNavigationVersion &&
                            phSubdivision.classList.contains("active")
                        ) {
                            showWelcome(cluster, phSubdivision, null);
                        } else if (!saved) {
                            setOpeningStatus(
                                "We could not save your district. Please try again.",
                                "warning",
                                5000,
                            );
                        }
                    });
                    list.appendChild(item);
                });

                const unknown = document.createElement("button");
                unknown.type = "button";
                unknown.className = "event-item";
                unknown.innerHTML =
                    `<span class="event-item-main">I'm not sure</span>` +
                    `<span class="event-item-meta">You can add your ${label.toLowerCase()} later.</span>`;
                unknown.style.setProperty("--active-accent", cluster.color);
                unknown.addEventListener("click", () => {
                    openSubdivisionHelp(cluster, state, phSubdivision);
                });
                list.appendChild(unknown);

                transitionPhase(fromPhase, phSubdivision);
            }

            function openSubdivisionHelp(cluster, state, fromPhase) {
                document.getElementById("subdivision-help-accent-bar").style.background =
                    cluster.color;
                const list = document.getElementById("subdivision-help-list");
                list.innerHTML = "";

                const find = document.createElement("button");
                find.type = "button";
                find.className = "event-item";
                find.innerHTML =
                    `<span class="event-item-main">Find my district</span>` +
                    `<span class="event-item-meta">Your DECA advisor can tell you your district. You may also recognize it from your district conference date or location.</span>`;
                find.style.setProperty("--active-accent", cluster.color);
                find.addEventListener("click", () => {
                    openSubdivisionSelection(cluster, state, phSubdivisionHelp);
                });
                list.appendChild(find);

                const later = document.createElement("button");
                later.type = "button";
                later.className = "event-item";
                later.innerHTML =
                    `<span class="event-item-main">I'll add it later</span>` +
                    `<span class="event-item-meta">You will still have complete access to studying KPIs.</span>`;
                later.style.setProperty("--active-accent", cluster.color);
                later.addEventListener("click", async () => {
                    const selectionVersion = phaseNavigationVersion;
                    later.disabled = true;
                    const saved = await saveUserLocation(state.code, null, "unknown");
                    later.disabled = false;
                    if (
                        saved &&
                        selectionVersion === phaseNavigationVersion &&
                        phSubdivisionHelp.classList.contains("active")
                    ) {
                        showWelcome(cluster, phSubdivisionHelp, null);
                    } else if (!saved) {
                        setOpeningStatus(
                            "We could not save your district status. Please try again.",
                            "warning",
                            5000,
                        );
                    }
                });
                list.appendChild(later);

                transitionPhase(fromPhase, phSubdivisionHelp);
            }

            document
                .getElementById("back-btn")
                .addEventListener("click", () => {
                    transitionPhase(phEvents, phGrid, 800);
                });

            document
                .getElementById("level-back-btn")
                .addEventListener("click", () => {
                    transitionPhase(phLevel, phGrid, 800);
                });

            document
                .getElementById("state-back-btn")
                .addEventListener("click", () => {
                    transitionPhase(phState, phLevel, 800);
                });

            document
                .getElementById("subdivision-back-btn")
                .addEventListener("click", () => {
                    transitionPhase(phSubdivision, phState, 800);
                });

            document
                .getElementById("subdivision-help-back-btn")
                .addEventListener("click", () => {
                    const state = getDecaState(OPENING_STATE.selectedStateCode);
                    if (state && OPENING_STATE.selectedCluster) {
                        openSubdivisionSelection(
                            OPENING_STATE.selectedCluster,
                            state,
                            phSubdivisionHelp,
                        );
                    } else {
                        transitionPhase(phSubdivisionHelp, phState, 800);
                    }
                });

            // ── WELCOME SPLASH ─────────────────────────────────────────────────────────────
            function showWelcome(cluster, fromPhase, tier, options = {}) {
                const displayName = (
                    OPENING_STATE.user?.display_name || DISPLAY_NAME
                ).split(" ")[0];

                if (options.returning) {
                    welcomeSubEl.textContent = "Welcome back";
                } else {
                    welcomeSubEl.textContent = "Welcome to Cluster Trainer,";
                }

                document.getElementById("welcome-name").textContent =
                    displayName;
                document.getElementById("welcome-name").style.color =
                    cluster.color;

                transitionPhase(fromPhase, phWelcome, 160);
            }

            phWelcome.addEventListener("click", () => {
                window.location.href = "/app/dashboard.html";
            });

            // ── BOOT ───────────────────────────────────────────────────────────────────────
            document.addEventListener("DOMContentLoaded", async () => {
                await initOpeningContext();

                if (OPENING_STATE.user) {
                    deactivatePhase(phExplode);

                    if (OPENING_STATE.skipCluster) {
                        showWelcome(
                            OPENING_STATE.clusterObj || CLUSTERS[0],
                            phExplode,
                            null,
                            { returning: true },
                        );
                    } else {
                        activatePhase(phGrid);
                    }
                } else {
                    startSequence();
                }

                if (openingLoadError) {
                    window.setTimeout(() => {
                        setOpeningStatus(
                            "We could not load your saved profile from Supabase, but you can still continue.",
                            "warning",
                            6000,
                        );
                    }, 4200);
                }
            });
