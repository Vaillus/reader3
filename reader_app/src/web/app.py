import os
import pickle
import tempfile
from functools import lru_cache
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup

from src.core.models import Book, ChapterContent, TOCEntry, Highlight, BookMetadata
from src.core.parser import parse_epub
from src.core.highlighter import inject_highlights
from src.integrations.kobo_service import KoboService
from src.integrations.kobo import fetch_highlights
from src.core.obsidian import ensure_main_note_exists, get_chapter_note_content, save_chapter_note_content
from pydantic import BaseModel

app = FastAPI()

class NoteUpdate(BaseModel):
    content: str

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "src" / "web" / "templates"
DATA_DIR = BASE_DIR / "data" / "library"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
kobo_service = KoboService()

@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    file_path = DATA_DIR / folder_name / "book.pkl"
    if not file_path.exists(): return None
    try:
        with open(file_path, "rb") as f: return pickle.load(f)
    except Exception: return None

def _strip_highlights(html_content: str) -> str:
    """Removes highlight spans but keeps their text content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    for span in soup.find_all('span', class_='highlight'):
        span.unwrap()
    return str(soup)

@app.post("/api/books/{book_id}/sync-highlights")
async def sync_highlights(book_id: str):
    # 1. Load book
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # 2. Fetch new highlights
    try:
        new_highlights = fetch_highlights(book.metadata.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching highlights: {str(e)}")
    
    # 3. Update each chapter
    total_injected = 0
    for chapter in book.spine:
        # Strip old highlights
        clean_html = _strip_highlights(chapter.content)
        
        # Inject new highlights
        soup = BeautifulSoup(clean_html, 'html.parser')
        inject_highlights(soup, new_highlights)
        
        # Identify which highlights ended up in this chapter
        # Note: simple heuristic check if highlight text is in content
        chapter_highlights = []
        soup_str = str(soup)
        for hl in new_highlights:
            # Check if a significant part of the highlight exists in the chapter
            # We use a small snippet to check presence because full text match might be tricky with HTML
            snippet = hl.text[:50] if len(hl.text) > 50 else hl.text
            if snippet in soup_str:
                chapter_highlights.append(hl)
        
        chapter.highlights = chapter_highlights
        total_injected += len(chapter_highlights)
        
        # Update content
        chapter.content = str(soup)
        
    # 4. Save book
    # We need to invalidate cache too
    load_book_cached.cache_clear()
    
    # Save using pickle
    book_dir = DATA_DIR / book_id
    with open(book_dir / "book.pkl", "wb") as f:
        pickle.dump(book, f)
        
    return {"status": "success", "highlights_count": total_injected}

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    books = []
    if DATA_DIR.exists():
        for item in os.listdir(DATA_DIR):
            if (DATA_DIR / item).is_dir():
                book = load_book_cached(item)
                if book:
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine),
                        "highlights": sum(len(c.highlights) for c in book.spine)
                    })
    return templates.TemplateResponse("library.html", {"request": request, "books": books})

@app.get("/import", response_class=HTMLResponse)
async def import_view(request: Request):
    return templates.TemplateResponse("import.html", {"request": request})

@app.get("/api/kobo/books")
async def list_kobo_books():
    books = kobo_service.list_books()
    return JSONResponse(content=books)

@app.post("/api/kobo/import/{book_id}")
async def import_kobo_book(book_id: str):
    # 1. Create temp dir
    with tempfile.TemporaryDirectory() as tmpdirname:
        # 2. Download
        epub_path = kobo_service.download_book(book_id, tmpdirname)
        if not epub_path:
            raise HTTPException(status_code=500, detail="Download failed")
        
        # 3. Parse and Import
        # We need a consistent naming strategy for the library folder
        # We parse to get title first?
        # Let's parse into a temporary location first to get metadata
        # Actually parse_epub handles the whole flow including creating output dir.
        # But we need to know the output dir name.
        
        # Simple approach: Import using book_id as safe name initially?
        # Or read metadata from epub first?
        
        # Let's do a quick parse to get metadata
        try:
            from ebooklib import epub
            book_tmp = epub.read_epub(str(epub_path))
            title = book_tmp.get_metadata('DC', 'title')[0][0]
            safe_title = "".join([c for c in title if c.isalnum() or c in ' -_']).strip().replace(' ', '_')
            
            library_folder = f"{safe_title}_data"
            output_dir = DATA_DIR / library_folder
            
            # Now run full parse
            final_book = parse_epub(str(epub_path), str(output_dir), fetch_kobo_highlights=True)
            
            return {"status": "success", "title": final_book.metadata.title, "library_id": library_folder}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(book_id: str):
    return await read_chapter(Request, book_id=book_id, chapter_index=0)

@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    book = load_book_cached(book_id)
    if not book: raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine): raise HTTPException(status_code=404, detail="Chapter not found")
    
    current_chapter = book.spine[chapter_index]
    
    # --- OBSIDIAN INTEGRATION ---
    # 1. Ensure main note exists (without chapter links)
    ensure_main_note_exists(book.metadata.title)
    
    # 2. Get existing note content for this chapter (always reload from disk for bi-directional sync)
    note_content = get_chapter_note_content(book.metadata.title, current_chapter.title)
    # ----------------------------
    
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    return templates.TemplateResponse("reader.html", {
        "request": request, "book": book, "current_chapter": current_chapter,
        "chapter_index": chapter_index, "book_id": book_id, "prev_idx": prev_idx, "next_idx": next_idx,
        "note_content": note_content
    })

@app.post("/api/notes/{book_id}/{chapter_index}")
async def save_note(book_id: str, chapter_index: int, note: NoteUpdate):
    book = load_book_cached(book_id)
    if not book: raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine): 
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    chapter = book.spine[chapter_index]
    try:
        save_chapter_note_content(book.metadata.title, chapter.title, note.content)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/notes/{book_id}/{chapter_index}")
async def get_note(book_id: str, chapter_index: int):
    """Get the latest note content from Obsidian (for bi-directional sync)."""
    book = load_book_cached(book_id)
    if not book: raise HTTPException(status_code=404, detail="Book not found")
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    chapter = book.spine[chapter_index]
    try:
        content = get_chapter_note_content(book.metadata.title, chapter.title)
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    img_path = DATA_DIR / os.path.basename(book_id) / "images" / os.path.basename(image_name)
    if not img_path.exists(): raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(img_path)

def start_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8123)
