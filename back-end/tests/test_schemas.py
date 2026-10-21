import pytest
from pydantic import ValidationError

from app.agent.state import Candidate
from app.schemas import AnswerRequest, UploadForm


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


def test_answer_request_cleans_categories():
    req = AnswerRequest(thread_id="t", categories=[" 겨울 배경 ", "", "소품"])
    assert req.categories == ["겨울 배경", "소품"]
    assert AnswerRequest(thread_id="t").categories is None  # 질문 답변만 보내는 경우


@pytest.mark.parametrize("names", [[], ["  "], ["a"] * 9, ["가" * 41]])
def test_answer_request_rejects_bad_categories(names):
    with pytest.raises(ValidationError):
        AnswerRequest(thread_id="t", categories=names)


@pytest.mark.parametrize("count, ok", [(1, True), (10, True), (5, True), (0, False), (11, False)])
def test_answer_request_per_category_range(count, ok):
    if ok:
        assert AnswerRequest(thread_id="t", categories=["a"], per_category=count).per_category == count
    else:
        with pytest.raises(ValidationError):
            AnswerRequest(thread_id="t", categories=["a"], per_category=count)


def test_answer_request_per_category_defaults_to_five():
    assert AnswerRequest(thread_id="t", categories=["a"]).per_category == 5
