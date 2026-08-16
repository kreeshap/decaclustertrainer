from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .config import BASE_DIR
from .routes.admin import admin_bp
from .routes.auth import auth_bp
from .routes.learn import learn_bp
from .routes.pages import pages_bp


def create_app():
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(learn_bp)
    app.register_blueprint(admin_bp)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Keep API failures machine-readable while preserving normal page errors."""
        if isinstance(error, HTTPException):
            return error
        if request.path.startswith("/api/"):
            app.logger.exception("Unhandled API error on %s", request.path)
            return jsonify({"error": "Internal server error"}), 500
        app.logger.exception("Unhandled page error on %s", request.path)
        return "Internal server error", 500

    return app


app = create_app()
