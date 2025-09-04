from dotenv import load_dotenv
import uuid, asyncio, random
import datetime as dt
import httpx
from fastapi import HTTPException

from logger import logger
from gcp.db import db_client
from gcp.storage import StorageManager
from gcp.storage import cloud_storage_client as storage_client
from gcp.secret import secret_mgr
from config.config import settings
from account.jwt_manager import verify_jwt, create_jwt
from movie_maker.edl_manager import EDLManager
from utils.db_utils import filter_active_projects, filter_active_projects_slim
from utils.session_utils import get_session_refs_by_ids
from video.video_processor import LazyVideoLoader

# Import Pydantic models for requests/responses.
from account.account_model import *
from video.video_actions_model import *
from movie_maker.movie_actions_model import *
from movie_maker.movie_actions import MovieActionsHandler
from movie_maker.edl_manager import EDL
from movie_maker.voiceover_model import ElevenLabs
from movie_maker.voiceover_manager import VoiceoverManager
from account.account_model import UserData
from notification.email_service import send_video_completion_mail, send_video_failure_mail
from notification.send_notification import send_notification
from project.project_manager import ProjectManager
from project.project_backfill import *
from project.project_stats_manager import ProjectStatsManager

load_dotenv()

ACTUAL_VIDEO_COUNT = 100

class VideoActionsHandler:
    def __init__(self, user_data:UserData):
        self.user_data = user_data  # Expects an object with an attribute 'id'
        self.prev_doc_snapshot = None

    # --- Endpoint Methods ---

    def fetch_edls(self) -> FetchEDLSResponse:
        try:
            edls = []
            edl_collection_ref = EDLManager.get_collection_ref(with_title=False)
            for doc in edl_collection_ref.stream():
                data = doc.to_dict()
                gs_url = data.get("soundtrack_uri")
                if gs_url:
                    data["music_url"] = StorageManager.generate_signed_url_from_gs_url(gs_url)
                edls.append(data)
            edls.sort(key=lambda e: e.get("rank", 0))
            
            # No template filtering - everyone gets all templates
            logger.info(f"Returning {len(edls)} templates (no access restrictions)")
            
            return FetchEDLSResponse(message="EDLS data fetched!", edls=edls)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_voices(self) -> FetchVoicesResponse:
        try:
            voiceover_model = VoiceoverManager().get_voice_mappings()
            if not voiceover_model:
                raise FileNotFoundError(f"Voice mappings document doesn't exist in Firestore")
                
            voices = []
            for voice in voiceover_model.voice_mappings:
                sample_uri = voice.sample_audio_uri
                if sample_uri:
                    voice_dict = voice.model_dump()
                    voice_dict["ai_audio_url"] = StorageManager.generate_signed_url_from_gs_url(str(sample_uri))
                    voices.append(voice_dict)
                else:
                    voices.append(voice.model_dump())
                    
            voices.sort(key=lambda v: v.get("rank", 0))
            return FetchVoicesResponse(message="AI voices fetched!", voices=voices)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def new_media_uploaded(self, request: NewMediaUploadedRequest) -> NewMediaUploadedResponse:
        try:
            project_manager = ProjectManager(
                user_id=self.user_data.id,
                project_id=request.project_id
            )
            project_manager.media_updated()
            return NewMediaUploadedResponse(
                message='Media successfully uploaded'
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_video_scenes_classification(self, video_uri: str, project_id: str) -> FetchVideoScenesResponse:
        """
        Fetch scene classifications for a specific video using the new consistent storage pattern.
        Called when user opens VideoPlayerModal.
        """
        try:
            from classification.storage.video_scene_storage import VideoScenesStorage
            
            logger.info(f"[VIDEO_ACTIONS] Fetching scene classification for video: {video_uri}")
            
            # Fetch video scene data using the new storage pattern
            classification_data = VideoScenesStorage.fetch_video_scenes(
                user_id=self.user_data.id,
                project_id=project_id,
                video_uri=video_uri
            )
            
            if not classification_data:
                logger.warning(f"[VIDEO_ACTIONS] No scene classification found for video: {video_uri}")
                return FetchVideoScenesResponse(
                    message="No scene classification found for this video",
                    video_uri=video_uri,
                    total_scenes=0,
                    scenes=[],
                    video_duration=0.0
                )
            
            # Convert scenes to display format
            display_scenes = []
            for scene in classification_data.get('scenes', []):
                display_scene = VideoSceneDisplay(
                    scene_id=scene['scene_id'],
                    start_time=scene['start_time'],
                    end_time=scene['end_time'],
                    duration=scene['duration'],
                    scene_type=scene.get('scene_type', 'unknown'),
                    scene_category=scene.get('scene_category', 'unknown'),
                    primary_label=scene.get('primary_label', 'Unknown'),
                    confidence=scene.get('scene_confidence', 0.0),
                    emoji=self._get_scene_emoji(scene.get('scene_category', 'unknown'), scene.get('scene_type', 'unknown')),
                    display_name=self._get_scene_display_name(scene.get('scene_type', 'unknown'), scene.get('primary_label', 'Unknown'))
                )
                display_scenes.append(display_scene)
            
            logger.info(f"[VIDEO_ACTIONS] Successfully retrieved {len(display_scenes)} scenes for video: {video_uri}")
            
            return FetchVideoScenesResponse(
                message="Scene classification retrieved successfully",
                video_uri=video_uri,
                total_scenes=len(display_scenes),
                scenes=display_scenes,
                video_duration=classification_data.get('video_duration', 0.0)
            )
            
        except Exception as e:
            logger.error(f"[VIDEO_ACTIONS] Failed to fetch video scene classification: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch scene classification: {str(e)}")
    
    def _get_scene_emoji(self, scene_category: str, scene_type: str) -> str:
        """Get appropriate emoji for scene type"""
        emoji_map = {
            # Indoor rooms
            'kitchen': '🍳',
            'living_room': '🛋️',
            'bedroom': '🛏️',
            'bathroom': '🛁',
            'office': '💼',
            'dining_room': '🍽️',
            
            # Outdoor areas
            'pool_area': '🏊',
            'patio': '🪴',
            'balcony': '🌸',
            'garden': '🌻',
            'outdoor_generic': '🌳',
            
            # Generic
            'interior_generic': '🏠',
        }
        
        # Try specific scene type first
        if scene_type in emoji_map:
            return emoji_map[scene_type]
        
        # Fall back to category
        if scene_category == 'indoor':
            return '🏠'
        elif scene_category == 'outdoor':
            return '🌳'
        else:
            return '📦'
    
    def _get_scene_display_name(self, scene_type: str, primary_label: str) -> str:
        """Get human-readable display name for scene"""
        display_names = {
            'kitchen': 'Kitchen',
            'living_room': 'Living Room',
            'bedroom': 'Bedroom',
            'bathroom': 'Bathroom',
            'office': 'Office',
            'dining_room': 'Dining Room',
            'pool_area': 'Pool Area',
            'patio': 'Patio',
            'balcony': 'Balcony',
            'garden': 'Garden',
            'outdoor_generic': 'Outdoor Area',
            'interior_generic': 'Interior Space'
        }
        
        # Try scene type first
        if scene_type in display_names:
            return display_names[scene_type]
        
        # Fall back to primary label, formatted nicely
        return primary_label.replace('_', ' ').title()

    def delete_media_files(self, request: DeleteMediaFilesRequest) -> DeleteMediaFilesResponse:
        try:
            bucket = storage_client.bucket(settings.GCP.Storage.USER_BUCKET)
            for gs_url in request.gs_urls:
                file_name = StorageManager.parse_gs_url(gs_url).get("file_name", None)
                blob = bucket.blob(file_name)
                if blob.exists():
                    blob.delete()
                else:
                    logger.warning(f"File '{file_name}' doesn't exist. Deletion is a no-op for this file")
                    
            project_manager = ProjectManager(
                user_id=self.user_data.id,
                project_id=request.project_id
            )
            project_manager.media_updated()
            
            return DeleteMediaFilesResponse(message="Files deleted successfully")
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def create_video(self, request: CreateVideoRequest, origin:str) -> CreateVideoResponse:
        try:
            project_id = request.project_id
            project_name = request.name
            version_id = request.version_id or str(uuid.uuid4())
            
            orientation = request.orientation
            included_endtitle = request.included_endtitle
            end_title = request.end_title
            end_subtitle = request.end_subtitle
            included_music = request.included_music # Included or not
            selected_music = request.selected_music # Music name
            included_ai_narration = request.included_ai_narration # Included or not
            selected_ai_narration = request.selected_ai_narration # VO script
            included_captions = request.included_captions
            selected_ai_voice = request.selected_ai_voice # Voice used in VO
            included_occasion_text = request.included_occasion_text
            selected_occasion = request.selected_occasion
            occasion_subtitle = request.occasion_subtitle
            custom_occasion_text = request.custom_occasion_text
            included_agent_presents = request.included_agent_presents
            
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id=self.user_data.id, project_id=project_id)
            user_doc = user_ref.get()
            if not user_doc.exists:
                raise HTTPException(status_code=404, detail="User not found")

            project_doc = project_ref.get()
            if project_doc.exists:
                project = project_doc.to_dict()
            else:
                project_manager = ProjectManager(
                    user_id=user_ref.id,
                    project_id=project_id
                )
                project = project_manager.new_project(
                    project_name=project_name,
                    property_id=request.property_id
                )

            if project_name and project.get("name") != project_name:
                project_ref.set({"name": project_name}, merge=True)
                
            image_repos = StorageManager.get_image_repos_for_project(
                user_id=self.user_data.id,
                project_id=project_id,
            )
            ordered_images = request.ordered_images
            
            if not image_repos and not ordered_images:
                raise ValueError('No images provided to make movie from')
        
            # Construct occasion config if included
            occasion_config = None
            if included_occasion_text:
                if selected_occasion == "custom":
                    occasion_config = {
                        "enabled": True,
                        "type": "custom",
                        "occasion": custom_occasion_text or "",
                        "subtitle": occasion_subtitle or None
                    }
                else:
                    # Map selected_occasion to readable format
                    occasion_map = {
                        "coming-soon": "COMING SOON",
                        "just-listed": "JUST LISTED", 
                        "open-house": "OPEN HOUSE",
                        "pending": "PENDING",
                        "price-reduced": "PRICE REDUCED",
                        "just-sold": "JUST SOLD"
                    }
                    occasion_config = {
                        "enabled": True,
                        "type": selected_occasion,
                        "occasion": occasion_map.get(selected_occasion, selected_occasion.upper()),
                        "subtitle": occasion_subtitle or None
                    }

            movie_maker_request_data = {
                "config": {
                    "end_titles": {"main_title": end_title or None, "sub_title": end_subtitle or None} if included_endtitle else None,
                    "image_orientation": orientation.capitalize(),
                    "music": included_music,
                    "narration": {
                        "captions": included_captions,
                        "script": selected_ai_narration,
                        "voice": selected_ai_voice or self._remix_voiceover()[0],
                        "enabled": included_ai_narration,
                    },
                    "watermark": False,
                    "occasion": occasion_config,
                    "agent_presents": request.included_agent_presents if request.included_agent_presents is not None else True
                },
                "image_repos": image_repos,
                "excluded_images": project.get("excluded_images", []),
                "ordered_images": ordered_images,
                "request_id": {
                    "project": {"id": project_id, "name": project_name},
                    "user": {"id": self.user_data.id},
                    "version": {"id": version_id}
                },
                "template": selected_music or self._remix_music(
                    image_count=len(ordered_images) \
                        if ordered_images \
                            else StorageManager.total_files_in_paths(image_repos),
                    orientation=orientation
                )
            }
            movie_maker_request = MakeMovieRequest.model_validate(movie_maker_request_data)
            
            movie_maker_response = MovieActionsHandler().make_movie(request=movie_maker_request)
            
            # Re-fetch user & project refs as project may have been updated (version stats, etc..)
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id=self.user_data.id, project_id=project_id)

            # Backfill version stats - Just as a sync up in case they went out of sync at some point
            backfill_version_stats(
                project_ref=project_ref
            )
                
            if movie_maker_response.result.state == ActionStatus.State.SUCCESS:
                # Update thumbnail info
                thumbnail_info = gen_thumbnail_info(
                    gs_url=movie_maker_response.story.used_images[0],
                    created_at=movie_maker_response.created
                )
                project_ref.update({PROJECT_THUMBNAIL_INFO_KEY: thumbnail_info})
                
                # Send completion email
                send_video_completion_mail(
                        to=self.user_data.user_info.email,
                        user_name=self.user_data.user_info.first_name,
                        video_name=project_name or project.get("name"),
                        video_link=f"{origin}/gallery/{project_id}"
                    )
                return CreateVideoResponse(message="Video creation task completed", project_id=project_id, version_id=version_id)
            elif movie_maker_response.result.state == ActionStatus.State.FAILURE:
                raise HTTPException(status_code=500, detail=movie_maker_response.result.reason)
            else:
                pass # STILL PENDING? Shouldn't get here
        except Exception as e:
            send_video_failure_mail(
                to=self.user_data.user_info.email,
                user_name=self.user_data.user_info.first_name,
                video_name=project_name or project.get("name"),
                refer_url=f"{origin}/gallery"
            )
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_videos(self) -> FetchVideosResponse:
        try:
            projects = filter_active_projects(
                user_id=self.user_data.id
            )
            videos = []
            for project in projects:
                # Build the filtered dictionary
                project_slim = {
                    "excluded_images": project.get("excluded_images", []),
                    "name": project.get("name", ''),
                    "id": project.get("id", ''),
                    "property_id": project.get("property_id", ''),
                    "music_rank": project.get("music_rank", {}),
                    "versions": []  # We'll fill this in with the filtered versions
                }

                # Process each version to include only the required keys
                versions_slim = []
                for version in project.get("versions", []):
                    if version.get("is_deleted") == True:
                        continue
                    version_slim = {
                        "id": version.get("request", {}).get("request_id", {}).get("version", {}).get("id", ""),
                        "created_at": version.get("time", {}).get("created"),
                        "request": version.get("request", {}),
                        "viewed": version.get("viewed"),
                        "is_favourite": version.get("is_favourite", False),
                        "status": version.get("status"),
                    }
                    status = version.get("status")
                    if status['state'] == 'Success' and "story" in version.keys():
                        movie_path = version.get("story", {}).get("movie_path")
                        if movie_path:
                            movie_path_signed_url = StorageManager.generate_signed_url_from_gs_url(movie_path)
                        else:
                            movie_path_signed_url = None
                        version_slim["story"] = {
                            "movie_path": movie_path,
                            "movie_path_signed_url": movie_path_signed_url,
                            "config": version.get("story", {}).get("config"),
                            "template": version.get("story", {}).get("template")
                        }
                        used_images = version.get("story", {}).get("used_images", [])
                        if len(used_images):
                            version_slim["thumbnail"] = StorageManager.generate_signed_url_from_gs_url(used_images[0])    
                    versions_slim.append(version_slim)
                
                versions_slim.sort(key=lambda v: v["created_at"], reverse=True)
                project_slim["versions"] = versions_slim
                videos.append(project_slim)
                
            videos.sort(key=lambda v: v["versions"][0]["created_at"] if v.get("versions") else dt.datetime.now(dt.timezone.utc), reverse=True)
            return FetchVideosResponse(message="Fetched videos!", videos=videos)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_all_projects_slim(self) -> FetchAllProjectsSlimResponse:
        try:
            projects = filter_active_projects_slim(user_id=self.user_data.id)
            current_time = dt.datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            
            for project in projects:
                # Check if the project has a thumbnail field
                thumbnail = project.get("thumbnail")
                if thumbnail:
                    # Check if signature_expiry exists and is in the past
                    signature_expiry = thumbnail.get("signature_expiry")
                    if signature_expiry and signature_expiry < current_time:
                        # Thumbnail signature has expired; regenerate the signed URL using the same gs_url.
                        thumbnail_info = gen_thumbnail_info(
                            gs_url=thumbnail.get("gs_url"),
                            created_at=thumbnail.get("created_at")
                        )
                        project["thumbnail"] = thumbnail_info
                        # Also update DB
                        _, project_ref, _ = get_session_refs_by_ids(
                            user_id=self.user_data.id,
                            project_id=project.get('id')
                        )
                        project_ref.update({"thumbnail": thumbnail_info})
                            
            return FetchAllProjectsSlimResponse(
                message='Fetched all projects!',
                projects=projects
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    
    def fetch_project(self, project_id:str):
        # Process each version to include only the required keys
        try:
            _, project_ref, _ = get_session_refs_by_ids(
                user_id=self.user_data.id, 
                project_id=project_id
            )
            PROJECT_KEY_FILTERS = [
                'id',
                "name",
                "property_id",
                "versions"
            ]
            project_dict = project_ref.get().to_dict()
            project_doc = project_ref.get()
            if not project_doc.exists:
                logger.error(f"Failed to fetch project for ID '{project_id}'")
                return FetchProjectResponse(message="Failed to fetch project", project={})
            
            project_dict = {key: project_dict[key] for key in PROJECT_KEY_FILTERS if key in project_dict}
            versions_ref = project_ref.collection(settings.GCP.Firestore.VERSIONS_COLLECTION_NAME)
            versions_slim = []
            for version_doc in versions_ref.stream():
                version = version_doc.to_dict()
                if version.get("is_deleted") == True:
                    continue
                version_slim = {
                    "id": version.get("request", {}).get("request_id", {}).get("version", {}).get("id", ""),
                    "created_at": version.get("time", {}).get("created"),
                    "request": version.get("request", {}),
                    "viewed": version.get("viewed"),
                    "is_favourite": version.get("is_favourite", False),
                    "status": version.get("status"),
                }
                status = version.get("status")
                if status['state'] == 'Success' and "story" in version.keys():
                    movie_path = version.get("story", {}).get("movie_path")
                    if movie_path:
                        movie_path_signed_url = StorageManager.generate_signed_url_from_gs_url(movie_path)
                    else:
                        movie_path_signed_url = None
                    used_images = version.get("story", {}).get("used_images", [])
                    used_images_signed = ProjectManager(
                        user_id=self.user_data.id,
                        project_id=project_id
                    ).fetch_signed_urls_for_images(used_images)
                    version_slim["story"] = {
                        "movie_path": movie_path,
                        "movie_path_signed_url": movie_path_signed_url,
                        "config": version.get("story", {}).get("config"),
                        "template": version.get("story", {}).get("template"),
                        "used_images": used_images_signed
                    }
                    if len(used_images):
                        version_slim["thumbnail"] = StorageManager.generate_signed_url_from_gs_url(used_images[0])    
                versions_slim.append(version_slim)
            
            versions_slim.sort(key=lambda v: v["created_at"], reverse=True)
            project_dict['versions'] = versions_slim
            return FetchProjectResponse(message="Fetched videos!", project=project_dict)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    def fetch_project_images(self, project_id: str) -> FetchProjectImagesResponse:
        try:
            if not project_id:
                raise ValueError('Project ID is required to fetch images')
            
            backfill_media_signed_urls_for_project(
                user_id=self.user_data.id,
                project_id=project_id
            ) 
            
            _, project_ref, _ = get_session_refs_by_ids(
                user_id=self.user_data.id, 
                project_id=project_id
            )
            project_dict = project_ref.get().to_dict()
            
            return FetchProjectImagesResponse(
                message="Images fetched!", 
                images=project_dict.get(PROJECT_MEDIA_SIGNED_URLS_KEY, {}).get('media', []),
                signature_expiry=project_dict.get(PROJECT_MEDIA_SIGNED_URLS_KEY, {}).get('signature_expiry', '')
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_project_videos(self, project_id: str) -> FetchProjectVideosResponse:
        try:
            if not project_id:
                raise ValueError('Project ID is required to fetch videos')
            
            backfill_media_signed_urls_for_project(
                user_id=self.user_data.id,
                project_id=project_id
            ) 
            
            _, project_ref, _ = get_session_refs_by_ids(
                user_id=self.user_data.id, 
                project_id=project_id
            )
            project_dict = project_ref.get().to_dict()
            
            return FetchProjectVideosResponse(
                message="Videos fetched!", 
                videos=project_dict.get("video_signed_urls", {}).get('media', []),
                signature_expiry=project_dict.get("video_signed_urls", {}).get('signature_expiry', '')
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_project_media(self, project_id: str) -> FetchProjectMediaResponse:
        """
        Fetch both images and videos for a project with unified response
        This supports the new mixed media upload functionality
        """
        try:
            if not project_id:
                raise ValueError('Project ID is required to fetch media')
            
            # Backfill signed URLs for both images and videos
            backfill_media_signed_urls_for_project(
                user_id=self.user_data.id,
                project_id=project_id
            ) 
            
            _, project_ref, _ = get_session_refs_by_ids(
                user_id=self.user_data.id, 
                project_id=project_id
            )
            project_dict = project_ref.get().to_dict()
            
            # Get images from media_signed_urls (backward compatible)
            images = project_dict.get(PROJECT_MEDIA_SIGNED_URLS_KEY, {}).get('media', [])
            
            # Get videos from video_signed_urls (new)
            videos = project_dict.get("video_signed_urls", {}).get('media', [])
            
            # Use the same signature expiry for both (they're generated together)
            signature_expiry_str = project_dict.get(PROJECT_MEDIA_SIGNED_URLS_KEY, {}).get('signature_expiry', '')
            
            # Convert empty string to None for proper Pydantic validation
            signature_expiry = None
            if signature_expiry_str:
                try:
                    # If it's already a datetime object, use it directly
                    if isinstance(signature_expiry_str, dt.datetime):
                        signature_expiry = signature_expiry_str
                    # If it's a string, try to parse it
                    elif isinstance(signature_expiry_str, str):
                        signature_expiry = dt.datetime.fromisoformat(signature_expiry_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # If parsing fails, leave as None
                    signature_expiry = None
            
            return FetchProjectMediaResponse(
                message="Media fetched!", 
                images=images,
                videos=videos,
                signature_expiry=signature_expiry
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def generate_signed_url(self, request: GenerateSignedUrlRequest) -> GenerateSignedUrlResponse:
        if not request.url:
            raise HTTPException(status_code=422, detail="Invalid URL!")
        try:
            signed_url = StorageManager.generate_signed_url_from_gs_url(gs_url=request.url, method=request.method, content_type=request.content_type)
            return GenerateSignedUrlResponse(message="Video url created!", url=signed_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def update_project(self, request: UpdateProjectRequest) -> UpdateProjectResponse:
        try:
            _, project_ref, _ = get_session_refs_by_ids(user_id=self.user_data.id, project_id=request.project_id)
            if request.name:
                project_ref.update({"name": request.name})
            return DeleteProjectResponse(message="Project updated")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
    def delete_project(self, request: DeleteProjectRequest) -> DeleteProjectResponse:
        try:
            _, project_ref, _ = get_session_refs_by_ids(user_id=self.user_data.id, project_id=request.project_id)
            project_ref.update({"is_deleted": True})
            return DeleteProjectResponse(message="Project deleted")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        
    def delete_video(self, request: DeleteVideoRequest) -> DeleteVideoResponse:
        try:
            _, project_ref, version_ref = get_session_refs_by_ids(user_id=self.user_data.id, project_id=request.project_id, version_id=request.version_id)
            
            version_dict = version_ref.get().to_dict()
            if version_dict.get("is_deleted", False):
                return DeleteVideoResponse(message="Video deleted") # No-op. Already deleted    
            
            version_ref.update({"is_deleted": True})
            
            ProjectStatsManager(
                project_ref=project_ref
            ).handle_video_deleted(
                viewed_video=version_dict.get('viewed', False)
            )
            
            return DeleteVideoResponse(message="Video deleted")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def download_video(self, request: DownloadVideoRequest) -> DownloadVideoResponse:
        if not request.url:
            raise HTTPException(status_code=422, detail="Invalid URL!")
        try:
            signed_url = StorageManager.generate_signed_url_from_gs_url(request.url)
            return DownloadVideoResponse(message="Video url created!", url=signed_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Error downloading video.")

    def render_video(self, request: RenderVideoRequest) -> RenderVideoResponse:
        try:
            payload = verify_jwt(request.token)
            user_id = payload.get("user")
            project_id = payload.get("project")
            version_id = payload.get("version")
            if not (user_id and project_id and version_id):
                raise HTTPException(status_code=422, detail=f"Failed to render video. JWT token '{request.token}' cannot be verified")
            _, _, version_ref = get_session_refs_by_ids(user_id=user_id, project_id=project_id, version_id=version_id)
            version_doc = version_ref.get()
            if not version_doc.exists:
                raise HTTPException(status_code=404, detail="Video doesn't exist anymore!")
            version = version_doc.to_dict()
            movie_path = version.get("story", {}).get("movie_path")
            if not movie_path:
                raise HTTPException(status_code=404, detail="Movie path not found!")
            redirect_url = StorageManager.generate_signed_url_from_gs_url(movie_path)
            version_ref.update({"viewed": True})
            return RenderVideoResponse(redirect_url=redirect_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def toggle_favourite_for_video(self, request: ToggleFavouriteRequest) -> ToggleFavouriteResponse:
        try:
            _, _, version_ref = get_session_refs_by_ids(user_id=self.user_data.id, project_id=request.project_id, version_id=request.version_id)
            version_doc = version_ref.get()
            if not version_doc.exists:
                raise HTTPException(status_code=404, detail="Video not found!")
            video = version_doc.to_dict()
            new_fav = not video.get("is_favourite", False)
            version_ref.update({"is_favourite": new_fav})
            msg = "Video marked as favourite!" if new_fav else "Video removed from favourite"
            return ToggleFavouriteResponse(message=msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_used_images(self, request: FetchUsedImagesRequest) -> FetchUsedImagesResponse:
        try:
            _, _, version_ref = get_session_refs_by_ids(user_id=self.user_data.id, project_id=request.project_id, version_id=request.version_id)
            version_doc = version_ref.get()
            if not version_doc.exists:
                raise HTTPException(status_code=404, detail="Video data not found!")
            version = version_doc.to_dict()
            if version.get("is_deleted"):
                raise HTTPException(status_code=404, detail="Video is not available!")
            used_images_url = []
            for image in version.get("story", {}).get("used_images", []):
                used_images_url.append(StorageManager.generate_signed_url_from_gs_url(image, send_file_name=True))
            return FetchUsedImagesResponse(message="Generated accessible image links", used_images_url=used_images_url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def update_view(self, request: UpdateViewRequest) -> UpdateViewResponse:
        try:
            _, project_ref, version_ref = get_session_refs_by_ids(user_id=self.user_data.id, project_id=request.project_id, version_id=request.version_id)
            version_dict = version_ref.get().to_dict()
            if not version_dict.get('viewed', False):
                version_ref.update({"viewed": True})
                ProjectStatsManager(
                    project_ref=project_ref
                ).handle_video_viewed()
            else:
                logger.warning(f"Version '{version_ref.id}' for Project '{project_ref.id}' already viewed. No-op")
                
            return UpdateViewResponse(message="View status updated!")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def exclude_media_files(self, request: ExcludeMediaFilesRequest) -> ExcludeMediaFilesResponse:
        try:
            _, project_ref, _ = get_session_refs_by_ids(user_id=self.user_data.id, project_id=request.project_id)
            project_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(self.user_data.id).collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).document(request.project_id)
            project_doc = project_ref.get()
            if not project_doc.exists:
                raise HTTPException(status_code=404, detail="Project not found!")
            project_data = project_doc.to_dict()
            excluded:list = project_data.get("excluded_images", [])
            excluded.extend(request.gs_urls)
            project_ref.set({"excluded_images": excluded}, merge=True)
            
            project_manager = ProjectManager(
                user_id=self.user_data.id,
                project_id=request.project_id
            )
            project_manager.media_updated()
            
            return ExcludeMediaFilesResponse(message="Image excluded!")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def generate_shareable_link(self, request: GetShareableLinkRequest) -> GetShareableLinkResponse:
        try:
            token = create_jwt({"user": self.user_data.id, "project": request.project_id, "version": request.version_id})
            original_url = f"{settings.Notification.VIDEO_RENDER_URL_PREFIX}/render-video?token={token}"
            payload = {"originalURL": original_url, "domain": "l.editora.ai"}
            headers = {"Content-Type": "application/json", "Authorization": secret_mgr.secret(settings.Secret.SHORTIO_API_KEY)}
            try:
                resp = httpx.post("https://api.short.io/links/public", 
                                json=payload, 
                                headers=headers,
                                timeout=None)
                if resp.status_code == 200:
                    url = resp.json().get("shortURL")
                else:    
                    error_msg = f"Failed to generate Short URL. Response Code : {resp.status_code}"
                    logger.warning(error_msg)
                    raise Exception(error_msg)
            except:
                url = original_url
                
            return GetShareableLinkResponse(message="Link generated!", link=url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def get_video_data(self, request: GetVideoDataRequest) -> GetVideoDataResponse:
        try:
            payload = verify_jwt(request.token)
            user_id = payload.get("user")
            project_id = payload.get("project")
            version_id = payload.get("version")
            _, project_ref, version_ref = get_session_refs_by_ids(user_id=user_id, project_id=project_id, version_id=version_id)
            
            version_doc = version_ref.get()
            if not version_doc.exists:
                raise HTTPException(status_code=404, detail="Video not found!")
            version = version_doc.to_dict()
            
            project_doc = project_ref.get()
            project_data = project_doc.to_dict() if project_doc.exists else {}
            thumbnail = None
            if version.get("story", {}).get("used_images"):
                thumbnail = StorageManager.generate_signed_url_from_gs_url(version["story"]["used_images"][0])
            video_url = StorageManager.generate_signed_url_from_gs_url(version.get("story", {}).get("movie_path"))
            updated_version = {
                "thumbnail": thumbnail,
                "movie_path": video_url,
                "project_name": project_data.get("name")
            }
            return GetVideoDataResponse(message="Video data fetched!", data=updated_version)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def preselect_images_for_template(self, request: PreselectImagesRequest) -> PreselectImagesResponse:
        if not (request.user_id and request.project_id and request.template):
            raise HTTPException(status_code=400, detail="Missing required fields.")
        try:
            request_data = {
                "user": {"id": request.user_id},
                "project": {"id": request.project_id},
                "template": request.template
            }
            request_model = PreselectForTemplateRequest.model_validate(request_data)
            response_model = MovieActionsHandler().preselect_imagges_for_template(request=request_model)
            
            signed_images = []
            for gs_url in response_model.preselected_images:
                signed_url = StorageManager.generate_signed_url_from_gs_url(gs_url)
                parsed = StorageManager.parse_gs_url(gs_url)
                signed_images.append({
                    "file_name": parsed["file_name"],
                    "signed_url": signed_url,
                    "gs_url": parsed["gs_url"]
                })
            return PreselectImagesResponse(message="Images successfully pre-selected", images=signed_images)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to pre-select images with signed URLs")
        
    def _remix_music(self, image_count: int, orientation: str) -> str:
        last_used_music_rank = self.user_data.remix.last_used_music_rank

        # Load all EDLs
        edls:list[EDL] = EDLManager.load_all_edls(with_title=False)

        # Filter EDLs whose number of clips is less than or equal to image_count
        # AND match the desired orientation (or are hybrid)
        conforming_edls = [
            edl for edl in edls 
            if len(edl.clips) <= image_count and 
            (edl.orientation.lower() == orientation.lower())
        ]

        if not conforming_edls:
            raise ValueError(f"No suitable EDL found for the given image count of {image_count} and orientation {orientation}")

        # Sort conforming EDLs by rank (priority)
        conforming_edls.sort(key=lambda edl: edl.rank)

        # Find the next EDL based on last used music rank
        next_edl = next((edl for edl in conforming_edls if edl.rank > last_used_music_rank), None)

        # If no next EDL is found, loop back to the first one
        if not next_edl:
            next_edl = conforming_edls[0]

        # Update last used music rank in Firestore
        self.user_data.remix.last_used_music_rank = next_edl.rank
        
        user_ref, _, _ = get_session_refs_by_ids(user_id=self.user_data.id)
        user_ref.update({UserData.REMIX_KEY: self.user_data.remix.model_dump()})

        logger.info(f"Selected music '{next_edl.name}' (orientation: {next_edl.orientation}) for user ID {self.user_data.id}")
        
        return next_edl.name
    
    def _remix_voiceover(self) -> str:
        last_used_voice_rank = self.user_data.remix.last_used_voice_rank

        # Load all voiceovers
        voiceover_model: ElevenLabs = VoiceoverManager().get_voice_mappings()
        if not voiceover_model:
            raise FileNotFoundError(f"Voice mappings document doesn't exist in Firestore")

        # Sort voice mappings by rank (priority)
        voiceover_model.voice_mappings.sort(key=lambda voice: voice.rank)

        # Find the next voice mapping based on last used voice rank
        next_voice = next((voice for voice in voiceover_model.voice_mappings if voice.rank > last_used_voice_rank), None)

        # If no next voice is found, loop back to the first voice
        if not next_voice:
            next_voice = voiceover_model.voice_mappings[0]

        # Update last used voice rank
        self.user_data.remix.last_used_voice_rank = next_voice.rank
        
        user_ref, _, _ = get_session_refs_by_ids(user_id=self.user_data.id)
        user_ref.update({UserData.REMIX_KEY: self.user_data.remix.model_dump()})
        
        logger.info(f"Selected voiceover '{next_voice.editora_name}'  for user ID {self.user_data.id}")

        return next_voice.id, next_voice.editora_name
    
    async def get_project_videos(self, project_id: str, 
                               include_scene_clips: bool = False,
                               include_classifications: bool = False) -> ProjectVideosResponse:
        """
        Get project videos with lazy loading options
        """
        try:
            _, project_ref, _ = get_session_refs_by_ids(
                user_id=self.user_data.id,
                project_id=project_id
            )
            
            project_doc = project_ref.get()
            if not project_doc.exists:
                raise HTTPException(status_code=404, detail="Project not found")
            
            project_data = project_doc.to_dict()
            media_data = project_data.get('media', {})
            
            # Get basic video info (always loaded)
            videos = media_data.get('videos', [])
            scene_clips_data = media_data.get('scene_clips', [])
            
            # Lazy loading: Scene clips
            scene_clips = None
            if include_scene_clips and scene_clips_data:
                scene_clips = scene_clips_data.copy()
                
                # Lazy load signed URLs
                scene_clips = await LazyVideoLoader.load_signed_urls(scene_clips)
                
                # Lazy load classifications if requested
                if include_classifications:
                    from classification.image_classification_manager import ImageClassificationManager
                    classification_manager = ImageClassificationManager()
                    scene_clips = await LazyVideoLoader.load_classifications(
                        scene_clips, classification_manager
                    )
            
            # Count selected scene clips
            selected_count = sum(
                1 for clip in scene_clips_data 
                if clip.get('usage', {}).get('is_selected', True)
            )
            
            return ProjectVideosResponse(
                message="Project videos fetched successfully",
                videos=[UploadedVideo(**video) for video in videos],
                scene_clips=scene_clips,
                total_scene_clips=len(scene_clips_data),
                selected_scene_clips=selected_count
            )
            
        except Exception as e:
            logger.exception(f"[VIDEO_ACTIONS] Failed to get project videos: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
def main():
    import argparse
    from rich import print
    
    parser = argparse.ArgumentParser(description='EDL Manager')
    
    parser.add_argument('-u', '--user_id', type=str, required=True, help='User ID')
    parser.add_argument('-p', '--project_id', type=str, required=True, help='Project ID')
    
    args = parser.parse_args()
    
    user_ref, _, _ = get_session_refs_by_ids(user_id=args.user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        raise HTTPException(status_code=400, detail="Authentication Failed! User doesn't exist!")

    user_data = UserData.model_validate(user_doc.to_dict())
    
    video_actions = VideoActionsHandler(
        user_data=user_data
    )
    
    fetch_project_response = video_actions.fetch_project_images(project_id=args.project_id)
    print(fetch_project_response)
        
if __name__ == '__main__':
    main()


