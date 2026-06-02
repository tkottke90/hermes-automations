#!/Users/thomaskottke/.hermes-automations/.venv/bin/python3
"""
ocr_pipeline.py — Email HTML → PDF → images → OCR text.

Fast path: if a plain-text body is available and non-trivial, return it directly.
Full path: render HTML via weasyprint → pdf2image pages → pytesseract OCR.
"""

import io
import sys
import tempfile
from pathlib import Path
from typing import Optional


# Minimum plain-text length to trust it over OCR
_PLAIN_TEXT_MIN_LEN = 100


def _check_system_deps() -> None:
    """Verify poppler and tesseract are installed. Print actionable error and exit if not."""
    import shutil

    missing = []
    if not shutil.which("pdftoppm") and not shutil.which("pdfinfo"):
        missing.append(
            "poppler (pdf2image backend):\n"
            "  brew install poppler"
        )
    if not shutil.which("tesseract"):
        missing.append(
            "tesseract (OCR engine):\n"
            "  brew install tesseract"
        )
    if missing:
        print(
            "ERROR: Missing system dependencies:\n\n" + "\n\n".join(missing),
            file=sys.stderr,
        )
        sys.exit(1)


def email_to_text(
    body_html: str,
    body_plain: str,
    verbose: bool = False,
) -> str:
    """
    Convert email content to plain text for classification.

    1. Fast path — return plain text if it's substantive.
    2. Full OCR path — render HTML to PDF, convert to images, run tesseract.
    3. Fallback — if both paths fail, return whatever plain text exists.
    """
    # Fast path: trust plain text if it's long enough
    stripped_plain = (body_plain or "").strip()
    if len(stripped_plain) >= _PLAIN_TEXT_MIN_LEN:
        if verbose:
            print(f"  [OCR] Fast path — using plain text ({len(stripped_plain)} chars)")
        return stripped_plain

    # Full OCR path
    if body_html and body_html.strip():
        try:
            return _html_to_ocr_text(body_html, verbose=verbose)
        except RuntimeError as e:
            print(f"  [ERROR] OCR pipeline failed: {e}", file=sys.stderr)
            if verbose:
                import traceback
                traceback.print_exc()
        except Exception as e:
            print(f"  [ERROR] Unexpected OCR error: {e}", file=sys.stderr)
            if verbose:
                import traceback
                traceback.print_exc()

    # Final fallback
    if stripped_plain:
        if verbose:
            print(f"  [OCR] Fallback — short plain text ({len(stripped_plain)} chars)")
        return stripped_plain

    return ""


def _html_to_ocr_text(html: str, verbose: bool = False) -> str:
    """
    Render HTML → PDF bytes → PIL images → OCR text strings → joined result.
    Includes robust error handling and resource cleanup.
    """
    # Step 1: HTML → PDF bytes via weasyprint
    from weasyprint import HTML  # type: ignore

    try:
        if verbose:
            print("  [OCR] Rendering HTML → PDF...")
        pdf_bytes = HTML(string=html).write_pdf()
    except Exception as e:
        raise RuntimeError(f"Failed to render HTML to PDF: {e}")

    # Step 2: PDF bytes → PIL images via pdf2image
    from pdf2image import convert_from_bytes  # type: ignore

    images = []
    try:
        if verbose:
            print("  [OCR] Converting PDF pages → images...")
        images = convert_from_bytes(pdf_bytes, dpi=150)
    except Exception as e:
        raise RuntimeError(f"Failed to convert PDF to images: {e}")

    # Step 3: images → text via pytesseract
    try:
        import pytesseract  # type: ignore
    except ImportError:
        raise RuntimeError("pytesseract is not installed. Run: pip install pytesseract")

    page_texts = []
    try:
        for i, img in enumerate(images):
            try:
                text = pytesseract.image_to_string(img, lang="eng")
                page_texts.append(text)
                if verbose:
                    print(f"  [OCR] Page {i + 1}: {len(text)} chars extracted")
            finally:
                # Explicitly close each PIL image to prevent memory leaks
                img.close()
        del images  # Explicitly delete the list of images
    except Exception as e:
        # Clean up any remaining images on error
        for img in images:
            try:
                img.close()
            except Exception:
                pass
        raise RuntimeError(f"OCR processing failed: {e}")

    combined = "\n\n".join(page_texts).strip()
    if verbose:
        print(f"  [OCR] Total OCR text: {len(combined)} chars")

    return combined
