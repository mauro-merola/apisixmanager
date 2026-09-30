# -*- coding: utf-8 -*-
"""
===============================================================================
ROTAS DO DASHBOARD — APISIX GATEWAY MANAGEMENT PLATFORM
===============================================================================
Arquivo     : dash_routes.py
Versão      : 1.0.0
Data        : 29/09/2026
===============================================================================
"""
import logging
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import login_required, current_user

from api.db.database import (
    inicializar_banco,
    listar_gateways,
    obter_gateway,
    buscar_auditoria,
)
from api.services.apisix_client import APISIXClient, get_client_for_gateway, _extract_items, extract_resource_value
from api.services.user_teams import obter_times_do_usuario, API_ADMIN_EMAILS

logger = logging.getLogger(__name__)
dash_bp = Blueprint('dash', __name__)


# ─── Helpers de permissão ──────────────────────────────────────────────────────

def _real_email():
    """E-mail real (permanente) do usuário autenticado."""
    return str(
        getattr(current_user, 'email', None) or
        getattr(current_user, 'id', None) or ''
    ).strip().lower()


def _is_real_admin():
    """Verifica se o usuário REAL é administrador do sistema."""
    return _real_email() in API_ADMIN_EMAILS


@dash_bp.before_request
def _injetar_contexto_na_sessao():
    """Injeta is_admin na sessão para o Jinja."""
    if current_user and current_user.is_authenticated:
        session['is_admin'] = _is_real_admin()
        session['user_role'] = 'Administrador' if _is_real_admin() else 'Operador'


# ─── Dashboard ────────────────────────────────────────────────────────────────

@dash_bp.route('/')
@dash_bp.route('/dashboard')
@login_required
def dashboard():
    """Visão geral: KPIs de todas as instâncias de gateway."""
    inicializar_banco()
    gateways = listar_gateways()

    # Coleta KPIs de cada gateway
    gateway_stats = []
    totais = {"routes": 0, "services": 0, "upstreams": 0, "consumers": 0, "ssl": 0}

    for gw in gateways:
        client = get_client_for_gateway(gw)
        stats = {
            "gateway": gw,
            "online": False,
            "routes": 0,
            "services": 0,
            "upstreams": 0,
            "consumers": 0,
            "ssl": 0,
        }

        try:
            if client.health_check():
                stats["online"] = True

                routes_resp = client.list_routes()
                services_resp = client.list_services()
                upstreams_resp = client.list_upstreams()
                consumers_resp = client.list_consumers()
                ssl_resp = client.list_ssls()

                stats["routes"] = len(_extract_items(routes_resp))
                stats["services"] = len(_extract_items(services_resp))
                stats["upstreams"] = len(_extract_items(upstreams_resp))
                stats["consumers"] = len(_extract_items(consumers_resp))
                stats["ssl"] = len(_extract_items(ssl_resp))

                for k in totais:
                    totais[k] += stats[k]
        except Exception as e:
            logger.warning(f"[DASHBOARD] Erro ao coletar stats do gateway {gw['name']}: {e}")

        gateway_stats.append(stats)

    # Últimas ações de auditoria
    recent_audit = buscar_auditoria(limite=10)

    return render_template(
        'dashboard.html',
        gateway_stats=gateway_stats,
        totais=totais,
        total_gateways=len(gateways),
        gateways_online=sum(1 for gs in gateway_stats if gs["online"]),
        recent_audit=recent_audit,
        current_user=current_user,
    )


# ─── Auditoria ────────────────────────────────────────────────────────────────

@dash_bp.route('/audit')
@login_required
def audit_log():
    """Log de auditoria completo."""
    gateway_id = request.args.get('gateway_id', type=int)
    recurso_tipo = request.args.get('tipo', '').strip() or None
    registros = buscar_auditoria(limite=500, gateway_id=gateway_id, recurso_tipo=recurso_tipo)
    gateways = listar_gateways()

    return render_template(
        'audit.html',
        registros=registros,
        gateways=gateways,
        filtro_gateway=gateway_id,
        filtro_tipo=recurso_tipo,
        current_user=current_user,
    )