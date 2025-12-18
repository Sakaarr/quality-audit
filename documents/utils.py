# pyright: reportMissingImports=false
from __future__ import annotations

import hashlib
import os
from typing import IO, Tuple

from django.core.files.uploadedfile import UploadedFile
from django.core.exceptions import ObjectDoesNotExist

from documents.domain import DocumentImage, SectionNode, UnifiedDocument


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


def _build_section_tree(payload: dict) -> SectionNode:
    """Reconstruct a SectionNode (and its children) from stored JSON."""
    if not isinstance(payload, dict):
        # Fallback to an empty top-level node if structure is unexpected
        return SectionNode(title=str(payload), level=1)

    children_payload = payload.get("children") or []
    children = [
        _build_section_tree(child) for child in children_payload if isinstance(child, dict)
    ]

    return SectionNode(
        title=str(payload.get("title", "")),
        level=int(payload.get("level", 1) or 1),
        paragraphs=list(payload.get("paragraphs") or []),
        children=children,
    )


def _build_sections_list(sections_json) -> list[SectionNode]:
    if not sections_json:
        return []
    return [_build_section_tree(item) for item in sections_json]


def _build_images_list(images_json) -> list[DocumentImage]:
    if not images_json:
        return []

    images: list[DocumentImage] = []
    for item in images_json:
        if not isinstance(item, dict):
            continue
        images.append(
            DocumentImage(
                identifier=str(
                    item.get("id")
                    or item.get("identifier")
                    or "image-unknown"
                ),
                mime_type=str(item.get("mime_type") or "application/octet-stream"),
                width=int(item.get("width") or 0),
                height=int(item.get("height") or 0),
                data=item.get("data"),
                metadata=item.get("metadata") or {},
            )
        )
    return images


def build_unified_document_from_parsed(parsed_doc) -> UnifiedDocument:
    """
    Reconstruct a UnifiedDocument instance from a ParsedDocument model.
    This avoids re-parsing the original binary document.
    """
    sections = _build_sections_list(getattr(parsed_doc, "sections_json", []))
    images = _build_images_list(getattr(parsed_doc, "images_json", []))

    return UnifiedDocument(
        source_type=getattr(parsed_doc, "source_type", "unknown"),
        metadata=getattr(parsed_doc, "metadata_json", {}) or {},
        sections=sections,
        text=getattr(parsed_doc, "text_json", {}) or {},
        tables=getattr(parsed_doc, "tables_json", []) or [],
        images=images,
        extras=getattr(parsed_doc, "extras_json", {}) or {},
    )


def get_or_create_unified_document(
    uploaded_file: UploadedFile, *, enable_ocr: bool = True
) -> Tuple[UnifiedDocument, object]:
    """
    Return a UnifiedDocument for the given uploaded file, reusing cached
    parsed data when available.

    - If a ParsedDocument already exists for this file hash, rebuild the
      UnifiedDocument from that JSON (no binary parsing).
    - Otherwise, parse the binary using the appropriate parser, persist it,
      and return the fresh UnifiedDocument.
    """
    # Local imports to avoid circular dependencies
    from documents.models import Document, ParsedDocument
    from documents.services.docx_parser import DocxParser
    from documents.services.pdf_parser import PdfParser

    # 1) Look up by stable SHA256 content hash
    file_hash = calculate_file_hash(uploaded_file)
    uploaded_file.seek(0)

    document = (
        Document.objects.filter(file_hash=file_hash)
        .select_related("parsed_data")
        .first()
    )

    if document:
        try:
            parsed_doc = document.parsed_data  # OneToOne relation
        except ObjectDoesNotExist:
            parsed_doc = None

        if parsed_doc:
            unified = build_unified_document_from_parsed(parsed_doc)
            return unified, parsed_doc

    # 2) No cached parse exists: parse now and persist it
    name = (getattr(uploaded_file, "name", "") or "").lower()
    _root, ext = os.path.splitext(name)

    if ext == ".pdf":
        parser = PdfParser()
        unified = parser.parse(uploaded_file, enable_ocr=enable_ocr)
    else:
        # Default to DOCX parser; validation layers already restrict types.
        parser = DocxParser()
        unified = parser.parse(uploaded_file)

    parsed_doc = save_parsed_document(uploaded_file, unified)
    return unified, parsed_doc


