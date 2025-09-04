"""
Configuration settings for property scrapers.
"""

class ScraperConfig:
    """Configuration settings for property scrapers."""
    
    # Minimum number of images required to return early from primary extraction strategy
    MIN_IMAGES_FOR_EARLY_RETURN = 5
    
    # Maximum number of images to extract per property
    MAX_IMAGES_PER_PROPERTY = 36
    
    # Timeout settings for web requests
    REQUEST_TIMEOUT = 30
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds 