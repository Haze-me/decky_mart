from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings


class GoogleTokenError(Exception):
    pass


def verify_google_id_token(token: str) -> dict:
    try:
        payload = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except ValueError as exc:
        raise GoogleTokenError(str(exc))

    if not payload.get("email_verified", False):
        raise GoogleTokenError("Google account email is not verified")

    return payload