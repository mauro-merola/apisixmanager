# -*- coding: utf-8 -*-
"""
===============================================================================
CLIENT HTTP PARA APISIX ADMIN API
===============================================================================
Arquivo     : apisix_client.py
Versão      : 1.0.0
Data        : 29/09/2026
Autor       : Equipe de Governança de APIs

Encapsula todas as chamadas à Admin API do Apache APISIX.
Suporta múltiplas instâncias de gateway.
===============================================================================
"""
import logging
import requests
from api.config import (
    APISIX_DEFAULT_ADMIN_URL,
    APISIX_DEFAULT_ADMIN_KEY,
    REQUESTS_CA_BUNDLE
)

logger = logging.getLogger(__name__)

# Timeout padrão para chamadas à Admin API (connect, read)
DEFAULT_TIMEOUT = (5, 15)


class APISIXClient:
    """
    Client HTTP genérico para interagir com a Admin API de uma instância APISIX.

    Uso:
        client = APISIXClient(admin_url="http://apisix:9180", admin_key="my-key")
        routes = client.list_routes()
        client.create_route("my-route", {...})
    """

    def __init__(self, admin_url=None, admin_key=None):
        self.admin_url = (admin_url or APISIX_DEFAULT_ADMIN_URL).rstrip("/")
        self.admin_key = admin_key or APISIX_DEFAULT_ADMIN_KEY
        self.base_path = f"{self.admin_url}/apisix/admin"
        self._session = requests.Session()
        self._session.headers.update({
            "X-API-KEY": self.admin_key,
            "Content-Type": "application/json"
        })

    def _verify_ssl(self):
        """Retorna o parâmetro de verificação SSL."""
        if isinstance(REQUESTS_CA_BUNDLE, str):
            return REQUESTS_CA_BUNDLE
        return True

    def _request(self, method, path, json_data=None, params=None):
        """Executa uma requisição HTTP à Admin API."""
        url = f"{self.base_path}{path}"
        try:
            resp = self._session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                verify=self._verify_ssl(),
                timeout=DEFAULT_TIMEOUT
            )
            result = {
                "status_code": resp.status_code,
                "ok": resp.ok,
                "data": None,
                "error": None
            }
            try:
                result["data"] = resp.json()
            except Exception:
                result["data"] = resp.text

            if not resp.ok:
                result["error"] = f"HTTP {resp.status_code}: {resp.text[:500]}"
                logger.warning(f"[APISIX] {method} {url} → {resp.status_code}")

            return result

        except requests.exceptions.ConnectionError as e:
            logger.error(f"[APISIX] Conexão recusada: {url} — {e}")
            return {"status_code": 0, "ok": False, "data": None, "error": f"Conexão recusada: {self.admin_url}"}
        except requests.exceptions.Timeout as e:
            logger.error(f"[APISIX] Timeout: {url} — {e}")
            return {"status_code": 0, "ok": False, "data": None, "error": f"Timeout ao conectar: {self.admin_url}"}
        except Exception as e:
            logger.error(f"[APISIX] Erro inesperado: {url} — {e}")
            return {"status_code": 0, "ok": False, "data": None, "error": str(e)}

    # ── Health Check ──────────────────────────────────────────────────────────

    def health_check(self):
        """Verifica se a instância APISIX está acessível."""
        try:
            resp = self._session.get(
                f"{self.admin_url}/apisix/admin/routes",
                verify=self._verify_ssl(),
                timeout=(3, 5)
            )
            return resp.ok
        except Exception:
            return False

    # ── Routes ────────────────────────────────────────────────────────────────

    def list_routes(self):
        return self._request("GET", "/routes")

    def get_route(self, route_id):
        return self._request("GET", f"/routes/{route_id}")

    def create_route(self, route_id, config):
        return self._request("PUT", f"/routes/{route_id}", json_data=config)

    def update_route(self, route_id, config):
        return self._request("PATCH", f"/routes/{route_id}", json_data=config)

    def delete_route(self, route_id):
        return self._request("DELETE", f"/routes/{route_id}")

    # ── Services ──────────────────────────────────────────────────────────────

    def list_services(self):
        return self._request("GET", "/services")

    def get_service(self, service_id):
        return self._request("GET", f"/services/{service_id}")

    def create_service(self, service_id, config):
        return self._request("PUT", f"/services/{service_id}", json_data=config)

    def update_service(self, service_id, config):
        return self._request("PATCH", f"/services/{service_id}", json_data=config)

    def delete_service(self, service_id):
        return self._request("DELETE", f"/services/{service_id}")

    # ── Upstreams ─────────────────────────────────────────────────────────────

    def list_upstreams(self):
        return self._request("GET", "/upstreams")

    def get_upstream(self, upstream_id):
        return self._request("GET", f"/upstreams/{upstream_id}")

    def create_upstream(self, upstream_id, config):
        return self._request("PUT", f"/upstreams/{upstream_id}", json_data=config)

    def update_upstream(self, upstream_id, config):
        return self._request("PATCH", f"/upstreams/{upstream_id}", json_data=config)

    def delete_upstream(self, upstream_id):
        return self._request("DELETE", f"/upstreams/{upstream_id}")

    # ── Consumers ─────────────────────────────────────────────────────────────

    def list_consumers(self):
        return self._request("GET", "/consumers")

    def get_consumer(self, username):
        return self._request("GET", f"/consumers/{username}")

    def create_consumer(self, config):
        return self._request("PUT", f"/consumers/{config.get('username', '')}", json_data=config)

    def update_consumer(self, username, config):
        return self._request("PATCH", f"/consumers/{username}", json_data=config)

    def delete_consumer(self, username):
        return self._request("DELETE", f"/consumers/{username}")

    # ── SSL Certificates ──────────────────────────────────────────────────────

    def list_ssls(self):
        return self._request("GET", "/ssls")

    def get_ssl(self, ssl_id):
        return self._request("GET", f"/ssls/{ssl_id}")

    def create_ssl(self, ssl_id, config):
        return self._request("PUT", f"/ssls/{ssl_id}", json_data=config)

    def delete_ssl(self, ssl_id):
        return self._request("DELETE", f"/ssls/{ssl_id}")

    # ── Plugins ───────────────────────────────────────────────────────────────

    def list_plugins(self):
        """Lista todos os plugins disponíveis na instância APISIX."""
        return self._request("GET", "/plugins/list")

    def get_plugin_schema(self, plugin_name):
        """Retorna o JSON Schema de um plugin específico."""
        return self._request("GET", f"/schema/plugins/{plugin_name}")

    # ── Global Rules ──────────────────────────────────────────────────────────

    def list_global_rules(self):
        return self._request("GET", "/global_rules")

    def get_global_rule(self, rule_id):
        return self._request("GET", f"/global_rules/{rule_id}")

    def create_global_rule(self, rule_id, config):
        return self._request("PUT", f"/global_rules/{rule_id}", json_data=config)

    def delete_global_rule(self, rule_id):
        return self._request("DELETE", f"/global_rules/{rule_id}")

    # ── Plugin Configs ────────────────────────────────────────────────────────

    def list_plugin_configs(self):
        return self._request("GET", "/plugin_configs")

    def get_plugin_config(self, config_id):
        return self._request("GET", f"/plugin_configs/{config_id}")

    def create_plugin_config(self, config_id, config):
        return self._request("PUT", f"/plugin_configs/{config_id}", json_data=config)

    def delete_plugin_config(self, config_id):
        return self._request("DELETE", f"/plugin_configs/{config_id}")


def get_client_for_gateway(gateway_data):
    """
    Factory: cria um APISIXClient a partir dos dados de um gateway (dict do banco).
    """
    return APISIXClient(
        admin_url=gateway_data.get("admin_url", APISIX_DEFAULT_ADMIN_URL),
        admin_key=gateway_data.get("admin_key", APISIX_DEFAULT_ADMIN_KEY)
    )


def _extract_items(response):
    """
    Extrai a lista de itens do response da Admin API APISIX v3.
    O formato varia: pode ser response['data']['list'] ou response['data']['nodes'] etc.
    """
    if not response or not response.get("ok"):
        return []

    data = response.get("data")
    if not data:
        return []

    # APISIX v3: { "list": [...], "total": N }
    if isinstance(data, dict):
        items = data.get("list") or data.get("nodes") or []
        if isinstance(items, list):
            return items
        # Recurso único (GET by ID)
        if data.get("value"):
            return [data]
        return []

    if isinstance(items, list):
        return data

    return []


def extract_resource_value(item):
    """
    Extrai os dados de um recurso APISIX de um item de lista.
    Cada item pode ser: { "key": "...", "value": {...}, "createdIndex": ... }
    ou diretamente o objeto do recurso.
    """
    if isinstance(item, dict):
        if "value" in item:
            val = item["value"]
            # Injeta o ID extraído da key se não existir
            if "id" not in val and "key" in item:
                key_parts = item["key"].rsplit("/", 1)
                if len(key_parts) > 1:
                    val["id"] = key_parts[-1]
            return val
        return item
    return {}
