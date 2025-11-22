import sys
import os
import argparse
from pathlib import Path

# Add the current directory to sys.path to allow imports from src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.parser import parse_epub
from src.web.app import start_server

def main():
    parser = argparse.ArgumentParser(description="Reader 3 - Ebook Reader & Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Command: Add
    add_parser = subparsers.add_parser("add", help="Add a local EPUB file to the library")
    add_parser.add_argument("file", help="Path to the .epub file")
    add_parser.add_argument("--no-highlights", action="store_true", help="Skip fetching Kobo highlights")

    # Command: Serve
    serve_parser = subparsers.add_parser("serve", help="Start the web reader interface")

    args = parser.parse_args()

    if args.command == "add":
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File {file_path} not found.")
            sys.exit(1)
            
        print(f"Adding book: {file_path.name}")
        
        # Define output directory in data/library/Title_Data
        # We do a first quick read or just use filename stem
        safe_name = file_path.stem.replace(" ", "_")
        # We'll let the parser handle the full metadata, but we need a target dir
        # Actually, let's pass a temporary output dir or decide logic
        # For now: simplified, we use filename as ID
        
        library_dir = Path("data/library")
        output_dir = library_dir / f"{safe_name}_data"
        
        try:
            book = parse_epub(str(file_path), str(output_dir), fetch_kobo_highlights=not args.no_highlights)
            print(f"✅ Successfully added: {book.metadata.title}")
            print(f"   Highlights: {sum(len(c.highlights) for c in book.spine)}")
            print(f"   Location: {output_dir}")
        except Exception as e:
            print(f"❌ Error adding book: {e}")
            import traceback
            traceback.print_exc()

    elif args.command == "serve":
        print("Starting Reader Server...")
        start_server()
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

