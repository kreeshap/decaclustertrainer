#!/usr/bin/env python3
"""Fix comp loading in loadSettings."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
js_path = os.path.join(BASE, "static", "js", "settings.js")

with open(js_path, encoding="utf-8") as f:
    js = f.read()

OLD = """                    if (tierEl) setComp(tierEl);"""

NEW = """                    if (tierEl) {
                        // Visual selection only — label is set from the saved value
                        document.querySelectorAll(".comp-opt").forEach((o) => o.classList.remove("selected"));
                        tierEl.classList.add("selected");
                        const display = tier === "icdc" ? "ICDC" : tier.charAt(0).toUpperCase() + tier.slice(1);
                        document.getElementById("comp-current-label").textContent = "Currently set to: " + display;
                    }"""

if OLD in js:
    js = js.replace(OLD, NEW)
    print("Comp load block patched")
else:
    print("ERROR: Old block not found")

with open(js_path, "w", encoding="utf-8") as f:
    f.write(js)
