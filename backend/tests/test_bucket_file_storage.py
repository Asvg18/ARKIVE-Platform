"""Bucket-backed upload storage (app/services/file_storage.py).

A small in-memory stand-in plays the S3 bucket, so these tests need no
network and no extra packages beyond botocore (for its error type). What
is being proved: a file survives the local disk being wiped, a file the
bucket never had is still reported missing, and deleting removes both
copies. With the bucket settings blank, nothing may reach the bucket.
"""

import io

import pytest
from botocore.exceptions import ClientError

from app.infra.config import settings
from app.services import file_storage

PDF = b"%PDF-1.4 a resume"


class FakeBucket:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.fail_puts = False

    def put_object(self, Bucket, Key, Body):
        if self.fail_puts:
            raise ClientError({"Error": {"Code": "InternalError", "Message": "down"}}, "PutObject")
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


class ExplodingClient:
    def __getattr__(self, name):
        raise AssertionError(f"the bucket was used ({name}) while it is switched off")


@pytest.fixture
def bucket(monkeypatch, tmp_path):
    fake = FakeBucket()
    monkeypatch.setattr(settings, "upload_bucket", "arkive-files")
    monkeypatch.setattr(settings, "aws_endpoint_url_s3", "https://bucket.example")
    monkeypatch.setattr(settings, "aws_access_key_id", "key")
    monkeypatch.setattr(settings, "aws_secret_access_key", "secret")
    monkeypatch.setattr(file_storage, "_client", fake)
    monkeypatch.setattr(file_storage, "_BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(file_storage, "_RESUME_UPLOAD_DIR", tmp_path / "uploads" / "resumes")
    monkeypatch.setattr(file_storage, "_DOCUMENT_UPLOAD_DIR", tmp_path / "uploads" / "documents")
    return fake


def test_resume_comes_back_after_the_local_disk_is_wiped(bucket):
    stored_path = file_storage.save_resume_file(PDF)
    assert ("arkive-files", stored_path) in bucket.objects

    file_storage.resolve_resume_path(stored_path).unlink()
    restored = file_storage.resolve_resume_path(stored_path)

    assert restored.read_bytes() == PDF


def test_a_resume_the_bucket_never_had_is_still_missing(bucket):
    path = file_storage.resolve_resume_path("uploads/resumes/" + "0" * 32 + ".pdf")

    assert not path.is_file()


def test_document_comes_back_after_the_local_disk_is_wiped(bucket):
    stored_path = file_storage.save_supplemental_document_file(PDF)

    file_storage.resolve_document_path(stored_path).unlink()

    assert file_storage.resolve_document_path(stored_path).read_bytes() == PDF


def test_job_description_upload_id_is_found_from_the_bucket(bucket):
    upload_id = file_storage.save_job_description_file(PDF)
    file_storage._JD_UPLOAD_DIR.joinpath(f"{upload_id}.pdf").unlink()

    stored_path = file_storage.job_description_stored_path(upload_id)

    assert stored_path == f"uploads/job_descriptions/{upload_id}.pdf"
    assert file_storage.resolve_job_description_path(stored_path).read_bytes() == PDF
    assert file_storage.job_description_stored_path("f" * 32) is None


def test_avatar_comes_back_and_deleting_removes_both_copies(bucket):
    name = file_storage.save_avatar_file(b"\xff\xd8\xff photo", "jpg")
    file_storage.resolve_avatar_path(name).unlink()

    restored = file_storage.resolve_avatar_path(name)
    assert restored is not None and restored.read_bytes() == b"\xff\xd8\xff photo"

    file_storage.delete_avatar_file(name)

    assert file_storage.resolve_avatar_path(name) is None
    assert bucket.objects == {}


def test_deleting_a_stored_file_removes_the_disk_and_bucket_copies(bucket):
    stored_path = file_storage.save_resume_file(PDF)
    path = file_storage.resolve_resume_path(stored_path)

    file_storage.delete_stored_file(path)

    assert not path.exists()
    assert bucket.objects == {}


def test_a_failed_bucket_write_raises_and_leaves_no_local_file(bucket):
    bucket.fail_puts = True

    with pytest.raises(ClientError):
        file_storage.save_resume_file(PDF)

    assert list(file_storage._RESUME_UPLOAD_DIR.glob("*")) == []


def test_nothing_reaches_the_bucket_when_it_is_not_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_bucket", None)
    monkeypatch.setattr(file_storage, "_client", ExplodingClient())
    monkeypatch.setattr(file_storage, "_BACKEND_ROOT", tmp_path)
    monkeypatch.setattr(file_storage, "_RESUME_UPLOAD_DIR", tmp_path / "uploads" / "resumes")

    stored_path = file_storage.save_resume_file(PDF)
    path = file_storage.resolve_resume_path(stored_path)
    assert path.read_bytes() == PDF

    file_storage.delete_stored_file(path)
    assert not path.exists()
