"""OpenAI 클라이언트와 모델 이름을 한곳에서 관리한다."""
import os
from functools import cache

from openai import AsyncOpenAI

INTAKE_MODEL = "gpt-4o-mini"  # 에셋 종류 분류, 필수 항목 추출용 (이미지 입력 지원)
ANALYSIS_MODEL = "gpt-4o-mini"  # 입력 분석용 (이미지 입력을 지원하는 모델)
ROUTER_MODEL = "gpt-4o-mini"  # 검색할 가이드 카테고리 선택용
REVIEW_MODEL = "gpt-4o-mini"  # 후보 이미지 적합성 검토용 (이미지 입력 지원)
WRITER_MODEL = os.getenv("WRITER_MODEL", "gpt-4o")  # 지시서 작성 계획·본문 작성용. 최종 산출물이라 정확도를 위해 더 강한 모델을 쓴다 (비용을 줄이려면 gpt-4o-mini)
PLANNER_MODEL = "gpt-4o-mini"  # 레퍼런스 카테고리 제안·보완용


@cache
def get_client() -> AsyncOpenAI:
    """처음 호출될 때 한 번만 만들고 재사용한다. (import 시점이 아니라 사용 시점에 API 키를 읽는다)"""
    return AsyncOpenAI()
