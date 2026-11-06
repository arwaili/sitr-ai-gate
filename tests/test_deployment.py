"""Guards on the files Hugging Face Spaces reads (space/README.md and space/requirements.txt)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
README = (ROOT / "space" / "README.md").read_text(encoding="utf-8")
RUNTIME = (ROOT / "space" / "requirements.txt").read_text(encoding="utf-8")
DEV = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
LOCKED_MODELS = (
    "OpenMed/privacy-filter-multilingual-v2",
    "Horizon-Labs/multilingual-zeroshot-small",
    "Qwen/Qwen2.5-1.5B-Instruct",
)


def front_matter() -> str:
    """The YAML block Spaces reads, without parsing it: PyYAML is not a dependency."""
    match = re.match(r"^---\n(.*?)\n---\n", README, re.DOTALL)
    assert match, "README must open with the Space's YAML block"
    return match.group(1)


@pytest.mark.parametrize(
    "line", ["title: Sitr AI Gate", "sdk: gradio", "app_file: app.py", "pinned: false"]
)
def test_space_metadata_declares_the_entry_point(line: str) -> None:
    assert line in front_matter().splitlines()


def test_space_sdk_version_is_a_release_the_pin_allows() -> None:
    version = re.search(r"^sdk_version: (\d+)\.\d+\.\d+$", front_matter(), re.MULTILINE)
    assert version, "sdk_version must be an exact x.y.z release"
    assert 5 <= int(version.group(1)) < 7, "outside the gradio>=5,<7 pin in requirements.txt"


def test_space_colors_are_names_spaces_accepts() -> None:
    allowed = {"red", "yellow", "green", "blue", "indigo", "purple", "pink", "gray"}
    for key in ("colorFrom", "colorTo"):
        found = re.search(rf"^{key}: (\w+)$", front_matter(), re.MULTILINE)
        assert found and found.group(1) in allowed, f"{key} must be one of {sorted(allowed)}"


def test_hugging_face_usage_stays_visible_on_the_space_page() -> None:
    # "Use of Hugging Face" is a judging criterion, so the Space page must link all of them.
    metadata = front_matter()
    for model in LOCKED_MODELS:
        assert f"  - {model}" in metadata
    assert "  - arwaili/sitr-synthetic-dlp" in metadata


def test_the_space_does_not_install_the_test_tools() -> None:
    for tool in ("pytest", "ruff"):
        assert tool not in RUNTIME, f"{tool} belongs in requirements-dev.txt, not the Space"
        assert tool in DEV


def test_dev_requirements_include_everything_the_space_runs() -> None:
    assert "-r requirements.txt" in DEV


def test_runtime_requirements_ask_for_cpu_only_torch() -> None:
    # The Space is CPU basic; the PyPI linux wheel drags in a CUDA build it cannot use.
    assert "--extra-index-url https://download.pytorch.org/whl/cpu" in RUNTIME
    assert "torch" in RUNTIME


def test_the_example_environment_file_holds_no_value_for_the_secret() -> None:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith("HF_TOKEN"):
            assert line.strip() == "HF_TOKEN=", "the token goes in Space secrets, never in a file"
