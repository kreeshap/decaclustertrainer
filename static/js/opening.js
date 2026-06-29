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
                openingTourSeen: "ct_openingTourSeen",
            };

            let openingLoadError = false;
            let openingStatusTimer = null;
            let openingTipTimer = null;

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

            function setSavedTier(tier) {
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
            }

            function hasSeenOpeningTour() {
                try {
                    return (
                        localStorage.getItem(STORAGE_KEYS.openingTourSeen) ===
                        "1"
                    );
                } catch (error) {
                    return true;
                }
            }

            function markOpeningTourSeen() {
                try {
                    localStorage.setItem(STORAGE_KEYS.openingTourSeen, "1");
                } catch (error) {
                    // ignore storage errors
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
                        body: JSON.stringify({ cluster: clusterName }),
                    });
                    if (!res.ok) return false;
                    const data = await res.json().catch(() => null);
                    if (!data?.user) return false;
                    OPENING_STATE.user = data.user;
                    OPENING_STATE.clusterObj =
                        findClusterByName(data.user.cluster) ||
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
                const eventId = (typeof getEventIdByName === "function")
                    ? getEventIdByName(eventName)
                    : String(eventName || "").toLowerCase().replace(/ /g, "_");
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
                    OPENING_STATE.clusterObj =
                        findClusterByName(OPENING_STATE.user.cluster || "") ||
                        null;
                    // For sign-in users, skip cluster selection if user exists
                    // For sign-up users, only skip if they have a saved cluster
                    if (OPENING_STATE.source === 'signin' || OPENING_STATE.clusterObj) {
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
            function activatePhase(el) {
                el.classList.add("active");
            }

            function deactivatePhase(el) {
                el.classList.remove("active");
            }

            function transitionTo(from, to, delay = 0) {
                return new Promise((res) => {
                    setTimeout(() => {
                        deactivatePhase(from);
                        setTimeout(() => {
                            activatePhase(to);
                            res();
                        }, 800);
                    }, delay);
                });
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

            function showOpeningTip(message, duration = 5000) {
                const el = document.getElementById("opening-tip");
                const text = document.getElementById("opening-tip-text");
                if (!el || !text) return;
                if (hasSeenOpeningTour()) return;

                window.clearTimeout(openingTipTimer);
                text.textContent = message || "";
                el.classList.remove("hidden");
                el.classList.add("show");

                if (duration > 0) {
                    openingTipTimer = window.setTimeout(
                        () => hideOpeningTip(true),
                        duration,
                    );
                }
            }

            function hideOpeningTip(markSeen = false) {
                const el = document.getElementById("opening-tip");
                if (!el) return;

                window.clearTimeout(openingTipTimer);
                el.classList.remove("show");
                window.setTimeout(() => el.classList.add("hidden"), 200);
                if (markSeen) markOpeningTourSeen();
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
                const card = document.createElement("div");
                card.className = "cluster-card";
                card.style.setProperty("--accent", c.color);
                card.style.setProperty("--glow", c.glow);
                card.innerHTML = `
    <div class="cluster-name">${c.name}</div>
    <div class="cluster-count">${c.events.length ? c.events.length + " events" : "Core event"}</div>
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
                                    // Returning user — swap "Welcome to" for "Welcome back"
                                    welcomeToEl.textContent = "Welcome back,";
                                    showWelcome(
                                        OPENING_STATE.clusterObj || CLUSTERS[0],
                                        phBrand,
                                        null,
                                        { forceWelcomeBack: true },
                                    );
                                } else {
                                    activatePhase(phGrid);
                                    if (!hasSeenOpeningTour()) {
                                        showOpeningTip(
                                            "Choose your cluster to begin.",
                                        );
                                    }
                                }
                            }, 800);
                        }, 3500);
                    }, 680);
                }, 0);
            }

                // ── OPEN CLUSTER ───────────────────────────────────────────────────────────────
            async function openCluster(index) {
                const cluster = CLUSTERS[index];
                hideOpeningTip(true);

                if (OPENING_STATE.user && !OPENING_STATE.user.cluster) {
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
                        item.addEventListener("click", () => {
                            // Derive slug the same way the server does: lowercase + underscores
                            const evSlug = evName.toLowerCase().replace(/ /g, '_');
                            UserPrefs.setEvent(evSlug, evName, cluster.name);
                            openLevelSelection(cluster, phEvents);
                        });
                        list.appendChild(item);
                    });
                }, 140);

                deactivatePhase(phGrid);
                activatePhase(phEvents);
            }

            function openLevelSelection(cluster, fromPhase) {
                const currentTier = getSavedTier();
                hideOpeningTip(true);

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
                deactivatePhase(fromPhase);
                activatePhase(phLevel);
                list.innerHTML = "";
                TIERS.forEach((tier) => {
                    const item = document.createElement("button");
                    item.type = "button";
                    item.className = "event-item";
                    item.textContent =
                        tier + (tier === currentTier ? " ✓" : "");
                    item.style.setProperty("--active-accent", cluster.color);
                    const chooseTier = () => {
                        setSavedTier(tier);
                        showWelcome(cluster, phLevel, tier);
                    };
                    item.addEventListener("pointerdown", chooseTier);
                    item.addEventListener("click", chooseTier);
                    list.appendChild(item);
                });
            }

            document
                .getElementById("back-btn")
                .addEventListener("click", () => {
                    deactivatePhase(phEvents);
                    setTimeout(() => activatePhase(phGrid), 800);
                });

            document
                .getElementById("level-back-btn")
                .addEventListener("click", () => {
                    deactivatePhase(phLevel);
                    setTimeout(() => activatePhase(phGrid), 800);
                });

            // ── WELCOME SPLASH ─────────────────────────────────────────────────────────────
            function showWelcome(cluster, fromPhase, tier, options = {}) {
                const selectedTier = tier || getSavedTier();
                const displayName = (
                    OPENING_STATE.user?.display_name || DISPLAY_NAME
                ).split(" ")[0];

                if (options.forceWelcomeBack) {
                    // Show their saved event name as context, not a redundant "welcome back"
                    const savedEvent = UserPrefs.getEvent();
                    welcomeSubEl.textContent = savedEvent ? `Ready to study ${savedEvent},` : "Good to see you again,";
                } else {
                    welcomeSubEl.textContent = selectedTier
                        ? `Studying for ${selectedTier},`
                        : "Let's get started,";
                }

                document.getElementById("welcome-name").textContent =
                    displayName;
                document.getElementById("welcome-name").style.color =
                    cluster.color;

                deactivatePhase(fromPhase);
                setTimeout(() => activatePhase(phWelcome), 800);
            }

            phWelcome.addEventListener("click", () => {
                markOpeningTourSeen();
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
                            { forceWelcomeBack: true },
                        );
                    } else {
                        activatePhase(phGrid);
                        if (!hasSeenOpeningTour()) {
                            showOpeningTip("Choose your cluster to begin.");
                        }
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
