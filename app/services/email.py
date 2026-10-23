import requests

from app.core.config import settings

RESEND_API_URL = "https://api.resend.com/emails"
MAIL_SENDER_NAME = "DeckyMart"

def _send(to_email: str, subject: str, text_body: str) -> None:
    response = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": f"{MAIL_SENDER_NAME} <{settings.RESEND_SENDER_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "text": text_body,
        },
        timeout=10,
    )
    if response.status_code >= 400:
        # Deliberately not including the response body: Resend's error payloads can echo back
        # request fields (e.g. the recipient address), and this message ends up in logs via the
        # callers' `logger.error`. Status code + error name is enough to act on; full detail is
        # in the Resend dashboard, which is where PII-adjacent debugging data belongs.
        error_name = None
        try:
            error_name = response.json().get("name")
        except ValueError:
            pass
        raise RuntimeError(f"Resend send failed: {response.status_code} ({error_name or 'unknown error'})")


def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    subject = "Verify your email" if purpose == "email_verification" else "Reset your password"
    text_body = f"Your verification code is {code}. It expires in {settings.OTP_EXPIRE_MINUTES} minutes."
    _send(to_email, subject, text_body)


def send_review_result_email(to_email: str, approved: bool, rejection_reason: str | None = None) -> None:
    if approved:
        subject = "Your DeckyMart account has been approved"
        text_body = "Congratulations! Your DeckyMart account has been reviewed and approved. You can now log in and start receiving jobs."
    else:
        subject = "Your DeckyMart account submission needs attention"
        text_body = f"Your DeckyMart account submission was not approved. Reason: {rejection_reason}. Please update your profile and resubmit."
    _send(to_email, subject, text_body)


def send_account_status_email(
    to_email: str, status: str, reason: str | None = None, restored_status: str | None = None
) -> None:
    if status == "suspended":
        subject = "Your DeckyMart account has been suspended"
        text_body = f"Your account has been suspended. Reason: {reason}. You can still view your account, but some features are restricted."
    elif status == "banned":
        subject = "Your DeckyMart account has been banned"
        text_body = f"Your account has been banned. Reason: {reason}. Please contact support if you believe this is a mistake."
    else:
        subject = "Your DeckyMart account restriction has been lifted"
        if restored_status == "active":
            text_body = "Your account has been reactivated and you now have full access again."
        elif restored_status == "pending_review":
            text_body = "Your account restriction has been lifted. Your account is still awaiting review before it goes live."
        elif restored_status == "rejected":
            text_body = "Your restriction has been lifted. Your earlier submission was not approved. Please update your profile and resubmit."
        else:
            text_body = "Your account restriction has been lifted. Please log in to continue your registration."
    _send(to_email, subject, text_body)
