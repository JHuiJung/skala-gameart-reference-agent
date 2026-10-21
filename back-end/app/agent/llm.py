"""OpenAI 클라이언트와 모델 이름을 한곳에서 관리한다."""
from functools import cache

from openai import AsyncOpenAI

ANALYSIS_MODEL = "gpt-4o-mini"  # 입력 분석용 (이미지 입력을 지원하는 모델)
ROUTER_MODEL = "gpt-4o-mini"  # 검색할 가이드 카테고리 선택용
PLANNER_MODEL = "gpt-4o-mini"  # 웹 이미지 검색 계획 생성용


@cache
def get_client() -> AsyncOpenAI:
    """처음 호출될 때 한 번만 만들고 재사용한다. (import 시점이 아니라 사용 시점에 API 키를 읽는다)"""
    return AsyncOpenAI()
