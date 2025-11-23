"""Module for managing chat sessions storage."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict, field


@dataclass
class ChatSession:
    """Represents a chat session for a chapter."""
    id: str
    chapter_index: int
    created_at: str
    title: str
    messages: List[Dict[str, str]] = field(default_factory=list)


def get_chats_file_path(book_id: str) -> Path:
    """Returns the path to the chats.json file for a book."""
    # BOOKS_DIR is "data/library" relative to reader_app directory
    project_root = Path(__file__).resolve().parent.parent.parent
    chats_file = project_root / "data" / "library" / book_id / "chats.json"
    return chats_file


def ensure_chats_dir_exists(book_id: str) -> None:
    """Ensures the directory for chats.json exists."""
    chats_file = get_chats_file_path(book_id)
    chats_file.parent.mkdir(parents=True, exist_ok=True)


def load_chat_sessions(book_id: str) -> List[ChatSession]:
    """Load chat sessions from chats.json file."""
    chats_file = get_chats_file_path(book_id)
    
    if not chats_file.exists():
        return []
    
    try:
        with open(chats_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sessions = []
        for session_data in data.get('sessions', []):
            session = ChatSession(
                id=session_data['id'],
                chapter_index=session_data['chapter_index'],
                created_at=session_data['created_at'],
                title=session_data['title'],
                messages=session_data.get('messages', [])
            )
            sessions.append(session)
        
        return sessions
    except Exception as e:
        print(f"Error loading chat sessions for {book_id}: {e}")
        return []


def save_chat_sessions(book_id: str, sessions: List[ChatSession]) -> None:
    """Save chat sessions to chats.json file."""
    ensure_chats_dir_exists(book_id)
    chats_file = get_chats_file_path(book_id)
    
    data = {
        'sessions': [asdict(session) for session in sessions]
    }
    
    try:
        with open(chats_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving chat sessions for {book_id}: {e}")
        raise


def create_new_session(book_id: str, chapter_index: int, title: Optional[str] = None) -> ChatSession:
    """Create a new empty chat session."""
    sessions = load_chat_sessions(book_id)
    
    new_session = ChatSession(
        id=str(uuid.uuid4()),
        chapter_index=chapter_index,
        created_at=datetime.now().isoformat(),
        title=title or f"Chat {datetime.now().strftime('%H:%M')}",
        messages=[]
    )
    
    sessions.append(new_session)
    save_chat_sessions(book_id, sessions)
    
    return new_session


def get_session_by_id(book_id: str, session_id: str) -> Optional[ChatSession]:
    """Get a specific session by ID."""
    sessions = load_chat_sessions(book_id)
    return next((s for s in sessions if s.id == session_id), None)


def add_message_to_session(book_id: str, session_id: str, role: str, content: str) -> None:
    """Add a message to a session and save."""
    sessions = load_chat_sessions(book_id)
    session = next((s for s in sessions if s.id == session_id), None)
    
    if not session:
        raise ValueError(f"Session {session_id} not found")
    
    session.messages.append({"role": role, "content": content})
    
    # Update title if it's still the default and we have messages
    if len(session.messages) <= 2 and role == "user":
        # Use first 30 characters of first user message as title
        first_user_msg = next((m["content"] for m in session.messages if m["role"] == "user"), "")
        if first_user_msg:
            session.title = first_user_msg[:30] + ("..." if len(first_user_msg) > 30 else "")
    
    save_chat_sessions(book_id, sessions)


def get_sessions_for_chapter(book_id: str, chapter_index: int) -> List[ChatSession]:
    """Get all sessions for a specific chapter."""
    sessions = load_chat_sessions(book_id)
    return [s for s in sessions if s.chapter_index == chapter_index]


def delete_session(book_id: str, session_id: str) -> None:
    """Delete a session."""
    sessions = load_chat_sessions(book_id)
    sessions = [s for s in sessions if s.id != session_id]
    save_chat_sessions(book_id, sessions)

