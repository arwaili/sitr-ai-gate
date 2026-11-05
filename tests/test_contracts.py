from src.contracts import IngestionResult, PageText


def test_ingestion_contract_accepts_minimal_text() -> None:
    result = IngestionResult(
        document_id="demo-1",
        input_type="text",
        language="en",
        text="Public information",
        pages=[PageText(page=1, text="Public information")],
    )
    assert result.input_type == "text"
    assert result.warnings == []

