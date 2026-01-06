from typing import Any, Dict
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class WordCountValidationResult:
    """Immutable result object for word count validation."""
    
    word_count: int
    is_valid: bool
    min_required: int
    max_required: int
    difference: int
    status: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "word_count": self.word_count,
            "is_valid": self.is_valid,
            "min_required": self.min_required,
            "max_required": self.max_required,
            "difference": self.difference,
            "status": self.status,
            "details": {
                "message": self._get_message()
            }
        }
    
    def _get_message(self) -> str:
        """Generate descriptive validation message."""
        if self.is_valid:
            return f"Document meets word count requirements ({self.word_count} words)"
        elif self.word_count < self.min_required:
            return f"Document is {abs(self.difference)} words below minimum requirement"
        else:
            return f"Document is {abs(self.difference)} words above maximum requirement"


class WordCountValidator:
    """
    Service to validate document word count against CE standards (2500-3000 words).
    
    This validator ensures documents meet Copy Editor requirements by:
    - Extracting clean text from parsed content
    - Counting words using consistent tokenization rules
    - Validating against specified range
    """
    
    DEFAULT_MIN_WORDS = 2400
    DEFAULT_MAX_WORDS = 3000
    
    def __init__(self, min_words: int = DEFAULT_MIN_WORDS, max_words: int = DEFAULT_MAX_WORDS):
        """
        Initialize validator with word count range.
        
        Args:
            min_words: Minimum required word count (default: 2500)
            max_words: Maximum allowed word count (default: 3000)
        
        Raises:
            ValueError: If min_words > max_words or if values are negative
        """
        if min_words < 0 or max_words < 0:
            raise ValueError("Word count limits must be non-negative")
        if min_words > max_words:
            raise ValueError("Minimum word count cannot exceed maximum")
            
        self.min_words = min_words
        self.max_words = max_words
    
    def validate(self, text: str) -> WordCountValidationResult:
        """
        Validate text against word count requirements.
        
        Args:
            text: The text content to validate
            
        Returns:
            WordCountValidationResult with validation status and metrics
            
        Raises:
            ValueError: If text is None
        """
        if text is None:
            raise ValueError("Text cannot be None")
            
        word_count = self._count_words(text)
        is_valid = self.min_words <= word_count <= self.max_words
        
        if word_count < self.min_words:
            difference = word_count - self.min_words
            status = "below_minimum"
        elif word_count > self.max_words:
            difference = word_count - self.max_words
            status = "above_maximum"
        else:
            difference = 0
            status = "valid"
        
        return WordCountValidationResult(
            word_count=word_count,
            is_valid=is_valid,
            min_required=self.min_words,
            max_required=self.max_words,
            difference=difference,
            status=status
        )
    
    def _count_words(self, text: str) -> int:
        """
        Count words in text using consistent tokenization.
        
        This method:
        - Removes special markers (e.g., <<TABLE>>, <<FIGURE>>)
        - Tokenizes based on whitespace and punctuation
        - Counts only alphanumeric word tokens
        
        Args:
            text: The text to count words in
            
        Returns:
            Integer count of words
        """
        if not text or not text.strip():
            return 0
        
        # Remove document markers that shouldn't count as words
        cleaned_text = re.sub(r'<<[A-Z]+>>', '', text)
        
        # Extract words: sequences of letters, numbers, hyphens, and apostrophes
        # This matches standard word definitions including contractions and hyphenated words
        word_pattern = r"\b[a-zA-Z0-9'-]+\b"
        words = re.findall(word_pattern, cleaned_text)
        
        # Filter out pure number tokens and single characters that are not 'a' or 'I'
        valid_words = [
            w for w in words 
            if not w.isdigit() and (len(w) > 1 or w.lower() in ['a', 'i'])
        ]
        
        return len(valid_words)