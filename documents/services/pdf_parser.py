# pyright: reportMissingImports=false
from __future__ import annotations

import base64
import io
import statistics
from typing import List, Tuple

import pdfplumber
import pytesseract
from django.conf import settings
from pdf2image import convert_from_bytes

from documents.domain import DocumentImage, SectionNode, UnifiedDocument


class PdfParser:
    """Parses PDF documents with layout, table, image, and OCR support."""

    def parse(self, uploaded_file, *, enable_ocr: bool = True) -> UnifiedDocument:
        raw_bytes = uploaded_file.read()
        uploaded_file.seek(0)

        ocr_used = False

        with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
            metadata = self._extract_metadata(pdf)
            full_text, page_blocks, section_inputs = self._extract_text(pdf)
            tables = self._extract_tables(pdf)
            images = []
            sections = self._infer_sections(section_inputs)

        # if enable_ocr and not full_text.strip():
        #     ocr_text, ocr_pages = self._ocr_fallback(raw_bytes)
        #     if ocr_text:
        #         full_text = ocr_text
        #         page_blocks = ocr_pages
        #         ocr_used = True

        text_payload = {"full_text": full_text, "pages": page_blocks}

        return UnifiedDocument(
            source_type="pdf",
            metadata=metadata,
            sections=sections,
            text=text_payload,
            tables=tables,
            images=images,
            extras={
                "page_count": len(page_blocks),
                "table_count": len(tables),
                "image_count": len(images),
                "ocr_applied": ocr_used,
            },
        )

    def _extract_metadata(self, pdf: pdfplumber.PDF) -> dict:
        metadata = {}
        if pdf.metadata:
            metadata = {
                "author": pdf.metadata.get("Author"),
                "creator": pdf.metadata.get("Creator"),
                "producer": pdf.metadata.get("Producer"),
                "subject": pdf.metadata.get("Subject"),
                "title": pdf.metadata.get("Title"),
                "created": pdf.metadata.get("CreationDate"),
                "modified": pdf.metadata.get("ModDate"),
            }

        metadata["page_count"] = len(pdf.pages)
        metadata["has_text_content"] = any(
            bool((page.extract_text() or "").strip()) for page in pdf.pages
        )
        metadata["page_dimensions"] = [
            {"width": page.width, "height": page.height} for page in pdf.pages
        ]
        return {key: value for key, value in metadata.items() if value not in (None, "", [])}

    def _extract_text(self, pdf: pdfplumber.PDF) -> Tuple[str, List[dict], List[dict]]:
        combined_text_chunks: List[str] = []
        page_payloads: List[dict] = []
        section_inputs: List[dict] = []

        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                combined_text_chunks.append(text.strip())

            words = page.extract_words(
                use_text_flow=True,
                extra_attrs=["fontname", "size", "adv", "upright"],
            )
            font_buckets: dict[str, dict] = {}
            font_order: List[str] = []
            for word in words:
                font_name = word.get("fontname") or "unknown"
                bucket = font_buckets.setdefault(
                    font_name,
                    {
                        "font": font_name,
                        "segments": [],
                        "font_sizes": set(),
                    },
                )
                if font_name not in font_order:
                    font_order.append(font_name)
                bucket["segments"].append(
                    {
                        "text": word["text"],
                        "x0": float(word["x0"]),
                        "x1": float(word["x1"]),
                        "top": float(word["top"]),
                    }
                )
                size_value = word.get("size")
                if isinstance(size_value, (int, float)):
                    bucket["font_sizes"].add(float(size_value))

            serialized_words = {}
            for font_name in font_order:
                bucket = font_buckets[font_name]
                entry = {"text": self._segments_to_words(bucket["segments"])}
                sizes = bucket["font_sizes"]
                if len(sizes) == 1:
                    entry["font_size"] = next(iter(sizes))
                elif sizes:
                    entry["font_sizes"] = sorted(sizes)
                serialized_words[font_name] = entry

            fonts = {word.get("fontname") for word in words if word.get("fontname")}
            font_sizes = {
                float(word.get("size"))
                for word in words
                if isinstance(word.get("size"), (int, float))
            }

            layout = {"words": serialized_words, "order": font_order}
            if len(fonts) == 1:
                layout["font"] = next(iter(fonts))
            elif fonts:
                layout["fonts"] = sorted(fonts)

            if len(font_sizes) == 1:
                layout["font_size"] = next(iter(font_sizes))
            elif font_sizes:
                layout["font_sizes"] = sorted(font_sizes)

            page_payload = {
                "page_number": index,
                "text": text,
                "layout": layout,
            }
            page_payloads.append(page_payload)

            section_words = [
                {
                    "text": word["text"],
                    "x0": float(word["x0"]),
                    "x1": float(word["x1"]),
                    "top": float(word["top"]),
                    "font": word.get("fontname"),
                    "font_size": float(word.get("size") or 0),
                }
                for word in words
            ]
            section_inputs.append({"page_number": index, "words": section_words})

        full_text = "\n\n".join(combined_text_chunks)
        return full_text, page_payloads, section_inputs

    def _extract_tables(self, pdf: pdfplumber.PDF) -> List[dict]:
        tables = []
        for page_number, page in enumerate(pdf.pages, start=1):
            for table_index, table in enumerate(page.extract_tables() or [], start=1):
                normalized_rows = [
                    [cell.strip() if isinstance(cell, str) else "" for cell in row]
                    for row in table
                ]
                tables.append(
                    {
                        "id": f"pdf-table-{page_number}-{table_index}",
                        "page_number": page_number,
                        "row_count": len(normalized_rows),
                        "column_count": len(normalized_rows[0]) if normalized_rows else 0,
                        "data": normalized_rows,
                    }
                )
        return tables

    def _extract_images(self, pdf: pdfplumber.PDF) -> List[DocumentImage]:
        images: List[DocumentImage] = []

        for page_number, page in enumerate(pdf.pages, start=1):
            if not page.images:
                continue

            for image_index, image_obj in enumerate(page.images, start=1):
                x0 = float(image_obj["x0"])
                x1 = float(image_obj["x1"])
                top = float(image_obj["top"])
                bottom = float(image_obj["bottom"])
                bbox = (min(x0, x1), min(top, bottom), max(x0, x1), max(top, bottom))
                try:
                    cropped_page = page.crop(bbox)
                    pil_image = cropped_page.to_image(resolution=200).original
                except Exception:
                    continue

                buffer = io.BytesIO()
                pil_image.save(buffer, format="PNG")
                payload = buffer.getvalue()
                encoded = base64.b64encode(payload).decode("utf-8")

                images.append(
                    DocumentImage(
                        identifier=f"pdf-image-{page_number}-{image_index}",
                        mime_type="image/png",
                        width=pil_image.width,
                        height=pil_image.height,
                        data=encoded,
                        metadata={
                            "page": page_number,
                            "bbox": bbox,
                            "area": abs((x1 - x0) * (bottom - top)),
                        },
                    )
                )

        return images

    def _infer_sections(self, pages: List[dict]) -> List[SectionNode]:
        sections: List[SectionNode] = []
        current_parent: SectionNode | None = None
        current_child: SectionNode | None = None

        for page in pages:
            words = page.get("words", [])
            if not words:
                continue

            sizes = [word.get("font_size", 0) for word in words if word.get("font_size")]
            if not sizes:
                continue

            mean_size = statistics.mean(sizes)
            stdev = statistics.pstdev(sizes) if len(sizes) > 1 else 0
            heading_threshold = mean_size + stdev
            subsection_threshold = mean_size

            for line in self._group_words_by_line(words):
                line_text = " ".join(word["text"] for word in line["words"]).strip()
                if not line_text:
                    continue
                line_size = max(word.get("font_size", 0) for word in line["words"])

                if line_size >= heading_threshold:
                    node = SectionNode(title=line_text, level=1)
                    sections.append(node)
                    current_parent = node
                    current_child = None
                elif line_size >= subsection_threshold:
                    node = SectionNode(title=line_text, level=2)
                    if current_parent:
                        current_parent.children.append(node)
                        current_child = node
                elif current_child:
                    current_child.paragraphs.append(line_text)
                elif current_parent:
                    current_parent.paragraphs.append(line_text)

        return sections

    def _group_words_by_line(self, words: List[dict]) -> List[dict]:
        """Group words into lines, properly handling single-character words."""
        if not words:
            return []

        # Sort words by line (top position) then left-to-right
        sorted_words = sorted(
            words, 
            key=lambda w: (round(float(w.get("top", 0)), 1), float(w.get("x0", 0)))
        )
        
        # Group into lines based on vertical position
        lines = []
        current_line_words = []
        current_top = None
        tolerance = 3.0

        for word in sorted_words:
            top = float(word.get("top", 0))
            if current_top is None or abs(top - current_top) <= tolerance:
                current_line_words.append(word)
                current_top = top if current_top is None else (current_top + top) / 2
            else:
                # Process the completed line
                if current_line_words:
                    lines.append({
                        "top": current_top,
                        "words": self._group_line_words(current_line_words)
                    })
                current_line_words = [word]
                current_top = top

        # Handle last line
        if current_line_words:
            lines.append({
                "top": current_top if current_top is not None else 0,
                "words": self._group_line_words(current_line_words)
            })

        return lines

    def _group_line_words(self, line_words: List[dict]) -> List[dict]:
        """Group single-character words into multi-character words within a line."""
        if not line_words:
            return []
        
        # Calculate gap threshold using percentile-based approach
        gaps = []
        widths = []
        
        for i in range(len(line_words) - 1):
            curr_word = line_words[i]
            next_word = line_words[i + 1]
            
            # Get x1 from current word, fallback to x0 if x1 not available
            x1_curr = float(curr_word.get("x1", curr_word.get("x0", 0)))
            x0_next = float(next_word.get("x0", 0))
            gap = x0_next - x1_curr
            
            if gap >= 0:  # Only consider positive gaps
                gaps.append(gap)
            
            # Track character widths
            x0 = float(curr_word.get("x0", 0))
            x1 = float(curr_word.get("x1", curr_word.get("x0", 0)))
            if x1 > x0:
                widths.append(x1 - x0)
        
        # Use percentile-based threshold
        if gaps:
            gaps_sorted = sorted(gaps)
            # Use 75th percentile - more aggressive grouping for character-by-character extraction
            percentile_75_idx = int(len(gaps_sorted) * 0.75)
            gap_threshold = gaps_sorted[percentile_75_idx] if percentile_75_idx < len(gaps_sorted) else gaps_sorted[-1]
            # Ensure minimum threshold - be more aggressive for character grouping
            avg_char_width = statistics.mean(widths) if widths else 5.0
            gap_threshold = max(gap_threshold, avg_char_width * 0.5)
        else:
            avg_char_width = statistics.mean(widths) if widths else 5.0
            gap_threshold = avg_char_width * 1.5
        
        # Group words based on spatial proximity
        grouped_words = []
        current_group = []
        prev_word = None
        
        for word in line_words:
            text = (word.get("text") or "").strip()
            if not text:
                continue
                
            # If this is already a multi-character word, add it as-is
            if len(text) > 1:
                if current_group:
                    grouped_words.append(self._merge_word_group(current_group))
                    current_group = []
                grouped_words.append(word)
                prev_word = word
                continue
            
            # Single character - check if it continues previous word
            if prev_word is None:
                current_group = [word]
            else:
                # Get x1 from previous word, with fallback
                prev_x1 = float(prev_word.get("x1", prev_word.get("x0", 0)))
                curr_x0 = float(word.get("x0", 0))
                gap = curr_x0 - prev_x1
                
                if gap <= gap_threshold:
                    # Continue current word group
                    current_group.append(word)
                else:
                    # Start new word group
                    if current_group:
                        grouped_words.append(self._merge_word_group(current_group))
                    current_group = [word]
            
            prev_word = word
        
        # Add final group
        if current_group:
            grouped_words.append(self._merge_word_group(current_group))
        
        return grouped_words

    def _merge_word_group(self, word_group: List[dict]) -> dict:
        """Merge a group of single-character words into one word dict."""
        if not word_group:
            return {}
        
        merged_text = "".join(w.get("text", "") for w in word_group)
        
        # Get x1 from the last word in the group (rightmost position)
        x1 = float(word_group[-1].get("x1", word_group[-1].get("x0", 0)))
        
        return {
            "text": merged_text,
            "x0": float(word_group[0].get("x0", 0)),
            "x1": x1,
            "top": float(word_group[0].get("top", 0)),
            "font": word_group[0].get("font"),
            "font_size": max(
                float(w.get("font_size", 0)) for w in word_group
            )
        }

    def _segments_to_words(self, segments: List[dict]) -> List[str]:
        """Group character-level segments into words based on spatial proximity."""
        if not segments:
            return []

        # Sort segments by top position, then x0 (left to right, top to bottom)
        sorted_segs = sorted(
            segments,
            key=lambda s: (round(float(s.get("top", 0)), 1), float(s.get("x0", 0))),
        )

        # Calculate average character width to determine word gaps
        widths = [
            seg["x1"] - seg["x0"]
            for seg in sorted_segs
            if isinstance(seg.get("x1"), (int, float))
            and isinstance(seg.get("x0"), (int, float))
            and seg["x1"] > seg["x0"]
        ]
        avg_char_width = statistics.mean(widths) if widths else 5.0
        gap_threshold = avg_char_width * 2.0
        line_tolerance = 3.0

        words = []
        current_word = ""
        prev_seg = None

        for seg in sorted_segs:
            text = (seg.get("text") or "").strip()
            if not text:
                if current_word:
                    words.append(current_word)
                    current_word = ""
                prev_seg = None
                continue

            # If segment is already a word (multiple characters), add it directly
            if len(text) > 1:
                if current_word:
                    words.append(current_word)
                    current_word = ""
                words.append(text)
                prev_seg = seg
                continue

            # Single character - check if it continues the current word
            if prev_seg is None:
                current_word = text
            else:
                # Check if same line and within gap threshold
                same_line = (
                    abs(float(seg.get("top", 0)) - float(prev_seg.get("top", 0)))
                    <= line_tolerance
                )
                gap = (
                    float(seg.get("x0", 0)) - float(prev_seg.get("x1", 0))
                    if same_line
                    else float("inf")
                )

                if same_line and gap <= gap_threshold:
                    # Continue current word
                    current_word += text
                else:
                    # Start new word
                    if current_word:
                        words.append(current_word)
                    current_word = text

            prev_seg = seg

        if current_word:
            words.append(current_word)

        return words

    def _ocr_fallback(self, raw_bytes: bytes) -> Tuple[str, List[dict]]:
        poppler_path = getattr(settings, "POPPLER_PATH", None)
        tess_command = getattr(settings, "TESSERACT_CMD", None)

        if tess_command:
            pytesseract.pytesseract.tesseract_cmd = tess_command

        try:
            page_images = convert_from_bytes(raw_bytes, dpi=200, poppler_path=poppler_path)
        except Exception:
            return "", []

        page_payloads = []
        page_text_chunks = []

        for index, image in enumerate(page_images, start=1):
            text = pytesseract.image_to_string(image).strip()
            page_payloads.append({"page_number": index, "text": text, "layout": []})
            if text:
                page_text_chunks.append(f"[Page {index}]\n{text}")

        return "\n\n".join(page_text_chunks), page_payloads