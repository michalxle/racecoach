"""Consistent SQLite backup, including data still present in WAL."""
import argparse
import os
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Kopia danych RaceCoach podczas działania serwera")
    parser.add_argument("--data", required=True, help="Folder zawierający racecoach.sqlite3")
    parser.add_argument("--output", required=True, help="Nowy plik kopii (nie nadpisuje istniejącego)")
    args = parser.parse_args()
    source_path = Path(args.data).resolve() / "racecoach.sqlite3"
    output_path = Path(args.output).resolve()
    if not source_path.is_file():
        parser.error("Nie znaleziono bazy danych")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(output_path) as target:
            source.backup(target)
    print("Kopia zapisana:", output_path)


if __name__ == "__main__":
    main()
