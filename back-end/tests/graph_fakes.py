"""그래프 전체 흐름 테스트에서 공유하는 대역(가짜 데이터)."""
from app.agent.state import ExtractedDetails, ExtractedField, ReferenceCategory

CATEGORY = ReferenceCategory(name="배경", reason="r", queries=["snowy field"])


def extracted(**values) -> ExtractedDetails:
    return ExtractedDetails(items=[ExtractedField(key=k, value=v) for k, v in values.items()])


def start_state() -> dict:
    return {"text": "입력", "image_b64": None, "image_mime": None}
