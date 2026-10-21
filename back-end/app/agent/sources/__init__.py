"""기본으로 사용하는 이미지 검색 출처. 출처를 추가·제거하려면 이 목록만 바꾸면 된다."""
from app.agent.sources.openverse import OpenverseSource
from app.agent.sources.tavily import TavilySource
from app.agent.sources.wikimedia import WikimediaSource

# Openverse, Wikimedia: 키 없이 사용, 라이선스 정보 있음
# Tavily: 키 필요(.env 의 TAVILY_API_KEY), 웹 전체 검색, 라이선스 정보 없음
DEFAULT_SOURCES = [OpenverseSource(), WikimediaSource(), TavilySource()]
