from typing import List, Dict, Any
import re
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

logger = logging.getLogger(__name__)

class GoogleSearchValidator:
    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.cse_id = settings.GOOGLE_CSE_ID
        self.service = None
        
        if self.api_key and self.cse_id:
            try:
                self.service = build("customsearch", "v1", developerKey=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Google Search service: {e}")

    def search_term(self, term: str) -> Dict[str, Any]:
        if not self.service:
            return {"error": "Google Search service not initialized. Key not found"}

        try:
            #start search
            res = self.service.cse().list(q=term, cx=self.cse_id, num=3).execute()
            items = res.get("items", [])
            
            results = []
            for item in items:
                results.append({
                    "title": item.get("title"),
                    "snippet": item.get("snippet"),
                    "link": item.get("link")
                })
                
            total_results = res.get("searchInformation", {}).get("totalResults", "0")
            
            return {
                "term": term,
                "found": bool(items),
                "total_results": total_results,
                "top_results": results
            }
            
        except HttpError as e:
            logger.error(f"Google Search API error for term '{term}': {e}")
            return {"term": term, "error": str(e), "found": False}
        except Exception as e:
            logger.error(f"Unexpected error searching for '{term}': {e}")
            return {"term": term, "error": str(e), "found": False}

    def _fetch_page_content(self, url: str) -> str:
        try:
            response = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                for script in soup(["script", "style"]):
                    script.decompose()
                return soup.get_text()
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
        return ""

    def _calculate_confidence(self, term: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not items:
            return {"score": 0, "label": "No Results"}

        # Normalize term: lowercase, remove punctuation
        term_clean = re.sub(r'[^\w\s]', '', term.lower())
        term_words = set(term_clean.split())
        
        stop_words = {"is", "an", "the", "of", "and", "a", "to", "in", "for", "on", "with", "as", "by", "at", "from"}
        term_keywords = term_words - stop_words
        
        if not term_keywords:
            return {"score": 0, "label": "Low (No Keywords)"}

        max_overlap = 0
        
        for i, item in enumerate(items[:3]):
            content = item.get("snippet", "") + " " + item.get("title", "")
            
            url = item.get("link")
            if url:
                page_text = self._fetch_page_content(url)
                if page_text:
                    content += " " + page_text

            content_clean = re.sub(r'[^\w\s]', '', content.lower())
            content_words = set(content_clean.split())
            
            overlap = len(term_keywords.intersection(content_words))
            overlap_ratio = overlap / len(term_keywords)
            
            if overlap_ratio > max_overlap:
                max_overlap = overlap_ratio

        if max_overlap == 0:
            return
        # Scoring logic
        score = int(max_overlap * 100)
        
        if score >= 80:
            label = "High"
        elif score >= 50:
            label = "Medium"
        else:
            label = "Low"

        return {"score": score, "label": label}

    def validate_terms(self, terms: List[str]) -> List[Dict[str, Any]]:
        results = []
        unique_terms = list(dict.fromkeys(terms))
        
        for term in unique_terms:
            search_result = self.search_term(term)
            
            if search_result.get("found"):
                confidence = self._calculate_confidence(term, search_result.get("top_results", []))
                search_result["confidence_score"] = confidence["score"]
                search_result["confidence_label"] = confidence["label"]
            else:
                search_result["confidence_score"] = 0
                search_result["confidence_label"] = "Not Found"

            results.append(search_result)
            
        return results
