import pytest

from src.deterministic import detect_deterministic
from src.ingestion import ingest


def test_ingest_preserves_arabic_text_and_detects_language() -> None:
    result = ingest(text="عقد عمل for Sara")
    assert result.text == "عقد عمل for Sara"
    assert result.language == "mixed"


def test_ingest_reads_code_file(tmp_path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("x = 1\n", encoding="utf-8")
    result = ingest(file_path=str(path))
    assert result.input_type == "code"
    assert result.filename == "sample.py"


@pytest.mark.parametrize("text", [None, "", "   \n"])
def test_ingest_rejects_empty_input(text) -> None:
    with pytest.raises(ValueError):
        ingest(text=text)


def test_ingest_rejects_binary_file(tmp_path) -> None:
    path = tmp_path / "corrupted.pdf"
    path.write_bytes(b"\xff\xfe\x00broken")
    with pytest.raises(ValueError):
        ingest(file_path=str(path))


def test_deterministic_offsets_select_exact_values() -> None:
    text = "key = sk-synthetic-0000 and mail test@example.com twice test@example.com"
    entities = detect_deterministic(text)
    assert [e.entity_type for e in entities] == ["API_KEY", "EMAIL", "EMAIL"]
    assert all(text[e.start : e.end] == e.value for e in entities)
    assert entities[0].severity == "critical"


def test_deterministic_ignores_clean_text() -> None:
    assert detect_deterministic("A risk-free public announcement") == []
