import os
import pickle
import json
import html
from pathlib import Path
from functools import lru_cache
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env file from project root (1 level up from reader_app)
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry, Highlight
from src.core.chat import ChatService
from src.core.obsidian import get_chapter_note_content, save_chapter_note_content

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

@app.post("/chat/send")
async def send_chat_message(request: Request, chat_data: ChatMessage):
    """Send a chat message and get LLM response."""
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
    
    # Load book and chapter
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    current_chapter = book.spine[chapter_index]
    current_notes = get_chapter_note_content(book.metadata.title, current_chapter.title)
    
    print(f"[Chat] Received message: {chat_data.message[:100]}...")
    print(f"[Chat] Chapter: {current_chapter.title}")
    print(f"[Chat] Conversation history length: {len(chat_data.conversation_history)}")
    
    # Get LLM response
    try:
        response_text, updated_notes = chat_service.send_message(
            user_message=chat_data.message,
            chapter_title=current_chapter.title,
            chapter_text=current_chapter.text,
            current_notes=current_notes,
            conversation_history=chat_data.conversation_history,
            book_title=book.metadata.title,
            quoted_text=chat_data.quoted_text
        )
        print(f"[Chat] LLM response received: {response_text[:100]}...")
    except Exception as e:
        print(f"[Chat] Error calling LLM: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error calling LLM: {str(e)}")
    
    # If notes were updated, save them
    if updated_notes is not None:
        print(f"[Chat] Notes updated by LLM")
        save_chapter_note_content(book.metadata.title, current_chapter.title, updated_notes)
    
    # Return HTML fragment for HTMX
    # The response includes both the chat message and optionally the updated note editor
    html_parts = []
    
    # Escape HTML to prevent XSS
    escaped_user_message = html.escape(chat_data.message)
    escaped_response = html.escape(response_text)
    
    # Add user message
    html_parts.append(f'''
    <div class="chat-message user-message">
        <div class="message-content">{escaped_user_message}</div>
    </div>
    ''')
    
    # Add assistant response (convert newlines to <br> for better display)
    escaped_response_formatted = escaped_response.replace('\n', '<br>')
    html_parts.append(f'''
    <div class="chat-message assistant-message">
        <div class="message-content">{escaped_response_formatted}</div>
    </div>
    ''')
    
    # If notes were updated, add OOB swap for the note editor
    if updated_notes is not None:
        # Escape notes content for textarea (but preserve newlines)
        escaped_notes = html.escape(updated_notes)
        html_parts.append(f'''
    <textarea id="note-editor" class="notes-editor" placeholder="Write your notes here... they will sync to Obsidian." hx-swap-oob="true">{escaped_notes}</textarea>
    ''')
    
    return HTMLResponse(content="".join(html_parts))

if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
