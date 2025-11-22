import re
from typing import List

def tokenize_text(text: str) -> List[str]:
    """
    Simple word tokenizer that normalizes text for fuzzy matching.
    Handles common encoding differences (apostrophes, dashes).
    """
    if not text:
        return []
        
    # Normalize unicode apostrophes and quotes to standard ASCII
    text = text.replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('—', '-').replace('–', '-').replace('\u2014', '-').replace('\u2013', '-')
    
    # Split on whitespace and punctuation, keep only words (alphanumeric)
    # Note: This strips punctuation, which is good for fuzzy matching logic
    tokens = re.findall(r'\w+', text.lower())
    return tokens

def find_token_sequence(haystack_tokens: List[str], needle_tokens: List[str]):
    """
    Find the start and end index of needle_tokens in haystack_tokens.
    Returns (start_idx, end_idx) or None if not found.
    """
    needle_len = len(needle_tokens)
    haystack_len = len(haystack_tokens)
    
    if needle_len == 0 or haystack_len == 0:
        return None
    
    for i in range(haystack_len - needle_len + 1):
        if haystack_tokens[i:i+needle_len] == needle_tokens:
            return (i, i + needle_len - 1)
            
    return None

