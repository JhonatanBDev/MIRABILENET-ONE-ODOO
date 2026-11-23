"""Dibuja las ilustraciones del sitio web (SVG, hechas por nosotros: sin derechos de terceros).
Se pueden reemplazar por fotos propias desde «Editar» en el sitio.

Uso:
  env\\Scripts\\python.exe documentacion\\herramientas\\generar_ilustraciones_sitio.py <carpeta de salida> [otra carpeta]
"""
import math
import os
import random
import sys

W, H = 1200, 560
BLUE, SKY, NIGHT, LIGHT = "#006db7", "#00abda", "#0b1220", "#f5f5f7"


def svg(body, defs="", w=W, h=H):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
            'role="img"><defs>%s</defs>%s</svg>\n' % (w, h, w, h, defs, body))


def grad(gid, stops, x1=0, y1=0, x2=1, y2=1):
    return '<linearGradient id="%s" x1="%s" y1="%s" x2="%s" y2="%s">%s</linearGradient>' % (
        gid, x1, y1, x2, y2,
        "".join('<stop offset="%s" stop-color="%s" stop-opacity="%s"/>' % s for s in stops))


def radial(gid, stops, cx="50%", cy="50%", r="50%"):
    return '<radialGradient id="%s" cx="%s" cy="%s" r="%s">%s</radialGradient>' % (
        gid, cx, cy, r,
        "".join('<stop offset="%s" stop-color="%s" stop-opacity="%s"/>' % s for s in stops))


def fibra():
    """Haz de fibras de luz que sale de un punto y se abre."""
    rnd = random.Random(7)
    defs = (grad("f1", [(0, BLUE, 0), (0.25, BLUE, 1), (0.8, SKY, 1), (1, "#7fe3ff", 0)], 0, 0, 1, 0)
            + grad("f2", [(0, "#5b5bd6", 0), (0.3, "#5b5bd6", .9), (0.85, SKY, .9), (1, SKY, 0)], 0, 0, 1, 0)
            + radial("glow", [(0, "#7fe3ff", .55), (1, "#7fe3ff", 0)]))
    paths = []
    for i in range(46):
        t = i / 45.0
        y_end = 40 + t * 480 + rnd.uniform(-12, 12)
        bend = rnd.uniform(-70, 70)
        width = rnd.choice([1.2, 1.6, 2.2, 3.0])
        paths.append('<path d="M -20 %.0f C 320 %.0f, 620 %.0f, 1220 %.0f" fill="none" stroke="url(#%s)" '
                     'stroke-width="%.1f" stroke-linecap="round" opacity="%.2f"/>' % (
                         280 + (t - .5) * 34, 280 + bend * .25, y_end * .55 + 125 + bend, y_end,
                         "f1" if i % 3 else "f2", width, rnd.uniform(.45, .95)))
    dots = "".join('<circle cx="%.0f" cy="%.0f" r="%.1f" fill="#fff" opacity="%.2f"/>' % (
        rnd.uniform(700, 1180), rnd.uniform(40, 520), rnd.uniform(1.5, 4), rnd.uniform(.5, 1))
        for _ in range(26))
    return svg('<ellipse cx="930" cy="280" rx="420" ry="250" fill="url(#glow)"/>' + "".join(paths) + dots,
               defs)


def camara():
    """Lente de cámara, de frente, sobre fondo oscuro."""
    defs = (radial("l1", [(0, "#1c2a44", 1), (0.7, "#0e1626", 1), (1, "#05080f", 1)])
            + radial("l2", [(0, "#0a84ff", .95), (0.45, "#0b3a7a", 1), (1, "#04060c", 1)], "42%", "38%", "60%")
            + radial("halo", [(0, "#2997ff", .45), (1, "#2997ff", 0)])
            + grad("ring", [(0, "#8e9bb3", 1), (0.5, "#2b3445", 1), (1, "#aab6cc", 1)]))
    cx, cy = 600, 330
    rings = "".join('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="#fff" stroke-opacity="%.2f" '
                    'stroke-width="1"/>' % (cx, cy, r, o) for r, o in ((150, .10), (118, .14), (86, .18)))
    ticks = "".join('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#fff" stroke-opacity=".28" '
                    'stroke-width="2"/>' % (cx + 196 * math.cos(a), cy + 196 * math.sin(a),
                                            cx + 208 * math.cos(a), cy + 208 * math.sin(a))
                    for a in (math.radians(d) for d in range(0, 360, 12)))
    body = ('<ellipse cx="%d" cy="%d" rx="520" ry="300" fill="url(#halo)"/>' % (cx, cy)
            + '<circle cx="%d" cy="%d" r="232" fill="url(#ring)"/>' % (cx, cy)
            + '<circle cx="%d" cy="%d" r="220" fill="url(#l1)"/>' % (cx, cy) + ticks
            + '<circle cx="%d" cy="%d" r="176" fill="#05080f"/>' % (cx, cy)
            + '<circle cx="%d" cy="%d" r="164" fill="url(#l2)"/>' % (cx, cy) + rings
            + '<circle cx="%d" cy="%d" r="46" fill="#02040a"/>' % (cx, cy)
            + '<ellipse cx="%d" cy="%d" rx="52" ry="26" fill="#fff" opacity=".22" '
              'transform="rotate(-32 %d %d)"/>' % (cx - 62, cy - 78, cx - 62, cy - 78)
            + '<circle cx="%d" cy="%d" r="9" fill="#fff" opacity=".5"/>' % (cx + 40, cy + 52)
            + '<circle cx="%d" cy="%d" r="7" fill="#ff453a"/>' % (cx + 290, cy - 150))
    return svg(body, defs)


def empresas():
    """Equipos de red apilados, con luces."""
    defs = (grad("box", [(0, "#ffffff", 1), (1, "#e3e8ef", 1)], 0, 0, 0, 1)
            + grad("box2", [(0, "#1a2436", 1), (1, "#0b1220", 1)], 0, 0, 0, 1))
    rnd = random.Random(3)
    out = ['<ellipse cx="600" cy="520" rx="430" ry="34" fill="#000" opacity=".07"/>']
    y = 150
    for k in range(4):
        dark = k == 1
        out.append('<rect x="210" y="%d" width="780" height="84" rx="18" fill="url(#%s)" '
                   'stroke="%s" stroke-width="1.5"/>' % (y, "box2" if dark else "box",
                                                       "#0b1220" if dark else "#cfd6e0"))
        for j in range(16):
            x = 250 + j * 34
            out.append('<rect x="%d" y="%d" width="22" height="22" rx="4" fill="%s"/>' % (
                x, y + 22, "#05080f" if not dark else "#27324a"))
            on = rnd.random() > .3
            out.append('<circle cx="%d" cy="%d" r="3.6" fill="%s"/>' % (
                x + 11, y + 60, (rnd.choice(["#30d158", "#30d158", SKY, "#ffd60a"]) if on else "#9aa3b2")))
        out.append('<circle cx="930" cy="%d" r="11" fill="%s"/>' % (y + 42, SKY if k % 2 else BLUE))
        out.append('<rect x="820" y="%d" width="70" height="8" rx="4" fill="%s"/>' % (
            y + 38, "#3a465c" if dark else "#c3cbd7"))
        y += 96
    return svg("".join(out), defs)


def comunidades():
    """Cerros, casas y una torre que emite señal."""
    defs = (grad("sky", [(0, "#dff3fb", 1), (1, "#f5f5f7", 1)], 0, 0, 0, 1)
            + grad("h1", [(0, "#9fd3ea", 1), (1, "#cfe9f4", 1)], 0, 0, 0, 1)
            + grad("h2", [(0, "#58aeda", 1), (1, "#8fcae6", 1)], 0, 0, 0, 1)
            + grad("h3", [(0, BLUE, 1), (1, "#3a94cf", 1)], 0, 0, 0, 1))
    arcs = "".join('<path d="M %d 150 A %d %d 0 0 1 %d 150" fill="none" stroke="%s" stroke-width="5" '
                   'stroke-linecap="round" opacity="%.2f"/>' % (600 - r, r, r, 600 + r, SKY, o)
                   for r, o in ((46, .95), (86, .65), (128, .4), (172, .22)))
    houses = "".join(
        '<g transform="translate(%d %d)"><rect x="0" y="22" width="56" height="40" rx="5" fill="#fff"/>'
        '<path d="M -6 24 L 28 0 L 62 24 Z" fill="%s"/><rect x="22" y="38" width="13" height="24" rx="2" '
        'fill="%s"/></g>' % (x, y, c, BLUE)
        for x, y, c in ((170, 420, "#0b1220"), (290, 440, "#ff9f0a"), (860, 430, "#0b1220"),
                        (980, 415, "#ff9f0a"), (420, 455, "#0b1220")))
    body = ('<rect width="1200" height="560" fill="url(#sky)"/>'
            '<path d="M 0 400 Q 200 250 430 370 T 820 330 T 1200 380 V 560 H 0 Z" fill="url(#h1)"/>'
            '<path d="M 0 450 Q 240 340 520 430 T 1200 420 V 560 H 0 Z" fill="url(#h2)"/>'
            + arcs +
            '<path d="M 600 150 L 560 470 M 600 150 L 640 470 M 572 380 L 628 380 M 580 310 L 620 310 '
            'M 588 240 L 612 240 M 572 380 L 620 310 M 628 380 L 580 310 M 580 310 L 612 240 '
            'M 620 310 L 588 240" stroke="#0b1220" stroke-width="5" stroke-linecap="round" fill="none"/>'
            '<circle cx="600" cy="150" r="10" fill="#ff453a"/>'
            '<path d="M 0 500 Q 300 440 620 490 T 1200 470 V 560 H 0 Z" fill="url(#h3)"/>' + houses)
    return svg(body, defs)


def mineria():
    """Enlace punto a punto entre dos cerros, de noche."""
    defs = (grad("n", [(0, "#101b33", 1), (1, "#0b1220", 1)], 0, 0, 0, 1)
            + grad("m1", [(0, "#1c2b4a", 1), (1, "#101a30", 1)], 0, 0, 0, 1)
            + grad("m2", [(0, "#27406e", 1), (1, "#15223d", 1)], 0, 0, 0, 1)
            + grad("beam", [(0, SKY, 0), (0.5, "#7fe3ff", 1), (1, SKY, 0)], 0, 0, 1, 0))
    rnd = random.Random(11)
    stars = "".join('<circle cx="%.0f" cy="%.0f" r="%.1f" fill="#fff" opacity="%.2f"/>' % (
        rnd.uniform(0, 1200), rnd.uniform(0, 260), rnd.uniform(.6, 1.8), rnd.uniform(.3, .9))
        for _ in range(70))

    def mast(x, y):
        return ('<path d="M %d %d L %d %d" stroke="#aab6cc" stroke-width="5" stroke-linecap="round"/>'
                '<circle cx="%d" cy="%d" r="15" fill="#f5f5f7"/><circle cx="%d" cy="%d" r="6" fill="%s"/>'
                % (x, y, x, y + 86, x, y, x, y, SKY))
    body = ('<rect width="1200" height="560" fill="url(#n)"/>' + stars
            + '<path d="M 0 560 L 0 420 L 180 250 L 300 340 L 420 300 L 560 470 L 700 420 L 860 260 '
              'L 1010 200 L 1200 360 V 560 Z" fill="url(#m1)"/>'
            + '<path d="M 0 560 L 0 480 L 240 360 L 420 470 L 640 520 L 900 380 L 1200 470 V 560 Z" '
              'fill="url(#m2)"/>'
            + '<path d="M 180 168 L 1010 118" stroke="url(#beam)" stroke-width="5" stroke-linecap="round"/>'
            + '<path d="M 180 168 L 1010 118" stroke="#7fe3ff" stroke-width="16" opacity=".12" '
              'stroke-linecap="round"/>'
            + "".join('<circle cx="%.0f" cy="%.0f" r="5" fill="#fff" opacity=".9"/>' % (
                180 + 830 * t, 168 - 50 * t) for t in (.22, .47, .71))
            + mast(180, 168) + mast(1010, 118))
    return svg(body, defs)


def aerolab():
    """Dron visto de arriba."""
    defs = (radial("p", [(0, SKY, .32), (1, SKY, .06)])
            + grad("b", [(0, "#2b3445", 1), (1, "#0b1220", 1)], 0, 0, 0, 1))
    cx, cy = 600, 300
    arms = "".join('<path d="M %d %d L %.0f %.0f" stroke="#1d2636" stroke-width="20" stroke-linecap="round"/>'
                   % (cx, cy, cx + dx, cy + dy) for dx, dy in ((-230, -150), (230, -150), (-230, 150), (230, 150)))
    props = "".join(
        '<circle cx="%.0f" cy="%.0f" r="112" fill="url(#p)" stroke="%s" stroke-opacity=".35" stroke-width="2"/>'
        '<ellipse cx="%.0f" cy="%.0f" rx="104" ry="11" fill="#0b1220" opacity=".55" '
        'transform="rotate(%d %.0f %.0f)"/><circle cx="%.0f" cy="%.0f" r="17" fill="#0b1220"/>' % (
            cx + dx, cy + dy, SKY, cx + dx, cy + dy, rot, cx + dx, cy + dy, cx + dx, cy + dy)
        for dx, dy, rot in ((-230, -150, 28), (230, -150, -34), (-230, 150, -18), (230, 150, 40)))
    body = ('<ellipse cx="600" cy="505" rx="330" ry="24" fill="#000" opacity=".08"/>' + arms + props
            + '<rect x="%d" y="%d" width="200" height="124" rx="46" fill="url(#b)"/>' % (cx - 100, cy - 62)
            + '<circle cx="%d" cy="%d" r="27" fill="#05080f"/><circle cx="%d" cy="%d" r="15" fill="%s"/>'
              % (cx, cy + 14, cx, cy + 14, BLUE)
            + '<circle cx="%d" cy="%d" r="5" fill="#fff" opacity=".6"/>' % (cx - 6, cy + 8)
            + '<circle cx="%d" cy="%d" r="6" fill="#30d158"/><circle cx="%d" cy="%d" r="6" fill="#ff453a"/>'
              % (cx - 62, cy - 34, cx + 62, cy - 34))
    return svg(body, defs)


def soporte():
    """Ondas de señal: para la llamada a la acción o lo que haga falta."""
    defs = grad("w", [(0, BLUE, 1), (1, SKY, 1)], 0, 0, 1, 0)
    waves = "".join(
        '<path d="M 0 %d C 200 %d, 400 %d, 600 %d S 1000 %d, 1200 %d" fill="none" stroke="url(#w)" '
        'stroke-width="%.1f" opacity="%.2f"/>' % (280 + k * 9, 280 - a, 280 + a, 280, 280 - a, 280 + k * 5,
                                                  2.2, .15 + .07 * (8 - abs(k)))
        for k, a in ((k, 30 + abs(k) * 26) for k in range(-7, 8)))
    return svg(waves, defs)


ART = {"hero_fibra": fibra, "tile_camara": camara, "tile_empresas": empresas,
       "tile_comunidades": comunidades, "tile_mineria": mineria, "tile_aerolab": aerolab,
       "ondas": soporte}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for folder in sys.argv[1:]:
        os.makedirs(folder, exist_ok=True)
        for name, draw in ART.items():
            with open(os.path.join(folder, name + ".svg"), "w", encoding="utf-8", newline="\n") as f:
                f.write(draw())
        print("Ilustraciones en", folder, sorted(ART))
