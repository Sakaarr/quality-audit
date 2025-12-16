from typing import List, IO
from rest_framework.exceptions import ValidationError
import pdfplumber
import docx

class TitleValidationService:
    def validate_and_extract_title(self, file_obj: IO[bytes]) -> str | None:
        file_name = file_obj.name.lower()
        file_obj.seek(0)
        
        if file_name.endswith(".docx"):
            return self.extract_from_docx(file_obj)
        elif file_name.endswith(".pdf"):
            return self.extract_from_pdf(file_obj)
        else:
            raise ValidationError("Unsupported file type")
    
    def extract_from_docx(self, file_obj: IO[bytes]) -> str | None:
        try:
            document = docx.Document(file_obj)
        except Exception:
            raise ValidationError("Invalid DOCX file")

        for paragraph in document.paragraphs[:50]:
            if paragraph.style.name.lower() == "title" and paragraph.text.strip():
                print(f"DEBUG: Found explicit 'Title' style: {paragraph.text.strip()}")
                return paragraph.text.strip()

        candidates = []
        for paragraph in document.paragraphs[:20]:
            text = paragraph.text.strip()
            if not text:
                continue
            
            max_size = 0
            for run in paragraph.runs:
                if run.font.size:
                    if run.font.size.pt > max_size:
                        max_size = run.font.size.pt
            
            if max_size > 15:
                # print(f"DEBUG: Found candidate with size {max_size}: {text}")
                candidates.append((max_size, text))
        
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            print(f"DEBUG: Selected visual candidate: {candidates[0][1]}")
            return candidates[0][1]

        # for paragraph in document.paragraphs[:50]:
        #     if paragraph.style.name.lower().startswith("heading 1") and paragraph.text.strip():
        #         print(f"DEBUG: Found 'Heading 1' style: {paragraph.text.strip()}")
        #         return paragraph.text.strip()

        for paragraph in document.paragraphs[:50]:
            if paragraph.text.strip():
                # print(f"DEBUG: Fallback to first text: {paragraph.text.strip()}")
                return paragraph.text.strip()

        return None

    def extract_from_pdf(self, file_obj: IO[bytes]) -> str | None:
        try:
            with pdfplumber.open(file_obj) as pdf:
                if not pdf.pages:
                    return None
                
                for page_num in range(min(3, len(pdf.pages))):
                    page = pdf.pages[page_num]
                    words = page.extract_words(extra_attrs=["size"])
                    
                    if not words:
                        continue
                    
                    lines = self._group_words_by_line(words, tolerance=5.0)
                    
                    if not lines:
                        continue
                    
                    max_size = max(
                        max(float(w["size"]) for w in line["words"])
                        for line in lines[:10] if line["words"]
                    )
                    
                    title_lines = []
                    found_title_start = False
                    
                    for line in lines[:15]:
                        line_words = line["words"]
                        if not line_words:
                            if found_title_start:
                                break
                            continue
                        
                        line_max_size = max(float(w["size"]) for w in line_words)
                        line_text = " ".join(w["text"] for w in line_words).strip()
                        
                        if abs(line_max_size - max_size) <= 1.0:
                            title_lines.append(line_text)
                            found_title_start = True
                        elif found_title_start:
                            break
                    
                    if title_lines:
                        full_title = " ".join(title_lines).strip()
                        # print(f"DEBUG: Extracted PDF title from page {page_num + 1}: {full_title}")
                        return full_title
                
                for page_num in range(min(3, len(pdf.pages))):
                    page = pdf.pages[page_num]
                    first_text = page.extract_text()
                    if first_text and first_text.strip():
                        title = first_text.split("\n")[0].strip()
                        # print(f"DEBUG: Fallback PDF title from page {page_num + 1}: {title}")
                        return title
        
        except Exception as e:
            # print(f"DEBUG: PDF Extraction Error: {e}")
            raise ValidationError("Invalid PDF file")
        
        return None

    def _group_words_by_line(self, words: List[dict], tolerance: float = 5.0) -> List[dict]:
        if not words:
            return []

        sorted_words = sorted(words, key=lambda w: (round(float(w["top"]), 1), float(w["x0"])))
        
        lines = []
        current_line = []
        current_top = None

        for word in sorted_words:
            top = float(word["top"])
            
            if current_top is None or abs(top - current_top) <= tolerance:
                current_line.append(word)
                current_top = top if current_top is None else (current_top + top) / 2
            else:
                if current_line:
                    lines.append({"top": current_top, "words": current_line})
                current_line = [word]
                current_top = top
        
        if current_line:
            lines.append({"top": current_top, "words": current_line})
        
        return lines