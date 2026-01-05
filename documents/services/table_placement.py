
import re
import re

class TablePlacementVerifier:
    def verify_placement(self, paragraphs: list[str]) -> dict:
        details = []
        table_pattern = re.compile(r"^(Table|Tab)\s*\d+", re.IGNORECASE)

        for i, text in enumerate(paragraphs):
            stripped_text = text.strip()
            if table_pattern.match(stripped_text):
                pos = "UNKNOWN"
                
                # Check for both <<TABLE>> and <<TABLE:table-X>> formats
                has_table_marker = "<<TABLE>>" in text or "<<TABLE:" in text
                
                if has_table_marker:
                    # Find table marker position
                    table_index = text.find("<<TABLE:")
                    if table_index == -1:
                        table_index = text.find("<<TABLE>>")
                    
                    caption_match = re.search(r"(Table|Tab)\s*\d+", text, re.IGNORECASE)
                    caption_index = caption_match.start() if caption_match else 0
                    
                    # If table marker comes before caption text, caption is BELOW (invalid)
                    # If caption comes before table marker, caption is ABOVE (valid)
                    pos = "BELOW" if table_index < caption_index else "ABOVE"
                    
                elif i > 0 and ("<<TABLE>>" in paragraphs[i-1] or "<<TABLE:" in paragraphs[i-1]):
                    # Caption is after table (invalid)
                    pos = "BELOW"
                elif i < len(paragraphs)-1 and ("<<TABLE>>" in paragraphs[i+1] or "<<TABLE:" in paragraphs[i+1]):
                    # Caption is before table (valid)
                    pos = "ABOVE"

                # For tables, caption should be ABOVE (is_valid = True when pos == "ABOVE")
                details.append({
                    "caption": stripped_text, 
                    "placement": pos, 
                    "is_valid": pos == "ABOVE"
                })

        total_tables = len(details)
        placements_above = sum(1 for d in details if d["placement"] == "ABOVE")
        placements_below = sum(1 for d in details if d["placement"] == "BELOW")
        
        accuracy_percentage = 0.0
        if total_tables > 0:
            accuracy_percentage = (placements_above / total_tables) * 100

        return {
            "all_valid": all(d["is_valid"] for d in details),
            "total_tables": total_tables,
            "placements_above": placements_above,
            "placements_below": placements_below,
            "accuracy_percentage": round(accuracy_percentage, 2),
            "details": details
        }