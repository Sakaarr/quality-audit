import re
import requests
from datetime import date, datetime

class ReferenceValidatorService:
    def __init__(self, project_date=None, passout_date=None, ce_activity_date_provided=False):
        self.project_date = self._parse_date(project_date)
        self.passout_date = self._parse_date(passout_date)
        self.ce_activity_date_provided = ce_activity_date_provided
        self.year_pattern = r'\b(?:19|20)\d{2}\b'
        self.url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

    def _parse_date(self, date_input):
        """Helper to ensure we have a valid date object"""
        if isinstance(date_input, date):
            return date_input
        if isinstance(date_input, str):
            try:
                return datetime.strptime(date_input, "%Y-%m-%d").date()
            except ValueError:
                pass
        return date.today()

    def process_document_text(self, full_text):
        # Use the UPDATED extraction method (Strict IEEE)
        references = self._extract_references_from_text(full_text)
        results = []

        for ref_text in references:
            year = self._extract_year(ref_text)
            urls = re.findall(self.url_pattern, ref_text)
            
            # Use YOUR working logic
            timeline_status = self._validate_timeline(year)
            format_status = self._validate_format(ref_text, urls)

            results.append({
                "raw_text": ref_text[:100] + "...",
                "extracted_year": year,
                "timeline_validation": timeline_status,
                "format_validation": format_status
            })

        return {
            "total_references_found": len(references),
            "details": results
        }

    def _validate_timeline(self, reference_year):
        if not reference_year:
            return {"is_valid": False, "message": "No year detected"}
        
        current_year = self.project_date.year
        
        # 1. Future Check
        if reference_year > current_year:
            return {"is_valid": False, "message": "Anachronistic (Future Date)"}
        
        # 2. Logic to determine Cutoff
        if self.ce_activity_date_provided:
            cutoff_year = self.project_date.year - 2
            rule = "Rule B (2-year)"
        else:
            cutoff_year = self.passout_date.year - 4
            rule = "Rule C (4-year)"

        # 3. Apply Cutoff
        if reference_year < cutoff_year:
            return {"is_valid": False, "message": f"Outdated. Exceeds {rule} limit ({cutoff_year})"}

        return {"is_valid": True, "message": "Timeline OK"}

    def _extract_references_from_text(self, text):
        lines = text.split('\n')
        extracted = []
        capture = False
        current_ref_buffer = ""

        # Regex to detect "References" header but ignore "References .... 45"
        header_pattern = r'^\s*(References|Bibliography|Works Cited)(?![ .]*\d+$)'
        stop_pattern = r'^\s*(Appendix|Index|Annex)'

        for line in lines:
            clean_line = line.strip()
            if not clean_line: continue

            # 1. Detect Start
            if "...." not in clean_line and re.match(header_pattern, clean_line, re.IGNORECASE):
                if len(clean_line) < 40:
                    capture = True
                    extracted = [] 
                    current_ref_buffer = ""
                    continue
            
            # 2. Capture Logic
            if capture:
                if re.match(stop_pattern, clean_line, re.IGNORECASE):
                    break

                # --- CHANGED: Strict IEEE Only ---
                if self._is_new_reference_start(clean_line):
                    if current_ref_buffer:
                        extracted.append(current_ref_buffer.strip())
                    current_ref_buffer = clean_line
                else:
                    if current_ref_buffer:
                        current_ref_buffer += " " + clean_line

        if current_ref_buffer:
            extracted.append(current_ref_buffer.strip())
            
        # Fallback Logic (if no header found)
        if not extracted:
             raw_candidates = []
             current_buffer = ""
             for line in lines:
                 clean = line.strip()
                 if not clean: continue
                 if self._is_new_reference_start(clean):
                     if current_buffer: raw_candidates.append(current_buffer)
                     current_buffer = clean
                 elif current_buffer:
                     current_buffer += " " + clean
             if current_buffer: raw_candidates.append(current_buffer)
             extracted = [r for r in raw_candidates if len(r) > 20]

        return extracted

    def _is_new_reference_start(self, line):
        # ONLY ALLOW [1], [10]
        return bool(re.match(r'^\s*\[\d+\]', line))

    def _extract_year(self, text):
        matches = re.findall(self.year_pattern, text)
        if matches:
            return int(matches[-1]) 
        return None

    def _validate_format(self, text, urls):
        issues = []
        if len(text) < 15 or not re.search(self.year_pattern, text):
            issues.append("Incomplete reference information")

        link_status = "No links"
        for url in urls:
            try:
                response = requests.head(url, timeout=3, allow_redirects=True)
                if response.status_code >= 400:
                    issues.append(f"Broken URL: {url} (Status {response.status_code})")
            except requests.RequestException:
                issues.append(f"Unreachable URL: {url}")
        
        if urls and not issues:
            link_status = "Links Valid"
        elif issues:
            link_status = "Link/Format Issues Detected"

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "link_status": link_status
        }