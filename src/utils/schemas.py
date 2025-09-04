from pydantic import BaseModel
import json
import argparse
import sys

from logger import logger
from config.config import settings
from utils.str_utils import camel_to_snake
from gcp.db import db_client

from movie_maker.movie_actions_model import *
from movie_maker.movie_model import *
from property.property_actions_model import *
from account.account_actions_model import *
from video.video_actions_model import *

class SchemaManager():
    def __init__(self, model_cls:BaseModel):
        self.model_cls = model_cls
        
    def schema(self)->str:
        return self.model_cls.model_json_schema()
    
    def save_schema(self):
        schema_id = camel_to_snake(self.model_cls.__name__)
        schema_ref = db_client.collection(
            settings.GCP.Firestore.SCHEMA_COLLECTION_NAME).document(
                document_id=schema_id)
        if schema_ref.get().exists:
            logger.warning(f'Schema {schema_id} already exists. Overwriting it')
        schema_ref.set(self.schema())
        
    def load_schema(self)->dict:
        schema_id = camel_to_snake(self.model_cls.__name__)
        schema_ref = db_client.collection(
            settings.GCP.Firestore.SCHEMA_COLLECTION_NAME).document(
                document_id=schema_id)
        schema = schema_ref.get()
        if not schema_ref.get().exists:
            logger.error(f'Schema {schema_id} does not exist')
            return None
        schema_json = json.dumps(schema.to_dict(), indent=2) 
        logger.info(schema_json)
        return schema_json
    
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Schema Manager')
    
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument('-s', '--save', action='store_true', help='Save schema doc in firestore')
    action_group.add_argument('-l', '--load', action='store_true', help='Load schema from firestore')

    parser.add_argument('-m', '--model', required=True, type=str, help='Pydantic model')
    args = parser.parse_args()
    
    model_cls = getattr(sys.modules[__name__], args.model)
    schema_mgr = SchemaManager(model_cls=model_cls)
    
    if args.save:
        schema_mgr.save_schema()
    elif args.load:
        schema_mgr.load_schema()
    else:
        # Shouldn't get here
        pass
    
if __name__ == '__main__':
    main()
    
    

    