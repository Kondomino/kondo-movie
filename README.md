# editora-v2-movie-maker
Video engine for Editora

## Docker - Local installation steps
1) docker build -t editora-v2-movie-maker .

2) docker compose up
OR
2) 
docker compose up -d (Detached mode: Run containers in the background)
docker compose down

# Shell access
3) docker exec -it editora-v2-movie-maker bin/bash

## Architecture Overview

### System Components

```
editora-v2-movie-maker/
├── src/
│   ├── account/           # User account management
│   ├── ai/               # AI services integration
│   ├── classification/   # Image classification and analysis
│   ├── movie_maker/      # Core video generation engine
│   ├── notification/     # Email and alert systems
│   ├── property/         # Property data management
│   ├── video/           # Video processing and storage
│   ├── gcp/             # Google Cloud Platform integrations
│   └── utils/           # Shared utilities
└── library/
    ├── fonts/           # Typography assets
    ├── templates/       # Video templates
    └── notification/    # Email templates
```

### Core Components

1. **Video Generation Engine** (`movie_maker/`)
   - `MovieMaker`: Main orchestrator for video creation
   - `VideoGenerator`: Handles video clip generation and composition
   - `AudioHandler`: Manages background music and voiceover
   - `CaptionsManager`: Handles subtitle generation and overlay
   - `Effects`: Implements video transitions and effects
   - `EDLManager`: Manages Edit Decision Lists (templates)

2. **AI Services** (`ai/`, `classification/`)
   - Image classification and analysis
   - AI-powered narration generation
   - Smart image selection and ordering
   - Template recommendations

3. **Property Management** (`property/`)
   - Property data models
   - MLS integration
   - Property image management
   - Property metadata handling

4. **Media Processing**
   - Image processing and optimization
   - Video encoding and compression
   - Audio processing and mixing
   - Watermark application

### Technical Architecture

1. **Frontend Integration**
   - RESTful API endpoints
   - FastAPI backend framework
   - JSON-based request/response models
   - Swagger/OpenAPI documentation

2. **Backend Services**
   - Containerized microservices (Docker)
   - Asynchronous task processing
   - Cloud storage integration
   - Database management (Firestore)

3. **Storage Layer**
   - Google Cloud Storage for media files
   - Firestore for metadata and configurations
   - Local caching system
   - Temporary file management

4. **Processing Pipeline**
   ```
   Input → Classification → Template Selection → Media Processing → Video Generation → Delivery
   ```

### Key Features

1. **Template System**
   - Customizable video templates
   - Edit Decision List (EDL) based composition
   - Dynamic text overlay support
   - Transition effects library

2. **Media Management**
   - Automatic image selection
   - Smart cropping and resizing
   - Format conversion
   - Quality optimization

3. **Audio System**
   - Background music integration
   - AI voiceover generation
   - Audio mixing and balancing
   - Caption synchronization

4. **Output Customization**
   - Multiple resolution support (Portrait/Landscape)
   - Configurable video quality
   - Custom watermarking
   - End title customization

### Infrastructure

1. **Cloud Services**
   - Google Cloud Platform
   - Cloud Storage
   - Firestore Database
   - Cloud Functions (optional)

2. **Development Environment**
   - Docker containerization
   - Python 3.x runtime
   - FastAPI framework
   - MoviePy for video processing

3. **Monitoring & Logging**
   - Structured logging system
   - Performance monitoring
   - Error tracking
   - Usage analytics

### Security Features

1. **Authentication & Authorization**
   - Token-based authentication
   - Role-based access control
   - API key management
   - Secure credential storage

2. **Data Protection**
   - Encrypted storage
   - Secure file handling
   - Temporary file cleanup
   - Access logging

### Scalability Considerations

1. **Performance Optimization**
   - Parallel processing
   - Resource pooling
   - Caching strategies
   - Load balancing

2. **Resource Management**
   - Dynamic resource allocation
   - Memory optimization
   - Storage cleanup
   - Connection pooling

## FastAPI Endpoints Reference

### Root
- **GET /**
  - Description: Welcome message
  - Response: `{ "message": "Welcome to the MovieMaker Service API" }`

### API v1 (prefix: `/api/v1`)

#### General
- **GET /**
  - Description: API root
  - Response: `{ "message": "User actions service API" }`

#### Account APIs
- **GET `/user-details/{user_id}`**
  - Path: `user_id` (str)
  - Response Model: `FetchUserDetailsResponse`
- **POST `/signup`**
  - Body: `SignupRequest`
  - Response Model: `SignupResponse`
- **PATCH `/update-details/{user_id}`**
  - Path: `user_id` (str)
  - Body: `UpdateUserDetailsRequest`
  - Response Model: `UpdateUserDetailsResponse`
- **POST `/check-user`**
  - Body: `CheckUserRequest`
  - Response Model: `CheckUserResponse`
- **GET `/delete-user/{user_id}`**
  - Path: `user_id` (str)
  - Response Model: `DeleteUserResponse`

#### Property APIs
- **POST `/fetch-property-details`**
  - Body: `FetchPropertyDetailsRequest`
  - Response Model: `FetchPropertyDetailsResponse`
- **POST `/fetch_property`**
  - Body: `FetchPropertyRequest`
  - Response Model: `FetchPropertyResponse`

#### Video Management APIs
- **GET `/fetch-edls`**
  - Response Model: `FetchEDLSResponse`
- **GET `/fetch-voices`**
  - Response Model: `FetchVoicesResponse`
- **POST `/new-media-uploaded`**
  - Body: `NewMediaUploadedRequest`
  - Response Model: `NewMediaUploadedResponse`
- **POST `/delete-media-files`**
  - Body: `DeleteMediaFilesRequest`
  - Response Model: `DeleteMediaFilesResponse`
- **POST `/create-video`**
  - Body: `CreateVideoRequest`
  - Response Model: `CreateVideoResponse`
- **GET `/fetch-video-list`**
  - Response Model: `FetchVideosResponse`
- **GET `/fetch-all-projects-slim`**
  - Response Model: `FetchAllProjectsSlimResponse`
- **GET `/fetch-project/{project_id}`**
  - Path: `project_id` (str)
  - Response Model: `FetchProjectResponse`
- **POST `/fetch-project-images`**
  - Body: `FetchProjectImagesRequest`
  - Response Model: `FetchProjectImagesResponse`
- **POST `/generate-signed-url`**
  - Body: `GenerateSignedUrlRequest`
  - Response Model: `GenerateSignedUrlResponse`
- **POST `/update-project`**
  - Body: `UpdateProjectRequest`
  - Response Model: `UpdateProjectResponse`
- **POST `/delete-project`**
  - Body: `DeleteProjectRequest`
  - Response Model: `DeleteProjectResponse`
- **POST `/delete-video`**
  - Body: `DeleteVideoRequest`
  - Response Model: `DeleteVideoResponse`
- **POST `/download-video`**
  - Body: `DownloadVideoRequest`
  - Response Model: `DownloadVideoResponse`
- **GET `/render-video?token={token}`**
  - Query: `token` (str)
  - Response: Redirect to URL from `RenderVideoResponse`
- **POST `/favourite`**
  - Body: `ToggleFavouriteRequest`
  - Response Model: `ToggleFavouriteResponse`
- **POST `/fetch-used-images`**
  - Body: `FetchUsedImagesRequest`
  - Response Model: `FetchUsedImagesResponse`
- **POST `/update-view`**
  - Body: `UpdateViewRequest`
  - Response Model: `UpdateViewResponse`
- **POST `/exclude-media-files`**
  - Body: `ExcludeMediaFilesRequest`
  - Response Model: `ExcludeMediaFilesResponse`
- **POST `/get-shareable-link`**
  - Body: `GetShareableLinkRequest`
  - Response Model: `GetShareableLinkResponse`
- **POST `/get-video-data`**
  - Body: `GetVideoDataRequest`
  - Response Model: `GetVideoDataResponse`
- **POST `/preselect-images`**
  - Body: `PreselectImagesRequest`
  - Response Model: `PreselectImagesResponse`

### Movie Maker Endpoints (no prefix)
- **POST `/make_movie`**
  - Body: `MakeMovieRequest`
  - Response Model: `MakeMovieResponse`
- **POST `/preselect_images`**
  - Body: `PreselectForTemplateRequest`
  - Response Model: `PreselectForTemplateResponse`
