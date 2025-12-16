from __future__ import annotations

import os
from typing import IO
from rest_framework import serializers
from documents.models import Document, ParsedDocument


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="DOCX or PDF document to parse.")
    enable_ocr = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Run OCR when PDF text extraction is empty.",
    )
    save_document = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Save the document and parsed data to database.",
    )

    ALLOWED_EXTENSIONS = {".pdf", ".docx"}

    def validate_file(self, value: IO[bytes]) -> IO[bytes]:
        extension = os.path.splitext(value.name)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported file type. Upload a .docx or .pdf document."
            )
        return value
    
    enable_ocr= serializers.BooleanField(
        required= False,
        default= True,
        help_text="Run OCR when PDF text extraction is empty."
    )


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "original_filename", "file_size", "file_hash", "uploaded_at"]
        read_only_fields = fields


class ParsedDocumentSerializer(serializers.ModelSerializer):
    document = DocumentSerializer(read_only=True)

    class Meta:
        model = ParsedDocument
        fields = [
            "id",
            "document",
            "source_type",
            "parsed_at",
            "metadata_json",
            "sections_json",
            "text_json",
            "tables_json",
            "images_json",
            "extras_json",
            "page_count",
            "table_count",
            "image_count",
            "section_count",
            "has_ocr",
            "author",
            "title",
        ]
        read_only_fields = fields
class TitleComparisonSerializer(serializers.Serializer):
    file_1 = serializers.FileField(help_text="First DOCX or PDF document.")
    file_2 = serializers.FileField(help_text="Second DOCX or PDF document.")

    ALLOWED_EXTENSIONS = {".pdf", ".docx"}

    def validate_file_1(self, value: IO[bytes]) -> IO[bytes]:
        return self._validate_extension(value)

    def validate_file_2(self, value: IO[bytes]) -> IO[bytes]:
        return self._validate_extension(value)

    def _validate_extension(self, value: IO[bytes]) -> IO[bytes]:
        extension = os.path.splitext(value.name)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported file type. Upload a .docx or .pdf document."
            )
        return value



class FormattingComparisonSerializer(serializers.Serializer):
    file_1 = serializers.FileField(help_text="First DOCX or PDF document.")
    file_2 = serializers.FileField(help_text="Second DOCX or PDF document.")
    file_3 = serializers.FileField(help_text="Third DOCX or PDF document.")

    ALLOWED_EXTENSIONS = {".pdf", ".docx"}

    def validate_file_1(self, value: IO[bytes]) -> IO[bytes]:
        return self._validate_extension(value)

    def validate_file_2(self, value: IO[bytes]) -> IO[bytes]:
        return self._validate_extension(value)

    def validate_file_3(self, value: IO[bytes]) -> IO[bytes]:
        return self._validate_extension(value)

    def _validate_extension(self, value: IO[bytes]) -> IO[bytes]:
        extension = os.path.splitext(value.name)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported file type. Upload a .docx or .pdf document."
            )
        return value

class SectionValidationSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="DOCX or PDF document to validate.")
    required_sections = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Optional list of required sections to override defaults.",
    )

    ALLOWED_EXTENSIONS = {".pdf", ".docx"}

    def validate_file(self, value: IO[bytes]) -> IO[bytes]:

        extension = os.path.splitext(value.name)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported file type. Upload a .docx or .pdf document."
            )
        return value


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    ce_activity_date_provided = serializers.BooleanField(
        required=False, 
        default=False, 
        help_text="Check this box if CE Activity Date is provided (Enables 2-year lookback)"
    )