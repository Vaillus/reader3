import re
from pathlib import Path
from typing import List, Optional
from src.utils.paths import get_obsidian_books_dir, ensure_dir_exists

def sanitize_filename(name: str) -> str:
    """Sanitizes a string to be safe for filenames."""
    # Remove invalid characters for files
    safe_name = re.sub(r'[<>:"/\\|?*]', '', name)
    return safe_name.strip()

def get_book_note_dir(book_title: str) -> Path:
    """Returns the directory for a specific book in the vault."""
    safe_title = sanitize_filename(book_title)
    path = get_obsidian_books_dir() / safe_title
    ensure_dir_exists(path)
    return path

def get_chapter_filename(chapter_title: str) -> str:
    """Generates a consistent filename for a chapter note based on the chapter title."""
    safe_title = sanitize_filename(chapter_title)
    return f"{safe_title}.md"

def get_main_note_path(book_title: str) -> Path:
    """Returns the path to the main note for a book."""
    book_dir = get_book_note_dir(book_title)
    safe_book_title = sanitize_filename(book_title)
    return book_dir / f"{safe_book_title}.md"

def ensure_main_note_exists(book_title: str) -> None:
    """Ensures the main note exists with basic structure, but without chapter links."""
    main_note_path = get_main_note_path(book_title)
    
    # Only create if doesn't exist
    if not main_note_path.exists():
        content = f"# {book_title}\n\n## Chapitres\n\n"
        with open(main_note_path, "w", encoding="utf-8") as f:
            f.write(content)

def add_chapter_link_to_main_note(book_title: str, chapter_title: str) -> None:
    """Adds a chapter link to the main note if it doesn't already exist."""
    main_note_path = get_main_note_path(book_title)
    
    # Ensure main note exists first
    ensure_main_note_exists(book_title)
    
    # Read current content
    with open(main_note_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if link already exists
    filename = get_chapter_filename(chapter_title)
    note_name = filename.replace('.md', '')
    link_line = f"- [[{note_name}|{chapter_title}]]"
    
    if link_line not in content:
        # Add the link after the "## Chapitres" section
        if "## Chapitres" in content:
            parts = content.split("## Chapitres\n", 1)
            content = parts[0] + "## Chapitres\n" + parts[1].rstrip() + f"\n{link_line}\n"
        else:
            # Fallback: append at the end
            content += f"\n{link_line}\n"
        
        # Save updated content
        with open(main_note_path, "w", encoding="utf-8") as f:
            f.write(content)

def get_chapter_note_content(book_title: str, chapter_title: str) -> str:
    """Gets the content of a chapter note, returns empty string if doesn't exist."""
    book_dir = get_book_note_dir(book_title)
    filename = get_chapter_filename(chapter_title)
    path = book_dir / filename
    
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def save_chapter_note_content(book_title: str, chapter_title: str, content: str) -> None:
    """Saves the content of a chapter note and adds link to main note."""
    book_dir = get_book_note_dir(book_title)
    filename = get_chapter_filename(chapter_title)
    path = book_dir / filename
    
    # Check if this is a new note
    is_new = not path.exists()
    
    # Save the note
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    
    # If new note, add link to main note
    if is_new:
        add_chapter_link_to_main_note(book_title, chapter_title)

