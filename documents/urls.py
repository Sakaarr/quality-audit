from django.urls import path
from documents.views import (
    AccessibilityValidationView,
    CalculationValidationView,
    CodeValidationView,
    DocxGrammarCheckView,
    DocxParseView,
    FormattingComparisonView,
    GoogleSearchValidationView,
    OllamaCalculationValidationView,
    ParsedDocumentListView,
    ParsedDocumentRetrieveView,
    PdfGrammarCheckView,
    PdfParseView,
    ReportGenerationView,
    SectionValidationView,
    TitleComparisonView,
    TitleValidationView,
    VisualValidationView,
    DocumentAnalysisView,
    AccessibilityValidationView,
    VisualComparisonView,
    FileCompareView,
    FigurePlacementValidationView,
    TablePlacementValidationView,
)


urlpatterns = [
    path("docx/parse/", DocxParseView.as_view(), name="docx-parse"),
    path("pdf/parse/", PdfParseView.as_view(), name="pdf-parse"),
    path("parsed/", ParsedDocumentListView.as_view(), name="parsed-document-list"),
    path("parsed/<int:pk>/", ParsedDocumentRetrieveView.as_view(), name="parsed-document-detail"),
    
    path("docx/grammar-check/", DocxGrammarCheckView.as_view(), name="docx-grammar-check"),
    path("pdf/grammar-check/", PdfGrammarCheckView.as_view(), name="pdf-grammar-check"),


    path("title/validate/", TitleValidationView.as_view(), name="title-validate"),
    path("title/compare/", TitleComparisonView.as_view(), name="title-compare"),
    path("section/validate/", SectionValidationView.as_view(), name="section-validate"),
    path("validate-google-search/", GoogleSearchValidationView.as_view(), name="validate-google-search"),
    path(
        "format/compare/",
        FormattingComparisonView.as_view(),
        name="format-compare",
    ),
    path("section/validate/", SectionValidationView.as_view(), name="section-validate"),

    path('visuals/validate/', VisualValidationView.as_view(), name='validate-visuals'),
    path('visual/compare/', VisualComparisonView.as_view(), name='visual-compare'),
    path('reference/validate/', DocumentAnalysisView.as_view(), name='reference-validate'),
    path('accessibility/validate/', AccessibilityValidationView.as_view(), name='validate-accessibility'),
    path(
        'validate-calculations/',
        CalculationValidationView.as_view(),
        name='validate-calculations'
    ),
    
    path(
        'validate-math-gemini/',
        OllamaCalculationValidationView.as_view(),
        name='validate-math-gemini'
    ),
    
    path(
        'validate-code/',
        CodeValidationView.as_view(),
        name='validate-code'
    ),
    
    path(
        'report/generate/',
        ReportGenerationView.as_view(),
        name='generate-report'
    ),
    
    path('compare/', FileCompareView.as_view(), name='file_compare'),
    path(
        'figure-placement/validate/',
        FigurePlacementValidationView.as_view(),
        name='figure-placement-validate'
    ),
    path(
        'table-placement/validate/',
        TablePlacementValidationView.as_view(),
        name='table-placement-validate'
    )
]

