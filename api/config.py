# -*- coding: utf-8 -*-
"""
===============================================================================
MÓDULO DE CONFIGURAÇÃO GLOBAL E VARIÁVEIS DE AMBIENTE
===============================================================================
Arquivo     : config.py
Versão      : 1.0.0
Data        : 29/09/2026
Autor       : Equipe de Governança de APIs

HISTÓRICO DE VERSÕES:
-------------------------------------------------------------------------------
Versão       Data         Autor                 Descrição
-------------------------------------------------------------------------------
1.0.0        29/09/2026   Equipe Governança     Configuração inicial para
                                                plataforma APISIX Gateway.
===============================================================================
"""
import os
import time
import requests
import logging
from dotenv import load_dotenv, find_dotenv

logger = logging.getLogger(__name__)

load_dotenv(find_dotenv())


def _sanitizar_ambiente_ssl():
    caminho_env = os.getenv("REQUESTS_CA_BUNDLE", "").strip()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    cert_padrao = os.path.join(base_dir, "certificates", "corp-ca.pem")

    ca_path = caminho_env if caminho_env else cert_padrao

    if ca_path and os.path.isfile(ca_path):
        try:
            with open(ca_path, 'r', encoding='utf-8', errors='ignore') as f:
                conteudo = f.read()
                if "BEGIN CERTIFICATE" in conteudo:
                    os.environ["REQUESTS_CA_BUNDLE"] = ca_path
                    return ca_path
        except Exception as e:
            logger.warning(f"[SSL WARNING] Falha ao ler certificado em '{ca_path}': {e}")

    os.environ.pop("REQUESTS_CA_BUNDLE", None)
    os.environ.pop("SSL_CERT_FILE", None)

    logger.info(f"[SSL INFO] Certificado '{ca_path}' inválido ou não encontrado. Utilizando CA Bundle padrão do sistema.")
    return True


REQUESTS_CA_BUNDLE = _sanitizar_ambiente_ssl()
LOGGER_LEVEL = os.getenv("LOGGER_LEVEL", "INFO")

FLASK_ENV = os.getenv("FLASK_ENV", "development")
FLASK_APP = os.getenv("FLASK_APP", "apisix-gateway-manager")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "8080"))

# Chave de Sessão Flask
FLASK_KEY_VAULT = os.getenv("FLASK_VAULT") or os.getenv("FLASK_KEY_VAULT", "")
if not FLASK_KEY_VAULT:
    logger.warning("[SEGURANÇA WARNING] A variável FLASK_KEY_VAULT / FLASK_VAULT não foi encontrada no ambiente!")

# ─── APISIX Gateway (instância padrão / fallback) ─────────────────────────────
APISIX_DEFAULT_ADMIN_URL = os.getenv("APISIX_DEFAULT_ADMIN_URL", "http://127.0.0.1:9180").rstrip("/")
APISIX_DEFAULT_ADMIN_KEY = os.getenv("APISIX_DEFAULT_ADMIN_KEY", "edd1c9f034335f136f87ad84b625c8f1")
APISIX_DEFAULT_INSTANCE_NAME = os.getenv("APISIX_DEFAULT_INSTANCE_NAME", "Local Development")

# Ambientes monitorados
_envs_raw = os.getenv("APISIX_ENVIRONMENTS", "DEV,HML,PRD")
APISIX_ENVIRONMENTS = [e.strip() for e in _envs_raw.split(",") if e.strip()]

# Cache TTL
APISIX_CACHE_TTL = int(os.getenv("APISIX_CACHE_TTL_SECONDS", "3600"))

# Banco de dados local
DB_NAME = os.getenv("DATABASE_NAME", "database.db")

# ─── OIDC / SSO (Azure AD / Entra ID) ─────────────────────────────────────────
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "")
OIDC_TENANT_ID = os.getenv("OIDC_TENANT_ID", "")
OIDC_ISSUER_URL = os.getenv("OIDC_ISSUER_URL", "").rstrip("/")

# Se tenant_id configurado mas issuer_url vazio, monta automaticamente para Azure AD
if OIDC_TENANT_ID and not OIDC_ISSUER_URL:
    OIDC_ISSUER_URL = f"https://login.microsoftonline.com/{OIDC_TENANT_ID}/v2.0"

# ─── GitLab Integration (ACL) ─────────────────────────────────────────────────
GIT_HOST = os.getenv("GIT_HOST", "https://gitlab.example.com")
PROJECT_PATH_ENCODED = os.getenv("PROJECT_PATH_ENCODED", "api_team%2Fapisix%2Fgovernanca%2Fcontrole")
FILE_NAME = os.getenv("FILE_NAME", "allowed_user_dashportal.json")
BRANCH = os.getenv("BRANCH", "main")
GIT_TOKEN_ID_VAULT = os.getenv("GIT_ID_VAULT") or os.getenv("GIT_TOKEN_ID_VAULT", "")

# Caminho do arquivo de permissões local (fallback quando GitLab não acessível)
_LOCAL_ACL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), FILE_NAME)

# Em modo dev, concede todas as permissões ao usuário local automaticamente
_DEV_ACL = {
    "allowed_emails": ["dev@local.com"],
    "allow_sync": ["dev@local.com"],
    "allow_client_block": ["dev@local.com"],
    "allow_prd_block": [],
    "exempt_clients": []
}

_CACHE_GITLAB_PERMISSOES = {
    "timestamp": 0,
    "allowed_emails": [],
    "allow_sync": [],
    "allow_client_block": [],
    "exempt_clients": []
}
_CACHE_TTL_SEGUNDOS = 300


def obter_permissoes_gitlab(force_refresh=False):
    """
    Carrega as permissões e listas do GitLab com suporte a cache local.
    """
    global _CACHE_GITLAB_PERMISSOES
    agora = time.time()

    if not force_refresh and (agora - _CACHE_GITLAB_PERMISSOES["timestamp"]) < _CACHE_TTL_SEGUNDOS:
        return {
            "allowed_emails": _CACHE_GITLAB_PERMISSOES["allowed_emails"],
            "allow_sync": _CACHE_GITLAB_PERMISSOES["allow_sync"],
            "allow_client_block": _CACHE_GITLAB_PERMISSOES.get("allow_client_block", []),
            "exempt_clients": _CACHE_GITLAB_PERMISSOES.get("exempt_clients", [])
        }

    url_raw = f"{GIT_HOST.rstrip('/')}/api/v4/projects/{PROJECT_PATH_ENCODED}/repository/files/{FILE_NAME}/raw?ref={BRANCH}"
    headers = {}

    token = GIT_TOKEN_ID_VAULT.strip()
    if token:
        headers["PRIVATE-TOKEN"] = token

    try:
        response = requests.get(url_raw, headers=headers, verify=REQUESTS_CA_BUNDLE, timeout=5)
        if response.status_code == 200:
            dados = response.json()

            allowed_emails = [e.strip().lower() for e in dados.get("allowed_emails", []) if e]
            allow_sync = [e.strip().lower() for e in dados.get("allow_sync", []) if e]
            allow_client_block = [e.strip().lower() for e in dados.get("allow_client_block", []) if e]
            exempt_clients = [str(c).strip() for c in dados.get("exempt_clients", []) if c]

            _CACHE_GITLAB_PERMISSOES = {
                "timestamp": agora,
                "allowed_emails": allowed_emails,
                "allow_sync": allow_sync,
                "allow_client_block": allow_client_block,
                "exempt_clients": exempt_clients
            }
            logger.info(f"[GITLAB ACL] Permissões atualizadas. Autorizados: {len(allowed_emails)}")
            return {
                "allowed_emails": allowed_emails,
                "allow_sync": allow_sync,
                "allow_client_block": allow_client_block,
                "exempt_clients": exempt_clients
            }
        else:
            logger.warning(f"[GITLAB ACL WARNING] Resposta inesperada ({response.status_code}) no GitLab.")
    except Exception as e:
        logger.warning(f"[GITLAB ACL] GitLab inacessível: {e}. Tentando arquivo local...")

    # --- FALLBACK 1: arquivo local (modo dev / sem rede corporativa) ---
    if os.path.isfile(_LOCAL_ACL_FILE):
        try:
            import json as _json
            with open(_LOCAL_ACL_FILE, 'r', encoding='utf-8') as f:
                dados = _json.load(f)
            allowed_emails = [e.strip().lower() for e in dados.get("allowed_emails", []) if e]
            allow_sync = [e.strip().lower() for e in dados.get("allow_sync", []) if e]
            allow_client_block = [e.strip().lower() for e in dados.get("allow_client_block", []) if e]
            exempt_clients = [str(c).strip() for c in dados.get("exempt_clients", []) if c]
            logger.info(f"[GITLAB ACL] Usando arquivo local: {_LOCAL_ACL_FILE}")
            _CACHE_GITLAB_PERMISSOES = {
                "timestamp": agora,
                "allowed_emails": allowed_emails,
                "allow_sync": allow_sync,
                "allow_client_block": allow_client_block,
                "exempt_clients": exempt_clients
            }
            return {
                "allowed_emails": allowed_emails,
                "allow_sync": allow_sync,
                "allow_client_block": allow_client_block,
                "exempt_clients": exempt_clients
            }
        except Exception as ef:
            logger.warning(f"[GITLAB ACL] Falha ao ler arquivo local: {ef}")

    # --- FALLBACK 2: modo dev - concede permissão total ao usuário local ---
    if str(FLASK_ENV).lower() in ("development", "dev"):
        logger.info("[GITLAB ACL] Modo DEV ativo: concedendo permissões completas ao usuário dev@local.com")
        return dict(_DEV_ACL)

    # --- FALLBACK 3: retorna cache anterior (pode estar vazio) ---
    return {
        "allowed_emails": _CACHE_GITLAB_PERMISSOES["allowed_emails"],
        "allow_sync": _CACHE_GITLAB_PERMISSOES["allow_sync"],
        "allow_client_block": _CACHE_GITLAB_PERMISSOES.get("allow_client_block", []),
        "exempt_clients": _CACHE_GITLAB_PERMISSOES.get("exempt_clients", [])
    }


get_gitlab_permissions = obter_permissoes_gitlab