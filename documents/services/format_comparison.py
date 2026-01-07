from __future__ import annotations

import io
import os
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

import pdfplumber
from docx import Document as DocxDocument
from docx.oxml.ns import qn
from rest_framework.exceptions import ValidationError


class FormattingComparisonService:
    """Inspect document formatting attributes and compare them across files."""

    MARGIN_TOLERANCE_PT = 0.5
    FONT_SIZE_TOLERANCE_PT = 0.2
    LINE_SPACING_TOLERANCE_PT = 0.5

    def compare(self, files: Dict[str, Any], reference_label: str = None) -> Dict[str, Any]:
        """
        Analyze each uploaded file and report formatting consistency.
        
        Args:
            files: Dictionary of file labels to uploaded files
            reference_label: Optional label of the reference file (e.g., 'reference_file').
                           When provided, all other files are compared against this reference.
                           When None, all files are compared together (legacy behavior).
        
        Returns:
            Dictionary with 'documents' (list of analyses) and 'consistency' (comparison results)
        """
        analyses: List[Dict[str, Any]] = []

        for label, uploaded in files.items():
            if uploaded:  # Skip None values
                analyses.append(self._analyze_file(label, uploaded))

        # Determine comparison mode
        if reference_label and reference_label in files and files[reference_label]:
            # Reference-based comparison: compare each file against the reference
            consistency = self._build_reference_comparison_report(analyses, reference_label)
        else:
            # Legacy mode: compare all files together
            consistency = self._build_consistency_report(analyses)
            
        return {"documents": analyses, "consistency": consistency}

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    def _analyze_file(self, label: str, uploaded) -> Dict[str, Any]:
        extension = os.path.splitext(uploaded.name or "")[1].lower()
        if extension not in {".docx", ".pdf"}:
            raise ValidationError(f"{label}: Unsupported file type '{extension}'")

        analyser = (
            self._analyze_docx if extension == ".docx" else self._analyze_pdf
        )
        return analyser(label, uploaded)

    def _analyze_docx(self, label: str, uploaded) -> Dict[str, Any]:
        uploaded.seek(0)
        raw_bytes = uploaded.read()
        uploaded.seek(0)

        try:
            document = DocxDocument(io.BytesIO(raw_bytes))
        except Exception as exc:  # pragma: no cover - docx errors bubble up
            raise ValidationError(f"{label}: Invalid DOCX file") from exc

        font_names: List[str] = []
        font_sizes: List[float] = []
        left_indent: List[float] = []
        right_indent: List[float] = []
        first_line_indent: List[float] = []
        line_spacing: List[float] = []
        spacing_before: List[float] = []
        spacing_after: List[float] = []
        warnings: List[str] = []

        for paragraph in document.paragraphs:
            if not paragraph.text.strip():
                continue

            for run in paragraph.runs:
                font_name = run.font.name or getattr(
                    getattr(paragraph.style, "font", None), "name", None
                )
                normalized_font = self._normalize_font_name(font_name)
                if normalized_font:
                    font_names.append(normalized_font)

                font_size_value = run.font.size or getattr(
                    getattr(paragraph.style, "font", None), "size", None
                )
                size_in_points = self._length_to_points(font_size_value)
                if size_in_points is not None:
                    font_sizes.append(size_in_points)

            fmt = paragraph.paragraph_format
            left_indent_value = self._length_to_points(getattr(fmt, "left_indent", None))
            right_indent_value = self._length_to_points(
                getattr(fmt, "right_indent", None)
            )
            first_line_value = self._length_to_points(
                getattr(fmt, "first_line_indent", None)
            )
            if left_indent_value is not None:
                left_indent.append(left_indent_value)
            if right_indent_value is not None:
                right_indent.append(right_indent_value)
            if first_line_value is not None:
                first_line_indent.append(first_line_value)

            spacing_values = self._extract_paragraph_spacing(paragraph)
            line, before, after = spacing_values
            if line is not None:
                line_spacing.append(line)
            if before is not None:
                spacing_before.append(before)
            if after is not None:
                spacing_after.append(after)

        if not font_names:
            warnings.append(
                "No explicit fonts detected; document may rely on default styles."
            )
        if not font_sizes:
            warnings.append(
                "No explicit font sizes detected; document may rely on default styles."
            )

        sections = list(getattr(document, "sections", []))
        margin_top = self._most_common_value(
            [self._length_to_points(getattr(section, "top_margin", None)) for section in sections]
        )
        margin_bottom = self._most_common_value(
            [self._length_to_points(getattr(section, "bottom_margin", None)) for section in sections]
        )
        margin_left = self._most_common_value(
            [self._length_to_points(getattr(section, "left_margin", None)) for section in sections]
        )
        margin_right = self._most_common_value(
            [self._length_to_points(getattr(section, "right_margin", None)) for section in sections]
        )

        return {
            "label": label,
            "original_name": uploaded.name,
            "source_type": "docx",
            "fonts": self._summarize_strings(font_names),
            "font_sizes": self._summarize_numeric(font_sizes),
            "margins": {
                "top": margin_top,
                "bottom": margin_bottom,
                "left": margin_left,
                "right": margin_right,
                "units": "pt",
            },
            "indentation": {
                "left": self._summarize_numeric(left_indent),
                "right": self._summarize_numeric(right_indent),
                "first_line": self._summarize_numeric(first_line_indent),
                "units": "pt",
            },
            "spacing": {
                "line": self._summarize_numeric(line_spacing),
                "before": self._summarize_numeric(spacing_before),
                "after": self._summarize_numeric(spacing_after),
                "units": "pt",
            },
            "warnings": warnings,
        }

    def _analyze_pdf(self, label: str, uploaded) -> Dict[str, Any]:
        uploaded.seek(0)

        try:
            pdf = pdfplumber.open(uploaded)
        except Exception as exc:  # pragma: no cover
            raise ValidationError(f"{label}: Invalid PDF file") from exc

        font_names: List[str] = []
        font_sizes: List[float] = []
        left_margins: List[float] = []
        right_margins: List[float] = []
        top_margins: List[float] = []
        bottom_margins: List[float] = []
        indentation_left: List[float] = []
        line_spacing: List[float] = []

        warnings: List[str] = []

        with pdf:
            for page in pdf.pages:
                words = page.extract_words(
                    use_text_flow=True,
                    extra_attrs=["fontname", "size", "x0", "x1", "top", "bottom"],
                )
                if not words:
                    continue

                for word in words:
                    normalized_font = self._normalize_font_name(word.get("fontname"))
                    if normalized_font:
                        font_names.append(normalized_font)
                    size_value = word.get("size")
                    if isinstance(size_value, (int, float)):
                        font_sizes.append(round(float(size_value), 2))

                xs0 = [
                    float(word.get("x0", 0))
                    for word in words
                    if isinstance(word.get("x0"), (int, float))
                ]
                xs1 = [
                    float(word.get("x1", 0))
                    for word in words
                    if isinstance(word.get("x1"), (int, float))
                ]
                tops = [
                    float(word.get("top", 0))
                    for word in words
                    if isinstance(word.get("top"), (int, float))
                ]
                bottoms = [
                    float(word.get("bottom", 0))
                    for word in words
                    if isinstance(word.get("bottom"), (int, float))
                ]

                if xs0:
                    left_margins.append(min(xs0))
                if xs1:
                    right_margins.append(page.width - max(xs1))
                if tops:
                    top_margins.append(min(tops))
                if bottoms:
                    bottom_margins.append(page.height - max(bottoms))

                line_entries = self._group_words_into_lines(words)
                indentation_left.extend(
                    entry["left_indent"] for entry in line_entries if entry["left_indent"] is not None
                )
                line_spacing.extend(
                    entry["line_spacing"] for entry in line_entries if entry["line_spacing"] is not None
                )

        if not font_names:
            warnings.append(
                "No font metadata detected; PDF text might be outlined or image-based."
            )
        if not left_margins:
            warnings.append("Unable to derive PDF margins (no text detected).")

        return {
            "label": label,
            "original_name": uploaded.name,
            "source_type": "pdf",
            "fonts": self._summarize_strings(font_names),
            "font_sizes": self._summarize_numeric(font_sizes),
            "margins": {
                "top": self._most_common_value(top_margins),
                "bottom": self._most_common_value(bottom_margins),
                "left": self._most_common_value(left_margins),
                "right": self._most_common_value(right_margins),
                "units": "pt",
            },
            "indentation": {
                "left": self._summarize_numeric(indentation_left),
                "right": {"primary": None, "values": []},
                "first_line": self._summarize_numeric(indentation_left),
                "units": "pt",
            },
            "spacing": {
                "line": self._summarize_numeric(line_spacing),
                "before": {"primary": None, "values": []},
                "after": {"primary": None, "values": []},
                "units": "pt",
            },
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------
    def _build_consistency_report(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not analyses:
            return {
                "fonts_match": True,
                "font_sizes_match": True,
                "margins_match": True,
                "indentation_match": True,
                "spacing_match": True,
                "all_match": True,
                "details": {},
                "mismatched_metrics": [],
            }

        font_match = self._strings_match(
            [doc["fonts"]["primary"] for doc in analyses]
        )
        font_size_match = self._numeric_match(
            [doc["font_sizes"]["primary"] for doc in analyses],
            tolerance=self.FONT_SIZE_TOLERANCE_PT,
        )

        margin_match = self._dict_match(
            [doc["margins"] for doc in analyses], tolerance=self.MARGIN_TOLERANCE_PT
        )

        indent_left_match = self._numeric_match(
            [doc["indentation"]["left"]["primary"] for doc in analyses],
            tolerance=self.MARGIN_TOLERANCE_PT,
            allow_partial=False,
        )
        indent_first_match = self._numeric_match(
            [doc["indentation"]["first_line"]["primary"] for doc in analyses],
            tolerance=self.MARGIN_TOLERANCE_PT,
            allow_partial=False,
        )
        indentation_match = indent_left_match and indent_first_match

        line_spacing_match = self._numeric_match(
            [doc["spacing"]["line"]["primary"] for doc in analyses],
            tolerance=self.LINE_SPACING_TOLERANCE_PT,
            allow_partial=False,
        )

        spacing_match = line_spacing_match

        metrics = {
            "fonts_match": font_match,
            "font_sizes_match": font_size_match,
            "margins_match": margin_match,
            "indentation_match": indentation_match,
            "spacing_match": spacing_match,
        }
        all_match = all(metrics.values())
        metrics["all_match"] = all_match
        metrics["details"] = {
            "line_spacing_match": line_spacing_match,
            "indent_left_match": indent_left_match,
            "indent_first_line_match": indent_first_match,
        }
        metrics["mismatched_metrics"] = [
            key for key, value in metrics.items() if key.endswith("_match") and not value
        ]
        metrics["tolerances"] = {
            "margin_pt": self.MARGIN_TOLERANCE_PT,
            "font_size_pt": self.FONT_SIZE_TOLERANCE_PT,
            "line_spacing_pt": self.LINE_SPACING_TOLERANCE_PT,
        }

        return metrics


    def _build_reference_comparison_report(
        self, analyses: List[Dict[str, Any]], reference_label: str
    ) -> Dict[str, Any]:
        """
        Build comparison report where each file is compared against a reference file.
        
        Args:
            analyses: List of document analyses
            reference_label: Label of the reference document
            
        Returns:
            Dictionary with individual comparison metrics for each file against the reference
        """
        if not analyses:
            return {
                "fonts_match": True,
                "font_sizes_match": True,
                "margins_match": True,
                "indentation_match": True,
                "spacing_match": True,
                "all_match": True,
                "details": {},
                "mismatched_metrics": [],
                "comparison_mode": "reference",
                "reference_file": None,
                "per_file_comparisons": {},
            }

        # Find the reference document
        reference_doc = None
        for doc in analyses:
            if doc["label"] == reference_label:
                reference_doc = doc
                break

        if not reference_doc:
            # Fallback to legacy mode if reference not found
            return self._build_consistency_report(analyses)

        # Store individual comparison results for each CE file
        per_file_comparisons = {}
        
        # Track overall results (for backward compatibility)
        all_fonts_match = True
        all_font_sizes_match = True
        all_margins_match = True
        all_indentation_match = True
        all_spacing_match = True

        for doc in analyses:
            if doc["label"] == reference_label:
                continue  # Skip the reference itself

            # Compare this document against the reference
            font_match = self._strings_match([
                reference_doc["fonts"]["primary"],
                doc["fonts"]["primary"]
            ])
            font_size_match = self._numeric_match(
                [reference_doc["font_sizes"]["primary"], doc["font_sizes"]["primary"]],
                tolerance=self.FONT_SIZE_TOLERANCE_PT,
            )
            margin_match = self._dict_match(
                [reference_doc["margins"], doc["margins"]],
                tolerance=self.MARGIN_TOLERANCE_PT
            )
            indent_left_match = self._numeric_match(
                [
                    reference_doc["indentation"]["left"]["primary"],
                    doc["indentation"]["left"]["primary"]
                ],
                tolerance=self.MARGIN_TOLERANCE_PT,
                allow_partial=False,
            )
            indent_first_match = self._numeric_match(
                [
                    reference_doc["indentation"]["first_line"]["primary"],
                    doc["indentation"]["first_line"]["primary"]
                ],
                tolerance=self.MARGIN_TOLERANCE_PT,
                allow_partial=False,
            )
            indentation_match = indent_left_match and indent_first_match

            line_spacing_match = self._numeric_match(
                [
                    reference_doc["spacing"]["line"]["primary"],
                    doc["spacing"]["line"]["primary"]
                ],
                tolerance=self.LINE_SPACING_TOLERANCE_PT,
                allow_partial=False,
            )
            spacing_match = line_spacing_match

            # Build individual file comparison result
            file_metrics = {
                "fonts_match": font_match,
                "font_sizes_match": font_size_match,
                "margins_match": margin_match,
                "indentation_match": indentation_match,
                "spacing_match": spacing_match,
            }
            file_all_match = all(file_metrics.values())
            file_metrics["all_match"] = file_all_match
            file_metrics["details"] = {
                "line_spacing_match": spacing_match,
                "indent_left_match": indent_left_match,
                "indent_first_line_match": indent_first_match,
            }
            file_metrics["mismatched_metrics"] = [
                key for key, value in file_metrics.items() if key.endswith("_match") and not value
            ]
            
            # Store this file's comparison result
            per_file_comparisons[doc["label"]] = file_metrics

            # Aggregate for overall result
            all_fonts_match = all_fonts_match and font_match
            all_font_sizes_match = all_font_sizes_match and font_size_match
            all_margins_match = all_margins_match and margin_match
            all_indentation_match = all_indentation_match and indentation_match
            all_spacing_match = all_spacing_match and spacing_match

        # Build overall metrics (for backward compatibility)
        metrics = {
            "fonts_match": all_fonts_match,
            "font_sizes_match": all_font_sizes_match,
            "margins_match": all_margins_match,
            "indentation_match": all_indentation_match,
            "spacing_match": all_spacing_match,
        }
        all_match = all(metrics.values())
        metrics["all_match"] = all_match
        metrics["details"] = {
            "line_spacing_match": all_spacing_match,
            "indent_left_match": indent_left_match if 'indent_left_match' in locals() else True,
            "indent_first_line_match": indent_first_match if 'indent_first_match' in locals() else True,
        }
        metrics["mismatched_metrics"] = [
            key for key, value in metrics.items() if key.endswith("_match") and not value
        ]
        metrics["tolerances"] = {
            "margin_pt": self.MARGIN_TOLERANCE_PT,
            "font_size_pt": self.FONT_SIZE_TOLERANCE_PT,
            "line_spacing_pt": self.LINE_SPACING_TOLERANCE_PT,
        }
        metrics["comparison_mode"] = "reference"
        metrics["reference_file"] = reference_doc.get("original_name", "Reference")
        metrics["per_file_comparisons"] = per_file_comparisons

        return metrics

    def _dict_match(
        self, dicts: List[Dict[str, Any]], tolerance: float = 0.0
    ) -> bool:
        if not dicts:
            return True

        keys = [key for key in dicts[0].keys() if key != "units"]
        for key in keys:
            base_value = dicts[0].get(key)
            for other in dicts[1:]:
                if not self._values_equal(base_value, other.get(key), tolerance):
                    return False
        return True

    def _strings_match(self, values: Iterable[str | None]) -> bool:
        normalized = [self._normalize_font_name(value) for value in values if value]
        if not normalized:
            return True
        return len(set(normalized)) == 1

    def _numeric_match(
        self,
        values: Iterable[float | None],
        *,
        tolerance: float = 0.0,
        allow_partial: bool = True,
    ) -> bool:
        values_list = list(values)
        numeric_values = [value for value in values_list if value is not None]

        if not numeric_values:
            return True

        if not allow_partial and len(numeric_values) != len(values_list):
            return False

        base = numeric_values[0]
        return all(
            self._values_equal(base, value, tolerance) for value in numeric_values[1:]
        )

    def _values_equal(self, a: Any, b: Any, tolerance: float) -> bool:
        if a is None or b is None:
            return a is None and b is None

        try:
            a_num = float(a)
            b_num = float(b)
        except (TypeError, ValueError):
            return str(a).strip().lower() == str(b).strip().lower()

        return abs(a_num - b_num) <= tolerance

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _summarize_strings(self, values: Iterable[str]) -> Dict[str, Any]:
        normalized = [value for value in (self._normalize_font_name(v) for v in values) if value]
        if not normalized:
            return {"primary": None, "values": []}

        counter = Counter(normalized)
        unique_values = sorted(set(normalized))
        return {"primary": counter.most_common(1)[0][0], "values": unique_values}

    def _summarize_numeric(self, values: Iterable[float]) -> Dict[str, Any]:
        normalized = [round(float(value), 2) for value in values if value is not None]
        if not normalized:
            return {"primary": None, "values": []}

        counter = Counter(normalized)
        unique_values = sorted(set(normalized))
        return {"primary": counter.most_common(1)[0][0], "values": unique_values}

    def _most_common_value(self, values: Iterable[float | None]) -> float | None:
        normalized = [round(float(value), 2) for value in values if value is not None]
        if not normalized:
            return None
        counter = Counter(normalized)
        return counter.most_common(1)[0][0]

    def _length_to_points(self, value) -> float | None:
        if value is None:
            return None
        if hasattr(value, "pt"):
            value = value.pt
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _twips_to_points(self, value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return round(int(value) / 20.0, 2)
        except (TypeError, ValueError):
            return None

    def _extract_paragraph_spacing(self, paragraph) -> Tuple[float | None, float | None, float | None]:
        spacing_element = None
        pPr = getattr(paragraph._p, "pPr", None)  # pylint: disable=protected-access
        if pPr is not None:
            spacing_element = getattr(pPr, "spacing", None)

        if spacing_element is not None:
            line = self._twips_to_points(spacing_element.get(qn("w:line")))
            before = self._twips_to_points(spacing_element.get(qn("w:before")))
            after = self._twips_to_points(spacing_element.get(qn("w:after")))
        else:
            line = None
            before = None
            after = None

        if line is None:
            line = self._length_to_points(paragraph.paragraph_format.line_spacing)
        if before is None:
            before = self._length_to_points(paragraph.paragraph_format.space_before)
        if after is None:
            after = self._length_to_points(paragraph.paragraph_format.space_after)

        return line, before, after

    def _normalize_font_name(self, name: str | None) -> str | None:
        if not name:
            return None
        normalized = name.split("+")[-1].strip()
        return normalized or None

    def _group_words_into_lines(self, words: List[dict]) -> List[Dict[str, float | None]]:
        """Group PDF words into logical lines to derive indentation and spacing."""
        if not words:
            return []

        sorted_words = sorted(
            words,
            key=lambda word: (
                round(float(word.get("top", 0)), 1),
                float(word.get("x0", 0)),
            ),
        )

        lines: List[List[dict]] = []
        current_line: List[dict] = []
        current_top: float | None = None
        tolerance = 2.0

        for word in sorted_words:
            top = float(word.get("top", 0))
            if current_top is None or abs(top - current_top) <= tolerance:
                current_line.append(word)
                current_top = top if current_top is None else (current_top + top) / 2
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [word]
                current_top = top

        if current_line:
            lines.append(current_line)

        serialized_lines: List[Dict[str, float | None]] = []
        for index, line_words in enumerate(lines):
            left_positions = [
                float(word.get("x0", 0))
                for word in line_words
                if isinstance(word.get("x0"), (int, float))
            ]
            top_positions = [
                float(word.get("top", 0))
                for word in line_words
                if isinstance(word.get("top"), (int, float))
            ]

            left_indent = min(left_positions) if left_positions else None
            line_top = min(top_positions) if top_positions else None
            next_top = None
            if index + 1 < len(lines):
                next_line = lines[index + 1]
                next_tops = [
                    float(word.get("top", 0))
                    for word in next_line
                    if isinstance(word.get("top"), (int, float))
                ]
                next_top = min(next_tops) if next_tops else None

            line_spacing = None
            if line_top is not None and next_top is not None:
                line_spacing = round(abs(next_top - line_top), 2)

            serialized_lines.append(
                {
                    "left_indent": round(left_indent, 2) if left_indent is not None else None,
                    "line_spacing": line_spacing,
                }
            )

        return serialized_lines

