"""Reading a job description whose PDF is only a picture (services/jd_text.py).

Made the same way as test_resume_text.py's: Pillow saving a picture as a
one-page PDF, so it has no text layer and exactly one embedded image, as a
scanned upload would. Only the model calls are mocked."""

import io
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw

from app.domain.jd_rules import NotAJobDescriptionError
from app.infra.config import settings
from app.schemas.pipeline import JDExtractionCandidate, JDImageReading
from app.services.jd_text import read_job_description_text
from app.services.pdf_text import AIExtractionFailedError, ExtractionNotConfiguredError, PdfTextExtractionError
from scripts._mini_pdf import text_pdf
from tests.conftest import auth_headers

_TRANSCRIPTION = (
    "INSTRUCTOR I\nCollege of Computing and Multimedia Studies\n"
    "QUALIFICATIONS\nMaster's degree in Computer Science\nREQUIREMENTS\nTeaching experience"
)


def _image_pdf(*, size=(850, 1100)) -> bytes:
    picture = Image.new("RGB", size, "white")
    ImageDraw.Draw(picture).text((60, 60), "INSTRUCTOR I  Job Description", fill="black")
    buffer = io.BytesIO()
    picture.save(buffer, format="PDF")
    return buffer.getvalue()


def _reading(**overrides) -> JDImageReading:
    values = dict(is_job_description=True, document_kind="job description", reason="", text=_TRANSCRIPTION)
    values.update(overrides)
    return JDImageReading(**values)


@patch("app.services.jd_text.ChatOpenAI")
def test_a_text_pdf_is_read_as_before_with_no_model_call(mock_llm):
    text = read_job_description_text(text_pdf(["Instructor I", "Qualifications"]), max_chars=1000)
    assert "Instructor I" in text
    mock_llm.assert_not_called()


@patch("app.services.jd_text.ChatOpenAI")
def test_an_image_pdf_that_is_a_job_description_is_transcribed(mock_llm, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    invoke = mock_llm.return_value.with_structured_output.return_value.invoke
    invoke.return_value = _reading()

    text = read_job_description_text(_image_pdf(), max_chars=1000)

    assert text == _TRANSCRIPTION
    messages = invoke.call_args.args[0]
    images = [part for part in messages[1]["content"] if part["type"] == "image_url"]
    assert len(images) == 1
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@patch("app.services.jd_text.ChatOpenAI")
def test_an_image_pdf_that_is_not_a_job_description_is_refused(mock_llm, monkeypatch):
    """The check comes before the transcription, and refuses the same way
    a typed PDF that is not a job description is refused."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.return_value = _reading(
        is_job_description=False,
        document_kind="a certificate of employment",
        reason="It certifies past service, it does not advertise a role.",
        text="CERTIFICATE OF EMPLOYMENT",
    )

    with pytest.raises(NotAJobDescriptionError) as refused:
        read_job_description_text(_image_pdf(), max_chars=1000)

    assert refused.value.document_kind == "a certificate of employment"


@patch("app.services.jd_text.ChatOpenAI")
def test_a_job_description_verdict_with_no_text_is_still_refused(mock_llm, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.return_value = _reading(text="  ")

    with pytest.raises(PdfTextExtractionError):
        read_job_description_text(_image_pdf(), max_chars=1000)


@patch("app.services.jd_text.ChatOpenAI")
def test_a_tiny_image_is_not_treated_as_a_page(mock_llm, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    with pytest.raises(PdfTextExtractionError):
        read_job_description_text(_image_pdf(size=(120, 60)), max_chars=1000)

    mock_llm.assert_not_called()


def test_an_image_pdf_needs_the_model_to_be_configured(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(ExtractionNotConfiguredError):
        read_job_description_text(_image_pdf(), max_chars=1000)


@patch("app.services.jd_text.ChatOpenAI")
def test_a_failed_model_call_is_reported_as_one(mock_llm, monkeypatch):
    import openai

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.side_effect = openai.OpenAIError("boom")

    with pytest.raises(AIExtractionFailedError):
        read_job_description_text(_image_pdf(), max_chars=1000)


@patch("app.services.jd_text.ChatOpenAI")
def test_a_file_that_is_not_a_pdf_is_refused_without_a_model_call(mock_llm):
    with pytest.raises(PdfTextExtractionError):
        read_job_description_text(b"not a pdf at all", max_chars=1000)
    mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Through HR's job builder route.
# ---------------------------------------------------------------------------


def _post(client):
    return client.post(
        "/hr/requisitions/extract-jd",
        headers=auth_headers(client, "hr-test@arkivetesting.com"),
        data={"job_title": "Instructor I"},
        files={"jd_file": ("scan.pdf", _image_pdf(), "application/pdf")},
    )


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
@patch("app.services.jd_text.ChatOpenAI")
def test_extract_refuses_a_scanned_file_that_is_not_a_job_description(
    mock_vision, mock_extract, client, hr_admin, monkeypatch
):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_vision.return_value.with_structured_output.return_value.invoke.return_value = _reading(
        is_job_description=False, document_kind="a lecture handout", reason="It teaches a lesson.", text=""
    )

    resp = _post(client)

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # the same refusal the builder already shows for a typed PDF
    assert detail["code"] == "not_a_job_description"
    assert detail["document_kind"] == "a lecture handout"
    mock_extract.assert_not_called()


@patch("app.services.jd_extraction.ChatOpenAI.with_structured_output")
@patch("app.services.jd_text.ChatOpenAI")
def test_extract_reads_the_fields_from_a_scanned_job_description(
    mock_vision, mock_extract, client, hr_admin, monkeypatch
):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_vision.return_value.with_structured_output.return_value.invoke.return_value = _reading()
    mock_extract.return_value.invoke.return_value = JDExtractionCandidate(
        department="College of Computing and Multimedia Studies",
        description="Teaches undergraduate computing courses and advises students.",
        qualifications="Master's degree in Computer Science",
        requirements="Teaching experience",
        is_job_description=True,
        document_kind="job description",
        reason="",
    )

    resp = _post(client)

    assert resp.status_code == 200, resp.text
    assert resp.json()["qualifications"] == "Master's degree in Computer Science"
    assert resp.json()["jd_upload_id"]
    # the field extraction read the transcription, not an empty string
    extraction_messages = mock_extract.return_value.invoke.call_args.args[0]
    assert _TRANSCRIPTION in extraction_messages[1]["content"]
