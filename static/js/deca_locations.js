const DECA_LOCATION_CONFIG = Object.freeze({
  states: [
    {
      code: "MI",
      name: "Michigan",
      isActive: true,
      subdivisionType: "district",
      subdivisionLabel: "District",
      subdivisionLabelPlural: "Districts",
      districtSelectionEnabled: true,
    },
    {
      code: "",
      name: "More states coming soon",
      isActive: false,
      subdivisionType: "",
      subdivisionLabel: "",
      subdivisionLabelPlural: "",
      districtSelectionEnabled: false,
    },
  ],
  subdivisions: [
    { id: "MI-D1", stateCode: "MI", type: "district", number: 1, name: "District 1", displayName: "District 1", isActive: true, season: "2026-27" },
    { id: "MI-D2", stateCode: "MI", type: "district", number: 2, name: "District 2", displayName: "District 2", isActive: true, season: "2026-27" },
    { id: "MI-D3", stateCode: "MI", type: "district", number: 3, name: "District 3", displayName: "District 3", isActive: true, season: "2026-27" },
    { id: "MI-D4", stateCode: "MI", type: "district", number: 4, name: "District 4", displayName: "District 4", isActive: true, season: "2026-27" },
    { id: "MI-D5", stateCode: "MI", type: "district", number: 5, name: "District 5", displayName: "District 5", isActive: true, season: "2026-27" },
    { id: "MI-D6", stateCode: "MI", type: "district", number: 6, name: "District 6", displayName: "District 6", isActive: true, season: "2026-27" },
    { id: "MI-D7", stateCode: "MI", type: "district", number: 7, name: "District 7", displayName: "District 7", isActive: true, season: "2026-27" },
    { id: "MI-D8", stateCode: "MI", type: "district", number: 8, name: "District 8", displayName: "District 8", isActive: true, season: "2026-27" },
    { id: "MI-D9", stateCode: "MI", type: "district", number: 9, name: "District 9", displayName: "District 9", isActive: true, season: "2026-27" },
  ],
  conferences: [
    { id: "MI-D1-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D1", name: "Michigan DECA District 1 Conference", startDate: "2026-12-10", endDate: "2026-12-10", venue: "Saginaw Valley State University", city: "University Center", status: "confirmed" },
    { id: "MI-D2-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D2", name: "Michigan DECA District 2 Conference", startDate: null, endDate: null, venue: null, city: null, status: "tba" },
    { id: "MI-D3-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D3", name: "Michigan DECA District 3 Conference", startDate: "2027-01-15", endDate: "2027-01-15", venue: "Western Michigan University", city: "Kalamazoo", status: "confirmed" },
    { id: "MI-D4-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D4", name: "Michigan DECA District 4 Conference", startDate: "2027-01-06", endDate: "2027-01-06", venue: "Eastern Michigan University", city: "Ypsilanti", status: "confirmed" },
    { id: "MI-D5-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D5", name: "Michigan DECA District 5 Conference", startDate: "2027-01-07", endDate: "2027-01-07", venue: "Eastern Michigan University", city: "Ypsilanti", status: "confirmed" },
    { id: "MI-D6-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D6", name: "Michigan DECA District 6 Conference", startDate: null, endDate: null, venue: null, city: null, status: "tba" },
    { id: "MI-D7-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D7", name: "Michigan DECA District 7 Conference", startDate: "2026-12-15", endDate: "2026-12-15", venue: "Macomb Community College", city: "Warren", status: "confirmed" },
    { id: "MI-D8-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D8", name: "Michigan DECA District 8 Conference", startDate: "2026-12-16", endDate: "2026-12-16", venue: "Wayne County Community College Taylor Campus", city: "Taylor", status: "confirmed" },
    { id: "MI-D9-2027", season: "2026-27", level: "district", stateCode: "MI", subdivisionId: "MI-D9", name: "Michigan DECA District 9 Conference", startDate: "2027-01-08", endDate: "2027-01-08", venue: "Eastern Michigan University", city: "Ypsilanti", status: "confirmed" },
  ],
});

function getActiveDecaStates() {
  return DECA_LOCATION_CONFIG.states.filter((state) => state.isActive);
}

function getDecaState(stateCode) {
  const code = String(stateCode || "").trim().toUpperCase();
  return DECA_LOCATION_CONFIG.states.find((state) => state.code === code) || null;
}

function getDecaSubdivisions(stateCode) {
  const code = String(stateCode || "").trim().toUpperCase();
  return DECA_LOCATION_CONFIG.subdivisions.filter(
    (subdivision) => subdivision.stateCode === code && subdivision.isActive,
  );
}

function getDecaSubdivision(subdivisionId) {
  return DECA_LOCATION_CONFIG.subdivisions.find(
    (subdivision) => subdivision.id === subdivisionId,
  ) || null;
}

function getDecaConferenceForSubdivision(subdivisionId) {
  return DECA_LOCATION_CONFIG.conferences.find(
    (conference) => conference.subdivisionId === subdivisionId,
  ) || null;
}

function formatConferenceShortDate(dateText) {
  if (!dateText) return "Date TBA";
  const date = new Date(`${dateText}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "Date TBA";
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function subdivisionConferenceLine(subdivisionId) {
  const conference = getDecaConferenceForSubdivision(subdivisionId);
  if (!conference || conference.status === "tba") return "Date TBA";
  const date = formatConferenceShortDate(conference.startDate);
  const venue = conference.venue || "Location TBA";
  return `${date} - ${venue}`;
}
