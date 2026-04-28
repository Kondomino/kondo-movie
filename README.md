# kondo-movie

Stateless video engine for [Kondomino](https://kondomino.com.br). Renders cinematic property reels from images + an EDL template, called from `kondos-api` via the v2 `/make_movie` contract.

The engine is invoked by the platform — agents never hit it directly. It owns no state: identity, jobs, video versions, and image classifications all live in `kondos-api`'s Postgres. The engine receives a payload, renders an MP4 to Cloudflare R2, fires a lifecycle webhook, and forgets.

## Local dev

Requires Python 3.12 + Poetry.

```bash
poetry install
cp .env.template .env  # fill in storage creds + KONDOS_API_URL + tokens
cd src && poetry run uvicorn main:app --reload --port 8080
```

`kondos-api` should be reachable at `KONDOS_API_URL` (defaults to `localhost:3003`) for the image-classification cache. Without it, classification falls back to a per-image Cloud Vision call (which silently no-ops without GCP credentials).

## HTTP surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Health |
| `POST` | `/make_movie` | Render entry point (v2 proxied-identity contract) |
| `GET` | `/jobs/{id}/status` | **501** — placeholder for arq integration |
| `DELETE` | `/jobs/{id}` | **501** — placeholder for arq integration |

`POST /make_movie` accepts `MakeMovieRequestV2` (see `src/movie_maker/movie_actions_model.py`):

```json
{
  "job_id": "...",
  "agent": { "id": 5, "name": "...", "logo_url": "..." },
  "kondo": { "id": 239, "address": "...", "brokerage_logo_url": "..." },
  "media_urls": ["https://media.kondomino.com.br/..."],
  "description": "...",
  "edl_id": "city_beat | dream_pop | sonoma",
  "voice_id": "...",
  "music_url": null,
  "webhook_url": "https://api.kondomino.com.br/internal/...",
  "capabilities": { "duration_max_seconds": 60, "images_max": 12, "captions_enabled": false }
}
```

The route translates v2 → legacy `MakeMovieRequest`, runs `MovieActionsHandler.make_movie()`, and POSTs `{ phase: "done"|"failed", progress: 100, output_url|error }` to `webhook_url` with the `X-Internal-Token` shared secret.

## Feature flags

Set in `.env`; read at runtime.

| Flag | Default | Effect |
|---|---|---|
| `NARRATION_ACTIVE` | `false` | When `false`, the engine skips ElevenLabs entirely. v1 ships silent (music + image clips + text overlays). Flip to `true` once a paid TTS plan is in place. |
| `Storage.PROVIDER` (config.yaml) | `CloudflareR2` | Storage backend. `DigitalOcean` and `GCP` legacy adapters still in tree but inactive. |

## Repository layout

```
kondo-movie/
├── src/
│   ├── ai/                 # OpenAI + Cloud Vision adapters (legacy classification path)
│   ├── classification/     # Image classification + bucketing (cold on v2 path)
│   ├── cloudflare/         # R2 storage adapter (S3-compat)
│   ├── digitalocean/       # DO Spaces storage adapter (S3-compat)
│   ├── gcp/                # GCS storage + Secret Manager + Vision adapters (legacy, off by default)
│   ├── movie_maker/        # Core renderer: EDL parsing → MoviePy compose → upload
│   ├── notification/       # Email module (orphaned; kondos-api owns email now)
│   ├── classification_cache_client.py  # HTTP client for kondos-api's classifications cache
│   ├── config/             # YAML + env loader
│   ├── storage_manager.py  # Provider-aware storage facade
│   └── main.py             # FastAPI route layer
├── library/
│   ├── fonts/              # Bundled fonts for text overlays
│   └── templates/          # 45 EDL JSONs (3 active, 42 inactive — flag pending)
├── playground/             # Dev/test scripts (e2e harness for rio-by-yoo lives here)
├── scripts/                # One-shot ops scripts (R2 upload, classification seed)
└── tests/                  # Pytest suite
```

## Running tests

```bash
poetry run pytest tests/ -q
```

The suite covers the v2→legacy translation, the classification cache HTTP client, the engine webhook, the R2 adapter, the EDL loader, and the active-EDL smoke test.

## Active EDLs (v1)

Three families, five JSON files: `city_beat_landscape`, `city_beat_portrait`, `dream_pop_landscape`, `dream_pop_portrait`, `sonoma`. The other 42 EDLs in `library/templates/` are inactive in v1 and pending an `is_active=false` flag pass.

Soundtracks are R2-hosted under `https://media.kondomino.com.br/music/library/`. Re-running `scripts/upload_music_library_to_r2.py` is idempotent if the local library changes.

## Architecture context

The engine was forked from Editora's `editora-v2-movie-maker` and progressively hardened for kondomino: Stytch + account module purged (PR #6), R2 adapter added (PR #5), `gs://` + http(s) image fetching (PR #15), Firestore writes removed from the hot loop (PR #16), Editora-era code deleted (PR #17), v2 proxied-identity contract (PR #14), silent-render path with `NARRATION_ACTIVE` flag (PR #18). The full integration plan and phase history live at `references/kondo/architecture/video-tool-plan.html` (sibling repo).
