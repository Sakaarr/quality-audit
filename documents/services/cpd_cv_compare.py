import json
import re
from io import BytesIO
from difflib import SequenceMatcher
import fitz  # PyMuPDF
from docx import Document

SECTION_HEADERS = [
    'experience', 'work', 'projects', 'skills', 'languages',
    'certifications', 'summary', 'achievements'
]

EDU_HEADERS = [
    'education', 'academic', 'qualification'
]

INSTITUTION_KEYWORDS = [
    'university', 'college', 'school', 'institute', 'academy',
    'polytechnic', 'vidyalaya', 'shikshya', 'organization', 'centre'
]

DEGREE_KEYWORDS = [
    'bachelor', 'master', 'phd', 'doctorate', 'diploma',
    'degree', 'b.sc', 'b.e', 'b.tech', 'm.sc', 'm.tech',
    'mba', 'bba', 'engineering', 'design', 'lecturer', 'assistant', 'project',
]

def normalize_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip().lower()


def fuzzy_match(a, b, threshold=0.8):
    a, b = normalize_text(a), normalize_text(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def is_academic_qualification(text):
    return any(k in normalize_text(text) for k in DEGREE_KEYWORDS)


def is_institution(text):
    return any(k in normalize_text(text) for k in INSTITUTION_KEYWORDS)


def extract_year(text):
    m = re.search(r'(19\d{2}|20\d{2})(\s*[-–]\s*(19\d{2}|20\d{2}))?', text)
    return m.group(0) if m else ""


def extract_cpd_content(file):
    try:
        if hasattr(file, 'read'):
            file.seek(0)
            doc = Document(BytesIO(file.read()))
        else:
            doc = Document(file)

        qualifications = []

        for table in doc.tables:
            headers = [normalize_text(c.text) for c in table.rows[0].cells]

            # Detect Degree Column
            idx_deg = next((i for i, h in enumerate(headers) if 'activit' in h or 'degree' in h or 'title' in h), None)
            
            # Detect Institution/Organization Column (UPDATED)
            idx_org = next((i for i, h in enumerate(headers) if 'institu' in h or 'college' in h or 'organi' in h), None)
            
            idx_per = next((i for i, h in enumerate(headers) if 'period' in h or 'year' in h or 'duration' in h), None)
            idx_loc = next((i for i, h in enumerate(headers) if 'locat' in h), None)

            for row in table.rows[1:]:
                degree = row.cells[idx_deg].text.strip() if idx_deg is not None else ""
                
                # Filters only for academic degrees
                if not is_academic_qualification(degree):
                    continue 

                qualifications.append({
                    "degree": degree,
                    "institution": row.cells[idx_org].text.strip() if idx_org is not None else "",
                    "period": row.cells[idx_per].text.strip() if idx_per is not None else "",
                    "location": row.cells[idx_loc].text.strip() if idx_loc is not None else "",
                    "source": "CPD"
                })

        return {
            "document_type": "CPD",
            "academic_qualifications": qualifications,
            "total_qualifications": len(qualifications)
        }

    except Exception as e:
        return {
            "document_type": "CPD",
            "error": str(e),
            "academic_qualifications": [],
            "total_qualifications": 0
        }


def parse_cv_education(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    qualifications = []

    start = -1
    for i, line in enumerate(lines):
        if any(h in normalize_text(line) for h in EDU_HEADERS):
            start = i
            break

    if start == -1:
        return []

    edu_lines = []
    for line in lines[start + 1:]:
        if normalize_text(line) in SECTION_HEADERS:
            break
        edu_lines.append(line)

    current = None

    for line in edu_lines:
        year = extract_year(line)

        if is_academic_qualification(line) and not is_institution(line):
            if current:
                qualifications.append(current)

            current = {
                "degree": line,
                "institution": "",
                "period": extract_year(line),
                "location": "",
                "source": "CV"
            }

        elif current:
            # Captures Organization or Institution
            if is_institution(line) and not current["institution"]:
                current["institution"] = line

            elif extract_year(line) and not current["period"]:
                current["period"] = extract_year(line)

            elif re.search(r'\b(nepal|india|usa|uk|australia|sri lanka)\b', normalize_text(line)):
                current["location"] = line

    if current:
        qualifications.append(current)

    return qualifications


def extract_cv_content(file):
    try:
        if hasattr(file, 'read'):
            file.seek(0)
            doc = fitz.open(stream=file.read(), filetype="pdf")
        else:
            doc = fitz.open(file)

        # Extraction using blocks to preserve layout logic
        blocks = []
        for page in doc:
            blocks.extend(page.get_text("blocks"))

        blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
        full_text = "\n".join(b[4] for b in blocks)

        quals = parse_cv_education(full_text)

        return {
            "document_type": "CV",
            "academic_qualifications": quals,
            "total_qualifications": len(quals)
        }

    except Exception as e:
        return {
            "document_type": "CV",
            "error": str(e),
            "academic_qualifications": [],
            "total_qualifications": 0
        }


def compare_academic_qualifications(cpd_json, cv_json):
    cpd_quals = cpd_json.get("academic_qualifications", [])
    cv_quals = cv_json.get("academic_qualifications", [])

    results = []
    matched = 0

    for cpd in cpd_quals:
        best = None
        best_score = 0

        for cv in cv_quals:
            score = 0
            if fuzzy_match(cpd["degree"], cv["degree"]): score += 2
            if fuzzy_match(cpd["institution"], cv["institution"]): score += 2
            if fuzzy_match(cpd["period"], cv["period"]): score += 1

            if score > best_score:
                best_score = score
                best = cv

        # Threshold of 3 means Degree + Institution must match
        is_match = best_score >= 3
        if is_match:
            matched += 1

        results.append({
            "cpd_qualification": cpd,
            "match_status": "MATCHED" if is_match else "NOT MATCHED",
            "confidence_score": best_score,
            "matched_cv_qualification": best
        })

    if matched == len(cpd_quals) and matched > 0:
        status = "FULLY_MATCHED"
    elif matched > 0:
        status = "PARTIALLY_MATCHED"
    else:
        status = "NOT_MATCHED"

    return {
        "overall_status": status,
        "total_cpd_qualifications": len(cpd_quals),
        "total_cv_qualifications": len(cv_quals),
        "matched_count": matched,
        "not_matched_count": len(cpd_quals) - matched,
        "comparison_details": results
    }