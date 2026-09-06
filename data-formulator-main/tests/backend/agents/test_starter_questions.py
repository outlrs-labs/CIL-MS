from types import SimpleNamespace

from data_formulator.agents.agent_starter_questions import StarterQuestionsAgent


class NullContentClient:
    model = "sarvam-105b"

    def get_completion(self, **_kwargs):
        message = SimpleNamespace(content=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_null_content_is_an_empty_optional_result():
    agent = StarterQuestionsAgent(NullContentClient())

    assert agent.run([{"name": "production", "columns": ["tonnes"]}]) == []
