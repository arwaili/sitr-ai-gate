"""Rebuild the synthetic demo PDFs with headless Chrome: python examples/make_examples.py

Chrome writes correct Unicode for Arabic, which PyMuPDF's own writer does not. Arial with
ligatures off is used because ligature glyphs (لا, لم) come back out of order when extracted.
Every person, number and credential here is synthetic. Phone numbers use the +974 0000 range,
which is not assigned to subscribers in Qatar.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HERE = Path(__file__).parent
STYLE = (
    "<style>body{font-family:Arial,sans-serif;margin:48px;line-height:1.5;"
    'font-feature-settings:"liga" 0,"rlig" 0,"dlig" 0}'
    ".ar{direction:rtl;text-align:right}.page{break-after:page}</style>"
)

CV = """
<h1>Curriculum Vitae (synthetic)</h1>
<p>Name: Mariam Al-Example</p>
<p>Email: mariam.al-example@example.com</p>
<p>Phone: +974 0000 0100</p>
<h2>Experience</h2>
<p>Data analyst at Example Trading, 2021 to 2025. Built weekly sales dashboards.</p>
<h2>Skills</h2>
<p>Python, SQL, Arabic and English reporting.</p>
<p class="ar">السيرة الذاتية</p>
<p class="ar">محللة بيانات تجيد العربية والإنجليزية</p>
"""

CONTRACT = """
<div class="page">
<h1>Employment Contract (synthetic)</h1>
<p>Employee: Mariam Al-Example</p>
<p>QID 28400001234</p>
<p>Position: Senior Data Analyst</p>
<p>Monthly salary: QAR 25,000</p>
<p>Bank IBAN: QA00SYNT000000000000000000001</p>
<p class="ar">عقد عمل سري</p>
<p class="ar">الراتب الشهري 25,000 ريال، ولا يجوز مشاركته</p>
</div>
<h2>Performance evaluation</h2>
<p>The annual evaluation rating is confidential and shared only with HR.</p>
<p class="ar">تقييم الأداء السنوي سري</p>
"""


def build(name: str, body: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "page.html"
        head = f"<!doctype html><meta charset='utf-8'><title>{name}</title>{STYLE}"
        html.write_text(head + body, encoding="utf-8")
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={HERE / name}", html.as_uri()],
            check=True, capture_output=True, timeout=60,
        )


if __name__ == "__main__":
    if not Path(CHROME).exists():
        sys.exit("Google Chrome is needed to rebuild the PDFs; the committed ones still work.")
    build("synthetic_cv.pdf", CV)
    build("synthetic_contract.pdf", CONTRACT)
    print("Wrote synthetic_cv.pdf and synthetic_contract.pdf")
