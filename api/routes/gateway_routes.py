# -*- coding: utf-8 -*-
"""
===============================================================================
ROTAS DE GERENCIAMENTO DE INSTÂNCIAS DE GATEWAY
===============================================================================
Arquivo     : gateway_routes.py
Versão      : 1.0.0
Data        : 29/09/2026
===============================================================================
"""
import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user

from api.db.database import (
    inicializar_banco,
    listar_gateways,
    obter_gateway,
    criar_gateway,
    atualizar_gateway,
    deletar_gateway,
    atualizar_health_gateway,
    registrar_auditoria,
)
from api.services.apisix_client import APISIXClient, get_client_for_gateway

logger = logging.getLogger(__name__)
gateway_bp = Blueprint('gateways', __name__, url_prefix='/gateways')


def _user_email():
    return str(getattr(current_user, 'email', '') or getattr(current_user, 'id', '')).strip().lower()


@gateway_bp.route('/')
@login_required
def listar():
    """Lista todas as instâncias de gateway registradas."""
    inicializar_banco()
    gateways = listar_gateways(apenas_ativos=False)

    # Health check rápido de cada gateway
    for gw in gateways:
        if gw.get("is_active"):
            try:
                client = get_client_for_gateway(gw)
                online = client.health_check()
                gw["health_live"] = "ONLINE" if online else "OFFLINE"
                atualizar_health_gateway(gw["id"], gw["health_live"])
            except Exception:
                gw["health_live"] = "ERRO"

    return render_template(
        'gateways.html',
        gateways=gateways,
        current_user=current_user,
    )


@gateway_bp.route('/criar', methods=['POST'])
@login_required
def criar():
    """Cadastra uma nova instância de gateway."""
    name = request.form.get('name', '').strip()
    admin_url = request.form.get('admin_url', '').strip()
    admin_key = request.form.get('admin_key', '').strip()
    environment = request.form.get('environment', 'DEV').strip()
    description = request.form.get('description', '').strip()

    if not name or not admin_url or not admin_key:
        flash('Nome, URL da Admin API e API Key são obrigatórios.', 'error')
        return redirect(url_for('gateways.listar'))

    gw_id = criar_gateway(name, admin_url, admin_key, environment, description)

    registrar_auditoria(
        usuario_email=_user_email(),
        acao="CRIAR_GATEWAY",
        recurso_tipo="gateway",
        recurso_id=str(gw_id),
        recurso_nome=name,
        gateway_id=gw_id,
        gateway_name=name,
        descricao=f"Gateway '{name}' ({environment}) cadastrado. URL: {admin_url}",
    )

    flash(f'Gateway "{name}" cadastrado com sucesso!', 'success')
    return redirect(url_for('gateways.listar'))


@gateway_bp.route('/<int:gw_id>/editar', methods=['POST'])
@login_required
def editar(gw_id):
    """Atualiza dados de uma instância de gateway."""
    campos = {}
    for field in ('name', 'admin_url', 'admin_key', 'environment', 'description'):
        val = request.form.get(field, '').strip()
        if val:
            campos[field] = val

    if campos.get("admin_url"):
        campos["admin_url"] = campos["admin_url"].rstrip("/")

    if atualizar_gateway(gw_id, **campos):
        registrar_auditoria(
            usuario_email=_user_email(),
            acao="EDITAR_GATEWAY",
            recurso_tipo="gateway",
            recurso_id=str(gw_id),
            recurso_nome=campos.get("name", ""),
            gateway_id=gw_id,
            descricao=f"Gateway atualizado: {campos}",
        )
        flash('Gateway atualizado com sucesso!', 'success')
    else:
        flash('Erro ao atualizar gateway.', 'error')

    return redirect(url_for('gateways.listar'))


@gateway_bp.route('/<int:gw_id>/deletar', methods=['POST'])
@login_required
def deletar(gw_id):
    """Desativa (soft delete) uma instância de gateway."""
    gw = obter_gateway(gw_id)
    if gw and deletar_gateway(gw_id):
        registrar_auditoria(
            usuario_email=_user_email(),
            acao="DELETAR_GATEWAY",
            recurso_tipo="gateway",
            recurso_id=str(gw_id),
            recurso_nome=gw["name"],
            gateway_id=gw_id,
            gateway_name=gw["name"],
            descricao=f"Gateway '{gw['name']}' desativado.",
        )
        flash(f'Gateway "{gw["name"]}" desativado.', 'success')
    else:
        flash('Gateway não encontrado.', 'error')

    return redirect(url_for('gateways.listar'))


@gateway_bp.route('/<int:gw_id>/health')
@login_required
def health_check(gw_id):
    """Verifica a saúde de uma instância de gateway (AJAX)."""
    gw = obter_gateway(gw_id)
    if not gw:
        return jsonify({"error": "Gateway não encontrado"}), 404

    client = get_client_for_gateway(gw)
    online = client.health_check()
    status = "ONLINE" if online else "OFFLINE"
    atualizar_health_gateway(gw_id, status)

    return jsonify({
        "gateway_id": gw_id,
        "name": gw["name"],
        "status": status,
        "admin_url": gw["admin_url"],
    })


@gateway_bp.route('/<int:gw_id>/reativar', methods=['POST'])
@login_required
def reativar(gw_id):
    """Reativa uma instância de gateway previamente desativada."""
    if atualizar_gateway(gw_id, is_active=1):
        flash('Gateway reativado com sucesso!', 'success')
    else:
        flash('Erro ao reativar gateway.', 'error')
    return redirect(url_for('gateways.listar'))
