import fitz  # PyMuPDF
import tempfile
import requests

async def extract_pdf_text(pdf_url: str) -> str:
    """
    Downloads a PDF from URL and extracts all text.
    Returns plain text or None on failure.
    """

    try:
        # Download PDF
        response = requests.get(pdf_url)
        response.raise_for_status()

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        # Read PDF using PyMuPDF
        doc = fitz.open(tmp_path)
        text = ""

        for page in doc:
            page_text = page.get_text()
            if page_text:
                text += page_text + "\n"

        doc.close()
        return text.strip() if text else None

    except Exception as e:
        print("PDF extraction error:", e)
        return None
