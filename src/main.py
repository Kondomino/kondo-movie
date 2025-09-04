from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Query, status, Path, Depends, Form, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from logger import logger
from config.config import settings
from account.authentication import authenticate

from account.account_actions import AccountActionsHandler
from account.account_actions_model import *
from property.property_actions_model import *
from property.property_actions import PropertyActionsHandler
from movie_maker.movie_actions import MovieActionsHandler
from movie_maker.movie_actions_model import *
from video.video_actions import VideoActionsHandler
from video.video_actions_model import *
from video.video_processor import VideoProcessor
from config.email_config_model import GetEmailConfigsResponse, UpdateEmailConfigsRequest, UpdateEmailConfigsResponse
from config.email_config_manager import email_config_manager
from utils.admin_utils import is_admin

# Initialize FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.Authentication.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.exception(exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)}
    )
    
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    logger.exception(exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.exception(exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)}
    )
    
@app.get("/")
async def read_root():
    return {"message": "Welcome to the MovieMaker Service API"}

v1_router = APIRouter(prefix="/api/v1")

@v1_router.get("/")
async def read_root():
    return {"message": "User actions service API"}

##############
# ACCOUNT APIs
##############

@v1_router.get('/user-details/{user_id}', response_model=FetchUserDetailsResponse)
async def fetch_user_details(
    user_id:str = Path(..., description="ID of user to fetch details for"), 
    response: Response = Response(),
    user_data: UserData = Depends(authenticate)
    ):
    return AccountActionsHandler(
            user_data=user_data
        ).fetch_user_details(user_id=user_id)
    
@v1_router.post('/signup', response_model=SignupResponse)
async def signup(
    request: SignupRequest,
    response: Response,
):
     return AccountActionsHandler().signup(request=request)
    
@v1_router.patch('/update-details/{user_id}', response_model=UpdateUserDetailsResponse)
async def update_user_details(
    request: UpdateUserDetailsRequest,
    response: Response,
    user_id:str = Path(..., description="ID of user to fetch details for"), 
    user_data: UserData = Depends(authenticate)
):
    return AccountActionsHandler(
            user_data=user_data,
        ).update_user_details(user_id=user_id, request=request)
        
@v1_router.post('/check-user', response_model=CheckUserResponse)
async def check_user(
    request: CheckUserRequest,
    response: Response,
):
    return AccountActionsHandler().check_user(request=request)
    
@v1_router.get('/delete-user/{user_id}', response_model=DeleteUserResponse)
async def fetch_user_details(
    user_id:str = Path(...,description="ID of user to delete"), 
    response: Response = Response(status_code=status.HTTP_200_OK),
    user_data: UserData = Depends(authenticate)):
    return AccountActionsHandler(
            user_data=user_data
        ).delete_user(user_id=user_id)

@v1_router.get('/tenants')
async def get_tenants():
    return AccountActionsHandler().get_tenants()

@v1_router.get('/search-users')
async def search_users(query: str):
    return AccountActionsHandler().search_users(query)

@v1_router.get('/list-all-users')
async def list_all_users(limit: int = 100):
    return AccountActionsHandler().list_all_users(limit)

@v1_router.patch('/update-user-tenant/{user_id}', response_model=UpdateUserTenantResponse)
async def update_user_tenant(
    request: UpdateUserTenantRequest,
    user_id: str = Path(..., description="ID of user to update tenant for"),
    user_data: UserData = Depends(authenticate)
):
    return AccountActionsHandler(user_data=user_data).update_user_tenant(user_id=user_id, request=request)

@v1_router.get('/is-admin')
async def is_admin(email: str):
    return AccountActionsHandler().is_admin(email)

@v1_router.get('/unactivated-agents', response_model=ListUnactivatedAgentsResponse)
async def list_unactivated_agents(
    user_data: UserData = Depends(authenticate)
):
    return AccountActionsHandler(user_data=user_data).list_unactivated_agents(
        request=ListUnactivatedAgentsRequest()
    )

@v1_router.patch('/activate-agent', response_model=ActivateAgentResponse)
async def activate_agent(
    request: ActivateAgentRequest,
    user_data: UserData = Depends(authenticate)
):
    return AccountActionsHandler(user_data=user_data).activate_agent(request=request)

@v1_router.post('/send-portal-ready-email', response_model=SendPortalReadyEmailResponse)
async def send_portal_ready_email(
    request: SendPortalReadyEmailRequest,
    user_data: UserData = Depends(authenticate)
):
    return AccountActionsHandler(user_data=user_data).send_portal_ready_email(request=request)

@v1_router.get('/email-configs', response_model=GetEmailConfigsResponse)
async def get_email_configs(user_data: UserData = Depends(authenticate)):
    """Get current email configuration settings (admin only)"""
    if not user_data.user_info or not user_data.user_info.email:
        raise HTTPException(status_code=403, detail="User email not found")
    
    if not is_admin(user_data.user_info.email):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        configs = email_config_manager.get_configs()
        return GetEmailConfigsResponse(message="Email configs retrieved successfully", configs=configs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@v1_router.put('/email-configs', response_model=UpdateEmailConfigsResponse)
async def update_email_configs(
    request: UpdateEmailConfigsRequest, 
    user_data: UserData = Depends(authenticate)
):
    """Update email configuration settings (admin only)"""
    if not user_data.user_info or not user_data.user_info.email:
        raise HTTPException(status_code=403, detail="User email not found")
    
    if not is_admin(user_data.user_info.email):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        updated_configs = email_config_manager.update_configs(request.configs)
        return UpdateEmailConfigsResponse(message="Email configs updated successfully", configs=updated_configs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

################
# PROPERTY APIs
################

@v1_router.post("/fetch-property-details", response_model=FetchPropertyDetailsResponse)
def fetch_property_details(
    request:FetchPropertyDetailsRequest,
    user_data: UserData = Depends(authenticate)
):
    from logger import logger
    logger.info(f"[API] /fetch-property-details called by user_id: {user_data.id}")
    logger.info(f"[API] Request data: property_id='{request.property_id}', property_address='{request.property_address}', address_input_type='{request.address_input_type}'")
    logger.info(f"[API] User tenant_id: {getattr(user_data, 'tenant_id', 'NOT_SET')}")
    
    return PropertyActionsHandler().fetch_property_details(user_data.id, request)

@v1_router.post("/properties/purge-cache/{property_id}", response_model=PurgePropertyCacheResponse)
def purge_property_cache(
    property_id: str = Path(..., description="ID of property to purge cache for"),
    user_data: UserData = Depends(authenticate)
):
    request = PurgePropertyCacheRequest(property_id=property_id)
    return PropertyActionsHandler().purge_property_cache(user_data.id, request)

@app.post('/fetch_property', response_model=FetchPropertyResponse)
async def fetch_property(
    request: FetchPropertyRequest,
    response: Response,
):
    from logger import logger
    logger.info(f"[API] /fetch_property called")
    logger.info(f"[API] Request data: request_id='{request.request_id}', property_address='{request.property_address}', address_input_type='{request.address_input_type}'")
    
    action_response = PropertyActionsHandler().fetch_property(request=request)
    if action_response.result.state != ActionStatus.State.SUCCESS:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return action_response
    
##############
# VIDEO APIs
##############

@v1_router.get("/fetch-edls", response_model=FetchEDLSResponse)
def fetch_edls(user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_edls()

@v1_router.get("/fetch-voices", response_model=FetchVoicesResponse)
def fetch_voices(user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_voices()

@v1_router.post("/new-media-uploaded", response_model=NewMediaUploadedResponse)
async def upload_images(
    request: NewMediaUploadedRequest,
    user_data: UserData = Depends(authenticate)
):
    return await VideoActionsHandler(user_data).new_media_uploaded(request)

@v1_router.get("/fetch-video-scenes-classification", response_model=FetchVideoScenesResponse)
def fetch_video_scenes_classification(
    video_uri: str,
    project_id: str,
    user_data: UserData = Depends(authenticate)
):
    """
    Fetch scene classifications for a specific video.
    Called when user opens VideoPlayerModal from create-by-upload page.
    """
    return VideoActionsHandler(user_data).fetch_video_scenes_classification(
        video_uri=video_uri,
        project_id=project_id
    )

@v1_router.post("/delete-media-files", response_model=DeleteMediaFilesResponse)
def delete_media_files(request: DeleteMediaFilesRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).delete_media_files(request)

@v1_router.post("/create-video", response_model=CreateVideoResponse)
def create_video(request: CreateVideoRequest, fastapi_request: Request, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).create_video(
        request=request,
        origin=fastapi_request.headers.get('origin')
    )

@v1_router.get("/fetch-video-list", response_model=FetchVideosResponse)
def fetch_videos(user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_videos()

@v1_router.get("/fetch-all-projects-slim", response_model=FetchAllProjectsSlimResponse)
def fetch_all_projects_slim(user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_all_projects_slim()

@v1_router.get("/fetch-project/{project_id}", response_model=FetchProjectResponse)
def fetch_project(project_id: str = Path(...,description="ID of project to fetch"), user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_project(project_id=project_id)

@v1_router.post("/fetch-project-images", response_model=FetchProjectImagesResponse)
def fetch_project_images(request: FetchProjectImagesRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_project_images(request.project_id)

@v1_router.post("/fetch-project-videos", response_model=FetchProjectVideosResponse)
def fetch_project_videos(request: FetchProjectVideosRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_project_videos(request.project_id)

@v1_router.post("/fetch-project-media", response_model=FetchProjectMediaResponse)
def fetch_project_media(request: FetchProjectMediaRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_project_media(request.project_id)

@v1_router.post("/generate-signed-url", response_model=GenerateSignedUrlResponse)
def generate_signed_url(request: GenerateSignedUrlRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).generate_signed_url(request)

@v1_router.post("/update-project", response_model=UpdateProjectResponse)
def delete_video(request: UpdateProjectRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).update_project(request)

@v1_router.post("/delete-project", response_model=DeleteProjectResponse)
def delete_video(request: DeleteProjectRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).delete_project(request)

@v1_router.post("/delete-video", response_model=DeleteVideoResponse)
def delete_video(request: DeleteVideoRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).delete_video(request)

@v1_router.post("/download-video", response_model=DownloadVideoResponse)
def download_video(request: DownloadVideoRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).download_video(request)

@v1_router.get("/render-video", response_model=RenderVideoResponse)
def render_video(token: str = Query(...)):
    request = RenderVideoRequest(token=token)
    response = VideoActionsHandler(None).render_video(request)
    return RedirectResponse(url=response.redirect_url)

@v1_router.post("/favourite", response_model=ToggleFavouriteResponse)
def toggle_favourite_for_video(request: ToggleFavouriteRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).toggle_favourite_for_video(request)

@v1_router.post("/fetch-used-images", response_model=FetchUsedImagesResponse)
def fetch_used_images(request: FetchUsedImagesRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).fetch_used_images(request)

@v1_router.post("/update-view", response_model=UpdateViewResponse)
def update_view(request: UpdateViewRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).update_view(request)

@v1_router.post("/exclude-media-files", response_model=ExcludeMediaFilesResponse)
def exclude_image(request: ExcludeMediaFilesRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).exclude_media_files(request)

@v1_router.post("/get-shareable-link", response_model=GetShareableLinkResponse)
def generate_shareable_link(request: GetShareableLinkRequest, fastapi_request: Request, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).generate_shareable_link(request=request)

@v1_router.post("/get-video-data", response_model=GetVideoDataResponse)
def get_video_data(request: GetVideoDataRequest):
    return VideoActionsHandler(None).get_video_data(request)

@v1_router.post("/preselect-images", response_model=PreselectImagesResponse)
def preselect_images_for_template(request: PreselectImagesRequest, user_data: UserData = Depends(authenticate)):
    return VideoActionsHandler(user_data).preselect_images_for_template(request)

# NEW: Video upload and processing endpoints
@v1_router.post("/upload-video", response_model=UploadVideoResponse)
async def upload_video(
    video_file: UploadFile,
    project_id: str = Form(...),
    scene_detection_threshold: float = Form(0.3),
    max_scenes: int = Form(20),
    user_data: UserData = Depends(authenticate)
):
    """
    Upload video and process it into scene clips with lazy computation
    """
    try:
        # Validate video file
        if not video_file.content_type.startswith('video/'):
            raise HTTPException(status_code=400, detail="File must be a video")
        
        # Check file size (max 500MB)
        max_size = 500 * 1024 * 1024  # 500MB
        if video_file.size and video_file.size > max_size:
            raise HTTPException(status_code=400, detail="Video file too large (max 500MB)")
        
        # Save video temporarily for processing
        import tempfile
        import aiofiles
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
            temp_path = temp_file.name
        
        # Save uploaded file
        async with aiofiles.open(temp_path, 'wb') as f:
            content = await video_file.read()
            await f.write(content)
        
        # Process video with lazy computation
        video_processor = VideoProcessor()
        result = await video_processor.process_uploaded_video(
            video_file_path=temp_path,
            project_id=project_id,
            user_id=user_data.id,
            scene_detection_threshold=scene_detection_threshold,
            max_scenes=max_scenes
        )
        
        # Clean up temp file
        import os
        os.unlink(temp_path)
        
        return UploadVideoResponse(
            message="Video processed successfully",
            video_id=result['video_id'],
            status=result['status'],
            estimated_processing_time=30  # Mock estimate
        )
        
    except Exception as e:
        logger.exception(f"[API] Video upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@v1_router.get("/project-videos/{project_id}", response_model=ProjectVideosResponse)
async def get_project_videos(
    project_id: str = Path(..., description="Project ID to fetch videos for"),
    include_scene_clips: bool = Query(False, description="Lazy load scene clips"),
    include_classifications: bool = Query(False, description="Lazy load classifications"),
    user_data: UserData = Depends(authenticate)
):
    """
    Get project videos with lazy loading options
    """
    try:
        return await VideoActionsHandler(user_data).get_project_videos(
            project_id=project_id,
            include_scene_clips=include_scene_clips,
            include_classifications=include_classifications
        )
    except Exception as e:
        logger.exception(f"[API] Failed to fetch project videos: {e}")
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(v1_router)

##################
# MOVIE MAKER APIs
##################

# Endpoint for making a movie
@app.post('/make_movie', response_model=MakeMovieResponse)
async def make_movie(
    request: MakeMovieRequest,
    response: Response,
):
    action_response = MovieActionsHandler().make_movie(request=request)
    if action_response.result.state != ActionStatus.State.SUCCESS:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return action_response

# Endpoint for making a movie
@app.post('/preselect_images', response_model=PreselectForTemplateResponse)
async def make_movie(
    request: PreselectForTemplateRequest,
    response: Response,
):
    action_response = MovieActionsHandler().preselect_imagges_for_template(request=request)
    if action_response.result.state != ActionStatus.State.SUCCESS:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return action_response