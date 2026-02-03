import json
import os
from dataclasses import dataclass
from typing import Optional
from urllib import request


class AiProvider:
    def ask(self, question: str, context: Optional[str]) -> str:
        raise NotImplementedError


class StubAiProvider(AiProvider):
    def ask(self, question: str, context: Optional[str]) -> str:
        del question, context
        return (
            "AI is not configured. Set AI_HTTP_ENDPOINT or replace the provider."
        )


@dataclass
class HttpAiProvider(AiProvider):
    endpoint: str
    timeout: int = 10

    def ask(self, question: str, context: Optional[str]) -> str:
        payload = {"question": question, "context": context}
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as resp:
            content = resp.read().decode("utf-8")
        try:
            obj = json.loads(content)
            answer = obj.get("answer")
            if isinstance(answer, str) and answer:
                return answer
        except Exception:
            pass
        return content.strip() or "AI endpoint returned empty response."


def build_ai_provider() -> AiProvider:
    endpoint = os.getenv("AI_HTTP_ENDPOINT")
    if endpoint:
        return HttpAiProvider(endpoint=endpoint)
    return StubAiProvider()
