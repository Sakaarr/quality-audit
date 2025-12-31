import imagehash
from PIL import Image
import io
from documents.services.visual_validator import VisualContentValidator

class VisualComparator(VisualContentValidator):
    def __init__(self):
        super().__init__()
        # We will use this to store hashes for the *current* file being processed
        self.current_file_hashes = {}  # {hash: [location1, location2]}

    def compare(self, file_obj_1, file_obj_2):
        """
        Compare two files and return statistics about image overlap.
        """
        # 1. Process File 1
        self.current_file_hashes = {}
        self._process_file(file_obj_1)
        hashes_1 = self.current_file_hashes

        # 2. Process File 2
        self.current_file_hashes = {}
        self._process_file(file_obj_2)
        hashes_2 = self.current_file_hashes

        # 3. Analyze Overlap
        set1 = set(hashes_1.keys())
        set2 = set(hashes_2.keys())
        
        common_hashes = set1.intersection(set2)
        unique_in_1 = set1 - set2
        unique_in_2 = set2 - set1

        return {
            "summary": {
                "file_1_total_images": len(set1),
                "file_2_total_images": len(set2),
                "common_images_count": len(common_hashes),
                "unique_in_file_1_count": len(unique_in_1),
                "unique_in_file_2_count": len(unique_in_2),
                "similarity_score": self._calculate_similarity(len(common_hashes), len(set1), len(set2))
            },
            "details": {
                "common_images": [
                    {
                        "hash": h,
                        "locations_in_file_1": hashes_1[h],
                        "locations_in_file_2": hashes_2[h]
                    } for h in common_hashes
                ]
            }
        }

    def _process_file(self, file_obj):
        """Helper to dispatch validation based on extension"""
        name = file_obj.name.lower()
        if name.endswith('.pdf'):
            self.validate_pdf(file_obj)
        elif name.endswith('.docx'):
            self.validate_docx(file_obj)
        else:
            raise ValueError("Unsupported file type")

    def _process_single_image(self, image_bytes, location, report):
        """
        Override parent method to collect hashes instead of checking for internal duplicates.
        """
        try:
            pil_image = Image.open(io.BytesIO(image_bytes))
            if pil_image.mode not in ('L', 'RGB'):
                pil_image = pil_image.convert('RGB')
            
            # Use same hash size as parent for consistency
            img_hash = str(imagehash.phash(pil_image, hash_size=16))

            if img_hash not in self.current_file_hashes:
                self.current_file_hashes[img_hash] = []
            self.current_file_hashes[img_hash].append(location)

        except Exception:
            return

    def _calculate_similarity(self, common, total1, total2):
        """Jaccard index or simple percentage"""
        union = total1 + total2 - common
        if union == 0:
            return 0.0
        return round((common / union) * 100, 2)
