import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="RaceCoach — serwer szkoleniowy")
    parser.add_argument("--demo", action="store_true", help="Jawnie włącz syntetyczne stanowiska i dane demonstracyjne")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", default=None)
    args = parser.parse_args()
    import uvicorn
    from .app import create_app
    uvicorn.run(create_app(args.data, demo=args.demo), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
