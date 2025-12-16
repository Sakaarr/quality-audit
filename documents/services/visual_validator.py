import fitz  # PyMuPDF
import pdfplumber
import docx
import imagehash
import pandas as pd
from PIL import Image
import io
import re
import zipfile
import xml.etree.ElementTree as ET

class VisualContentValidator:
    def __init__(self):
        self.seen_hashes = {} 
        self.seen_table_hashes = {}
        # Standard Namespaces for DOCX XML
        self.NS = {
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
            'v': 'urn:schemas-microsoft-com:vml',
            'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006'
        }

    def validate_pdf(self, file_obj):
        file_obj.seek(0)
        report = self._init_report()
        self.seen_hashes = {}
        self.seen_table_hashes = {}

        try:
            doc = fitz.open(stream=file_obj.read(), filetype="pdf")
            for page_num, page in enumerate(doc):
                images = page.get_images(full=True)
                for img_index, img in enumerate(images):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    location = f"PDF Page {page_num + 1} Image {img_index + 1}"
                    self._process_single_image(base_image["image"], location, report)
        except Exception as e:
            report["errors"] = f"PDF Image Error: {str(e)}"

        file_obj.seek(0)
        try:
            with pdfplumber.open(file_obj) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    for t_idx, table in enumerate(tables):
                        cleaned_table = [['' if cell is None else cell for cell in row] for row in table]
                        location = f"PDF Page {page_num + 1} Table {t_idx + 1}"
                        self._process_table(cleaned_table, location, report)
        except Exception as e:
             if not report["errors"]: report["errors"] = ""
             report["errors"] += f" PDF Table Error: {str(e)}"

        return report

    def validate_docx(self, file_obj):
        file_obj.seek(0)
        report = self._init_report()
        self.seen_hashes = {}
        self.seen_table_hashes = {}

        try:
            with zipfile.ZipFile(file_obj) as z:
                # 1. Parse Relationships (Map rId -> Filename)
                rels_xml = z.read("word/_rels/document.xml.rels")
                rels_tree = ET.fromstring(rels_xml)
                
                id_to_target = {}
                for rel in rels_tree.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                    rid = rel.get("Id")
                    target = rel.get("Target")
                    if target and "media/" in target:
                        if not target.startswith("word/"):
                             target = "word/" + target
                        id_to_target[rid] = target

                # 2. Strict XML Traversal (Skips Fallback content)
                doc_xml = z.read("word/document.xml")
                doc_tree = ET.fromstring(doc_xml)
                
                # We collect image RIDs using a recursive walker that ignores <mc:Fallback>
                found_rids = []
                self._recursive_image_search(doc_tree, found_rids)
                
                # 3. Process the found images in order
                for i, rid in enumerate(found_rids):
                    if rid in id_to_target:
                        img_filename = id_to_target[rid]
                        try:
                            img_bytes = z.read(img_filename)
                            location = f"DOCX Image #{i + 1}"
                            self._process_single_image(img_bytes, location, report)
                        except KeyError:
                            continue

        except Exception as e:
            report["errors"] = f"DOCX Image Analysis Failed: {str(e)}"

        file_obj.seek(0)
        try:
            doc = docx.Document(file_obj)
            real_table_count = 0
            
            for t_idx, table in enumerate(doc.tables):
                # Filter out layout tables (1x1 or empty)
                if len(table.rows) < 2 and len(table.columns) < 2: continue
                
                table_data = []
                has_content = False
                for row in table.rows:
                    row_data = [cell.text.strip() for cell in row.cells]
                    if any(row_data): has_content = True
                    table_data.append(row_data)

                if not has_content: continue

                real_table_count += 1
                location = f"DOCX Table #{real_table_count}"
                self._process_table(table_data, location, report)

        except Exception as e:
            pass 

        return report

    def _recursive_image_search(self, element, found_rids):
        """
        Walks the XML tree. 
        If it hits <mc:Fallback>, it STOPS and does not look inside.
        This prevents double counting VML legacy images.
        """
        tag = element.tag
        
        # STOP CONDITION: Do not enter Fallback tags (Legacy duplicates live here)
        if 'Fallback' in tag:
            return

        # 1. Modern Images (a:blip)
        if 'blip' in tag:
            embed = element.get(f"{{{self.NS['r']}}}embed") or element.get(f"{{{self.NS['r']}}}link")
            if embed:
                found_rids.append(embed)
        
        # 2. Legacy VML Images (v:imagedata)
        # Only processed if NOT inside a Fallback tag (handled by the stop condition above)
        elif 'imagedata' in tag:
            rid = element.get(f"{{{self.NS['r']}}}id") or element.get('id')
            if rid:
                found_rids.append(rid)

        # Recurse children
        for child in element:
            self._recursive_image_search(child, found_rids)

    def _init_report(self):
        return {
            "duplicates": [],
            "table_issues": [],
            "errors": None,
            "stats": {"images_processed": 0, "tables_processed": 0}
        }

    #SHARED IMAGE LOGIC
    def _process_single_image(self, image_bytes, location, report):
        report["stats"]["images_processed"] += 1
        try:
            pil_image = Image.open(io.BytesIO(image_bytes))
            if pil_image.mode not in ('L', 'RGB'):
                pil_image = pil_image.convert('RGB')
            
            # 16-hash size for better sensitivity
            img_hash = str(imagehash.phash(pil_image, hash_size=16))

            if img_hash in self.seen_hashes:
                report["duplicates"].append({
                    "type": "Image Duplicate",
                    "original": self.seen_hashes[img_hash],
                    "duplicate": location,
                    "details": "Visual duplicate detected"
                })
            else:
                self.seen_hashes[img_hash] = location
        except Exception:
            return

    # SHARED TABLE LOGIC
    def _process_table(self, table_data, location, report):
        report["stats"]["tables_processed"] += 1
        
        hash_key = str(table_data)
        if hash_key in self.seen_table_hashes:
            report["duplicates"].append({
                "type": "Table Duplicate",
                "original": self.seen_table_hashes[hash_key],
                "duplicate": location,
                "details": "Exact content match"
            })
        else:
            self.seen_table_hashes[hash_key] = location

        df = pd.DataFrame(table_data)
        if df.empty: return

        for _, row in df.iterrows():
            first_cell = str(row.iloc[0]).lower()
            if "total" in first_cell:
                rest_values = "".join(row.iloc[1:].astype(str))
                clean_values = re.sub(r'[$,£€]', '', rest_values)
                if not any(char.isdigit() for char in clean_values):
                    report["table_issues"].append({
                        "location": location,
                        "issue": "Total row seems to lack numeric values"
                    })