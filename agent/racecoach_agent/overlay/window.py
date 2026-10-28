"""Nakładki na pulpicie: przezroczyste okno nad grą z tą samą stroną co /overlay/N.

Tak działają nakładki SimHub czy RaceLab: osobne okno bez ramki, zawsze na wierzchu,
przezroczyste i „przepuszczające” mysz i klawiaturę do gry. Wyświetla stronę nakładek
z agenta RaceCoach w trybie gry (bez paska, bez tła), więc wygląd i położenie okienek
są dokładnie takie, jak ustawione w panelu.

Okno dopasowuje się do okna gry „Assetto Corsa” (obszar roboczy, bez paska tytułu);
gdy go nie ma – zajmuje główny ekran. Gra musi działać w oknie albo w trybie bez ramki
(pełny ekran wyłączny przykrywa każde okno).

Uruchamiane przez agenta jako osobny proces: python -m racecoach_agent.overlay.window <adres>.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

GAME_TITLE = "Assetto Corsa"


def _game_client_rect() -> tuple[int, int, int, int] | None:
    """Obszar roboczy okna gry w pikselach ekranu (x, y, w, h) albo None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, GAME_TITLE)
    if not hwnd or user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
        return None
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 200 or h < 150:
        return None
    return pt.x, pt.y, w, h


def _make_click_through(hwnd: int) -> None:
    """WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW – mysz trafia do gry."""
    if sys.platform != "win32":
        return
    import ctypes

    user32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= 0x00000020 | 0x00080000 | 0x08000000 | 0x00000080
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def run_overlay_window(url: str, follow_game: bool = True) -> int:
    from PySide6.QtCore import QRect, Qt, QTimer, QUrl
    from PySide6.QtGui import QColor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    view = QWebEngineView()
    view.setWindowTitle("RaceCoach – nakładki")
    view.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                        | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                        | Qt.WindowType.WindowDoesNotAcceptFocus)
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    view.setStyleSheet("background: transparent")
    view.page().setBackgroundColor(QColor(0, 0, 0, 0))
    view.setUrl(QUrl(url))

    screen = app.primaryScreen()

    def place() -> None:
        rect = _game_client_rect() if follow_game else None
        if rect is None:
            if follow_game and sys.platform == "win32":
                view.hide()          # gra zminimalizowana / jeszcze się nie uruchomiła
                return
            g = screen.geometry()
        else:
            ratio = screen.devicePixelRatio() or 1.0   # skalowanie Windows (np. 125%)
            x, y, w, h = rect
            g = QRect(round(x / ratio), round(y / ratio), round(w / ratio), round(h / ratio))
        if view.geometry() != g:
            view.setGeometry(g)
        if not view.isVisible():
            view.show()
            _make_click_through(int(view.winId()))
        view.raise_()

    timer = QTimer()
    timer.timeout.connect(place)
    timer.start(1000)
    place()
    log.info("Nakładki na pulpicie: %s", url)
    return app.exec()


def available():
    """Czy na stanowisku jest PySide6 z QtWebEngine (pip install "./agent[overlay]")."""
    import importlib.util
    try:
        return importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None
    except (ImportError, ValueError):
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Okno nakładek RaceCoach nad grą")
    parser.add_argument("url")
    parser.add_argument("--na-pulpicie", action="store_true", help="cały ekran zamiast okna gry (test bez gry)")
    args = parser.parse_args()
    sys.exit(run_overlay_window(args.url, follow_game=not args.na_pulpicie))
