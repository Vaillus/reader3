import os
import pickle
from functools import lru_cache
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.core.models import Book, ChapterContent, TOCEntry

app = FastAPI()

# Determine paths relative to this file
# Structure: reader_app/src/web/app.py -> templates is in reader_app/src/web/templates
BASE_DIR = Path(__file__).resolve().parent.parent.parent # reader_app/
TEMPLATES_DIR = BASE_DIR / "src" / "web" / "templates"
DATA_DIR = BASE_DIR / "data" / "library"

print(f"Server starting...")
print(f"Templates: {TEMPLATES_DIR}")
print(f"Library: {DATA_DIR}")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    file_path = DATA_DIR / folder_name / "book.pkl"
    if not file_path.exists():
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []
    
    if DATA_DIR.exists():
        for item in os.listdir(DATA_DIR):
            book_path = DATA_DIR / item
            if book_path.is_dir():
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

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(book_id: str):
    return await read_chapter(Request, book_id=book_id, chapter_index=0)

@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]
    
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx
    })

@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = DATA_DIR / safe_book_id / "images" / safe_image_name

    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)

def start_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8123)

