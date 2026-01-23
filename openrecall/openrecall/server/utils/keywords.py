import re
from collections import Counter
from typing import List

class KeywordExtractor:
    # Common English stopwords + programming keywords
    STOPWORDS = {
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
        "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
        "this", "but", "his", "by", "from", "they", "we", "say", "her",
        "she", "or", "an", "will", "my", "one", "all", "would", "there",
        "their", "what", "so", "up", "out", "if", "about", "who", "get",
        "which", "go", "me", "when", "make", "can", "like", "time", "no",
        "just", "him", "know", "take", "people", "into", "year", "your",
        "good", "some", "could", "them", "see", "other", "than", "then",
        "now", "look", "only", "come", "its", "over", "think", "also",
        "back", "after", "use", "two", "how", "our", "work", "first",
        "well", "way", "even", "new", "want", "because", "any", "these",
        "give", "day", "most", "us", "def", "class", "import", "return",
        "from", "self", "none", "true", "false", "file", "path", "str",
        "int", "float", "list", "dict", "bool", "var", "val", "const",
        "function", "async", "await"
    }

    def __init__(self, strategy: str = "local"):
        self.strategy = strategy

    def extract(self, text: str) -> List[str]:
        """Extract top 10 keywords from text."""
        if not text:
            return []
        
        # Tokenize (lowercase, only word characters)
        words = re.findall(r'\w+', text.lower())
        
        # Filter: length >= 3, not in stopwords, not purely digits
        filtered_words = [
            w for w in words 
            if len(w) >= 3 and w not in self.STOPWORDS and not w.isdigit()
        ]
        
        # Count and get top 10
        counter = Counter(filtered_words)
        return [word for word, _ in counter.most_common(10)]
