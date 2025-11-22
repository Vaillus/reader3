import os
import shutil
import pickle
from datetime import datetime
from urllib.parse import unquote
from typing import List, Dict
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment
from src.core.models import Book, BookMetadata, ChapterContent, TOCEntry, Highlight
from src.core.highlighter import inject_highlights
from src.integrations.kobo import fetch_highlights

def parse_epub(epub_path: str, output_dir: str, fetch_kobo_highlights: bool = True) -> Book:
    book = epub.read_epub(epub_path)
    metadata = _extract_metadata(book)
    highlights = []
    if fetch_kobo_highlights:
        highlights = fetch_highlights(metadata.title)
    if os.path.exists(output_dir) and ("data" in output_dir or "library" in output_dir):
        shutil.rmtree(output_dir)
    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)
    image_map = _extract_images(book, images_dir)
    toc_structure = _parse_toc_recursive(book.toc) or _get_fallback_toc(book)
    spine_chapters = []
    for i, spine_item in enumerate(book.spine):
        item_id, _ = spine_item
        item = book.get_item_with_id(item_id)
        if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        raw_content = item.get_content().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(raw_content, 'html.parser')
        _fix_image_sources(soup, image_map)
        _clean_html(soup)
        inject_highlights(soup, highlights)
        chapter_highlights = [hl for hl in highlights if hl.text[:20] in str(soup)]
        body = soup.find('body')
        final_html = "".join([str(x) for x in body.contents]) if body else str(soup)
        chapter = ChapterContent(
            id=item_id, href=item.get_name(), title=f"Section {i+1}",
            content=final_html, text=soup.get_text(separator=' '), order=i,
            highlights=chapter_highlights
        )
        spine_chapters.append(chapter)
    final_book = Book(
        metadata=metadata, spine=spine_chapters, toc=toc_structure,
        images=image_map, source_file=os.path.basename(epub_path),
        processed_at=datetime.now().isoformat()
    )
    _save_pickle(final_book, output_dir)
    return final_book

def _extract_metadata(book_obj) -> BookMetadata:
    def get_list(key): return [x[0] for x in (book_obj.get_metadata('DC', key) or [])]
    def get_one(key): d = book_obj.get_metadata('DC', key); return d[0][0] if d else None
    return BookMetadata(
        title=get_one('title') or "Untitled", language=get_one('language') or "en",
        authors=get_list('creator'), description=get_one('description'),
        publisher=get_one('publisher'), date=get_one('date'),
        identifiers=get_list('identifier'), subjects=get_list('subject')
    )

def _extract_images(book, images_dir) -> Dict[str, str]:
    image_map = {}
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            fname = os.path.basename(item.get_name())
            safe_fname = "".join([c for c in fname if c.isalpha() or c.isdigit() or c in '._-']).strip()
            with open(os.path.join(images_dir, safe_fname), 'wb') as f: f.write(item.get_content())
            image_map[item.get_name()] = f"images/{safe_fname}"
            image_map[fname] = f"images/{safe_fname}"
    return image_map

def _fix_image_sources(soup, image_map):
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if not src: continue
        src = unquote(src)
        fname = os.path.basename(src)
        if src in image_map: img['src'] = image_map[src]
        elif fname in image_map: img['src'] = image_map[fname]

def _clean_html(soup):
    for tag in soup(['script', 'style', 'iframe', 'video', 'nav', 'form', 'button']): tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)): comment.extract()

def _save_pickle(book: Book, output_dir: str):
    with open(os.path.join(output_dir, 'book.pkl'), 'wb') as f: pickle.dump(book, f)

def _parse_toc_recursive(toc_list, depth=0) -> List[TOCEntry]:
    result = []
    for item in toc_list:
        if isinstance(item, tuple):
            section, children = item
            entry = TOCEntry(section.title, section.href, section.href.split('#')[0], section.href.split('#')[1] if '#' in section.href else "", _parse_toc_recursive(children, depth + 1))
            result.append(entry)
        elif isinstance(item, epub.Link):
            entry = TOCEntry(item.title, item.href, item.href.split('#')[0], item.href.split('#')[1] if '#' in item.href else "")
            result.append(entry)
        elif isinstance(item, epub.Section):
             entry = TOCEntry(item.title, item.href, item.href.split('#')[0], item.href.split('#')[1] if '#' in item.href else "")
             result.append(entry)
    return result

def _get_fallback_toc(book_obj) -> List[TOCEntry]:
    return [TOCEntry(item.get_name().replace('.html', '').title(), item.get_name(), item.get_name(), "") 
            for item in book_obj.get_items() if item.get_type() == ebooklib.ITEM_DOCUMENT]
