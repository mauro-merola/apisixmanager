# -*- coding: utf-8 -*-
"""
app_run.py - v1.0.0
Orquestrador de inicialização — APISIX Gateway Management Platform.
Suporta modo dev (sem OIDC) e produção (com OIDC).
"""
import os
import socket
import logging
from flask import Flask

from api import config as config_module
from api.config import FLASK_APP, FLASK_ENV, FLASK_HOST, FLASK_PORT
from api.routes.dash_routes import dash_bp
from api.routes.gateway_routes import gateway_bp
from api.routes.api_routes import api_admin_bp
from api.routes.consumer_routes import consumer_bp
from api.routes.ssl_routes import ssl_bp
from api.routes.health_routes import health_bp
from api.db.database import inicializar_banco

logger = logging.getLogger(__name__)


def obter_ip_local():
    try:
        hostname = socket.gethostname()
        ip_local = socket.gethostbyname(hostname)
        if ip_local and not ip_local.startswith("127."):
            return ip_local
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip_local = s.getsockname()[0]
        s.close()
        return ip_local
    except Exception:
        return "127.0.0.1"


class FlaskApp:
    @staticmethod
    def create_app():
        api_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(api_dir)
        flask_app = Flask(
            import_name=FLASK_APP,
            template_folder=os.path.join(root_dir, "templates"),
            static_folder=os.path.join(root_dir, "static"),
            root_path=root_dir
        )
        return flask_app

    @staticmethod
    def configure_app(flask_app):
        flask_app.config.from_object(config_module)

        from api.config import FLASK_KEY_VAULT
        flask_app.secret_key = FLASK_KEY_VAULT or "dev-secret-key-local-only-change-in-prod"

        inicializar_banco()

        is_dev = str(FLASK_ENV).lower() in ("development", "dev", "")

        if is_dev:
            FlaskApp._configure_dev_auth(flask_app)
        else:
            from api.routes.auth_routes import init_auth
            init_auth(flask_app)

        # Registra todos os blueprints
        flask_app.register_blueprint(dash_bp)
        flask_app.register_blueprint(gateway_bp)
        flask_app.register_blueprint(api_admin_bp)
        flask_app.register_blueprint(consumer_bp)
        flask_app.register_blueprint(ssl_bp)
        flask_app.register_blueprint(health_bp)

    @staticmethod
    def _configure_dev_auth(flask_app):
        """Auto-login em modo dev local, sem OIDC."""
        from flask import Blueprint, redirect, url_for, session
        from flask_login import LoginManager, UserMixin, login_user, logout_user

        login_manager = LoginManager()
        login_manager.init_app(flask_app)
        login_manager.login_view = "auth.login"

        class DevUser(UserMixin):
            def __init__(self):
                self.id = "dev-user"
                self.name = "Mauro Merola"
                self.email = "mauro.merola@portoseguro.com.br"

        @login_manager.user_loader
        def load_user(user_id):
            return DevUser()

        dev_bp = Blueprint("auth", __name__)

        @dev_bp.route("/login")
        def login():
            user = DevUser()
            login_user(user, remember=True)
            session["user"] = {"id": user.id, "name": user.name, "email": user.email}
            return redirect(url_for("dash.dashboard"))

        @dev_bp.route("/logout")
        def logout():
            logout_user()
            session.clear()
            return redirect(url_for("auth.login"))

        @dev_bp.route("/getAToken")
        def authorized():
            return redirect(url_for("auth.login"))

        flask_app.register_blueprint(dev_bp)

        @flask_app.before_request
        def auto_login_dev():
            from flask_login import current_user
            if not current_user.is_authenticated:
                user = DevUser()
                login_user(user, remember=True)
                session["user"] = {"id": user.id, "name": user.name, "email": user.email}

        logger.info("[DEV MODE] OIDC desativado. Usuário 'mauro.merola@portoseguro.com.br' logado automaticamente.")

    @staticmethod
    def run_app(flask_app):
        host_bind = "0.0.0.0"
        ip_rede = obter_ip_local()
        port = FLASK_PORT
        threads = int(os.environ.get("WAITRESS_THREADS", 8))
        channel_timeout = int(os.environ.get("WAITRESS_CHANNEL_TIMEOUT", 120))

        print("\n" + "=" * 65)
        print("    APISIX GATEWAY MANAGEMENT PLATFORM")
        print("=" * 65)
        print(f"  -> http://127.0.0.1:{port}")
        print(f"  -> http://{ip_rede}:{port}")
        print(f"  -> Modo: {FLASK_ENV}")
        print("=" * 65 + "\n")

        try:
            from waitress import serve
            serve(flask_app, host=host_bind, port=port, threads=threads, channel_timeout=channel_timeout)
        except ImportError:
            flask_app.run(host=host_bind, port=port, debug=True, threaded=True)


app = FlaskApp.create_app()
FlaskApp.configure_app(app)

if __name__ == "__main__":
    FlaskApp.run_app(app)