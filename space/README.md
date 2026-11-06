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

Ask Sitr "Can I share this with an AI assistant?" with text or a file. It answers yes or no,
says what it found, and gives you the safe version: redacted text to copy, a redacted PDF for a
PDF, or a redacted text file for other files. Behind it, the pipeline allows, redacts, routes
privately, or blocks. Built for the Qai x Hugging Face Hackathon in Qatar. English and Arabic,
light and dark.

- Rules find secrets, IDs, IBANs and salaries in Arabic and English.
- `OpenMed/privacy-filter-multilingual-v2` finds names and personal data.
- `Horizon-Labs/multilingual-zeroshot-small` reads what the text is about.
- `Qwen/Qwen2.5-1.5B-Instruct` is the pipeline's model: allowed and redacted requests go
  through Hugging Face Inference Providers, private requests stay inside this Space. The chat
  checks every message first, inside this Space. Only short small talk with nothing sensitive in it
  ("hello", "what can you do?") is then answered by Qwen; files, content pasted under a question,
  and anything with findings get Sitr's verdict and are not sent to Qwen.

**Use synthetic data only.** This is a security decision-support prototype; the private route is
a demonstration, not an isolated environment. The models load when the Space starts: wait until
the bottom of the sidebar says `Privacy detector ready` before the first request.
