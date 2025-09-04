import sys
import os
import logging
from dotenv import load_dotenv

from config.config import settings
from loguru import logger
from google.cloud import logging as g_logging
from google.cloud.logging.handlers import CloudLoggingHandler

load_dotenv()

class SingletonLogger():
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup_logger()
        return cls._instance

    def setup_logger(self):
        # Configure Loguru
        logger.remove()  # Remove default handler
        
        log_level = os.getenv('LOG_LEVEL')
        deployment = os.getenv('DEPLOYMENT')
        if deployment == 'CLOUD':
            g_client = g_logging.Client(project=settings.GCP.PROJECT_ID)
            g_client.setup_logging(log_level=logging.WARNING)
            g_logging_handler = CloudLoggingHandler(client=g_client)
            logger.add(sink=g_logging_handler, level=log_level if log_level else 'INFO')
        else:
            logger.add(sink=sys.stdout, level=log_level if log_level else 'INFO')
        

    def get_logger(self):
        return logger

logger = SingletonLogger().get_logger()