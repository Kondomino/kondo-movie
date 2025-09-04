from fastapi import HTTPException
from google.cloud.firestore_v1.base_query import FieldFilter, Or

from logger import logger
from config.config import settings
from account.account_actions_model import *
from account.account_model import *
from gcp.db import db_client
from notification.email_service import send_welcome_pilot_mail
from account.stytch_manager import stytch_client
from notification.email_service import send_portal_is_ready_mail

class AccountActionsHandler:
    def __init__(self, user_data:UserData=None):
        self.user_data = user_data

    def fetch_user_details(self, user_id: str) -> FetchUserDetailsResponse:
        try:
            if user_id != self.user_data.id:
                raise HTTPException(status_code=404, detail=f"ID Mismatch: Requested '{user_id}', Authenticated '{self.user_data.id}'")

            # Get user details with tenant information
            user_details = self.user_data.model_dump()
            
            # Add tenant information to the response
            from utils.tenant_utils import get_tenant_info
            tenant_info = get_tenant_info(self.user_data)
            if tenant_info:
                user_details['tenant'] = {
                    'id': tenant_info.get('id'),
                    'name': tenant_info.get('name'),
                    'url': tenant_info.get('url')
                }
            else:
                # If no tenant info found, use default tenant
                from config.config import settings
                tenants_dict = settings.Tenants.TENANTS.model_dump()
                default_tenant = tenants_dict.get(settings.Tenants.DEFAULT_TENANT_ID)
                if default_tenant:
                    user_details['tenant'] = {
                        'id': default_tenant.get('id'),
                        'name': default_tenant.get('name'),
                        'url': default_tenant.get('url')
                }

            return FetchUserDetailsResponse(message="User details fetched", details=user_details)
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Error occurred while fetching user details")

    def signup(self, request: SignupRequest) -> SignupResponse:
        try:
            user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(request.id)
            user_doc = user_ref.get()

            if user_doc.exists:
                user_data = UserData.model_validate(user_doc.to_dict())
                logger.warning(f"User w/ ID '{user_data.id}' already exists! Updating DB record")
            else:
                user_data = UserData(
                    id=request.id
                )

            user_data.user_info = UserInfo(email=request.email)
            
            # Only set defaults for NEW users
            if not user_doc.exists:
                # Ensure welcome email tracking starts as False for new users
                user_data.welcome_email_sent = False
                user_data.portal_ready_email_sent = False
                # Set portal_ready to False for new users (pilot onboarding)
                user_data.portal_ready = False
                
            if request.first_name:
                user_data.user_info.first_name = request.first_name
            if request.last_name:
                user_data.user_info.last_name = request.last_name
            if request.agreed_to_terms:
                user_data.agreed_to_terms = request.agreed_to_terms
            if request.tenant_id:
                user_data.tenant_id = request.tenant_id
                
            user_ref.set(user_data.model_dump())

            # Send welcome email for new users (only once)
            if not user_doc.exists and not user_data.welcome_email_sent:
                try:
                    first_name = user_data.user_info.first_name if user_data.user_info and user_data.user_info.first_name else "there"
                    send_welcome_pilot_mail(user_data.user_info.email, first_name)
                    
                    # Mark email as sent
                    user_data.welcome_email_sent = True
                    user_ref.set(user_data.model_dump())
                    
                    logger.info(f"Welcome email sent to {user_data.user_info.email}")
                except Exception as e:
                    logger.error(f"Failed to send welcome email to {user_data.user_info.email}: {e}")
                    # Don't fail signup if email fails

            return SignupResponse(message="User signup successful!")
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Error occurred during signup")

    def update_user_details(self, user_id: str, request: UpdateUserDetailsRequest) -> UpdateUserDetailsResponse:
        try:
            user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                raise HTTPException(status_code=404, detail=f"User with ID '{user_id}' not found")

            update_data = {}

            if request.first_name:
                update_data["user_info.first_name"] = request.first_name
            if request.last_name:
                update_data["user_info.last_name"] = request.last_name
            if request.device_token:
                update_data["device_token"] = request.device_token
            if request.agreed_to_terms and request.agreed_to_terms == True: # Only allow updates to true
                update_data["agreed_to_terms"] = True
                
            user_ref.update(update_data)
            return UpdateUserDetailsResponse(message=f"User details for ID '{user_id}' updated successfully!")
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=f"Error occurred while updating user details for ID '{user_id}'")

    def update_user_tenant(self, user_id: str, request: UpdateUserTenantRequest) -> UpdateUserTenantResponse:
        try:
            logger.info(f"Starting tenant update for user_id: {user_id}, new_tenant_id: {request.tenant_id}")
            
            user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(user_id)
            logger.info(f"Created user reference for collection: {settings.GCP.Firestore.USERS_COLLECTION_NAME}, document: {user_id}")
            
            user_doc = user_ref.get()
            logger.info(f"Retrieved user document, exists: {user_doc.exists}")

            if not user_doc.exists:
                logger.warning(f"User with ID '{user_id}' not found in database")
                raise HTTPException(status_code=404, detail=f"User with ID '{user_id}' not found")

            # Update the tenant_id
            update_data = {"tenant_id": request.tenant_id}
            logger.info(f"Updating user document with data: {update_data}")
            user_ref.update(update_data)
            logger.info(f"Successfully updated user document")
            
            # Fetch the updated user data
            logger.info(f"Fetching updated user document")
            updated_doc = user_ref.get()
            logger.info(f"Retrieved updated document, exists: {updated_doc.exists}")
            
            if not updated_doc.exists:
                logger.error(f"Updated document does not exist after update for user_id: {user_id}")
                raise HTTPException(status_code=500, detail=f"Failed to retrieve updated user data for ID '{user_id}'")
            
            user_dict = updated_doc.to_dict()
            logger.info(f"Retrieved user data: {user_dict}")
            
            user_data = UserData.model_validate(user_dict)
            logger.info(f"Successfully validated user data model")
            
            # Convert to dict and add tenant information if available
            user_details = user_data.model_dump()
            logger.info(f"Converted user data to dict")
            
            from utils.tenant_utils import get_tenant_info
            # Safely get tenant_id with fallback
            current_tenant_id = getattr(user_data, 'tenant_id', None)
            logger.info(f"Getting tenant info for user with tenant_id: {current_tenant_id}")
            tenant_info = get_tenant_info(user_data)
            
            if tenant_info:
                logger.info(f"Found tenant info: {tenant_info}")
                user_details['tenant'] = {
                    'id': tenant_info.get('id'),
                    'name': tenant_info.get('name'),
                    'url': tenant_info.get('url')
                }
            else:
                logger.warning(f"No tenant info found for tenant_id: {current_tenant_id}")

            logger.info(f"Tenant update completed successfully for user_id: {user_id}")
            return UpdateUserTenantResponse(
                message=f"User tenant updated successfully for ID '{user_id}'",
                user_data=user_details
            )
        except Exception as e:
            logger.exception(f"Error occurred while updating user tenant for ID '{user_id}': {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error occurred while updating user tenant for ID '{user_id}'")

    def check_user(self, request: CheckUserRequest) -> CheckUserResponse:
        
        query={
            "email": request.email
        }
        try:
            stytch_user_info = stytch_client.search(email=request.email)
            
            if stytch_user_info:
                return CheckUserResponse(found=True, user=stytch_user_info)
            else:
                return CheckUserResponse(found=False)
            
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=f"Stytch failed to find user for email '{request.email}'")

    def delete_user(self, user_id: str) -> DeleteUserResponse:
        try:
            user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                raise HTTPException(status_code=404, detail=f"User ID '{user_id}' not found")

            user_ref.update({"is_deleted": True})

            return DeleteUserResponse(message=f"User with ID '{user_id}' deleted!")
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail=f"Error occurred while deleting user '{user_id}'")

    def get_tenants(self) -> dict:
        tenants_dict = settings.Tenants.TENANTS.model_dump()
        tenants_list = [
            {
                'id': t['id'],
                'name': t['name'],
                'url': t['url']
            } for t in tenants_dict.values()
        ]
        return {'tenants': tenants_list}

    def search_users(self, query: str) -> dict:
        """
        Search users in Firestore by email substring, return id, email, tenant_id
        Improved version with better handling of larger datasets
        """
        try:
            users_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME)
            
            # Increase limit significantly to handle larger user bases
            # Firestore does not support substring search natively, so fetch a larger set and filter in Python
            # For production, consider using a proper search index like Algolia or Elasticsearch
            users = users_ref.limit(1000).stream()  # Increased from 50 to 1000
            
            results = []
            for user_doc in users:
                user = user_doc.to_dict()
                
                # Skip deleted users
                if user.get('is_deleted', False):
                    continue
                    
                email = user.get('user_info', {}).get('email', '')
                
                # Case-insensitive substring search
                if query.lower() in email.lower():
                    results.append({
                        'id': user.get('id'),
                        'email': email,
                        'tenant_id': user.get('tenant_id', None),
                        'portal_ready': user.get('portal_ready', False),
                        'first_name': user.get('user_info', {}).get('first_name', ''),
                        'last_name': user.get('user_info', {}).get('last_name', '')
                    })
            
            logger.info(f"Search for '{query}' returned {len(results)} users from {len(list(users_ref.limit(1000).stream()))} total users checked")
            
            return {'users': results}
            
        except Exception as e:
            logger.exception(f"Error in search_users for query '{query}': {e}")
            return {'users': [], 'error': str(e)}

    def list_all_users(self, limit: int = 100) -> dict:
        """
        List all users (for admin purposes) with pagination support
        """
        try:
            users_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME)
            users = users_ref.limit(limit).stream()
            
            results = []
            for user_doc in users:
                user = user_doc.to_dict()
                
                # Skip deleted users
                if user.get('is_deleted', False):
                    continue
                    
                results.append({
                    'id': user.get('id'),
                    'email': user.get('user_info', {}).get('email', ''),
                    'tenant_id': user.get('tenant_id', None),
                    'portal_ready': user.get('portal_ready', False),
                    'first_name': user.get('user_info', {}).get('first_name', ''),
                    'last_name': user.get('user_info', {}).get('last_name', ''),
                    'welcome_email_sent': user.get('welcome_email_sent', False),
                    'portal_ready_email_sent': user.get('portal_ready_email_sent', False)
                })
            
            logger.info(f"List all users returned {len(results)} users (limit: {limit})")
            
            return {'users': results, 'total_returned': len(results)}
            
        except Exception as e:
            logger.exception(f"Error in list_all_users: {e}")
            return {'users': [], 'error': str(e)}

    def is_admin(self, email: str) -> dict:
        from utils.admin_utils import is_admin
        return {"is_admin": is_admin(email)}
    
    def activate_agent(self, request: ActivateAgentRequest) -> ActivateAgentResponse:
        """
        Activate or deactivate an agent by toggling their portal_ready status.
        """
        try:
            user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(request.user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                raise HTTPException(status_code=404, detail=f"User with ID '{request.user_id}' not found")

            user_data = UserData.model_validate(user_doc.to_dict())
            
            # Update portal_ready status
            user_data.portal_ready = request.portal_ready
            user_ref.set(user_data.model_dump())

            action = "activated" if request.portal_ready else "deactivated"
            logger.info(f"Agent {request.user_id} {action} successfully")

            return ActivateAgentResponse(
                message=f"Agent {action} successfully",
                user_id=request.user_id,
                portal_ready=request.portal_ready
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Error occurred while updating agent status")

    def list_unactivated_agents(self, request: ListUnactivatedAgentsRequest) -> ListUnactivatedAgentsResponse:
        """
        List all users with portal_ready = False (unactivated agents).
        """
        try:
            users_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME)

            filters = Or([
                FieldFilter("portal_ready", "==", False),
                FieldFilter("portal_ready_email_sent", "==", False),
            ])
            
            # Query for users with portal_ready = False
            query = users_ref.where(filter=filters)
            
            docs = query.stream()

            agents = []
            for doc in docs:
                user_data = UserData.model_validate(doc.to_dict())
                if not user_data.is_deleted:  # Exclude deleted users
                    agent_info = {
                        "id": user_data.id,
                        "email": user_data.user_info.email if user_data.user_info else "No email",
                        "first_name": user_data.user_info.first_name if user_data.user_info and user_data.user_info.first_name else "",
                        "last_name": user_data.user_info.last_name if user_data.user_info and user_data.user_info.last_name else "",
                        "tenant_id": user_data.tenant_id,
                        "portal_ready": user_data.portal_ready,
                        "welcome_email_sent": user_data.welcome_email_sent
                    }
                    agents.append(agent_info)

            return ListUnactivatedAgentsResponse(
                message=f"Found {len(agents)} unactivated agents",
                agents=agents
            )
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Error occurred while fetching unactivated agents")

    def send_portal_ready_email(self, request: SendPortalReadyEmailRequest) -> SendPortalReadyEmailResponse:
        try:
            user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(request.user_id)
            user_doc = user_ref.get()

            if not user_doc.exists:
                raise HTTPException(status_code=404, detail=f"User with ID '{request.user_id}' not found")

            user_data = UserData.model_validate(user_doc.to_dict())

            if not user_data.portal_ready:
                raise HTTPException(status_code=400, detail="Portal is not active for this user")

            user_name = user_data.user_info.first_name if user_data.user_info and user_data.user_info.first_name else "there"
            to_email = user_data.user_info.email if user_data.user_info else None

            if not to_email:
                raise HTTPException(status_code=400, detail="User email not found")

            send_portal_is_ready_mail(to_email, user_name, request.portal_url)

            # Update flags: mark portal_ready_email_sent true and welcome_email_sent true
            user_ref.update({
                "portal_ready_email_sent": True,
                "welcome_email_sent": True
            })

            return SendPortalReadyEmailResponse(message="Portal is ready email sent successfully")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(e)
            raise HTTPException(status_code=500, detail="Failed to send portal is ready email")