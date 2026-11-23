"""Reading a resume whose PDF is only a picture (services/resume_text.py).

The image PDFs here are made the way an image-to-PDF converter makes them
-- Pillow saving a picture as a one-page PDF -- so they really have no
text layer and exactly one embedded image, and pypdf sees them as a real
scanned upload would look. Only the model call is mocked."""

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from app.infra.config import settings
from app.schemas.resume import ResumeImageReading
from app.services.pdf_text import AIExtractionFailedError, ExtractionNotConfiguredError, PdfTextExtractionError
from app.services.resume_text import NotAResumeError, read_resume_text
from scripts._mini_pdf import text_pdf
from tests.conftest import auth_headers

_TRANSCRIPTION = "JUAN DELA CRUZ\nEXPERIENCE\nQA Engineer, Acme\nSKILLS\nPython, Testing"


def _image_pdf(*, size=(850, 1100)) -> bytes:
    picture = Image.new("RGB", size, "white")
    ImageDraw.Draw(picture).text((60, 60), "JUAN DELA CRUZ  QA Engineer", fill="black")
    buffer = io.BytesIO()
    picture.save(buffer, format="PDF")
    return buffer.getvalue()


def _reading(**overrides) -> ResumeImageReading:
    values = dict(is_resume=True, reason="A one-page CV.", text=_TRANSCRIPTION)
    values.update(overrides)
    return ResumeImageReading(**values)


def test_the_image_pdf_fixture_really_has_no_text_layer():
    reader = PdfReader(io.BytesIO(_image_pdf()))
    assert (reader.pages[0].extract_text() or "").strip() == ""
    assert len(list(reader.pages[0].images)) == 1


@patch("app.services.resume_text.ChatOpenAI")
def test_a_text_pdf_is_read_as_before_with_no_model_call(mock_llm):
    text = read_resume_text(text_pdf(["Ada Applicant", "QA Engineer"]), max_chars=1000)
    assert "QA Engineer" in text
    mock_llm.assert_not_called()


@patch("app.services.resume_text.ChatOpenAI")
def test_an_image_pdf_that_is_a_resume_is_transcribed(mock_llm, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    invoke = mock_llm.return_value.with_structured_output.return_value.invoke
    invoke.return_value = _reading()

    text = read_resume_text(_image_pdf(), max_chars=1000)

    assert text == _TRANSCRIPTION
    # the page went to the model as an image, not as text
    messages = invoke.call_args.args[0]
    images = [part for part in messages[1]["content"] if part["type"] == "image_url"]
    assert len(images) == 1
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@patch("app.services.resume_text.ChatOpenAI")
def test_an_image_pdf_that_is_not_a_resume_is_refused(mock_llm, monkeypatch):
    """The check comes before the transcription: an ID or a certificate
    must not become someone's resume record."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.return_value = _reading(
        is_resume=False, reason="A certificate of completion.", text="CERTIFICATE OF COMPLETION"
    )

    with pytest.raises(NotAResumeError) as refused:
        read_resume_text(_image_pdf(), max_chars=1000)

    # a PdfTextExtractionError, so every route already answers it with 422
    assert isinstance(refused.value, PdfTextExtractionError)
    assert "doesn't look like a resume" in str(refused.value)


@patch("app.services.resume_text.ChatOpenAI")
def test_a_resume_verdict_with_no_text_is_still_refused(mock_llm, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.return_value = _reading(text="  ")

    with pytest.raises(PdfTextExtractionError):
        read_resume_text(_image_pdf(), max_chars=1000)


@patch("app.services.resume_text.ChatOpenAI")
def test_a_tiny_image_is_not_treated_as_a_page(mock_llm, monkeypatch):
    """A logo-sized picture is not a page of text: same refusal as an
    image-free PDF, and no model call."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    with pytest.raises(PdfTextExtractionError) as refused:
        read_resume_text(_image_pdf(size=(120, 60)), max_chars=1000)

    assert not isinstance(refused.value, NotAResumeError)
    mock_llm.assert_not_called()


def test_an_image_pdf_needs_the_model_to_be_configured(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(ExtractionNotConfiguredError):
        read_resume_text(_image_pdf(), max_chars=1000)


@patch("app.services.resume_text.ChatOpenAI")
def test_a_failed_model_call_is_reported_as_one(mock_llm, monkeypatch):
    import openai

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.side_effect = openai.OpenAIError("boom")

    with pytest.raises(AIExtractionFailedError):
        read_resume_text(_image_pdf(), max_chars=1000)


@patch("app.services.resume_text.ChatOpenAI")
def test_the_transcription_cannot_loop_past_the_upload_time_limit(mock_llm, monkeypatch):
    """A column-laid-out CV once sent the model into a whitespace loop to
    its 16k-token limit, past the browser's two minutes (20 Oct 2026)."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.return_value = _reading()

    read_resume_text(_image_pdf(), max_chars=1000)

    options = mock_llm.call_args.kwargs
    assert options["frequency_penalty"] > 0
    assert options["max_tokens"] <= 8000


@patch("app.services.resume_text.ChatOpenAI")
def test_a_transcription_cut_off_at_the_token_cap_is_reported_as_a_failure(mock_llm, monkeypatch):
    import openai

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_llm.return_value.with_structured_output.return_value.invoke.side_effect = openai.LengthFinishReasonError(
        completion=MagicMock()
    )

    with pytest.raises(AIExtractionFailedError):
        read_resume_text(_image_pdf(), max_chars=1000)


@patch("app.services.resume_text.ChatOpenAI")
def test_the_same_scanned_file_is_not_read_twice(mock_llm, monkeypatch):
    """The preview reads a scanned resume; the upload, a minute later,
    sends the very same file. Reading it again was what pushed the upload
    past the browser's time limit."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    invoke = mock_llm.return_value.with_structured_output.return_value.invoke
    invoke.return_value = _reading()
    pdf = _image_pdf()

    assert read_resume_text(pdf, max_chars=1000) == _TRANSCRIPTION
    assert read_resume_text(pdf, max_chars=10) == _TRANSCRIPTION[:10]

    assert invoke.call_count == 1


@patch("app.services.resume_text.ChatOpenAI")
def test_a_different_scanned_file_is_read_and_checked_again(mock_llm, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    invoke = mock_llm.return_value.with_structured_output.return_value.invoke
    invoke.return_value = _reading()
    read_resume_text(_image_pdf(), max_chars=1000)

    invoke.return_value = _reading(is_resume=False, reason="An ID.", text="")
    with pytest.raises(NotAResumeError):
        read_resume_text(_image_pdf(size=(900, 1200)), max_chars=1000)

    assert invoke.call_count == 2


@patch("app.services.resume_text.ChatOpenAI")
def test_a_refused_scan_is_not_kept(mock_llm, monkeypatch):
    """Only a reading that passed the check is reused; a refusal is asked
    again, so the same file can never slip through on a later call."""
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    invoke = mock_llm.return_value.with_structured_output.return_value.invoke
    invoke.return_value = _reading(is_resume=False, reason="A certificate.", text="")
    pdf = _image_pdf()

    for _ in range(2):
        with pytest.raises(NotAResumeError):
            read_resume_text(pdf, max_chars=1000)

    assert invoke.call_count == 2


@patch("app.services.resume_text.ChatOpenAI")
def test_a_file_that_is_not_a_pdf_is_refused_without_a_model_call(mock_llm):
    with pytest.raises(PdfTextExtractionError):
        read_resume_text(b"not a pdf at all", max_chars=1000)
    mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Through the applicant's own routes.
# ---------------------------------------------------------------------------


@patch("app.services.resume_extraction.ChatOpenAI.with_structured_output")
@patch("app.services.resume_text.ChatOpenAI")
def test_preview_refuses_a_scanned_file_that_is_not_a_resume(mock_vision, mock_extract, client, applicant, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_vision.return_value.with_structured_output.return_value.invoke.return_value = _reading(
        is_resume=False, reason="A government ID.", text=""
    )
    headers = auth_headers(client, applicant.email)

    resp = client.post(
        "/applicant/resume/extract",
        headers=headers,
        files={"resume_file": ("scan.pdf", _image_pdf(), "application/pdf")},
    )

    assert resp.status_code == 422, resp.text
    assert "doesn't look like a resume" in resp.json()["detail"]
    # refused before the resume fields were ever extracted
    mock_extract.assert_not_called()


@patch("app.services.resume_extraction.ChatOpenAI.with_structured_output")
@patch("app.services.resume_text.ChatOpenAI")
def test_preview_extracts_fields_from_a_scanned_resume(mock_vision, mock_extract, client, applicant, monkeypatch):
    from tests.test_applicant_flow import _fake_resume

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    mock_vision.return_value.with_structured_output.return_value.invoke.return_value = _reading()
    mock_extract.return_value.invoke.return_value = _fake_resume()
    headers = auth_headers(client, applicant.email)

    resp = client.post(
        "/applicant/resume/extract",
        headers=headers,
        files={"resume_file": ("scan.pdf", _image_pdf(), "application/pdf")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["full_name"] == "Ada Applicant"
    # the field extraction read the transcription, not an empty string
    extraction_messages = mock_extract.return_value.invoke.call_args.args[0]
    assert _TRANSCRIPTION in extraction_messages[1]["content"]
