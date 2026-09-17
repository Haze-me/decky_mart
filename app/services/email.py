from mailjet_rest import Client

from app.core.config import settings

mailjet = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_API_SECRET), version="v3.1")


def send_otp_email(to_email: str, code: str, purpose: str) -> None:
    subject = "Verify your email" if purpose == "email_verification" else "Reset your password"
    text_body = f"Your verification code is {code}. It expires in {settings.OTP_EXPIRE_MINUTES} minutes."

    data = {
        "Messages": [
            {
                "From": {"Email": settings.MAILJET_SENDER_EMAIL, "Name": "SolveMart"},
                "To": [{"Email": to_email}],
                "Subject": subject,
                "TextPart": text_body,
            }
        ]
    }
    result = mailjet.send.create(data=data)
    if result.status_code != 200:
        raise RuntimeError(f"Mailjet send failed: {result.status_code} {result.json()}")
    
def send_review_result_email(to_email: str, approved: bool, rejection_reason: str | None = None) -> None:
    if approved:
        subject = "Your SolveMart account has been approved"
        text_body = "Congratulations! Your Solver account has been reviewed and approved. You can now log in and start receiving jobs."
    else:
        subject = "Your SolveMart account submission needs attention"
        text_body = f"Your Solver account submission was not approved. Reason: {rejection_reason}. Please update your profile and resubmit."

    data = {
        "Messages": [
            {
                "From": {"Email": settings.MAILJET_SENDER_EMAIL, "Name": "SolveMart"},
                "To": [{"Email": to_email}],
                "Subject": subject,
                "TextPart": text_body,
            }
        ]
    }
    result = mailjet.send.create(data=data)
    if result.status_code != 200:
        raise RuntimeError(f"Mailjet send failed: {result.status_code} {result.json()}")