# RaceCoach – okno „Instruktor”: cel sesji i wiadomości od instruktora.
#
# Wszystkie nakładki RaceCoach to osobne aplikacje, więc każdą można
# włączyć/wyłączyć i przesunąć niezależnie – w grze (pasek aplikacji po prawej
# stronie ekranu, okno przeciąga się myszą) albo w panelu RaceCoach
# (/overlay/N), który przenosi układ do gry:
#   RaceCoach          – instruktor (to okno)
#   RaceCoachDelta     – delta do okrążenia referencyjnego
#   RaceCoachCzasy     – bieżące, ostatnie, najlepsze okrążenie i rekord
#   RaceCoachMapa      – minimapa z najbliższym fragmentem toru
#   RaceCoachWskazowki – wskazówki po okrążeniu

import os
import sys

import ac

sys.path.insert(0, os.path.join("apps", "python", "RaceCoach"))
import rc_common as st  # noqa: E402

APP = "RaceCoach"
W, H = 320, 110
window = 0
goal_label = 0
msg_labels = []
overlay = st.JsonFile("overlay.json")
layout = st.Layout("w-msg")
timer = 0.0


def acMain(ac_version):
    global window, goal_label
    window = ac.newApp(APP)
    st.style_window(window, W, H)
    st.label(window, "INSTRUKTOR", 14, 10, 11, st.ACCENT)
    goal_label = st.label(window, "", 14, 28, 13, st.GREY)
    for i in range(3):
        msg_labels.append(st.label(window, "", 14, 48 + i * 20, 16))
    ac.setText(msg_labels[0], "Brak wiadomosci.")
    ac.setFontColor(msg_labels[0], *st.GREY)
    return APP


def _acUpdate(deltaT):
    global timer
    timer += deltaT
    if timer < 0.5:
        return
    timer = 0.0
    if not overlay.poll():
        return
    d = overlay.data or {}
    layout.apply(window, d)
    goal = d.get("goal") or ""
    ac.setText(goal_label, st.plain("Cel: " + goal) if goal else "")
    msg = (d.get("message") or {}).get("text") or ""
    lines = st.wrap(st.plain(msg), 34)[:3] if msg else ["Brak wiadomosci."]
    for i, lab in enumerate(msg_labels):
        ac.setText(lab, lines[i] if i < len(lines) else "")
        ac.setFontColor(lab, *(st.WHITE if msg else st.GREY))


def acUpdate(deltaT):
    try:
        _acUpdate(deltaT)
    except Exception:
        st.log_error(APP, "acUpdate")
