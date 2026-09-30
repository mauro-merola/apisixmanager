# -*- coding: utf-8 -*-
"""
===============================================================================
ROTAS DE ADMINISTRAÇÃO DE APIs (Routes, Services, Upstreams)
===============================================================================
Arquivo     : api_routes.py
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
)
from api.services.apisix_client import get_client_for_gateway, _extract_items, extract_resource_value

logger = logging.getLogger(__name__)
api_admin_bp = Blueprint('api_admin', __name__, url_prefix='/apis')


def _user_email():
    return str(getattr(current_user, 'email', '') or getattr(current_user, 'id', '')).strip().lower()


def _get_gw_and_client(gw_id):
    """Helper: obtém o gateway e cria o client APISIX."""
    gw = obter_gateway(gw_id)
    if not gw:
        return None, None
    return gw, get_client_for_gateway(gw)


# ── Página principal de APIs ──────────────────────────────────────────────────

@api_admin_bp.route('/')
@login_required
def index():
    """Página de administração de APIs com seleção de gateway."""
    inicializar_banco()
    gateways = listar_gateways()
    gw_id = request.args.get('gateway_id', type=int)
    tab = request.args.get('tab', 'routes')

    routes_list = []
    services_list = []
    upstreams_list = []
    plugins_list = []
    selected_gw = None
    error_msg = None

    if gw_id:
        selected_gw = obter_gateway(gw_id)
        if selected_gw:
            client = get_client_for_gateway(selected_gw)
            try:
                if tab == 'routes' or tab == 'all':
                    resp = client.list_routes()
                    if resp["ok"]:
                        routes_list = [extract_resource_value(i) for i in _extract_items(resp)]
                    elif resp.get("error"):
                        error_msg = resp["error"]

                if tab == 'services' or tab == 'all':
                    resp = client.list_services()
                    if resp["ok"]:
                        services_list = [extract_resource_value(i) for i in _extract_items(resp)]

                if tab == 'upstreams' or tab == 'all':
                    resp = client.list_upstreams()
                    if resp["ok"]:
                        upstreams_list = [extract_resource_value(i) for i in _extract_items(resp)]

                if tab == 'plugins':
                    resp = client.list_plugins()
                    if resp["ok"]:
                        data = resp.get("data")
                        if isinstance(data, list):
                            plugins_list = data
                        elif isinstance(data, dict):
                            plugins_list = list(data.keys()) if data else []

            except Exception as e:
                error_msg = str(e)
                logger.error(f"[API ADMIN] Erro ao listar recursos: {e}")

    return render_template(
        'apis.html',
        gateways=gateways,
        selected_gw=selected_gw,
        routes=routes_list,
        services=services_list,
        upstreams=upstreams_list,
        plugins=plugins_list,
        tab=tab,
        error_msg=error_msg,
        current_user=current_user,
    )


# ── API REST — Routes ─────────────────────────────────────────────────────────

@api_admin_bp.route('/route/<int:gw_id>', methods=['POST'])
@login_required
def criar_route(gw_id):
    """Cria uma nova route no gateway."""
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    data = request.get_json() or {}
    route_id = data.pop("id", data.pop("route_id", ""))
    if not route_id:
        return jsonify({"error": "ID da route é obrigatório"}), 400

    result = client.create_route(route_id, data)

    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="CRIAR_ROUTE",
            recurso_tipo="route", recurso_id=route_id,
            recurso_nome=data.get("name", data.get("uri", "")),
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Route '{route_id}' criada.", payload_json=data,
        )
    return jsonify(result), 201 if result["ok"] else 400


@api_admin_bp.route('/route/<int:gw_id>/<route_id>', methods=['PUT'])
@login_required
def atualizar_route(gw_id, route_id):
    """Atualiza uma route existente."""
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    data = request.get_json() or {}
    result = client.update_route(route_id, data)

    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="EDITAR_ROUTE",
            recurso_tipo="route", recurso_id=route_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Route '{route_id}' atualizada.", payload_json=data,
        )
    return jsonify(result)


@api_admin_bp.route('/route/<int:gw_id>/<route_id>', methods=['DELETE'])
@login_required
def deletar_route(gw_id, route_id):
    """Deleta uma route."""
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    result = client.delete_route(route_id)

    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="DELETAR_ROUTE",
            recurso_tipo="route", recurso_id=route_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Route '{route_id}' removida.",
        )
    return jsonify(result)


@api_admin_bp.route('/route/<int:gw_id>/<route_id>', methods=['GET'])
@login_required
def detalhe_route(gw_id, route_id):
    """Retorna os detalhes de uma route (AJAX)."""
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404
    return jsonify(client.get_route(route_id))


# ── API REST — Services ───────────────────────────────────────────────────────

@api_admin_bp.route('/service/<int:gw_id>', methods=['POST'])
@login_required
def criar_service(gw_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    data = request.get_json() or {}
    service_id = data.pop("id", data.pop("service_id", ""))
    if not service_id:
        return jsonify({"error": "ID do service é obrigatório"}), 400

    result = client.create_service(service_id, data)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="CRIAR_SERVICE",
            recurso_tipo="service", recurso_id=service_id,
            recurso_nome=data.get("name", ""),
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Service '{service_id}' criado.", payload_json=data,
        )
    return jsonify(result), 201 if result["ok"] else 400


@api_admin_bp.route('/service/<int:gw_id>/<service_id>', methods=['PUT'])
@login_required
def atualizar_service(gw_id, service_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    data = request.get_json() or {}
    result = client.update_service(service_id, data)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="EDITAR_SERVICE",
            recurso_tipo="service", recurso_id=service_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Service '{service_id}' atualizado.", payload_json=data,
        )
    return jsonify(result)


@api_admin_bp.route('/service/<int:gw_id>/<service_id>', methods=['DELETE'])
@login_required
def deletar_service(gw_id, service_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    result = client.delete_service(service_id)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="DELETAR_SERVICE",
            recurso_tipo="service", recurso_id=service_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Service '{service_id}' removido.",
        )
    return jsonify(result)


@api_admin_bp.route('/service/<int:gw_id>/<service_id>', methods=['GET'])
@login_required
def detalhe_service(gw_id, service_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404
    return jsonify(client.get_service(service_id))


# ── API REST — Upstreams ──────────────────────────────────────────────────────

@api_admin_bp.route('/upstream/<int:gw_id>', methods=['POST'])
@login_required
def criar_upstream(gw_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    data = request.get_json() or {}
    upstream_id = data.pop("id", data.pop("upstream_id", ""))
    if not upstream_id:
        return jsonify({"error": "ID do upstream é obrigatório"}), 400

    result = client.create_upstream(upstream_id, data)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="CRIAR_UPSTREAM",
            recurso_tipo="upstream", recurso_id=upstream_id,
            recurso_nome=data.get("name", ""),
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Upstream '{upstream_id}' criado.", payload_json=data,
        )
    return jsonify(result), 201 if result["ok"] else 400


@api_admin_bp.route('/upstream/<int:gw_id>/<upstream_id>', methods=['PUT'])
@login_required
def atualizar_upstream(gw_id, upstream_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    data = request.get_json() or {}
    result = client.update_upstream(upstream_id, data)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="EDITAR_UPSTREAM",
            recurso_tipo="upstream", recurso_id=upstream_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Upstream '{upstream_id}' atualizado.", payload_json=data,
        )
    return jsonify(result)


@api_admin_bp.route('/upstream/<int:gw_id>/<upstream_id>', methods=['DELETE'])
@login_required
def deletar_upstream(gw_id, upstream_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404

    result = client.delete_upstream(upstream_id)
    if result["ok"]:
        registrar_auditoria(
            usuario_email=_user_email(), acao="DELETAR_UPSTREAM",
            recurso_tipo="upstream", recurso_id=upstream_id,
            gateway_id=gw_id, gateway_name=gw["name"],
            descricao=f"Upstream '{upstream_id}' removido.",
        )
    return jsonify(result)


@api_admin_bp.route('/upstream/<int:gw_id>/<upstream_id>', methods=['GET'])
@login_required
def detalhe_upstream(gw_id, upstream_id):
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404
    return jsonify(client.get_upstream(upstream_id))


# ── Plugins — Schema Info ─────────────────────────────────────────────────────

@api_admin_bp.route('/plugin-schema/<int:gw_id>/<plugin_name>', methods=['GET'])
@login_required
def plugin_schema(gw_id, plugin_name):
    """Retorna o JSON Schema de um plugin para exibição na UI."""
    gw, client = _get_gw_and_client(gw_id)
    if not client:
        return jsonify({"error": "Gateway não encontrado"}), 404
    return jsonify(client.get_plugin_schema(plugin_name))
