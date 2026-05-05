#!/usr/bin/env python3
"""
One-shot migration: rewrite every EDL template's `soundtrack_uri` from
the legacy `gs://editora-v2-templates/music/...` GCS path to the
HTTPS Cloudflare R2 URL of an equivalent track from the current music
catalog (kondos-api/src/video/config/video-capability-caps.ts).

The 13 tracks in the catalog already live at
  https://media.kondomino.com.br/music/library/<filename>.mp3

Mapping below pairs each EDL's vibe (inferred from the location/theme
name in its old gs:// filename) with a track from the catalog.
Inactive EDLs (everything outside the 3 in FREE_EDLS) get reasonable
defaults — they're loaded by the engine but not user-selectable, so
quality-tuning their music is a follow-up if/when they're activated.

Idempotent: rerunning is a no-op once gs:// URIs are gone.

Usage:
    python scripts/migrate_edl_music_to_r2.py        # apply changes
    python scripts/migrate_edl_music_to_r2.py --dry  # report only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


R2_PREFIX = "https://media.kondomino.com.br/music/library/"


# Old-name (without extension or prefix) → new track filename without extension.
# Built by inspecting library/templates/**/*.json — see the README of this script.
TRACK_MAP: dict[str, str] = {
    # 3 ACTIVE EDLs (FREE_EDLS in kondos-api)
    "CITY_BEAT_V2": "cool-lounge-403501",
    "DREAM_POP_V2": "downtempo-cinematic-ambient-beat-515885",
    "SONOMA_WITH_TITLE": "elegant-corporate-inspiration-2-506051",
    # Coastal / luxury / wine country
    "BELAIR_NO_TITLE": "black-gold-luxury-lounge-collection-388752",
    "BELAIR_WITH_TITLE": "black-gold-luxury-lounge-collection-388752",
    "BIG_SUR_NO_TITLE": "downtempo-cinematic-ambient-beat-515885",
    "BIG_SUR_WITH_TITLE": "downtempo-cinematic-ambient-beat-515885",
    "CALISTOGA_NO_TITLE": "elegant-corporate-inspiration-2-506051",
    "CALISTOGA_WITH_TITLE": "elegant-corporate-inspiration-2-506051",
    "CARMEL_NO_TITLE": "elegant-elegant-music-508012",
    "CARMEL_WITH_TITLE": "elegant-elegant-music-508012",
    "LAGUNA_NO_TITLE": "platinum-sky-luxury-lounge-collection-388749",
    "LAGUNA_WITH_TITLE": "platinum-sky-luxury-lounge-collection-388749",
    "MALIBU_NO_TITLE": "velvet-dreams-luxury-lounge-collection-388755",
    "MALIBU_WITH_TITLE": "velvet-dreams-luxury-lounge-collection-388755",
    "NAPA_NO_TITLE": "elegant-corporate-inspiration-2-506051",
    "NAPA_WITH_TITLE": "elegant-corporate-inspiration-2-506051",
    "OJAI_NO_TITLE": "rain-waves-soul-hip-hop-512540",
    "OJAI_WITH_TITLE": "rain-waves-soul-hip-hop-512540",
    "PIONEERTOWN_NO_TITLE": "downtempo-cinematic-ambient-beat-515885",
    "PIONEERTOWN_WITH_TITLE": "downtempo-cinematic-ambient-beat-515885",
    "PRESIDIO_NO_TITLE": "luminous-future-corporate-tech-413585",
    "PRESIDIO_WITH_TITLE": "luminous-future-corporate-tech-413585",
    "SANTACRUZ_NO_TITLE": "cool-lounge-403501",
    "SANTACRUZ_WITH_TITLE": "cool-lounge-403501",
    "TAHOE_NO_TITLE": "harmony-in-motion-235766",
    "TAHOE_WITH_TITLE": "harmony-in-motion-235766",
    "VENICE_NO_TITLE": "electronic-smooth-bossa-jazz-482901",
    "VENICE_WITH_TITLE": "electronic-smooth-bossa-jazz-482901",
    # Misc
    "AMBIENT_DANIEL_GALE_TITLE": "harmony-in-motion-235766",
    "PIANI_BREAK_WITH_TITLE": "harmony-in-motion-235766",
    "SONATA_V2": "elegant-elegant-music-508012",
}

# Fallback for any old-name we didn't anticipate. Neutral, works for
# most EDL aesthetics. Keeps the script idempotent on unexpected names.
FALLBACK_TRACK = "elegant-elegant-music-508012"

GS_URI_REGEX = re.compile(
    r"gs://editora-v2-templates/music/(?P<name>[A-Z0-9_]+)\.(?P<ext>[a-z0-9]+)"
)


def remap_uri(old_uri: str) -> str:
    match = GS_URI_REGEX.fullmatch(old_uri)
    if not match:
        # Already migrated, or non-music gs:// URI — leave untouched.
        return old_uri
    old_name = match.group("name")
    new_name = TRACK_MAP.get(old_name, FALLBACK_TRACK)
    return f"{R2_PREFIX}{new_name}.mp3"


def patch_file(path: Path) -> tuple[bool, str | None]:
    """
    Return (changed, old_uri). When changed=True, old_uri is what we
    rewrote so the script's report tells you which tracks moved.
    """
    text = path.read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"  [SKIP] {path}: invalid JSON — {exc}", file=sys.stderr)
        return False, None

    old_uri = data.get("soundtrack_uri")
    if not isinstance(old_uri, str) or not old_uri.startswith("gs://"):
        return False, None

    new_uri = remap_uri(old_uri)
    if new_uri == old_uri:
        return False, None

    data["soundtrack_uri"] = new_uri
    # Preserve trailing newline + 2-space indent matching existing files
    out = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(out + "\n")
    return True, old_uri


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate EDL music URIs to R2.")
    parser.add_argument("--dry", action="store_true", help="Report only, no writes.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent / "library" / "templates"),
        help="EDL templates root (default: kondo-movie/library/templates).",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Templates root not found: {root}", file=sys.stderr)
        return 1

    files = sorted(root.rglob("*.json"))
    changed = 0
    untouched = 0
    for path in files:
        if args.dry:
            text = path.read_text()
            if "gs://editora-v2-templates" in text:
                print(f"  [DRY] would update {path.relative_to(root.parent.parent)}")
                changed += 1
            else:
                untouched += 1
        else:
            did_change, old_uri = patch_file(path)
            if did_change:
                rel = path.relative_to(root.parent.parent)
                print(f"  [DONE] {rel}: {old_uri}")
                changed += 1
            else:
                untouched += 1

    action = "would update" if args.dry else "updated"
    print(f"\n{action} {changed} files, {untouched} unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
