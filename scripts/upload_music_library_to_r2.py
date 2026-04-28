"""
Upload the kondomino music library (12 tracks) to Cloudflare R2.

Source: ~/Projects/references/kondo/movie/music/*.mp3 (excludes the 34s
loop-unfriendly track per the v1 plan).
Target: r2://kondo-media/music/library/<filename>.mp3
Public:  https://media.kondomino.com.br/music/library/<filename>.mp3

Idempotent: skips files already present in the bucket. Safe to re-run.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

SOURCE_DIR = Path("/home/victorvm/Projects/references/kondo/movie/music")
BUCKET = "kondo-media"
KEY_PREFIX = "music/library/"
PUBLIC_URL_PREFIX = "https://media.kondomino.com.br"

# Per the locked plan, exclude the 34s track that doesn't loop well.
EXCLUDED = {"two-in-the-rain_34sec-198162.mp3"}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["CLOUDFLARE_R2_ENDPOINT"],
        aws_access_key_id=os.environ["CLOUDFLARE_R2_KEY_ID"],
        aws_secret_access_key=os.environ["CLOUDFLARE_R2_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def already_uploaded(client, key: str) -> bool:
    try:
        client.head_object(Bucket=BUCKET, Key=key)
        return True
    except ClientError as e:
        # R2 returns 403 (not 404) for missing objects with non-list-permission tokens.
        # Treat both as "not present"; PutObject will overwrite anyway.
        code = e.response["Error"]["Code"]
        if code in ("404", "NoSuchKey", "403", "Forbidden"):
            return False
        raise


def main() -> int:
    if not SOURCE_DIR.is_dir():
        print(f"Source dir missing: {SOURCE_DIR}")
        return 1

    files = sorted(
        f for f in SOURCE_DIR.iterdir()
        if f.is_file() and f.suffix == ".mp3" and f.name not in EXCLUDED
    )
    if not files:
        print("No .mp3 files to upload")
        return 1

    client = s3_client()
    print(f"Uploading {len(files)} tracks to s3://{BUCKET}/{KEY_PREFIX}\n")

    uploaded = skipped = 0
    for path in files:
        key = f"{KEY_PREFIX}{path.name}"
        if already_uploaded(client, key):
            print(f"  SKIP   {path.name} (already in bucket)")
            skipped += 1
            continue
        client.upload_file(
            Filename=str(path),
            Bucket=BUCKET,
            Key=key,
            ExtraArgs={"ContentType": "audio/mpeg"},
        )
        size_kb = path.stat().st_size // 1024
        print(f"  UPLOAD {path.name} ({size_kb} KB)")
        uploaded += 1

    print(f"\nDone. uploaded={uploaded} skipped={skipped} total={len(files)}")
    print(f"\nVerify: curl -I {PUBLIC_URL_PREFIX}/{KEY_PREFIX}{files[0].name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
