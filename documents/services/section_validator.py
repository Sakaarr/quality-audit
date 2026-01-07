from typing import Any, Dict, List, Set
import re

from dataclasses import dataclass, field
import re

@dataclass(frozen=True)
class ValidationResult:

    completeness_score: float
    missing_sections: List[str]
    present_sections: List[str]
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "completeness_score": self.completeness_score,
            "missing_sections": self.missing_sections,
            "present_sections": self.present_sections,
            "details": self.details,
        }


class SectionValidator:


    DEFAULT_REQUIRED_SECTIONS = [
        "Background",
        "Introduction",
        "Objectives",
        "Duties",
        "PEAs",
        "Problem and Solution",
        "Creative Works",
        "Team Management",
        "Summary",
    ]

    def __init__(self, required_sections: List[str] | None = None):
        self.required_sections = required_sections or self.DEFAULT_REQUIRED_SECTIONS

    def validate(
        self, 
        sections: List[Dict[str, Any]], 
        paragraphs: List[str] | None = None
    ) -> ValidationResult:

        try:
            document_titles = self.__flatten_sections(sections)
            
            # If no structured sections found, try to extract from paragraphs
            if not document_titles and paragraphs:
                document_titles = self._extract_sections_from_paragraphs(paragraphs)

            present_sections = []
            missing_sections = []

            for required in self.required_sections:
                if self._is_match(required, document_titles):
                    present_sections.append(required)
                else:
                    missing_sections.append(required)
            
            total_required = len(self.required_sections)
            found_count = len(present_sections)
            completeness_score = (found_count / total_required  * 100) if total_required > 0 else 100.0

            return ValidationResult(
                completeness_score=completeness_score,
                missing_sections=missing_sections,
                present_sections=present_sections,
                details={
                    "total_required": total_required,
                    "found_count": found_count,
                    "extracted_titles_count": len(document_titles)
                },
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            return ValidationResult(
                completeness_score=0.0,
                missing_sections=self.required_sections,
                present_sections=[],
                details={"error": str(e)},
            )

    def _extract_sections_from_paragraphs(self, paragraphs: List[str]) -> Set[str]:
        """
        Extracts potential section titles from paragraphs.
        Looks for patterns like '3.1 Introduction', 'Chapter 1', etc.
        """
        extracted = set()
        # Pattern for numbered headers: '3.1 Introduction' or '3.1. Introduction'
        # Also handles things like '3.1.1 Sub-section'
        header_pattern = re.compile(r'^(\d+(\.\d+)*)\.?\s+(.+)$')
        
        for p in paragraphs:
            text = p.strip()
            if not text:
                continue
            
            # Check if paragraph is short (likely a header) or matches header pattern
            if len(text) < 100:
                match = header_pattern.match(text)
                if match:
                    # Add both full text and just the title part
                    extracted.add(text)
                    extracted.add(match.group(3).strip())
                else:
                    extracted.add(text)
                    
        return extracted

    def __flatten_sections(self, sections: List[Dict[str, Any]]) -> Set[str]:
        flattened_titles = set()
        
        for section in sections:
            raw_title = section.get("title")
            if raw_title and isinstance(raw_title, str):
                flattened_titles.add(raw_title.strip())
            
            children = section.get("children")
            if isinstance(children, list):
                flattened_titles.update(self.__flatten_sections(children))

        return flattened_titles

    def _is_match(self, required_pattern: str, document_titles: Set[str]) -> bool:
        """
        Checks if a required section (which might have alternatives like 'A/B')
        matches any of the extracted document titles.
        """
        # REQUIRED: normalized list of alternatives
        alternatives = [alt.strip().lower() for alt in required_pattern.split("/")]

        for title in document_titles:
            # 1. Full match (case insensitive)
            title_lower = title.lower()
            
            # 2. Match without numbers (e.g. "3.1 Introduction" -> "introduction")
            clean_title = re.sub(r'^[\d\w\.]+\s+', '', title).lower()

            for alt in alternatives:
                # Direct match
                if alt == title_lower or alt == clean_title:
                    return True
                
                # Substring match (more lenient)
                if alt in title_lower:
                    return True

        return False
