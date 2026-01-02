
import re

class FigurePlacementVerifier:
    def verify_placement(self, paragraphs: list[str]) -> dict:
        details = []
        fig_pattern = re.compile(r"^(Figure|Fig)\s*\d+", re.IGNORECASE)

        for i, text in enumerate(paragraphs):
            if fig_pattern.match(text):
                pos = "UNKNOWN"
                # Check neighbors for the marker inserted by our DocxParser
                if "<<IMAGE>>" in text: # Same paragraph
                    pos = "BELOW" if text.find("<<IMAGE>>") < text.find("Fig") else "ABOVE"
                elif i > 0 and "<<IMAGE>>" in paragraphs[i-1]: # Image is above
                    pos = "BELOW"
                elif i < len(paragraphs)-1 and "<<IMAGE>>" in paragraphs[i+1]: # Image is below
                    pos = "ABOVE"

                details.append({"caption": text, "placement": pos, "is_valid": pos == "BELOW"})

        total_figures = len(details)
        placements_above = sum(1 for d in details if d["placement"] == "ABOVE")
        placements_below = sum(1 for d in details if d["placement"] == "BELOW")
        
        accuracy_percentage = 0.0
        if total_figures > 0:
            accuracy_percentage = (placements_below / total_figures) * 100

        return {
            "all_valid": all(d["is_valid"] for d in details),
            "total_figures": total_figures,
            "placements_above": placements_above,
            "placements_below": placements_below,
            "accuracy_percentage": round(accuracy_percentage, 2),
            "details": details
        }