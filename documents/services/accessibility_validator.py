import fitz
import re
from docx import Document

class AccessibilityValidator:
    DOCX_NS = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    }

    def validate(self, file_obj):
        filename = file_obj.name.lower()
        file_obj.seek(0)

        if filename.endswith('.docx'):
            return self._validate_docx(file_obj)
        elif filename.endswith('.pdf'):
            return self._validate_pdf(file_obj)
        else:
            raise ValueError("Unsupported file type")

    def _validate_docx(self, file_obj):
        errors = []
        image_audit = []

        try:
            doc = Document(file_obj)
        except Exception:
            return {"status": "error", "message": "Could not parse DOCX structure"}

        for i, shape in enumerate(doc.inline_shapes):
            inline = shape._inline
            docPr = inline.find('wp:docPr', namespaces=self.DOCX_NS)
            
            alt_text = ""
            if docPr is not None:
                alt_text = (docPr.get('descr', '') or docPr.get('title', '') or "").strip()
            
            # If alt text exists = BAD, no alt text = GOOD
            if alt_text:
                status = "NQ"  # Not Qualified - has alt text (bad)
                errors.append({
                    "location": f"Image #{i+1}",
                    "issue": "Alt Text found",
                    "found_text": alt_text
                })
            else:
                status = "OK"  # No alt text (good)

            image_audit.append({
                "location": f"Image #{i+1}",
                "status": status,
                "alt_text": alt_text if alt_text else None
            })

        return self._build_report(errors, image_audit)

    def _validate_pdf(self, file_obj):
        errors = []
        image_audit = []

        try:
            doc = fitz.open(stream=file_obj.read(), filetype="pdf")
        except Exception:
            return {"status": "error", "message": "Could not parse PDF structure"}

        for page_num, page in enumerate(doc):
            images = page.get_images(full=True)
            for img_idx, img in enumerate(images):
                xref = img[0]
                img_obj_str = doc.xref_object(xref)
                alt_text = self._extract_pdf_alt_text(img_obj_str)
                
                # If alt text exists = BAD, no alt text = GOOD
                if alt_text and alt_text.strip() != "":
                    status = "NQ"  # Not Qualified - has alt text (bad)
                    errors.append({
                        "location": f"Page {page_num+1}, Image #{img_idx+1}",
                        "issue": "Alt Text found",
                        "found_text": alt_text
                    })
                else:
                    status = "OK"  # No alt text (good) - FIXED: was "Q"
                
                image_audit.append({
                    "location": f"Page {page_num+1}, Image #{img_idx+1}",
                    "status": status,
                    "alt_text": alt_text
                })

        return self._build_report(errors, image_audit)

    def _extract_pdf_alt_text(self, obj_str):
        # Extracts Alt text from PDF object syntax
        pattern = r"/Alt\s*(?:\((.*?)\)|<([0-9A-Fa-f]+)>)"
        match = re.search(pattern, obj_str, re.DOTALL)
        if not match: return None
        if match.group(1): return match.group(1)
        if match.group(2):
            try: return bytes.fromhex(match.group(2)).decode('utf-8', errors='ignore')
            except: return None
        return None

    def _build_report(self, errors, image_audit):
        return {
            "is_compliant": len(errors) == 0,
            "total_issues": len(errors),
            "issues": errors,
            "image_audit": image_audit 
        }