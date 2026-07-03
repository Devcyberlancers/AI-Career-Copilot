import html
import logging
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser

logger = logging.getLogger("app.services.pdf_service")

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_ROOT = os.path.join(BACKEND_ROOT, "uploads")
RESUME_PDF_DIR = os.path.join(UPLOAD_ROOT, "resumes")
RESUME_CSS_PATH = os.path.join(BACKEND_ROOT, "app", "static", "css", "resume.css")


class ResumeTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str):
        if tag in {"script", "style"} and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if self.skip_depth:
            return
        cleaned = html.unescape(data).strip()
        if cleaned:
            self.parts.append(cleaned + " ")

    def text(self) -> str:
        raw_text = "".join(self.parts)
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw_text.splitlines()]
        return "\n".join(line for line in lines if line)


def ensure_resume_pdf_dir() -> None:
    os.makedirs(RESUME_PDF_DIR, exist_ok=True)


def sanitize_resume_html(resume_html: str) -> str:
    resume_html = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", resume_html, flags=re.I)
    resume_html = re.sub(r"\son\w+\s*=\s*(['\"]).*?\1", "", resume_html, flags=re.I)
    resume_html = re.sub(r"javascript:", "", resume_html, flags=re.I)
    return resume_html


def html_to_text(resume_html: str) -> str:
    parser = ResumeTextExtractor()
    parser.feed(sanitize_resume_html(resume_html))
    return parser.text()


def fallback_html_text(resume_html: str) -> str:
    sanitized = sanitize_resume_html(resume_html)
    without_tags = re.sub(r"<[^>]+>", " ", sanitized)
    decoded = html.unescape(without_tags)
    cleaned = re.sub(r"\s+", " ", decoded).strip()
    if cleaned:
        return cleaned
    return re.sub(r"\s+", " ", resume_html).strip()


def render_pdf(resume_html: str, text: str, output_path: str) -> None:
    sanitized_html = sanitize_resume_html(resume_html)
    css_exists = os.path.exists(RESUME_CSS_PATH)
    logger.info(
        "PDF renderer selected: WeasyPrint; output_path=%s css_path=%s css_exists=%s",
        output_path,
        RESUME_CSS_PATH,
        css_exists,
    )
    if not css_exists:
        raise FileNotFoundError(f"Resume stylesheet not found: {RESUME_CSS_PATH}")

    try:
        from weasyprint import CSS, HTML
    except Exception as exc:
        raise RuntimeError(
            "WeasyPrint is not installed in the backend Python environment. "
            f"Backend Python: {sys.executable}. "
            "Install it with: python -m pip install -r backend/requirements.txt"
        ) from exc

    logger.info("Rendering resume PDF with WeasyPrint.")
    html_doc = HTML(string=sanitized_html, base_url=BACKEND_ROOT)
    base_css = CSS(filename=RESUME_CSS_PATH)
    document = None
    selected_font_size = 11.0
    for step in range(0, 3):
        font_size = 11.0 - (step * 0.5)
        override_css = CSS(string=f"""
            body {{ font-size: {font_size}pt; }}
            li {{ font-size: {max(10.0, font_size - 0.2)}pt; }}
            .tech-line, .project-description {{ font-size: {max(10.0, font_size - 0.5)}pt; }}
        """)
        document = html_doc.render(stylesheets=[base_css, override_css])
        page_count = len(document.pages)
        logger.info("WeasyPrint page-count check: pages=%s font_size=%s", page_count, font_size)
        selected_font_size = font_size
        if page_count <= 1 or font_size <= 10.0:
            break

    if document is None:
        raise RuntimeError("WeasyPrint failed to render the resume document.")
    document.write_pdf(output_path)
    logger.info("PDF generated successfully.")
    logger.info("Saved PDF: %s using font_size=%s", output_path, selected_font_size)


def generate_resume_pdf(user_id: int, resume_html: str) -> dict:
    ensure_resume_pdf_dir()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    file_name = f"resume_{user_id}_{timestamp}.pdf"
    pdf_path = os.path.join(RESUME_PDF_DIR, file_name)
    logger.info(
        "Resume PDF generation using ATS HTML pipeline: css_path=%s css_exists=%s",
        RESUME_CSS_PATH,
        os.path.exists(RESUME_CSS_PATH),
    )
    logger.info(f"Resume PDF input HTML length: {len(resume_html or '')}")
    text = html_to_text(resume_html)
    logger.info(f"Resume PDF extracted text length: {len(text)}")
    logger.info(f"Resume PDF extracted text preview: {text[:1000]}")
    if not text:
        logger.warning("HTML parser extracted no resume text; falling back to raw HTML text.")
        text = fallback_html_text(resume_html)
        logger.info(f"Resume PDF fallback text length: {len(text)}")
        logger.info(f"Resume PDF fallback text preview: {text[:1000]}")

    if not text:
        logger.warning("Resume PDF text extraction returned empty content; writing placeholder PDF instead of crashing.")
        text = "Tailored resume content was generated, but readable text could not be extracted for PDF rendering."

    render_pdf(resume_html, text, pdf_path)
    file_size = os.path.getsize(pdf_path)

    return {
        "file_name": file_name,
        "file_size": file_size,
        "pdf_path": pdf_path,
        "text": text,
    }
