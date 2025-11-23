import os
import pickle
import json
import html
from pathlib import Path
from functools import lru_cache
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load .env file from project root (1 level up from reader_app)
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry, Highlight
from src.core.chat import ChatService
from src.core.obsidian import get_chapter_note_content, save_chapter_note_content
from src.core.highlighter import inject_highlights
from src.integrations.kobo import fetch_highlights

app = FastAPI()
# Templates are in src/web/templates relative to reader_app directory
templates = Jinja2Templates(directory="src/web/templates")

# Where are the book folders located?
BOOKS_DIR = "data/library"

# Initialize chat service (will raise error if GOOGLE_API_KEY not set)
try:
    chat_service = ChatService()
except ValueError as e:
    print(f"Warning: Chat service not available: {e}")
    chat_service = None

@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None

def save_book_to_disk(folder_name: str, book: Book):
    """Helper pour sauvegarder le pickle."""
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as f:
        pickle.dump(book, f)
    # Invalider le cache pour forcer le rechargement
    load_book_cached.cache_clear()

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            item_path = os.path.join(BOOKS_DIR, item)
            if item.endswith("_data") and os.path.isdir(item_path):
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine)
                    })

    return templates.TemplateResponse("library.html", {"request": request, "books": books})

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(book_id: str):
    """Helper to just go to chapter 0."""
    return await read_chapter(book_id=book_id, chapter_index=0)

@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    # Load note content for this chapter
    note_content = get_chapter_note_content(book.metadata.title, current_chapter.title)

    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx,
        "note_content": note_content
    })

@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)

    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)

# Notes API endpoints
@app.get("/api/notes/{book_id}/{chapter_index}")
async def get_notes(book_id: str, chapter_index: int):
    """Get notes for a specific chapter."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    current_chapter = book.spine[chapter_index]
    note_content = get_chapter_note_content(book.metadata.title, current_chapter.title)
    
    return JSONResponse({"content": note_content})

class NoteUpdate(BaseModel):
    content: str

@app.post("/api/notes/{book_id}/{chapter_index}")
async def save_notes(book_id: str, chapter_index: int, note_update: NoteUpdate):
    """Save notes for a specific chapter."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    current_chapter = book.spine[chapter_index]
    save_chapter_note_content(book.metadata.title, current_chapter.title, note_update.content)
    
    return JSONResponse({"status": "saved"})

# Chat API endpoints
class ChatMessage(BaseModel):
    message: str
    conversation_history: List[Dict[str, str]] = []
    quoted_text: Optional[str] = None
    include_chapter: bool = True
    include_notes: bool = True
    current_notes: Optional[str] = None
    snippets: List[str] = [] # List of text snippets to include in context

async def generate_chat_stream(chat_data: ChatMessage, book_id: str, chapter_index: int):
    """Generator function for streaming chat responses."""
    # Escape HTML to prevent XSS
    escaped_user_message = html.escape(chat_data.message)
    
    # Send user message first
    yield f"data: {json.dumps({'type': 'user_message', 'content': escaped_user_message})}\n\n"
    
    # Load book and chapter
    book = load_book_cached(book_id)
    if not book:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Book not found'})}\n\n"
        return
    
    if chapter_index < 0 or chapter_index >= len(book.spine):
        yield f"data: {json.dumps({'type': 'error', 'content': 'Chapter not found'})}\n\n"
        return
    
    current_chapter = book.spine[chapter_index]
    
    # Determine notes content: use provided content from frontend if available, else load from disk
    if chat_data.current_notes is not None:
        current_notes = chat_data.current_notes
    else:
        current_notes = get_chapter_note_content(book.metadata.title, current_chapter.title)
    
    print(f"[Chat] Received message: {chat_data.message[:100]}...")
    print(f"[Chat] Chapter: {current_chapter.title}")
    print(f"[Chat] Context - Chapter: {chat_data.include_chapter}, Notes: {chat_data.include_notes}")
    print(f"[Chat] Notes length: {len(current_notes)}")
    print(f"[Chat] Conversation history length: {len(chat_data.conversation_history)}")
    
    # Signal start of assistant message
    yield f"data: {json.dumps({'type': 'assistant_start'})}\n\n"
    
    # Stream LLM response
    try:
        for chunk in chat_service.send_message_stream(
            user_message=chat_data.message,
            chapter_title=current_chapter.title,
            chapter_text=current_chapter.text,
            current_notes=current_notes,
            conversation_history=chat_data.conversation_history,
            book_title=book.metadata.title,
            quoted_text=chat_data.quoted_text,
            include_chapter=chat_data.include_chapter,
            include_notes=chat_data.include_notes,
            snippets=chat_data.snippets
        ):
            # Escape HTML and send chunk
            escaped_chunk = html.escape(chunk)
            yield f"data: {json.dumps({'type': 'chunk', 'content': escaped_chunk})}\n\n"
        
        # Signal end of assistant message
        yield f"data: {json.dumps({'type': 'assistant_end'})}\n\n"
        
    except Exception as e:
        print(f"[Chat] Error calling LLM: {e}")
        import traceback
        traceback.print_exc()
        error_msg = html.escape(f"Erreur lors de la communication avec le LLM: {str(e)}")
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

@app.post("/chat/send")
async def send_chat_message(request: Request, chat_data: ChatMessage):
    """Send a chat message and stream LLM response."""
    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not available. Please set GOOGLE_API_KEY.")
    
    # Get book_id and chapter_index from query params
    book_id = request.query_params.get("book_id")
    chapter_index = request.query_params.get("chapter_index")
    
    if not book_id or chapter_index is None:
        raise HTTPException(status_code=400, detail="book_id and chapter_index are required")
    
    try:
        chapter_index = int(chapter_index)
    except ValueError:
        raise HTTPException(status_code=400, detail="chapter_index must be an integer")
    
    return StreamingResponse(
        generate_chat_stream(chat_data, book_id, chapter_index),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering for nginx
        }
    )

# Highlights API endpoints
class HighlightPayload(BaseModel):
    book_id: str
    chapter_index: int
    text: str
    annotation: Optional[str] = None

@app.post("/api/highlights/add")
async def add_highlight_endpoint(payload: HighlightPayload):
    """Ajoute un highlight manuel sans casser le contenu existant."""
    book = load_book_cached(payload.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if payload.chapter_index < 0 or payload.chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    current_chapter = book.spine[payload.chapter_index]
    
    # 1. Créer l'objet Highlight
    new_hl = Highlight(
        text=payload.text,
        annotation=payload.annotation or "Manuel",
        date="",
        chapter_id=""
    )
    
    # 2. Vérifier si ce highlight n'existe pas déjà (éviter doublons)
    existing_texts = {h.text.strip() for h in current_chapter.highlights}
    if payload.text.strip() in existing_texts:
        return JSONResponse({"status": "already_exists"})
    
    # 3. Mettre à jour la liste des highlights du chapitre
    current_chapter.highlights.append(new_hl)
    
    # 4. Injecter dans le HTML (PERSISTANCE)
    # On parse le contenu actuel (qui contient déjà des spans) pour ajouter le nouveau
    soup = BeautifulSoup(current_chapter.content, 'html.parser')
    
    # On utilise la fonction existante inject_highlights pour wrapper le texte
    inject_highlights(soup, [new_hl])
    
    current_chapter.content = str(soup)
    
    # 5. Sauvegarder sur le disque
    save_book_to_disk(payload.book_id, book)
    
    return JSONResponse({"status": "added"})

@app.post("/api/highlights/remove")
async def remove_highlight_endpoint(payload: HighlightPayload):
    """Supprime un highlight manuel."""
    book = load_book_cached(payload.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if payload.chapter_index < 0 or payload.chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")
        
    chapter = book.spine[payload.chapter_index]
    
    # 1. Retirer de la liste (filtrer par texte exact)
    original_count = len(chapter.highlights)
    chapter.highlights = [h for h in chapter.highlights if h.text.strip() != payload.text.strip()]
    
    # 2. Retirer du HTML (unwrap les spans manual-highlight qui contiennent ce texte)
    soup = BeautifulSoup(chapter.content, 'html.parser')
    for span in soup.find_all('span', class_='manual-highlight'):
        if span.get_text().strip() == payload.text.strip():
            span.unwrap()  # Enlève la balise <span> mais garde le texte
    
    chapter.content = str(soup)
    
    # Sauvegarder seulement si quelque chose a changé
    if len(chapter.highlights) < original_count:
        save_book_to_disk(payload.book_id, book)
    
    return JSONResponse({"status": "removed"})

@app.post("/api/books/{book_id}/sync-highlights")
async def sync_kobo_highlights(book_id: str):
    """
    Synchronise avec Kobo de manière ADDITIVE.
    Ne supprime pas les highlights manuels existants.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # 1. Récupérer les highlights frais depuis la DB Kobo
    kobo_highlights = fetch_highlights(book.metadata.title)
    if not kobo_highlights:
        return JSONResponse({"status": "no_new_highlights", "count": 0})

    added_count = 0
    
    # 2. Pour chaque chapitre, on vérifie quels highlights Kobo manquent
    for chapter in book.spine:
        soup = BeautifulSoup(chapter.content, 'html.parser')
        chapter_text = soup.get_text()  # Texte brut pour recherche rapide
        
        # Liste des textes déjà surlignés dans ce chapitre (pour éviter doublons)
        existing_texts = {h.text.strip() for h in chapter.highlights}
        
        new_chapter_highlights = []
        
        for kh in kobo_highlights:
            clean_text = kh.text.strip()
            
            # Si ce texte n'est pas déjà connu ET qu'il est présent dans ce chapitre
            if clean_text not in existing_texts and clean_text in chapter_text:
                new_chapter_highlights.append(kh)
                chapter.highlights.append(kh)  # Ajout à la liste de données
                added_count += 1
        
        # 3. Injection uniquement des NOUVEAUX highlights dans le HTML existant
        if new_chapter_highlights:
            inject_highlights(soup, new_chapter_highlights)
            chapter.content = str(soup)

    # 4. Sauvegarde globale
    if added_count > 0:
        save_book_to_disk(book_id, book)

    return JSONResponse({"status": "synced", "highlights_count": added_count})

if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
