import argparse
import random
import concurrent.futures
from typing import Dict, List, Optional, Callable
from tempfile import TemporaryDirectory
from pathlib import Path
import os
import uuid
import json
from rich import print

from gcp.db import db_client
from config.config import settings
from logger import logger
from utils.session_utils import get_session_refs_by_ids
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath
from classification.classification_model import (
    RealEstate, HeroSelectionEnum, ImageSequence, 
    ImageBuckets
)
from ai.image_analyzer import ImageAnalyzer

class ImageClassificationManager():
    def __init__(self):
        self.model = self.load_real_estate_model_local()
        
    def save_real_estate_model(self, model: RealEstate):
        try:
            document_id = settings.Classification.REAL_ESTATE_DOC_ID
            doc_ref = db_client.collection(
                settings.GCP.Firestore.CLASSIFICATION_COLLECTION_NAME
            ).document(document_id=document_id)
            doc = doc_ref.get()
            if doc.exists:
                logger.warning(f"Classification model {document_id} already exists. Overwriting record in DB")
                
            doc_ref.set(model.model_dump())
            self.model = model
            
            logger.success(f"Saved classification model in Firestore. Name : {document_id}")
                    
        except Exception as e:
            logger.exception(f"Failed to save classification model in Firestore DB: {e}")
            raise e
        
    def load_real_estate_model(self) -> RealEstate:
        try:
            document_id = settings.Classification.REAL_ESTATE_DOC_ID
            doc_ref = db_client.collection(
                settings.GCP.Firestore.CLASSIFICATION_COLLECTION_NAME
            ).document(document_id=document_id)
            doc = doc_ref.get()
            if not doc.exists:
                logger.warning(f"Classification model {document_id} does not exist")
                return None
                            
            logger.info(f"Loaded classification model '{document_id}'")
            return RealEstate(**doc.to_dict())
                        
        except Exception as e:
            logger.exception(f"Failed to load classification model from Firestore DB: {e}")
            raise e
        
    def load_real_estate_model_local(self) -> RealEstate:
        logger.info("Loaded Real Estate classification model LOCALLY")
        
        return RealEstate(
            categories=['Exterior', 'Living', 'Dining', 'Kitchen', 'Bedroom', 'Bathroom', 'Pool', 'Backyard', 'Neighborhood', 'Plan', 'Other'],
            hero_image=settings.Classification.ENABLE_HERO_SHOT,
            hero_selection=HeroSelectionEnum.FILENAME,
            boundary_priorities_small={
                '1': ["Exterior", "Backyard", "Living"],  # 1st clip
                '-1': ["Pool", "Backyard", "Neighborhood", "Exterior"],  # Last clip
            },
            boundary_priorities_large={
                '1': ["Exterior", "Backyard", "Living"],  # 1st clip
                '-2': ["Pool", "Backyard", "Neighborhood", "Living", "Kitchen"],  # Second last clip
                '-1': ["Neighborhood", "Backyard", "Exterior", "Pool"],  # Last clip
            },
            interior_order=["Living", "Dining", "Kitchen", "Bedroom"]
        )
                        
    def label_image(self, image_file_path: str) -> ImageBuckets.ImageInfo:
        image_analyzer = ImageAnalyzer()
        
        response = image_analyzer.analyze_image_from_uri(
            image_file_path=image_file_path, 
            num_features=settings.Classification.MAX_LABELS
        )
        
        image_labels = image_analyzer.labels(response=response)
                    
        return ImageBuckets.ImageInfo(
            category='',
            uri=image_file_path,
            labels=[
                ImageBuckets.ImageInfo.Label(
                    score=image_label['score'],
                    description=image_label['description']
                ) 
                for image_label in image_labels
            ],
            score = max(len(image_labels), 1)
        )
        
    def label_images(self, image_file_paths: List[str]) -> List[ImageBuckets.ImageInfo]:
        images_data = []
            
        # Use ThreadPoolExecutor for I/O-bound tasks (e.g., API calls)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self.label_image, img_file_path): img_file_path
                for img_file_path in image_file_paths
            }

            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                img = futures[future]
                try:
                    result = future.result()
                    images_data.append(result)
                except Exception as exc:
                    logger.error(f"Image {img} generated an exception: {exc}")
                    
        return images_data
    
    def categorize_images(self, labeled_images: List[ImageBuckets.ImageInfo]) -> List[ImageBuckets.ImageInfo]:
        image_analyzer = ImageAnalyzer()
        
        # Use ThreadPoolExecutor for I/O-bound tasks
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    image_analyzer.categorize_image,
                    categories=self.model.categories, 
                    image_labels=[label.model_dump() for label in image.labels]
                ): image
                for image in labeled_images
            }

            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                image = futures[future]
                try:
                    result = future.result()
                    image.category = result
                except Exception as exc:
                    logger.error(f"Image {image} generated an exception: {exc}")
                    
        return labeled_images
    
    def rank(self, images: List[ImageBuckets.ImageInfo], categories: List[str]) -> ImageBuckets:
        """
        Populate the ImageBuckets model with a ranking of images by category and score.
        """
        buckets = ImageBuckets()
        # Initialize each category with an empty list of ImageBuckets.buckets
        buckets.buckets = {cat: [] for cat in categories}

        def normalize_category(cat):
            return cat if cat in categories else 'Other'

        # Build up the ranking lists
        for item in images:
            item.category = normalize_category(item.category)
            # Use ImageBuckets.Item instead of a tuple
            buckets.buckets[item.category].append(
                ImageBuckets.Item(uri=item.uri, score=item.score)
            )

        # Sort each category's list by descending score
        for cat in categories:
            buckets.buckets[cat].sort(key=lambda r: r.score, reverse=True)

        return buckets
    
    def run_classification_for_project(self, user_id:str, project_id:str):
        _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
        
        if not project_ref.get().exists:
            logger.error(f"Unable to fetch project for user '{user_id}' and project '{project_id}'")
            return
            
        image_repos = StorageManager.get_image_repos_for_project(
            user_id=user_id,
            project_id=project_id
        )
        
        images_path_l2c_mapping = {}
        images_path_c2l_mapping = {}
        loaded_local_paths = []
        
        with TemporaryDirectory() as images_folder:
            for repo in image_repos:
                cloud_path = CloudPath.from_path(repo)
                subfolder_uuid = str(uuid.uuid4())
                images_subfolder = os.path.join(images_folder, subfolder_uuid)
                os.makedirs(images_subfolder, exist_ok=True)

                sub_l2c, sub_c2l = StorageManager.load_blobs(
                    cloud_path=cloud_path, 
                    dest_dir=images_subfolder,
                    excluded_files=project_ref.get().to_dict().get('excluded_images', None)
                )
                images_path_l2c_mapping.update(sub_l2c)
                images_path_c2l_mapping.update(sub_c2l)

            loaded_local_paths = [
                str(file) for file in Path(images_folder).rglob("*") if file.is_file()
            ]
            
            image_buckets_local = self.run_classification_for_files(
                image_file_paths=loaded_local_paths
            )
            
            if not image_buckets_local:
                return
            
            image_buckets_cloud = ImageBuckets(buckets={})
            for category, item_list in image_buckets_local.buckets.items():
                cloud_items = []
                for item in item_list:
                    cloud_uri = images_path_l2c_mapping.get(item.uri, item.uri)
                    cloud_item = ImageBuckets.Item(uri=cloud_uri, score=item.score)
                    cloud_items.append(cloud_item)
                image_buckets_cloud.buckets[category] = cloud_items

            IMAGE_CLASSIFICATION_KEY = settings.Classification.IMAGE_CLASSIFICATION_KEY
            project_dict = project_ref.get().to_dict()
            if project_dict.get(IMAGE_CLASSIFICATION_KEY, None):
                logger.info(f"Images are already classified for project '{project_id}'. Overwriting")
            else:
                logger.debug(f"New image classification run for project '{project_id}'")
            project_ref.set({IMAGE_CLASSIFICATION_KEY: image_buckets_cloud.model_dump()}, merge=True)
            
    def run_classification_for_files(self, image_file_paths: List[str]) -> ImageBuckets:
        # Step 1 - Label images
        if not image_file_paths:
            logger.error("Failed to run classification. No images to categorize and rank")
            return None
        
        labeled_images = self.label_images(image_file_paths=image_file_paths)
            
        # Step 2 - Categorize images
        categorized_images = self.categorize_images(labeled_images=labeled_images)

        # Step 3 - Rank images
        buckets = self.rank(
            images=categorized_images, 
            categories=self.model.categories
        )
            
        logger.debug("Image Classification Buckets:")
        logger.debug(json.dumps(buckets.model_dump(), indent=2))
        
        return buckets
    
    def gen_sequence(
        self,
        num_clips: int,
        buckets: ImageBuckets,
    ) -> ImageSequence:
        """
        Generate an ordered sequence of images.
        """

        categories = self.model.categories
        interior_order = self.model.interior_order
        boundary_priorities = (
            self.model.boundary_priorities_small
            if num_clips < settings.Classification.MIN_CLIPS_IN_LARGE_MOVIE
            else self.model.boundary_priorities_large
        )

        # Validate categories
        for cat in buckets.buckets:
            if cat not in categories:
                raise ValueError(f"Invalid category '{cat}' found in image_info. Valid categories are: {categories}")

        # Sort images within each category by descending score
        for cat in buckets.buckets:
            buckets.buckets[cat].sort(key=lambda ri: ri.score, reverse=True)

        # Count total available images
        total_images = sum(len(imgs) for imgs in buckets.buckets.values())
        if self.model.hero_image:
            if total_images == 0:
                return ImageSequence(sequence=[])
            num_clips = min(num_clips, total_images)  # Adjust num_clips if not enough images
        else:
            if total_images < num_clips:
                num_clips = total_images  # Adjust num_clips if not enough images

        if num_clips == 0:
            # No images available
            return ImageSequence(sequence=[])

        # Define fallback categories (not in interior_order)
        fallback_categories = [cat for cat in categories if cat not in interior_order]

        # Make a mutable copy of interior_order to allow cycling
        current_interior_order = interior_order.copy()

        # Set to track used categories for boundary clip fallbacks
        fallback_used_categories = set()

        def weighted_random_choice(items: List[ImageBuckets.Item]) -> ImageBuckets.Item:
            """
            Select an item using weighted randomness based on score.
            
            Returns ImageBuckets.Item or None if empty.
            """
            if not items:
                return None
            scores = [ri.score for ri in items]
            chosen = random.choices(items, weights=scores, k=1)[0]
            return chosen

        def pick_image_from_category(cat: str) -> ImageBuckets.ImageInfo:
            """
            Pick an image from a specific category using weighted randomness.
            
            Returns ImageBuckets.ImageInfo or None
            """
            if cat not in buckets.buckets or not buckets.buckets[cat]:
                return None
            chosen = weighted_random_choice(buckets.buckets[cat])
            if not chosen:
                return None
            # Remove the chosen image to prevent repetition
            buckets.buckets[cat] = [ri for ri in buckets.buckets[cat] if ri.uri != chosen.uri]
            return ImageBuckets.ImageInfo(
                category=cat,
                uri=chosen.uri,
                labels=[],
                score=chosen.score
            )

        def hero_selector_exterior(buckets:ImageBuckets)->tuple[str, str, int]:
            all_images = []
            for cat, bucket_items in buckets.buckets.items():
                for ri in bucket_items:
                    all_images.append((cat, ri.uri, ri.score))
                        
            all_images_sorted = sorted(all_images, key=lambda x: x[1].split('/')[-1])
            zero_cat, zero_uri, zero_score = all_images_sorted[0]
            if zero_cat == 'Exterior':
                return zero_cat, zero_uri, zero_score
            else: #Default to hero shot
                hero_image = pick_image_from_category(cat='Exterior')
                return ('Exterior', hero_image.uri, hero_image.score) if hero_image \
                else (zero_cat, zero_uri, zero_score)
            
        def get_boundary_key(clip_idx: int, total_clips: int) -> Optional[str]:
            """
            Determine the boundary key for a given clip index.
            """
            pos_key = clip_idx
            neg_key = -(total_clips - clip_idx + 1)
            if pos_key in boundary_priorities:
                return pos_key
            if neg_key in boundary_priorities:
                return neg_key
            return None

        def pick_image_for_boundary_clip(clip_idx: int, priority_list: List[str]) -> ImageSequence.ImageInfo:
            """
            Pick an image for a boundary clip based on priority_list.
            """
            # Try each category in the priority list in order
            for cat in priority_list:
                image_info = pick_image_from_category(cat)
                if image_info and image_info.uri:
                    rationale = f"Selected boundary prioritized clip image (clip {clip_idx})."
                    return ImageSequence.ImageInfo(
                        uri=image_info.uri,
                        category=image_info.category,
                        rationale=rationale,
                        score=image_info.score
                    )

            # Fallback to any unused category
            not_used_candidates = []
            for c, bucket_items in buckets.buckets.items():
                if c not in fallback_used_categories and bucket_items:
                    for ri in bucket_items:
                        not_used_candidates.append((c, ri.uri, ri.score))

            if not_used_candidates:
                chosen_cat, chosen_uri, chosen_score = random.choices(
                    not_used_candidates, 
                    weights=[s for _, _, s in not_used_candidates], 
                    k=1
                )[0]
                # Remove the chosen image
                buckets.buckets[chosen_cat] = [ri for ri in buckets.buckets[chosen_cat] if ri.uri != chosen_uri]
                fallback_used_categories.add(chosen_cat)
                rationale = f"Selected boundary clip image (fallback unused category, clip {clip_idx})."
                return ImageSequence.ImageInfo(
                    uri=chosen_uri,
                    category=chosen_cat,
                    rationale=rationale,
                    score=chosen_score
                )

            # Final fallback to any available category
            all_candidates = []
            for cat, bucket_items in buckets.buckets.items():
                for ri in bucket_items:
                    all_candidates.append((cat, ri.uri, ri.score))
            if all_candidates:
                chosen_cat, chosen_uri, chosen_score = random.choices(
                    all_candidates, 
                    weights=[s for _, _, s in all_candidates], 
                    k=1
                )[0]
                # Remove the chosen image
                buckets.buckets[chosen_cat] = [ri for ri in buckets.buckets[chosen_cat] if ri.uri != chosen_uri]
                rationale = f"Selected boundary clip image (final fallback any category, clip {clip_idx})"
                return ImageSequence.ImageInfo(
                    uri=chosen_uri,
                    category=chosen_cat,
                    rationale=rationale,
                    score=chosen_score
                )

            # No images left
            return None

        def pick_image_for_interior_clip(clip_idx: int) -> ImageSequence.ImageInfo:
            """
            Pick an image for an interior (non-boundary) clip based on interior_order.
            """
            # Cycle through the current_interior_order
            for _ in range(len(current_interior_order)):
                cat = current_interior_order[0]
                if buckets.buckets.get(cat):
                    image_info = pick_image_from_category(cat)
                    if image_info and image_info.uri:
                        rationale = f"Selected interior clip image (clip {clip_idx}) from '{cat}'"
                        current_interior_order.append(current_interior_order.pop(0))
                        return ImageSequence.ImageInfo(
                            uri=image_info.uri,
                            category=image_info.category,
                            rationale=rationale,
                            score=image_info.score
                        )
                # Move the category to the end if no images are available
                current_interior_order.append(current_interior_order.pop(0))

            # If no images available in interior_order, fallback to other categories
            fallback_candidates = []
            for cat in fallback_categories:
                if buckets.buckets.get(cat):
                    for ri in buckets.buckets[cat]:
                        fallback_candidates.append((cat, ri.uri, ri.score))
            if fallback_candidates:
                chosen_cat, chosen_uri, chosen_score = random.choices(
                    fallback_candidates, 
                    weights=[s for _, _, s in fallback_candidates], 
                    k=1
                )[0]
                # Remove the chosen image
                buckets.buckets[chosen_cat] = [ri for ri in buckets.buckets[chosen_cat] if ri.uri != chosen_uri]
                rationale = f"Selected interior clip image (clip {clip_idx}) from fallback category '{chosen_cat}'"
                return ImageSequence.ImageInfo(
                    uri=chosen_uri,
                    category=chosen_cat,
                    rationale=rationale,
                    score=chosen_score
                )

            # Final fallback to any available category
            all_candidates = []
            for cat, bucket_items in buckets.buckets.items():
                for ri in bucket_items:
                    all_candidates.append((cat, ri.uri, ri.score))
            if all_candidates:
                chosen_cat, chosen_uri, chosen_score = random.choices(
                    all_candidates, 
                    weights=[s for _, _, s in all_candidates], 
                    k=1
                )[0]
                buckets.buckets[chosen_cat] = [ri for ri in buckets.buckets[chosen_cat] if ri.uri != chosen_uri]
                rationale = f"Selected interior clip image (clip {clip_idx}) from any available category '{chosen_cat}'"
                return ImageSequence.ImageInfo(
                    uri=chosen_uri,
                    category=chosen_cat,
                    rationale=rationale,
                    score=chosen_score
                )

            # No images left
            return None

        image_sequence = ImageSequence(sequence=[])

        # Handle Hero Image if enabled
        if self.model.hero_image:
            # Collect all images across all categories
            all_images = []
            for cat, bucket_items in buckets.buckets.items():
                for ri in bucket_items:
                    all_images.append((cat, ri.uri, ri.score))
            
            if all_images:
                if self.model.hero_selection == HeroSelectionEnum.FILENAME:
                    # Sort by filename
                    all_images_sorted = sorted(all_images, key=lambda x: x[1].split('/')[-1])
                    hero_cat, hero_uri, hero_score = all_images_sorted[0]
                elif self.model.hero_selection == HeroSelectionEnum.HIGH_SCORE:
                    # Highest score
                    hero_cat, hero_uri, hero_score = max(all_images, key=lambda x: x[2])
                elif self.model.hero_selection == HeroSelectionEnum.CUSTOM:
                    hero_cat, hero_uri, hero_score = hero_selector_exterior(buckets)
                else:
                    raise ValueError("Invalid hero_selection criteria.")
                
                # Remove the hero image from buckets
                buckets.buckets[hero_cat] = [ri for ri in buckets.buckets[hero_cat] if ri.uri != hero_uri]
                # Add hero image to the sequence
                hero_rationale = "Selected hero image"
                image_sequence.sequence.append(ImageSequence.ImageInfo(
                    uri=hero_uri,
                    category=hero_cat,
                    rationale=hero_rationale,
                    score=hero_score
                ))
                clip_start = 2
            else:
                return ImageSequence(sequence=[])
        else:
            clip_start = 1

        # Generate remaining clips
        for i in range(clip_start, num_clips + 1):
            boundary_key = get_boundary_key(i, num_clips)
            if boundary_key:
                priority_list = boundary_priorities[boundary_key]
                image_info = pick_image_for_boundary_clip(i, priority_list)
            else:
                image_info = pick_image_for_interior_clip(i)
            
            if not image_info or image_info.uri is None:
                # No image found
                break

            image_sequence.sequence.append(image_info)

        return image_sequence
        
    def run_selection(self, buckets:ImageBuckets, num_clips: int, verbose=False) -> List[str]:
        
        total_images = sum(len(images) for images in buckets.buckets.values())
        if total_images < num_clips:
            logger.error(f'Not enough images to run selection. Required: {num_clips}, Available: {total_images}')
            return None

        image_sequence: ImageSequence = None
        try:
            if verbose:
                logger.info(f'Selecting {num_clips} images')
            image_sequence = self.gen_sequence(num_clips=num_clips, buckets=buckets.model_copy(deep=True))
        except Exception as e:
            logger.exception(f'Unable to select images to make movie. Reason: {e}')
        
        if image_sequence:
            if verbose:
                logger.debug(f'\n{image_sequence.model_dump_json(indent=2)}')
            return [image_info.uri for image_info in image_sequence.sequence]
        else:
            logger.error('Failed to classify and pick images. Fallback: pick in lexicographic order')
            return sorted(image_file_paths)[:num_clips]


def main():
    parser = argparse.ArgumentParser(description="Script to save model or run selector")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-s", "--save_model", action="store_true", help="Save model")
    group.add_argument("-l", "--load_model", action="store_true", help="Load model")

    args = parser.parse_args()

    if args.save_model:
        print("Saving model...")
        real_estate_model = RealEstate(
            categories=['Exterior', 'Living', 'Dining', 'Kitchen', 'Bedroom', 'Bathroom', 'Backyard', 'Neighborhood', 'Plan', 'Other'],
            hero_image=True,
            hero_selection=HeroSelectionEnum.FILENAME,
            boundary_priorities_small={
                '1': ["Exterior", "Living"],  # 1st clip
                '-1': ["Neighborhood", "Backyard", "Exterior", "Plan"],  # Last clip
            },
            boundary_priorities_large={
                '1': ["Exterior", "Living"],  # 1st clip
                '-2': ["Backyard", "Neighborhood", "Living", "Kitchen"],  # Second last clip
                '-1': ["Neighborhood", "Backyard", "Exterior", "Plan"],  # Last clip
            },
            interior_order=["Living", "Dining", "Kitchen", "Bedroom", "Bathroom"]
        )
        ImageClassificationManager().save_real_estate_model(model=real_estate_model)
        
    if args.load_model:
        print('Loading model...')
        print(ImageClassificationManager().model)


def main2():
    parser = argparse.ArgumentParser(description="Run Classification")
    parser.add_argument("-u", "--user_id", type=str, required=True, help="User ID")
    parser.add_argument("-p", "--project_id", type=str, required=True, help="Project ID or 'all'")
    args = parser.parse_args()
    
    classification_mgr = ImageClassificationManager()
    classification_mgr.run_classification_for_project(
        user_id=args.user_id,
        project_id=args.project_id
    )
    
if __name__ == '__main__':
    main2()
