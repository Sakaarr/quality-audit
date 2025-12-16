import os
import requests
from documents.services.readability_calculation import calculate_readability_metrics

# Configuration: Use remote API on low-memory hosts (free tier)
USE_REMOTE_API = os.environ.get("GRAMMAR_USE_REMOTE_API", "true").lower() in ("true", "1", "yes")
REMOTE_API_URL = "https://api.languagetool.org/v2/check"

# Lazy loading for local mode
_tool_us = None
_tool_gb = None
_language_tool_module = None


def _get_language_tool():
    """Lazy import of language_tool_python to avoid loading Java at startup."""
    global _language_tool_module
    if _language_tool_module is None:
        import language_tool_python
        _language_tool_module = language_tool_python
    return _language_tool_module


def _get_tool(language='en-US'):
    """
    Lazy initialization of LanguageTool instances.
    Only loads when grammar check is actually requested.
    """
    global _tool_us, _tool_gb
    
    language_tool_python = _get_language_tool()
    
    if language == 'en-GB':
        if _tool_gb is None:
            _tool_gb = language_tool_python.LanguageTool('en-GB')
        return _tool_gb
    else:
        if _tool_us is None:
            _tool_us = language_tool_python.LanguageTool('en-US')
        return _tool_us


# Rules to IGNORE (Formatting & Styling rules)
IGNORED_RULES = [
    "WHITESPACE_RULE",           
    "COMMA_PARENTHESIS_WHITESPACE", 
    "UPPERCASE_SENTENCE_START", 
    "EN_QUOTES",                 
    "MORFOLOGIK_RULE_EN_US",     
    "EN_COMPOUNDS",              
    "SENTENCE_WHITESPACE",
    "ENGLISH_WORD_REPEAT_RULE",
    "EN_UNPAIRED_QUOTES",
    "PHRASE_REPETITION",
]


def _analyze_with_remote_api(text, language='en-US'):
    """
    Use LanguageTool's free public API instead of local Java server.
    This saves ~300MB of memory on free hosting tiers.
    """
    if not text or not text.strip():
        return None
    
    try:
        # Map language codes
        lang_code = 'en-GB' if language == 'en-GB' else 'en-US'
        
        response = requests.post(
            REMOTE_API_URL,
            data={
                'text': text[:10000],  # API limit
                'language': lang_code,
            },
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        spelling_errors = []
        grammar_errors = []
        
        for match in result.get('matches', []):
            rule_id = match.get('rule', {}).get('id', '')
            
            # Apply same filters as local mode
            if rule_id in IGNORED_RULES:
                continue
            
            context = match.get('context', {}).get('text', '')
            if " . " in context or "...." in context:
                continue
            
            word = text[match['offset']:match['offset'] + match['length']]
            if word.isupper() and len(word) > 1:
                continue
            
            if rule_id == "ENGLISH_WORD_REPEAT_RULE" and ("\n" in word or "\r" in word):
                continue
            
            replacements = match.get('replacements', [])
            suggestion = replacements[0].get('value', '') if replacements else ''
            
            error_obj = {
                "error_text": word,
                "message": match.get('message', ''),
                "suggestion": suggestion,
                "offset": match['offset'],
                "length": match['length'],
                "rule_id": rule_id
            }
            
            issue_type = match.get('rule', {}).get('issueType', '')
            if issue_type == 'misspelling':
                spelling_errors.append(error_obj)
            else:
                grammar_errors.append(error_obj)
        
        # Simple correction (apply first suggestion for each match)
        corrected_text = text
        for match in reversed(result.get('matches', [])):
            if match.get('rule', {}).get('id', '') in IGNORED_RULES:
                continue
            replacements = match.get('replacements', [])
            if replacements:
                start = match['offset']
                end = start + match['length']
                corrected_text = corrected_text[:start] + replacements[0].get('value', '') + corrected_text[end:]
        
        return {
            "spelling_errors": spelling_errors,
            "grammar_errors": grammar_errors,
            "corrected_text": corrected_text
        }
        
    except Exception as e:
        print(f"Remote API error: {e}")
        # Return empty result on API failure
        return {
            "spelling_errors": [],
            "grammar_errors": [],
            "corrected_text": text
        }


def _analyze_with_local_tool(text, language='en-US'):
    """
    Use local LanguageTool Java server (requires ~300MB memory).
    """
    if not text or not text.strip():
        return None

    current_tool = _get_tool(language)
    language_tool_python = _get_language_tool()
    
    # Run the check
    matches = current_tool.check(text)

    spelling_errors = []
    grammar_errors = []

    for match in matches:
        word = text[match.offset : match.offset + match.error_length]

        if match.rule_id in IGNORED_RULES:
            continue

        if " . " in match.context or "...." in match.context:
            continue

        if word.isupper() and len(word) > 1:
            continue

        if match.rule_id == "ENGLISH_WORD_REPEAT_RULE":
            if "\n" in word or "\r" in word:
                continue

        suggestion = match.replacements[0] if match.replacements else ""
        
        error_obj = {
            "error_text": word,
            "message": match.message, 
            "suggestion": suggestion,
            "offset": match.offset,        
            "length": match.error_length,
            "rule_id": match.rule_id
        }

        if match.rule_issue_type == 'misspelling':
            spelling_errors.append(error_obj)
        else:
            grammar_errors.append(error_obj)

    filtered_matches = [
        m for m in matches 
        if m.rule_id not in IGNORED_RULES 
        and " . " not in m.context
        and not (m.rule_id == "ENGLISH_WORD_REPEAT_RULE" and ("\n" in text[m.offset:m.offset+m.error_length]))
    ]
    
    corrected_text = language_tool_python.utils.correct(text, filtered_matches)

    return {
        "spelling_errors": spelling_errors,
        "grammar_errors": grammar_errors,
        "corrected_text": corrected_text
    }


def analyze_text_segment(text, language='en-US'):
    """
    Runs LanguageTool (remote API or local) based on configuration.
    """
    if USE_REMOTE_API:
        return _analyze_with_remote_api(text, language)
    else:
        return _analyze_with_local_tool(text, language)


class GrammarAnalysisService:
    """
    Service to handle text analysis and error intersection (US/GB).
    """

    @staticmethod
    def analyze_segment(text):
        # 1. Run raw analysis
        us_result = analyze_text_segment(text, language='en-US')
        gb_result = analyze_text_segment(text, language='en-GB')

        # Handle None results
        if us_result is None:
            us_result = {"spelling_errors": [], "grammar_errors": [], "corrected_text": text}
        if gb_result is None:
            gb_result = {"spelling_errors": [], "grammar_errors": [], "corrected_text": text}

        # 2. Intersect Errors (Permissive Check)
        final_spelling = GrammarAnalysisService._intersect_errors(
            us_result.get("spelling_errors", []),
            gb_result.get("spelling_errors", [])
        )
        
        final_grammar = GrammarAnalysisService._intersect_errors(
            us_result.get("grammar_errors", []),
            gb_result.get("grammar_errors", [])
        )

        # 3. Readability
        readability_scores = calculate_readability_metrics(text)

        # 4. Corrected Text Logic
        if not final_spelling and not final_grammar:
            final_corrected = text
        else:
            final_corrected = us_result.get("corrected_text", text)

        return {
            "spelling_errors": final_spelling,
            "grammar_errors": final_grammar,
            "corrected_text": final_corrected,
            "readability_scores": readability_scores,
            "has_errors": bool(final_spelling or final_grammar)
        }

    @staticmethod
    def _intersect_errors(list_a, list_b):
        common = []
        b_lookup = {(e.get('offset'), e.get('length')) for e in list_b}

        for error in list_a:
            if (error.get('offset'), error.get('length')) in b_lookup:
                common.append(error)
        return common
