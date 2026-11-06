"""Every word the interface shows, in English and Arabic. The app shows one language at a time."""

from src.orchestrator import DETECTOR_DOWN_MESSAGE

TEXT = {
    "en": {
        "switch": "العربية",
        "product": "Sitr AI Gate",
        "purpose": "Checks what employees send to AI before it leaves: it lets safe text through, "
        "hides personal data, keeps confidential work in-house, and stops secrets.",
        "detector": "Privacy detector",
        "classifier": "Risk classifier",
        "states": {"ready": "ready", "not loaded": "loading", "unavailable": "unavailable",
                   "disabled": "off"},
        "tab_inspect": "Chat",
        "new_chat": "New chat",
        "next": {
            "allow": ("Safe to send",
                      "Nothing sensitive was found. You can paste this into ChatGPT, Claude or "
                      "any AI assistant as it is."),
            "redact": ("Send this version instead",
                       "Personal data is replaced with placeholders. Give the AI assistant this "
                       "version, or the redacted file below, not the original."),
            "private": ("Don't send this to ChatGPT or Claude",
                        "This is confidential work. Use your organization's approved internal AI "
                        "tool instead. If your policy allows outside tools, send only this "
                        "version, with the sensitive details removed."),
            "block": ("Don't send this",
                      "It contains a secret such as a password or API key, and secrets must never "
                      "go into an AI assistant. If you need help with it, send this version, "
                      "where the secret is replaced. If the secret was shared anywhere, ask for "
                      "it to be changed."),
            "error": ("Nothing to send", "Sitr could not read this. Try pasting the text instead."),
        },
        "answer": {
            "allow": ("Safe", "Yes, you can send it to {dest}.",
                      "I didn't find anything personal, confidential or secret in it."),
            "redact": ("Needs changes", "Not as it is. Send this version to {dest} instead.",
                       "It has {things}. I replaced them with placeholders such as [EMAIL_1], so "
                       "this version is safe to share."),
            "private": ("Keep private", "No, keep this one inside the company.",
                        "It's confidential work{with_things}. Use your organization's approved "
                        "internal AI tool for it."),
            "block": ("Don't send", "No, don't send this to {dest}.",
                      "It contains {things}, and secrets should never go into an AI assistant. "
                      "If the secret was shared anywhere, have it changed."),
            "error": ("Couldn't read", "I couldn't read that.", "{reason} Try pasting the text."),
        },
        "default_dest": "an AI assistant",
        "with_things_prefix": ": ",
        "and": " and ",
        "things": {
            "PERSON": "a name", "EMAIL": "an email address", "PHONE": "a phone number",
            "ADDRESS": "an address", "DATE_OF_BIRTH": "a date of birth", "USERNAME": "a username",
            "QATAR_ID": "a Qatar ID number", "NATIONAL_ID": "an ID number",
            "PASSPORT": "a passport number", "IBAN": "a bank account (IBAN)",
            "ACCOUNT_NUMBER": "an account number", "CREDIT_CARD": "a card number",
            "PIN": "a PIN", "SALARY": "salary details", "API_KEY": "an API key",
            "CLOUD_KEY": "a cloud access key", "PASSWORD": "a password",
            "DATABASE_URL": "database login details", "PRIVATE_KEY": "a private key",
            "JWT": "an access token", "BEARER_TOKEN": "an access token",
            "INTERNAL_HOST": "internal server addresses",
        },
        "ready_text": "Ready to paste",
        "ready_text_limited": "If your policy allows outside tools, share only this version",
        "ready_secret": "If you need help with it, send this version, with the secret removed",
        "original_ok": "You can upload the original file as it is.",
        "see_found": "See what I found",
        "copy": "Copy",
        "copied": "Copied",
        "files_ready": "Redacted file, ready to send:",
        "pdf_not_safe": "A redacted PDF could not be made safely for this file, so use the text "
        "version above.",
        "models_title": "Models",
        "theme": "Switch light or dark",
        "kpi_inspected": "Messages checked",
        "tab_dashboard": "Dashboard",
        "tab_how": "How it works",
        "examples": ["Can I ask ChatGPT for a cafe slogan?", "Can I send this CV to ChatGPT?",
                     "Can I upload this Arabic contract to Claude?",
                     "Can I ask ChatGPT to fix this code?"],
        "placeholder": "Ask Sitr, or attach a file with +",
        "task_label": "Task",
        "tasks": ["Summarize", "Answer the request", "Rewrite professionally",
                  "Translate to English", "Translate to Arabic"],
        "decision_label": "Sitr's decision",
        "answer_label": "Answer",
        "found_label": "What Sitr found",
        "sent_label": "What the AI model received",
        "details_label": "Technical details",
        "refresh": "Refresh",
        "empty_title": "Can I send this to ChatGPT?",
        "empty_hint": "Paste text or attach a file and ask. Sitr tells you if it is safe to share "
        "with an AI assistant, and gives you a safe version if it is not.",
        "pending": "Checking it…",
        "attached": "Attached",
        "private_note": "Qwen inside Sitr received the original. Nothing left Sitr.",
        "decisions": {"allow": "Allowed", "redact": "Redacted", "private": "Private route",
                      "block": "Blocked", "error": "Not inspected"},
        "risk": "Risk",
        "found": "Found",
        "sent_to": "Sent to",
        "not_assessed": "Not assessed",
        "risk_levels": {"low": "Low", "medium": "Medium", "high": "High", "critical": "Critical"},
        "of_100": "{score} of 100",
        "nothing": "Nothing",
        "routes": {
            "allow": "Qwen through Hugging Face Inference",
            "redact": "Qwen through Hugging Face Inference, placeholders only",
            "private": "Qwen inside Sitr; nothing leaves",
            "block": "No model",
            "error": "No model",
        },
        "no_model": "No model was called.",
        "nothing_sent": "Nothing. No AI model received this message.",
        "reason_codes": "Reason codes",
        "detector_used": "Detector",
        "classifier_used": "Classifier",
        "time": "Time",
        "columns": ["Type", "Severity", "Source", "Confidence", "Page"],
        "no_findings": "No findings.",
        "none": "None",
        "dashboard_intro": "Decisions for every visitor since the app started. Only the decision "
        "and the kinds of data found are counted, never the text itself.",
        "dashboard_empty": "No inspections yet. Each decision is counted here as it happens.",
        "inspected": "inspected since the app started",
        "times": "Times",
        "nothing_found_yet": "Nothing sensitive found yet.",
        "how": (
            "Each input passes three checks, then a fixed policy decides.\n\n"
            "1. Rules find secrets, IDs, IBANs and salaries in Arabic and English.\n"
            "2. `OpenMed/privacy-filter-multilingual-v2` finds names and other personal data.\n"
            "3. `Horizon-Labs/multilingual-zeroshot-small` reads what the text is about.\n\n"
            "| Decision | What reaches a model |\n|---|---|\n"
            "| Allowed | The text, sent to `Qwen/Qwen2.5-1.5B-Instruct` through Hugging Face "
            "Inference Providers |\n"
            "| Redacted | Only the text with placeholders such as `[EMAIL_1]` |\n"
            "| Private route | Nothing leaves: Qwen runs inside this app. This is a "
            "demonstration, not an isolated environment |\n"
            "| Blocked | Nothing, not even the models inside Sitr |\n\n"
            "Audit logs hold decisions and counts, never content, and uploads are deleted after "
            "inspection. Use synthetic data only. Evaluation data: [arwaili/sitr-synthetic-dlp]"
            "(https://huggingface.co/datasets/arwaili/sitr-synthetic-dlp)."
        ),
    },
    "ar": {
        "switch": "English",
        "product": "بوابة الذكاء الاصطناعي",
        "purpose": "يفحص سِتر ما يرسله الموظفون إلى الذكاء الاصطناعي قبل أن يغادر: يمرّر النص "
        "الآمن، ويُخفي البيانات الشخصية، ويُبقي العمل السري داخل المؤسسة، ويوقف الأسرار.",
        "detector": "كاشف الخصوصية",
        "classifier": "مصنّف المخاطر",
        "states": {"ready": "جاهز", "not loaded": "قيد التحميل", "unavailable": "غير متاح",
                   "disabled": "متوقف"},
        "tab_inspect": "المحادثة",
        "new_chat": "محادثة جديدة",
        "next": {
            "allow": ("آمن للإرسال",
                      "لم يُعثر على شيء حساس. يمكنك لصقه في ChatGPT أو Claude أو أي مساعد ذكاء "
                      "اصطناعي كما هو."),
            "redact": ("أرسل هذه النسخة بدلًا منه",
                       "استُبدلت البيانات الشخصية بعناصر بديلة. أعطِ المساعد هذه النسخة أو الملف "
                       "المنقّح أدناه، وليس الأصل."),
            "private": ("لا ترسل هذا إلى ChatGPT أو Claude",
                        "هذا عمل سري. استخدم أداة الذكاء الاصطناعي الداخلية المعتمدة في "
                        "مؤسستك. وإن سمحت سياستك بالأدوات الخارجية، فأرسل هذه النسخة فقط بعد "
                        "حذف التفاصيل الحساسة."),
            "block": ("لا ترسل هذا",
                      "يحتوي على سر مثل كلمة مرور أو مفتاح API، ولا يجوز إدخال الأسرار في أي مساعد "
                      "ذكاء اصطناعي. إن احتجت مساعدة فيه، فأرسل هذه النسخة التي استُبدل فيها السر. "
                      "وإن شاركت السر في أي مكان، فاطلب تغييره."),
            "error": ("لا شيء للإرسال", "تعذر على سِتر قراءة هذا. جرّب لصق النص بدلًا منه."),
        },
        "answer": {
            "allow": ("آمن", "نعم، يمكنك إرساله إلى {dest}.",
                      "لم أجد فيه شيئًا شخصيًا أو سريًا أو أي أسرار."),
            "redact": ("يحتاج تعديلًا", "ليس كما هو. أرسل هذه النسخة إلى {dest} بدلًا منه.",
                       "فيه {things}. استبدلتها بعناصر بديلة مثل [EMAIL_1]، فهذه النسخة آمنة "
                       "للمشاركة."),
            "private": ("أبقِه خاصًا", "لا، أبقِ هذا داخل المؤسسة.",
                        "هذا عمل سري{with_things}. استخدم أداة الذكاء الاصطناعي الداخلية المعتمدة "
                        "في مؤسستك."),
            "block": ("لا ترسله", "لا، لا ترسل هذا إلى {dest}.",
                      "فيه {things}، ولا يجوز إدخال الأسرار في أي مساعد ذكاء اصطناعي. وإن شاركت "
                      "السر في أي مكان، فاطلب تغييره."),
            "error": ("تعذرت القراءة", "تعذر عليّ قراءة هذا.", "{reason} جرّب لصق النص."),
        },
        "default_dest": "مساعد الذكاء الاصطناعي",
        "with_things_prefix": "، وفيه ",
        "and": " و",
        "things": {
            "PERSON": "اسم", "EMAIL": "بريد إلكتروني", "PHONE": "رقم هاتف",
            "ADDRESS": "عنوان", "DATE_OF_BIRTH": "تاريخ ميلاد", "USERNAME": "اسم مستخدم",
            "QATAR_ID": "رقم هوية قطرية", "NATIONAL_ID": "رقم هوية",
            "PASSPORT": "رقم جواز سفر", "IBAN": "رقم حساب بنكي (IBAN)",
            "ACCOUNT_NUMBER": "رقم حساب", "CREDIT_CARD": "رقم بطاقة",
            "PIN": "رمز PIN", "SALARY": "تفاصيل راتب", "API_KEY": "مفتاح API",
            "CLOUD_KEY": "مفتاح وصول سحابي", "PASSWORD": "كلمة مرور",
            "DATABASE_URL": "بيانات دخول قاعدة بيانات", "PRIVATE_KEY": "مفتاح خاص",
            "JWT": "رمز وصول", "BEARER_TOKEN": "رمز وصول",
            "INTERNAL_HOST": "عناوين خوادم داخلية",
        },
        "ready_text": "جاهز للصق",
        "ready_text_limited": "إن سمحت سياستك بالأدوات الخارجية، فشارك هذه النسخة فقط",
        "ready_secret": "إن احتجت مساعدة فيه، فأرسل هذه النسخة بعد حذف السر",
        "original_ok": "يمكنك رفع الملف الأصلي كما هو.",
        "see_found": "اعرض ما وجدته",
        "copy": "نسخ",
        "copied": "نُسخ",
        "files_ready": "ملف منقّح جاهز للإرسال:",
        "pdf_not_safe": "تعذر إنشاء ملف PDF منقّح بأمان لهذا الملف، فاستخدم النسخة النصية أعلاه.",
        "models_title": "النماذج",
        "theme": "تبديل الوضع الفاتح أو الداكن",
        "kpi_inspected": "رسائل فُحصت",
        "tab_dashboard": "لوحة المتابعة",
        "tab_how": "كيف يعمل",
        "examples": ["هل أطلب من ChatGPT شعارًا لمقهى؟", "هل أرسل هذه السيرة الذاتية إلى ChatGPT؟",
                     "هل أرفع هذا العقد إلى Claude؟", "هل أطلب من ChatGPT إصلاح هذا الكود؟"],
        "placeholder": "اسأل سِتر، أو أرفق ملفًا بالضغط على +",
        "task_label": "المهمة",
        "tasks": ["لخّص", "أجب عن الطلب", "أعد الصياغة بأسلوب مهني", "ترجم إلى الإنجليزية",
                  "ترجم إلى العربية"],
        "decision_label": "قرار سِتر",
        "answer_label": "الإجابة",
        "found_label": "ما وجده سِتر",
        "sent_label": "ما وصل إلى نموذج الذكاء الاصطناعي",
        "details_label": "التفاصيل التقنية",
        "refresh": "تحديث",
        "empty_title": "هل يمكنني إرسال هذا إلى ChatGPT؟",
        "empty_hint": "الصق النص أو أرفق ملفًا واسأل. يخبرك سِتر إن كان آمنًا لمشاركته مع مساعد ذكاء "
        "اصطناعي، ويعطيك نسخة آمنة إن لم يكن كذلك.",
        "pending": "جارٍ الفحص…",
        "attached": "مرفق",
        "private_note": "استلم Qwen داخل سِتر النص الأصلي، ولم يخرج شيء من سِتر.",
        "decisions": {"allow": "مسموح", "redact": "منقّح", "private": "مسار خاص",
                      "block": "محظور", "error": "لم يُفحص"},
        "risk": "الخطورة",
        "found": "ما وُجد",
        "sent_to": "أُرسل إلى",
        "not_assessed": "لم تُقيَّم",
        "risk_levels": {"low": "منخفضة", "medium": "متوسطة", "high": "عالية",
                        "critical": "حرجة"},
        "of_100": "{score} من 100",
        "nothing": "لا شيء",
        "routes": {
            "allow": "Qwen عبر Hugging Face",
            "redact": "Qwen عبر Hugging Face، بعد إخفاء البيانات",
            "private": "Qwen داخل سِتر، ولا يخرج شيء",
            "block": "لا يوجد نموذج",
            "error": "لا يوجد نموذج",
        },
        "no_model": "لم يُستدعَ أي نموذج.",
        "nothing_sent": "لا شيء. لم تصل هذه الرسالة إلى أي نموذج ذكاء اصطناعي.",
        "reason_codes": "رموز الأسباب",
        "detector_used": "الكاشف",
        "classifier_used": "المصنّف",
        "time": "الوقت",
        "columns": ["النوع", "الخطورة", "المصدر", "الثقة", "الصفحة"],
        "no_findings": "لا نتائج.",
        "none": "لا يوجد",
        "dashboard_intro": "قرارات جميع الزوار منذ تشغيل التطبيق. يُحسب القرار ونوع البيانات "
        "التي وُجدت فقط، ولا يُحفظ النص نفسه.",
        "dashboard_empty": "لا عمليات فحص بعد. يُحسب كل قرار هنا لحظة صدوره.",
        "inspected": "عملية فحص منذ تشغيل التطبيق",
        "times": "المرات",
        "nothing_found_yet": "لم يُعثر على شيء حساس بعد.",
        "how": (
            "يمر كل مدخل بثلاث مراحل فحص، ثم تقرر سياسة ثابتة.\n\n"
            "1. قواعد تكشف الأسرار وأرقام الهوية وأرقام IBAN والرواتب بالعربية والإنجليزية.\n"
            "2. نموذج `OpenMed/privacy-filter-multilingual-v2` يكشف الأسماء والبيانات الشخصية.\n"
            "3. نموذج `Horizon-Labs/multilingual-zeroshot-small` يفهم موضوع النص.\n\n"
            "| القرار | ما يصل إلى النموذج |\n|---|---|\n"
            "| مسموح | النص كما هو، إلى `Qwen/Qwen2.5-1.5B-Instruct` عبر Hugging Face |\n"
            "| منقّح | النص بعد استبدال البيانات بعناصر بديلة مثل `[EMAIL_1]` |\n"
            "| مسار خاص | لا يخرج شيء: يعمل Qwen داخل هذا التطبيق. هذا عرض توضيحي وليس بيئة "
            "معزولة |\n"
            "| محظور | لا شيء، ولا حتى النماذج داخل سِتر |\n\n"
            "تحفظ سجلات التدقيق القرارات والأعداد فقط دون أي محتوى، وتُحذف الملفات المرفوعة بعد "
            "فحصها. استخدم بيانات اصطناعية فقط. بيانات التقييم: [arwaili/sitr-synthetic-dlp]"
            "(https://huggingface.co/datasets/arwaili/sitr-synthetic-dlp)."
        ),
    },
}

# Arabic for each reason the policy gives; the first reason code picks the sentence.
REASONS_AR = {
    "ACTIVE_CREDENTIAL": "وُجد مفتاح أو رمز وصول، لذلك لم يُرسل شيء إلى أي نموذج.",
    "PASSWORD": "وُجدت كلمة مرور، لذلك لم يُرسل شيء إلى أي نموذج.",
    "DATABASE_CREDENTIAL": "وُجدت بيانات دخول لقاعدة بيانات، لذلك لم يُرسل شيء إلى أي نموذج.",
    "PRIVATE_KEY": "وُجد مفتاح خاص، لذلك لم يُرسل شيء إلى أي نموذج.",
    "RESTRICTED_OPERATIONAL": "وُجد محتوى مقيّد، لذلك لم يُرسل شيء إلى أي نموذج.",
    "CRITICAL_FINDING": "وُجد محتوى مقيّد، لذلك لم يُرسل شيء إلى أي نموذج.",
}
DECISION_REASONS_AR = {
    "allow": "لم يُعثر على محتوى حساس.",
    "redact": "وُجدت بيانات شخصية واستُبدلت بعناصر بديلة قبل المعالجة.",
    "private": "وُجد محتوى سري، لذلك لا يعالجه إلا المسار الخاص.",
    "block": "وُجد محتوى مقيّد، لذلك لم يُرسل شيء إلى أي نموذج.",
}
# Arabic for each content-free error the pipeline can return.
ERRORS_AR = {
    "No readable content was provided.": "لا يوجد محتوى قابل للقراءة.",
    "This PDF could not be read. It may be corrupted.": "تعذرت قراءة ملف PDF، وقد يكون تالفًا.",
    "This PDF is password-protected.": "ملف PDF محمي بكلمة مرور.",
    "Images need OCR, which is not enabled in this demo.":
        "الصور تحتاج إلى التعرف الضوئي على النص، وهو غير مفعّل في هذا العرض.",
    "This file type is not supported.": "نوع الملف غير مدعوم.",
    "This file could not be read.": "تعذرت قراءة الملف.",
    "This PDF has no extractable text. Scanned PDFs need OCR.":
        "لا يحتوي ملف PDF على نص قابل للاستخراج، والملفات الممسوحة ضوئيًا تحتاج إلى OCR.",
    "This file could not be read as text.": "تعذرت قراءة الملف كنص.",
    DETECTOR_DOWN_MESSAGE: "كاشف الخصوصية غير جاهز، لذلك حُظر هذا المدخل. حاول مرة أخرى.",
    "Sitr could not inspect this input.": "تعذر على سِتر فحص هذا المدخل.",
}
ERROR_FALLBACK_AR = "تعذر فحص هذا المدخل."
NOTHING_SENT_AR = "لم يُرسل شيء إلى أي نموذج."
