"""에셋 종류별로 지시서 작성 전에 반드시 알아야 하는 항목(체크리스트)."""
from pydantic import BaseModel

UNDECIDED = "미정"  # 사용자가 답하지 않은 항목에 채우는 값 (지시서에서 AI 제안이 필요한 항목으로 취급)


class ChecklistItem(BaseModel):
    key: str  # 상태/API 에서 쓰는 식별자
    label: str  # 화면에 보여줄 이름
    hint: str  # 어떤 내용을 적으면 되는지 (LLM 추출 기준 + 사용자 안내 예시)
    question: str  # 입력에 없을 때 사용자에게 물을 질문


# 종류 코드 -> 화면에 보여줄 이름
TYPE_LABELS = {"character": "캐릭터", "background": "배경", "prop": "소품", "ui": "UI"}

CHECKLISTS: dict[str, list[ChecklistItem]] = {
    "character": [
        ChecklistItem(key="personality", label="성격", hint="예: 과묵하고 경계심이 많음",
                      question="캐릭터의 성격은 어떤가요?"),
        ChecklistItem(key="age_body", label="나이·체형", hint="예: 30대 중반, 마르고 키가 큼",
                      question="캐릭터의 나이와 체형은 어떤가요?"),
        ChecklistItem(key="outfit", label="의상", hint="예: 낡은 가죽 외투, 청동 랜턴",
                      question="캐릭터가 입고 있는 의상은 어떤가요?"),
        ChecklistItem(key="expression_pose", label="표정·포즈", hint="예: 무표정, 방패를 든 채 경계하는 자세",
                      question="기본 표정과 포즈는 어떤가요?"),
        ChecklistItem(key="weapon_items", label="무기·소지품", hint="예: 한손검, 허리춤의 물약 두 병",
                      question="들고 있는 무기나 소지품이 있나요?"),
    ],
    "background": [
        ChecklistItem(key="layout", label="레이아웃", hint="예: 중앙 광장을 둘러싼 원형 마을",
                      question="공간의 전체 레이아웃은 어떤가요?"),
        ChecklistItem(key="flow", label="동선", hint="예: 입구에서 광장을 거쳐 언덕으로 이어지는 길",
                      question="플레이어가 이동하는 동선은 어떻게 되나요?"),
        ChecklistItem(key="landmark", label="랜드마크", hint="예: 마을 중앙의 거대한 고목",
                      question="눈에 띄는 랜드마크가 있나요?"),
        ChecklistItem(key="depth", label="원경·근경 구분", hint="예: 원경은 안개 낀 산, 근경은 울타리와 풀",
                      question="원경과 근경은 어떻게 구분하나요?"),
    ],
    "prop": [
        ChecklistItem(key="scale", label="크기 기준(캐릭터 대비)", hint="예: 캐릭터 허리 높이, 한 손으로 들 수 있는 크기",
                      question="캐릭터와 비교한 크기는 어느 정도인가요?"),
        ChecklistItem(key="function", label="기능", hint="예: 불을 밝히는 조명, 열쇠로 여는 상자",
                      question="이 소품의 기능은 무엇인가요?"),
        ChecklistItem(key="interaction", label="상호작용 여부", hint="예: 조사하면 열림 / 장식용으로 상호작용 없음",
                      question="플레이어와 상호작용하나요?"),
    ],
    "ui": [
        ChecklistItem(key="states", label="상태별 디자인(기본·눌림·비활성)", hint="예: 기본 / 눌림 시 어두워짐 / 비활성은 회색조",
                      question="기본, 눌림, 비활성 상태는 각각 어떻게 보이나요?"),
        ChecklistItem(key="text_area", label="텍스트 영역", hint="예: 중앙 한 줄, 최대 8글자",
                      question="텍스트가 들어가는 영역은 어디이고 얼마나 되나요?"),
        ChecklistItem(key="resolution", label="해상도 대응", hint="예: 1920x1080 기준, 비율 변경 시 앵커 고정",
                      question="어떤 해상도와 화면 비율에 대응해야 하나요?"),
    ],
}
