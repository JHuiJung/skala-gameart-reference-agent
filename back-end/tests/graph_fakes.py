"""그래프 전체 흐름 테스트에서 공유하는 대역(가짜 데이터)."""
from app.agent import runner
from app.agent.state import ExtractedDetails, ExtractedField, ReferenceCategory
from app.schemas import AnswerRequest

CATEGORY = ReferenceCategory(name="배경", reason="r", queries=["snowy field"])


def extracted(**values) -> ExtractedDetails:
    return ExtractedDetails(items=[ExtractedField(key=k, value=v) for k, v in values.items()])


def start_state() -> dict:
    return {"text": "입력", "image_b64": None, "image_mime": None}


def ans(thread_id: str, **fields) -> AnswerRequest:
    """사용자의 답 요청. 예: ans(tid, categories=["배경"], per_category=3)"""
    return AnswerRequest(thread_id=thread_id, **fields)


async def to_select_images(per_category: int = 3):
    """입력부터 시작해 '이미지 선택' 단계에서 멈춘 응답을 돌려준다. (필수 항목이 모두 있는 입력이어야 한다)"""
    first = await runner.start(start_state())  # 카테고리 확인에서 멈춤
    return await runner.resume(ans(first.thread_id, categories=["배경"], per_category=per_category))


async def to_confirm_brief(save_unverified: bool = False):
    """이미지 선택까지 마치고 '지시서 계획 확인' 단계에서 멈춘 응답을 돌려준다."""
    selecting = await to_select_images()
    ids = [c.id for c in selecting.candidates]
    return await runner.resume(ans(selecting.thread_id, selected_ids=ids, save_unverified=save_unverified))
