# /// script
# requires-python = ">=3.11"
# dependencies = ["transformers>=4.48,<6", "torch>=2.4,<3", "huggingface-hub>=0.27,<2"]
# ///
"""Build Sitr's synthetic Arabic-English evaluation dataset.

Every value is fictional. Labels come from templates, so offsets and expected actions are exact.
With --qwen, Qwen/Qwen2.5-1.5B-Instruct writes the benign carrier sentences used by low-risk
examples. It never writes sensitive values, and every sentence passes a safety filter.

Local, templates only:
    python data/generate_dataset.py
As a Hugging Face Job that publishes to the Hub:
    hf jobs uv run --flavor t4-small --secrets HF_TOKEN data/generate_dataset.py \
        --qwen --push <namespace>/sitr-synthetic-dlp
"""

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
ACTION_RISK = {"allow": "low", "redact": "medium", "private": "high", "block": "critical"}
LANGUAGES = ("en", "ar", "mixed")

FIRST_EN = ["Sara", "Omar", "Lina", "Yousef", "Maya", "Khalid", "Noor", "Adam", "Huda", "Faris"]
LAST_EN = ["Haddad", "Rahman", "Saleh", "Nasser", "Karim", "Mansour", "Aziz", "Hamdan"]
FIRST_AR = ["سارة", "عمر", "لينا", "يوسف", "مايا", "خالد", "نور", "آدم", "هدى", "فارس"]
LAST_AR = ["الحداد", "الرحمن", "الصالح", "الناصر", "الكريم", "المنصور", "العزيز", "الحمدان"]

STATIC_CARRIERS = {
    "en": [
        "Discover the new seasonal menu at our cafe by the Corniche.",
        "Join us this weekend for a family day at the public park.",
        "Our bookstore is hosting a reading hour for children every morning.",
        "Celebrate the desert spring with a guided walk through the dunes.",
        "The new metro line makes it easier to reach the old market.",
        "Try our fresh karak tea, now served all day.",
        "Explore traditional crafts at the heritage village this month.",
        "Our gym now offers early morning classes for beginners.",
        "Visit the museum to see an exhibition of pearl diving history.",
        "Bring your friends to taste our new saffron desserts.",
        "The community garden welcomes volunteers every Friday.",
        "Learn the basics of photography in our free online workshop.",
        "Enjoy a calm evening by the sea with live oud music.",
        "Our bakery now offers gluten free bread every day.",
        "Cheer for your favorite team at the open air fan zone.",
    ],
    "ar": [
        "اكتشف قائمة الموسم الجديدة في مقهانا على الكورنيش.",
        "انضموا إلينا في يوم عائلي ممتع في الحديقة العامة.",
        "تستضيف مكتبتنا ساعة قراءة للأطفال كل صباح.",
        "استمتع بنزهة إرشادية بين الكثبان الرملية في الربيع.",
        "يسهّل خط المترو الجديد الوصول إلى السوق القديم.",
        "جرّب شاي الكرك الطازج المتوفر طوال اليوم.",
        "تعرّف على الحرف التقليدية في القرية التراثية هذا الشهر.",
        "يقدّم النادي الرياضي حصصًا صباحية للمبتدئين.",
        "زر المتحف لمشاهدة معرض عن تاريخ الغوص على اللؤلؤ.",
        "أحضر أصدقاءك لتذوق حلويات الزعفران الجديدة.",
        "ترحب الحديقة المجتمعية بالمتطوعين كل جمعة.",
        "تعلّم أساسيات التصوير في ورشتنا المجانية عبر الإنترنت.",
        "استمتع بأمسية هادئة على البحر مع عزف العود.",
        "يقدّم مخبزنا خبزًا خاليًا من الغلوتين كل يوم.",
        "شجّع فريقك المفضل في منطقة المشجعين المفتوحة.",
    ],
}

TOPICS = {
    "en": [
        "a cafe marketing campaign in Doha",
        "a family weekend event at a public park",
        "a new public transport line",
        "a heritage and crafts festival",
        "a children's reading program at a library",
        "a seasonal sale at a clothing store",
        "a sports fan zone",
        "a free online workshop for beginners",
        "a desert camping trip",
        "a new bakery product",
    ],
    "ar": [
        "حملة تسويقية لمقهى في الدوحة",
        "فعالية عائلية في حديقة عامة",
        "خط جديد للنقل العام",
        "مهرجان التراث والحرف اليدوية",
        "برنامج قراءة للأطفال في مكتبة",
        "تخفيضات موسمية في متجر ملابس",
        "منطقة لتجمع مشجعي كرة القدم",
        "ورشة مجانية عبر الإنترنت للمبتدئين",
        "رحلة تخييم في الصحراء",
        "منتج جديد في مخبز",
    ],
}
INSTRUCTIONS = {
    "en": "Write one short, friendly public marketing sentence in English about {topic}. "
    "Do not mention any person, name, number, price, date, email, or website.",
    "ar": "اكتب جملة تسويقية عامة قصيرة باللغة العربية فقط عن {topic}. "
    "لا تذكر أي شخص أو اسم أو رقم أو سعر أو تاريخ أو بريد إلكتروني أو موقع.",
}

# Templates per (action, language): (scenario, template). {KEY} slots become labeled entities,
# with _EN/_AR suffixes dropped from the type; {CARRIER_EN}/{CARRIER_AR} insert carrier sentences.
TEMPLATES = {
    ("allow", "en"): [
        ("public_prompt", "{CARRIER_EN}"),
        ("public_prompt", "Improve this marketing sentence: {CARRIER_EN}"),
        ("safe_code", "def add(a, b):\n    return a + b\n"),
        ("safe_code", "names = [line.strip() for line in open(path)]\nprint(len(names))\n"),
        (
            "documentation",
            "API keys look like sk-XXXXXXXXXXXX. Store yours in an environment variable.",
        ),
    ],
    ("allow", "ar"): [
        ("public_prompt", "{CARRIER_AR}"),
        ("public_prompt", "حسّن هذه الجملة التسويقية: {CARRIER_AR}"),
    ],
    ("allow", "mixed"): [
        ("public_prompt", "Translate to English: {CARRIER_AR}"),
        ("public_prompt", "ترجم إلى العربية: {CARRIER_EN}"),
        ("safe_code", "# دالة لجمع رقمين\ndef add(a, b):\n    return a + b\n"),
        ("documentation", "تبدو المفاتيح بهذا الشكل sk-XXXXXXXXXXXX، احفظها في متغيرات البيئة."),
    ],
    ("redact", "en"): [
        ("cv", "Please summarize this CV. Name: {PERSON_EN}. Email: {EMAIL}. Phone: {PHONE}."),
        ("contact", "Draft a welcome note for {PERSON_EN} ({EMAIL}), reachable on {PHONE}."),
        ("email_reply", "Rewrite this politely: Hi {PERSON_EN}, I will send the files to {EMAIL}."),
    ],
    ("redact", "ar"): [
        ("cv", "لخّص هذه السيرة الذاتية. الاسم: {PERSON_AR}. البريد: {EMAIL}. الهاتف: {PHONE}."),
        ("contact", "اكتب رسالة ترحيب إلى {PERSON_AR} على البريد {EMAIL} أو الهاتف {PHONE}."),
    ],
    ("redact", "mixed"): [
        ("cv", "Summarize this CV: الاسم {PERSON_AR}، email {EMAIL}، phone {PHONE}."),
        ("contact", "أرسل تذكيرًا إلى {PERSON_EN} at {EMAIL}."),
    ],
    ("private", "en"): [
        (
            "employment_contract",
            "Summarize this employment contract. Employee: {PERSON_EN}. "
            "Salary: {SALARY_EN}. QID: {QATAR_ID}.",
        ),
        (
            "performance_evaluation",
            "Improve this performance evaluation for {PERSON_EN}: missed two deadlines.",
        ),
        ("payroll", "Check this payroll transfer to {PERSON_EN}, IBAN {IBAN}, for {SALARY_EN}."),
    ],
    ("private", "ar"): [
        (
            "employment_contract",
            "لخّص عقد العمل التالي. الموظف: {PERSON_AR}. الراتب: {SALARY_AR}. "
            "الرقم الشخصي: {QATAR_ID}.",
        ),
        ("performance_evaluation", "حسّن صياغة تقييم الأداء للموظف {PERSON_AR}: تأخر في مشروعين."),
        ("payroll", "راجع تحويل الراتب إلى {PERSON_AR} على الحساب {IBAN} بمبلغ {SALARY_AR}."),
    ],
    ("private", "mixed"): [
        (
            "employment_contract",
            "عقد عمل / Employment contract: Employee {PERSON_AR}, Salary {SALARY_EN}, "
            "QID {QATAR_ID}.",
        ),
        ("performance_evaluation", "Employee evaluation تقييم الموظف {PERSON_EN}: يحتاج تدريبًا."),
        ("payroll", "Payroll تحويل الراتب: IBAN {IBAN}، المبلغ {SALARY_AR}."),
    ],
    ("block", "en"): [
        (
            "api_key_code",
            'import requests\n\nAPI_KEY = "{API_KEY}"\n'
            'requests.get(URL, headers={"Authorization": "Bearer " + API_KEY})\n',
        ),
        ("password_config", 'DB_USER = "app"\nDB_PASSWORD = "{PASSWORD}"\n'),
        ("database_url", 'DATABASE_URL = "{DATABASE_URL}"\nengine = create_engine(DATABASE_URL)\n'),
    ],
    ("block", "ar"): [
        ("api_key_message", "هذا مفتاح الوصول الخاص بنا: {API_KEY} لماذا لا يعمل الطلب؟"),
        ("password_message", "كلمة المرور لقاعدة البيانات هي {PASSWORD}، ساعدني في إعداد الاتصال."),
    ],
    ("block", "mixed"): [
        ("api_key_code", '# مفتاح الإنتاج\nSERVICE_KEY = "{API_KEY}"\nprint("جاهز")\n'),
        ("database_url", "اربط التطبيق بقاعدة البيانات {DATABASE_URL} من فضلك."),
    ],
}

_UNSAFE_CARRIER = re.compile(
    r"[0-9٠-٩۰-۹]|@|https?://|www\.|sk-|password|كلمة المرور", re.IGNORECASE
)
_CONFIDENTIAL = ("contract", "salary", "evaluation", "confidential", "عقد", "راتب", "تقييم", "سري")


def is_safe_carrier(text: str, language: str) -> bool:
    """Accept only benign single-script sentences with no numbers, contacts, or business terms."""
    if not 15 <= len(text) <= 200 or _UNSAFE_CARRIER.search(text):
        return False
    if any(term in text.lower() for term in _CONFIDENTIAL):
        return False
    has_arabic = bool(re.search(r"[؀-ۿ]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    return has_arabic and not has_latin if language == "ar" else has_latin and not has_arabic


def fake_values(rng: random.Random) -> dict[str, str]:
    n = rng.randrange(100)
    return {
        "PERSON_EN": f"{rng.choice(FIRST_EN)} {rng.choice(LAST_EN)}",
        "PERSON_AR": f"{rng.choice(FIRST_AR)} {rng.choice(LAST_AR)}",
        "EMAIL": f"{rng.choice(['applicant', 'staff', 'hr.contact', 'employee'])}{n}@example.com",
        "PHONE": f"+974 5555 01{n:02d}",
        "QATAR_ID": f"2840000{rng.randrange(10_000):04d}",
        "IBAN": f"QA00SYNT{rng.randrange(10**21):021d}",
        "SALARY_EN": f"{rng.randrange(8, 60) * 1000:,} QAR",
        "SALARY_AR": f"{rng.randrange(8, 60) * 1000} ريال",
        "API_KEY": "sk-synthetic-" + "".join(rng.choices("0123456789abcdef", k=24)),
        "PASSWORD": f"Synthetic-Pass-{n:02d}",
        "DATABASE_URL": f"postgresql://app:synthetic{n}@db.example.internal:5432/hr",
    }


def render(
    template: str, values: dict[str, str], carriers: dict[str, str]
) -> tuple[str, list[dict]]:
    """Fill a template, recording each inserted value with exact character offsets."""
    text, entities = "", []
    for index, part in enumerate(re.split(r"\{([A-Z_]+)\}", template)):
        if index % 2 == 0:
            text += part
        elif part.startswith("CARRIER_"):
            text += carriers[part.removeprefix("CARRIER_").lower()]
        else:
            entities.append(
                {
                    "entity_type": part.removesuffix("_EN").removesuffix("_AR"),
                    "value": values[part],
                    "start": len(text),
                    "end": len(text) + len(values[part]),
                }
            )
            text += values[part]
    return text, entities


def build_examples(
    per_class: int = 75, seed: int = 7, carriers: dict[str, list[str]] | None = None
) -> list[dict]:
    """Return per_class unique examples per action, split evenly across languages, 20% test."""
    rng = random.Random(seed)
    carriers = carriers or STATIC_CARRIERS
    qwen_written = set(carriers["en"] + carriers["ar"]) - set(
        STATIC_CARRIERS["en"] + STATIC_CARRIERS["ar"]
    )
    examples: list[dict] = []
    seen: set[str] = set()
    for action, risk in ACTION_RISK.items():
        for lang_index, language in enumerate(LANGUAGES):
            target = per_class // 3 + (lang_index < per_class % 3)
            count = attempts = 0
            while count < target:
                attempts += 1
                if attempts > target * 50:
                    raise ValueError(f"Not enough unique {action}/{language} examples.")
                scenario, template = rng.choice(TEMPLATES[(action, language)])
                chosen = {key: rng.choice(pool) for key, pool in carriers.items()}
                text, entities = render(template, fake_values(rng), chosen)
                if text in seen:
                    continue
                seen.add(text)
                used_qwen = any(c in text for c in chosen.values() if c in qwen_written)
                examples.append(
                    {
                        "id": f"sitr-{len(examples) + 1:04d}",
                        "language": language,
                        "scenario": scenario,
                        "text": text,
                        "entities": entities,
                        "expected_risk": risk,
                        "expected_action": action,
                        "carrier_source": "qwen" if used_qwen else "static",
                        "split": "test" if count % 5 == 4 else "dev",
                    }
                )
                count += 1
    return examples


def generate_carriers(per_language: int, seed: int) -> dict[str, list[str]]:
    """Ask Qwen for benign carrier sentences; top up from the static list if it falls short."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype="auto").to(device)
    carriers: dict[str, list[str]] = {"en": [], "ar": []}
    for language, instruction in INSTRUCTIONS.items():
        for _ in range(10):
            if len(carriers[language]) >= per_language:
                break
            prompts = [
                tokenizer.apply_chat_template(
                    [{"role": "user", "content": instruction.format(topic=topic)}],
                    tokenize=False,
                    add_generation_prompt=True,
                )
                for topic in TOPICS[language]
                for _ in range(2)
            ]
            batch = tokenizer(prompts, return_tensors="pt", padding=True).to(device)
            output = model.generate(
                **batch, max_new_tokens=60, do_sample=True, temperature=0.9, top_p=0.95
            )
            replies = tokenizer.batch_decode(
                output[:, batch["input_ids"].shape[1] :], skip_special_tokens=True
            )
            for reply in replies:
                line = reply.strip().split("\n")[0].strip(" \"'“”«»")
                if is_safe_carrier(line, language) and line not in carriers[language]:
                    carriers[language].append(line)
        print(f"Qwen wrote {len(carriers[language])} accepted {language} carriers.")
        carriers[language] = (carriers[language] + STATIC_CARRIERS[language])[:per_language]
    return carriers


def dataset_card(examples: list[dict]) -> str:
    counts = Counter((e["split"], e["expected_action"], e["language"]) for e in examples)
    rows = "\n".join(
        f"| {split} | {action} | {language} | {n} |"
        for (split, action, language), n in sorted(counts.items())
    )
    qwen = sum(e["carrier_source"] == "qwen" for e in examples)
    return f"""---
license: apache-2.0
language: [ar, en]
pretty_name: Sitr Synthetic DLP
tags: [synthetic, pii, data-loss-prevention, arabic, qatar]
task_categories: [token-classification, text-classification]
configs:
- config_name: default
  data_files:
  - split: dev
    path: data/dev.jsonl
  - split: test
    path: data/test.jsonl
---

# Sitr Synthetic DLP

Fully synthetic Arabic, English, and mixed-language prompts for evaluating Sitr AI Gate, a
security gateway that decides whether employee input to an AI model is allowed, redacted,
routed privately, or blocked. Built for the Qai x Hugging Face Hackathon in Qatar.

**Every name, email, phone number, ID, IBAN, salary, and credential is fictional.** Emails use
`example.com`, IBANs use the invalid check digits `QA00`, and keys start with `sk-synthetic-`.

## How it was made

Sensitive values and labels come from templates, so entity offsets and expected actions are
exact. `{MODEL_ID}` wrote the benign carrier sentences used by low-risk prompts ({qwen} examples)
inside a Hugging Face Job. Each sentence passed a filter that rejects digits, contacts,
credentials, and confidential business terms.

## Fields

`id`, `language` (ar, en, mixed), `scenario`, `text`, `entities` (entity_type, value, start,
end as Python string offsets), `expected_risk`, `expected_action`, `carrier_source`, `split`.

## Splits

Use `dev` for development and `test` only for final measured results.

| Split | Action | Language | Examples |
|---|---|---|---:|
{rows}

## Limitations

Template-based examples are less varied than real documents, so results on this dataset
overstate real-world accuracy. Qwen sentences were instructed not to mention people, but names
in them are not checked automatically. Sitr is a decision-support prototype, not a compliance
guarantee.
"""


def push(repo_id: str, examples: list[dict]) -> None:
    from huggingface_hub import CommitOperationAdd, HfApi

    api = HfApi()
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True)
    operations = [
        CommitOperationAdd(
            f"data/{split}.jsonl",
            "".join(
                json.dumps(e, ensure_ascii=False) + "\n" for e in examples if e["split"] == split
            ).encode(),
        )
        for split in ("dev", "test")
    ]
    operations.append(CommitOperationAdd("README.md", dataset_card(examples).encode()))
    api.create_commit(
        repo_id, operations, commit_message="Generate Sitr synthetic dataset", repo_type="dataset"
    )
    print(f"Published https://huggingface.co/datasets/{repo_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--per-class", type=int, default=75)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--qwen", action="store_true", help="Generate carriers with Qwen.")
    parser.add_argument("--push", metavar="REPO_ID", help="Publish to this Hub dataset repo.")
    parser.add_argument("--output", default="data/synthetic_examples.json")
    args = parser.parse_args()

    carriers = generate_carriers(40, args.seed) if args.qwen else None
    examples = build_examples(args.per_class, args.seed, carriers)
    dev = [e for e in examples if e["split"] == "dev"]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(dev, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(dev)} dev examples to {args.output}; {len(examples) - len(dev)} held out.")
    if args.push:
        push(args.push, examples)


if __name__ == "__main__":
    main()
