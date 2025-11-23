import sys
import os
import argparse
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.parser import parse_epub
# from src.web.app import start_server
import uvicorn
from server import app

def start_server():
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)

def main():
    parser = argparse.ArgumentParser(description="Reader 3")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add", help="Add EPUB")
    add_parser.add_argument("file")
    add_parser.add_argument("--no-highlights", action="store_true")

    subparsers.add_parser("serve", help="Start Server")

    args = parser.parse_args()

    if args.command == "add":
        file_path = Path(args.file)
        safe_name = file_path.stem.replace(" ", "_")
        output_dir = Path("data/library") / f"{safe_name}_data"
        try:
            book = parse_epub(str(file_path), str(output_dir), fetch_kobo_highlights=not args.no_highlights)
            print(f"Added: {book.metadata.title}")
        except Exception as e:
            print(f"Error: {e}")

    elif args.command == "serve":
        start_server()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
