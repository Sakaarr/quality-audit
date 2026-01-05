from __future__ import annotations

import base64
import io
import re
import uuid
from datetime import datetime
from typing import List

from docx import Document as DocxDocument
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from PIL import Image

from documents.domain import DocumentImage, SectionNode, UnifiedDocument


class DocxParser:
    """Parses DOCX documents into the unified document model."""

    def parse(self, uploaded_file) -> UnifiedDocument:
        raw_bytes = uploaded_file.read()
        uploaded_file.seek(0)
        document = DocxDocument(io.BytesIO(raw_bytes))

        metadata = self._extract_metadata(document)
        sections = self._build_sections(document)
        tables = self._extract_tables(document)
        images = self._extract_images(document)
        
        paragraphs = []
        from docx.oxml.text.paragraph import CT_P
        from docx.oxml.table import CT_Tbl
        from docx.text.paragraph import Paragraph

        for child in document.element.body.iterchildren():
                if child.tag.endswith('p'):

                    p = Paragraph(child, document.element.body)
                    text_with_markers = self._get_paragraph_text_with_images(p)
                    if text_with_markers.strip():
                        paragraphs.append(text_with_markers)
                
                elif child.tag.endswith('tbl'):
                    paragraphs.append("<<TABLE>>")
        text_payload = {"full_text": "\n".join(paragraphs), "paragraphs": paragraphs}

        return UnifiedDocument(
            source_type="docx",
            metadata=metadata,
            sections=sections,
            text=text_payload,
            tables=tables,
            images=images,
            extras={
                "paragraph_count": len(paragraphs),
                "section_count": len(sections),
                "table_count": len(tables),
                "image_count": len(images),
            },
        )

    def _get_paragraph_text_with_images(self, paragraph) -> str:
        """
        Iterates through runs to extract text AND detect where images are located.
        Returns a string with '<<IMAGE>>' markers inserted at the correct positions.
        """
        text_parts = []
        
        # XML namespace for Word processing drawings
        # We need this to find the <w:drawing> tags hidden in the XML
        namespace = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        
        for run in paragraph.runs:
            # 1. Add the text content of the run
            if run.text:
                text_parts.append(run.text)
            
            # 2. Check the underlying XML of the run for drawing elements
            # This detects images, charts, and shapes
            if run.element.findall(f'.//{namespace}drawing') or \
               run.element.findall(f'.//{namespace}pict'):
                text_parts.append("\n<<IMAGE>>\n")

        return "".join(text_parts).strip()
    def _extract_metadata(self, document: DocxDocument) -> dict:
        props = document.core_properties

        def iso(value: datetime | None) -> str | None:
            return value.isoformat() if isinstance(value, datetime) else None

        metadata = {
            "author": props.author,
            "created": iso(props.created),
            "modified": iso(props.modified),
            "last_modified_by": getattr(props, "last_modified_by", None),
            "category": props.category,
            "comments": props.comments,
            "keywords": props.keywords,
            "subject": props.subject,
            "title": props.title,
        }
        return {key: value for key, value in metadata.items() if value}

    def _build_sections(self, document: DocxDocument) -> List[SectionNode]:
        sections: List[SectionNode] = []
        stack: List[SectionNode] = []

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue

            style_name = getattr(getattr(paragraph, "style", None), "name", "")
            if style_name and style_name.lower().startswith("heading"):
                level = self._heading_level(style_name)
                node = SectionNode(title=text, level=level)

                while stack and stack[-1].level >= level:
                    stack.pop()

                if stack:
                    stack[-1].children.append(node)
                else:
                    sections.append(node)

                stack.append(node)
            elif stack:
                stack[-1].paragraphs.append(text)

        return sections

    def _heading_level(self, style_name: str) -> int:
        match = re.search(r"(\d+)", style_name)
        return int(match.group(1)) if match else 1

    def _extract_tables(self, document: DocxDocument) -> list:
        tables = []
        for index, table in enumerate(document.tables, start=1):
            rows = [
                [cell.text.strip() for cell in row.cells]
                for row in table.rows
            ]
            tables.append(
                {
                    "id": f"table-{index}",
                    "row_count": len(rows),
                    "column_count": len(rows[0]) if rows else 0,
                    "data": rows,
                }
            )
        return tables

    def _extract_images(self, document: DocxDocument) -> List[DocumentImage]:
        images: List[DocumentImage] = []

        for rel in document.part.rels.values():
            if rel.reltype != RT.IMAGE:
                continue

            image_bytes = rel.target_part.blob
            identifier = f"docx-image-{uuid.uuid4().hex}"
            width = height = 0
            mime_type = "image/unknown"

            try:
                with Image.open(io.BytesIO(image_bytes)) as image:
                    width, height = image.size
                    if image.format:
                        mime_type = f"image/{image.format.lower()}"
            except Exception:
                # Keep defaults when the image cannot be opened.
                pass

            encoded = base64.b64encode(image_bytes).decode("utf-8")
            images.append(
                DocumentImage(
                    identifier=identifier,
                    mime_type=mime_type,
                    width=width,
                    height=height,
                    data=encoded,
                    metadata={"relationship_id": rel.rId, "size_bytes": len(image_bytes)},
                )
            )

        return images

