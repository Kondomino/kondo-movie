# movie_actions.py
import concurrent.futures
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import uuid
from typing import Tuple, Any, List, Dict, Optional


from config.config import settings
from logger import logger
from utils.common_models import Session
from utils.session_utils import get_session_refs, get_session_refs_by_ids
from movie_maker.movie_actions_model import *
from movie_maker.movie_model import MovieModel, MovieMakerResponseModel
from movie_maker.movie import MovieMaker
from movie_maker.edl_manager import EDLManager
from movie_maker.edl_model import EDL
from gcp.storage_model import CloudPath
from gcp.storage import StorageManager
from project.project_backfill import *
from project.project_stats_manager import ProjectStatsManager

from classification.image_classification_manager import ImageClassificationManager
from classification.classification_model import ImageBuckets


class MovieActionsHandler:
    """
    Encapsulates all logic for handling the 'make_movie' request,
    including Firestore checks, EDL loading, image classification,
    movie creation, and final upload.
    """

    def make_movie(self, request: MakeMovieRequest) -> MakeMovieResponse:
        """
        Public entry point.
        1) Checks if version already exists,
        2) Updates a 'pending' VersionSnapshot,
        3) Runs main movie logic,
        4) Updates final snapshot,
        5) Returns MakeMovieResponse.
        """
        logger.info(
            f"Incoming request : {request.request_id.model_dump_json(indent=2)}"
        )

        # 1) Check if version already exists
        _, project_ref, version_ref = get_session_refs(request.request_id)
        version = version_ref.get()
        if version.exists:
            reason = f"Version ID '{request.request_id.version.id}' already exists"
            logger.error(reason)
            return MakeMovieResponse(
                request_id=request.request_id,
                result=ActionStatus(state=ActionStatus.State.FAILURE, reason=reason),
                created=datetime.now(
                    tz=ZoneInfo(settings.General.TIMEZONE)
                ),  # Not quite. Ideally want to fetch from DB
                last_updated=datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)),
            )

        # 2) Store a VersionSnapshot in 'pending' state
        created = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
        self._update_version_snapshot(
            version_ref=version_ref,
            request=request,
            status=ActionStatus(state=ActionStatus.State.PENDING),
            time=VersionSnapshot.Time(created=created),
        )

        # 2b) Update project's version stats
        ProjectStatsManager(project_ref=project_ref).handle_movie_pending()

        # 3) Main movie logic (EDL load, images, classification, etc.)
        result, story = self._process_movie(project_ref, request)

        # 4) Build final response
        last_updated = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
        response = MakeMovieResponse(
            request_id=request.request_id,
            result=result,
            created=created,
            last_updated=last_updated,
            story=story,
        )

        # 5) Final snapshot update
        self._update_version_snapshot(
            version_ref=version_ref,
            status=result,
            time=VersionSnapshot.Time(
                created=created,
                updated=last_updated,
                duration=int((last_updated - created).total_seconds()),
            ),
            story=story,
        )

        if result.state == ActionStatus.State.SUCCESS:
            # Update version stats
            logger.info(f"Successfully made movie for project '{project_ref.id}'")
            ProjectStatsManager(project_ref=project_ref).handle_movie_success()
        else:
            logger.error(
                f"Failed to make movie for project '{project_ref.id}': {result.reason}"
            )
            ProjectStatsManager(project_ref=project_ref).handle_movie_failure()

        return response

    def preselect_imagges_for_template(
        self, request: PreselectForTemplateRequest
    ) -> PreselectForTemplateResponse:
        _, project_ref, _ = get_session_refs(
            session=Session(user=request.user, project=request.project)
        )

        image_buckets = self._get_image_classification_buckets(project_ref=project_ref)
        if not image_buckets:
            failure_reason = f"Cannot find image classification buckets for project. User ID: `{request.user.id}`, Project ID: `{request.project.id}`"
            logger.error(failure_reason)
            return PreselectForTemplateResponse(
                result=ActionStatus(
                    state=ActionStatus.State.FAILURE, reason=failure_reason
                ),
                template=request.template,
            )

        edl = EDLManager.load_edl(edl_id=request.template, with_title=False)
        if not edl:
            failure_reason = f"Failed to generate image classification for project. User ID: `{request.user.id}`, Project ID: `{request.project.id}` - Cannot load EDL `{request.template}`"

            logger.error(failure_reason)
            return PreselectForTemplateResponse(
                result=ActionStatus(
                    state=ActionStatus.State.FAILURE, reason=failure_reason
                ),
                template=request.template,
            )

        image_list = self._run_selection_for_edl(
            edl=edl,
            classification_mgr=ImageClassificationManager(),
            image_buckets=image_buckets,
        )

        if image_list:
            logger.info(
                f"Images preselected for EDL `{request.template}`, User ID: `{request.user.id}`, Project ID: `{request.project.id}`"
            )
            return PreselectForTemplateResponse(
                result=ActionStatus(state=ActionStatus.State.SUCCESS),
                template=request.template,
                preselected_images=image_list,
            )
        else:
            failure_reason = f"Failed to generate image classification for project. User ID: `{request.user.id}`, Project ID: `{request.project.id}` - Failed to run selection for EDL `{request.template}`"
            logger.error(failure_reason)
            return PreselectForTemplateResponse(
                result=ActionStatus(
                    state=ActionStatus.State.FAILURE, reason=failure_reason
                ),
                template=request.template,
            )

    # --------------------------------------------------------------------------
    # Internal methods
    # --------------------------------------------------------------------------

    def _process_movie(
        self, project_ref: Any, request: MakeMovieRequest
    ) -> Tuple[ActionStatus, Optional[Story]]:
        """
        Orchestrates the steps for making a movie:
          1) Load EDL
          2) Fetch images
          3) Get or create image classification
          3B) Spawn of job to run selection for all templates for future use
          4) Pick final images (ordered)
          5) Create the movie
          6) Upload final artifacts
        Returns (ActionStatus, Story).
        """
        video_local_path = None
        voiceover_local_path = None
        captions_local_path = None

        try:
            # 1) Load EDL by template ID
            edl = EDLManager.load_edl(
                edl_id=request.template, with_title=(request.config.end_titles != None)
            )
            # Determine how many shots needed from EDL + config
            min_shots = MovieMaker.image_clip_count(edl=edl, config=request.config)

            print("🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷🇧🇷")
            print(f"min_shots: {min_shots}")

            # 2) Fetch images to a temp folder
            with TemporaryDirectory() as images_folder:
                (
                    images_path_l2c_mapping,
                    images_path_c2l_mapping,
                    loaded_local_paths,
                ) = self._fetch_images(images_folder, request)

                # 3) Get or create classification
                classification_mgr = ImageClassificationManager()
                image_buckets_local = self._get_or_create_image_classification_buckets(
                    classification_mgr=classification_mgr,
                    project_ref=project_ref,
                    images_folder=images_folder,
                    images_path_l2c_mapping=images_path_l2c_mapping,
                    images_path_c2l_mapping=images_path_c2l_mapping,
                )

                # # 3B) Spawn of job to run selection for all templates for future use
                # status = self._generate_and_store_for_all_edls(
                #     classification_mgr=classification_mgr,
                #     image_buckets_local=image_buckets_local,
                #     images_path_l2c_mapping=images_path_l2c_mapping,
                #     project_ref=project_ref
                # )
                # if status.state == ActionStatus.State.SUCCESS:
                #     logger.info("Images preselected for all templates!")
                # else:
                #     logger.error(f"Failed to preselect images for all templates: {status.reason}")

                # 4) Determine final ordered images
                ordered_images = self._generate_ordered_images(
                    request,
                    classification_mgr,
                    min_shots,
                    image_buckets_local,
                    loaded_local_paths,
                )

                # 5) Generate the movie
                make_movie_rsp: MovieMakerResponseModel = self._generate_movie(
                    edl, request, ordered_images
                )
                video_local_path = make_movie_rsp.video_file_path
                voiceover_local_path = make_movie_rsp.voiceover_file_path
                captions_local_path = make_movie_rsp.captions_file_path
                used_images = make_movie_rsp.used_images

                if not video_local_path:
                    raise ValueError(
                        "Cannot upload video to cloud; no local path available"
                    )

                # 6) Upload to cloud
                session = request.request_id
                (video_cloud_path, voiceover_cloud_path, captions_cloud_path) = (
                    self._upload_assets(
                        video_local_path,
                        voiceover_local_path,
                        captions_local_path,
                        session,
                    )
                )

                # Success result
                logger.success(
                    f"Video created and uploaded to path : {video_cloud_path.full_path()}"
                )
                result = ActionStatus(state=ActionStatus.State.SUCCESS)
                story = Story(
                    template=edl.name,
                    config=request.config,
                    used_images=[
                        images_path_l2c_mapping[local_path]
                        for local_path in used_images
                    ],
                    movie_path=video_cloud_path.full_path(),
                )
                return result, story

        except (KeyError, ValueError) as kve:
            logger.error(kve)
            return ActionStatus(state=ActionStatus.State.FAILURE, reason=str(kve)), None
        except Exception as e:
            logger.exception(e)
            return ActionStatus(state=ActionStatus.State.FAILURE, reason=str(e)), None
        finally:
            # Cleanup local artifacts if they were created
            if video_local_path and os.path.exists(video_local_path):
                os.remove(video_local_path)
            if voiceover_local_path and os.path.exists(voiceover_local_path):
                os.remove(voiceover_local_path)
            if captions_local_path and os.path.exists(captions_local_path):
                os.remove(captions_local_path)

    def _fetch_images(
        self, images_folder: str, request: MakeMovieRequest
    ) -> Tuple[dict, dict, list]:
        """
        Copies images from cloud to a local temp folder.
        Returns (images_path_l2c_mapping, images_path_c2l_mapping, loaded_local_paths).
        """
        images_path_l2c_mapping = {}
        images_path_c2l_mapping = {}
        loaded_local_paths = []

        _, project_ref, _ = get_session_refs(request.request_id)
        excluded_files = project_ref.get().to_dict().get("excluded_images", None)

        # If user did not provide an explicitly ordered list, then we fetch from multiple repos
        if not request.ordered_images:
            for repo in request.image_repos:
                cloud_path = CloudPath.from_path(repo)
                subfolder_uuid = str(uuid.uuid4())
                images_subfolder = os.path.join(images_folder, subfolder_uuid)
                os.makedirs(images_subfolder, exist_ok=True)

                sub_l2c, sub_c2l = StorageManager.load_blobs(
                    cloud_path=cloud_path,
                    dest_dir=images_subfolder,
                    excluded_files=excluded_files,
                )
                images_path_l2c_mapping.update(sub_l2c)
                images_path_c2l_mapping.update(sub_c2l)

            loaded_local_paths = [
                str(file) for file in Path(images_folder).rglob("*") if file.is_file()
            ]
        else:
            # If user has an ordered list, copy each image individually
            for gs_path in request.ordered_images:
                cloud_path = CloudPath.from_path(gs_path)
                filename = f"{uuid.uuid4()}{cloud_path.path.suffix}"
                local_path = os.path.join(images_folder, filename)
                StorageManager.load_blob(cloud_path=cloud_path, dest_file=local_path)
                images_path_l2c_mapping[local_path] = cloud_path.full_path()
                loaded_local_paths.append(local_path)

        return images_path_l2c_mapping, images_path_c2l_mapping, loaded_local_paths

    def _get_image_classification_buckets(
        self,
        project_ref: Any,
    ) -> ImageBuckets:
        """
        Checks Firestore for existing classification. If not found, returns None
        """
        IMAGE_CLASSIFICATION_KEY = settings.Classification.IMAGE_CLASSIFICATION_KEY
        project_doc = project_ref.get()

        image_buckets_cloud = None
        if project_doc.exists and IMAGE_CLASSIFICATION_KEY in (
            project_dict := project_doc.to_dict()
        ):
            logger.info("Image classification already exists for project! Using it.")
            # Convert Firestore data to model
            image_buckets_cloud = ImageBuckets.model_validate(
                project_dict[IMAGE_CLASSIFICATION_KEY]
            )

        return image_buckets_cloud

    def _get_or_create_image_classification_buckets(
        self,
        classification_mgr: ImageClassificationManager,
        project_ref: Any,
        images_folder: str,
        images_path_l2c_mapping: dict,
        images_path_c2l_mapping: dict,
    ) -> ImageBuckets:
        """
        Checks Firestore for existing classification. If not found, runs local classification and saves it.
        Returns the local version of ImageBuckets (with local URIs).
        """
        IMAGE_CLASSIFICATION_KEY = settings.Classification.IMAGE_CLASSIFICATION_KEY
        project_doc = project_ref.get()

        if project_doc.exists and IMAGE_CLASSIFICATION_KEY in (
            project_dict := project_doc.to_dict()
        ):
            logger.info("Image classification already exists for project! Using it.")
            # Convert Firestore data to model
            image_buckets_cloud = ImageBuckets.model_validate(
                project_dict[IMAGE_CLASSIFICATION_KEY]
            )

            # Convert cloud URIs -> local URIs
            image_buckets_local = ImageBuckets(buckets={})
            for category, item_list in image_buckets_cloud.buckets.items():
                local_items = []
                for item in item_list:
                    # item is an ImageBuckets.Item
                    local_uri = images_path_c2l_mapping.get(item.uri, item.uri)
                    local_item = ImageBuckets.Item(uri=local_uri, score=item.score)
                    local_items.append(local_item)
                image_buckets_local.buckets[category] = local_items

        else:
            logger.info("Image classification not found; creating a new one.")
            image_file_paths = [
                str(file) for file in Path(images_folder).rglob("*") if file.is_file()
            ]
            # Classify locally
            image_buckets_local = classification_mgr.run_classification_for_files(
                image_file_paths=image_file_paths
            )
            # ^ The 'run_classification_for_files' method presumably returns an ImageBuckets with 'buckets'

            # Convert local URIs -> cloud URIs, store in DB
            image_buckets_cloud = ImageBuckets(buckets={})
            for category, item_list in image_buckets_local.buckets.items():
                cloud_items = []
                for item in item_list:
                    cloud_uri = images_path_l2c_mapping.get(item.uri, item.uri)
                    cloud_item = ImageBuckets.Item(uri=cloud_uri, score=item.score)
                    cloud_items.append(cloud_item)
                image_buckets_cloud.buckets[category] = cloud_items

            if project_ref.get().exists:
                project_ref.update(
                    {IMAGE_CLASSIFICATION_KEY: image_buckets_cloud.model_dump()}
                )
            else:
                project_ref.set(
                    {IMAGE_CLASSIFICATION_KEY: image_buckets_cloud.model_dump()}
                )

        return image_buckets_local

    def _generate_ordered_images(
        self,
        request: MakeMovieRequest,
        classification_mgr: ImageClassificationManager,
        min_shots: int,
        image_buckets_local: ImageBuckets,
        loaded_local_paths: list,
    ) -> List[str]:
        """
        If user did not provide ordered_images, pick them by classification.
        Otherwise, we already have the local copies from _fetch_images.
        """
        if not request.ordered_images:
            ordered_images = classification_mgr.run_selection(
                buckets=image_buckets_local,
                num_clips=min_shots,
                verbose=True
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
        Create the MovieModel, run the MovieMaker, return paths to local artifacts.
        """
        from utils.session_utils import get_session_refs_by_ids

        user_ref, _, _ = get_session_refs_by_ids(user_id=request.request_id.user.id)
        user_doc = user_ref.get()
        agent_name = None
        if user_doc.exists:
            user_info = user_doc.to_dict().get("user_info", {})
            first_name = user_info.get("first_name", "")
            last_name = user_info.get("last_name", "")
            agent_name = f"{first_name} {last_name}".strip()
        movie_model = MovieModel(
            edl=edl,
            ordered_images=ordered_images,
            config=request.config,
            user_id=request.request_id.user.id,
            agent_name=agent_name,
        )
        movie_maker = MovieMaker(movie_model=movie_model)
        _, project_ref, version_ref = get_session_refs(request.request_id)
        response: MovieMakerResponseModel = movie_maker.make_movie()
        return response

    def _upload_assets(
        self,
        video_local_path: Path,
        voiceover_local_path: Path,
        captions_local_path: Path,
        session: Session,
    ) -> Tuple[CloudPath, Optional[CloudPath], Optional[CloudPath]]:
        """
        Uploads final assets (video, voiceover, captions) to Cloud Storage.
        Returns (video_cloud_path, voiceover_cloud_path, captions_cloud_path).
        """
        video_cloud_path = CloudPath(
            bucket_id=settings.GCP.Storage.USER_BUCKET,
            path=Path(
                session.user.id,
                session.project.id,
                session.version.id,
                video_local_path.name,
            ),
        )
        StorageManager.save_blob(
            source_file=video_local_path, cloud_path=video_cloud_path
        )

        voiceover_cloud_path = None
        captions_cloud_path = None

        # Voiceover
        if voiceover_local_path and os.path.exists(voiceover_local_path):
            voiceover_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(
                    session.user.id,
                    session.project.id,
                    session.version.id,
                    voiceover_local_path.name,
                ),
            )
            StorageManager.save_blob(
                source_file=voiceover_local_path, cloud_path=voiceover_cloud_path
            )

        # Captions
        if captions_local_path and os.path.exists(captions_local_path):
            captions_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(
                    session.user.id,
                    session.project.id,
                    session.version.id,
                    captions_local_path.name,
                ),
            )
            StorageManager.save_blob(
                source_file=captions_local_path, cloud_path=captions_cloud_path
            )

        return video_cloud_path, voiceover_cloud_path, captions_cloud_path

    def _run_selection_for_edl(
        self,
        edl: EDL,
        classification_mgr: ImageClassificationManager,
        image_buckets: ImageBuckets,
    ) -> List[str]:
        """
        Worker method run in a thread:
        2) Compute the required min_shots,
        3) Run selection from the classification.
        Returns a list of local file paths selected.
        """

        return classification_mgr.run_selection(
            buckets=image_buckets, num_clips=len(edl.clips)
        )

    def _generate_and_store_for_all_edls(
        self,
        classification_mgr: ImageClassificationManager,
        image_buckets_local: ImageBuckets,
        images_path_l2c_mapping: Dict[str, str],
        project_ref: Any,
    ) -> ActionStatus:
        """
        1) Runs selection for each EDL in parallel (non-blocking for others if you call this in a separate thread).
        2) Waits for all selections to finish.
        3) Converts local file paths to cloud URIs.
        4) Updates Firestore exactly once with the final map of EDL -> list of cloud paths.

        Returns an ActionStatus indicating success/failure.
        """
        project_doc = project_ref.get()

        # Simply return if preselection already exists
        if (
            project_doc.exists
            and settings.Classification.IMAGE_CLASSIFICATION_KEY
            in (project_dict := project_doc.to_dict())
            and settings.Classification.PRESELECTION_KEY
            in project_dict[settings.Classification.IMAGE_CLASSIFICATION_KEY]
        ):
            return ActionStatus(state=ActionStatus.State.SUCCESS)

        # Step A: Prepare concurrency for each EDL
        images_by_edl = {}  # { edl_name: [list_of_local_paths], ... }

        edls = EDLManager.load_all_edls()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_map = {}
            for edl in edls:
                future = executor.submit(
                    self._run_selection_for_edl,
                    edl,
                    classification_mgr,
                    image_buckets_local,
                )
                future_map[future] = edl.name

            # Step B: Collect results as they complete
            for future in concurrent.futures.as_completed(future_map):
                edl_name = future_map[future]
                try:
                    selected_local_paths = future.result()
                    images_by_edl[edl_name] = selected_local_paths
                except Exception as exc:
                    logger.error(f"Selection failed for EDL '{edl_name}': {exc}")
                    return ActionStatus(
                        state=ActionStatus.State.FAILURE,
                        reason=f"Failed to run selection for EDL '{edl_name}': {exc}",
                    )

        # Step C: Convert local -> cloud URIs for all EDLs
        # Example structure: { edl_id: ["gs://...", "gs://..."] }
        edl_selections_cloud = {}
        for edl_name, local_paths in images_by_edl.items():
            cloud_paths = [
                images_path_l2c_mapping.get(path, path) for path in local_paths
            ]
            edl_selections_cloud[edl_name] = cloud_paths

        # Step D: Single Firestore update
        preselection_key = f"{settings.Classification.IMAGE_CLASSIFICATION_KEY}.{settings.Classification.PRESELECTION_KEY}"
        try:
            project_ref.update({preselection_key: edl_selections_cloud})
            logger.info("Template pre-selections stored in Firestore:")
        except Exception as e:
            logger.exception("Failed to update Firestore with EDL selections")
            return ActionStatus(state=ActionStatus.State.FAILURE, reason=str(e))

        return ActionStatus(state=ActionStatus.State.SUCCESS)

    # --------------------------------------------------------------------------
    # Firestore helpers
    # --------------------------------------------------------------------------

    def _update_version_snapshot(
        self,
        version_ref: Any,
        request: MakeMovieRequest = None,
        status: ActionStatus = None,
        time: VersionSnapshot.Time = None,
        story: Story = None,
    ) -> VersionSnapshot:
        """
        Update or create a Firestore document with the current snapshot.
        """
        snapshot = VersionSnapshot(
            request=request, status=status, time=time, story=story
        )

        if version_ref.get().exists:
            payload = snapshot.model_dump(exclude_none=True)
            version_ref.update(payload)
            logger.info(
                f"Version Update:\n{snapshot.model_dump_json(exclude_none=True, indent=2)}"
            )
        else:
            payload = snapshot.model_dump()
            version_ref.set(payload)
            logger.info(f"Version Set:\n{snapshot.model_dump_json(indent=2)}")

        return snapshot
