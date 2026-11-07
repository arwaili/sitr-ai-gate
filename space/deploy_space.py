"""Publish the app to a Hugging Face Space: python space/deploy_space.py [--public]

Uploads app.py, ui_text.py, src/, examples/, the screenshots in docs/images/ (the Space page
shows them), and this folder's README.md and requirements.txt. Tests, data and other docs stay
on GitHub. The Space starts private unless --public is given.

After the first deploy, add an HF_TOKEN secret in the Space settings (Settings > Variables and
secrets) so the allow and redact routes can call hosted Qwen.
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPACE_FILES = {"README.md": "space/README.md", "requirements.txt": "space/requirements.txt"}


def files_to_upload() -> dict[str, Path]:
    files = {"app.py": ROOT / "app.py", "ui_text.py": ROOT / "ui_text.py"}
    files |= {f"src/{p.name}": p for p in sorted((ROOT / "src").glob("*.py"))}
    files |= {
        f"examples/{p.name}": p
        for p in sorted((ROOT / "examples").iterdir())
        if p.suffix in {".pdf", ".py", ".txt"} and p.name != "make_examples.py"
    }
    files |= {f"docs/images/{p.name}": p for p in sorted((ROOT / "docs/images").glob("*.png"))}
    files |= {target: ROOT / source for target, source in SPACE_FILES.items()}
    return files


def main() -> None:
    from huggingface_hub import CommitOperationAdd, HfApi

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", default="arwaili/sitr-ai-gate")
    parser.add_argument("--public", action="store_true", help="Make the Space public.")
    args = parser.parse_args()

    api = HfApi()
    api.create_repo(
        args.repo, repo_type="space", space_sdk="gradio", private=not args.public, exist_ok=True
    )
    if args.public:
        api.update_repo_settings(args.repo, repo_type="space", private=False)
    operations = [
        CommitOperationAdd(target, str(path)) for target, path in files_to_upload().items()
    ]
    api.create_commit(
        args.repo, operations, commit_message="Deploy Sitr AI Gate", repo_type="space"
    )
    print(f"Deployed https://huggingface.co/spaces/{args.repo} ({len(operations)} files)")


if __name__ == "__main__":
    main()
