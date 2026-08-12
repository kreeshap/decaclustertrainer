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

            const OPENING_STATE = {
                source: null,
                user: null,
                skipCluster: false,
                clusterObj: null,
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
                            showWelcome(cluster, phLevel, tier);
                        }
                    };
                    item.addEventListener("click", chooseTier);
                    list.appendChild(item);
                });
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
