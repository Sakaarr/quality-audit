# pyright: reportMissingImports=false
from __future__ import annotations

import base64
import io
import statistics
from typing import List, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    import pymupdf as fitz 
import pytesseract
from django.conf import settings
from pdf2image import convert_from_bytes

from documents.domain import DocumentImage, SectionNode, UnifiedDocument


class PdfParser:
    """Parses PDF documents with layout, table, image, and OCR support using PyMuPDF."""

    def parse(self, uploaded_file, *, enable_ocr: bool = True) -> UnifiedDocument:
        raw_bytes = uploaded_file.read()
        uploaded_file.seek(0)

        ocr_used = False

        # Open PDF with PyMuPDF
        pdf = fitz.open(stream=raw_bytes, filetype="pdf")
        
        metadata = self._extract_metadata(pdf)
        full_text, page_blocks, section_inputs = self._extract_text(pdf)
        tables = self._extract_tables(pdf)
        images = self._extract_images(pdf)
        sections = self._infer_sections(section_inputs)
        
        pdf.close()

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

    def _extract_metadata(self, pdf: fitz.Document) -> dict:
        metadata = {}
        pdf_metadata = pdf.metadata
        
        if pdf_metadata:
            metadata = {
                "author": pdf_metadata.get("author"),
                "creator": pdf_metadata.get("creator"),
                "producer": pdf_metadata.get("producer"),
                "subject": pdf_metadata.get("subject"),
                "title": pdf_metadata.get("title"),
                "created": pdf_metadata.get("creationDate"),
                "modified": pdf_metadata.get("modDate"),
            }

        metadata["page_count"] = pdf.page_count
        metadata["has_text_content"] = any(
            bool(page.get_text().strip()) for page in pdf
        )
        metadata["page_dimensions"] = [
            {"width": page.rect.width, "height": page.rect.height} 
            for page in pdf
        ]
        return {key: value for key, value in metadata.items() if value not in (None, "", [])}

    def _extract_text(self, pdf: fitz.Document) -> Tuple[str, List[dict], List[dict]]:
        combined_text_chunks: List[str] = []
        page_payloads: List[dict] = []
        section_inputs: List[dict] = []

        for page_num in range(pdf.page_count):
            page = pdf[page_num]
            index = page_num + 1
            
            # Extract plain text
            text = page.get_text()
            if text.strip():
                combined_text_chunks.append(text.strip())

            # Extract detailed word information
            blocks = page.get_text("dict")["blocks"]
            words = []
            font_buckets: dict[str, dict] = {}
            font_order: List[str] = []
            
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_text = span.get("text", "")
                            font_name = span.get("font", "unknown")
                            font_size = span.get("size", 0)
                            bbox = span.get("bbox", [0, 0, 0, 0])
                            
                            # Split span into words
                            span_words = span_text.split()
                            if not span_words:
                                continue
                            
                            # Approximate word positions within span
                            x0, y0, x1, y1 = bbox
                            word_width = (x1 - x0) / len(span_words) if span_words else 0
                            
                            for i, word_text in enumerate(span_words):
                                word_x0 = x0 + (i * word_width)
                                word_x1 = word_x0 + word_width
                                
                                word = {
                                    "text": word_text,
                                    "x0": float(word_x0),
                                    "x1": float(word_x1),
                                    "top": float(y0),
                                    "fontname": font_name,
                                    "size": float(font_size),
                                }
                                words.append(word)
                                
                                # Build font buckets
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
                                
                                bucket["segments"].append({
                                    "text": word_text,
                                    "x0": float(word_x0),
                                    "x1": float(word_x1),
                                    "top": float(y0),
                                })
                                bucket["font_sizes"].add(float(font_size))

            # Build serialized words structure
            serialized_words = {}
            for font_name in font_order:
                bucket = font_buckets[font_name]
                entry = {"text": [seg["text"] for seg in bucket["segments"]]}
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

            # Section words for section inference
            section_words = [
                {
                    "text": word["text"],
                    "x0": word["x0"],
                    "x1": word["x1"],
                    "top": word["top"],
                    "font": word.get("fontname"),
                    "font_size": word.get("size", 0),
                }
                for word in words
            ]
            section_inputs.append({"page_number": index, "words": section_words})

        full_text = "\n\n".join(combined_text_chunks)
        return full_text, page_payloads, section_inputs

    def _extract_tables(self, pdf: fitz.Document) -> List[dict]:
        """
        PyMuPDF doesn't have built-in table extraction like pdfplumber.
        You can use camelot-py or tabula-py for table extraction.
        For now, returning empty list.
        """
        tables = []
        # Note: PyMuPDF doesn't have native table extraction
        # You would need to integrate with camelot-py or tabula-py
        # Or implement custom table detection logic
        return tables

    def _extract_images(self, pdf: fitz.Document) -> List[DocumentImage]:
        images: List[DocumentImage] = []

        for page_number in range(pdf.page_count):
            page = pdf[page_number]
            image_list = page.get_images(full=True)
            
            if not image_list:
                continue

            for image_index, img in enumerate(image_list, start=1):
                xref = img[0]
                
                try:
                    base_image = pdf.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Convert to PNG if needed
                    if image_ext != "png":
                        pix = fitz.Pixmap(image_bytes)
                        if pix.alpha:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        image_bytes = pix.tobytes("png")
                        pix = None
                    
                    encoded = base64.b64encode(image_bytes).decode("utf-8")
                    
                    # Get image position on page
                    img_rects = page.get_image_rects(xref)
                    bbox = img_rects[0] if img_rects else fitz.Rect(0, 0, 0, 0)
                    
                    # Get actual image dimensions
                    pix = fitz.Pixmap(image_bytes)
                    width = pix.width
                    height = pix.height
                    pix = None
                    
                    images.append(
                        DocumentImage(
                            identifier=f"pdf-image-{page_number + 1}-{image_index}",
                            mime_type="image/png",
                            width=width,
                            height=height,
                            data=encoded,
                            metadata={
                                "page": page_number + 1,
                                "bbox": (bbox.x0, bbox.y0, bbox.x1, bbox.y1),
                                "area": bbox.width * bbox.height,
                            },
                        )
                    )
                except Exception as e:
                    print(f"Error extracting image {image_index} from page {page_number + 1}: {e}")
                    continue

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
        """Group words into lines based on vertical position."""
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
        tolerance = 5.0

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
                        "words": current_line_words
                    })
                current_line_words = [word]
                current_top = top

        # Handle last line
        if current_line_words:
            lines.append({
                "top": current_top if current_top is not None else 0,
                "words": current_line_words
            })

        return lines

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