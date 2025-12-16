# pyright: reportMissingImports=false
from __future__ import annotations

import hashlib
from typing import IO

from django.core.files.uploadedfile import UploadedFile

from documents.domain import UnifiedDocument


def calculate_file_hash(file_obj: IO[bytes] | UploadedFile) -> str:
    """Calculate SHA256 hash of file contents."""
    hasher = hashlib.sha256()
    position = file_obj.tell()
    file_obj.seek(0)

    for chunk in iter(lambda: file_obj.read(8192), b""):
        hasher.update(chunk)

    file_obj.seek(position)
    return hasher.hexdigest()


def save_parsed_document(
    uploaded_file: UploadedFile, unified_doc: UnifiedDocument
):
    """Save uploaded file and parsed document data to database."""
    # Import here to avoid circular import
    from documents.models import Document, ParsedDocument

    file_hash = calculate_file_hash(uploaded_file)
    uploaded_file.seek(0)

    # Check if document with same hash already exists
    existing_doc = Document.objects.filter(file_hash=file_hash).first()
    if existing_doc:
        document = existing_doc
    else:
        document = Document.objects.create(
            file=uploaded_file,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            file_hash=file_hash,
        )

    # Get or create parsed document
    parsed_doc, created = ParsedDocument.objects.get_or_create(
        document=document,
        defaults={
            "source_type": unified_doc.source_type,
            "metadata_json": unified_doc.metadata,
            "sections_json": [
                section.to_representation() for section in unified_doc.sections
            ],
            "text_json": unified_doc.text,
            "tables_json": unified_doc.tables,
            "images_json": [
                img.to_representation() for img in unified_doc.images
            ],
            "extras_json": unified_doc.extras,
            "page_count": unified_doc.extras.get("page_count"),
            "table_count": len(unified_doc.tables),
            "image_count": len(unified_doc.images),
            "section_count": len(unified_doc.sections),
            "has_ocr": unified_doc.extras.get("ocr_applied", False),
            "author": unified_doc.metadata.get("author"),
            "title": unified_doc.metadata.get("title"),
        },
    )

    return parsed_doc

