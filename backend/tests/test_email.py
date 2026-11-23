from email import policy
from email.parser import Parser
from unittest.mock import patch

from app.infra.config import settings
from app.services import email


def test_every_email_includes_the_confidentiality_notice(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "username")
    monkeypatch.setattr(settings, "smtp_password", "password")
    monkeypatch.setattr(settings, "smtp_from_email", "hr@example.com")

    with patch("app.services.email.smtplib.SMTP") as smtp:
        email.send_email(
            to="applicant@example.com",
            subject="Application update",
            body="Your application has been updated.",
        )

    server = smtp.return_value.__enter__.return_value
    raw_message = server.send_message.call_args.args[0].as_string()
    message = Parser(policy=policy.default).parsestr(raw_message)
    assert message.get_content() == (
        "Your application has been updated.\n\n"
        f"{email.CONFIDENTIALITY_NOTICE}\n"
    )
