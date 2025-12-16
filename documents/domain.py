from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SectionNode:
    """Represents a logical section derived from headings."""

    title: str
    level: int
    paragraphs: List[str] = field(default_factory=list)
    children: List["SectionNode"] = field(default_factory=list)

    def to_representation(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "level": self.level,
            "paragraphs": self.paragraphs,
            "children": [child.to_representation() for child in self.children],
        }


@dataclass
class DocumentImage:
    identifier: str
    mime_type: str
    width: int
    height: int
    data: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_representation(self) -> Dict[str, Any]:
        payload = {
            "id": self.identifier,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "metadata": self.metadata,
        }
        if self.data:
            payload["data"] = self.data
        return payload


@dataclass
class UnifiedDocument:
    """Shared response contract for DOCX and PDF parsers."""

    source_type: str
    metadata: Dict[str, Any]
    sections: List[SectionNode] = field(default_factory=list)
    text: Dict[str, Any] = field(default_factory=dict)
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[DocumentImage] = field(default_factory=list)
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_representation(self) -> Dict[str, Any]:
        return {
            "source_type": self.source_type,
            "metadata": self.metadata,
            "sections": [section.to_representation() for section in self.sections],
            "text": self.text,
            "tables": self.tables,
            "images": [image.to_representation() for image in self.images],
            "extras": self.extras,
        }

