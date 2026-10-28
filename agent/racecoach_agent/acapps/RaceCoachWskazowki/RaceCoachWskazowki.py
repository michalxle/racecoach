# RaceCoach – wskazówki po okrążeniu: gdzie tracisz najwięcej czasu i dlaczego.

import os
import sys

import ac

sys.path.insert(0, os.path.join("apps", "python", "RaceCoach"))
import rc_common as st  # noqa: E402

APP = "RaceCoachWskazowki"
W, H = 340, 190
MAX_LINES = 8

window = 0
title_label = 0
lines = []
overlay = st.JsonFile("overlay.json")
layout = st.Layout("w-tips")
timer = 0.0


def acMain(ac_version):
    global window, title_label
    window = ac.newApp(APP)
    st.style_window(window, W, H)
    title_label = st.label(window, "WSKAZOWKI", 14, 10, 11, st.GREY)
    for i in range(MAX_LINES):
        lines.append(st.label(window, "", 14, 30 + i * 19, 14))
    ac.setText(lines[0], "Pojawia sie po okrazeniu.")
    ac.setFontColor(lines[0], *st.GREY)
    return APP


def _acUpdate(deltaT):
    global timer
    timer += deltaT
    if timer < 0.5:
        return
    timer = 0.0
    if not overlay.poll():
        return
    layout.apply(window, overlay.data)
    tips = (overlay.data or {}).get("tips")
    if not tips:
        return
    ac.setText(title_label, "WSKAZOWKI   PO OKRAZENIU {}".format(tips.get("lap_no", "")))
    out = []
    for text in st.wrap(st.plain(tips.get("summary", "")), 42):
        out.append((text, st.GREY))
    for tip in tips.get("lines", []):
        text = st.plain(tip.get("text", ""))
        prefix = "[{}] ".format(tip.get("corner", "")) if tip.get("corner") else "- "
        text = text.split(", ", 1)[1] if text.startswith("Zakret ") and ", " in text else text
        for j, part in enumerate(st.wrap(text, 38)):
            out.append(((prefix if j == 0 else "     ") + part, st.ACCENT if j == 0 else st.WHITE))
    for i, lab in enumerate(lines):
        if i < len(out):
            ac.setText(lab, out[i][0])
            ac.setFontColor(lab, *out[i][1])
        else:
            ac.setText(lab, "")


def acUpdate(deltaT):
    try:
        _acUpdate(deltaT)
    except Exception:
        st.log_error(APP, "acUpdate")
