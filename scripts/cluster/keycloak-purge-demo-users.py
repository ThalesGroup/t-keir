#!/usr/bin/env python3
"""Remove T-KEIR demo Keycloak persona users (and optional persona roles).

Used by ``make down`` / ``make keycloak-purge-demo-users`` so hybrid-demo
personas do not linger when tearing the stack down.

Usernames and roles are collected from every ``datasets/*/keycloak.json``
plus platform demo accounts, so a local usecase pack is purged even when ``TKEIR_USECASE`` points at
another pack.

Env matches keycloak-sync-demo-users.py:
  KEYCLOAK_URL, KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD, KEYCLOAK_REALM
  KEYCLOAK_PURGE_ROLES=1  also delete pack persona roles (default 0)
  KEYCLOAK_WAIT_SECS      default 30 (best-effort; skip if Keycloak is down)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

BASE = os.environ.get("KEYCLOAK_URL", "http://localhost:8082").rstrip("/")
ADMIN = os.environ.get("KEYCLOAK_ADMIN", "admin")
PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
REALM = os.environ.get("KEYCLOAK_REALM", "tkeir")
WAIT_SECS = int(os.environ.get("KEYCLOAK_WAIT_SECS", "30"))
PURGE_ROLES = os.environ.get("KEYCLOAK_PURGE_ROLES", "0").strip() in {
    "1",
    "true",
    "yes",
    "on",
}

PLATFORM_USERNAMES = [
    "demo-user",
    "demo-auditor",
    "demo-admin",
]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def collect_usernames_and_roles() -> tuple[list[str], list[str]]:
    """Load demo usernames/roles from every usecase Keycloak pack."""
    names = list(PLATFORM_USERNAMES)
    roles: list[str] = []
    datasets = REPO / "datasets"
    if datasets.is_dir():
        for path in sorted(datasets.glob("*/keycloak.json")):
            try:
                pack = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(pack, dict):
                continue
            for user in pack.get("users") or []:
                if isinstance(user, dict) and user.get("username"):
                    names.append(str(user["username"]))
            for role in pack.get("roles") or []:
                if isinstance(role, dict) and role.get("name"):
                    roles.append(str(role["name"]))
    return _unique(names), _unique(roles)


def _request(
    method: str,
    path: str,
    token: str | None = None,
    payload: Any = None,
    form: dict[str, str] | None = None,
) -> tuple[int, Any]:
    url = path if path.startswith("http") else f"{BASE}{path}"
    data: bytes | None = None
    headers: dict[str, str] = {}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, None
            try:
                return resp.status, json.loads(raw)
            except Exception:  # noqa: BLE001
                return resp.status, raw.decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(body)
        except Exception:  # noqa: BLE001
            return e.code, body
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def wait_for_admin_token() -> str | None:
    deadline = time.time() + WAIT_SECS
    ssl_fix_attempted = False
    while time.time() < deadline:
        st, body = _request(
            "POST",
            "/realms/master/protocol/openid-connect/token",
            form={
                "client_id": "admin-cli",
                "username": ADMIN,
                "password": PASSWORD,
                "grant_type": "password",
            },
        )
        if st == 200 and isinstance(body, dict) and body.get("access_token"):
            return str(body["access_token"])
        desc = ""
        if isinstance(body, dict):
            desc = str(body.get("error_description") or body.get("error") or "")
        if st == 403 and "HTTPS required" in desc and not ssl_fix_attempted:
            ssl_fix_attempted = True
            # Reuse the sync script helper when available.
            try:
                import importlib.util

                sync_path = Path(__file__).with_name("keycloak-sync-demo-users.py")
                spec = importlib.util.spec_from_file_location(
                    "keycloak_sync_demo_users", sync_path
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "relax_master_ssl_via_container"):
                        mod.relax_master_ssl_via_container()
            except Exception as exc:  # noqa: BLE001
                print(f"  warn: SSL relax skipped: {exc}", file=sys.stderr)
        time.sleep(2)
    return None


def main() -> int:
    usernames, persona_roles = collect_usernames_and_roles()
    print(f"Purging demo personas on {BASE} realm={REALM} …")
    token = wait_for_admin_token()
    if not token:
        print("Keycloak not reachable — skip persona purge (volumes may still be wiped).")
        return 0

    for username in usernames:
        st, found = _request(
            "GET",
            f"/admin/realms/{REALM}/users?username={urllib.parse.quote(username)}&exact=true",
            token,
        )
        if st != 200 or not found:
            print(f"user {username}: absent")
            continue
        uid = found[0]["id"]
        st, body = _request("DELETE", f"/admin/realms/{REALM}/users/{uid}", token)
        if st in (204, 200, 404):
            print(f"user {username}: deleted")
        else:
            print(f"user {username}: warn delete {st} {body}", file=sys.stderr)

    if PURGE_ROLES:
        for role in persona_roles:
            st, body = _request(
                "DELETE",
                f"/admin/realms/{REALM}/roles/{urllib.parse.quote(role)}",
                token,
            )
            if st in (204, 200, 404):
                print(f"role {role}: deleted")
            else:
                print(f"role {role}: warn delete {st} {body}", file=sys.stderr)

    print("Demo persona purge done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
