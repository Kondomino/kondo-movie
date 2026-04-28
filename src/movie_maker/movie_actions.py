# movie_actions.py
#
# Stateless render handler. The engine no longer persists anything to
# Firestore — the v2 contract carries all identity (agent + kondo + job)
# in the request payload, and kondos-api owns the canonical Video /
# VideoVersion / VideoJob state. See video-tool-plan.html Apêndice C.
#
# What this module does per request:
#   1. Load the EDL template from disk (library/templates/)
#   2. Download input images (http(s) URLs from kondos-api)
#   3. Classify them (per-image cache via kondos-api HTTP)
#   4. Pick ordered images, render the movie, transcode
#   5. Upload outputs to active storage provider (DO Spaces / R2)
#   6. Return a Story with the public output URL
#
# Webhook firing back to kondos-api lives in main.py.

import os
import uuid
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple, List, Optional
from zoneinfo import ZoneInfo

from config.config import settings
from logger import logger
from movie_maker.movie_actions_model import (
    MakeMovieRequest,
    MakeMovieResponse,
    PreselectForTemplateRequest,
    PreselectForTemplateResponse,
    Story,
)
from utils.common_models import ActionStatus, Session
from movie_maker.movie_model import MovieModel, MovieMakerResponseModel
from movie_maker.movie import MovieMaker
from movie_maker.edl_manager import EDLManager
from movie_maker.edl_model import EDL
from movie_maker.image_fetch import download_http_image, suffix_from_url, is_http_url
from gcp.storage_model import CloudPath
from gcp.storage import StorageManager as GCPStorageManager
from storage_manager import StorageManager as UnifiedStorageManager

from classification.image_classification_manager import ImageClassificationManager
from classification.classification_model import ImageBuckets


_OUTPUT_KEY_PREFIX = "videos"


class MovieActionsHandler:
    """
    Stateless make-movie handler. Each request is independent — no
    Firestore reads/writes, no project-level cache, no version snapshots.
    The per-image classification cache (handled inside
    ImageClassificationManager.label_image) is the only state lookup,
    and that's via HTTP to kondos-api.
    """

    def make_movie(self, request: MakeMovieRequest) -> MakeMovieResponse:
        logger.info(
            f"Incoming render request: user={request.request_id.user.id} "
            f"project={request.request_id.project.id} "
            f"version={request.request_id.version.id if request.request_id.version else None} "
            f"template={request.template}"
        )

        created = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
        result, story = self._process_movie(request)
        last_updated = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))

        if result.state == ActionStatus.State.SUCCESS:
            logger.success(
                f"Render OK: project={request.request_id.project.id} "
                f"version={request.request_id.version.id if request.request_id.version else None}"
            )
        else:
            logger.error(
                f"Render FAIL: project={request.request_id.project.id} "
                f"reason={result.reason}"
            )

        return MakeMovieResponse(
            request_id=request.request_id,
            result=result,
            created=created,
            last_updated=last_updated,
            story=story,
        )

    def preselect_imagges_for_template(
        self, request: PreselectForTemplateRequest
    ) -> PreselectForTemplateResponse:
        """
        Standalone classify-and-preselect endpoint, kept for parity with
        the legacy Editora API. Stateless here too — caller supplies the
        image set; we run classification + selection without touching
        Firestore.
        """
        edl = EDLManager.load_edl(edl_id=request.template, with_title=False)
        if not edl:
            return PreselectForTemplateResponse(
                result=ActionStatus(
                    state=ActionStatus.State.FAILURE,
                    reason=f"Cannot load EDL '{request.template}'",
                ),
                template=request.template,
            )

        # Without a project_ref, this endpoint can't materialize image
        # buckets from a stored cache — callers should use POST /make_movie
        # with explicit `ordered_images` for the v2 flow. Returning a
        # clean failure is preferable to silently skipping.
        return PreselectForTemplateResponse(
            result=ActionStatus(
                state=ActionStatus.State.FAILURE,
                reason="preselect_for_template requires a project image cache; "
                       "use POST /make_movie with ordered_images instead.",
            ),
            template=request.template,
        )

    # --------------------------------------------------------------------------
    # Internal pipeline
    # --------------------------------------------------------------------------

    def _process_movie(
        self, request: MakeMovieRequest
    ) -> Tuple[ActionStatus, Optional[Story]]:
        video_local_path = None
        voiceover_local_path = None
        captions_local_path = None

        try:
            orientation = (
                request.config.image_orientation.value.lower()
                if request.config and request.config.image_orientation
                else "landscape"
            )
            edl = EDLManager.load_edl(
                edl_id=request.template,
                with_title=(request.config.end_titles is not None),
                orientation=orientation,
            )
            if edl is None:
                raise ValueError(f"EDL '{request.template}' not found in bundled templates")

            min_shots = MovieMaker.image_clip_count(edl=edl, config=request.config)

            with TemporaryDirectory() as images_folder:
                (
                    images_path_l2c_mapping,
                    _images_path_c2l_mapping,
                    loaded_local_paths,
                ) = self._fetch_images(images_folder, request)

                # Classification is dead work on the v2 path (request.ordered_images
                # is populated; _generate_ordered_images returns those URLs as-is
                # without consulting buckets). Skip the GCP Vision call entirely
                # to avoid the 15s/render ADC-discovery latency and the noisy
                # per-image errors. Legacy `image_repos` flow still classifies
                # because it actually needs the buckets.
                # See `project_classification_noise.md` for the design rationale.
                classification_mgr = ImageClassificationManager()
                if request.ordered_images:
                    image_buckets_local = None  # not consulted on the v2 path
                else:
                    image_buckets_local = classification_mgr.run_classification_for_files(
                        image_file_paths=loaded_local_paths
                    )

                ordered_images = self._generate_ordered_images(
                    request,
                    classification_mgr,
                    min_shots,
                    image_buckets_local,
                    loaded_local_paths,
                )

                make_movie_rsp: MovieMakerResponseModel = self._generate_movie(
                    edl, request, ordered_images
                )
                video_local_path = make_movie_rsp.video_file_path
                voiceover_local_path = make_movie_rsp.voiceover_file_path
                captions_local_path = make_movie_rsp.captions_file_path
                used_images = make_movie_rsp.used_images

                if not video_local_path:
                    raise ValueError("Render finished without producing a video file")

                output_url = self._upload_video(
                    video_local_path=video_local_path,
                    session=request.request_id,
                )

                # Voiceover and captions uploads are best-effort — they're
                # nice-to-have artifacts but the only thing kondos-api
                # actually needs is the final MP4 URL.
                if voiceover_local_path and os.path.exists(voiceover_local_path):
                    try:
                        self._upload_artifact(voiceover_local_path, request.request_id)
                    except Exception as upload_err:
                        logger.warning(f"Voiceover upload skipped: {upload_err}")
                if captions_local_path and os.path.exists(captions_local_path):
                    try:
                        self._upload_artifact(captions_local_path, request.request_id)
                    except Exception as upload_err:
                        logger.warning(f"Captions upload skipped: {upload_err}")

                story = Story(
                    template=edl.name,
                    config=request.config,
                    used_images=[
                        images_path_l2c_mapping[local_path]
                        for local_path in used_images
                    ],
                    movie_path=output_url,
                )
                return ActionStatus(state=ActionStatus.State.SUCCESS), story

        except (KeyError, ValueError) as kve:
            logger.error(kve)
            return ActionStatus(state=ActionStatus.State.FAILURE, reason=str(kve)), None
        except Exception as e:
            logger.exception(e)
            return ActionStatus(state=ActionStatus.State.FAILURE, reason=str(e)), None
        finally:
            for path in (video_local_path, voiceover_local_path, captions_local_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def _fetch_images(
        self, images_folder: str, request: MakeMovieRequest
    ) -> Tuple[dict, dict, list]:
        """
        Download input images to a local temp folder. The v2 flow always
        sends an explicit ordered list (`ordered_images`); the legacy
        `image_repos` branch is preserved for parity with the old API
        but isn't reached from kondos-api today.
        """
        images_path_l2c_mapping = {}
        images_path_c2l_mapping = {}
        loaded_local_paths = []

        if not request.ordered_images:
            # Legacy multi-repo aggregation. No project_ref to consult
            # for `excluded_images` in the stateless world — callers
            # filter upstream now.
            for repo in request.image_repos or []:
                cloud_path = CloudPath.from_path(repo)
                subfolder_uuid = str(uuid.uuid4())
                images_subfolder = os.path.join(images_folder, subfolder_uuid)
                os.makedirs(images_subfolder, exist_ok=True)

                sub_l2c, sub_c2l = GCPStorageManager.load_blobs(
                    cloud_path=cloud_path,
                    dest_dir=images_subfolder,
                    excluded_files=None,
                )
                images_path_l2c_mapping.update(sub_l2c)
                images_path_c2l_mapping.update(sub_c2l)

            loaded_local_paths = [
                str(file) for file in Path(images_folder).rglob("*") if file.is_file()
            ]
        else:
            # v2 flow: explicit ordered URLs. http(s) → streaming HTTP
            # download, gs:// → existing GCP code path.
            for source_url in request.ordered_images:
                if is_http_url(source_url):
                    filename = f"{uuid.uuid4()}{suffix_from_url(source_url)}"
                    local_path = os.path.join(images_folder, filename)
                    download_http_image(source_url, local_path)
                    images_path_l2c_mapping[local_path] = source_url
                else:
                    cloud_path = CloudPath.from_path(source_url)
                    filename = f"{uuid.uuid4()}{cloud_path.path.suffix}"
                    local_path = os.path.join(images_folder, filename)
                    GCPStorageManager.load_blob(cloud_path=cloud_path, dest_file=local_path)
                    images_path_l2c_mapping[local_path] = cloud_path.full_path()
                loaded_local_paths.append(local_path)

        return images_path_l2c_mapping, images_path_c2l_mapping, loaded_local_paths

    def _generate_ordered_images(
        self,
        request: MakeMovieRequest,
        classification_mgr: ImageClassificationManager,
        min_shots: int,
        image_buckets_local: ImageBuckets,
        loaded_local_paths: list,
    ) -> List[str]:
        if not request.ordered_images:
            ordered_images = classification_mgr.run_selection(
                buckets=image_buckets_local,
                num_clips=min_shots,
                verbose=True,
            )
        else:
            ordered_images = loaded_local_paths

        if not ordered_images:
            raise ValueError("Failed to load or select images needed to make movie")

        if len(ordered_images) < min_shots:
            raise ValueError(
                f"Not enough images to make movie. Need at least {min_shots}, found {len(ordered_images)}"
            )
        return ordered_images

    def _generate_movie(
        self, edl, request: MakeMovieRequest, ordered_images: List[str]
    ) -> MovieMakerResponseModel:
        """
        Build the MovieModel from the request and run the renderer.
        Agent name is taken from the request payload now (v2 contract);
        the old Firestore user-doc lookup is gone.
        """
        movie_model = MovieModel(
            edl=edl,
            ordered_images=ordered_images,
            config=request.config,
            user_id=request.request_id.user.id,
            agent_name=request.agent_name,
        )
        movie_maker = MovieMaker(movie_model=movie_model)
        return movie_maker.make_movie()

    # --------------------------------------------------------------------------
    # Output upload
    # --------------------------------------------------------------------------

    def _upload_video(self, video_local_path: Path, session: Session) -> str:
        """
        Upload the rendered MP4 to the active storage provider and return
        a public URL kondos-api can store on VideoVersion.outputVideoUrl.
        """
        bucket, key = self._video_bucket_and_key(video_local_path, session)
        unified = UnifiedStorageManager()
        unified.save_blob(source_file=video_local_path, bucket=bucket, key=key)
        return self._public_url(unified, bucket, key)

    def _upload_artifact(self, local_path: Path, session: Session) -> str:
        """Upload a sidecar artifact (voiceover wav, captions srt) under the same prefix."""
        bucket, key = self._video_bucket_and_key(local_path, session)
        unified = UnifiedStorageManager()
        unified.save_blob(source_file=local_path, bucket=bucket, key=key)
        return self._public_url(unified, bucket, key)

    def _video_bucket_and_key(self, local_path: Path, session: Session) -> Tuple[str, str]:
        bucket = self._active_user_bucket()
        key = "/".join(
            [
                _OUTPUT_KEY_PREFIX,
                str(session.user.id),
                str(session.project.id),
                str(session.version.id) if session.version else "no-version",
                local_path.name,
            ]
        )
        return bucket, key

    def _active_user_bucket(self) -> str:
        provider = settings.Storage.PROVIDER
        if provider == "CloudflareR2":
            return settings.Cloudflare.R2.USER_BUCKET
        if provider == "DigitalOcean":
            return settings.DigitalOcean.Spaces.USER_BUCKET
        # GCP fallback (legacy Editora) — not used in kondomino.
        return settings.GCP.Storage.USER_BUCKET

    def _public_url(self, unified: UnifiedStorageManager, bucket: str, key: str) -> str:
        """
        Compose a publicly accessible URL for a written object.
        Falls back to a signed URL if a public CDN/custom-domain prefix
        isn't configured. Long-term, kondos-api may want to store
        bucket+key and re-sign on demand; this is the v1 simple path.
        """
        public_prefix = self._public_url_prefix()
        if public_prefix:
            return f"{public_prefix.rstrip('/')}/{key}"
        # No public prefix → presigned view URL (24h default per config).
        return unified.generate_signed_url_for_view(bucket=bucket, key=key)

    def _public_url_prefix(self) -> Optional[str]:
        provider = settings.Storage.PROVIDER
        if provider == "CloudflareR2":
            return os.getenv("CLOUDFLARE_R2_PUBLIC_URL") or None
        if provider == "DigitalOcean":
            return os.getenv("DIGITAL_OCEAN_CDN_ENDPOINT") or None
        return None
