#!/usr/bin/env python3
"""Patch settings.html and settings.js to implement requested changes."""
import re
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── settings.html ────────────────────────────────────────────────────────────
html_path = os.path.join(BASE, "templates", "settings.html")
with open(html_path, encoding="utf-8") as f:
    html = f.read()

# ── 1. Remove Notifications sidebar item ─────────────────────────────────────
# Find the block starting at the notifications anchor and remove it
html = re.sub(
    r'\s{16}<a\s+class="sidebar-item"\s+href="#notifications"[^>]*>.*?</a>\n',
    "\n",
    html,
    flags=re.DOTALL,
)

# ── 2. Remove Notifications main section ──────────────────────────────────────
html = re.sub(
    r'[ \t]*<!-- ={40,}\n\s+NOTIFICATIONS\s*\n\s+=+\s+-->.*?</div>\s*\n\s*<!-- ={40,}',
    "\n                <!-- ════════════════════════════════════════",
    html,
    flags=re.DOTALL,
)

# ── 3. Replace the old cluster prefs block + randomize/save cluster rows ──────
#    Target: the loose div with default cluster / session time selects
#    followed by the randomize + save cluster setting-row-group
OLD_CLUSTER_BLOCK = re.compile(
    r'[ \t]*<!-- cluster preferences section removed -->.*?</div>\s*\n\s*<!-- ={40,}',
    re.DOTALL,
)

NEW_CLUSTER_BLOCK = """\
                <!-- ════════════════════════════════════════
           EVENT SELECTION
      ════════════════════════════════════════ -->
                <div class="settings-section" id="event-selection">
                    <div class="settings-section-title">Event Selection</div>
                    <p style="font-size:0.85rem;color:var(--muted);margin:0 0 14px;line-height:1.55;">
                        Choose the DECA cluster and event you want to study.
                    </p>
                    <div style="padding:16px 18px;background:rgba(19,47,47,0.3);border:1px solid var(--border);border-radius:8px;margin-bottom:14px;">
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
                            <div class="field-group">
                                <label for="select-deca-cluster">DECA Cluster</label>
                                <select class="field-select" id="select-deca-cluster" onchange="onClusterChange()">
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
                                <strong>Save event selection</strong>
                                <span>This event will be used in Learn mode</span>
                            </div>
                            <button class="row-btn primary" id="btn-save-event" onclick="saveEventSelection()">
                                Save
                            </button>
                        </div>
                    </div>
                </div>

                <!-- ════════════════════════════════════════"""

html = OLD_CLUSTER_BLOCK.sub(NEW_CLUSTER_BLOCK, html)

# ── 4. Fix Reset All Progress button (remove disabled + badge-soon) ───────────
html = html.replace(
    '''<strong
                                    >Reset all progress<span class="badge-soon"
                                        >Coming soon</span
                                    ></strong
                                >''',
    '''<strong>Reset all progress</strong>''',
)
html = html.replace(
    '''<button class="row-btn danger" disabled>
                                Reset progress
                            </button>''',
    '''<button class="row-btn danger" id="btn-reset-progress" onclick="resetProgress()">
                                Reset progress
                            </button>''',
)

# ── 5. Add event-selection sidebar item ───────────────────────────────────────
# Insert after study-goals sidebar item
if 'id="event-selection"' not in html or 'event-selection' not in html:
    pass  # already handled by block replacement above

# Add sidebar link for event-selection after Appearance link
html = html.replace(
    '''                <a
                    class="sidebar-item"
                    href="#study-goals"
                    onclick="navTo(event, 'study-goals')"
                >''',
    '''                <a
                    class="sidebar-item"
                    href="#event-selection"
                    onclick="navTo(event, 'event-selection')"
                >
                    <svg viewBox="0 0 24 24">
                        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                        <polyline points="9 22 9 12 15 12 15 22"></polyline>
                    </svg>
                    Event Selection
                </a>
                <a
                    class="sidebar-item"
                    href="#study-goals"
                    onclick="navTo(event, 'study-goals')"
                >''',
)

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

print("settings.html patched OK")
print("  Notifications section removed:", "lbl-notif-reminders" not in html)
print("  Old cluster block removed:", "select-cluster" not in html)
print("  Event selection added:", "select-deca-cluster" in html)
print("  Reset progress enabled:", 'btn-reset-progress' in html)
