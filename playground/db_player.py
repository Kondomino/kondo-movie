from rich import print
import datetime as dt

from logger import logger
from gcp.storage import StorageManager
from utils.db_utils import filter_active_projects, filter_active_projects_slim

def fetch_projects_slim(projects:list):
    videos = []
    for project in projects:
        # Build the filtered dictionary
        project_slim = {
            "excluded_images": project.get("excluded_images", []),
            "name": project.get("name", ''),
            "id": project.get("id", ''),
            "music_rank": project.get("music_rank", {}),
            "versions": []  # We'll fill this in with the filtered versions
        }
        project_slim["versions"] = []

        # Process each version to include only the required keys
        for version in project.get("versions", []):
            version_slim = {
                "id": version.get("request", {}).get("request_id", {}).get("version", {}).get("id", ""),
                "created_at": version.get("time", {}).get("created"),
                "request": version.get("request", {}),
                "story": {
                    "movie_path": version.get("story", {}).get("movie_path"),
                    "config": version.get("story", {}).get("config"),
                    "template": version.get("story", {}).get("template")
                },
                "viewed": version.get("viewed"),
                "status": version.get("status"),
            }
            used_images = version.get("story", {}).get("used_images", [])
            if len(used_images):
                version_slim["thumbnail"] = StorageManager.generate_signed_url_from_gs_url(used_images[0])
            
            project_slim["versions"].append(version_slim)
        videos.append(project_slim)
        
    videos.sort(key=lambda v: v["versions"][0]["created_at"] if v.get("versions") else dt.datetime.now(dt.timezone.utc), reverse=True)
    return videos
            
def main():
    user_id = 'user-test-91821539-9f1f-40d2-b93c-a0ce69126ae3'
    
    import time
    start_time = time.time()
    projects = filter_active_projects_slim(user_id=user_id)
    end_time = time.time()
    execution_time = end_time - start_time
    
    print(projects[2])
    logger.debug(f"Execution time: {execution_time:.2f} seconds")

if __name__ == '__main__':
    main()
