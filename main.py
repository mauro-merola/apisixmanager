
# -*- coding: utf-8 -*-
"""
===============================================================================
PONTO DE ENTRADA DA APLICAÇÃO (ENTRYPOINT WSGI)
===============================================================================
Arquivo     : main.py
Versão      : 1.0.0
Data        : 29/09/2026
Autor       : Equipe de Governança de APIs
===============================================================================
"""
import sys
import os
import logging

# Força o diretório raiz no caminho de busca de módulos do Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.app_run import FlaskApp

# [DEBUG_OBSERVABILIDADE] Flag para desativar fácil posteriormente
ENABLE_DEBUG_LOGS = True
DEBUG_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coleta_debug.log")


class HopByHopCleanerMiddleware:
    HOP_BY_HOP_HEADERS = {
        'connection', 'keep-alive', 'proxy-authenticate',
        'proxy-authorization', 'te', 'trailers',
        'transfer-encoding', 'upgrade'
    }

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            clean_headers = [
                (name, value) for name, value in headers
                if name.lower() not in self.HOP_BY_HOP_HEADERS
            ]
            return start_response(status, clean_headers, exc_info)

        return self.wsgi_app(environ, custom_start_response)


# Inicializa a aplicação Flask
app = FlaskApp.create_app()
FlaskApp.configure_app(app)
app.wsgi_app = HopByHopCleanerMiddleware(app.wsgi_app)


if __name__ == "__main__":
    log_format = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if ENABLE_DEBUG_LOGS else logging.INFO)

    # Clean handlers existentes para evitar duplicações
    root_logger.handlers.clear()

    # [DEBUG_OBSERVABILIDADE] Handler de Terminal (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if ENABLE_DEBUG_LOGS else logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # [DEBUG_OBSERVABILIDADE] Handler dedicado para gravação do arquivo de log
    if ENABLE_DEBUG_LOGS:
        file_handler = logging.FileHandler(DEBUG_LOG_FILE, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(file_handler)
        logging.info(f"🔍 [OBSERVABILIDADE] Arquivo de log ativado em: {DEBUG_LOG_FILE}")

    logging.getLogger("waitress").setLevel(logging.INFO)

    FlaskApp.run_app(app)