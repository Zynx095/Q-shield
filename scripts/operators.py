"""Manage named gateway operators directly in the gateway database (local admin, no network).

    python scripts/operators.py create alice "Alice Example" operator [--ttl-days 30]
    python scripts/operators.py list
    python scripts/operators.py revoke alice

`create` prints the bearer token ONCE; only its SHA-256 is stored. Use DATABASE_URL like the gateway does.
The same actions are available over the API to an admin operator (POST /api/v1/operators, .../revoke).
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.config import Settings  # noqa: E402
from backend.devices.store import Store  # noqa: E402
from backend.security.operators import ROLES, OperatorError, OperatorStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("operator_id")
    c.add_argument("display_name")
    c.add_argument("role", choices=ROLES)
    c.add_argument("--ttl-days", type=float)
    sub.add_parser("list")
    r = sub.add_parser("revoke")
    r.add_argument("operator_id")
    a = ap.parse_args()
    store = Store(Settings.load().db_path)
    ops, now = OperatorStore(store), time.time()
    try:
        if a.cmd == "create":
            op, token = ops.create(a.operator_id, a.display_name, a.role, now, created_by="local-cli",
                                   ttl_s=a.ttl_days * 86400 if a.ttl_days else None)
            store.add_event(now, None, "operator_action", "low", {"operator_id": "local-cli", "action": "CREATE_OPERATOR",
                                                                 "target_operator": op.operator_id, "result": "success"})
            print(json.dumps(op.public()))
            print(f"TOKEN (shown once, store it securely): {token}")
        elif a.cmd == "list":
            print(json.dumps(ops.list(), indent=2))
        else:
            ops.revoke(a.operator_id, now, by="local-cli")
            store.add_event(now, None, "operator_action", "low", {"operator_id": "local-cli", "action": "REVOKE_OPERATOR",
                                                                 "target_operator": a.operator_id, "result": "success"})
            print(f"revoked {a.operator_id}")
    except OperatorError as e:
        raise SystemExit(f"error: {e}")


if __name__ == "__main__":
    main()
