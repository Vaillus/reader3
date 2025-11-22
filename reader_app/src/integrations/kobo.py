import sqlite3
import os
from pathlib import Path
from typing import List, Optional

from src.core.models import Highlight

def get_kobo_db_path() -> Optional[Path]:
    """Returns the path to the Kobo database on macOS."""
    base = Path(os.path.expanduser("~/Library/Application Support/Kobo/Kobo Desktop Edition"))
    for name in ["Kobo.sqlite", "Book.sqlite", "KoboReader.sqlite"]:
        p = base / name
        if p.exists():
            return p
    return None

def fetch_highlights(book_title: str) -> List[Highlight]:
    """
    Fetches highlights from Kobo DB matching the book title.
    """
    db_path = get_kobo_db_path()
    if not db_path:
        print("Warning: Kobo database not found.")
        return []

    print(f"Connecting to Kobo DB at {db_path}...")
    results = []
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Find the VolumeID (Book)
        # Try exact match first
        cursor.execute("""
            SELECT ContentID, Title 
            FROM content 
            WHERE Title = ? AND ContentType = 6 
            LIMIT 1
        """, (book_title,))
        book_row = cursor.fetchone()
        
        # Fallback: partial match
        if not book_row:
            cursor.execute("""
                SELECT ContentID, Title 
                FROM content 
                WHERE Title LIKE ? AND ContentType = 6 
                LIMIT 1
            """, (f"%{book_title}%",))
            book_row = cursor.fetchone()
            
        if not book_row:
            print(f"No book found in Kobo DB matching '{book_title}'")
            conn.close()
            return []
            
        full_id = book_row[0]
        volume_id = full_id.split('!')[0] # Kobo IDs often look like "UUID!..."
        print(f"Found Kobo Book ID: {volume_id} ({book_row[1]})")
        
        # 2. Fetch Highlights for this VolumeID
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
            
        conn.close()
        
    except sqlite3.Error as e:
        print(f"SQLite Error: {e}")
        
    return results

