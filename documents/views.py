# pyright: reportMissingImports=false
from __future__ import annotations

import re
from datetime import datetime

from django.http import request
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from documents.services.file_hash import get_file_hash, get_or_create_file_report, get_report_data_by_hash
from documents.services.report_generator import generate_html_report
from django.http import HttpResponse
import json
from django.utils import timezone

from documents.models import ParsedDocument
from documents.serializers import (
    DocumentUploadSerializer,
    FormattingComparisonSerializer,
    ParsedDocumentSerializer,
    TitleComparisonSerializer,
    FigureUploadSerializer,
)
from documents.services.docx_parser import DocxParser
from documents.services.format_comparison import FormattingComparisonService
from documents.services.pdf_parser import PdfParser
from documents.services.file_hash import get_or_create_file_report
from documents.services.title_validation import TitleValidationService
from documents.utils import save_parsed_document, get_or_create_unified_document
from documents.services.pdf_parser import PdfParser
from documents.services.visual_validator import VisualContentValidator
from documents.services.figure_placement_service import FigurePlacementVerifier
from documents.serializers import DocumentUploadSerializer, TitleComparisonSerializer, SectionValidationSerializer, SectionValidationSerializer, UploadSerializer
from documents.services.docx_parser import DocxParser
from documents.services.pdf_parser import PdfParser
from documents.services.title_validation import TitleValidationService
from documents.services.section_validator import SectionValidator
from documents.services.google_search_validator import GoogleSearchValidator
from documents.services.section_validator import SectionValidator
from documents.services.reference_validator import ReferenceValidatorService
from documents.services.calculation import CalculationValidator
from documents.services.accessibility_validator import AccessibilityValidator
from documents.validator.OllamaValidator import AICalculationValidator
from documents.validator.CodeValidator import AICodeValidator
from documents.services.grammar_checker import GrammarAnalysisService
from documents.services.visual_comparator import VisualComparator

class BaseDocumentParserView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    def handle(self, serializer: DocumentUploadSerializer) -> Response:  # pragma: no cover
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.handle(serializer)


class DocxParseView(BaseDocumentParserView):
    parser = DocxParser()

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Parsed DOCX payload",
                examples=[
                    OpenApiExample(
                        "DocxParseResponse",
                        value={
                            "source_type": "docx",
                            "metadata": {"author": "Jane Doe"},
                            "sections": [
                                {
                                    "title": "Executive Summary",
                                    "level": 1,
                                    "paragraphs": ["Overview paragraph..."],
                                    "children": [],
                                }
                            ],
                            "text": {
                                "full_text": "Full concatenated text...",
                                "paragraphs": ["Paragraph 1", "Paragraph 2"],
                            },
                            "tables": [
                                {
                                    "id": "table-1",
                                    "row_count": 2,
                                    "column_count": 3,
                                    "data": [["H1", "H2", "H3"], ["R1C1", "R1C2", "R1C3"]],
                                }
                            ],
                            "images": [
                                {
                                    "id": "docx-image-123",
                                    "mime_type": "image/png",
                                    "width": 600,
                                    "height": 400,
                                }
                            ],
                            "extras": {
                                "paragraph_count": 12,
                                "section_count": 3,
                                "table_count": 1,
                                "image_count": 1,
                            },
                        },
                    )
                ],
            )
        },
    )
    def handle(self, serializer: DocumentUploadSerializer) -> Response:
        file_obj = serializer.validated_data["file"]
        if not file_obj.name.lower().endswith(".docx"):
            raise ValidationError("Upload a .docx file to this endpoint.")

        unified_doc = self.parser.parse(file_obj)
        response_data = unified_doc.to_representation()

        # Optionally save to database
        if serializer.validated_data.get("save_document", False):
            parsed_doc = save_parsed_document(file_obj, unified_doc)
            response_data["saved_document_id"] = parsed_doc.id
            response_data["document_id"] = parsed_doc.document.id

        return Response(response_data, status=status.HTTP_200_OK)


class ParsedDocumentListView(ListAPIView):
    """List all parsed documents stored in the database."""

    queryset = ParsedDocument.objects.select_related("document").all()
    serializer_class = ParsedDocumentSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        description="Retrieve a list of all parsed documents stored in the database.",
        responses={200: ParsedDocumentSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ParsedDocumentRetrieveView(RetrieveAPIView):
    """Retrieve a specific parsed document by ID."""

    queryset = ParsedDocument.objects.select_related("document").all()
    serializer_class = ParsedDocumentSerializer
    permission_classes = [AllowAny]
    lookup_field = "pk"

    @extend_schema(
        description="Retrieve a specific parsed document by its ID.",
        responses={
            200: ParsedDocumentSerializer,
            404: OpenApiResponse(description="Document not found"),
        },
    )
    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except ParsedDocument.DoesNotExist:
            raise NotFound("Parsed document not found.")

class DocxGrammarCheckView(BaseDocumentParserView):
    parser = DocxParser()

    def handle(self, serializer):
        file_obj = serializer.validated_data["file"]

        if not file_obj.name.lower().endswith(".docx"):
            raise ValidationError("Upload a .docx file to this endpoint.")

        # 1) Try to serve from cached grammar report (no re-parse, no re-analysis)
        cache_info = get_or_create_file_report(file_obj, "docx-grammer-validation")
        if cache_info.get("from_cache"):
            analyzed_segments = cache_info.get("report_data") or []
        else:
            # 2) Parse (or load) the document once using the shared parser cache
            unified_doc, _ = get_or_create_unified_document(
                file_obj,
                enable_ocr=serializer.validated_data.get("enable_ocr", True),
            )
            parsed_data = unified_doc.to_representation()

            paragraphs = parsed_data.get("text", {}).get("paragraphs", [])
            if not paragraphs:
                full_text = parsed_data.get("text", {}).get("full_text", "")
                if full_text:
                    paragraphs = [full_text]

            analyzed_segments = []

            for index, paragraph in enumerate(paragraphs):
                analysis = GrammarAnalysisService.analyze_segment(paragraph)

                if analysis["has_errors"]:
                    analyzed_segments.append(
                        {
                            "paragraph_number": index + 1,
                            "original_text": paragraph,
                            "spelling_errors": analysis["spelling_errors"],
                            "grammar_errors": analysis["grammar_errors"],
                            "corrected_text": analysis["corrected_text"],
                            "readability_scores": analysis["readability_scores"],
                        }
                    )

            # 3) Persist grammar report keyed by file hash for future calls
            get_or_create_file_report(
                file_obj, "docx-grammer-validation", analyzed_segments
            )

        return Response(
            {
                "source_type": "docx",
                "language_check": "en-US & en-GB (Permissive)",
                "total_segments": len(analyzed_segments),
                "results": analyzed_segments,
            }
        )


class PdfParseView(BaseDocumentParserView):
    parser = PdfParser()

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Parsed PDF payload",
                examples=[
                    OpenApiExample(
                        "PdfParseResponse",
                        value={
                            "source_type": "pdf",
                            "metadata": {"author": "Acme Analyst", "page_count": 4},
                            "sections": [
                                {
                                    "title": "Findings",
                                    "level": 1,
                                    "paragraphs": ["Summary line..."],
                                    "children": [
                                        {
                                            "title": "Data Issues",
                                            "level": 2,
                                            "paragraphs": ["Details..."],
                                            "children": [],
                                        }
                                    ],
                                }
                            ],
                            "text": {
                                "full_text": "Full PDF text ...",
                                "pages": [
                                    {
                                        "page_number": 1,
                                        "text": "Page 1 text",
                                        "layout": {
                                            "words": {
                                                "Helvetica-Bold": {
                                                    "text": ["Headline"],
                                                    "font_size": 16.0,
                                                },
                                                "Helvetica": {
                                                    "text": ["Body", "text"],
                                                    "font_sizes": [12.0, 12.5],
                                                },
                                            },
                                            "order": ["Helvetica-Bold", "Helvetica"],
                                            "font": "Helvetica",
                                            "fonts": ["Helvetica", "Helvetica-Bold"],
                                            "font_sizes": [12.0, 12.5, 16.0],
                                        },
                                    }
                                ],
                            },
                            "tables": [
                                {
                                    "id": "pdf-table-1-1",
                                    "page_number": 1,
                                    "row_count": 3,
                                    "column_count": 4,
                                    "data": [["Col1", "Col2"], ["Val1", "Val2"]],
                                }
                            ],
                            "images": [
                                {
                                    "id": "pdf-image-1-1",
                                    "mime_type": "image/png",
                                    "width": 512,
                                    "height": 256,
                                }
                            ],
                            "extras": {
                                "page_count": 4,
                                "table_count": 1,
                                "image_count": 2,
                                "ocr_applied": False,
                            },
                        },
                    )
                ],
            )
        },
    )
    def handle(self, serializer: DocumentUploadSerializer) -> Response:
        file_obj = serializer.validated_data["file"]
        if not file_obj.name.lower().endswith(".pdf"):
            raise ValidationError("Upload a .pdf file to this endpoint.")

        unified_doc = self.parser.parse(
            file_obj, enable_ocr=serializer.validated_data.get("enable_ocr", True)
        )
        response_data = unified_doc.to_representation()

        # Optionally save to database
        if serializer.validated_data.get("save_document", False):
            parsed_doc = save_parsed_document(file_obj, unified_doc)
            response_data["saved_document_id"] = parsed_doc.id
            response_data["document_id"] = parsed_doc.document.id

        return Response(response_data, status=status.HTTP_200_OK)


class ParsedDocumentListView(ListAPIView):
    """List all parsed documents stored in the database."""

    queryset = ParsedDocument.objects.select_related("document").all()
    serializer_class = ParsedDocumentSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        description="Retrieve a list of all parsed documents stored in the database.",
        responses={200: ParsedDocumentSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ParsedDocumentRetrieveView(RetrieveAPIView):
    """Retrieve a specific parsed document by ID."""

    queryset = ParsedDocument.objects.select_related("document").all()
    serializer_class = ParsedDocumentSerializer
    permission_classes = [AllowAny]
    lookup_field = "pk"

    @extend_schema(
        description="Retrieve a specific parsed document by its ID.",
        responses={
            200: ParsedDocumentSerializer,
            404: OpenApiResponse(description="Document not found"),
        },
    )
    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except ParsedDocument.DoesNotExist:
            raise NotFound("Parsed document not found.")
        return Response(document.to_representation(), status=status.HTTP_200_OK)

class PdfGrammarCheckView(BaseDocumentParserView):
    parser = PdfParser()

    def handle(self, serializer):
        file_obj = serializer.validated_data["file"]

        if not file_obj.name.lower().endswith(".pdf"):
            raise ValidationError("Upload a .pdf file to this endpoint.")

        # 1) Try cached PDF grammar report first
        cache_info = get_or_create_file_report(file_obj, "pdf-grammer-validation")
        if cache_info.get("from_cache"):
            analyzed_pages = cache_info.get("report_data") or []
        else:
            # 2) Parse (or load) unified document once via shared cache
            unified_doc, _ = get_or_create_unified_document(
                file_obj,
                enable_ocr=serializer.validated_data.get("enable_ocr", True),
            )
            parsed_data = unified_doc.to_representation()
            pages = parsed_data.get("text", {}).get("pages", [])

            analyzed_pages = []

            for page in pages:
                page_num = page.get("page_number", "Unknown")
                text = page.get("text", "")

                analysis = GrammarAnalysisService.analyze_segment(text)

                if analysis["has_errors"]:
                    analyzed_pages.append(
                        {
                            "page": page_num,
                            "original_text": text,
                            "spelling_errors": analysis["spelling_errors"],
                            "grammar_errors": analysis["grammar_errors"],
                            "corrected_text": analysis["corrected_text"],
                            "readability_scores": analysis["readability_scores"],
                        }
                    )

            # 3) Persist analyzed pages keyed by file hash
            get_or_create_file_report(
                file_obj, "pdf-grammer-validation", analyzed_pages
            )

        return Response(
            {
                "source_type": "pdf",
                "language_check": "en-US & en-GB (Permissive)",
                "total_pages": len(analyzed_pages),
                "results": analyzed_pages,
            }
        )

class TitleValidationView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Title validation response",
                examples=[
                    OpenApiExample(
                        "TitleValidationResponse",
                        value={
                            "title": "Validated title",
                            "is_valid": True,
                            "reason": "Title is valid",
                        },
                    )
                ],
            )
        },
    )

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data["file"]
        # First, try to reuse cached title validation for this file
        cache_info = get_or_create_file_report(file_obj, "title_validation")
        if cache_info.get("from_cache"):
            title = cache_info.get("report_data")
        else:
            title = TitleValidationService().validate_and_extract_title(file_obj)
            get_or_create_file_report(file_obj, "title_validation", title)

        if not title:
            return Response({"title": None, "is_valid": False, "reason": "Title not found"})
        return Response({"title": title, "is_valid": True, "reason": "Title is valid"})


class TitleComparisonView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = TitleComparisonSerializer

    @extend_schema(
        request=TitleComparisonSerializer,
        responses={
            200: OpenApiResponse(
                description="Title comparison response",
                examples=[
                    OpenApiExample(
                        "TitleComparisonResponse",
                        value={
                            "file_1_title": "Title A",
                            "file_2_title": "Title A",
                            "match": True,
                        },
                    )
                ],
            )
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_1 = serializer.validated_data["file_1"]
        file_2 = serializer.validated_data["file_2"]
        
        service = TitleValidationService()
        title_1 = service.validate_and_extract_title(file_1)
        title_2 = service.validate_and_extract_title(file_2)
        
        # Normalize for comparison (ignore case and whitespace)
        t1_norm = (title_1 or "").strip().lower()
        t2_norm = (title_2 or "").strip().lower()
        
        match = t1_norm == t2_norm and bool(t1_norm)
        
        return Response({
            "file_1_title": title_1,
            "file_2_title": title_2,
            "match": match
        })


class SectionValidationView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = SectionValidationSerializer

    @extend_schema(
        request=SectionValidationSerializer,
        responses={
            200: OpenApiResponse(
                description="Section validation response",
                examples=[
                    OpenApiExample(
                        "SectionValidationResponse",
                        value={
                            "completeness_score": 85.5,
                            "missing_sections": ["Conclusion"],
                            "present_sections": ["Introduction", "Results"],
                            "details": {"total_required": 3, "found_count": 2},
                        },
                    )
                ],
            )
        },
    )
    def post(self, request, *args, **kwargs):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            file_obj = serializer.validated_data["file"]
            required_sections = serializer.validated_data.get("required_sections")
            
            # Handle JSON string from frontend
            if isinstance(required_sections, str):
                import json
                try:
                    required_sections = json.loads(required_sections)
                except json.JSONDecodeError:
                    required_sections = None

            # If we already have a cached section validation for this file, reuse it
            cache_info = get_or_create_file_report(file_obj, "section_validation")
            if cache_info.get("from_cache"):
                cached_result = cache_info.get("report_data") or {}
                return Response(cached_result, status=status.HTTP_200_OK)

            # Ensure supported type and obtain (or build) unified document from cache
            lower_name = file_obj.name.lower()
            if not (lower_name.endswith(".docx") or lower_name.endswith(".pdf")):
                raise ValidationError(
                    "Unsupported file type. Only DOCX and PDF files are supported."
                )

            unified_doc, _ = get_or_create_unified_document(file_obj)
            sections_data = [s.to_representation() for s in unified_doc.sections]

            validator = SectionValidator(required_sections=required_sections)
            result = validator.validate(sections_data)
            
            if hasattr(result, 'to_dict'):
                result_dict = result.to_dict()
            else:
                result_dict = result
            
            get_or_create_file_report(file_obj, "section_validation", result_dict)
            return Response(result_dict, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({
                "error": str(e),
                "completeness_score": 0,
                "missing_sections": [],
                "present_sections": [],
                "details": {"total_required": 0, "found_count": 0}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class GoogleSearchValidationView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Google Search validation response",
                examples=[
                    OpenApiExample(
                        "GoogleSearchValidationResponse",
                        value={
                            "total_sentences_checked": 1,
                            "results": [
                                {
                                    "title": "Design of Vhcl AdtaR-TmEryNS",
                                    "found": True
                                }
                            ]
                        },
                    )
                ],
            )
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data["file"]
        lower_name = file_obj.name.lower()

        # 0. Try to reuse cached Google search validation for this file
        cache_info = get_or_create_file_report(file_obj, "google_search_validation")
        if cache_info.get("from_cache"):
            cached_results = cache_info.get("report_data") or []
            return Response(
                {
                    "total_sentences_checked": len(cached_results),
                    "results": cached_results,
                }
            )

        # 1. Parse (or load) unified document to get full text
        if not (lower_name.endswith(".docx") or lower_name.endswith(".pdf")):
            raise ValidationError("Unsupported file type. Use .docx or .pdf")

        unified_doc, _ = get_or_create_unified_document(file_obj)
        text = unified_doc.text.get("full_text", "") or ""

        # 2. Extract title
        service = TitleValidationService()
        title = service.validate_and_extract_title(file_obj)
        print(f"DEBUG: title in view: {title}")
        
        # 3. Validate with Google Search
        validator = GoogleSearchValidator()
        result = validator.validate_title(title)
        results = [result]  # Wrap in list for consistent response format
        
        get_or_create_file_report(file_obj, "google_search_validation", results)
        return Response(
            {
                "total_sentences_checked": len(results),
                "results": results,
            }
        )

class FormattingComparisonView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = FormattingComparisonSerializer
    service_class = FormattingComparisonService

    @extend_schema(
        request=FormattingComparisonSerializer,
        responses={
            200: OpenApiResponse(
                description="Formatting comparison response",
                examples=[
                    OpenApiExample(
                        "FormattingComparisonResponse",
                        value={
                            "documents": [
                                {
                                    "label": "file_1",
                                    "original_name": "ce_a.docx",
                                    "source_type": "docx",
                                    "fonts": {"primary": "Calibri", "values": ["Calibri"]},
                                    "font_sizes": {"primary": 11.0, "values": [11.0]},
                                    "margins": {
                                        "top": 72.0,
                                        "bottom": 72.0,
                                        "left": 90.0,
                                        "right": 72.0,
                                        "units": "pt",
                                    },
                                    "indentation": {
                                        "left": {"primary": 0.0, "values": [0.0]},
                                        "right": {"primary": 0.0, "values": [0.0]},
                                        "first_line": {"primary": 36.0, "values": [36.0]},
                                        "units": "pt",
                                    },
                                    "spacing": {
                                        "line": {"primary": 14.0, "values": [14.0]},
                                        "before": {"primary": 0.0, "values": [0.0]},
                                        "after": {"primary": 8.0, "values": [8.0]},
                                        "units": "pt",
                                    },
                                    "warnings": [],
                                },
                                {
                                    "label": "file_2",
                                    "original_name": "ce_b.docx",
                                    "source_type": "docx",
                                    "fonts": {"primary": "Calibri", "values": ["Calibri"]},
                                    "font_sizes": {"primary": 11.0, "values": [11.0]},
                                    "margins": {
                                        "top": 60.0,
                                        "bottom": 60.0,
                                        "left": 90.0,
                                        "right": 72.0,
                                        "units": "pt",
                                    },
                                    "indentation": {
                                        "left": {"primary": 0.0, "values": [0.0]},
                                        "right": {"primary": 0.0, "values": [0.0]},
                                        "first_line": {"primary": 36.0, "values": [36.0]},
                                        "units": "pt",
                                    },
                                    "spacing": {
                                        "line": {"primary": 14.0, "values": [14.0]},
                                        "before": {"primary": 0.0, "values": [0.0]},
                                        "after": {"primary": 8.0, "values": [8.0]},
                                        "units": "pt",
                                    },
                                    "warnings": [],
                                },
                                {
                                    "label": "file_3",
                                    "original_name": "ce_c.pdf",
                                    "source_type": "pdf",
                                    "fonts": {"primary": "Calibri", "values": ["Calibri"]},
                                    "font_sizes": {"primary": 11.0, "values": [11.0]},
                                    "margins": {
                                        "top": 72.0,
                                        "bottom": 72.0,
                                        "left": 90.0,
                                        "right": 72.0,
                                        "units": "pt",
                                    },
                                    "indentation": {
                                        "left": {"primary": 0.0, "values": [0.0]},
                                        "right": {"primary": None, "values": []},
                                        "first_line": {"primary": 0.0, "values": [0.0]},
                                        "units": "pt",
                                    },
                                    "spacing": {
                                        "line": {"primary": 14.0, "values": [14.0]},
                                        "before": {"primary": None, "values": []},
                                        "after": {"primary": None, "values": []},
                                        "units": "pt",
                                    },
                                    "warnings": [],
                                },
                            ],
                            "consistency": {
                                "fonts_match": True,
                                "font_sizes_match": True,
                                "margins_match": False,
                                "indentation_match": True,
                                "spacing_match": True,
                                "all_match": False,
                                "details": {
                                    "line_spacing_match": True,
                                    "indent_left_match": True,
                                    "indent_first_line_match": True,
                                },
                                "mismatched_metrics": ["margins_match"],
                                "tolerances": {
                                    "margin_pt": 0.5,
                                    "font_size_pt": 0.2,
                                    "line_spacing_pt": 0.5,
                                },
                            },
                        },
                    )
                ],
            )
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = self.service_class()
        comparison = service.compare(
            {
                "file_1": serializer.validated_data["file_1"],
                "file_2": serializer.validated_data["file_2"],
                "file_3": serializer.validated_data.get("file_3"),
            }
        )
        
        # Persist results for each file
        files_map = {
            "file_1": serializer.validated_data["file_1"],
            "file_2": serializer.validated_data["file_2"],
            "file_3": serializer.validated_data.get("file_3"),
        }
        
        documents_stats = comparison.get("documents", [])
        for doc_stat in documents_stats:
            label = doc_stat.get("label")
            if label in files_map and files_map[label]:
                get_or_create_file_report(files_map[label], "formatting_validation", doc_stat)
                
        return Response(comparison)

class VisualValidationView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = DocumentUploadSerializer  

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(description="Validation Report generated successfully"),
            400: OpenApiResponse(description="Invalid file or validation error")
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_obj = serializer.validated_data['file']
        filename = file_obj.name.lower()
        
        # Reuse cached visual validation if already computed for this file
        cache_info = get_or_create_file_report(file_obj, "visual_validation")
        if cache_info.get("from_cache"):
            report = cache_info.get("report_data") or {}
            return Response(
                {
                    "status": "success",
                    "filename": filename,
                    "source_type": "pdf" if filename.endswith('.pdf') else "docx",
                    "validation_report": report,
                }
            )

        validator = VisualContentValidator()

        try:
            if filename.endswith('.pdf'):
                report = validator.validate_pdf(file_obj)
                get_or_create_file_report(file_obj, "visual_validation", report)
            elif filename.endswith('.docx'):
                report = validator.validate_docx(file_obj)
                get_or_create_file_report(file_obj, "visual_validation", report)
            else:
                raise ValidationError("Unsupported file type. Please upload .pdf or .docx")

            return Response(
                {
                    "status": "success",
                    "filename": filename,
                    "source_type": "pdf" if filename.endswith('.pdf') else "docx",
                    "validation_report": report,
                }
            )

        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=400)

class DocumentAnalysisView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    serializer_class = UploadSerializer

    @extend_schema(
        request=UploadSerializer,
        responses={
            200: OpenApiResponse(description="Validation Report"),
            400: OpenApiResponse(description="Error")
        }
    )
    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        
        if serializer.is_valid():
            uploaded_file = serializer.validated_data['file']

            # --- ROBUST BOOLEAN EXTRACTION ---
            # 1. Try to get boolean from validated data
            ce_provided = serializer.validated_data.get('ce_activity_date_provided')

            # 2. Fallback: If validated data is None/False, check raw request data 
            # (Because HTML forms send "on" or "true" strings, sometimes missed by serializer)
            if not ce_provided:
                raw_val = request.data.get('ce_activity_date_provided')
                if str(raw_val).lower() in ['true', 'on', '1']:
                    ce_provided = True

            try:
                lower_name = uploaded_file.name.lower()

                # Initialize validator configuration (independent of parsing)
                validator = ReferenceValidatorService(
                    project_date=None,
                    passout_date=None,
                    ce_activity_date_provided=ce_provided
                )

                # 1) If report already exists for this file, reuse it (no re-parse)
                cache_info = get_or_create_file_report(
                    uploaded_file, "reference_validation"
                )
                if cache_info.get("from_cache"):
                    report = cache_info.get("report_data") or {}
                else:
                    # 2) Ensure supported type and obtain (or build) unified document
                    if not (lower_name.endswith('.docx') or lower_name.endswith('.pdf')):
                        return Response({"error": "Unsupported file type"}, status=400)

                    unified_doc, _ = get_or_create_unified_document(uploaded_file)
                    full_text = unified_doc.text.get("full_text", "") or ""

                    report = validator.process_document_text(full_text)
                    get_or_create_file_report(
                        uploaded_file, "reference_validation", report
                    )

                return Response(
                    {
                        "status": "success",
                        "filename": uploaded_file.name,
                        "config_used": {
                            "date_used": str(validator.project_date),
                            "ce_provided": validator.ce_activity_date_provided,
                        },
                        "report": report,
                    },
                    status=status.HTTP_200_OK,
                )

            except Exception as e:
                return Response({"status": "error", "message": str(e)}, status=500)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CalculationValidationView(APIView):
    """
    API endpoint to validate mathematical calculations in PDF or DOCX documents.
    Extracts calculations from text and tables, validates them, and returns a detailed report.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    @extend_schema(
        summary="Validate Calculations in Document",
        description=(
            "Upload a PDF or DOCX document to extract and validate mathematical calculations. "
            "The validator checks:\n"
            "- Basic arithmetic operations (addition, subtraction, multiplication, division)\n"
            "- Percentage calculations\n"
            "- Table totals and sums\n\n"
            "Returns a detailed report with accuracy statistics and identified issues."
        ),
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Calculation validation report",
                examples=[
                    OpenApiExample(
                        "CalculationValidationResponse",
                        value={
                            "status": "success",
                            "filename": "financial_report.pdf",
                            "source_type": "pdf",
                            "validation_report": {
                                "summary": {
                                    "total_calculations": 15,
                                    "correct_calculations": 13,
                                    "incorrect_calculations": 2,
                                    "accuracy_percentage": 86.67
                                },
                                "issues": [
                                    {
                                        "expression": "100 + 50 = 160",
                                        "expected_result": 150.0,
                                        "actual_result": 160.0,
                                        "difference": 10.0,
                                        "location": "Page 2",
                                        "issue_type": "basic_arithmetic",
                                        "severity": "medium"
                                    }
                                ],
                                "all_calculations": [
                                    {
                                        "expression": "100 + 50 = 150",
                                        "expected_result": 150.0,
                                        "actual_result": 150.0,
                                        "is_correct": True,
                                        "location": "Page 1",
                                        "calculation_type": "basic_arithmetic",
                                        "tolerance": 0.01,
                                        "context": {}
                                    }
                                ]
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="Invalid file or unsupported format")
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_obj = serializer.validated_data['file']
        filename = file_obj.name.lower()
        
        # Optional: Allow custom tolerance
        tolerance = float(request.data.get('tolerance', 0.01))
        
        # Parse document based on type (using cached unified document when available)
        try:
            if filename.endswith('.pdf'):
                source_type = 'pdf'
            elif filename.endswith('.docx'):
                source_type = 'docx'
            else:
                raise ValidationError(
                    "Unsupported file type. Please upload .pdf or .docx"
                )

            unified_doc, _ = get_or_create_unified_document(
                file_obj, enable_ocr=True
            )
            
            # Initialize validator
            validator = CalculationValidator(tolerance=tolerance)
            all_results = []
            
            # Extract calculations from text
            if source_type == 'pdf':
                pages = unified_doc.text.get('pages', [])
                for page in pages:
                    page_num = page.get('page_number', 'unknown')
                    text = page.get('text', '')
                    if text:
                        results = validator.extract_calculations_from_text(
                            text, 
                            location=f"Page {page_num}"
                        )
                        all_results.extend(results)
            else:  # docx
                paragraphs = unified_doc.text.get('paragraphs', [])
                full_text = '\n'.join(paragraphs)
                results = validator.extract_calculations_from_text(
                    full_text,
                    location="Document"
                )
                all_results.extend(results)
            
            # Extract calculations from tables
            for table in unified_doc.tables:
                table_id = table.get('id', 'unknown')
                table_data = table.get('data', [])
                if table_data:
                    table_results = validator.extract_calculations_from_table(
                        table_data,
                        location=f"Table {table_id}"
                    )
                    all_results.extend(table_results)
            
            result_data = {
                "status": "success",
                "filename": file_obj.name,
                "source_type": source_type,
                "total_calculations": len(all_results),
                "calculations": [result.to_dict() for result in all_results]
            }
            get_or_create_file_report(file_obj, "math_validation", result_data)
            
            return Response(result_data, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class AccessibilityValidationView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Accessibility Validation Report",
                examples=[
                    OpenApiExample(
                        "AccessibilityReport",
                        value={
                            "status": "success",
                            "source_type": "docx",
                            "report": {
                                "is_compliant": False,
                                "accessibility_score": 85,
                                "total_issues": 2,
                                "issues": [
                                    {
                                        "location": "Image #1",
                                        "issue": "Missing Alt Text",
                                    },
                                    {
                                        "location": "Paragraph #5",
                                        "issue": "Non-descriptive link text ('click here')"
                                    }
                                ]
                            }
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="Invalid file or format"),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data["file"]
        filename = file_obj.name.lower()

        if not (filename.endswith('.pdf') or filename.endswith('.docx')):
            raise ValidationError("Unsupported file type. Please upload .pdf or .docx")

        # If we've already computed accessibility validation for this file, reuse it
        cache_info = get_or_create_file_report(
            file_obj, "accessibility_validation"
        )
        if cache_info.get("from_cache"):
            cached_response = cache_info.get("report_data") or {}
            return Response(cached_response, status=status.HTTP_200_OK)

        try:
            validator = AccessibilityValidator()
            report = validator.validate(file_obj)

            response_data = {
                "status": "success",
                "source_type": "pdf" if filename.endswith('.pdf') else "docx",
                "report": report
            }
            get_or_create_file_report(file_obj, "accessibility_validation", response_data)

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )

class OllamaCalculationValidationView(APIView):
    """
    Comprehensive mathematical validation using Gemini AI.
    Analyzes entire PDF/DOCX documents and provides confidence-scored validation results.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    @extend_schema(
        summary="AI-Powered Mathematical Validation (Gemini)",
        description=(
            "Upload a PDF or DOCX document to analyze and validate ALL mathematical calculations "
            "using Google Gemini AI. The AI will:\n"
            "- Identify every calculation in the document\n"
            "- Validate each calculation's correctness\n"
            "- Provide confidence scores (0.0 to 1.0) for each validation\n"
            "- Suggest potential issues and recommendations\n\n"
            "Returns a comprehensive report with detailed analysis and confidence metrics."
        ),
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Gemini AI validation report",
                examples=[
                    OpenApiExample(
                        "GeminiValidationResponse",
                        value={
                            "status": "success",
                            "filename": "financial_report.pdf",
                            "source_type": "pdf",
                            "model_used": "gemini-2.0-flash-exp",
                            "total_calculations_found": 8,
                            "validations": [
                                {
                                    "expression": "1000 + 500 = 1500",
                                    "location": "Page 2",
                                    "calculated_result": 1500.0,
                                    "confidence_score": 0.98,
                                    "reasoning": "Simple addition verified correctly",
                                    "potential_issues": []
                                }
                            ],
                            "overall_assessment": {
                                "correct_calculations": 7,
                                "incorrect_calculations": 1,
                                "accuracy_percentage": 87.5,
                                "average_confidence": 0.92,
                                "summary": "Document has high mathematical accuracy with one minor error on Page 3"
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="Invalid file or validation error")
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_obj = serializer.validated_data['file']
        filename = file_obj.name.lower()
        
        try:
            # Parse document based on type using shared unified-document cache
            if filename.endswith('.pdf'):
                source_type = 'pdf'
            elif filename.endswith('.docx'):
                source_type = 'docx'
            else:
                raise ValidationError(
                    "Unsupported file type. Please upload .pdf or .docx"
                )

            unified_doc, _ = get_or_create_unified_document(
                file_obj, enable_ocr=True
            )
            
            # Initialize AI validator
            validator = AICalculationValidator()
            result = validator.analyze_document_math(unified_doc)

            
            # Add metadata
            result["filename"] = file_obj.name
            result["source_type"] = source_type
            res = get_or_create_file_report(file_obj, "math_validation", result)
            
            return Response(result, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class CodeValidationView(APIView):
    """
    Comprehensive code validation using Gemini AI.
    Analyzes entire PDF/DOCX documents and validates all code snippets.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    @extend_schema(
        summary="AI-Powered Code Validation (Gemini)",
        description=(
            "Upload a PDF or DOCX document to extract and validate ALL code snippets "
            "using Google Gemini AI. The AI will:\n"
            "- Identify every code snippet in the document\n"
            "- Detect programming language automatically\n"
            "- Validate syntax and logical correctness\n"
            "- Provide confidence scores (0.0 to 1.0) for each validation\n"
            "- Suggest improvements and best practices\n\n"
            "Returns a comprehensive report with detailed analysis and confidence metrics."
        ),
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Gemini AI code validation report",
                examples=[
                    OpenApiExample(
                        "CodeValidationResponse",
                        value={
                            "status": "success",
                            "filename": "tutorial.pdf",
                            "source_type": "pdf",
                            "model_used": "gemini-2.0-flash-exp",
                            "total_code_snippets_found": 5,
                            "validations": [
                                {
                                    "code": "def add(a, b):\n    return a + b",
                                    "language": "python",
                                    "location": "Page 3",
                                    "is_valid": True,
                                    "confidence_score": 0.95,
                                    "reasoning": "Syntactically correct Python function",
                                    "issues": [],
                                    "suggestions": ["Add type hints for better code quality"]
                                }
                            ],
                            "overall_assessment": {
                                "valid_snippets": 4,
                                "invalid_snippets": 1,
                                "accuracy_percentage": 80.0,
                                "average_confidence": 0.88,
                                "summary": "Most code snippets are valid with minor style improvements suggested"
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(description="Invalid file or validation error")
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_obj = serializer.validated_data['file']
        filename = file_obj.name.lower()
        
        try:
            # Parse document based on type using shared unified-document cache
            if filename.endswith('.pdf'):
                source_type = 'pdf'
            elif filename.endswith('.docx'):
                source_type = 'docx'
            else:
                raise ValidationError(
                    "Unsupported file type. Please upload .pdf or .docx"
                )

            unified_doc, _ = get_or_create_unified_document(
                file_obj, enable_ocr=True
            )
            
            # Initialize AI code validator
            validator = AICodeValidator()
            result = validator.analyze_document_code(unified_doc)
            
            # Add metadata
            result["filename"] = file_obj.name
            result["source_type"] = source_type
            res= get_or_create_file_report(file_obj, "code_validation", result)
            
            return Response(result, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class ReportGenerationView(APIView):
    """
    Generate beautiful HTML report from cached validation data.
    Accepts file upload, checks if hash exists, and generates report.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = DocumentUploadSerializer

    @extend_schema(
        request=DocumentUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="HTML report generated successfully",
                examples=[
                    OpenApiExample(
                        "ReportGenerationResponse",
                        value="<html>...</html>"
                    )
                ]
            ),
            404: OpenApiResponse(description="Report data not found")
        }
    )
    def post(self, request, *args, **kwargs):
        """
        Generate report from uploaded file.
        Checks if file hash exists in hashFiles directory.
        If exists, generates report from cached data.
        If not, creates empty JSON structure and returns empty report.
        """        
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data["file"]
        
        try:
            # Get file hash
            file_hash = get_file_hash(file_obj)
            
            # Try to load existing report data
            try:
                report_data = get_report_data_by_hash(file_hash)
            except FileNotFoundError:
                # Hash file doesn't exist, create empty structure
                report_data = {"reports": {}}
                # Save empty structure to create the hash file
                get_or_create_file_report(file_obj, "_initialized", {})
            
            # Generate HTML report
            html_content = generate_html_report(report_data, filename=file_obj.name)
            
            # Return HTML response
            return HttpResponse(html_content, content_type='text/html')
            
        except Exception as e:
            return Response({
                "status": "error",
                "message": f"Failed to generate report: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VisualComparisonView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = TitleComparisonSerializer  # Reusing file_1/file_2 serializer

    @extend_schema(
        request=TitleComparisonSerializer,
        responses={
            200: OpenApiResponse(
                description="Visual comparison response",
                examples=[
                    OpenApiExample(
                        "VisualComparisonResponse",
                        value={
                            "summary": {
                                "file_1_total_images": 5,
                                "file_2_total_images": 5,
                                "common_images_count": 5,
                                "similarity_score": 100.0
                            }
                        },
                    )
                ],
            )
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_1 = serializer.validated_data["file_1"]
        file_2 = serializer.validated_data["file_2"]

        comparator = VisualComparator()
        try:
            result = comparator.compare(file_1, file_2)

            # Persist results to File 1's report
            summary_1 = result["summary"].copy()
            summary_1["current_file_images"] = summary_1.get("file_1_total_images", 0)
            summary_1["other_file_images"] = summary_1.get("file_2_total_images", 0)
            
            get_or_create_file_report(file_1, "visual_comparison", {
                "compared_with": file_2.name,
                "summary": summary_1,
                "timestamp": str(datetime.now())
            })

            # Persist results to File 2's report
            summary_2 = result["summary"].copy()
            summary_2["current_file_images"] = summary_2.get("file_2_total_images", 0)
            summary_2["other_file_images"] = summary_2.get("file_1_total_images", 0)

            get_or_create_file_report(file_2, "visual_comparison", {
                "compared_with": file_1.name,
                "summary": summary_2,
                "timestamp": str(datetime.now())
            })

            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
class FigurePlacementValidationView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]
    serializer_class = FigureUploadSerializer 

    @extend_schema(
        summary="Validate Figure Caption Placement",
        request=FigureUploadSerializer,
        responses={
            200: OpenApiResponse(
                description="Shortened placement report",
                examples=[
                    OpenApiExample(
                        "SuccessResponse",
                        value={
                            "file_name": "report.docx",
                            "all_valid": False,
                            "total_figures": 2,
                            "placements_above": 1,
                            "placements_below": 1,
                            "accuracy_percentage": 50.0,
                            "details": [
                                {"caption": "Figure 1: Site Map", "placement": "BELOW", "is_valid": True},
                                {"caption": "Figure 2: Chart", "placement": "ABOVE", "is_valid": False}
                            ]
                        },
                    )
                ],
            )
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_obj = serializer.validated_data['file']
        
        # Parse and verify
        doc_data = DocxParser().parse(file_obj)
        result = FigurePlacementVerifier().verify_placement(doc_data.text["paragraphs"])
        
        # Persist for report generation
        get_or_create_file_report(file_obj, "figure_placement", result)

        return Response({
            "file_name": file_obj.name,
            **result
        }, status=status.HTTP_200_OK)