from logger import logger

def load_template(template_path: str) -> str:
    """Read and return the template content from the given file."""
    try:
        with open(template_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        logger.error(f"Error loading template from {template_path}: {e}")
        raise

def video_completion_template(template_path: str, user_name: str, video_name: str, video_link: str) -> str:
    """
    Load an HTML template for video completion, replace placeholders with actual values,
    and return the final HTML string.
    """
    template = load_template(template_path)
    return template.format(user_name=user_name, video_name=video_name, video_link=video_link)

def video_failure_template(template_path: str, user_name: str, video_name: str, refer_url: str) -> str:
    """
    Load an HTML template for video failure, replace placeholders with actual values,
    and return the final HTML string.
    """
    template = load_template(template_path)
    return template.format(user_name=user_name, video_name=video_name, refer_url=refer_url)

def welcome_pilot_template(template_path: str, user_name: str) -> str:
    """
    Load an HTML template for welcome pilot email, replace placeholders with actual values,
    and return the final HTML string.
    """
    template = load_template(template_path)
    return template.replace('{{user_name}}', user_name)


def portal_is_ready_template(template_path: str, user_name: str, portal_url: str) -> str:
    """
    Load an HTML template for portal is ready email, replace placeholders with actual values,
    and return the final HTML string.
    """
    template = load_template(template_path)
    # support both {{user_name}} and {user_name} style
    template = template.replace('{{user_name}}', user_name)
    return template.format(user_name=user_name, portal_url=portal_url)