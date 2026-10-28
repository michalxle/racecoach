# RaceCoach – minimapa: najbliższy fragment toru (120 m za autem, 380 m przed nim), obrócony
# w kierunku jazdy, z numerami zakrętów takimi jak we wskazówkach.
#
# Kształt toru pochodzi z gry: linia AI (content/tracks/<tor>/[<wariant>/]ai/fast_lane.ai).
# Jeśli tor jej nie ma, pokazujemy oficjalną mapę z gry (map.png + data/map.ini) w całości –
# API aplikacji AC nie pozwala obracać ani przycinać obrazka.

import math
import os
import sys

import ac
import acsys

sys.path.insert(0, os.path.join("apps", "python", "RaceCoach"))
import rc_common as st  # noqa: E402

APP = "RaceCoachMapa"
SIZE = 256
PAD = 8
BACK_M, AHEAD_M = 120.0, 380.0
ROAD_M = 12.0

window = 0
info_label = 0
corner_labels = []
ref_file = st.JsonFile("reference.json")
overlay = st.JsonFile("overlay.json")
layout = st.Layout("w-map")
ref = None
lane = None          # punkty (x, z) linii AI
near = 0             # indeks punktu linii AI najbliżej auta
texture = None
params = None
fit = 1.0
off_x = off_y = 0.0
timer = 0.0


def acMain(ac_version):
    global window, info_label, lane
    window = ac.newApp(APP)
    st.style_window(window, SIZE, SIZE)
    info_label = st.label(window, "", 0, SIZE / 2 - 10, 13, st.GREY, w=SIZE, align="center")
    for i in range(12):
        lab = st.label(window, "", 0, 0, 12, (0.08, 0.07, 0.04, 1), w=20, align="center", bold=True)
        corner_labels.append(lab)
    try:
        track = ac.getTrackName(0)
        cfg = ac.getTrackConfiguration(0) or ""
    except Exception:
        track, cfg = "", ""
    lane = st.read_fast_lane(track, cfg)
    if lane is None:
        load_texture(track, cfg)
    ac.addRenderCallback(window, on_render)
    return APP


def load_texture(track, cfg):
    global texture, params, fit, off_x, off_y
    png, ini = st.track_map_paths(track, cfg)
    params = st.read_map_ini(ini)
    if params is None or not os.path.isfile(png):
        ac.setText(info_label, "Brak mapy toru w grze")
        return
    texture = ac.newTexture(png)
    w = params.get("WIDTH") or 1.0
    h = params.get("HEIGHT") or 1.0
    fit = min((SIZE - 2 * PAD) / w, (SIZE - 2 * PAD) / h)
    off_x = (SIZE - w * fit) / 2.0
    off_y = (SIZE - h * fit) / 2.0


def _acUpdate(deltaT):
    global timer, ref
    timer += deltaT
    if timer >= 1.0:
        timer = 0.0
        if ref_file.poll():
            ref = st.load_reference(ref_file)
        if overlay.poll():
            layout.apply(window, overlay.data)


def find_near(x, z):
    """Najbliższy punkt linii AI – szukamy w pobliżu poprzedniego (szybko), a gdy daleko – wszędzie."""
    global near
    n = len(lane)

    def d2(i):
        p = lane[i % n]
        return (p[0] - x) ** 2 + (p[1] - z) ** 2

    best = min(range(near - 40, near + 41), key=d2) % n
    if d2(best) > 40 * 40:
        best = min(range(n), key=d2)
    near = best
    return best


def on_render(deltaT):
    try:
        for lab in corner_labels:
            ac.setText(lab, "")
        pos = ac.getCarState(0, acsys.CS.WorldPosition)
        cx, cz = pos[0], pos[2]
        if lane is not None:
            draw_local(cx, cz)
        elif texture is not None:
            draw_full(cx, cz)
    except Exception:
        st.log_error(APP, "rysowanie")


def draw_local(cx, cz):
    n = len(lane)
    i0 = find_near(cx, cz)
    ax, az = lane[(i0 + 3) % n]
    bx, bz = lane[(i0 - 3) % n]
    rot = -math.pi / 2 - math.atan2(az - bz, ax - bx)      # kierunek jazdy = w górę
    cs, sn = math.cos(rot), math.sin(rot)
    scale = (SIZE * 0.68) / AHEAD_M
    ox, oy = SIZE / 2.0, SIZE * 0.74

    def tx(x, z):
        dx, dz = x - cx, z - cz
        return ox + (dx * cs - dz * sn) * scale, oy + (dx * sn + dz * cs) * scale

    seg = max(1.0, ((lane[1][0] - lane[0][0]) ** 2 + (lane[1][1] - lane[0][1]) ** 2) ** 0.5)
    k_from, k_to = -int(BACK_M / seg), int(AHEAD_M / seg)
    # tor jako gęsty ciąg małych kwadratów (ac.glQuad) – bez glBegin/glVertex, które bywają niestabilne
    dot = max(5.0, ROAD_M * scale)
    ac.glColor4f(0.42, 0.45, 0.50, 1)
    prev = None
    for k in range(k_from, k_to + 1):
        px, py = tx(*lane[(i0 + k) % n])
        if prev is not None:
            # dopełnienie, gdy punkty są rzadziej niż pół szerokości drogi
            steps = int(math.hypot(px - prev[0], py - prev[1]) / (dot / 2.0))
            for j in range(1, min(steps, 20) + 1):
                f = j / float(steps + 1)
                qx, qy = prev[0] + (px - prev[0]) * f, prev[1] + (py - prev[1]) * f
                if dot / 2 <= qx <= SIZE - dot / 2 and dot / 2 <= qy <= SIZE - dot / 2:
                    ac.glQuad(qx - dot / 2, qy - dot / 2, dot, dot)
        if dot / 2 <= px <= SIZE - dot / 2 and dot / 2 <= py <= SIZE - dot / 2:
            ac.glQuad(px - dot / 2, py - dot / 2, dot, dot)
        prev = (px, py)

    # numery zakrętów (pozycja na torze z wskazówek → punkt linii AI)
    if ref is not None:
        used = 0
        for c in ref.corners:
            k = int(round(c["s"] * n)) - i0
            if k < -n / 2:
                k += n
            if k > n / 2:
                k -= n
            if k < k_from + 3 or k > k_to - 3 or used >= len(corner_labels):
                continue
            px, py = tx(*lane[(i0 + k) % n])
            if 12 <= px <= SIZE - 12 and 12 <= py <= SIZE - 12:
                ac.glColor4f(*st.ACCENT)
                ac.glQuad(px - 10, py - 10, 20, 20)
                lab = corner_labels[used]
                ac.setPosition(lab, px - 10, py - 9)
                ac.setText(lab, str(c["n"]))
                used += 1

    # auto: zielony znacznik (strzałka z prostokątów – kierunek jazdy zawsze w górę)
    ac.glColor4f(*st.GREEN)
    ac.glQuad(ox - 6, oy - 2, 12, 10)
    ac.glQuad(ox - 3, oy - 9, 6, 7)


def draw_full(cx, cz):
    sf = params["SCALE_FACTOR"]
    ac.glColor4f(1, 1, 1, 0.9)
    ac.glQuadTextured(off_x, off_y, params.get("WIDTH", 1.0) * fit, params.get("HEIGHT", 1.0) * fit, texture)
    x = off_x + (cx + params.get("X_OFFSET", 0.0)) / sf * fit
    y = off_y + (cz + params.get("Z_OFFSET", 0.0)) / sf * fit
    ac.glColor4f(*st.GREEN)
    ac.glQuad(x - 5, y - 5, 10, 10)


def acUpdate(deltaT):
    try:
        _acUpdate(deltaT)
    except Exception:
        st.log_error(APP, "acUpdate")
