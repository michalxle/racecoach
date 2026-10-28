# RaceCoach – delta do okrążenia referencyjnego (rekord osobisty / grupy / najlepsze w sesji).
# Liczona w każdej klatce: czas bieżącego okrążenia minus czas referencji w tym samym miejscu toru.
# Na okrążeniu wyjazdowym z boksu i w alei serwisowej delty nie ma (czas okrążenia liczy się wtedy
# od wyjazdu, a nie od linii mety, więc porównanie nie miałoby sensu).

import os
import sys

import ac
import acsys

sys.path.insert(0, os.path.join("apps", "python", "RaceCoach"))
import rc_common as st  # noqa: E402

APP = "RaceCoachDelta"
W, H = 230, 96
window = 0
title_label = 0
num_label = 0
ref_file = st.JsonFile("reference.json")
overlay = st.JsonFile("overlay.json")
layout = st.Layout("w-delta")
ref = None
delta = None
pit_lap = None
timer = 0.0


def acMain(ac_version):
    global window, title_label, num_label
    window = ac.newApp(APP)
    st.style_window(window, W, H)
    title_label = st.label(window, "DELTA", 14, 10, 11, st.GREY)
    num_label = st.label(window, "-", 0, 26, 40, st.GREY, w=W, align="center", bold=True)
    ac.addRenderCallback(window, on_render)
    return APP


def _acUpdate(deltaT):
    global timer, ref, delta, pit_lap
    timer += deltaT
    if timer >= 0.5:
        timer = 0.0
        if ref_file.poll():
            ref = st.load_reference(ref_file)
            ac.setText(title_label, st.plain("DELTA   vs " + ref.label) if ref and ref.label else "DELTA")
        if overlay.poll():
            layout.apply(window, overlay.data)

    lap_count = ac.getCarState(0, acsys.CS.LapCount)
    try:
        in_pit = bool(ac.isCarInPitline(0) or ac.isCarInPit(0))
    except Exception:
        in_pit = False
    if in_pit:
        pit_lap = lap_count          # okrążenie, które zaczęło się w boksie, to okrążenie wyjazdowe
    outlap = pit_lap is not None and lap_count <= pit_lap

    if ref is None or in_pit or outlap:
        delta = None
        ac.setText(num_label, "PIT" if in_pit else ("OUT" if outlap and ref else "-"))
        ac.setFontColor(num_label, *st.GREY)
        return
    s = ac.getCarState(0, acsys.CS.NormalizedSplinePosition)
    t = ac.getCarState(0, acsys.CS.LapTime)
    delta = st.delta_ms(ref, s, t)
    ac.setText(num_label, st.fmt_delta(delta))
    ac.setFontColor(num_label, *(st.GREEN if delta < 0 else st.RED))


def _on_render(deltaT):
    # pasek: środek = 0, pełna szerokość = ±1 s
    x0, y0, w, h = 14, H - 20, W - 28, 10
    ac.glColor4f(0.16, 0.18, 0.22, 1)
    ac.glQuad(x0, y0, w, h)
    if delta is not None:
        frac = min(abs(delta) / 1000.0, 1.0) * (w / 2.0)
        if delta < 0:
            ac.glColor4f(*st.GREEN)
            ac.glQuad(x0 + w / 2.0 - frac, y0, frac, h)
        else:
            ac.glColor4f(*st.RED)
            ac.glQuad(x0 + w / 2.0, y0, frac, h)
    ac.glColor4f(0.77, 0.79, 0.82, 1)
    ac.glQuad(x0 + w / 2.0 - 1, y0 - 2, 2, h + 4)


def acUpdate(deltaT):
    try:
        _acUpdate(deltaT)
    except Exception:
        st.log_error(APP, "acUpdate")


def on_render(deltaT):
    try:
        _on_render(deltaT)
    except Exception:
        st.log_error(APP, "rysowanie")
