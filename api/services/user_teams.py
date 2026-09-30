# -*- coding: utf-8 -*-
"""
===============================================================================
MÓDULO DE TIMES E PERMISSÕES DE USUÁRIOS
===============================================================================
Arquivo     : user_teams.py
Versão      : 1.0.0
Data        : 29/09/2026
===============================================================================
"""
import os
import logging

logger = logging.getLogger(__name__)

# Admins da plataforma (e-mails com permissões totais)
_admin_env = os.getenv("ADMIN_EMAILS", "")
API_ADMIN_EMAILS = [e.strip().lower() for e in _admin_env.split(",") if e.strip()]


def obter_times_do_usuario(email):
    """
    Retorna a lista de times do usuário.
    None = admin (sem restrição).
    [] = sem time (sem permissão).
    """
    if not email:
        return []

    email = str(email).strip().lower()

    if email in API_ADMIN_EMAILS:
        return None  # Admin vê tudo

    # Em desenvolvimento, concede acesso total
    flask_env = os.getenv("FLASK_ENV", "development").lower()
    if flask_env in ("development", "dev"):
        return None

    return []
