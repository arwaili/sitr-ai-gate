---
title: Sitr AI Gate
emoji: 🛡️
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 6.31.0
python_version: "3.11"
app_file: app.py
pinned: false
license: apache-2.0
short_description: Arabic-English AI gateway that guards sensitive data
models:
  - OpenMed/privacy-filter-multilingual-v2
  - Horizon-Labs/multilingual-zeroshot-small
  - Qwen/Qwen2.5-1.5B-Instruct
datasets:
  - arwaili/sitr-synthetic-dlp
---

# Sitr AI Gate · سِتر

Sitr inspects employee prompts and files before they reach an AI model, then allows, redacts,
routes privately, or blocks them. Built for the Qai x Hugging Face Hackathon in Qatar.

- Rules find secrets, IDs, IBANs and salaries in Arabic and English.
- `OpenMed/privacy-filter-multilingual-v2` finds names and personal data.
- `Horizon-Labs/multilingual-zeroshot-small` reads what the text is about.
- `Qwen/Qwen2.5-1.5B-Instruct` answers allowed and redacted requests through Hugging Face
  Inference Providers, and private requests inside this Space.

**Use synthetic data only.** This is a security decision-support prototype; the private route is
a demonstration, not an isolated environment. The models load when the Space starts: wait until
the header says `ready` before the first request.
