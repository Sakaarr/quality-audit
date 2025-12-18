import re
import language_tool_python
from spellchecker import SpellChecker
from documents.services.readability_calculation import calculate_readability_metrics

grammar_tool = language_tool_python.LanguageTool('en-GB')
spell = SpellChecker()


# 3. Define Rules to IGNORE
IGNORED_RULES = [
    "WHITESPACE_RULE",           
    "COMMA_PARENTHESIS_WHITESPACE", 
    "UPPERCASE_SENTENCE_START", 
    "EN_QUOTES",                      
    "EN_COMPOUNDS",              
    "SENTENCE_WHITESPACE",
    "ENGLISH_WORD_REPEAT_RULE",
    "EN_UNPAIRED_QUOTES",
    "PHRASE_REPETITION",
    "SPACE_BEFORE_PARENTHESIS",
    "ARROWS",
    "GERMAN_QUOTES",
    "DASH_RULE",
    "MORFOLOGIK_RULE_EN_US",
    "MORFOLOGIK_RULE_EN_GB"
]

def analyze_text_segment(text):
    if not text or not text.strip():
        return None

    spelling_errors = []
    grammar_errors = []

    matches = grammar_tool.check(text)

    for match in matches:
        word = text[match.offset : match.offset + match.error_length]

        # --- FILTER 1: Ignore Specific Annoying Rules ---
        if match.rule_id in IGNORED_RULES:
            continue

        # --- FILTER 2: Ignore Table of Contents/Formatting Dots ---
        if " . " in match.context or "...." in match.context:
            continue

        # --- FILTER 3: Ignore ALL CAPS (Titles) ---
        if word.isupper() and len(word) > 1:
            continue
        
        # --- FILTER 4: Ignore "Native" Spelling Errors ---
        # We skip LanguageTool's spelling checks to avoid duplicates.
        if match.rule_issue_type == 'misspelling':
            continue

        suggestion = match.replacements[0] if match.replacements else ""
        
        error_obj = {
            "error_text": word,
            "message": match.message, 
            "suggestion": suggestion,
            "offset": match.offset,        
            "length": match.error_length,
            "rule_id": match.rule_id,
            "type": "grammar"
        }
        grammar_errors.append(error_obj)


    # 1. Clean & Tokenize: Find words (preserving apostrophes)
    words = re.findall(r"\b[a-zA-Z']+\b", text)
    
    # 2. Identify Unknown Words
    unknown_words = spell.unknown(words)

    # 3. Locate Words & Apply Name Filter
    for word in unknown_words:
        # Skip numbers
        if word.isdigit():
            continue

        # Find all occurrences of the misspelled word in the text
        for match in re.finditer(r'\b' + re.escape(word) + r'\b', text):
            
            # --- NAME FILTER ---
            # Extract the word exactly as typed in the text
            actual_word = text[match.start() : match.end()]
            
            # Check: If it starts with a Capital letter, assume it's a Name/Place
            # This fixes the issue with "Ramesh", "Kathmandu", etc.
            if actual_word[0].isupper():
                continue

            # If it passes the filter, generate a suggestion
            correction = spell.correction(word)
            
            error_obj = {
                "error_text": actual_word,
                "message": f"Possible spelling error: '{actual_word}'",
                "suggestion": correction if correction else "",
                "offset": match.start(),
                "length": match.end() - match.start(),
                "rule_id": "SPELL_CHECKER_RULE",
                "type": "spelling"
            }
            spelling_errors.append(error_obj)

    filtered_matches = [
        m for m in matches 
        if m.rule_id not in IGNORED_RULES 
        and " . " not in m.context
        and m.rule_issue_type != 'misspelling'
    ]
    
    corrected_text = language_tool_python.utils.correct(text, filtered_matches)

    return {
        "spelling_errors": spelling_errors,
        "grammar_errors": grammar_errors,
        "corrected_text": corrected_text
    }

class GrammarAnalysisService:
    """
    Service to handle text analysis (British English + Name-Aware Spelling).
    """

    @staticmethod
    def analyze_segment(text):
        # 1. Run the Single-Pass Analysis
        analysis_result = analyze_text_segment(text)
        
        if not analysis_result:
            return None

        # 2. Readability Calculation
        readability_scores = calculate_readability_metrics(text)

        # 3. Return Final Object
        return {
            "spelling_errors": analysis_result["spelling_errors"],
            "grammar_errors": analysis_result["grammar_errors"],
            "corrected_text": analysis_result["corrected_text"],
            "readability_scores": readability_scores,
            "has_errors": bool(analysis_result["spelling_errors"] or analysis_result["grammar_errors"])
        }