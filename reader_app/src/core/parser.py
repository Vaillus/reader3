import os
import shutil
import pickle
from datetime import datetime
from urllib.parse import unquote
from typing import List, Dict, Optional

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment

from src.core.models import Book, BookMetadata, ChapterContent, TOCEntry, Highlight
from src.core.highlighter import inject_highlights
from src.integrations.kobo import fetch_highlights

def parse_epub(epub_path: str, output_dir: str, fetch_kobo_highlights: bool = True) -> Book:
    """
    Main logic: Parse EPUB -> Extract Metadata -> Fetch Highlights -> Inject -> Return Book Object
    Also handles image extraction to output_dir.
    """
    
    # 1. Load Book
    print(f"Loading {epub_path}...")
    try:
        book = epub.read_epub(epub_path)
    except Exception as e:
        raise RuntimeError(f"Failed to read EPUB file: {e}")

    # 2. Extract Metadata
    metadata = _extract_metadata(book)
    
    # 3. Fetch Highlights
    highlights = []
    if fetch_kobo_highlights:
        highlights = fetch_highlights(metadata.title)
        print(f"Retrieved {len(highlights)} highlights from Kobo.")

    # 4. Prepare Output Directories
    if os.path.exists(output_dir):
        # Safety check: don't delete root or weird paths
        if "data" in output_dir or "library" in output_dir:
            shutil.rmtree(output_dir)
    
    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    # 5. Extract Images
    print("Extracting images...")
    image_map = _extract_images(book, images_dir)

    # 6. Process TOC
    print("Parsing Table of Contents...")
    toc_structure = _parse_toc_recursive(book.toc)
    if not toc_structure:
        toc_structure = _get_fallback_toc(book)

    # 7. Process Content (Spine)
    print("Processing chapters...")
    spine_chapters = []

    for i, spine_item in enumerate(book.spine):
        item_id, _ = spine_item
        item = book.get_item_with_id(item_id)

        if not item:
            continue

        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Raw content
            raw_content = item.get_content().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(raw_content, 'html.parser')

            # A. Fix Images
            _fix_image_sources(soup, image_map)

            # B. Clean HTML
            _clean_html(soup)
            
            # C. Inject Highlights
            # We pass ALL highlights to every chapter. The injector finds matching text.
            inject_highlights(soup, highlights)
            
            # Filter highlights that were effectively found in this chapter (simple text check)
            # This is an approximation for the metadata
            chapter_highlights = [hl for hl in highlights if hl.text[:20] in str(soup)]

            # D. Extract Body
            body = soup.find('body')
            final_html = "".join([str(x) for x in body.contents]) if body else str(soup)

            # E. Create Object
            chapter = ChapterContent(
                id=item_id,
                href=item.get_name(),
                title=f"Section {i+1}", # Can be improved by mapping TOC
                content=final_html,
                text=soup.get_text(separator=' '),
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
    
    # 9. Save to disk (Pickle)
    _save_pickle(final_book, output_dir)
    
    return final_book

# --- Internal Helpers ---

def _extract_metadata(book_obj) -> BookMetadata:
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

def _extract_images(book, images_dir) -> Dict[str, str]:
    image_map = {}
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            original_fname = os.path.basename(item.get_name())
            # Safe filename
            safe_fname = "".join([c for c in original_fname if c.isalpha() or c.isdigit() or c in '._-']).strip()
            
            local_path = os.path.join(images_dir, safe_fname)
            with open(local_path, 'wb') as f:
                f.write(item.get_content())

            rel_path = f"images/{safe_fname}"
            image_map[item.get_name()] = rel_path
            image_map[original_fname] = rel_path
    return image_map

def _fix_image_sources(soup, image_map):
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if not src: continue
        
        src_decoded = unquote(src)
        filename = os.path.basename(src_decoded)

        if src_decoded in image_map:
            img['src'] = image_map[src_decoded]
        elif filename in image_map:
            img['src'] = image_map[filename]

def _clean_html(soup):
    for tag in soup(['script', 'style', 'iframe', 'video', 'nav', 'form', 'button']):
        tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

def _save_pickle(book: Book, output_dir: str):
    p_path = os.path.join(output_dir, 'book.pkl')
    with open(p_path, 'wb') as f:
        pickle.dump(book, f)
    print(f"Book data saved to {p_path}")

def _parse_toc_recursive(toc_list, depth=0) -> List[TOCEntry]:
    result = []
    for item in toc_list:
        if isinstance(item, tuple):
            section, children = item
            entry = TOCEntry(
                title=section.title,
                href=section.href,
                file_href=section.href.split('#')[0],
                anchor=section.href.split('#')[1] if '#' in section.href else "",
                children=_parse_toc_recursive(children, depth + 1)
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
        elif isinstance(item, epub.Section):
             entry = TOCEntry(
                title=item.title,
                href=item.href,
                file_href=item.href.split('#')[0],
                anchor=item.href.split('#')[1] if '#' in item.href else ""
            )
             result.append(entry)
    return result

def _get_fallback_toc(book_obj) -> List[TOCEntry]:
    toc = []
    for item in book_obj.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            name = item.get_name()
            title = item.get_name().replace('.html', '').replace('.xhtml', '').replace('_', ' ').title()
            toc.append(TOCEntry(title=title, href=name, file_href=name, anchor=""))
    return toc

