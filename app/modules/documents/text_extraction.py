from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import AppError, BadRequestError


def read_text(filename: str, data: bytes) -> tuple[str, int | None]:
    """Returns (text, page count) for a .txt or .pdf file. Page count is None for text files."""
    name = filename.lower()
    if name.endswith(".txt"):
        try:
            return data.decode("utf-8").strip(), None
        except UnicodeDecodeError as exc:
            raise BadRequestError("INVALID_ENCODING", "Text files must be UTF-8") from exc
    if name.endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
        except PdfReadError as exc:
            raise BadRequestError("INVALID_PDF", "The file could not be read as a PDF") from exc
        text = "\n\n".join(page.strip() for page in pages if page.strip())
        if not text:
            # A scanned PDF is an image with no text layer; there is no OCR in this project.
            raise AppError(422, "NO_TEXT", "The PDF has no text layer (scanned PDFs need OCR)")
        return text, len(pages)
    raise BadRequestError("UNSUPPORTED_FILE_TYPE", "Only .txt and .pdf files are supported")
