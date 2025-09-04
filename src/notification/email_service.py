import argparse
from rich import print

import mailchimp_transactional

from logger import logger
from config.config import settings
from gcp.secret import secret_mgr
from config.email_config_manager import email_config_manager
from notification.email_templates import video_completion_template, video_failure_template, welcome_pilot_template, portal_is_ready_template

MAILCHIMP_API_KEY = secret_mgr.secret(settings.Secret.MAILCHIMP_API_KEY)

def send_mail(to: str, subject: str, html: str) -> dict:
    mailchimp = mailchimp_transactional.Client(MAILCHIMP_API_KEY)
    
    message = {
        "from_email": settings.Notification.Email.EDITORA_INFO,
        "from_name": "Editora",
        "to": [
            {
                "email": to,
                "type": "to",
            }
        ],
        "subject": subject,
        "html": html,
    }
    try:
        response = mailchimp.messages.send({"message": message})
        return response
    except Exception as err:
        raise err

def send_video_completion_mail(to: str, user_name: str, video_name: str, video_link: str) -> dict:
    if not email_config_manager.is_email_enabled("video_completion"):
        logger.info(f"[EMAIL_SERVICE] Video completion email skipped - disabled in config for {to}")
        return {"status": "skipped", "reason": "disabled_in_config"}
    
    try:
        html_template_path = 'library/notification/email/video_completion.html'
        subject=f"Your video \"{video_name}\" is ready"
        html = video_completion_template(
            template_path=html_template_path,
            user_name=user_name, 
            video_name=video_name, 
            video_link=video_link
        )
        return send_mail(to, subject, html)
    except Exception as e:
        logger.error(e)
        return None

def send_video_failure_mail(to: str, user_name: str, video_name: str, refer_url: str) -> dict:
    if not email_config_manager.is_email_enabled("video_failure"):
        logger.info(f"[EMAIL_SERVICE] Video failure email skipped - disabled in config for {to}")
        return {"status": "skipped", "reason": "disabled_in_config"}
    
    try:
        html_template_path = 'library/notification/email/video_failure.html'
        subject=f"Your video \"{video_name}\" needs attention"
        html = video_failure_template(
            template_path=html_template_path,
            user_name=user_name, 
            video_name=video_name, 
            refer_url=refer_url
        )
        return send_mail(to, subject, html)
    except Exception as e:
        logger.error(e)
        return None

def send_welcome_pilot_mail(to: str, user_name: str) -> dict:
    if not email_config_manager.is_email_enabled("welcome_pilot"):
        logger.info(f"[EMAIL_SERVICE] Welcome pilot email skipped - disabled in config for {to}")
        return {"status": "skipped", "reason": "disabled_in_config"}
    
    try:
        html_template_path = 'library/notification/email/welcome_pilot.html'
        subject = "Welcome to the Editora pilot"
        html = welcome_pilot_template(
            template_path=html_template_path,
            user_name=user_name
        )
        return send_mail(to, subject, html)
    except Exception as e:
        logger.error(e)
        raise e

def send_portal_is_ready_mail(to: str, user_name: str, portal_url: str) -> dict:
    if not email_config_manager.is_email_enabled("portal_ready"):
        logger.info(f"[EMAIL_SERVICE] Portal ready email skipped - disabled in config for {to}")
        return {"status": "skipped", "reason": "disabled_in_config"}
    
    try:
        html_template_path = 'library/notification/email/portal_is_ready.html'
        subject = "Your Editora portal is ready"
        html = portal_is_ready_template(
            template_path=html_template_path,
            user_name=user_name,
            portal_url=portal_url,
        )
        return send_mail(to, subject, html)
    except Exception as e:
        logger.error(e)
        raise e


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Email client")

    # Create a mutually exclusive group to ensure user chooses either file or directory mode, not both
    notification_type_group = parser.add_mutually_exclusive_group(required=True)
    notification_type_group.add_argument('-s', '--success', action='store_true', help='Success')
    notification_type_group.add_argument('-f', '--failure', action='store_true', help='Failure')
    
    to = 'kishan.jay@editora.ai'
    user_name = 'Kishan Jay'
    video_name = '123 Park Ave'
    video_link = "https://storage.googleapis.com/editora-v2-users/user-test-91821539-9f1f-40d2-b93c-a0ce69126ae3/177a3af7-7260-49e7-af0f-a39df123e00e/a90371f8-61d4-43cf-92f3-c8661c0bf573/tmpwnr5n7xq.mp4?GoogleAccessId=firebase-adminsdk-52sf1%40editora-prod.iam.gserviceaccount.com&Expires=1739985749&Signature=HqOCggawCTsAeLxNYItn5%2FzXN269f4XuHQgl%2BWy8hcY9RkYY6zqVrFHlcplrvmcygvxtZu2fQSu3o%2BEMlmAMBtBD%2FMPoTdZ6mHC8JwF9d0Ps6vAj73QCGkiu12XelILtdyFuhe8TiMXxi03Y%2BDwa7JG3LP5uL9RsjXXthCAtcq7ZNervrwQJToZWcrCvw6K6af4bCjWND%2BGZAT%2B%2BdgBQSw%2FtACff%2FbWoqfIt%2BhpHHRFD3qGGoUMuPksap3hR%2BDjeoEhlYt3ld8%2FA1P1i32Ww%2FDoGpY80E5HFuHetindnLoKo904QX3OqaCevtaK38%2B%2BePgCxQevtu5ZlVSzYcgXXqw%3D%3D"
    refer_url = 'https://editora.ai'
    
    args = parser.parse_args()
    
    if args.success:
        response = send_video_completion_mail(
            to=to,                                         
            user_name=user_name,
            video_name=video_name,
            video_link=video_link)
    else:
        response = send_video_failure_mail(
            to=to,
            user_name=user_name,
            video_name=video_name,
            refer_url=refer_url
        )
    
    print(response)

if __name__ == '__main__':
    main()
