/**
 * clusters.js — Single source of truth for DECA cluster + event structure.
 *
 * Each event entry:
 *   name      — display name (must match JSON filename stem)
 *   type      — 'exam' | 'tdm' | 'series' | 'principles' | 'operations'
 *               exam      = written exam only (no roleplay component)
 *               tdm       = Team Decision Making (roleplay-heavy)
 *               series    = Individual series event (exam + roleplay)
 *               principles= Principles event (vocab/concept/application only)
 *               operations= Operations Research (written + presentation)
 */

const EVENT_TYPES = {
    exam:       'exam',
    tdm:        'tdm',
    series:     'series',
    principles: 'principles',
    operations: 'operations',
};

const EVENT_ID_OVERRIDES = {
  "Financial Services Team Decision Making": "financial_services_tdm",
};

const EVENT_ID_ALIASES = {
  "financial_services_team_decision_making": "financial_services_tdm",
  "financial services team decision making": "financial_services_tdm",
};

const BETA_EVENT_IDS = Object.freeze([
  "accounting_application_series",
  "business_finance_series",
  "financial_services_tdm",
]);

function isSupportedBetaEventId(value) {
  return BETA_EVENT_IDS.includes(getEventIdByName(value));
}

function supportedBetaEvents(cluster) {
  return (cluster?.events || []).filter((ev) => {
    const name = typeof ev === "string" ? ev : ev.name;
    return isSupportedBetaEventId(name);
  });
}

const CLUSTERS = [
  {
    name: "Business Administration Core",
    color: "#4a7fa5",
    glow: "rgba(74,127,165,0.25)",
    folder: null,
    events: []
  },
  {
    name: "Business Management & Administration",
    color: "#f5c400",
    glow: "rgba(245,196,0,0.2)",
    folder: "business_management",
    events: [
      { name: "Business Law and Ethics Team Decision Making", type: "tdm" },
      { name: "Human Resources Management Series",           type: "series" },
      { name: "Business Services Operations Research",        type: "operations" },
    ]
  },
  {
    name: "Entrepreneurship",
    color: "#9ca3af",
    glow: "rgba(156,163,175,0.2)",
    folder: "entrepreneurship",
    events: [
      { name: "Entrepreneurship Team Decision Making", type: "tdm" },
      { name: "Entrepreneurship Series",               type: "series" },
    ]
  },
  {
    name: "Finance",
    color: "#22c55e",
    glow: "rgba(34,197,94,0.2)",
    folder: "finance",
    events: [
      { name: "Financial Services Team Decision Making", type: "tdm" },
      { name: "Accounting Application Series",           type: "series" },
      { name: "Business Finance Series",                 type: "series" },
      { name: "Finance Operations Research",             type: "operations" },
      { name: "Financial Consulting",                    type: "exam" },
    ]
  },
  {
    name: "Hospitality & Tourism",
    color: "#38bdf8",
    glow: "rgba(56,189,248,0.2)",
    folder: "hospitality_tourism",
    events: [
      { name: "Hospitality Services Team Decision Making",          type: "tdm" },
      { name: "Hotel and Lodging Management Series",                type: "series" },
      { name: "Travel and Tourism Team Decision Making",            type: "tdm" },
      { name: "Quick Serve Restaurant Management Series",           type: "series" },
      { name: "Restaurant and Food Service Management Series",      type: "series" },
      { name: "Hospitality and Tourism Operations Research",        type: "operations" },
      { name: "Hospitality and Tourism Professional Selling",       type: "series" },
    ]
  },
  {
    name: "Marketing",
    color: "#f87171",
    glow: "rgba(248,113,113,0.2)",
    folder: "marketing",
    events: [
      { name: "Buying and Merchandising Team Decision Making",             type: "tdm" },
      { name: "Marketing Management Team Decision Making",                 type: "tdm" },
      { name: "Sports and Entertainment Marketing Team Decision Making",   type: "tdm" },
      { name: "Apparel and Accessories Marketing",                         type: "series" },
      { name: "Automotive Services Marketing",                             type: "series" },
      { name: "Business Services Marketing Series",                        type: "series" },
      { name: "Food Marketing Series",                                     type: "series" },
      { name: "Marketing Communications Series",                           type: "series" },
      { name: "Retail Merchandising Series",                               type: "series" },
      { name: "Sports and Entertainment Marketing Series",                 type: "series" },
      { name: "Buying and Merchandising Operations Research",              type: "operations" },
      { name: "Sports and Entertainment Marketing Operations Research",    type: "operations" },
      { name: "Prepared Event",                                            type: "exam" },
      { name: "Professional Selling",                                      type: "series" },
    ]
  },
  {
    name: "Personal Financial Literacy",
    color: "#a3e635",
    glow: "rgba(163,230,53,0.2)",
    folder: "personal_finance",
    events: []
  },
  {
    name: "Principles",
    color: "#a78bfa",
    glow: "rgba(167,139,250,0.2)",
    folder: "principles",
    events: [
      { name: "Principles of Business Management and Administration", type: "principles" },
      { name: "Principles of Entrepreneurship",                       type: "principles" },
      { name: "Principles of Finance",                                type: "principles" },
      { name: "Principles of Hospitality",                            type: "principles" },
      { name: "Principles of Marketing",                              type: "principles" },
    ]
  }
];

/**
 * Look up a cluster object by its name.
 * @param {string} name
 * @returns {object|null}
 */
function findClusterByName(name) {
  return CLUSTERS.find(c => c.name === name) || null;
}

/**
 * Find which cluster owns a given event name.
 * @param {string} eventName
 * @returns {object|null}
 */
function findClusterByEvent(eventName) {
  return CLUSTERS.find(c =>
    c.events.some(e => (typeof e === 'string' ? e : e.name) === eventName)
  ) || null;
}

/**
 * Get the event type for a given event name.
 * Returns 'series' as the default (most common event type).
 * @param {string} eventName
 * @returns {string}
 */
function getEventType(eventName) {
  for (const cluster of CLUSTERS) {
    for (const ev of cluster.events) {
      const name = typeof ev === 'string' ? ev : ev.name;
      if (name === eventName) {
        return typeof ev === 'string' ? 'series' : (ev.type || 'series');
      }
    }
  }
  return 'series';
}

/**
 * Get the canonical event_id slug for a given event display name.
 * Uses known overrides for legacy JSON/file-name mismatches.
 * @param {string} eventName
 * @returns {string}
 */
function getEventIdByName(eventName) {
  const name = String(eventName || "").trim();
  if (!name) return "";
  const lowered = name.toLowerCase();
  if (EVENT_ID_ALIASES[lowered]) return EVENT_ID_ALIASES[lowered];
  if (EVENT_ID_OVERRIDES[name]) return EVENT_ID_OVERRIDES[name];
  if (EVENT_ID_OVERRIDES[lowered]) return EVENT_ID_OVERRIDES[lowered];
  return lowered.replace(/ /g, "_");
}

function getEventNameById(eventId) {
  const canonicalId = getEventIdByName(eventId);
  for (const cluster of CLUSTERS) {
    for (const event of cluster.events) {
      const name = typeof event === "string" ? event : event.name;
      if (getEventIdByName(name) === canonicalId) return name;
    }
  }
  return "";
}

/**
 * Return the accent color for a given DECA cluster name.
 * Falls back to the app's default cyan if not found.
 * @param {string} clusterName
 * @returns {string}
 */
function clusterColor(clusterName) {
  const c = findClusterByName(clusterName);
  return c ? c.color : '#00c2e0';
}
