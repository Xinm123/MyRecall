from datetime import datetime
import re
from typing import List, Optional
from pydantic import BaseModel

class ParsedQuery(BaseModel):
    text: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    mandatory_keywords: List[str] = []

class QueryParser:
    def parse(self, query: str) -> ParsedQuery:
        text = query.strip()
        mandatory_keywords = []
        start_time = None
        end_time = None
        
        # 1. Extract Quoted Keywords
        # Find strings inside double quotes
        quoted = re.findall(r'"([^"]*)"', text)
        mandatory_keywords.extend(quoted)
        
        # 2. Time Extraction (Simple Logic)
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day).timestamp()
        
        lower_text = text.lower()
        
        if "today" in lower_text:
            start_time = today_start
            text = re.sub(r'\btoday\b', '', text, flags=re.IGNORECASE).strip()
            
        elif "yesterday" in lower_text:
            yesterday_start = today_start - 86400
            start_time = yesterday_start
            end_time = today_start
            text = re.sub(r'\byesterday\b', '', text, flags=re.IGNORECASE).strip()
            
        elif "last week" in lower_text:
            start_time = today_start - (86400 * 7)
            text = re.sub(r'\blast week\b', '', text, flags=re.IGNORECASE).strip()

        # Clean up double spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return ParsedQuery(
            text=text,
            start_time=start_time,
            end_time=end_time,
            mandatory_keywords=mandatory_keywords
        )
