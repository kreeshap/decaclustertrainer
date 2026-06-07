/**
 * clusters.js — Single source of truth for DECA cluster + event structure.
 *
 * Loaded by opening.html, learn.html, and any other page that needs
 * the full cluster/event list. Keep this file in sync with the
 * "performance indicator jsons/" folder structure.
 *
 * Each entry:
 *   name   — DECA career cluster display name
 *   color  — accent hex used for UI highlights
 *   glow   — rgba version for glow/shadow effects
 *   folder — subfolder name under "performance indicator jsons/"
 *            (omit if no KPI JSONs exist yet)
 *   events — ordered list of event names; file names inside `folder`
 *            must match these exactly (e.g. "Accounting Application Series.json")
 */

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
      "Business Law and Ethics Team Decision Making",
      "Human Resources Management Series",
      "Business Services Operations Research"
    ]
  },
  {
    name: "Entrepreneurship",
    color: "#9ca3af",
    glow: "rgba(156,163,175,0.2)",
    folder: "entrepreneurship",
    events: [
      "Entrepreneurship Team Decision Making",
      "Entrepreneurship Series"
    ]
  },
  {
    name: "Finance",
    color: "#22c55e",
    glow: "rgba(34,197,94,0.2)",
    folder: "finance",
    events: [
      "Financial Services Team Decision Making",
      "Accounting Application Series",
      "Business Finance Series",
      "Finance Operations Research",
      "Financial Consulting"
    ]
  },
  {
    name: "Hospitality & Tourism",
    color: "#38bdf8",
    glow: "rgba(56,189,248,0.2)",
    folder: "hospitality_tourism",
    events: [
      "Hospitality Services Team Decision Making",
      "Hotel and Lodging Management Series",
      "Travel and Tourism Team Decision Making",
      "Quick Serve Restaurant Management Series",
      "Restaurant and Food Service Management Series",
      "Hospitality and Tourism Operations Research",
      "Hospitality and Tourism Professional Selling"
    ]
  },
  {
    name: "Marketing",
    color: "#f87171",
    glow: "rgba(248,113,113,0.2)",
    folder: "marketing",
    events: [
      "Buying and Merchandising Team Decision Making",
      "Marketing Management Team Decision Making",
      "Sports and Entertainment Marketing Team Decision Making",
      "Apparel and Accessories Marketing",
      "Automotive Services Marketing",
      "Business Services Marketing Series",
      "Food Marketing Series",
      "Marketing Communications Series",
      "Retail Merchandising Series",
      "Sports and Entertainment Marketing Series",
      "Buying and Merchandising Operations Research",
      "Sports and Entertainment Marketing Operations Research",
      "Prepared Event",
      "Professional Selling"
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
      "Principles of Business Management and Administration",
      "Principles of Entrepreneurship",
      "Principles of Finance",
      "Principles of Hospitality",
      "Principles of Marketing"
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
  return CLUSTERS.find(c => c.events.includes(eventName)) || null;
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
