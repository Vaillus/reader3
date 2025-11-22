"""
Parses an EPUB file into a structured object that can be used to serve the book via a web interface.
"""

import os
import pickle
import shutil
import sqlite3
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from urllib.parse import unquote
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment

# --- Data structures ---

@dataclass
class Highlight:
    """Represents a user highlight from Kobo"""
    text: str
    annotation: str
    date: str
    chapter_id: str

@dataclass
class ChapterContent:
    """
    Represents a physical file in the EPUB (Spine Item).
    A single file might contain multiple logical chapters (TOC entries).
    """
    id: str           # Internal ID (e.g., 'item_1')
    href: str         # Filename (e.g., 'part01.html')
    title: str        # Best guess title from file
    content: str      # Cleaned HTML with rewritten image paths
    text: str         # Plain text for search/LLM context
    order: int        # Linear reading order
    highlights: List[Highlight] = field(default_factory=list) # List of highlights in this chapter


@dataclass
class TOCEntry:
    """Represents a logical entry in the navigation sidebar."""
    title: str
    href: str         # original href (e.g., 'part01.html#chapter1')
    file_href: str    # just the filename (e.g., 'part01.html')
    anchor: str       # just the anchor (e.g., 'chapter1'), empty if none
    children: List['TOCEntry'] = field(default_factory=list)


@dataclass
class BookMetadata:
    """Metadata"""
    title: str
    language: str
    authors: List[str] = field(default_factory=list)
    description: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    identifiers: List[str] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)


@dataclass
class Book:
    """The Master Object to be pickled."""
    metadata: BookMetadata
    spine: List[ChapterContent]  # The actual content (linear files)
    toc: List[TOCEntry]          # The navigation tree
    images: Dict[str, str]       # Map: original_path -> local_path

    # Meta info
    source_file: str
    processed_at: str
    version: str = "3.0"


# --- Utilities ---

def clean_html_content(soup: BeautifulSoup) -> BeautifulSoup:

    # Remove dangerous/useless tags
    for tag in soup(['script', 'style', 'iframe', 'video', 'nav', 'form', 'button']):
        tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove input tags
    for tag in soup.find_all('input'):
        tag.decompose()

    return soup


def extract_plain_text(soup: BeautifulSoup) -> str:
    """Extract clean text for LLM/Search usage."""
    text = soup.get_text(separator=' ')
    # Collapse whitespace
    return ' '.join(text.split())


def parse_toc_recursive(toc_list, depth=0) -> List[TOCEntry]:
    """
    Recursively parses the TOC structure from ebooklib.
    """
    result = []

    for item in toc_list:
        # ebooklib TOC items are either `Link` objects or tuples (Section, [Children])
        if isinstance(item, tuple):
            section, children = item
            entry = TOCEntry(
                title=section.title,
                href=section.href,
                file_href=section.href.split('#')[0],
                anchor=section.href.split('#')[1] if '#' in section.href else "",
                children=parse_toc_recursive(children, depth + 1)
            )
            result.append(entry)
        elif isinstance(item, epub.Link):
            entry = TOCEntry(
                title=item.title,
                href=item.href,
                file_href=item.href.split('#')[0],
                anchor=item.href.split('#')[1] if '#' in item.href else ""
            )
            result.append(entry)
        # Note: ebooklib sometimes returns direct Section objects without children
        elif isinstance(item, epub.Section):
             entry = TOCEntry(
                title=item.title,
                href=item.href,
                file_href=item.href.split('#')[0],
                anchor=item.href.split('#')[1] if '#' in item.href else ""
            )
             result.append(entry)

    return result


def get_fallback_toc(book_obj) -> List[TOCEntry]:
    """
    If TOC is missing, build a flat one from the Spine.
    """
    toc = []
    for item in book_obj.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            name = item.get_name()
            # Try to guess a title from the content or ID
            title = item.get_name().replace('.html', '').replace('.xhtml', '').replace('_', ' ').title()
            toc.append(TOCEntry(title=title, href=name, file_href=name, anchor=""))
    return toc


def extract_metadata_robust(book_obj) -> BookMetadata:
    """
    Extracts metadata handling both single and list values.
    """
    def get_list(key):
        data = book_obj.get_metadata('DC', key)
        return [x[0] for x in data] if data else []

    def get_one(key):
        data = book_obj.get_metadata('DC', key)
        return data[0][0] if data else None

    return BookMetadata(
        title=get_one('title') or "Untitled",
        language=get_one('language') or "en",
        authors=get_list('creator'),
        description=get_one('description'),
        publisher=get_one('publisher'),
        date=get_one('date'),
        identifiers=get_list('identifier'),
        subjects=get_list('subject')
    )


# --- Highlights Integration ---

def get_kobo_db_path() -> Path:
    """Returns the path to the Kobo database on macOS."""
    # Try both possible filenames
    base = Path(os.path.expanduser("~/Library/Application Support/Kobo/Kobo Desktop Edition"))
    for name in ["Kobo.sqlite", "Book.sqlite", "KoboReader.sqlite"]:
        p = base / name
        if p.exists():
            return p
    return None

def get_highlights_for_book(title_part: str) -> List[Highlight]:
    """
    Fetches highlights from Kobo DB matching the book title.
    Returns a list of Highlight objects.
    """
    db_path = get_kobo_db_path()
    if not db_path:
        print("Warning: Kobo database not found.")
        return []

    print(f"Checking Kobo DB at {db_path} for highlights...")
    results = []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Find the VolumeID
        cursor.execute("""
            SELECT ContentID, Title 
            FROM content 
            WHERE Title LIKE ? AND ContentType = 6 
            LIMIT 1
        """, (f"%{title_part}%",))
        
        book_row = cursor.fetchone()
        
        # Fallback: loose search
        if not book_row:
            cursor.execute("SELECT ContentID, Title FROM content WHERE Title LIKE ? LIMIT 1", (f"%{title_part}%",))
            book_row = cursor.fetchone()
            
        if not book_row:
            print(f"No book found in Kobo DB for '{title_part}'")
            conn.close()
            return []
            
        full_id = book_row[0]
        volume_id = full_id.split('!')[0]
        print(f"Found Kobo Book ID: {volume_id} ({book_row[1]})")
        
        # 2. Fetch Highlights
        query = """
            SELECT Text, Annotation, ContentID, DateCreated
            FROM Bookmark 
            WHERE VolumeID = ? 
            AND Type = 'highlight'
            ORDER BY DateCreated
        """
        cursor.execute(query, (volume_id,))
        rows = cursor.fetchall()
        
        for row in rows:
            results.append(Highlight(
                text=row[0],
                annotation=row[1],
                chapter_id=row[2],
                date=row[3]
            ))
            
        print(f"Found {len(results)} highlights.")
        conn.close()
        
    except sqlite3.Error as e:
        print(f"SQLite Error: {e}")
        
    return results

def tokenize_text(text: str) -> List[str]:
    """Simple word tokenizer that normalizes text."""
    import re
    # Normalize unicode apostrophes and quotes
    text = text.replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2014', '-').replace('\u2013', '-')
    # Split on whitespace and punctuation, keep only words
    tokens = re.findall(r'\w+', text.lower())
    return tokens

def find_token_sequence(haystack_tokens: List[str], needle_tokens: List[str]) -> Optional[Tuple[int, int]]:
    """
    Find the start and end index of needle_tokens in haystack_tokens.
    Returns (start_idx, end_idx) or None if not found.
    """
    needle_len = len(needle_tokens)
    haystack_len = len(haystack_tokens)
    
    for i in range(haystack_len - needle_len + 1):
        if haystack_tokens[i:i+needle_len] == needle_tokens:
            return (i, i + needle_len - 1)
    return None

def inject_highlights_into_soup(soup: BeautifulSoup, highlights: List[Highlight]) -> BeautifulSoup:
    """
    Injects highlights into HTML using token-based sequence matching.
    This approach is robust against HTML tags splitting the text.
    """
    if not highlights:
        return soup
    
    import re
    
    matched_highlights = []
    
    for hl in highlights:
        raw_text = hl.text.strip()
        if not raw_text or len(raw_text) < 5:
            continue
        
        # Tokenize the highlight
        hl_tokens = tokenize_text(raw_text)
        if len(hl_tokens) < 2:  # Skip very short highlights
            continue
        
        # Strategy: Find blocks (paragraphs, divs) and check if highlight is inside
        for block in soup.find_all(['p', 'div', 'li', 'blockquote', 'td', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            # Extract text from this block
            block_text = block.get_text()
            block_tokens = tokenize_text(block_text)
            
            # Try to find the highlight token sequence
            match = find_token_sequence(block_tokens, hl_tokens)
            
            if match:
                start_idx, end_idx = match
                
                # Now the hard part: map token indices back to the HTML structure
                # We need to traverse the block's text nodes and wrap the right portion
                
                # Collect all text nodes in reading order with their token ranges
                text_nodes = []
                current_token_idx = 0
                
                for text_node in block.find_all(string=True):
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
                
                # Find which text nodes contain the highlight
                nodes_to_wrap = []
                for node_info in text_nodes:
                    # Check if this node overlaps with [start_idx, end_idx]
                    if not (node_info['token_end'] < start_idx or node_info['token_start'] > end_idx):
                        nodes_to_wrap.append(node_info)
                
                if not nodes_to_wrap:
                    continue
                
                # Case 1: Highlight is entirely within ONE text node
                if len(nodes_to_wrap) == 1:
                    node_info = nodes_to_wrap[0]
                    text_node = node_info['node']
                    
                    # Calculate the character positions (approximate)
                    # This is tricky because tokens are normalized
                    # Simple approach: wrap the entire text node if it's small enough
                    # Or use a fuzzy regex search
                    
                    # Try regex with flexible whitespace
                    escaped_text = re.escape(raw_text)
                    pattern_str = escaped_text.replace(r'\ ', r'\s+')
                    pattern_str = pattern_str.replace("'", r"['\u2019]")  # Handle apostrophe variants
                    
                    try:
                        pattern = re.compile(pattern_str, re.IGNORECASE)
                        if pattern.search(str(text_node)):
                            def replace_func(match):
                                return f'<span class="highlight" title="{hl.annotation or ""}">{match.group(0)}</span>'
                            
                            new_content = pattern.sub(replace_func, str(text_node))
                            new_tag = BeautifulSoup(new_content, 'html.parser')
                            text_node.replace_with(new_tag)
                            matched_highlights.append(hl)
                            break  # Highlight injected, move to next highlight
                    except re.error:
                        pass
                
                # Case 2: Highlight spans multiple nodes (complex)
                # For now, we wrap the entire range by inserting marks around the first and last node
                # This is a simplified approach that may not be perfect visually but preserves structure
                elif len(nodes_to_wrap) > 1:
                    # Insert opening <span class="highlight"> before first node
                    first_node = nodes_to_wrap[0]['node']
                    last_node = nodes_to_wrap[-1]['node']
                    
                    # Wrap the content by inserting tags
                    # This is tricky with BeautifulSoup - we need to insert new tags
                    # Simplified: wrap each node individually
                    for node_info in nodes_to_wrap:
                        text_node = node_info['node']
                        wrapped = soup.new_tag('span', **{'class': 'highlight', 'title': hl.annotation or ""})
                        text_node.wrap(wrapped)
                    
                    matched_highlights.append(hl)
                    break  # Move to next highlight
                
    return soup


# --- Main Conversion Logic ---

def process_epub(epub_path: str, output_dir: str) -> Book:

    # 1. Load Book
    print(f"Loading {epub_path}...")
    book = epub.read_epub(epub_path)

    # 2. Extract Metadata
    metadata = extract_metadata_robust(book)
    
    # 3. Fetch Highlights (Kobo)
    # We use the title from metadata to find it in DB
    highlights = get_highlights_for_book(metadata.title)

    # 4. Prepare Output Directories
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    # 5. Extract Images & Build Map
    print("Extracting images...")
    image_map = {} # Key: internal_path, Value: local_relative_path

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            # Normalize filename
            original_fname = os.path.basename(item.get_name())
            # Sanitize filename for OS
            safe_fname = "".join([c for c in original_fname if c.isalpha() or c.isdigit() or c in '._-']).strip()

            # Save to disk
            local_path = os.path.join(images_dir, safe_fname)
            with open(local_path, 'wb') as f:
                f.write(item.get_content())

            # Map keys: We try both the full internal path and just the basename
            # to be robust against messy HTML src attributes
            rel_path = f"images/{safe_fname}"
            image_map[item.get_name()] = rel_path
            image_map[original_fname] = rel_path

    # 6. Process TOC
    print("Parsing Table of Contents...")
    toc_structure = parse_toc_recursive(book.toc)
    if not toc_structure:
        print("Warning: Empty TOC, building fallback from Spine...")
        toc_structure = get_fallback_toc(book)

    # 7. Process Content (Spine-based to preserve HTML validity)
    print("Processing chapters...")
    spine_chapters = []

    # We iterate over the spine (linear reading order)
    for i, spine_item in enumerate(book.spine):
        item_id, linear = spine_item
        item = book.get_item_with_id(item_id)

        if not item:
            continue

        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Raw content
            raw_content = item.get_content().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(raw_content, 'html.parser')

            # A. Fix Images
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if not src: continue

                # Decode URL (part01/image%201.jpg -> part01/image 1.jpg)
                src_decoded = unquote(src)
                filename = os.path.basename(src_decoded)

                # Try to find in map
                if src_decoded in image_map:
                    img['src'] = image_map[src_decoded]
                elif filename in image_map:
                    img['src'] = image_map[filename]

            # B. Clean HTML
            soup = clean_html_content(soup)
            
            # C. Inject Highlights
            # Filter highlights that might belong to this chapter (based on content search)
            # Since mapping IDs is hard, we just pass all highlights and let the text searcher find them
            soup = inject_highlights_into_soup(soup, highlights)
            
            # Count highlights in this chapter by looking for <span class="highlight">
            chapter_highlights = []
            for hl in highlights:
                # Check if this highlight was injected (approximation: check if text exists in modified soup)
                if '<span class="highlight"' in str(soup) and hl.text[:30] in str(soup):
                    chapter_highlights.append(hl)

            # D. Extract Body Content only
            body = soup.find('body')
            if body:
                # Extract inner HTML of body
                final_html = "".join([str(x) for x in body.contents])
            else:
                final_html = str(soup)

            # E. Create Object
            chapter = ChapterContent(
                id=item_id,
                href=item.get_name(), # Important: This links TOC to Content
                title=f"Section {i+1}", # Fallback, real titles come from TOC
                content=final_html,
                text=extract_plain_text(soup),
                order=i,
                highlights=chapter_highlights
            )
            spine_chapters.append(chapter)

    # 8. Final Assembly
    final_book = Book(
        metadata=metadata,
        spine=spine_chapters,
        toc=toc_structure,
        images=image_map,
        source_file=os.path.basename(epub_path),
        processed_at=datetime.now().isoformat()
    )

    return final_book


def save_to_pickle(book: Book, output_dir: str):
    p_path = os.path.join(output_dir, 'book.pkl')
    with open(p_path, 'wb') as f:
        pickle.dump(book, f)
    print(f"Saved structured data to {p_path}")


# --- CLI ---

if __name__ == "__main__":

    import sys
    if len(sys.argv) < 2:
        print("Usage: python reader3.py <file.epub>")
        sys.exit(1)

    epub_file = sys.argv[1]
    assert os.path.exists(epub_file), "File not found."
    out_dir = os.path.splitext(epub_file)[0] + "_data"

    book_obj = process_epub(epub_file, out_dir)
    save_to_pickle(book_obj, out_dir)
    print("\n--- Summary ---")
    print(f"Title: {book_obj.metadata.title}")
    print(f"Authors: {', '.join(book_obj.metadata.authors)}")
    print(f"Physical Files (Spine): {len(book_obj.spine)}")
    print(f"TOC Root Items: {len(book_obj.toc)}")
    print(f"Images extracted: {len(book_obj.images)}")
    
    total_hl = sum(len(c.highlights) for c in book_obj.spine)
    print(f"Highlights found & injected: {total_hl}")
