import pytest

from src.contracts import FinalResponse
from src.orchestrator import inspect_and_process

CV = "Curriculum vitae: Mariam, test.applicant@example.com, +974 5555 0100"
CONTRACT = "عقد عمل: الراتب 15000 ريال، الرقم الشخصي 28400000000"
LEAKY_CODE = 'API_KEY = "sk-synthetic-000000000000"\nprint(API_KEY)'


@pytest.mark.parametrize(
    ("scenario", "text", "risk", "action"),
    [
        ("T1", "Write a public marketing slogan for a Doha cafe.", "low", "allow"),
        ("T2", CV, "medium", "redact"),
        ("T3", CONTRACT, "high", "private"),
        ("T4", LEAKY_CODE, "critical", "block"),
        ("T5", "def add(a, b):\n    return a + b\n", "low", "allow"),
        ("T6", "Employee evaluation تقييم الموظف: needs coaching", "high", "private"),
    ],
)
def test_shared_matrix(scenario: str, text: str, risk: str, action: str) -> None:
    result = inspect_and_process(text=text)
    FinalResponse.model_validate(result)
    assert result["analysis"]["risk_level"] == risk, scenario
    assert result["action_taken"] == action, scenario


@pytest.mark.xfail(reason="T7 needs the real secret scanner, the mock flags any key-shaped text")
def test_t7_documentation_key_is_not_critical() -> None:
    result = inspect_and_process(text="Keys look like sk-XXXXXXXXXXXX in the documentation.")
    assert result["analysis"]["risk_level"] != "critical"


@pytest.mark.parametrize("text", [None, "", "  \n"])
def test_t8_empty_input_is_an_explained_error(text) -> None:
    result = inspect_and_process(text=text)
    FinalResponse.model_validate(result)
    assert result["status"] == "error"
    assert result["model_response"] is None
    assert result["user_message"]


def test_t8_corrupted_file_is_an_explained_error(tmp_path) -> None:
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"\xff\xfe\x00broken")
    result = inspect_and_process(file_path=str(path))
    assert result["status"] == "error"
    assert "\xff" not in result["user_message"]


def test_blocked_secret_never_reaches_a_model() -> None:
    result = inspect_and_process(text=LEAKY_CODE)
    assert result["status"] == "blocked"
    assert result["model_response"] is None
    assert "sk-synthetic" not in result["user_message"]
    assert "sk-synthetic" not in result["redaction"]["safe_text"]


def test_redaction_is_stable_for_repeated_values() -> None:
    text = "a@example.com, b@example.com, a@example.com"
    redaction = inspect_and_process(text=text)["redaction"]
    assert redaction["safe_text"] == "[EMAIL_1], [EMAIL_2], [EMAIL_1]"
    assert [item["original_value"] for item in redaction["replacements"]] == [
        "a@example.com",
        "b@example.com",
    ]


def test_entity_offsets_select_exact_values() -> None:
    result = inspect_and_process(text=CONTRACT)
    assert result["analysis"]["entities"]
    for entity in result["analysis"]["entities"]:
        assert CONTRACT[entity["start"] : entity["end"]] == entity["value"]
