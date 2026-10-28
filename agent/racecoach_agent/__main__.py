import argparse
import logging
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit

from .hardware import Hardware
from .launcher import Launcher
from .runtime import Agent
from .storage import AgentStore


def main():
    parser = argparse.ArgumentParser(description="Agent stanowiska RaceCoach — oryginalne Assetto Corsa")
    parser.add_argument("--server", required=True)
    parser.add_argument("--game-dir", required=True)
    parser.add_argument("--documents", default=str(Path.home() / "Documents/Assetto Corsa"))
    parser.add_argument("--data", default=str(Path(os.getenv("LOCALAPPDATA", Path.home())) / "RaceCoachAgent"))
    parser.add_argument("--hardware", choices=["off", "openffboard", "ffbeast"], default="off")
    parser.add_argument("--ddcontrol")
    parser.add_argument("--max-strength", type=int, default=25)
    parser.add_argument("--restore-config", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.max_strength <= 100:
        parser.error("--max-strength musi należeć do zakresu 0–100")
    parsed = urlsplit(args.server)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        parser.error("Podaj adres http(s) centrali bez danych logowania")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", 31398))
    except OSError:
        parser.error("Inny agent RaceCoach już działa na tym komputerze")
    launcher = Launcher(args.game_dir, args.documents, args.data)
    if args.restore_config:
        launcher.restore()
        return
    token = os.getenv("RACECOACH_AGENT_TOKEN")
    if not token:
        parser.error("Ustaw RACECOACH_AGENT_TOKEN tokenem uzyskanym przy rejestracji stanowiska")
    hardware = Hardware(args.hardware, args.ddcontrol, args.max_strength)
    store = AgentStore(Path(args.data) / "agent.sqlite3")
    agent = Agent(args.server, token, store, launcher, hardware)
    try:
        agent.run()
    except KeyboardInterrupt:
        pass
    finally:
        agent.close()
        store.close()
        lock.close()


if __name__ == "__main__":
    main()
