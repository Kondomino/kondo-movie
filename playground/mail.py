import argparse

from config.config import settings

from mailchimp_transactional import Client
from gcp.secret import secret_mgr

MAILCHIMP_API_KEY = secret_mgr.secret(settings.Secret.MAILCHIMP_API_KEY)

def send_mailchimp_email(subject, message, from_email, to_email, to_name):
    try:
        mailchimp = Client(MAILCHIMP_API_KEY)
        payload = {
            "from_email": from_email,
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "text": message
        }
        response = mailchimp.messages.send({"message": payload})
        print("Email sent successfully:", response)
    except Exception as e:
        print("An error occurred:", e)

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Email client")

    # Create a mutually exclusive group to ensure user chooses either file or directory mode, not both
    parser.add_argument("-f", "--from_address", type=str, required=True, help="From email address")
    parser.add_argument("-n", "--to_name", type=str, help="From email address")
    parser.add_argument("-t", "--to_address", type=str, required=True, help="To email address")
    parser.add_argument("-s", "--subject", type=str, required=True, help="Subject")
    
    args = parser.parse_args()
    
    message = f"""
Hello {args.to_name}! 

We are thrilled to inform you that your support team is ready to handle tickets via email. Have a great day!

Cheers,
Editora Support
    """
    
    send_mailchimp_email(
        from_email=args.from_address,
        to_email=args.to_address,
        to_name=args.to_name if args.to_name else 'Recipient',
        subject=args.subject,
        message=message
    )
    
if __name__ == '__main__':
    main()
