"""Local demo: tamper with and replay a stored signed observation against our own gateway.

    python scripts/demo_forgery.py --db qshield.db [--gateway http://127.0.0.1:8000]

Takes the most recent signed observation the gateway stored, then
  1. re-sends it with the payload altered (an attacker hiding the anomaly)  -> expected HTTP 401
  2. re-sends it unchanged (a replay)                                       -> HTTP 409 within the freshness
     window (300 s) of the original; HTTP 401 (stale timestamp) after it. Both are rejections.
Nothing is forged cryptographically: the altered copy simply carries the original signature, which
no longer matches. Controlled local simulation only: the script refuses any non-loopback target.
"""
import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse


def post(url: str, body: dict) -> int:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="gateway SQLite file (to read a stored signed envelope)")
    ap.add_argument("--gateway", default="http://127.0.0.1:8000")
    a = ap.parse_args()

    host = urlparse(a.gateway).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("refusing: this demo only targets a local gateway", file=sys.stderr)
        return 2

    row = sqlite3.connect(a.db).execute(
        "SELECT envelope FROM observations WHERE envelope IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        print("no signed observation stored yet; run the vision service with --signer-id first", file=sys.stderr)
        return 1
    env = json.loads(row[0])
    payload = json.loads(env["payload"])
    print(f"stored observation {env['observation_id']} signed by {env['signer_id']} ({env['algorithm']})")

    forged = dict(env)
    payload["anomaly"], payload["anomaly_reason"] = False, None
    payload["confidence"] = 0.01
    forged["payload"] = json.dumps(payload, sort_keys=True)
    url = a.gateway.rstrip("/") + "/api/v1/observations/signed"
    print("1. payload altered, original signature kept ->", post(url, forged), "(expected 401)")
    print("2. exact replay of the stored envelope      ->", post(url, env),
          "(409 = duplicate within the 300 s window; 401 = stale timestamp after it; both are rejections)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
