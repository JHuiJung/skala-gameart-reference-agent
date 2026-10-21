"""노드가 실행 도중 '세부 진행 상황'을 화면에 알리는 도구."""
from langgraph.config import get_stream_writer


def emit_detail(text: str) -> None:
    """스트리밍 중이면 세부 진행 메시지를 보낸다. (예: '겨울 의상 검색 완료 (2/5)')

    그래프 밖에서 노드를 직접 호출한 경우(단위 테스트 등)에는 아무 일도 하지 않는다.
    """
    try:
        get_stream_writer()({"detail": text})
    except RuntimeError:
        pass
