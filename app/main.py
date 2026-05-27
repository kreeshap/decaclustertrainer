from pathlib import Path

from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


@app.get("/")
def home():
    return render_template("signon.html")


@app.get("/app/dashboard.html")
def dashboard():
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Cluster Trainer - Dashboard</title>
        <style>
          body {
            font-family: Arial, sans-serif;
            background: #0b1f1f;
            color: #f0fafa;
            display: grid;
            place-items: center;
            min-height: 100vh;
            margin: 0;
          }
        </style>
      </head>
      <body>
        <main>
          <h1>Dashboard</h1>
          <p>You are signed in.</p>
        </main>
      </body>
    </html>
    """


@app.post("/auth/signin")
def signin():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""

    if not email or not password:
        return jsonify({"detail": "Please fill in all fields."}), 400

    return jsonify({"access_token": "demo-token"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
