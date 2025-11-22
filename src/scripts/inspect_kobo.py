
import sqlite3
import sys
import os
from pathlib import Path

# Add project root to sys.path to allow imports from src
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utilities.paths import get_kobo_db_path

def inspect_highlights(book_title_part: str):
    db_names = ["Kobo.sqlite", "Book.sqlite", "KoboReader.sqlite"]
    base_dir = Path(os.path.expanduser("~/Library/Application Support/Kobo/Kobo Desktop Edition"))
    
    for db_name in db_names:
        db_path = base_dir / db_name
        if not db_path.exists():
            continue
            
        print(f"\n{'='*50}")
        print(f"Testing database: {db_name}")
        print(f"{'='*50}")
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # List tables to see what we're dealing with
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [t[0] for t in cursor.fetchall()]
            print(f"Tables found: {len(tables)}")
            if 'Bookmark' in tables:
                print("✅ Table 'Bookmark' found!")
            else:
                print("❌ Table 'Bookmark' NOT found.")
                
            if 'content' in tables:
                print("✅ Table 'content' found!")
                
                # 1. Find the root book ID (ContentType = 6 usually represents the full book)
                print(f"Searching for book ID containing '{book_title_part}'...")
                
                # We search for the base book ID first
                cursor.execute("""
                    SELECT ContentID, Title 
                    FROM content 
                    WHERE Title LIKE ? AND ContentType = 6 
                    LIMIT 1
                """, (f"%{book_title_part}%",))
                
                book = cursor.fetchone()
                
                if not book:
                    print("⚠️ Root book entry not found via Title. Trying broader search...")
                    # Fallback: Search any content to find the ID prefix
                    cursor.execute("SELECT ContentID, Title FROM content WHERE Title LIKE ? LIMIT 1", (f"%{book_title_part}%",))
                    book = cursor.fetchone()
                
                if book:
                    full_id = book[0]
                    # The VolumeID is usually the UUID part before the first '!' if it exists, or the whole ID
                    volume_id = full_id.split('!')[0] 
                    print(f"Found Book: {book[1]}")
                    print(f"Root VolumeID: {volume_id}")
                    
                    # 2. Extract ALL bookmarks for this VolumeID
                    if 'Bookmark' in tables:
                        print(f"\nExtracting ALL highlights for VolumeID: {volume_id}...")
                        query_highlights = """
                            SELECT Text, Annotation, ContentID, DateCreated
                            FROM Bookmark 
                            WHERE VolumeID = ? 
                            AND Type = 'highlight'
                            ORDER BY DateCreated
                        """
                        cursor.execute(query_highlights, (volume_id,))
                        highlights = cursor.fetchall()
                        
                        if not highlights:
                            print("❌ No highlights found for this VolumeID.")
                        else:
                            print(f"✅ Found {len(highlights)} highlights:\n")
                            for i, h in enumerate(highlights):
                                text = h[0]
                                note = h[1]
                                content_id = h[2] # Which chapter/file it belongs to
                                date = h[3]
                                
                                print(f"[{i+1}] {date}")
                                print(f"Chapter ID: {content_id}")
                                print(f"Quote: \"{text}\"")
                                if note:
                                    print(f"Note: {note}")
                                print("-" * 40)
                else:
                    print("No matching books found in this DB.")

            else:
                print("❌ Table 'content' NOT found.")

            conn.close()
            
        except sqlite3.Error as e:
            print(f"Error reading {db_name}: {e}")


if __name__ == "__main__":
    # Default to "Scaling" if no argument provided
    search_term = sys.argv[1] if len(sys.argv) > 1 else "Scaling"
    inspect_highlights(search_term)

