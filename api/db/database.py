# -*- coding: utf-8 -*-
"""
===============================================================================
MÓDULO DE PERSISTÊNCIA E ACESSO AO BANCO DE DADOS (SQLITE)
===============================================================================
Arquivo     : database.py
Versão      : 1.0.0
Data        : 29/09/2026
Autor       : Equipe de Governança de APIs

Schema para APISIX Gateway Management Platform:
  - tb_gateways             : Instâncias de gateway APISIX registradas
  - tb_audit_log            : Log de ações realizadas pelos usuários
  - tb_usuarios             : Cadastro de usuários autorizados
  - tb_idp_bindings         : Vínculos IDP ↔ consumers/routes
===============================================================================
"""

import sqlite3
import logging
import json
from datetime import datetime
from api.config import DB_NAME

__version__ = "1.0.0-APISIX"
__module_name__ = "database_governanca_apisix"

logger = logging.getLogger(__name__)


def conectar_bd():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


obter_conexao = conectar_bd


def _garantir_colunas(cursor, tabela, colunas_desejadas):
    cursor.execute(f"PRAGMA table_info({tabela})")
    colunas_existentes = [row["name"] for row in cursor.fetchall()]
    for nome_col, tipo_col in colunas_desejadas.items():
        if nome_col not in colunas_existentes:
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_col} {tipo_col}")


def inicializar_banco():
    conn = conectar_bd()
    cursor = conn.cursor()

    # ── Instâncias de Gateway APISIX ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tb_gateways (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            admin_url       TEXT NOT NULL,
            admin_key       TEXT NOT NULL,
            environment     TEXT DEFAULT 'DEV',
            description     TEXT,
            is_active       INTEGER DEFAULT 1,
            health_status   TEXT DEFAULT 'UNKNOWN',
            last_health_check TEXT,
            created_at      TEXT,
            updated_at      TEXT
        )
    """)

    # ── Audit Log ─────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tb_audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT,
            usuario_email   TEXT,
            acao            TEXT,
            recurso_tipo    TEXT,
            recurso_id      TEXT,
            recurso_nome    TEXT,
            gateway_id      INTEGER,
            gateway_name    TEXT,
            descricao       TEXT,
            payload_json    TEXT,
            origem          TEXT DEFAULT 'MANUAL',
            FOREIGN KEY (gateway_id) REFERENCES tb_gateways(id)
        )
    """)

    # ── Usuários (Cadastro Completo) ──────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tb_usuarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT,
            email           TEXT UNIQUE,
            role            TEXT DEFAULT 'viewer',
            teams_json      TEXT,
            last_login      TEXT,
            created_at      TEXT,
            updated_at      TEXT
        )
    """)

    # ── Vínculos IDP ↔ API/Consumer (controle de credenciais externas) ────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tb_idp_bindings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            gateway_id      INTEGER NOT NULL,
            consumer_username TEXT NOT NULL,
            idp_provider    TEXT NOT NULL,
            idp_client_id   TEXT,
            idp_issuer      TEXT,
            discovery_url   TEXT,
            plugin_name     TEXT DEFAULT 'openid-connect',
            config_json     TEXT,
            routes_json     TEXT,
            status          TEXT DEFAULT 'ACTIVE',
            created_at      TEXT,
            updated_at      TEXT,
            created_by      TEXT,
            FOREIGN KEY (gateway_id) REFERENCES tb_gateways(id)
        )
    """)

    # ── Cache de recursos APISIX (snapshot local) ─────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tb_apisix_cache (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            gateway_id      INTEGER NOT NULL,
            resource_type   TEXT NOT NULL,
            resource_id     TEXT,
            resource_data   TEXT,
            cached_at       TEXT,
            FOREIGN KEY (gateway_id) REFERENCES tb_gateways(id),
            UNIQUE(gateway_id, resource_type, resource_id)
        )
    """)

    conn.commit()
    conn.close()


# ── Gateway CRUD ──────────────────────────────────────────────────────────────

def listar_gateways(apenas_ativos=True):
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        if apenas_ativos:
            cursor.execute("SELECT * FROM tb_gateways WHERE is_active = 1 ORDER BY environment ASC, name ASC")
        else:
            cursor.execute("SELECT * FROM tb_gateways ORDER BY environment ASC, name ASC")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def obter_gateway(gateway_id):
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM tb_gateways WHERE id = ?", (gateway_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def criar_gateway(name, admin_url, admin_key, environment="DEV", description=""):
    conn = conectar_bd()
    cursor = conn.cursor()
    agora = datetime.now().isoformat()
    try:
        cursor.execute("""
            INSERT INTO tb_gateways (name, admin_url, admin_key, environment, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, admin_url.rstrip("/"), admin_key, environment, description, agora, agora))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def atualizar_gateway(gateway_id, **campos):
    conn = conectar_bd()
    cursor = conn.cursor()
    campos["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k} = ?" for k in campos)
    vals = list(campos.values()) + [gateway_id]
    try:
        cursor.execute(f"UPDATE tb_gateways SET {sets} WHERE id = ?", vals)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def deletar_gateway(gateway_id):
    return atualizar_gateway(gateway_id, is_active=0)


def atualizar_health_gateway(gateway_id, status):
    return atualizar_gateway(
        gateway_id,
        health_status=status,
        last_health_check=datetime.now().isoformat()
    )


# ── Audit Log ─────────────────────────────────────────────────────────────────

def registrar_auditoria(usuario_email, acao, recurso_tipo="", recurso_id="",
                        recurso_nome="", gateway_id=None, gateway_name="",
                        descricao="", payload_json=None, origem="MANUAL"):
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO tb_audit_log (
                timestamp, usuario_email, acao, recurso_tipo, recurso_id,
                recurso_nome, gateway_id, gateway_name, descricao,
                payload_json, origem
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(), usuario_email, acao, recurso_tipo,
            recurso_id, recurso_nome, gateway_id, gateway_name,
            descricao, json.dumps(payload_json) if payload_json else None, origem
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"[AUDIT] Erro ao registrar auditoria: {e}")
    finally:
        conn.close()


def buscar_auditoria(limite=200, gateway_id=None, recurso_tipo=None):
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        where = ["1=1"]
        params = []
        if gateway_id:
            where.append("gateway_id = ?")
            params.append(gateway_id)
        if recurso_tipo:
            where.append("recurso_tipo = ?")
            params.append(recurso_tipo)

        where_sql = " AND ".join(where)
        params.append(limite)
        cursor.execute(f"""
            SELECT * FROM tb_audit_log
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ?
        """, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


# ── IDP Bindings ──────────────────────────────────────────────────────────────

def listar_idp_bindings(gateway_id=None):
    conn = conectar_bd()
    cursor = conn.cursor()
    try:
        if gateway_id:
            cursor.execute("""
                SELECT b.*, g.name as gateway_display_name
                FROM tb_idp_bindings b
                LEFT JOIN tb_gateways g ON b.gateway_id = g.id
                WHERE b.gateway_id = ? AND b.status = 'ACTIVE'
                ORDER BY b.created_at DESC
            """, (gateway_id,))
        else:
            cursor.execute("""
                SELECT b.*, g.name as gateway_display_name
                FROM tb_idp_bindings b
                LEFT JOIN tb_gateways g ON b.gateway_id = g.id
                WHERE b.status = 'ACTIVE'
                ORDER BY b.created_at DESC
            """)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def criar_idp_binding(gateway_id, consumer_username, idp_provider, idp_client_id="",
                      idp_issuer="", discovery_url="", plugin_name="openid-connect",
                      config_json=None, routes_json=None, created_by=""):
    conn = conectar_bd()
    cursor = conn.cursor()
    agora = datetime.now().isoformat()
    try:
        cursor.execute("""
            INSERT INTO tb_idp_bindings (
                gateway_id, consumer_username, idp_provider, idp_client_id,
                idp_issuer, discovery_url, plugin_name, config_json,
                routes_json, status, created_at, updated_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
        """, (
            gateway_id, consumer_username, idp_provider, idp_client_id,
            idp_issuer, discovery_url, plugin_name,
            json.dumps(config_json) if config_json else None,
            json.dumps(routes_json) if routes_json else None,
            agora, agora, created_by
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def atualizar_idp_binding(binding_id, **campos):
    conn = conectar_bd()
    cursor = conn.cursor()
    campos["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k} = ?" for k in campos)
    vals = list(campos.values()) + [binding_id]
    try:
        cursor.execute(f"UPDATE tb_idp_bindings SET {sets} WHERE id = ?", vals)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def deletar_idp_binding(binding_id):
    return atualizar_idp_binding(binding_id, status="INACTIVE")