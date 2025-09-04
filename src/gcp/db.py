import os
import firebase_admin
from google.cloud import firestore
from google.oauth2 import service_account

from logger import logger
from config.config import settings

DB_SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'

class DBManager():
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup_db()
        return cls._instance

    def setup_db(self):
        try:
            firebase_admin.initialize_app()
            
            cred = service_account.Credentials.from_service_account_file(DB_SERVICE_ACCOUNT_KEY_FILE_PATH) \
                if os.path.exists(DB_SERVICE_ACCOUNT_KEY_FILE_PATH) \
                else None
            
            db = settings.GCP.Firestore.DB
            self.db_client = firestore.Client(project=settings.GCP.PROJECT_ID, database=db, credentials=cred)
        except Exception as e:
            logger.exception(f"Failed to connect to Firestore DB for project {settings.GCP.PROJECT_ID}")
            raise e

    def get_db_client(self):
        return self.db_client
    
    def delete_collection(self, collection_path: str):
        """Delete all documents in a collection"""
        try:
            collection_ref = self.db_client.collection(collection_path)
            docs = collection_ref.list_documents()
            
            deleted_count = 0
            for doc in docs:
                # Delete subcollections first
                subcollections = doc.collections()
                for subcollection in subcollections:
                    self.delete_collection(f"{collection_path}/{doc.id}/{subcollection.id}")
                
                # Delete the document
                doc.delete()
                deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} documents from collection: {collection_path}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_path}: {str(e)}")
            raise e

    def delete_document(self, document_path: str):
        """Delete a specific document"""
        try:
            doc_ref = self.db_client.document(document_path)
            doc = doc_ref.get()
            
            if not doc.exists:
                logger.warning(f"Document {document_path} does not exist")
                return 0
            
            # Delete subcollections first
            subcollections = doc_ref.collections()
            for subcollection in subcollections:
                self.delete_collection(f"{document_path}/{subcollection.id}")
            
            # Delete the document itself
            doc_ref.delete()
            logger.info(f"Deleted document: {document_path}")
            return 1
            
        except Exception as e:
            logger.error(f"Failed to delete document {document_path}: {str(e)}")
            raise e


# Create a Firestore client
db_client = DBManager().get_db_client()