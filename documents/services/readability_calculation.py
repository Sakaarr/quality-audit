import textstat
import re
import nltk

# We force-load the CMU dictionary immediately when this file is imported.
# This prevents multiple threads from trying to load it simultaneously later.
try:
    # 1. Ensure the file is downloaded
    try:
        nltk.data.find('corpora/cmudict.zip')
    except LookupError:
        nltk.download('cmudict', quiet=True)

    # 2. FORCE LOAD into memory now (The critical fix)
    # Accessing .dict() triggers the lazy loader. We do this here
    # so it doesn't happen inside the view function.
    _ = nltk.corpus.cmudict.dict()
    
except Exception as e:
    # If NLTK fails completely, we configure textstat to NOT use it.
    # This forces textstat to fallback to 'pyphen' (which is safer/simpler).
    print(f"Warning: NLTK failed to load ({e}). Switching textstat to Pyphen mode.")
    textstat.set_lang("en_US") 

def calculate_readability_metrics(text):
    # Handle empty text
    if not text or not text.strip():
        return {
            "flesch_reading_ease": 0,
            "flesch_kincaid_grade": 0,
            "gunning_fog": 0,
            "smog_index": 0,
            "avg_sentence_length": 0,
            "avg_word_length": 0
        }

    # 1. Basic Counts
    num_sentences = textstat.sentence_count(text)
    num_words = textstat.lexicon_count(text, removepunct=True)
    
    num_sentences = max(1, num_sentences)
    num_words = max(1, num_words)

    # 2. Calculate Averages
    avg_sentence_length = num_words / num_sentences

    clean_text = re.sub(r'\s+', '', text)
    avg_word_length = len(clean_text) / num_words

    # 3. Calculate Scores (Wrapped in Try/Except for extra safety)
    try:
        flesch_ease = textstat.flesch_reading_ease(text)
    except Exception:
        flesch_ease = 0
        
    try:
        flesch_grade = textstat.flesch_kincaid_grade(text)
    except Exception:
        flesch_grade = 0
        
    try:
        gunning = textstat.gunning_fog(text)
    except Exception:
        gunning = 0
        
    try:
        smog = textstat.smog_index(text)
    except Exception:
        smog = 0

    return {
        "flesch_reading_ease": flesch_ease,
        "flesch_kincaid_grade": flesch_grade,
        "gunning_fog": gunning,
        "smog_index": smog,
        "avg_sentence_length": round(avg_sentence_length, 2),
        "avg_word_length": round(avg_word_length, 2)
    }