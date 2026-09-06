from io import BytesIO


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from an uploaded PDF.

    Prefers pdfplumber (better layout / tables). Falls back to pypdf
    if pdfplumber is missing or returns nothing.
    """

    text = _extract_with_pdfplumber(file_bytes)
    if text.strip():
        return text

    return _extract_with_pypdf(file_bytes)


def _extract_with_pdfplumber(file_bytes: bytes) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""

    pages = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text() or ""
            if extracted:
                pages.append(extracted)
    return "\n".join(pages)


def _extract_with_pypdf(file_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(file_bytes))
    pages = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)

    return "\n".join(pages)
