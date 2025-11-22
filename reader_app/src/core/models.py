from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Highlight:
    text: str
    annotation: str
    date: str
    chapter_id: str

@dataclass
class ChapterContent:
    id: str
    href: str
    title: str
    content: str
    text: str
    order: int
    highlights: List[Highlight] = field(default_factory=list)

@dataclass
class TOCEntry:
    title: str
    href: str
    file_href: str
    anchor: str
    children: List['TOCEntry'] = field(default_factory=list)

@dataclass
class BookMetadata:
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
    metadata: BookMetadata
    spine: List[ChapterContent]
    toc: List[TOCEntry]
    images: Dict[str, str]
    source_file: str
    processed_at: str
    version: str = "4.0"
