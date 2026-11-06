import pytest


@pytest.fixture(autouse=True)
def _no_live_llm(monkeypatch) -> None:
    # Tests never call hosted Qwen; model routes return canned text unless a test patches them.
    monkeypatch.setenv("SITR_LLM", "mock")
