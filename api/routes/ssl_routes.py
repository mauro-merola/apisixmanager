# -*- coding: utf-8 -*-
"""
===============================================================================
ROTAS DE GESTÃO DE CERTIFICADOS SSL
===============================================================================
"""
import logging
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from api.db.database import listar_gateways, obter_gateway, registrar_auditoria
from api.services.apisix_client import get_client_for_gateway, _extract_items, extract_resource_value

logger = logging.getLogger(__name__)
ssl_bp = Blueprint('ssl', __name__, url_prefix='/ssl')


def _user_email():
    return str(getattr(current_user, 'email', '') or getattr(current_user, 'id', '')).strip().lower()


@ssl_bp.route('/')
@login_required
def index():
    gateways = listar_gateways()
    gw_id = request.args.get('gateway_id', type=int)
    ssl_list = []
    selected_gw = None
    error_msg = None

    if gw_id:
        selected_gw = obter_gateway(gw_id)
        if selected_gw:
            client = get_client_for_gateway(selected_gw)
            try:
                resp = client.list_ssls()
                if resp["ok"]:
                    ssl_list = [extract_resource_value(i) for i in _extract_items(resp)]
                elif resp.get("error"):
                    error_msg = resp["error"]
            except Exception as e:
                error_msg = str(e)

    return render_template(
        'ssl_certs.html',
        gateways=gateways,
        selected_gw=selected_gw,
        ssl_certs=ssl_list,
        error_msg=error_msg,
        current_user=current_user,
    )


@ssl_bp.route('/create/<int:gw_id>', methods=['POST'])
@login_required
def criar_ssl(gw_id):
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404

    client = get_client_for_gateway(gw)
    data = request.get_json() or {}
    ssl_id = data.pop("id", data.pop("ssl_id", ""))
    if not ssl_id:
        return jsonify({"error": "ID do certificado é obrigatório"}), 400

    result = client.create_ssl(ssl_id, data)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="CRIAR_SSL",
            recurso_tipo="ssl", recurso_id=ssl_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Certificado SSL '{ssl_id}' criado.",
        )
    return jsonify(result), 201 if result["ok"] else 400


@ssl_bp.route('/delete/<int:gw_id>/<ssl_id>', methods=['DELETE'])
@login_required
def deletar_ssl(gw_id, ssl_id):
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404

    client = get_client_for_gateway(gw)
    result = client.delete_ssl(ssl_id)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="DELETAR_SSL",
            recurso_tipo="ssl", recurso_id=ssl_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Certificado SSL '{ssl_id}' removido.",
        )
    return jsonify(result)
