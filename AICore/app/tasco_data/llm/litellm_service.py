from app.utils.llm_partern import LLM

# Giới hạn output cao để không cắt cụt JSON response khi batch nhiều POI (Phase 2/3).
_PIPELINE_MAX_TOKENS = 16000


class LiteLLMService:
    """Wrapper mỏng cho pipeline offline, dùng chung gateway LLM với phía API."""

    def __init__(self, model: str = "openai/gpt-4o", temperature: float = 0):
        self._llm = LLM(model=model, temperature=temperature, max_tokens=_PIPELINE_MAX_TOKENS)

    def complete_json(self, system_prompt: str, user_payload: dict) -> dict:
        return self._llm.complete_json(system_prompt, user_payload)
