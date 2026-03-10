#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _read_token(env_name: str) -> str | None:
    value = (os.getenv(env_name) or "").strip()
    return value or None


def _request_json(req: urllib.request.Request, *, timeout: float = 20.0) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(body) if body else {}
            return int(getattr(resp, "status", 200)), payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as e:
        body = (e.read() or b"").decode("utf-8", errors="ignore")
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {"message": body[:300] or str(e)}
        return int(getattr(e, "code", 0) or 0), payload if isinstance(payload, dict) else {"message": str(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename a Gitee repository via API v5.")
    parser.add_argument("--owner", required=True, help="Repo owner, e.g. BetaStreetOmnis")
    parser.add_argument("--old", required=True, help="Current repo path, e.g. co-desk-team")
    parser.add_argument("--new", required=True, help="New repo name/path, e.g. teamclaw")
    parser.add_argument(
        "--token-env",
        default="GITEE_ACCESS_TOKEN",
        help="Environment variable that stores the Gitee access token (default: GITEE_ACCESS_TOKEN)",
    )
    args = parser.parse_args()

    token = _read_token(args.token_env)
    if not token:
        print(f"Missing token: export {args.token_env}='...'", file=sys.stderr)
        return 2

    edit_url = f"https://gitee.com/api/v5/repos/{urllib.parse.quote(args.owner)}/{urllib.parse.quote(args.old)}"
    body = urllib.parse.urlencode(
        {
            "access_token": token,
            "name": args.new,
            "path": args.new,
        }
    ).encode("utf-8")
    req = urllib.request.Request(edit_url, data=body, method="PATCH")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    status, payload = _request_json(req)
    if status < 200 or status >= 300:
        message = str(payload.get("message") or payload.get("error") or payload or "unknown error")
        print(f"Gitee rename failed (HTTP {status}): {message}", file=sys.stderr)
        return 1

    full_name = str(payload.get("full_name") or "")
    html_url = str(payload.get("html_url") or "")
    print("GITEE_RENAME_OK")
    if full_name:
        print(full_name)
    if html_url:
        print(html_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
