from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Highlight:
    """Represents a user highlight imported from an external source (e.g. Kobo)."""
    text: str
    annotation: str
    date: str
    chapter_id: str  # The ID in the source system (if available)

@dataclass
class ChapterContent:
    """
    Represents a physical file in the EPUB (Spine Item).
    """
    id: str           # Internal ID (e.g., 'item_1')
    href: str         # Filename (e.g., 'part01.html')
    title: str        # Best guess title from file
    content: str      # Cleaned HTML with rewritten image paths and injected highlights
    text: str         # Plain text for search/LLM context
    order: int        # Linear reading order
    highlights: List[Highlight] = field(default_factory=list)

@dataclass
class TOCEntry:
    """Represents a logical entry in the navigation tree."""
    title: str
    href: str         # original href (e.g., 'part01.html#chapter1')
    file_href: str    # just the filename (e.g., 'part01.html')
    anchor: str       # just the anchor (e.g., 'chapter1'), empty if none
    children: List['TOCEntry'] = field(default_factory=list)

@dataclass
class BookMetadata:
    """Standard book metadata."""
    title: str
    language: str
    authors: List[str] = field(default_factory=list)
    description: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    identifiers: List[str] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)

@dataclass
class Book:
    """The root object representing a processed book."""
    metadata: BookMetadata
    spine: List[ChapterContent]  # The actual content (linear files)
    toc: List[TOCEntry]          # The navigation tree
    images: Dict[str, str]       # Map: original_path -> local_path
    
    source_file: str
    processed_at: str
    version: str = "4.0"

