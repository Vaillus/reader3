import re
from typing import List

def tokenize_text(text: str) -> List[str]:
    if not text:
        return []
    text = text.replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('—', '-').replace('–', '-').replace('\u2014', '-').replace('\u2013', '-')
    tokens = re.findall(r'\w+', text.lower())
    return tokens

def find_token_sequence(haystack_tokens: List[str], needle_tokens: List[str]):
    needle_len = len(needle_tokens)
    haystack_len = len(haystack_tokens)
    if needle_len == 0 or haystack_len == 0:
        return None
    for i in range(haystack_len - needle_len + 1):
        if haystack_tokens[i:i+needle_len] == needle_tokens:
            return (i, i + needle_len - 1)
    return None
