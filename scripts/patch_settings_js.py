#!/usr/bin/env python3
"""Patch settings.js: fix loadSettings to remove notif loading, add theme apply."""
import os, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
js_path = os.path.join(BASE, "static", "js", "settings.js")

with open(js_path, encoding="utf-8") as f:
    js = f.read()

# Find the Theme block through Notifications block in loadSettings
THEME_START = "// \u2500\u2500 Theme \u2500"
STUDY_GOALS_START = "// \u2500\u2500 Study goals \u2500"

ts = js.find(THEME_START)
sg = js.find(STUDY_GOALS_START)
assert ts != -1, "Theme marker not found"
assert sg != -1, "Study goals marker not found"
assert ts < sg

old_block = js[ts:sg]
print("Old block:")
print(repr(old_block[:300]))

new_block = """// \u2500\u2500 Theme \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
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

                    """

js = js[:ts] + new_block + js[sg:]

# Also update the comp level loading so it doesn't update the label inline
# The label is now set only on save, but loadSettings should set it once on load
COMP_LOAD = """                    // \u2500\u2500 Competition \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
                    const tier = (
                        u.competition_tier || "districts"
                    ).toLowerCase();
                    const tierEl = document.querySelector(
                        '.comp-opt[data-level="' + tier + '"]',
                    );
                    if (tierEl) setComp(tierEl);"""

if COMP_LOAD in js:
    COMP_NEW = """                    // \u2500\u2500 Competition \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
                    const tier = (
                        u.competition_tier || "districts"
                    ).toLowerCase();
                    const tierEl = document.querySelector(
                        '.comp-opt[data-level="' + tier + '"]',
                    );
                    if (tierEl) {
                        // Only set visual selection, not the label (label updates on save)
                        document.querySelectorAll(".comp-opt").forEach((o) => o.classList.remove("selected"));
                        tierEl.classList.add("selected");
                        // Set label to reflect the currently saved value
                        const display = tier === "icdc" ? "ICDC" : tier.charAt(0).toUpperCase() + tier.slice(1);
                        document.getElementById("comp-current-label").textContent = "Currently set to: " + display;
                    }"""
    js = js.replace(COMP_LOAD, COMP_NEW)
    print("Comp loading updated")
else:
    print("WARNING: Comp loading block not found, skipping")

with open(js_path, "w", encoding="utf-8") as f:
    f.write(js)

print("settings.js patched:")
print("  applyTheme in loadSettings:", "applyTheme(theme)" in js)
print("  Notif toggles removed from loadSettings:", "toggle-notif-reminders" not in js.split("loadSettings")[1].split("clearSkeletons")[0] if "loadSettings" in js else "N/A")
