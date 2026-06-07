from flask import Flask

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
    return app


app = create_app()
