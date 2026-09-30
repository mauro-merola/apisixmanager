# -*- coding: utf-8 -*-
"""
===============================================================================
ROTAS DE HEALTH CHECK
===============================================================================
"""
import json
import os
import logging
from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)
health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health():
    versao_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'versao.json')
    versao = "unknown"
    try:
        with open(versao_path, 'r') as f:
            versao = json.load(f).get("versao", "unknown")
    except Exception:
        pass

    return jsonify({
        "status": "healthy",
        "application": "apisix-gateway-manager",
        "version": versao
    }), 200


@health_bp.route('/ready')
def ready():
    return jsonify({"status": "ready"}), 200
