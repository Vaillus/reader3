import os
import logging
import tempfile
from typing import List, Dict, Optional
from pathlib import Path
from src.integrations.kobo_api.Kobo import Kobo
from src.integrations.kobo_api.Settings import Settings
from src.integrations.kobo_api.Globals import Globals

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KoboService:
    def __init__(self):
        Globals.Settings = Settings()
        Globals.Logger = logger
        if not Globals.Settings.Load():
            logger.warning("Could not load Kobo settings.")
        self.kobo = Kobo()
        Globals.Kobo = self.kobo
        if self.is_authenticated():
            try:
                self.kobo.LoadInitializationSettings()
            except Exception:
                pass

    def is_authenticated(self) -> bool:
        return Globals.Settings.IsLoggedIn()

    def list_books(self, unread_only: bool = False) -> List[Dict]:
        if not self.is_authenticated():
            logger.warning("Not authenticated to Kobo")
            return []
        try:
            raw_books = self.kobo.GetMyBookList()
            
            cleaned_books = []
            for book in raw_books:
                try:
                    # Extract nested data structure
                    entitlement = book.get('NewEntitlement', {})
                    book_metadata = entitlement.get('BookMetadata', {})
                    book_entitlement = entitlement.get('BookEntitlement', {})
                    reading_state = entitlement.get('ReadingState', {})
                    status_info = reading_state.get('StatusInfo', {})
                    
                    # Get basic info
                    book_id = book_entitlement.get('RevisionId') or book_entitlement.get('Id')
                    title = book_metadata.get('Title')
                    
                    # Get authors (Contributors is now a list of strings)
                    contributors = book_metadata.get('Contributors', [])
                    if isinstance(contributors, list):
                        author_str = ", ".join(contributors) if contributors else "Unknown"
                    else:
                        author_str = "Unknown"
                    
                    # Get cover image
                    cover_url = book_metadata.get('CoverImageUrl')
                    if cover_url and not cover_url.startswith('http'):
                        cover_url = 'https:' + cover_url
                    
                    # Get reading status
                    status = status_info.get('Status', 'Unread')
                    is_read = status == 'Finished'
                    
                    if unread_only and is_read:
                        continue
                    
                    # Get download format
                    download_urls = book_metadata.get('DownloadUrls', [])
                    format_str = None
                    for url_info in download_urls:
                        if url_info.get('DrmType') == 'KDRM':
                            format_str = url_info.get('Format', 'EPUB')
                            break
                    if not format_str and download_urls:
                        format_str = download_urls[0].get('Format', 'EPUB')
                    
                    cleaned_books.append({
                        "id": book_id,
                        "title": title,
                        "author": author_str,
                        "is_read": is_read,
                        "cover_image": cover_url,
                        "format": format_str
                    })
                except Exception as e:
                    logger.warning(f"Error parsing book: {e}")
                    continue
            
            logger.info(f"Successfully parsed {len(cleaned_books)} books")
            return cleaned_books
        except Exception as e:
            logger.error(f"Error fetching Kobo books: {e}", exc_info=True)
            return []

    def download_book(self, book_id: str, output_dir: str) -> Optional[Path]:
        if not self.is_authenticated():
            raise RuntimeError("Not authenticated")
        try:
            os.makedirs(output_dir, exist_ok=True)
            display_profile = Kobo.DisplayProfile
            temp_path = os.path.join(output_dir, f"{book_id}.epub")
            self.kobo.Download(book_id, display_profile, temp_path)
            if os.path.exists(temp_path):
                return Path(temp_path)
            return None
        except Exception as e:
            logger.error(f"Error downloading book {book_id}: {e}")
            return None
