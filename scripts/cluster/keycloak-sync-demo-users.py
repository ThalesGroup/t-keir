#!/usr/bin/env python3
"""Ensure T-KEIR demo Keycloak users, roles, and clearance claims exist.

Idempotent: safe to run after every ``make keycloak-up``. Needed when the
Keycloak volume was created before persona users were added to
``deploy/keycloak/realm-tkeir.json`` (realm import only runs on first boot).

Env:
  KEYCLOAK_URL              default http://localhost:8082
  KEYCLOAK_ADMIN            default admin
  KEYCLOAK_ADMIN_PASSWORD   default admin
  KEYCLOAK_REALM            default tkeir
  KEYCLOAK_WAIT_SECS        default 180
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = os.environ.get("KEYCLOAK_URL", "http://localhost:8082").rstrip("/")
ADMIN = os.environ.get("KEYCLOAK_ADMIN", "admin")
PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
REALM = os.environ.get("KEYCLOAK_REALM", "tkeir")
WAIT_SECS = int(os.environ.get("KEYCLOAK_WAIT_SECS", "180"))

ROLES: list[tuple[str, str, list[str] | None]] = [
    ("c2-j2-analyst", "NATO C2 J2 analyst persona", None),
    ("c2-moc-watch", "NATO C2 MOC watch persona", None),
    ("c2-j2x-humint", "NATO C2 J2X HUMINT persona", None),
    ("c2-ctf-commander", "NATO C2 CTF commander persona", None),
    (
        "c2-admin",
        "NATO C2 admin persona",
        ["tkeir-admin", "tkeir-user", "tkeir-operator", "tkeir-auditor"],
    ),
]

USERS: list[dict[str, Any]] = [
    {
        "username": "demo-user",
        "email": "demo-user@tkeir",
        "firstName": "Demo",
        "lastName": "User",
        "clearance": "UNCLASSIFIED",
        "password": "demo-user",
        "roles": ["tkeir-user"],
    },
    {
        "username": "demo-auditor",
        "email": "demo-auditor@tkeir",
        "firstName": "Demo",
        "lastName": "Auditor",
        "clearance": "FOUO",
        "password": "demo-auditor",
        "roles": ["tkeir-auditor", "tkeir-user"],
    },
    {
        "username": "demo-admin",
        "email": "demo-admin@tkeir",
        "firstName": "Demo",
        "lastName": "Admin",
        "clearance": "SECRET",
        "password": "demo-admin",
        "roles": ["tkeir-admin", "c2-admin"],
    },
    {
        "username": "analyst",
        "email": "analyst@tkeir",
        "firstName": "J2",
        "lastName": "Analyst",
        "clearance": "SECRET",
        "password": "analyst",
        "roles": ["c2-j2-analyst", "tkeir-user"],
    },
    {
        "username": "moc-watch",
        "email": "moc-watch@tkeir",
        "firstName": "MOC",
        "lastName": "Watch",
        "clearance": "FOUO",
        "password": "moc-watch",
        "roles": ["c2-moc-watch", "tkeir-user"],
    },
    {
        "username": "humint",
        "email": "humint@tkeir",
        "firstName": "J2X",
        "lastName": "HUMINT",
        "clearance": "SECRET",
        "password": "humint",
        "roles": ["c2-j2x-humint", "tkeir-user"],
    },
    {
        "username": "commander",
        "email": "commander@tkeir",
        "firstName": "CTF",
        "lastName": "Commander",
        "clearance": "SECRET",
        "password": "commander",
        "roles": ["c2-ctf-commander", "tkeir-user"],
    },
    {
        "username": "c2-admin",
        "email": "c2-admin@tkeir",
        "firstName": "C2",
        "lastName": "Admin",
        "clearance": "SECRET",
        "password": "c2-admin",
        "roles": ["c2-admin", "tkeir-admin"],
    },
]

CLIENTS_NEEDING_CLEARANCE = ("tkeir-hmi", "tkeir-cli")
CLIENTS_NEEDING_ROLES_SCOPE = ("tkeir-hmi", "tkeir-cli")


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
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if not raw:
                return resp.status, None
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body


def _https_required(body: Any) -> bool:
    if isinstance(body, dict):
        desc = str(body.get("error_description") or body.get("error") or "")
        return "HTTPS required" in desc or "https required" in desc.lower()
    return "HTTPS required" in str(body)


def relax_master_ssl_via_container() -> bool:
    """Best-effort: set master realm sslRequired=NONE inside the Keycloak container.

    Existing volumes often keep master.sslRequired=external, which rejects
    HTTP token requests from the host even when KC_HTTP_ENABLED=true.
    """
    import shutil
    import subprocess

    if not shutil.which("docker"):
        return False
    container = os.environ.get("KEYCLOAK_CONTAINER", "tkeir-keycloak")
    # Inside the container Keycloak listens on :8080 (host maps 8082:8080).
    server = "http://127.0.0.1:8080"
    try:
        cfg = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "/opt/keycloak/bin/kcadm.sh",
                "config",
                "credentials",
                "--server",
                server,
                "--realm",
                "master",
                "--user",
                ADMIN,
                "--password",
                PASSWORD,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if cfg.returncode != 0:
            print(
                f"  warn: kcadm login failed ({cfg.returncode}): {cfg.stderr or cfg.stdout}",
                file=sys.stderr,
            )
            return False
        upd = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "/opt/keycloak/bin/kcadm.sh",
                "update",
                "realms/master",
                "-s",
                "sslRequired=NONE",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if upd.returncode != 0:
            print(
                f"  warn: set master sslRequired=NONE failed: {upd.stderr or upd.stdout}",
                file=sys.stderr,
            )
            return False
        print("set master realm sslRequired=NONE (via docker exec)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  warn: cannot relax master SSL via docker: {exc}", file=sys.stderr)
        return False


def wait_for_admin_token() -> str:
    deadline = time.time() + WAIT_SECS
    last_err = "unreachable"
    ssl_fix_attempted = False
    while time.time() < deadline:
        try:
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
            last_err = f"HTTP {st}: {body}"
            if st == 403 and _https_required(body) and not ssl_fix_attempted:
                ssl_fix_attempted = True
                print(
                    "admin token rejected (HTTPS required) — "
                    "relaxing master realm SSL for local HTTP…",
                    file=sys.stderr,
                )
                relax_master_ssl_via_container()
        except Exception as exc:  # noqa: BLE001 — wait loop
            last_err = str(exc)
        time.sleep(2)
    raise SystemExit(
        f"Keycloak admin token not available after {WAIT_SECS}s ({BASE}): {last_err}\n"
        "Hint: wipe Keycloak state with `make down` (default wipes volumes), then "
        "`make keycloak-up`. Compose must use KC_HOSTNAME=http://localhost:8082."
    )


def ensure_unmanaged_attributes(token: str) -> None:
    st, realm = _request("GET", f"/admin/realms/{REALM}", token)
    if st != 200 or not isinstance(realm, dict):
        raise SystemExit(f"Cannot load realm {REALM}: {st} {realm}")
    attrs = dict(realm.get("attributes") or {})
    if attrs.get("unmanagedAttributePolicy") != "ENABLED":
        attrs["unmanagedAttributePolicy"] = "ENABLED"
        realm["attributes"] = attrs
        st, body = _request("PUT", f"/admin/realms/{REALM}", token, realm)
        if st not in (204, 200):
            raise SystemExit(f"Failed enabling unmanaged attributes: {st} {body}")
        print("enabled unmanagedAttributePolicy=ENABLED")

    st, profile = _request("GET", f"/admin/realms/{REALM}/users/profile", token)
    if st != 200 or not isinstance(profile, dict):
        return
    attrs_list = list(profile.get("attributes") or [])
    names = {a.get("name") for a in attrs_list}
    changed = False
    if "clearance" not in names:
        attrs_list.append(
            {
                "name": "clearance",
                "displayName": "Clearance",
                "permissions": {"view": ["admin", "user"], "edit": ["admin"]},
                "multivalued": False,
            }
        )
        changed = True
    if profile.get("unmanagedAttributePolicy") != "ENABLED":
        profile["unmanagedAttributePolicy"] = "ENABLED"
        changed = True
    if changed:
        profile["attributes"] = attrs_list
        st, body = _request(
            "PUT", f"/admin/realms/{REALM}/users/profile", token, profile
        )
        if st not in (204, 200):
            raise SystemExit(f"Failed updating user profile: {st} {body}")
        print("updated user profile (clearance + unmanaged)")


def ensure_role(
    token: str, name: str, description: str, composites: list[str] | None
) -> None:
    st, _ = _request(
        "POST",
        f"/admin/realms/{REALM}/roles",
        token,
        {"name": name, "description": description},
    )
    if st not in (201, 409):
        # 409 if exists on some versions; others return 400
        st2, existing = _request("GET", f"/admin/realms/{REALM}/roles/{urllib.parse.quote(name)}", token)
        if st2 != 200:
            raise SystemExit(f"Failed creating role {name}: {st}")
    print(f"role {name}: ok")
    if not composites:
        return
    reps = []
    for rn in composites:
        st, role = _request(
            "GET", f"/admin/realms/{REALM}/roles/{urllib.parse.quote(rn)}", token
        )
        if st == 200 and isinstance(role, dict):
            reps.append(role)
    if reps:
        st, body = _request(
            "POST",
            f"/admin/realms/{REALM}/roles/{urllib.parse.quote(name)}/composites",
            token,
            reps,
        )
        if st not in (204, 200, 409):
            print(f"  warn: composites for {name}: {st} {body}", file=sys.stderr)


def ensure_roles_client_scope(token: str) -> str:
    st, scopes = _request("GET", f"/admin/realms/{REALM}/client-scopes", token)
    if st != 200 or not isinstance(scopes, list):
        raise SystemExit(f"Cannot list client scopes: {st}")
    roles_scope = next((s for s in scopes if s.get("name") == "roles"), None)
    if not roles_scope:
        st, body = _request(
            "POST",
            f"/admin/realms/{REALM}/client-scopes",
            token,
            {
                "name": "roles",
                "description": "OpenID Connect scope for realm roles",
                "protocol": "openid-connect",
                "attributes": {
                    "include.in.token.scope": "true",
                    "display.on.consent.screen": "false",
                },
            },
        )
        if st not in (201, 204):
            raise SystemExit(f"Failed creating roles client scope: {st} {body}")
        st, scopes = _request("GET", f"/admin/realms/{REALM}/client-scopes", token)
        roles_scope = next(s for s in scopes if s.get("name") == "roles")
        print("created client scope: roles")
    else:
        # Keep the built-in / existing scope discoverable in the token scope list.
        attrs = dict(roles_scope.get("attributes") or {})
        if attrs.get("include.in.token.scope") != "true":
            attrs["include.in.token.scope"] = "true"
            roles_scope["attributes"] = attrs
            st, body = _request(
                "PUT",
                f"/admin/realms/{REALM}/client-scopes/{roles_scope['id']}",
                token,
                roles_scope,
            )
            if st not in (204, 200):
                print(f"  warn: update roles scope attrs: {st} {body}", file=sys.stderr)
            else:
                print("roles scope: include.in.token.scope=true")

    sid = roles_scope["id"]
    st, mappers = _request(
        "GET", f"/admin/realms/{REALM}/client-scopes/{sid}/protocol-mappers/models", token
    )
    by_name = {m.get("name"): m for m in (mappers or []) if isinstance(m, dict)}
    wanted = [
        (
            "realm roles",
            {
                "name": "realm roles",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-realm-role-mapper",
                "consentRequired": False,
                "config": {
                    "multivalued": "true",
                    "claim.name": "roles",
                    "jsonType.label": "String",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true",
                    "introspection.token.claim": "true",
                },
            },
        ),
        (
            "realm access",
            {
                "name": "realm access",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-realm-role-mapper",
                "consentRequired": False,
                "config": {
                    "multivalued": "true",
                    "claim.name": "realm_access.roles",
                    "jsonType.label": "String",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true",
                    "introspection.token.claim": "true",
                },
            },
        ),
    ]
    for name, payload in wanted:
        existing = by_name.get(name)
        if existing:
            mid = existing.get("id")
            if mid:
                merged = dict(existing)
                merged.update(payload)
                merged["id"] = mid
                st, body = _request(
                    "PUT",
                    f"/admin/realms/{REALM}/client-scopes/{sid}/protocol-mappers/models/{mid}",
                    token,
                    merged,
                )
                if st not in (204, 200):
                    print(f"  warn: update mapper {name}: {st} {body}", file=sys.stderr)
                else:
                    print(f"mapper on roles scope: {name} (updated)")
            continue
        st, body = _request(
            "POST",
            f"/admin/realms/{REALM}/client-scopes/{sid}/protocol-mappers/models",
            token,
            payload,
        )
        if st not in (201, 204):
            print(f"  warn: mapper {name}: {st} {body}", file=sys.stderr)
        else:
            print(f"mapper on roles scope: {name}")
    return sid


def ensure_client_mapper(
    token: str, client_uuid: str, name: str, payload: dict[str, Any]
) -> None:
    st, mappers = _request(
        "GET",
        f"/admin/realms/{REALM}/clients/{client_uuid}/protocol-mappers/models",
        token,
    )
    if st != 200:
        return
    if any(m.get("name") == name for m in (mappers or [])):
        return
    st, body = _request(
        "POST",
        f"/admin/realms/{REALM}/clients/{client_uuid}/protocol-mappers/models",
        token,
        payload,
    )
    if st not in (201, 204):
        print(f"  warn: client mapper {name}: {st} {body}", file=sys.stderr)
    else:
        print(f"client mapper {name}: created")


def ensure_clients(token: str, roles_scope_id: str) -> None:
    clearance_mapper = {
        "name": "clearance",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-attribute-mapper",
        "consentRequired": False,
        "config": {
            "user.attribute": "clearance",
            "claim.name": "clearance",
            "jsonType.label": "String",
            "id.token.claim": "true",
            "access.token.claim": "true",
            "userinfo.token.claim": "true",
            "multivalued": "false",
        },
    }
    for cname in CLIENTS_NEEDING_CLEARANCE:
        st, clients = _request(
            "GET",
            f"/admin/realms/{REALM}/clients?clientId={urllib.parse.quote(cname)}",
            token,
        )
        if st != 200 or not clients:
            print(f"  warn: client {cname} missing", file=sys.stderr)
            continue
        client = clients[0]
        cid = client["id"]
        # Ensure realm roles are included in tokens for this client.
        if client.get("fullScopeAllowed") is not True:
            client["fullScopeAllowed"] = True
            st, body = _request(
                "PUT", f"/admin/realms/{REALM}/clients/{cid}", token, client
            )
            if st not in (204, 200):
                print(f"  warn: fullScopeAllowed {cname}: {st} {body}", file=sys.stderr)
            else:
                print(f"client {cname}: fullScopeAllowed=true")
        ensure_client_mapper(token, cid, "clearance", clearance_mapper)
        if cname in CLIENTS_NEEDING_ROLES_SCOPE:
            st, body = _request(
                "PUT",
                f"/admin/realms/{REALM}/clients/{cid}/default-client-scopes/{roles_scope_id}",
                token,
            )
            if st not in (204, 200):
                print(f"  warn: attach roles->{cname}: {st} {body}", file=sys.stderr)
            else:
                print(f"default scope roles -> {cname}")


def ensure_user(token: str, spec: dict[str, Any]) -> None:
    username = spec["username"]
    st, found = _request(
        "GET",
        f"/admin/realms/{REALM}/users?username={urllib.parse.quote(username)}&exact=true",
        token,
    )
    if st != 200:
        raise SystemExit(f"Cannot query user {username}: {st}")
    if not found:
        st, body = _request(
            "POST",
            f"/admin/realms/{REALM}/users",
            token,
            {
                "username": username,
                "enabled": True,
                "email": spec["email"],
                "emailVerified": True,
                "firstName": spec["firstName"],
                "lastName": spec["lastName"],
                "attributes": {"clearance": [spec["clearance"]]},
                "credentials": [
                    {
                        "type": "password",
                        "value": spec["password"],
                        "temporary": False,
                    }
                ],
            },
        )
        if st not in (201, 204):
            raise SystemExit(f"Failed creating user {username}: {st} {body}")
        st, found = _request(
            "GET",
            f"/admin/realms/{REALM}/users?username={urllib.parse.quote(username)}&exact=true",
            token,
        )
        print(f"user {username}: created")
    else:
        print(f"user {username}: exists")

    uid = found[0]["id"]
    st, full = _request("GET", f"/admin/realms/{REALM}/users/{uid}", token)
    if st == 200 and isinstance(full, dict):
        attrs = dict(full.get("attributes") or {})
        attrs["clearance"] = [spec["clearance"]]
        full["attributes"] = attrs
        full["enabled"] = True
        full["emailVerified"] = True
        st, body = _request("PUT", f"/admin/realms/{REALM}/users/{uid}", token, full)
        if st not in (204, 200):
            print(f"  warn: update {username}: {st} {body}", file=sys.stderr)

    st, body = _request(
        "PUT",
        f"/admin/realms/{REALM}/users/{uid}/reset-password",
        token,
        {"type": "password", "value": spec["password"], "temporary": False},
    )
    if st not in (204, 200):
        raise SystemExit(f"Failed setting password for {username}: {st} {body}")

    role_reps = []
    for rn in spec["roles"]:
        st, role = _request(
            "GET", f"/admin/realms/{REALM}/roles/{urllib.parse.quote(rn)}", token
        )
        if st == 200 and isinstance(role, dict):
            role_reps.append(role)
    if role_reps:
        st, body = _request(
            "POST",
            f"/admin/realms/{REALM}/users/{uid}/role-mappings/realm",
            token,
            role_reps,
        )
        if st not in (204, 200):
            print(f"  warn: roles for {username}: {st} {body}", file=sys.stderr)


def verify_analyst() -> None:
    st, body = _request(
        "POST",
        f"/realms/{REALM}/protocol/openid-connect/token",
        form={
            "client_id": "tkeir-cli",
            "username": "analyst",
            "password": "analyst",
            "grant_type": "password",
        },
    )
    if st != 200 or not isinstance(body, dict) or not body.get("access_token"):
        raise SystemExit(f"Verify analyst login failed: {st} {body}")
    payload = body["access_token"].split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    roles = (claims.get("realm_access") or {}).get("roles") or claims.get("roles") or []
    clearance = claims.get("clearance")
    print(
        f"verify analyst: clearance={clearance!r} roles={sorted(r for r in roles if r.startswith('c2-') or r.startswith('tkeir-'))}"
    )
    if "c2-j2-analyst" not in roles:
        raise SystemExit("analyst token missing c2-j2-analyst role")
    if clearance != "SECRET":
        raise SystemExit(f"analyst token missing clearance=SECRET (got {clearance!r})")


def main() -> int:
    print(f"Syncing demo users on {BASE} realm={REALM} …")
    token = wait_for_admin_token()
    ensure_unmanaged_attributes(token)
    for name, desc, composites in ROLES:
        ensure_role(token, name, desc, composites)
    roles_scope_id = ensure_roles_client_scope(token)
    ensure_clients(token, roles_scope_id)
    for user in USERS:
        ensure_user(token, user)
    verify_analyst()
    print("Demo users ready (password = username for each account).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
