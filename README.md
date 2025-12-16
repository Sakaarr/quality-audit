# Quality Audit Document APIs

Unified Django REST Framework service that parses DOCX and PDF documents into a
single JSON schema, extracts metadata, tables, images, and runs OCR for scanned
content. The project uses **drf-spectacular** to expose interactive API
documentation at `/api/docs/`.

## Requirements

- Python 3.13+
- Optional native dependencies:
  - Poppler (set `POPPLER_PATH` env var if `pdf2image` cannot find it)
  - Tesseract OCR (set `TESSERACT_CMD` env var when the binary is outside PATH)

Install Python dependencies inside a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows PowerShell
pip install -r requirements.txt
```

## Running locally

```bash
python manage.py migrate  # Create database tables
python manage.py runserver
```

- Swagger UI: `http://localhost:8000/api/docs/`
- Raw OpenAPI schema: `http://localhost:8000/api/schema/`
- Django Admin: `http://localhost:8000/admin/` (create superuser with `python manage.py createsuperuser`)

## API overview

| Endpoint | Description |
| --- | --- |
| `POST /api/documents/docx/parse/` | Upload a `.docx` file and receive the unified JSON model. |
| `POST /api/documents/pdf/parse/` | Upload a `.pdf` file. Optional `enable_ocr` flag (default `true`) turns on OCR fallback. |
| `GET /api/documents/parsed/` | List all parsed documents stored in the database. |
| `GET /api/documents/parsed/<id>/` | Retrieve a specific parsed document by ID. |
| `POST /api/documents/title/compare/` | Extract titles from two documents and report whether they match. |
| `POST /api/documents/format/compare/` | Upload three DOCX/PDF files and verify that margins, fonts, indentation, and spacing are aligned across all of them. |

### Request fields (parse endpoints)

| Field | Type | Notes |
| --- | --- | --- |
| `file` | multipart file | Required. Must be `.docx` or `.pdf`. |
| `enable_ocr` | boolean | Optional; PDF endpoint only. Default `true`. |
| `save_document` | boolean | Optional. If `true`, saves the document and parsed data to database. Default `false`. |

### Database Models

The project includes Django models for storing uploaded documents and their parsed data:

- **Document**: Stores the uploaded file with metadata (filename, size, hash, upload timestamp)
- **ParsedDocument**: Stores the parsed document data linked to a Document, including all extracted information in JSON fields

When `save_document=true` is passed to a parse endpoint, the system will:
1. Check if a document with the same file hash already exists (prevents duplicates)
2. Save the uploaded file to the `media/documents/` directory
3. Store all parsed data in the database for later retrieval
4. Return the parsed document ID in the response

The models are registered in Django Admin for easy management.

### Response structure (both endpoints)

```json
{
  "source_type": "docx | pdf",
  "metadata": {
    "author": "Jane Doe",
    "created": "2025-01-01T08:00:00Z",
    "has_text_content": true,
    "page_count": 3,
    "page_dimensions": [
      {"width": 595.2, "height": 841.8}
    ]
  },
  "sections": [
    {
      "title": "Executive Summary",
      "level": 1,
      "paragraphs": ["Section body..."],
      "children": [
        {"title": "Scope", "level": 2, "paragraphs": ["..."], "children": []}
      ]
    }
  ],
  "text": {
    "full_text": "Full concatenated text",
    "paragraphs": ["Docx only"],
    "pages": [
      {
        "page_number": 1,
        "text": "PDF text per page",
        "layout": {
          "words": {
            "Helvetica-Bold": {
              "text": ["Heading"],
              "font_size": 16.0
            },
            "Helvetica": {
              "text": ["Body", "text", "..."],
              "font_sizes": [12.0, 12.5]
            }
          },
          "order": ["Helvetica-Bold", "Helvetica"],
          "font": "Helvetica",
          "fonts": ["Helvetica", "Helvetica-Bold"],
          "font_sizes": [12.0, 12.5, 16.0]
        }
      }
    ]
  },
  "tables": [
    {
      "id": "pdf-table-1-1",
      "page_number": 1,
      "row_count": 3,
      "column_count": 4,
      "data": [["H1", "H2"], ["V1", "V2"]]
    }
  ],
  "images": [
    {
      "id": "pdf-image-1-1",
      "mime_type": "image/png",
      "width": 640,
      "height": 320,
      "metadata": {"page": 1, "bbox": [32, 72, 320, 220]}
    }
  ],
  "extras": {
    "paragraph_count": 24,
    "section_count": 4,
    "table_count": 2,
    "image_count": 3,
    "ocr_applied": false
  }
}
```

## Implementation notes

- **DOCX parsing:** Uses `python-docx` to gather headings/paragraphs, tables, and
  embedded images (base64 encoded) with metadata from core document properties.
- **PDF parsing:** Uses `pdfplumber` for layout-aware text, table detection,
  embedded image bounding boxes (cropped via `page.crop(...)`), and metadata. A
  heuristic groups larger font sizes into sections/subsections.
- **OCR fallback:** When `pdfplumber` returns no text, pages are rendered via
  `pdf2image` and pushed through `pytesseract` to populate the text blocks.

All responses conform to a shared `UnifiedDocument` dataclass defined in
`documents/domain.py`, ensuring downstream consumers can treat DOCX and PDF
parsing results identically.

### Formatting comparison endpoint

- **Route:** `POST /api/documents/format/compare/`
- **Payload:** `file_1`, `file_2`, `file_3` multipart fields (DOCX or PDF)
- **Response:** Per-file formatting summary (fonts, font sizes, margins, indentation, spacing, warnings) and an overall `consistency` block showing which metrics match plus the applied tolerances.

The service inspects explicit formatting metadata. When a file relies entirely on default styles (common with DOCX templates) or has no extractable text (image-only PDF), the response will include warnings and the affected metrics may return `null`, which also counts as a mismatch when the other documents provide concrete values.

