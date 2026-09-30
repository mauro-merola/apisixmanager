# -*- coding: utf-8 -*-
"""
===============================================================================
MÓDULO DE AUTENTICAÇÃO OIDC (Azure AD / Entra ID) E AUTORIZAÇÃO GITLAB
===============================================================================
Arquivo     : auth_routes.py
Versão      : 1.0.0
Data        : 29/09/2026
Autor       : Equipe de Governança de APIs
===============================================================================
"""
import os
import json
import logging
import requests
from time import time
from flask import Blueprint, redirect, url_for, session, request, render_template
from flask_login import LoginManager, UserMixin, login_user, logout_user

from api.config import (
    OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_ISSUER_URL, OIDC_TENANT_ID,
    GIT_HOST, PROJECT_PATH_ENCODED, FILE_NAME, BRANCH, GIT_TOKEN_ID_VAULT,
    FLASK_KEY_VAULT, REQUESTS_CA_BUNDLE
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)
login_manager = LoginManager()

CACHE_USUARIOS = None
ULTIMO_FETCH = 0
CACHE_TIMEOUT = 300

class User(UserMixin):
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    user_data = session.get("user")
    if user_data and str(user_data.get("id")) == str(user_id):
        return User(
            id=user_data["id"],
            name=user_data.get("name", "Usuário"),
            email=user_data.get("email", "")
        )
    return None

def init_auth(app):
    if not FLASK_KEY_VAULT or len(FLASK_KEY_VAULT.strip()) == 0:
        logger.critical("[CRÍTICO SEGURANÇA] FLASK_KEY_VAULT não definida no ambiente! Aplicação abortada.")
        raise ValueError("CRÍTICO: A variável de ambiente FLASK_KEY_VAULT/FLASK_VAULT precisa ser configurada.")

    app.secret_key = FLASK_KEY_VAULT
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    app.register_blueprint(auth_bp)

def _carregar_usuarios_git():
    global CACHE_USUARIOS, ULTIMO_FETCH
    agora = time()
    if CACHE_USUARIOS and (agora - ULTIMO_FETCH < CACHE_TIMEOUT):
        return CACHE_USUARIOS

    url = f"{GIT_HOST}/api/v4/projects/{PROJECT_PATH_ENCODED}/repository/files/{FILE_NAME}/raw?ref={BRANCH}"
    headers = {"PRIVATE-TOKEN": GIT_TOKEN_ID_VAULT}

    try:
        resp = requests.get(url, headers=headers, verify=REQUESTS_CA_BUNDLE, timeout=10)
        if resp.status_code == 200:
            CACHE_USUARIOS = resp.json()
            ULTIMO_FETCH = agora
            return CACHE_USUARIOS
    except Exception as e:
        logger.error(f"[AUTH EXCEÇÃO] Erro ao conectar no GitLab: {e}")

    if CACHE_USUARIOS:
        return CACHE_USUARIOS

    try:
        caminho_local = os.path.join(os.path.dirname(__file__), "..", FILE_NAME)
        if os.path.exists(caminho_local):
            with open(caminho_local, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"[AUTH FALLBACK ERRO] Erro no backup local: {e}")

    return {}

def usuario_esta_autorizado(email):
    if not email:
        return False
    data = _carregar_usuarios_git()
    email_normalizado = str(email).lower().strip()

    if isinstance(data, dict):
        emails_liberados = [str(e).lower().strip() for e in data.get("allowed_emails", []) if e]
    elif isinstance(data, list):
        emails_liberados = [str(e).lower().strip() for e in data if e]
    else:
        emails_liberados = []

    return email_normalizado in emails_liberados

def _get_oidc_endpoints():
    """
    Descobre os endpoints OIDC via well-known.
    Suporta Azure AD e qualquer provedor OIDC compatível.
    """
    well_known_url = f"{OIDC_ISSUER_URL}/.well-known/openid-configuration"
    try:
        resp = requests.get(well_known_url, verify=REQUESTS_CA_BUNDLE, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"[AUTH] Falha discovery OIDC: {e}")

    # Fallback para Azure AD
    if OIDC_TENANT_ID:
        base = f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/oauth2/v2.0"
        return {
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
            "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
            "end_session_endpoint": f"{base}/logout"
        }

    # Fallback genérico (Keycloak / RHSSO)
    return {
        "authorization_endpoint": f"{OIDC_ISSUER_URL}/protocol/openid-connect/auth",
        "token_endpoint": f"{OIDC_ISSUER_URL}/protocol/openid-connect/token",
        "userinfo_endpoint": f"{OIDC_ISSUER_URL}/protocol/openid-connect/userinfo",
        "end_session_endpoint": f"{OIDC_ISSUER_URL}/protocol/openid-connect/logout"
    }

@auth_bp.route("/login")
def login():
    endpoints = _get_oidc_endpoints()
    redirect_uri = url_for("auth.authorized", _external=True)
    auth_url = (
        f"{endpoints['authorization_endpoint']}?"
        f"client_id={OIDC_CLIENT_ID}&"
        f"response_type=code&"
        f"scope=openid%20profile%20email&"
        f"redirect_uri={redirect_uri}"
    )
    return redirect(auth_url)

@auth_bp.route("/getAToken")
def authorized():
    code = request.args.get("code")
    if not code:
        return render_template('acesso_negado.html', mensagem="Sua tentativa de login foi cancelada ou o código expirou."), 401

    endpoints = _get_oidc_endpoints()
    redirect_uri = url_for("auth.authorized", _external=True)

    payload = {
        "client_id": OIDC_CLIENT_ID,
        "client_secret": OIDC_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }

    resp = requests.post(endpoints["token_endpoint"], data=payload, verify=REQUESTS_CA_BUNDLE, timeout=10)
    if resp.status_code != 200:
        return render_template('acesso_negado.html', mensagem="Não foi possível validar suas credenciais."), 401

    token_data = resp.json()
    access_token = token_data.get("access_token")

    userinfo_endpoint = endpoints.get("userinfo_endpoint", f"{OIDC_ISSUER_URL}/protocol/openid-connect/userinfo")
    headers = {"Authorization": f"Bearer {access_token}"}

    userinfo_resp = requests.get(userinfo_endpoint, headers=headers, verify=REQUESTS_CA_BUNDLE, timeout=10)
    claims = userinfo_resp.json() if userinfo_resp.status_code == 200 else token_data

    user_email = str(claims.get("email", claims.get("preferred_username", ""))).lower().strip()
    user_name = claims.get("name", claims.get("preferred_username", "Usuário"))
    user_id = claims.get("sub", user_email)

    if not usuario_esta_autorizado(user_email):
        return render_template('acesso_negado.html', mensagem="Seu usuário foi autenticado, mas não possui permissão para acessar a plataforma.", user_email=user_email), 403

    user_data = {"id": user_id, "name": user_name, "email": user_email}
    session["user"] = user_data
    user = User(id=user_id, name=user_name, email=user_email)
    login_user(user)

    return redirect(url_for("dash.dashboard"))

@auth_bp.route("/logout")
def logout():
    logout_user()
    session.clear()
    endpoints = _get_oidc_endpoints()
    logout_url = endpoints.get("end_session_endpoint")
    if logout_url:
        redirect_uri = url_for("auth.login", _external=True)
        return redirect(f"{logout_url}?post_logout_redirect_uri={redirect_uri}&client_id={OIDC_CLIENT_ID}")
    return redirect(url_for("auth.login"))