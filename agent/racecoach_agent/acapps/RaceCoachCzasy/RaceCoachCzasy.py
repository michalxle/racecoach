# RaceCoach – czasy: bieżące okrążenie, ostatnie, najlepsze w sesji i rekord osobisty.

import os
import sys

import ac
import acsys

sys.path.insert(0, os.path.join("apps", "python", "RaceCoach"))
import rc_common as st  # noqa: E402

APP = "RaceCoachCzasy"
W, H = 250, 112
window = 0
lap_label = cur_label = 0
last_label = best_label = pb_label = 0
overlay = st.JsonFile("overlay.json")
layout = st.Layout("w-times")
pb_ms = None
timer = 0.0


def fmt_running(ms):
    ms = int(ms or 0)
    return "{}:{:02d}.{}".format(ms // 60000, (ms % 60000) // 1000, (ms % 1000) // 100)


def acMain(ac_version):
    global window, lap_label, cur_label, last_label, best_label, pb_label
    window = ac.newApp(APP)
    st.style_window(window, W, H)
    lap_label = st.label(window, "OKRAZENIE -", 14, 10, 11, st.GREY)
    cur_label = st.label(window, "0:00.0", 14, 24, 30, st.WHITE, bold=True)
    for i, title in enumerate(("Ostatnie", "Najlepsze", "Rekord os.")):
        st.label(window, title, 14 + i * 78, 66, 11, st.GREY)
    last_label = st.label(window, "-", 14, 82, 14)
    best_label = st.label(window, "-", 92, 82, 14, (0.78, 0.57, 1.0, 1.0))
    pb_label = st.label(window, "-", 170, 82, 14)
    return APP


def _acUpdate(deltaT):
    global timer, pb_ms
    timer += deltaT
    ac.setText(cur_label, fmt_running(ac.getCarState(0, acsys.CS.LapTime)))
    if timer < 0.5:
        return
    timer = 0.0
    if overlay.poll():
        d = overlay.data or {}
        layout.apply(window, d)
        pb_ms = d.get("pb_ms")
    ac.setText(lap_label, "OKRAZENIE {}".format(ac.getCarState(0, acsys.CS.LapCount) + 1))
    ac.setText(last_label, st.fmt_ms(ac.getCarState(0, acsys.CS.LastLap)))
    ac.setText(best_label, st.fmt_ms(ac.getCarState(0, acsys.CS.BestLap)))
    ac.setText(pb_label, st.fmt_ms(pb_ms))


def acUpdate(deltaT):
    try:
        _acUpdate(deltaT)
    except Exception:
        st.log_error(APP, "acUpdate")
