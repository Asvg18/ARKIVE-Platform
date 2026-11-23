"""Outbound email over SMTP, always in addition to the in-app notice
(call send_email_safely)."""

import logging
import smtplib
from email.message import EmailMessage

from app.infra.config import settings

logger = logging.getLogger(__name__)

CONFIDENTIALITY_NOTICE = (
    "CONFIDENTIALITY NOTICE\n"
    "The information in this e-mail, including any attached file, is confidential and is solely "
    "for the use of the intended recipient/s. If you received this e-mail in error, please notify "
    "the sender immediately. Disseminating, distributing or copying this e-mail including any "
    "attachment is prohibited."
)


class EmailNotConfiguredError(Exception):
    """SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD aren't all set."""


def email_configured() -> bool:
    """Whether this copy of ARKIVE has a mail server to send through at
    all. True does not promise delivery -- the server can still refuse a
    login or a message -- but False promises that nothing will be sent,
    which is what a screen needs to know to say so up front."""
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)


def send_email(*, to: str, subject: str, body: str) -> None:
    """The real send. Raises on anything wrong -- unconfigured, refused
    connection, rejected login -- rather than swallowing it, so a caller
    that genuinely needs to know can. Most callers don't; see
    send_email_safely below."""
    if not email_configured():
        raise EmailNotConfiguredError(
            "SMTP is not configured -- set SMTP_HOST, SMTP_USERNAME and "
            "SMTP_PASSWORD in backend/.env."
        )

    # A relay's login is often not a verified sender (Brevo's
    # `<id>@smtp-brevo.com`): mail From it is accepted, then silently
    # dropped. So falling back to it logs a warning.
    sender = settings.smtp_from_email
    if not sender:
        sender = settings.smtp_username
        logger.warning(
            "SMTP_FROM_EMAIL is not set, so mail is being sent From the SMTP "
            "login (%s). Most relays only deliver mail From a verified sender "
            "address -- if messages are accepted but never arrive, this is why.",
            sender,
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message.set_content(f"{body.rstrip()}\n\n{CONFIDENTIALITY_NOTICE}")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_use_tls:
            server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def send_email_safely(*, to: str, subject: str, body: str) -> bool:
    """What every call site should call: never raises, so a mail problem
    never fails the action that sent it. Without SMTP_HOST it logs and
    returns False. Returns whether it sent, for logging only."""
    try:
        send_email(to=to, subject=subject, body=body)
        return True
    except EmailNotConfiguredError:
        logger.info("Email not sent (SMTP not configured): %r", subject)
        return False
    except Exception:
        logger.exception("Failed to send email: %r", subject)
        return False
