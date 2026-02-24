#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.jetlinks_ai_api.config import load_settings  # noqa: E402
from backend.jetlinks_ai_api.services.doc_service import DocService  # noqa: E402
from backend.jetlinks_ai_api.services.prototype_service import PrototypeService  # noqa: E402


def _load_payload(args: argparse.Namespace) -> dict:
    if args.payload_file:
        data = Path(args.payload_file).read_text(encoding="utf-8")
    elif args.payload_json:
        data = args.payload_json
    else:
        data = sys.stdin.read()
    try:
        payload = json.loads(data)
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"invalid payload json: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("payload must be a JSON object")
    return payload


async def _run(action: str, payload: dict) -> dict:
    settings = load_settings()
    docs = DocService(settings)

    if action == "ppt":
        title = str(payload.get("title") or "").strip() or "演示文稿"
        slides = payload.get("slides")
        if not isinstance(slides, list):
            raise SystemExit("ppt payload missing slides[]")
        style = payload.get("style")
        layout_mode = payload.get("layout_mode")
        return await docs.create_pptx(title=title, slides=slides, style=style, layout_mode=layout_mode)

    if action == "quote_docx" or action == "quote_xlsx":
        seller = str(payload.get("seller") or "").strip()
        buyer = str(payload.get("buyer") or "").strip()
        currency = str(payload.get("currency") or "CNY").strip() or "CNY"
        items = payload.get("items")
        if not isinstance(items, list):
            raise SystemExit("quote payload missing items[]")
        note = payload.get("note")
        if action == "quote_docx":
            return await docs.create_quote_docx(seller=seller, buyer=buyer, currency=currency, items=items, note=note)
        return await docs.create_quote_xlsx(seller=seller, buyer=buyer, currency=currency, items=items, note=note)

    if action == "inspection_docx" or action == "inspection_xlsx":
        title = str(payload.get("title") or "报检单").strip() or "报检单"
        basic_info = payload.get("basic_info") or {}
        device_info = payload.get("device_info") or {}
        network_info = payload.get("network_info") or {}
        inspection_info = payload.get("inspection_info") or {}
        inspection_items = payload.get("inspection_items") or []
        conclusion = payload.get("conclusion") or {}
        signatures = payload.get("signatures") or {}
        attachments = payload.get("attachments")
        if action == "inspection_docx":
            return await docs.create_inspection_docx(
                title=title,
                basic_info=basic_info,
                device_info=device_info,
                network_info=network_info,
                inspection_info=inspection_info,
                inspection_items=inspection_items,
                conclusion=conclusion,
                signatures=signatures,
                attachments=attachments,
            )
        return await docs.create_inspection_xlsx(
            title=title,
            basic_info=basic_info,
            device_info=device_info,
            network_info=network_info,
            inspection_info=inspection_info,
            inspection_items=inspection_items,
            conclusion=conclusion,
            signatures=signatures,
            attachments=attachments,
        )

    if action == "proto":
        project_name = str(payload.get("project_name") or "").strip()
        pages = payload.get("pages")
        if not project_name:
            raise SystemExit("proto payload missing project_name")
        if not isinstance(pages, list) or not pages:
            raise SystemExit("proto payload missing pages[]")
        proto = PrototypeService(settings)
        return await proto.generate(project_name=project_name, pages=pages)

    raise SystemExit(f"unknown action: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="jetlinks-ai skill runner")
    parser.add_argument(
        "action",
        choices=[
            "ppt",
            "quote_docx",
            "quote_xlsx",
            "inspection_docx",
            "inspection_xlsx",
            "proto",
        ],
    )
    parser.add_argument("--payload-file", dest="payload_file")
    parser.add_argument("--payload-json", dest="payload_json")
    args = parser.parse_args()

    payload = _load_payload(args)
    result = asyncio.run(_run(args.action, payload))
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
