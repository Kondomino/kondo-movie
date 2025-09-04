import argparse
from rich import print
import json

from config.config import settings
from gcp.db import db_client

def whoami(uid:str):
    user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(document_id=uid)
    user = user_ref.get()
    if user.exists:
        user_data = user.to_dict()
        print(json.dumps(user_data, indent=2))
    else:
        print(f"User doesn't exit for id: {uid}")
    
def main():
    # Parse Args
    parser = argparse.ArgumentParser(description='Editora video maker')
    parser.add_argument('-u', '--uid', required=True, type=str, help='User ID')
    args = parser.parse_args()
    
    whoami(args.uid)
    
if __name__ == '__main__':
    main()