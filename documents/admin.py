from django.contrib import admin

from documents.models import Document, ParsedDocument


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "file_size", "source_type", "uploaded_at"]
    list_filter = ["uploaded_at"]
    search_fields = ["original_filename", "file_hash"]
    readonly_fields = ["file_hash", "uploaded_at", "updated_at"]
    date_hierarchy = "uploaded_at"

    def source_type(self, obj):
        """Display source type from related ParsedDocument."""
        parsed = getattr(obj, "parsed_data", None)
        return parsed.source_type if parsed else "-"

    source_type.short_description = "Type"


@admin.register(ParsedDocument)
class ParsedDocumentAdmin(admin.ModelAdmin):
    list_display = [
        "document",
        "source_type",
        "author",
        "title",
        "page_count",
        "table_count",
        "image_count",
        "has_ocr",
        "parsed_at",
    ]
    list_filter = ["source_type", "has_ocr", "parsed_at"]
    search_fields = ["document__original_filename", "author", "title"]
    readonly_fields = ["parsed_at"]
    date_hierarchy = "parsed_at"
    raw_id_fields = ["document"]
