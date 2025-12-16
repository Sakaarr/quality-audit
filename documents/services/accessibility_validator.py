import fitz  # PyMuPDF
import re
from docx import Document

class AccessibilityValidator:
    # Namespaces required to parse Word XML for Alt Text
    DOCX_NS = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    }

    # Terms that are considered "bad" descriptions
    GENERIC_TERMS = {'image', 'picture', 'photo', 'img', 'graphic', 'temp', 'click here', 'read more', 'link', 'untitled'}

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
        image_audit = [] # List to store details of ALL images

        try:
            doc = Document(file_obj)
        except Exception:
            return {"status": "error", "message": "Could not parse DOCX structure"}

        # --- 1. Image Alt Text Check ---
        for i, shape in enumerate(doc.inline_shapes):
            inline = shape._inline
            docPr = inline.find('wp:docPr', namespaces=self.DOCX_NS)
            
            alt_text = ""
            if docPr is not None:
                alt_text = docPr.get('descr', '') or docPr.get('title', '')
            
            alt_text = alt_text.strip()
            
            # Determine status
            status = "OK"
            if not alt_text:
                status = "Missing"
                errors.append({
                    "location": f"Image #{i+1}",
                    "issue": "Missing Alt Text",
                    "found_text": None
                })
            elif self._is_generic(alt_text):
                status = "Generic"
                errors.append({
                    "location": f"Image #{i+1}",
                    "issue": "Generic Alt Text detected",
                    "found_text": alt_text
                })

            # Add to full audit list
            image_audit.append({
                "location": f"Image #{i+1}",
                "status": status,
                "alt_text": alt_text if alt_text else None
            })

        # --- 2. Hyperlink Text Check ---
        for p_idx, para in enumerate(doc.paragraphs):
            try:
                hyperlinks = para._element.findall('.//w:hyperlink', namespaces=self.DOCX_NS)
                for link in hyperlinks:
                    text_elements = link.findall('.//w:t', namespaces=self.DOCX_NS)
                    link_text = "".join([t.text for t in text_elements]).strip()
                    
                    if not link_text: continue 

                    if self._is_generic(link_text):
                        errors.append({
                            "location": f"Paragraph #{p_idx+1}",
                            "issue": "Non-descriptive link text",
                            "found_text": link_text
                        })
                    elif link_text.lower().startswith('http'):
                        errors.append({
                            "location": f"Paragraph #{p_idx+1}",
                            "issue": "Raw URL used as link text",
                            "found_text": link_text
                        })
            except Exception:
                continue

        return self._build_report(errors, image_audit)

    def _validate_pdf(self, file_obj):
        errors = []
        image_audit = [] # List to store details of ALL images

        try:
            doc = fitz.open(stream=file_obj.read(), filetype="pdf")
        except Exception:
            return {"status": "error", "message": "Could not parse PDF structure"}

        for page_num, page in enumerate(doc):
            # --- 1. Image Alt Text Check ---
            images = page.get_images(full=True)
            for img_idx, img in enumerate(images):
                xref = img[0]
                img_obj_str = doc.xref_object(xref)
                
                alt_text = self._extract_pdf_alt_text(img_obj_str)
                
                # Determine status
                status = "OK"
                if alt_text is None or alt_text.strip() == "":
                    status = "Missing"
                    errors.append({
                        "location": f"Page {page_num+1}, Image #{img_idx+1}",
                        "issue": "Missing Alt Text metadata",
                        "found_text": None
                    })
                elif self._is_generic(alt_text):
                    status = "Generic"
                    errors.append({
                        "location": f"Page {page_num+1}, Image #{img_idx+1}",
                        "issue": "Generic Alt Text detected",
                        "found_text": alt_text
                    })
                
                # Add to full audit list
                image_audit.append({
                    "location": f"Page {page_num+1}, Image #{img_idx+1}",
                    "status": status,
                    "alt_text": alt_text
                })

            # --- 2. Hyperlink Text Check ---
            links = page.get_links()
            for link in links:
                rect = link['from']
                link_text = page.get_text("text", clip=rect).strip()
                
                if link_text and self._is_generic(link_text):
                     errors.append({
                        "location": f"Page {page_num+1}",
                        "issue": "Non-descriptive link text",
                        "found_text": link_text
                    })

        return self._build_report(errors, image_audit)

    def _extract_pdf_alt_text(self, obj_str):
        pattern = r"/Alt\s*(?:\((.*?)\)|<([0-9A-Fa-f]+)>)"
        match = re.search(pattern, obj_str, re.DOTALL)
        
        if not match:
            return None
            
        if match.group(1):
            return match.group(1)
        elif match.group(2):
            try:
                return bytes.fromhex(match.group(2)).decode('utf-8', errors='ignore')
            except Exception:
                return "<invalid hex data>"
        return None

    def _is_generic(self, text):
        return text.lower().strip() in self.GENERIC_TERMS

    def _build_report(self, errors, image_audit=None):
        return {
            "is_compliant": len(errors) == 0,
            "total_issues": len(errors),
            "issues": errors,
            "image_audit": image_audit or [] 
        }