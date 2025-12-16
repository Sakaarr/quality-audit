# pyright: reportMissingImports=false
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from django.db import models
from django.utils import timezone

from documents.utils import calculate_file_hash


def document_upload_path(instance, filename):
    """Generate upload path for document files."""
    timestamp = timezone.now().strftime("%Y/%m/%d")
    hash_prefix = hashlib.md5(str(timezone.now().timestamp()).encode()).hexdigest()[:8]
    return f"documents/{timestamp}/{hash_prefix}_{filename}"


class Document(models.Model):
    """Stores uploaded document files."""

    file = models.FileField(upload_to=document_upload_path, max_length=500)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    file_hash = models.CharField(
        max_length=64, db_index=True, help_text="SHA256 hash of file contents"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Calculate file hash on save if not already set."""
        if not self.file_hash and self.file and hasattr(self.file, "read"):
            # Only calculate hash if file is newly uploaded
            self.file_hash = calculate_file_hash(self.file)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["-uploaded_at"]),
            models.Index(fields=["file_hash"]),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.file_size} bytes)"

    def delete(self, *args, **kwargs):
        """Delete the file from storage when model is deleted."""
        if self.file:
            self.file.delete(save=False)
        super().delete(*args, **kwargs)


class ParsedDocument(models.Model):
    """Stores parsed document data linked to an uploaded file."""

    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="parsed_data",
        help_text="The uploaded document file",
    )
    source_type = models.CharField(
        max_length=10, choices=[("docx", "DOCX"), ("pdf", "PDF")], db_index=True
    )
    parsed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Store the full parsed document as JSON
    metadata_json = models.JSONField(default=dict, help_text="Document metadata")
    sections_json = models.JSONField(
        default=list, help_text="Parsed sections hierarchy"
    )
    text_json = models.JSONField(default=dict, help_text="Extracted text content")
    tables_json = models.JSONField(default=list, help_text="Extracted tables")
    images_json = models.JSONField(default=list, help_text="Extracted images metadata")
    extras_json = models.JSONField(
        default=dict, help_text="Additional parsing information"
    )

    # Denormalized fields for easier querying
    page_count = models.PositiveIntegerField(null=True, blank=True)
    table_count = models.PositiveIntegerField(default=0)
    image_count = models.PositiveIntegerField(default=0)
    section_count = models.PositiveIntegerField(default=0)
    has_ocr = models.BooleanField(
        default=False, db_index=True, help_text="OCR was applied during parsing"
    )
    author = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    title = models.CharField(max_length=500, null=True, blank=True)

    class Meta:
        ordering = ["-parsed_at"]
        indexes = [
            models.Index(fields=["-parsed_at"]),
            models.Index(fields=["source_type"]),
            models.Index(fields=["author"]),
            models.Index(fields=["has_ocr"]),
        ]

    def __str__(self) -> str:
        return f"Parsed {self.source_type.upper()}: {self.document.original_filename}"

    @property
    def full_text(self) -> str:
        """Extract full text from text_json."""
        if isinstance(self.text_json, dict):
            return self.text_json.get("full_text", "")
        return ""

    def to_representation(self) -> dict:
        """Convert model instance to API response format."""
        return {
            "id": self.id,
            "document_id": self.document.id,
            "source_type": self.source_type,
            "metadata": self.metadata_json,
            "sections": self.sections_json,
            "text": self.text_json,
            "tables": self.tables_json,
            "images": self.images_json,
            "extras": self.extras_json,
            "parsed_at": self.parsed_at.isoformat(),
        }
