"""Aplica los grupos sugeridos por llm_suggest_groups.py al portal.

Lee data/group_suggestions.json y crea cada grupo asignando sus miembros via
POST /api/v1/groups/suggestions/accept (un grupo + miembros en una transaccion).

Si en el JSON se agrega una clave "_skip": true a un grupo, se omite.

Uso:
    python scripts/apply_group_suggestions.py
    python scripts/apply_group_suggestions.py --api=http://localhost:8000
    python scripts/apply_group_suggestions.py --dry-run

Requiere credenciales admin (email + password) via env:
    APU_ADMIN_EMAIL=...
    APU_ADMIN_PASSWORD=...
(o se solicitan interactivamente)
"""

import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
IN_FILE = DATA_DIR / "group_suggestions.json"
DEFAULT_API = "https://apu-marketplace-app.q8waob.easypanel.host"


def parse_args():
    cfg = {"api": DEFAULT_API, "dry_run": False}
    for a in sys.argv[1:]:
        if a.startswith("--api="):
            cfg["api"] = a.split("=", 1)[1].rstrip("/")
        elif a == "--dry-run":
            cfg["dry_run"] = True
    return cfg


def load_creds():
    email = os.environ.get("APU_ADMIN_EMAIL", "").strip()
    password = os.environ.get("APU_ADMIN_PASSWORD", "").strip()
    if not email:
        email = input("Email admin: ").strip()
    if not password:
        password = getpass.getpass("Password: ").strip()
    return email, password


def login(api_url, email, password):
    payload = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{api_url}/api/v1/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"ERROR login HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
        sys.exit(1)
    token = data.get("access_token")
    if not token:
        print(f"ERROR: login sin access_token. Respuesta: {data}")
        sys.exit(1)
    print(f"Login OK como {data.get('user', {}).get('email', email)}")
    return token


def post_group(api_url, token, group):
    payload = json.dumps({
        "name": group["name"],
        "category": group.get("category"),
        "variant_label": group.get("variant_label"),
        "insumo_ids": group["member_ids"],
    }).encode()
    req = urllib.request.Request(
        f"{api_url}/api/v1/groups/suggestions/accept",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return True, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return False, {"error": f"HTTP {e.code}", "body": e.read().decode(errors="replace")[:300]}
    except Exception as e:
        return False, {"error": str(e)}


def main():
    cfg = parse_args()
    if not IN_FILE.exists():
        print(f"ERROR: no existe {IN_FILE}")
        print("Corre primero: python scripts/llm_suggest_groups.py")
        sys.exit(1)

    with open(IN_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    groups = data.get("groups", [])
    groups = [g for g in groups if not g.get("_skip")]

    if not groups:
        print("No hay grupos para aplicar.")
        sys.exit(0)

    print(f"{len(groups)} grupos a aplicar en {cfg['api']}")
    if cfg["dry_run"]:
        print("\n[DRY-RUN] No se enviaran requests.")
        for g in groups:
            print(f"  - {g['name']} [{g.get('variant_label', '-')}] ({len(g['member_ids'])} miembros)")
        return

    email, password = load_creds()
    token = login(cfg["api"], email, password)

    ok = 0
    fail = 0
    for i, g in enumerate(groups, 1):
        print(f"[{i}/{len(groups)}] {g['name']} ({len(g['member_ids'])} miembros)...", end=" ", flush=True)
        success, resp = post_group(cfg["api"], token, g)
        if success:
            print("OK")
            ok += 1
        else:
            print(f"FAIL: {resp}")
            fail += 1
        time.sleep(0.2)

    print(f"\n{'=' * 60}")
    print(f"Creados: {ok} | Fallidos: {fail} | Total: {len(groups)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
