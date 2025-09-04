from logger import logger

def send_notification(title: str, body: str, subscription_id: str):
    try:
        message = {
            "notification": {
                "title": title,
                "body": body,
            },
            "token": subscription_id,
        }
        # Replace this with your actual notification client logic.
        # For example, if using Firebase Admin SDK:
        # response = notification_client.send(message)
        # logging.info(response)
        logger.info(f"Notification sent: {message}")
    except Exception as error:
        logger.error(error)
