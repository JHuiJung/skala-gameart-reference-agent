"""기본으로 사용하는 이미지 검색 출처. 출처를 추가·제거하려면 이 목록만 바꾸면 된다."""
from app.agent.sources.openverse import OpenverseSource
from app.agent.sources.wikimedia import WikimediaSource

DEFAULT_SOURCES = [OpenverseSource(), WikimediaSource()]  # 둘 다 API 키가 필요 없다
