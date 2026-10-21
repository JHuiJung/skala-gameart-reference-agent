import pytest
from fastapi import HTTPException

from app.dependencies import get_upload_form


def test_valid_text_becomes_form():
    assert get_upload_form("어두운 숲").text == "어두운 숲"


@pytest.mark.parametrize("text", ["", "a" * 2001])
def test_invalid_text_raises_422(text):
    with pytest.raises(HTTPException) as e:
        get_upload_form(text)
    assert e.value.status_code == 422
