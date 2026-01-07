import re
import language_tool_python
from spellchecker import SpellChecker
from documents.services.readability_calculation import calculate_readability_metrics
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

class GrammarAnalysisService:    
    IGNORED_RULES = {
        "WHITESPACE_RULE",
        "COMMA_PARENTHESIS_WHITESPACE",
        "SENTENCE_WHITESPACE",
        "EN_UNPAIRED_QUOTES",
        "ARROWS",
    }

    PERFORMANCE_IGNORED_RULES = {
        "CONSECUTIVE_SPACES",
        "DOUBLE_PUNCTUATION",
        "ENGLISH_WORD_REPEAT_RULE",
        "MORFOLOGIK_RULE_EN_GB", 
    }
    
    CUSTOM_DICTIONARY = {
        'api', 'apis', 'admin', 'backend', 'frontend', 'database', 'username',
        'email', 'url', 'urls', 'http', 'https', 'json', 'xml', 'html', 'css',
        'javascript', 'python', 'django', 'pdf', 'docx', 'cpd', 'cv',
        'ui', 'ux', 'seo', 'ceo', 'cto', 'hr', 'it', 'qa', 'ai', 'ml', 'multi',
        'etc', 'vs', 'eg', 'ie',
    }
    
    def __init__(self, fast_mode=True, max_workers=4):
        """
        Args:
            fast_mode: Enable performance optimizations (disable some rules)
            max_workers: Number of parallel workers for batch processing
        """
        # Initialize LanguageTool with optimizations
        self.grammar_tool = language_tool_python.LanguageTool('en-GB')
        
        # Disable rules for performance if fast_mode enabled
        if fast_mode:
            all_ignored = self.IGNORED_RULES | self.PERFORMANCE_IGNORED_RULES
            self.grammar_tool.disabled_rules = list(all_ignored)
        
        self.spell_checker = SpellChecker()
        self.spell_checker.word_frequency.load_words(self.CUSTOM_DICTIONARY)
        self.max_workers = max_workers
        
        # Pre-compile all regex patterns for reuse
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for better performance"""
        # Proper noun patterns
        self.proper_noun_compiled = [
            re.compile(r'^[A-Z][a-z]+$'),
            re.compile(r'^[A-Z][a-z]+[A-Z][a-z]+'),
            re.compile(r'^[A-Z]{2,}$'),
            re.compile(r'^[A-Z]\.$'),
        ]
        
        # TOC patterns
        self.toc_dots_pattern = re.compile(r'\.{3,}')
        self.toc_page_pattern = re.compile(r'\.\s*\d+\s*$')
        
        # Technical context patterns
        self.url_pattern = re.compile(r'https?://|www\.', re.IGNORECASE)
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.path_pattern = re.compile(r'[/\\][A-Za-z0-9_\-./\\]+')
        self.code_pattern = re.compile(r'[a-z]+[A-Z][a-z]+|[a-z]+_[a-z]+')
        
        # Word extraction pattern
        self.word_pattern = re.compile(r"\b[a-zA-Z']+\b")
    
    @lru_cache(maxsize=1024)
    def _is_likely_proper_noun_cached(self, word):
        """Cached proper noun detection"""
        if not word:
            return False
        for pattern in self.proper_noun_compiled:
            if pattern.match(word):
                return True
        return False
    
    def _is_table_of_contents_context(self, context):
        """Optimized TOC detection with pre-compiled patterns"""
        if not context:
            return False
        if self.toc_dots_pattern.search(context):
            return True
        if ' . ' in context or '. . .' in context:
            return True
        if self.toc_page_pattern.search(context):
            return True
        return False
    
    def _is_technical_context(self, text, offset, length):
        """Optimized technical context detection"""
        start = max(0, offset - 50)
        end = min(len(text), offset + length + 50)
        context = text[start:end]
        
        if self.url_pattern.search(context):
            return True
        if self.email_pattern.search(context):
            return True
        if self.path_pattern.search(context):
            return True
        if self.code_pattern.search(context):
            return True
        return False
    
    @staticmethod
    def _categorize_error_severity(rule_id, issue_type):
        """Fast severity categorization"""
        rule_upper = rule_id.upper()
        
        if any(p in rule_upper for p in ['AGREEMENT', 'VERB', 'TENSE', 'PRONOUN', 'ARTICLE', 'SUBJECT_VERB', 'PLURAL', 'SINGULAR']):
            return 'critical'
        if any(p in rule_upper for p in ['SPELL', 'WORD_CHOICE', 'CONFUSION', 'HOMOPHONE']):
            return 'moderate'
        return 'minor'
    
    def _filter_grammar_errors(self, matches, text):
        grammar_errors = []
        
        for match in matches:
            try:
                word = text[match.offset : match.offset + match.error_length]
                
                # Quick checks first (cheapest operations)
                if match.rule_issue_type == 'misspelling':
                    continue
                if match.rule_id in self.IGNORED_RULES:
                    continue
                
                # More expensive checks
                if self._is_likely_proper_noun_cached(word):
                    continue
                if self._is_table_of_contents_context(match.context):
                    continue
                if self._is_technical_context(text, match.offset, match.error_length):
                    continue
                
                error_obj = {
                    "error_text": word,
                    "message": match.message,
                    "suggestion": match.replacements[0] if match.replacements else "",
                    "suggestions": match.replacements[:3] if match.replacements else [],
                    "offset": match.offset,
                    "length": match.error_length,
                    "rule_id": match.rule_id,
                    "type": "grammar",
                    "severity": self._categorize_error_severity(match.rule_id, match.rule_issue_type),
                    "category": match.rule_issue_type or "grammar"
                }
                grammar_errors.append(error_obj)
            except:
                continue
        
        return grammar_errors
    
    def _detect_spelling_errors(self, text):
        spelling_errors = []
        
        try:
            # Use pre-compiled pattern
            words = self.word_pattern.findall(text)
            
            # Filter words before spell checking
            words_to_check = [
                w for w in words 
                if len(w) > 2 and not w.isdigit() and w.lower() not in self.CUSTOM_DICTIONARY
            ]
            
            # Batch check unknown words
            unknown_words = self.spell_checker.unknown(words_to_check)
            
            for word in unknown_words:
                # Find all occurrences
                for match in re.finditer(r'\b' + re.escape(word) + r'\b', text):
                    actual_word = text[match.start() : match.end()]
                    
                    if self._is_likely_proper_noun_cached(actual_word):
                        continue
                    if self._is_technical_context(text, match.start(), len(actual_word)):
                        continue
                    
                    correction = self.spell_checker.correction(word)
                    candidates = list(self.spell_checker.candidates(word))[:3] if self.spell_checker.candidates(word) else []
                    
                    error_obj = {
                        "error_text": actual_word,
                        "message": f"Possible spelling error: '{actual_word}'",
                        "suggestion": correction if correction and correction != word else "",
                        "suggestions": candidates,
                        "offset": match.start(),
                        "length": len(actual_word),
                        "rule_id": "SPELL_CHECKER",
                        "type": "spelling",
                        "severity": "moderate",
                        "category": "spelling"
                    }
                    spelling_errors.append(error_obj)
        except:
            pass
        
        return spelling_errors
    
    def _generate_corrected_text(self, text, grammar_matches):
        try:
            valid_matches = [
                m for m in grammar_matches
                if m.ruleId not in self.IGNORED_RULES
                and not self._is_table_of_contents_context(m.context)
                and m.ruleIssueType != 'misspelling'
                and not self._is_technical_context(text, m.offset, m.errorLength)
            ]
            
            if valid_matches:
                return language_tool_python.utils.correct(text, valid_matches)
            return text
        except:
            return text
    
    def analyze_segment(self, text, include_readability=True):
        if text is None or not str(text).strip():
            return None
        
        text = str(text).strip()
        
        # Skip very short text (< 10 chars) - likely not worth checking
        if len(text) < 10:
            return None
        
        try:
            grammar_matches = self.grammar_tool.check(text)
            grammar_errors = self._filter_grammar_errors(grammar_matches, text)
            spelling_errors = self._detect_spelling_errors(text)
            corrected_text = self._generate_corrected_text(text, grammar_matches)
            
            # Only calculate readability if requested and text is substantial
            readability_scores = {}
            if include_readability and len(text) > 50:
                try:
                    readability_scores = calculate_readability_metrics(text)
                except:
                    pass
            
            return {
                "spelling_errors": spelling_errors,
                "grammar_errors": grammar_errors,
                "corrected_text": corrected_text,
                "readability_scores": readability_scores,
                "has_errors": bool(spelling_errors or grammar_errors),
                "total_errors": len(spelling_errors) + len(grammar_errors),
                "error_summary": {
                    "spelling": len(spelling_errors),
                    "grammar": len(grammar_errors),
                    "critical": sum(1 for e in grammar_errors if e.get("severity") == "critical"),
                    "moderate": sum(1 for e in grammar_errors + spelling_errors if e.get("severity") == "moderate"),
                    "minor": sum(1 for e in grammar_errors if e.get("severity") == "minor")
                }
            }
        except:
            return {
                "spelling_errors": [],
                "grammar_errors": [],
                "corrected_text": text,
                "readability_scores": {},
                "has_errors": False,
                "total_errors": 0,
                "error_summary": {"spelling": 0, "grammar": 0, "critical": 0, "moderate": 0, "minor": 0}
            }
    
    def analyze_batch(self, texts, include_readability=True):
        # Filter out empty texts with their indices
        valid_texts = [(i, text) for i, text in enumerate(texts) if text and str(text).strip()]
        
        if not valid_texts:
            return [None] * len(texts)
        
        # Process in parallel
        results = [None] * len(texts)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_index = {
                executor.submit(self.analyze_segment, text, include_readability): i
                for i, text in valid_texts
            }
            
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except:
                    results[index] = None
        
        return results


# Singleton with configurable performance
_service_instance = None
_fast_mode = True

def get_service_instance(fast_mode=True, max_workers=4):
    global _service_instance, _fast_mode
    
    # Recreate if fast_mode changed
    if _service_instance is None or _fast_mode != fast_mode:
        _service_instance = GrammarAnalysisService(fast_mode, max_workers)
        _fast_mode = fast_mode
    
    return _service_instance


def analyze_text_segment(text):
    service = get_service_instance()
    result = service.analyze_segment(text)
    
    if not result:
        return None
    
    return {
        "spelling_errors": result["spelling_errors"],
        "grammar_errors": result["grammar_errors"],
        "corrected_text": result["corrected_text"]
    }