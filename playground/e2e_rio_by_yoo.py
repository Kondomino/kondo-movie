"""
End-to-end smoke for the v2 /make_movie contract using kondo 239 (rio-by-yoo).

Spawns a webhook catcher on :9999 in a background thread, builds a v2
payload from the local kondos-api Postgres (Media URLs + kondo address),
POSTs to localhost:8080/make_movie, prints the engine response, and waits
up to N seconds for the lifecycle webhook to arrive.

Pre-flight:
  - kondo-movie running on :8080 with Storage.PROVIDER=CloudflareR2
  - kondos-api running on :3003 (cache lookup short-circuits Vision)
  - Postgres on localhost:5433/kondo
  - KondoImageClassifications pre-seeded for kondo 239's images
    (run scripts/seed_rio_by_yoo_classifications.py first)

Usage:
  poetry run python playground/e2e_rio_by_yoo.py
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg2
import requests

KONDO_ID = 239
AGENT_ID = 5
AGENT_NAME = "Victor Souto"
WEBHOOK_PORT = 9999
ENGINE_URL = "http://localhost:8080/make_movie"
DB = dict(host="localhost", port=5433, user="postgres", password="postgres", dbname="kondo")
WEBHOOK_TIMEOUT_SECONDS = 30
ENGINE_TIMEOUT_SECONDS = 600

DESCRIPTION = (
    "Viva o requinte de um dos cartões postais do Rio. "
    "Apartamentos exclusivos com vista privilegiada, infraestrutura completa "
    "e o design assinado YOO. Conheça o Rio by YOO."
)


webhook_received: dict | None = None
webhook_event = threading.Event()


class WebhookCatcher(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        global webhook_received
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            webhook_received = json.loads(body) if body else {}
        except json.JSONDecodeError:
            webhook_received = {"_raw": body}
        webhook_received["_headers"] = dict(self.headers)
        self.send_response(204)
        self.end_headers()
        webhook_event.set()

    def log_message(self, *_args, **_kwargs):  # silence default access log
        return


def start_catcher() -> HTTPServer:
    server = HTTPServer(("127.0.0.1", WEBHOOK_PORT), WebhookCatcher)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def fetch_media_urls(limit: int = 7) -> list[str]:
    conn = psycopg2.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT storage_url FROM "Media" '
                'WHERE "kondoId"=%s AND type=\'image\' AND storage_url IS NOT NULL '
                'ORDER BY id LIMIT %s',
                (KONDO_ID, limit),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def fetch_kondo_address() -> str:
    conn = psycopg2.connect(**DB)
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT address_street_and_numbers, neighborhood, city '
                'FROM "Kondos" WHERE id=%s',
                (KONDO_ID,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    parts = [p for p in (row or []) if p and p.strip()]
    return ", ".join(parts) or "Rio de Janeiro"


def build_payload() -> dict:
    return {
        "job_id": f"e2e-rio-{uuid.uuid4()}",
        "agent": {"id": AGENT_ID, "name": AGENT_NAME},
        "kondo": {"id": KONDO_ID, "address": fetch_kondo_address()},
        "media_urls": fetch_media_urls(9),
        "description": DESCRIPTION,
        "edl_id": "dream_pop",
        "voice_id": "pNInz6obpgDQGcFmaJgB",  # Adam (pre-made, free-tier API)
        "music_url": None,
        "webhook_url": f"http://localhost:{WEBHOOK_PORT}/",
        "capabilities": {
            "duration_max_seconds": 60,
            "images_max": 12,
            "captions_enabled": False,
        },
    }


def main() -> int:
    catcher = start_catcher()
    try:
        payload = build_payload()
        print(f"[e2e] media_urls={len(payload['media_urls'])} "
              f"job_id={payload['job_id']}")
        print(f"[e2e] address={payload['kondo']['address']!r}")
        print(f"[e2e] POST {ENGINE_URL} (this can take minutes)…")
        t0 = time.time()
        try:
            resp = requests.post(ENGINE_URL, json=payload, timeout=ENGINE_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            print(f"[e2e] engine request failed: {exc}")
            return 2
        dt = time.time() - t0
        print(f"[e2e] engine responded {resp.status_code} in {dt:.1f}s")
        try:
            engine_body = resp.json()
        except ValueError:
            engine_body = {"_text": resp.text}
        print(json.dumps(engine_body, indent=2, default=str))

        story = (engine_body or {}).get("story") or {}
        movie_path = story.get("movie_path")
        if movie_path:
            print(f"\n[e2e] OUTPUT URL: {movie_path}")
        else:
            print("\n[e2e] no movie_path in response (render likely failed)")

        print(f"\n[e2e] waiting up to {WEBHOOK_TIMEOUT_SECONDS}s for webhook…")
        if webhook_event.wait(timeout=WEBHOOK_TIMEOUT_SECONDS):
            print("[e2e] webhook received:")
            print(json.dumps(webhook_received, indent=2, default=str))
            return 0 if resp.ok else 1
        else:
            print("[e2e] webhook DID NOT arrive in time")
            return 3
    finally:
        catcher.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
