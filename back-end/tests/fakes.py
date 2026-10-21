from types import SimpleNamespace


class FakeClient:
    """OpenAI 클라이언트 대역. 호출 인자를 기록하고 미리 정한 결과를 돌려준다.

    parsed 가 dict 면 {response_format 클래스: 결과} 로 보고, 호출마다 알맞은 결과를 고른다.
    """

    def __init__(self, parsed):
        self.calls = []
        self._parsed = parsed
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kwargs):
        self.calls.append(kwargs)
        parsed = self._parsed[kwargs["response_format"]] if isinstance(self._parsed, dict) else self._parsed
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])
