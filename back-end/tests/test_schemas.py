import pytest
from pydantic import ValidationError

from app.agent.state import Candidate
from app.schemas import UploadForm


def test_upload_form_accepts_text():
    assert UploadForm(text="숲속 마을").text == "숲속 마을"


@pytest.mark.parametrize("text", ["", "a" * 2001])
def test_upload_form_rejects_empty_or_too_long(text):
    with pytest.raises(ValidationError):
        UploadForm(text=text)


def test_candidate_license_defaults_to_unclear():
    # 라이선스가 불명확한 이미지는 기본적으로 검토 대상으로 표시한다 (Need.md 10장)
    c = Candidate(id="c1", image_url="https://x/i.jpg", source_url="https://x")
    assert c.license == "unclear"


def test_candidate_rejects_unknown_license():
    with pytest.raises(ValidationError):
        Candidate(id="c1", image_url="u", source_url="s", license="free")
