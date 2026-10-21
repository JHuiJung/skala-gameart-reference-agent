"""그래프 실행과 결과 변환을 맡는다. API 라우트는 여기 함수만 부르면 된다."""
import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from langgraph.types import Command

from app.agent.checklist import CHECKLISTS
from app.agent.graph import NODE_LABELS, graph
from app.agent import storage
from app.schemas import AgentResponse, AnswerRequest, OutputSummary

logger = logging.getLogger(__name__)


class ThreadNotWaiting(Exception):
    """이어서 실행할 작업이 없거나(없는 thread_id), 답을 기다리는 상태가 아닐 때."""


class WrongAnswerKind(Exception):
    """기다리는 답의 종류(질문 답변 / 카테고리 확정 / 이미지 선택 / 지시서 계획 승인)와 보낸 답의 종류가 다를 때."""


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _output_summary(result: dict) -> OutputSummary:
    refs = result["saved_refs"]
    count = lambda status: sum(r.status == status for r in refs)  # noqa: E731
    return OutputSummary(
        folder=f"{storage.RESULT_DIR.name}/{Path(result['output_dir']).name}",
        brief_file=Path(result["brief_path"]).name,
        saved=count("saved"),
        link_only=count("link_only"),
        failed=count("failed"),
        brief_markdown=result["brief_markdown"],
    )


def _to_response(thread_id: str, result: dict) -> AgentResponse:
    plan = result.get("reference_plan")
    common = {
        "thread_id": thread_id,
        "asset_type": result.get("asset_type"),
        "details": result.get("details", {}),
        "detail_labels": {i.key: i.label for i in CHECKLISTS.get(result.get("asset_type"), [])},
        # 지금까지의 처리 결과. 이미지 선택·계획 승인 화면에서도 이미지와 분석 내용을 계속 보여줘야 한다
        "analysis": result.get("analysis"),
        "guidelines": result.get("guidelines", []),
        "categories": result.get("final_categories", []),
        "exclude_terms": plan.exclude_terms if plan else [],
        "candidates": result.get("candidates", []),
        "rejected_candidates": result.get("rejected_candidates", []),
        "source_errors": result.get("source_errors", []),
        "selected_ids": result.get("selected_ids", []),
    }
    if "__interrupt__" in result:  # 사용자 답변이 필요해서 그래프가 멈춘 상태
        payload = result["__interrupt__"][0].value
        kind = payload["kind"]
        extra = {}
        if kind == "questions":
            extra = {"questions": payload["questions"]}
        elif kind == "confirm_categories":
            extra = {"proposed_categories": payload["categories"], "goal": payload["goal"]}
        elif kind == "confirm_brief":
            extra = {"brief_sections": payload["sections"], "auto_sections": payload["auto_sections"]}
        return AgentResponse(status="needs_input", kind=kind, **common, **extra)
    return AgentResponse(status="done", output=_output_summary(result), **common)


async def start(initial_state: dict) -> AgentResponse:
    """새 작업을 시작한다. 사용자의 입력이 필요하면 needs_input, 끝났으면 done 을 돌려준다."""
    thread_id = uuid.uuid4().hex
    result = await graph.ainvoke(initial_state, _config(thread_id))
    return _to_response(thread_id, result)


async def prepare_resume(body: AnswerRequest) -> dict:
    """이어서 실행할 수 있는 상태인지 확인하고, 그래프에 전달할 재개 값을 만든다.

    서버가 기다리는 답의 종류와 body 에 담긴 답의 종류가 맞아야 한다.
    스트리밍 응답은 시작한 뒤에는 상태 코드를 바꿀 수 없어서, 이 검사를 응답을 시작하기 전에 따로 한다.
    """
    snapshot = await graph.aget_state(_config(body.thread_id))
    if not snapshot.next:  # 없는 thread 이거나 이미 끝난 작업
        raise ThreadNotWaiting(body.thread_id)

    waiting_for = snapshot.tasks[0].interrupts[0].value["kind"]
    provided = {
        "confirm_categories": body.categories is not None,
        "select_images": body.selected_ids is not None,
        "confirm_brief": body.brief_sections is not None,
    }
    if waiting_for == "questions":
        if any(provided.values()):
            raise WrongAnswerKind(waiting_for)
    elif not provided[waiting_for] or sum(provided.values()) != 1:
        raise WrongAnswerKind(waiting_for)

    # LangGraph 는 빈 값({})으로 재개하면 '답이 없다'고 보고 같은 질문을 다시 하므로, 항상 비어 있지 않은 구조로 감싼다
    if waiting_for == "confirm_categories":
        return {"categories": body.categories, "per_category": body.per_category}
    if waiting_for == "select_images":
        return {"selected_ids": body.selected_ids, "save_unverified": body.save_unverified}
    if waiting_for == "confirm_brief":
        return {"sections": [s.model_dump() for s in body.brief_sections], "notes": body.brief_notes}
    return {"answers": body.answers}


async def resume(body: AnswerRequest) -> AgentResponse:
    """사용자의 답을 전달해 멈춘 작업을 이어서 실행한다."""
    value = await prepare_resume(body)
    result = await graph.ainvoke(Command(resume=value), _config(body.thread_id))
    return _to_response(body.thread_id, result)


async def _final_result(thread_id: str) -> dict:
    """실행이 멈추거나 끝난 뒤의 상태를 ainvoke 결과와 같은 모양으로 만든다."""
    snapshot = await graph.aget_state(_config(thread_id))
    result = dict(snapshot.values)
    interrupts = [i for task in snapshot.tasks for i in task.interrupts]
    if interrupts:  # 사용자 답변을 기다리는 중
        result["__interrupt__"] = interrupts
    return result


async def _stream(graph_input, thread_id: str) -> AsyncIterator[tuple[str, dict]]:
    """그래프를 실행하면서 진행 상황을 (이벤트 이름, 데이터)로 흘려보낸다.

    step  : 작업 단계가 시작됨 {label}
    detail: 단계 안의 세부 진행 {detail}
    result: 최종 응답 (사용자 입력이 필요하면 needs_input, 끝났으면 done)
    error : 실패 {message}
    """
    try:
        async for mode, chunk in graph.astream(graph_input, _config(thread_id), stream_mode=["tasks", "custom"]):
            if mode == "tasks" and "triggers" in chunk:  # 노드 시작 이벤트 (끝날 때의 이벤트에는 triggers 가 없다)
                label = NODE_LABELS.get(chunk["name"])
                if label:
                    yield "step", {"label": label}
            elif mode == "custom":
                yield "detail", chunk
        response = _to_response(thread_id, await _final_result(thread_id))
        yield "result", response.model_dump(mode="json")
    except Exception as e:  # 연결이 끊긴 경우(CancelledError)는 여기서 잡지 않고 그대로 중단된다
        logger.exception("에이전트 실행 실패")
        yield "error", {"message": f"서버에서 오류가 발생했어요 ({type(e).__name__})"}


def stream_start(initial_state: dict) -> AsyncIterator[tuple[str, dict]]:
    """새 작업을 시작하며 진행 상황을 흘려보낸다."""
    return _stream(initial_state, uuid.uuid4().hex)


def stream_resume(thread_id: str, value: dict) -> AsyncIterator[tuple[str, dict]]:
    """prepare_resume 이 만든 값으로 멈춘 작업을 이어서 실행하며 진행 상황을 흘려보낸다."""
    return _stream(Command(resume=value), thread_id)
