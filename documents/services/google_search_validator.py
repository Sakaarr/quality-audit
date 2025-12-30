from typing import List, Dict, Any
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

    def search_title(self, title: str) -> Dict[str, Any]:
        if not self.service:
            return {"title": title, "found": False, "error": "Google Search service not initialized"}

        try:
            # Search for exact phrase by wrapping in quotes
            search_query = f'"{title}"'
            res = self.service.cse().list(q=search_query, cx=self.cse_id, num=1).execute()
            items = res.get("items", [])
            
            if items:
                return {
                    "title": title,
                    "found": True
                }
            else:
                return {
                    "title": title,
                    "found": False
                }
            
        except HttpError as e:
            logger.error(f"Google Search API error for title '{title}': {e}")
            return {"title": title, "found": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error searching for '{title}': {e}")
            return {"title": title, "found": False, "error": str(e)}

    def validate_title(self, title: str) -> Dict[str, Any]:
        return self.search_title(title)