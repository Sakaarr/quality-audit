import re

class TablePlacementVerifier:
    def verify_placement(self, paragraphs: list[str]) -> dict:
        details = []
        unlabeled_tables = []
        
        tbl_pattern = re.compile(r"^(Table)\s*\d+", re.IGNORECASE)

        for i, text in enumerate(paragraphs):
            raw_text = text.strip()
            if raw_text in ["<<TABLE>>", "<<IMAGE>>"]:
                continue

            if tbl_pattern.match(raw_text):
                pos = "UNKNOWN"
                is_valid = False
                table_type = "Unknown"

                if i < len(paragraphs) - 1:
                    next_text = paragraphs[i+1].strip()
                    if next_text == "<<TABLE>>":
                        pos = "ABOVE"
                        is_valid = True
                        table_type = "Real Table"
                    elif next_text == "<<IMAGE>>":
                        pos = "ABOVE"
                        is_valid = True
                        table_type = "Image (Screenshot)"

                if i > 0 and pos == "UNKNOWN":
                    prev_text = paragraphs[i-1].strip()
                    if prev_text == "<<TABLE>>":
                        pos = "BELOW"
                        is_valid = False
                        table_type = "Real Table"
                    elif prev_text == "<<IMAGE>>":
                        pos = "BELOW"
                        is_valid = False
                        table_type = "Image (Screenshot)"
                
                details.append({
                    "caption": text[:100], 
                    "placement": pos, 
                    "is_valid": is_valid,
                    "type": table_type
                })

        first_table_index = -1
        for idx, p in enumerate(paragraphs):
            if p.strip() == "<<TABLE>>":
                first_table_index = idx
                break
        
        metadata_tables = []
        
        for i, text in enumerate(paragraphs):
            if text.strip() == "<<TABLE>>":
                has_label = False
                
                if i > 0:
                    prev_text = paragraphs[i-1].strip()
                    if tbl_pattern.match(prev_text):
                        has_label = True
                
                if i < len(paragraphs) - 1 and not has_label:
                    next_text = paragraphs[i+1].strip()
                    if tbl_pattern.match(next_text):
                        has_label = True

                if not has_label:
                    if i == first_table_index and i < 15:
                        metadata_tables.append(f"Table at paragraph {i+1} identified as Cover Page/Metadata (No caption required)")
                    else:
                        unlabeled_tables.append(f"Table at paragraph {i+1} missing caption")

        total_tables = len(details)
        valid_count = sum(1 for d in details if d["is_valid"])
        placements_above = sum(1 for d in details if d["placement"] == "ABOVE")
        placements_below = sum(1 for d in details if d["placement"] == "BELOW")

        accuracy_percentage = 0.0
        if total_tables > 0:
            accuracy_percentage = (valid_count / total_tables) * 100

        return {
            "all_valid": all(d["is_valid"] for d in details) and len(unlabeled_tables) == 0,
            "total_tables": total_tables,
            "placements_above": placements_above,
            "placements_below": placements_below,
            "accuracy_percentage": round(accuracy_percentage, 2),
            "details": details,
            "unlabeled_tables": unlabeled_tables,
            "metadata_tables": metadata_tables,
            "debug_info": {
                "first_table_index": first_table_index,
                "first_5_paragraphs": paragraphs[:5]
            }
        }