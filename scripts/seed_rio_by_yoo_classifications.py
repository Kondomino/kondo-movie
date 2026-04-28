"""
Seed empty-labels classification rows for kondo 239 (rio-by-yoo) so the
v2 e2e render skips GCP Vision on the no-ADC dev machine.

Idempotent: ON CONFLICT (imageHash) DO NOTHING. Safe to re-run.
"""
import hashlib
import os
import sys
import urllib.request

import psycopg2

KONDO_ID = 239
DB = dict(host="localhost", port=5433, user="postgres", password="postgres", dbname="kondo")
SOURCE = "manual_seed_rio_by_yoo_e2e"


def fetch_media_urls(conn) -> list[tuple[int, str]]:
    with conn.cursor() as cur:
        cur.execute(
            'SELECT id, storage_url FROM "Media" '
            'WHERE "kondoId"=%s AND type=\'image\' AND storage_url IS NOT NULL '
            'ORDER BY id',
            (KONDO_ID,),
        )
        return cur.fetchall()


def hash_url(url: str) -> str:
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "kondo-movie-seed/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        for chunk in iter(lambda: resp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def seed(conn, kondo_id: int, image_hash: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO "KondoImageClassifications" '
            '("imageHash", "kondoId", classification, source, "computedAt", "createdAt", "updatedAt") '
            "VALUES (%s, %s, %s::jsonb, %s, NOW(), NOW(), NOW()) "
            'ON CONFLICT ("imageHash") DO NOTHING '
            "RETURNING id",
            (image_hash, kondo_id, '{"labels": []}', SOURCE),
        )
        return cur.fetchone() is not None


def main() -> int:
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    try:
        rows = fetch_media_urls(conn)
        if not rows:
            print(f"No media for kondo {KONDO_ID}")
            return 1
        print(f"Found {len(rows)} media rows for kondo {KONDO_ID}")
        inserted = skipped = 0
        for media_id, url in rows:
            try:
                h = hash_url(url)
            except Exception as e:
                print(f"  media={media_id} {url} → hash failed: {e}")
                continue
            if seed(conn, KONDO_ID, h):
                print(f"  media={media_id} hash={h[:12]}… INSERTED")
                inserted += 1
            else:
                print(f"  media={media_id} hash={h[:12]}… already cached")
                skipped += 1
        print(f"\nDone. inserted={inserted} skipped={skipped}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
