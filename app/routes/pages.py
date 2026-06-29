from flask import Blueprint, jsonify, render_template

from ..ai import call_gemini_json, call_groq

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/api/debug/ai")
def debug_ai():
    """Quick smoke-test for both AI keys. Hit /api/debug/ai in your browser."""
    probe = [{"role": "user", "content": 'Reply with valid JSON: {"ok": true}'}]

    groq_data, groq_err = call_groq(probe, max_tokens=20)
    gemini_data, gemini_err = call_gemini_json(
        'Reply with valid JSON: {"ok": true}', max_tokens=20
    )

    return jsonify(
        {
            "groq": {"ok": groq_err is None, "result": groq_data, "error": groq_err},
            "gemini": {
                "ok": gemini_err is None,
                "result": gemini_data,
                "error": gemini_err,
            },
        }
    )


@pages_bp.get("/")
def home():
    return render_template("signon.html")


@pages_bp.get("/terms")
def terms():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Terms</title>
      </head>
      <body style="margin:0;min-height:100vh;background:#081415;color:#eef7f7;font-family:Barlow,Arial,sans-serif;padding:32px;line-height:1.6;">
        <main style="max-width:760px;margin:0 auto;">
          <h1>Terms of Service</h1>
          <p>This is a placeholder terms page for Cluster Trainer.</p>
          <p>Replace this with your final legal terms before launch.</p>
        </main>
      </body>
    </html>
    """


@pages_bp.get("/privacy")
def privacy():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Privacy</title>
      </head>
      <body style="margin:0;min-height:100vh;background:#081415;color:#eef7f7;font-family:Barlow,Arial,sans-serif;padding:32px;line-height:1.6;">
        <main style="max-width:760px;margin:0 auto;">
          <h1>Privacy Policy</h1>
          <p>This is a placeholder privacy page for Cluster Trainer.</p>
          <p>Replace this with your final privacy policy before launch.</p>
        </main>
      </body>
    </html>
    """


@pages_bp.get("/app/index.html")
def app_index():
    return render_template("signon.html")


@pages_bp.get("/reset-password")
def reset_password():
    return render_template("signon.html")


@pages_bp.get("/app/opening.html")
def opening():
    return render_template("opening.html")


@pages_bp.get("/app/greeting.html")
def greeting():
    return render_template("greeting.html")


@pages_bp.get("/app/dashboard.html")
def dashboard():
    return render_template("dashboard.html")


@pages_bp.get("/app/learn.html")
def learn():
    return render_template("learn.html")


@pages_bp.get("/app/practicequestions.html")
def practice_questions():
    return render_template("practicequestions.html")


@pages_bp.get("/app/practiceroleplays.html")
def practice_roleplays():
    return render_template("practiceroleplays.html")


@pages_bp.get("/app/adminpanel.html")
def admin_panel():
    return render_template("adminpanel.html")


@pages_bp.get("/app/settings.html")
def settings():
    return render_template("settings.html")


@pages_bp.get("/app/settings-old.html")
def settings_old():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Settings</title>
        <script src="/static/js/common.js"></script>
        <style>
          body {
            margin: 0;
            min-height: 100vh;
            background: #081415;
            color: #eef7f7;
            font-family: Barlow, Arial, sans-serif;
          }
          .settings-shell {
            padding: 28px;
            max-width: 520px;
            margin: 0 auto;
          }
          h1 {
            margin-bottom: 18px;
            font-size: 2rem;
          }
          .settings-section {
            margin-top: 24px;
            padding: 20px;
            border: 1px solid rgba(238,247,247,0.12);
            border-radius: 18px;
            background: rgba(255,255,255,0.04);
          }
          .option-label {
            display: block;
            margin-bottom: 12px;
            padding: 14px 18px;
            border: 1px solid rgba(238,247,247,0.09);
            border-radius: 14px;
            cursor: pointer;
            transition: border-color 200ms ease, background 200ms ease;
          }
          .option-label:hover {
            border-color: rgba(0,194,224,0.35);
            background: rgba(0,194,224,0.08);
          }
          .option-label input {
            margin-right: 14px;
          }
          .save-button {
            margin-top: 18px;
            padding: 12px 18px;
            border: none;
            border-radius: 12px;
            background: #00c2e0;
            color: #081415;
            font-weight: 700;
            cursor: pointer;
          }
          .status {
            margin-top: 14px;
            color: #a3e635;
            min-height: 1.4em;
          }
          .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            padding: 18px 28px;
            border-bottom: 1px solid rgba(238,247,247,0.08);
            background: rgba(0,0,0,0.18);
            position: sticky;
            top: 0;
            z-index: 10;
          }
          .app-brand {
            font-size: 1.1rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            cursor: pointer;
          }
          .topbar-actions {
            display: flex;
            gap: 10px;
            align-items: center;
          }
          .pill {
            border: 1px solid rgba(238,247,247,0.2);
            border-radius: 999px;
            background: rgba(255,255,255,0.08);
            color: #eef7f7;
            padding: 8px 14px;
            cursor: pointer;
          }
        </style>
      </head>
      <body>
        <div class="topbar">
          <div class="app-brand">Cluster Trainer</div>
          <div class="topbar-actions">
            <div id="topbar-name">User</div>
            <button class="pill" id="btn-settings" type="button">Settings</button>
            <button class="pill" id="btn-logout" type="button">Log out</button>
          </div>
        </div>
        <main class="settings-shell" id="settings-shell"></main>
        <script>
          const STORAGE_KEYS = {
            competitionTier: 'ct_competitionTier'
          };

          function getSavedTier() {
            try {
              return localStorage.getItem(STORAGE_KEYS.competitionTier) || '';
            } catch (error) {
              return '';
            }
          }

          function setSavedTier(tier) {
            try {
              localStorage.setItem(STORAGE_KEYS.competitionTier, tier);
            } catch (error) {
            }
          }

          function renderSettings() {
            const currentTier = getSavedTier();
            const shell = document.getElementById('settings-shell');
            shell.innerHTML = `
              <h1>Settings</h1>
              <div class="settings-section">
                <p style="margin-bottom: 16px; color: #9cc6c6;">Select the competition tier you are studying for.</p>
                <label class="option-label"><input type="radio" name="competition-tier" value="Districts" ${currentTier === 'Districts' ? 'checked' : ''}>Districts</label>
                <label class="option-label"><input type="radio" name="competition-tier" value="States" ${currentTier === 'States' ? 'checked' : ''}>States</label>
                <label class="option-label"><input type="radio" name="competition-tier" value="ICDC" ${currentTier === 'ICDC' ? 'checked' : ''}>ICDC</label>
                <button class="save-button" id="save-tier">Save Tier</button>
                <div class="status" id="status-message">${currentTier ? `Current selection: ${currentTier}` : 'No competition tier selected yet.'}</div>
              </div>
            `;

            document.getElementById('save-tier').addEventListener('click', () => {
              const selected = document.querySelector('input[name="competition-tier"]:checked');
              if (!selected) {
                document.getElementById('status-message').textContent = 'Please select a tier before saving.';
                return;
              }
              setSavedTier(selected.value);
              document.getElementById('status-message').textContent = 'Settings saved successfully.';
            });
          }

          requireAuth().then((user) => {
            if (!user) return;
            initTopbar(user);
            renderSettings();
          });
        </script>
      </body>
    </html>
    """
