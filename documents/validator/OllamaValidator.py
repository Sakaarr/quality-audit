
import os
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import json
import google.generativeai as genai



class CalculationValidationResult(BaseModel):
    """Result of a single calculation validation"""
    reasoning: str = Field(..., description="Step-by-step explanation")
    calculated_result: float = Field(..., description="AI computed result")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence (0.0-1.0)")
    is_correct: bool = Field(..., description="Whether calculation is correct")
    potential_issues: List[str] = Field(default_factory=list, description="Identified issues")


class AICalculationValidator:
    def __init__(self):

        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", )

        if not self.api_key:
            raise ValueError(" No Key Found")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)
        self.generation_config = {
            "temperature": 0.0,
            "top_p": 0.1,
            "top_k": 1,
            "max_output_tokens": 2048
        }


    def extract_document_text(self, unified_doc) -> str:
        """
        Extract full text from already-parsed document.
        Works with both PDF and DOCX unified document objects.
        """
        try:
            text_parts = []
            
            # Extract from PDF pages if available
            if hasattr(unified_doc, 'text') and 'pages' in unified_doc.text:
                pages = unified_doc.text.get('pages', [])
                for page in pages:
                    page_num = page.get('page_number', 'unknown')
                    page_text = page.get('text', '')
                    if page_text.strip():
                        text_parts.append(f"=== PAGE {page_num} ===\n{page_text}")
            
            # Extract from DOCX paragraphs if available
            elif hasattr(unified_doc, 'text') and 'paragraphs' in unified_doc.text:
                paragraphs = unified_doc.text.get('paragraphs', [])
                text_parts.append('\n'.join(paragraphs))
            
            # Fallback to full_text if available
            elif hasattr(unified_doc, 'text') and 'full_text' in unified_doc.text:
                text_parts.append(unified_doc.text.get('full_text', ''))
            
            return "\n\n".join(text_parts)
        except Exception as e:
            raise ValueError(f"Failed to extract document text: {str(e)}")

    def analyze_document_math(self, unified_doc) -> Dict[str, Any]:
        """
        Analyze a document for calculations, validate them using the AI model,
        and return a detailed analysis.
        """
        
        try:
            full_text = self.extract_document_text(unified_doc)
        
        except:
            return {
                "status": "error",
                "message": "Failed to extract document text"
            }

        text_to_analyze = full_text[:60000]
        if len(full_text) > 60000:
            text_to_analyze += "\n\n..."
        
        prompt = f"""You are a mathematical validation expert analyzing a document .
        Document Text: {text_to_analyze}

        TASK: Find and validate ALL mathematical calculations in this document.

For each calculation found:
1. Identify the mathematical expression
2. Calculate the correct result
3. Rate your confidence (0.0-1.0)
4. Note any issues

OUTPUT ONLY THIS JSON (no markdown, no explanation):
{{
    "total_calculations_found": <number>,
    "validations": [
        {{
            "expression": "<calculation>",
            "location": "<where found>",
            "calculated_result": <number>,
            "confidence_score": <0.0-1.0>,
            "reasoning": "<brief explanation>",
            "potential_issues": []
        }}
    ],
    "overall_assessment": {{
        "correct_calculations": <count>,
        "incorrect_calculations": <count>,
        "accuracy_percentage": <percent>,
        "average_confidence": <0.0-1.0>,
        "summary": "<brief assessment>",
    }}
}}
        """

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=self.generation_config,
            )
            response_text = response.text.strip()
        
        # Clean markdown if present
            if '```' in response_text:
                parts = response_text.split('```')
                for part in parts:
                    if 'json' in part.lower():
                        response_text = part.replace('json', '').strip()
                        break
                    elif part.strip().startswith('{'):
                        response_text = part.strip()
                        break
        
            result = json.loads(response_text)
            result["status"] = "success"
            result["model_used"] = self.model_name
            return result
        
        except Exception as e:
            return {
                "status": "error",
                "message": f"Gemini analysis failed: {str(e)}",
                "model": self.model_name
            }
        