# -*- coding: utf-8 -*-
"""
===============================================================================
ROTAS DE CONSUMERS E CONTROLE DE CREDENCIAIS IDP
===============================================================================
Arquivo     : consumer_routes.py
Versão      : 1.0.0
Data        : 29/09/2026
===============================================================================
"""
import json
import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from api.db.database import (
    inicializar_banco,
    listar_gateways,
    obter_gateway,
    registrar_auditoria,
    listar_idp_bindings,
    criar_idp_binding,
    atualizar_idp_binding,
    deletar_idp_binding,
)
from api.services.apisix_client import get_client_for_gateway, _extract_items, extract_resource_value

logger = logging.getLogger(__name__)
consumer_bp = Blueprint('consumers', __name__, url_prefix='/consumers')


def _user_email():
    return str(getattr(current_user, 'email', '') or getattr(current_user, 'id', '')).strip().lower()


# ── Página principal de Consumers ─────────────────────────────────────────────

@consumer_bp.route('/')
@login_required
def index():
    """Lista consumers de um gateway selecionado + vínculos IDP."""
    inicializar_banco()
    gateways = listar_gateways()
    gw_id = request.args.get('gateway_id', type=int)

    consumers_list = []
    selected_gw = None
    error_msg = None
    idp_bindings = []

    if gw_id:
        selected_gw = obter_gateway(gw_id)
        if selected_gw:
            client = get_client_for_gateway(selected_gw)
            try:
                resp = client.list_consumers()
                if resp["ok"]:
                    consumers_list = [extract_resource_value(i) for i in _extract_items(resp)]
                elif resp.get("error"):
                    error_msg = resp["error"]
            except Exception as e:
                error_msg = str(e)

            idp_bindings = listar_idp_bindings(gateway_id=gw_id)
    else:
        idp_bindings = listar_idp_bindings()

    return render_template(
        'consumers.html',
        gateways=gateways,
        selected_gw=selected_gw,
        consumers=consumers_list,
        idp_bindings=idp_bindings,
        error_msg=error_msg,
        current_user=current_user,
    )


# ── CRUD de Consumers via APISIX ──────────────────────────────────────────────

@consumer_bp.route('/create/<int:gw_id>', methods=['POST'])
@login_required
def criar_consumer(gw_id):
    """Cria um novo consumer no gateway."""
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404

    client = get_client_for_gateway(gw)
    data = request.get_json() or {}

    if not data.get("username"):
        return jsonify({"error": "Username é obrigatório"}), 400

    result = client.create_consumer(data)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="CRIAR_CONSUMER",
            recurso_tipo="consumer", recurso_id=data["username"],
            recurso_nome=data["username"],
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Consumer '{data['username']}' criado.", payload_json=data,
        )
    return jsonify(result), 201 if result["ok"] else 400


@consumer_bp.route('/update/<int:gw_id>/<username>', methods=['PUT'])
@login_required
def atualizar_consumer(gw_id, username):
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404

    client = get_client_for_gateway(gw)
    data = request.get_json() or {}
    result = client.update_consumer(username, data)

    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="EDITAR_CONSUMER",
            recurso_tipo="consumer", recurso_id=username,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Consumer '{username}' atualizado.", payload_json=data,
        )
    return jsonify(result)


@consumer_bp.route('/delete/<int:gw_id>/<username>', methods=['DELETE'])
@login_required
def deletar_consumer(gw_id, username):
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404

    client = get_client_for_gateway(gw)
    result = client.delete_consumer(username)

    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="DELETAR_CONSUMER",
            recurso_tipo="consumer", recurso_id=username,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Consumer '{username}' removido.",
        )
    return jsonify(result)


@consumer_bp.route('/detail/<int:gw_id>/<username>', methods=['GET'])
@login_required
def detalhe_consumer(gw_id, username):
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404
    client = get_client_for_gateway(gw)
    return jsonify(client.get_consumer(username))


# ── IDP Bindings (Controle de Credenciais Externas) ───────────────────────────

@consumer_bp.route('/idp/bind', methods=['POST'])
@login_required
def vincular_idp():
    """Cria um vínculo entre um consumer e um IDP externo."""
    data = request.get_json() or {}

    required = ["gateway_id", "consumer_username", "idp_provider"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo '{field}' é obrigatório."}), 400

    gw_id = int(data["gateway_id"])
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404

    binding_id = criar_idp_binding(
        gateway_id=gw_id,
        consumer_username=data["consumer_username"],
        idp_provider=data["idp_provider"],
        idp_client_id=data.get("idp_client_id", ""),
        idp_issuer=data.get("idp_issuer", ""),
        discovery_url=data.get("discovery_url", ""),
        plugin_name=data.get("plugin_name", "openid-connect"),
        config_json=data.get("plugin_config"),
        routes_json=data.get("routes"),
        created_by=_user_email(),
    )

    # Aplicar plugin no consumer via APISIX Admin API
    if data.get("apply_to_gateway", True):
        client = get_client_for_gateway(gw)
        plugin_config = data.get("plugin_config") or {}

        # Monta config do plugin openid-connect
        oidc_config = {
            "client_id": data.get("idp_client_id", ""),
            "client_secret": data.get("idp_client_secret", ""),
            "discovery": data.get("discovery_url", ""),
            "bearer_only": plugin_config.get("bearer_only", True),
            "realm": data.get("idp_provider", ""),
            "introspection_endpoint_auth_method": plugin_config.get("introspection_method", "client_secret_basic"),
        }
        oidc_config.update(plugin_config)

        consumer_config = {
            "username": data["consumer_username"],
            "plugins": {
                data.get("plugin_name", "openid-connect"): oidc_config
            }
        }

        result = client.create_consumer(consumer_config)
        if not result["ok"]:
            logger.warning(f"[IDP] Falha ao aplicar plugin no consumer: {result.get('error')}")

    registrar_auditoria(
        usuario_email=_user_email(), acao="VINCULAR_IDP",
        recurso_tipo="idp_binding", recurso_id=str(binding_id),
        recurso_nome=f"{data['consumer_username']} ↔ {data['idp_provider']}",
        gateway_id=gw_id, gateway_name=gw["name"],
        descricao=f"IDP '{data['idp_provider']}' vinculado ao consumer '{data['consumer_username']}'.",
        payload_json=data,
    )

    return jsonify({"success": True, "binding_id": binding_id}), 201


@consumer_bp.route('/idp/unbind/<int:binding_id>', methods=['DELETE'])
@login_required
def desvincular_idp(binding_id):
    """Remove um vínculo IDP."""
    if deletar_idp_binding(binding_id):
        registrar_auditoria(
            usuario_email=_user_email(), acao="DESVINCULAR_IDP",
            recurso_tipo="idp_binding", recurso_id=str(binding_id),
            descricao=f"Vínculo IDP #{binding_id} removido.",
        )
        return jsonify({"success": True}), 200
    return jsonify({"error": "Vínculo não encontrado"}), 404


@consumer_bp.route('/idp/list')
@login_required
def listar_vinculos_idp():
    """Lista todos os vínculos IDP (AJAX)."""
    gw_id = request.args.get('gateway_id', type=int)
    bindings = listar_idp_bindings(gateway_id=gw_id)
    return jsonify(bindings)
