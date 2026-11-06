"""Lane 1 deterministic detection: structured PII and credentials with exact offsets.

Each pattern either matches the value itself or puts it in the named group `v`, so context
words such as "salary" or "passport" are required but never redacted.
"""

import base64
import binascii
import re

from src.contracts import PageText, SensitiveEntity
from src.ingestion import PAGE_SEPARATOR

_AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?"
_AR_AMOUNT = r"[\d٠-٩]{1,3}(?:[,٬][\d٠-٩]{3})+|[\d٠-٩]{4,}"
_NUMBER_LABEL = r"(?:\s*(?:no\.?|number|#))?\s*[:#]?\s*"
# Keyword start: not inside a longer word, but `DB_PASSWORD` and `MY_API_KEY` still match.
_KW = r"(?<![A-Za-z0-9])"
_PASSWORD_WORD = (
    rf"(?i)(?:{_KW}(?:password|passwd|pwd|passphrase|passcode|pass code)"
    rf"|{_KW}(?:word|code|key|phrase|secret)\s+(?:to|for)\s+(?:log|sign)[\s-]?in"
    rf"|{_KW}(?:log|sign)[\s-]?in\s+(?:word|code|key|phrase|secret)"
    r"|كلمة المرور|كلمة السر|الرمز السري|الرقم السري|الكود السري|رمز سري|رقم سري"
    r"|رمز الدخول|كود الدخول|رمز المرور)"
)

# (entity type, pattern, severity, source). Order matters: on an identical span the first wins.
_PATTERNS = [
    # Credentials: always critical.
    ("PRIVATE_KEY",
     r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----(?:[\s\S]*?-----END (?:[A-Z]+ )*PRIVATE KEY-----"
     r"|[\s\S]*)", "critical", "secret_scanner"),
    ("DATABASE_URL",
     r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|mssql|sqlserver|amqp)://"
     r"[^\s:@/]+:[^\s@/]+@[^\s'\"`]+", "critical", "secret_scanner"),
    ("JWT", r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}",
     "critical", "secret_scanner"),
    ("BEARER_TOKEN", r"(?i)\bbearer\s+(?P<v>[A-Za-z0-9\-._~+/]{20,}=*)",
     "critical", "secret_scanner"),
    ("API_KEY", r"\bsk-[A-Za-z0-9_-]{8,}", "critical", "secret_scanner"),
    ("API_KEY", r"\bhf_[A-Za-z0-9]{30,}\b", "critical", "secret_scanner"),
    ("API_KEY", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "critical", "secret_scanner"),
    ("API_KEY", r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "critical", "secret_scanner"),
    ("API_KEY",
     rf"(?i){_KW}(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|secret[_-]?key)"
     r"\b[\"']?\s*[:=]\s*[\"'](?P<v>[A-Za-z0-9_\-./+=]{12,})[\"']", "critical", "secret_scanner"),
    ("CLOUD_KEY", r"\bAKIA[0-9A-Z]{16}\b", "critical", "secret_scanner"),
    ("CLOUD_KEY", r"\bAIza[0-9A-Za-z_-]{35}\b", "critical", "secret_scanner"),
    ("CLOUD_KEY", rf"(?i){_KW}aws_secret_access_key[\"']?\s*[:=]\s*[\"']?(?P<v>[A-Za-z0-9/+=]{40})",
     "critical", "secret_scanner"),
    # Passwords: a quoted literal, or an unquoted or prose ("password is X") value that is not
    # a plain identifier (so `password=password` and `password: str` in safe code are not findings).
    ("PASSWORD",
     rf"{_PASSWORD_WORD}[\"']?\s*[:=]\s*"
     r"(?P<q>[\"'])(?P<v>[^\"'\s]{4,})(?P=q)", "critical", "secret_scanner"),
    ("PASSWORD",
     rf"{_PASSWORD_WORD}\s*[:=]\s*"
     r"(?P<v>[^\s,;()\[\]{}\"'`]{4,}+)(?![(\[])", "critical", "secret_scanner"),
    ("PASSWORD",
     rf"{_PASSWORD_WORD}[^\n:=\"']{{0,40}}?(?P<prose>\s(?:is|هي|هو)\s+)"
     r"(?P<v>[^\s,.،;\"'`]{6,}+)", "critical", "secret_scanner"),
    # Words between the keyword and the value: "password for the server: X".
    ("PASSWORD",
     rf"{_PASSWORD_WORD}[^\n:=\"']{{1,40}}?\s*[:=]\s*"
     r"(?P<v>[^\s,;()\[\]{}\"'`]{6,}+)(?![(\[])", "critical", "secret_scanner"),
    ("INTERNAL_HOST",
     r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
     "high", "secret_scanner"),
    ("INTERNAL_HOST",
     r"(?<![a-z0-9.-])[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){0,8}"
     r"\.(?:internal|corp|lan|intranet)\b",
     "high", "secret_scanner"),
    # Identifiers and financial data.
    ("IBAN", r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b", "high", "regex"),
    ("QATAR_ID", r"\b[23]\d{10}\b", "high", "regex"),
    ("PASSPORT", rf"(?i)\bpassport{_NUMBER_LABEL}(?P<v>[A-Z]{{1,2}}\d{{6,8}})\b", "high", "regex"),
    ("PASSPORT", r"(?:رقم الجواز|جواز السفر|جواز)\s*[:#]?\s*(?P<v>[A-Z]{1,2}\d{6,8})\b",
     "high", "regex"),
    ("ACCOUNT_NUMBER",
     rf"(?i)\b(?:account|acct|a/c){_NUMBER_LABEL}(?P<v>\d[\d -]{{6,18}}\d)\b", "high", "regex"),
    ("ACCOUNT_NUMBER", r"(?:رقم الحساب|الحساب)\s*[:#]?\s*(?P<v>\d[\d -]{6,18}\d)\b",
     "high", "regex"),
    ("SALARY",
     rf"(?i)\b(?:salary|salaries|wage|monthly pay|basic pay|compensation|amount|transfer)\b"
     rf"[^\n\d]{{0,25}}?"
     rf"(?P<v>(?:(?:QAR|QR|USD|\$)\s?)?(?:{_AMOUNT})(?:\s?(?:QAR|QR|riyals?|USD))?)",
     "high", "regex"),
    ("SALARY",
     rf"(?:راتب|رواتب|أجر|مبلغ)[^\n\d٠-٩]{{0,25}}?"
     rf"(?P<v>(?:{_AR_AMOUNT})(?:\s?(?:ريال|ر\.ق))?)", "high", "regex"),
    # Contact details.
    ("EMAIL", r"(?<![\w.+-])[\w.+-]{1,64}@[\w-]{1,63}\.[\w.-]{0,190}\w", "medium", "regex"),
    ("PHONE", r"(?<![\d+])(?:\+|00)974[ -]?\d{4}[ -]?\d{4}(?!\d)", "medium", "regex"),
]
_COMPILED = [(t, re.compile(p), sev, src) for t, p, sev, src in _PATTERNS]

# Documentation placeholders such as sk-XXXXXXXX or "<your-api-key>" are not live credentials.
_PLACEHOLDER = re.compile(
    r"(?i)x{4,}|\*{3,}|\.{3,}|<[^>]*>|\$\{|\{\{|your[-_ ]?(?:api[-_ ]?)?(?:key|token|secret|pass)"
    r"|placeholder|changeme|redacted|dummy"
)
_REPEATED = re.compile(r"(?:sk-|hf_|gh[pousr]_)?(.)\1+")
# An unquoted password value that looks like a variable name is code, not a credential.
_IDENTIFIER = re.compile(r"[A-Za-z_][\w.]*")
_SEVERITY_RANK = {"medium": 0, "high": 1, "critical": 2}
# Secrets written so the patterns above miss them: spaced out letter by letter, broken up with
# invisible characters, or base64-encoded.
_SPACED_OUT = re.compile(r"(?<!\S)\S(?:\s{1,3}\S(?!\S)){7,}")
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_WORD = re.compile(r"\S+")
_NO_ZERO_WIDTH = str.maketrans("", "", _ZERO_WIDTH)
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/=])")


def _is_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER.search(value) or _REPEATED.fullmatch(value))


def _page_finder(text: str, pages: list[PageText] | None):
    if not pages or PAGE_SEPARATOR.join(p.text for p in pages) != text:
        return lambda _start: None
    bounds, offset = [], 0
    for page in pages:
        offset += len(page.text)
        bounds.append((offset, page.page))
        offset += len(PAGE_SEPARATOR)
    return lambda start: next(number for end, number in bounds if start <= end)


def _not_a_password(value: str, prose: bool) -> bool:
    """True for an unquoted value that reads as a URL, a plain word, or a variable name."""
    if "://" in value or value.startswith("//"):
        return True
    if prose:
        return value.isalpha() or (
            bool(_IDENTIFIER.fullmatch(value)) and not any(c.isdigit() for c in value)
        )
    return bool(_IDENTIFIER.fullmatch(value))


def _scan(text: str, page_of) -> dict[tuple[int, int], SensitiveEntity]:
    found: dict[tuple[int, int], SensitiveEntity] = {}
    for entity_type, pattern, severity, source in _COMPILED:
        for match in pattern.finditer(text):
            group = "v" if "v" in pattern.groupindex else 0
            start, end = match.span(group)
            value = match.group(group)
            if source == "secret_scanner" and _is_placeholder(value):
                continue
            unquoted = "q" not in pattern.groupindex
            prose = "prose" in pattern.groupindex
            if entity_type == "PASSWORD" and unquoted and _not_a_password(value, prose):
                continue
            found.setdefault((start, end), SensitiveEntity(
                entity_type=entity_type,
                value=value,
                start=start,
                end=end,
                confidence=0.99 if source == "secret_scanner" else 0.95,
                source=source,
                severity=severity,
                page=page_of(start),
            ))
    return found


def _decode_base64(value: str) -> str | None:
    bare = value.rstrip("=")
    try:
        padded = bare + "=" * (-len(bare) % 4)
        return base64.b64decode(padded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None


def _disguised(text: str):
    """Yield (start, end, plain text) for each span that may hide a secret."""
    for match in _SPACED_OUT.finditer(text):
        yield *match.span(), "".join(match.group().split())
    if any(char in text for char in _ZERO_WIDTH):
        for match in _WORD.finditer(text):
            plain = match.group().translate(_NO_ZERO_WIDTH)
            if plain != match.group():
                yield *match.span(), plain
    for match in _BASE64.finditer(text):
        decoded = _decode_base64(match.group())
        if decoded:
            yield *match.span(), decoded


def detect_deterministic(text: str, pages: list[PageText] | None = None) -> list[SensitiveEntity]:
    """Return findings sorted by position. Pass IngestionResult.pages to fill in `page`."""
    page_of = _page_finder(text, pages)
    found = _scan(text, page_of)
    for start, end, plain in _disguised(text):
        # Only credentials count here, and the whole disguised span is reported.
        secret = next(
            (e for e in _scan(plain, lambda _s: None).values() if e.severity == "critical"), None
        )
        if secret:
            found.setdefault((start, end), secret.model_copy(update={
                "value": text[start:end], "start": start, "end": end, "page": page_of(start),
            }))
    # A finding inside a larger one (the host inside a database URL) adds nothing.
    # Sorted by start then longest first, an entity is nested when an earlier one reaches past it.
    # A nested entity that is more severe (a key inside an email-shaped string) is kept.
    kept, reach, reach_rank = [], -1, -1
    for entity in sorted(found.values(), key=lambda e: (e.start, -e.end)):
        rank = _SEVERITY_RANK[entity.severity]
        if entity.end <= reach and rank <= reach_rank:
            continue
        kept.append(entity)
        if entity.end > reach:
            reach, reach_rank = entity.end, rank
    return kept
