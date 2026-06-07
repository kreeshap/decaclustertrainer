#!/usr/bin/env python3
"""
Patch settings.html:
 - Remove Notifications section (and old cluster prefs block in same slice)
 - Replace with Event Selection block
 - Fix Reset all progress button
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html_path = os.path.join(BASE, "templates", "settings.html")

with open(html_path, encoding="utf-8") as f:
    html = f.read()

# ── Find the exact slice: from the NOTIFICATIONS comment to just before STUDY GOALS comment ──
NOTIF_COMMENT = "<!-- \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n           NOTIFICATIONS"
STUDY_COMMENT = "<!-- \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\n       STUDY GOALS"

start = html.find(NOTIF_COMMENT)
end = html.find(STUDY_COMMENT)

assert start != -1, "NOTIFICATIONS comment not found"
assert end != -1, "STUDY GOALS comment not found"
assert start < end

# Build replacement: Event Selection section then APPEARANCE & THEME (already present before this block)
# We just replace notifications+cluster block with the event selection section.
NEW_BLOCK = """\
<!-- \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
           EVENT SELECTION
      \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550 -->
                <div class="settings-section" id="event-selection">
                    <div class="settings-section-title">Event Selection</div>
                    <p style="font-size:0.85rem;color:var(--muted);margin:0 0 14px;line-height:1.55;">
                        Choose the DECA cluster and event you want to study in Learn mode.
                    </p>
                    <div style="padding:16px 18px;background:rgba(19,47,47,0.3);border:1px solid var(--border);border-radius:8px;margin-bottom:14px;">
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
                            <div class="field-group">
                                <label for="select-deca-cluster">DECA Cluster</label>
                                <select class="field-select" id="select-deca-cluster">
                                    <option value="">— Select a cluster —</option>
                                </select>
                            </div>
                            <div class="field-group">
                                <label for="select-deca-event">Event</label>
                                <select class="field-select" id="select-deca-event" disabled>
                                    <option value="">— Select a cluster first —</option>
                                </select>
                            </div>
                        </div>
                    </div>
                    <div class="setting-row-group">
                        <div class="setting-row">
                            <div class="row-label">
                                <strong id="event-current-label">Currently studying: —</strong>
                                <span>Saved event is loaded when you start Learn mode</span>
                            </div>
                            <button class="row-btn primary" id="btn-save-event" onclick="saveEventSelection()">
                                Save
                            </button>
                        </div>
                    </div>
                </div>

                """

html = html[:start] + NEW_BLOCK + html[end:]

# ── Fix Reset All Progress button ────────────────────────────────────────────
html = html.replace(
    '<strong\n                                    >Reset all progress<span class="badge-soon"\n                                        >Coming soon</span\n                                    ></strong\n                                >',
    '<strong>Reset all progress</strong>'
)
html = html.replace(
    '<button class="row-btn danger" disabled>\n                                Reset progress\n                            </button>',
    '<button class="row-btn danger" id="btn-reset-progress" onclick="resetProgress()">\n                                Reset progress\n                            </button>'
)

# ── Add Event Selection sidebar link ─────────────────────────────────────────
# Insert between Appearance and Study Goals
APPEARANCE_LINK_START = '''                <a
                    class="sidebar-item"
                    href="#appearance"'''
STUDY_LINK_START = '''                <a
                    class="sidebar-item"
                    href="#study-goals"'''

insert_after = html.find(APPEARANCE_LINK_START)
if insert_after != -1:
    # Find the closing </a> of the appearance link
    close_a = html.find("</a>", insert_after) + 4
    EVENT_LINK = """
                <a
                    class="sidebar-item"
                    href="#event-selection"
                    onclick="navTo(event, 'event-selection')"
                >
                    <svg viewBox="0 0 24 24">
                        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                        <polyline points="9 22 9 12 15 12 15 22"></polyline>
                    </svg>
                    Event Selection
                </a>"""
    html = html[:close_a] + EVENT_LINK + html[close_a:]

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

print("settings.html patched:")
print("  Notifications section removed:", "lbl-notif-reminders" not in html)
print("  Old cluster block removed:", "select-cluster" not in html and "saveClusterPrefs" not in html)
print("  Event selection added:", "select-deca-cluster" in html)
print("  Reset progress enabled:", 'btn-reset-progress' in html)
print("  Event Selection sidebar link:", "event-selection" in html)
