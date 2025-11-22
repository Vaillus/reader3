import re
import logging
from typing import List, Dict
from bs4 import BeautifulSoup
from src.core.models import Highlight
from src.utils.text import tokenize_text, find_token_sequence

logger = logging.getLogger(__name__)

def inject_highlights(soup: BeautifulSoup, highlights: List[Highlight]) -> BeautifulSoup:
    if not highlights:
        return soup
    for hl in highlights:
        raw_text = hl.text.strip()
        if not raw_text or len(raw_text) < 5:
            continue
        hl_tokens = tokenize_text(raw_text)
        if len(hl_tokens) < 2:
            continue
        for block in soup.find_all(['p', 'div', 'li', 'blockquote', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            block_text = block.get_text()
            block_tokens = tokenize_text(block_text)
            match = find_token_sequence(block_tokens, hl_tokens)
            if match:
                start_idx, end_idx = match
                text_nodes = _get_text_nodes_with_tokens(block)
                nodes_to_wrap = []
                for node_info in text_nodes:
                    if not (node_info['token_end'] < start_idx or node_info['token_start'] > end_idx):
                        nodes_to_wrap.append(node_info)
                if not nodes_to_wrap:
                    continue
                _wrap_nodes(soup, nodes_to_wrap, hl, raw_text)
                break 
    return soup

def _get_text_nodes_with_tokens(block_element) -> List[Dict]:
    text_nodes = []
    current_token_idx = 0
    for text_node in block_element.find_all(string=True):
        text = str(text_node)
        node_tokens = tokenize_text(text)
        node_token_count = len(node_tokens)
        if node_token_count > 0:
            text_nodes.append({
                'node': text_node,
                'text': text,
                'token_start': current_token_idx,
                'token_end': current_token_idx + node_token_count - 1,
                'tokens': node_tokens
            })
            current_token_idx += node_token_count
    return text_nodes

def _wrap_nodes(soup: BeautifulSoup, nodes_to_wrap: List[Dict], highlight: Highlight, raw_text: str):
    if len(nodes_to_wrap) == 1:
        node_info = nodes_to_wrap[0]
        text_node = node_info['node']
        escaped_text = re.escape(raw_text)
        pattern_str = escaped_text.replace(r'\ ', r'\s+').replace("'", r"['\u2019]")
        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            if pattern.search(str(text_node)):
                def replace_func(match):
                    title_attr = f' title="{highlight.annotation}"' if highlight.annotation else ''
                    return f'<span class="highlight"{title_attr}>{match.group(0)}</span>'
                new_content = pattern.sub(replace_func, str(text_node))
                new_tag = BeautifulSoup(new_content, 'html.parser')
                text_node.replace_with(new_tag)
        except re.error:
            pass
    else:
        for node_info in nodes_to_wrap:
            text_node = node_info['node']
            attrs = {'class': 'highlight'}
            if highlight.annotation:
                attrs['title'] = highlight.annotation
            wrapped = soup.new_tag('span', **attrs)
            text_node.wrap(wrapped)
