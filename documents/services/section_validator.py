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
        "Abstract/Executive Summary",
        "Introduction",
        "Literature Review/Background",
        "Methodology",
        "Implementation/Development",
        "Results",
        "Analysis/Discussion",
        "Conclusion",
        "References",
    ]

    def __init__(self, required_sections: List[str] | None = None):
        self.required_sections = required_sections or self.DEFAULT_REQUIRED_SECTIONS

    def validate(self, sections: List[Dict[str, Any]]) -> ValidationResult:

        try:
            flattened_titles = self.__flatten_sections(sections)
            present_sections = set()
            missing_sections = []

            for required in self.required_sections:
                if self._is_match(required, flattened_titles):
                    present_sections.add(required)
                else:
                    missing_sections.append(required)
            
            total_required = len(self.required_sections)
            found_count = len(present_sections)
            completeness_score = (found_count / total_required  * 100) if total_required > 0 else 100.0

            return ValidationResult(
                completeness_score=completeness_score,
                missing_sections=missing_sections,
                present_sections=list(present_sections),
                details={
                    "total_required": total_required,
                    "found_count": found_count,
                },
            )

            
        except Exception as e:
            print(f"An error occurred: {e}")
            return ValidationResult(
                completeness_score=0.0,
                missing_sections=self.required_sections,
                present_sections=[],
                details={"error": str(e)},
            )

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
        alternatives = [alt.strip().lower() for alt in required_pattern.split("/")]

        for title in document_titles:
            clean_title = re.sub(r"^[\d\w\.]+\s+", "", title).lower()
            full_title_lower = title.lower()

            for alt in alternatives:
                if alt == clean_title:
                    return True
                if alt in full_title_lower:
                    return True

        return False
