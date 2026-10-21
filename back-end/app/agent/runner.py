"""그래프 실행과 결과 변환을 맡는다. API 라우트는 여기 함수만 부르면 된다."""
import uuid

from langgraph.types import Command

from app.agent.checklist import CHECKLISTS
from app.agent.graph import graph
from app.schemas import AgentResponse


class ThreadNotWaiting(Exception):
    """이어서 실행할 작업이 없거나(없는 thread_id), 답을 기다리는 상태가 아닐 때."""


class WrongAnswerKind(Exception):
    """기다리는 답의 종류(질문 답변 / 카테고리 확정)와 보낸 답의 종류가 다를 때."""


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _to_response(thread_id: str, result: dict) -> AgentResponse:
    common = {
        "thread_id": thread_id,
        "asset_type": result.get("asset_type"),
        "details": result.get("details", {}),
        "detail_labels": {i.key: i.label for i in CHECKLISTS.get(result.get("asset_type"), [])},
    }
    if "__interrupt__" in result:  # 사용자 답변이 필요해서 그래프가 멈춘 상태
        payload = result["__interrupt__"][0].value
        if payload["kind"] == "confirm_categories":
            return AgentResponse(
                status="needs_input", kind="confirm_categories",
                proposed_categories=payload["categories"], **common,
            )
        return AgentResponse(status="needs_input", kind="questions", questions=payload["questions"], **common)
    plan = result.get("reference_plan")
    return AgentResponse(
        status="done",
        analysis=result.get("analysis"),
        guidelines=result.get("guidelines", []),
        categories=result.get("final_categories", []),
        exclude_terms=plan.exclude_terms if plan else [],
        candidates=result.get("candidates", []),
        source_errors=result.get("source_errors", []),
        **common,
    )


async def start(initial_state: dict) -> AgentResponse:
    """새 작업을 시작한다. 질문이 필요하면 needs_input, 아니면 끝까지 실행해 done 을 돌려준다."""
    thread_id = uuid.uuid4().hex
    result = await graph.ainvoke(initial_state, _config(thread_id))
    return _to_response(thread_id, result)


async def resume(thread_id: str, answers: dict[str, str], categories: list[str] | None = None) -> AgentResponse:
    """사용자의 답을 전달해 멈춘 작업을 이어서 실행한다.

    answers 는 질문에 대한 답, categories 는 카테고리 확정에 대한 답이다. 기다리는 답의 종류와 맞아야 한다.
    """
    snapshot = await graph.aget_state(_config(thread_id))
    if not snapshot.next:  # 없는 thread 이거나 이미 끝난 작업
        raise ThreadNotWaiting(thread_id)

    waiting_for = snapshot.tasks[0].interrupts[0].value["kind"]
    if (waiting_for == "confirm_categories") != (categories is not None):
        raise WrongAnswerKind(waiting_for)

    value = {"categories": categories} if categories is not None else answers
    result = await graph.ainvoke(Command(resume=value), _config(thread_id))
    return _to_response(thread_id, result)
