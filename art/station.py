"""The space station screen: Ship, Weapons and Tools pages with 3-level upgrade panels.

It opens when you press E at the station. The game keeps running behind it, so it sits on
the right of the screen and leaves your ship, the station and anything coming at you in view.
Everything is drawn at the game's 640x360 resolution. The rows and prices here are only for the
mockups; the game will read them from its data files.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from . import hud, items, pix, pixfont, sprites as S
from .palette import rgba

PANEL_W, PANEL_H = 404, 252
LIST_W = 196
ROW_H = 27
PAGES = ("ship", "weapons", "tools")
PAGE_LABEL = {"ship": "SHIP", "weapons": "WEAPONS", "tools": "TOOLS"}


@dataclass
class Row:
    kind: str                     # icon kind (see hud.item_icon)
    name: str
    price: int | None             # next price; None when there's nothing left to buy
    level: int | None = None      # upgrades: levels owned (0 to `levels`)
    levels: int = 3               # upgrades: how many levels there are
    sub: str | None = None        # items: a short line under the name, e.g. "2/5 CARRIED"
    owned: bool = True            # weapons you haven't bought yet show their price only
    tag: str | None = None        # shown instead of the price, e.g. SOON or FREE


@dataclass
class Step:
    label: str                    # "LV1", "T2"...
    value: str                    # what that level gives
    price: int
    state: str                    # owned, next or locked
    art: Image.Image | None = None


@dataclass
class Detail:
    title: str
    subtitle: str
    lines: list[str]
    steps: list[Step]
    stats: list[tuple[str, str, str]] = field(default_factory=list)   # (label, now, next)
    bars: list[tuple[str, float, float]] = field(default_factory=list)  # (label, now, next) as 0..1
    buy: str = "BUY"
    price: int | None = 0         # None: nothing to buy, the button just says `buy`


def _money(v: int) -> str:
    return f"{v:,}"


def _text(img: Image.Image, text: str, x: int, y: int, color: str = "hud_text") -> int:
    t = pixfont.render(text, color)
    img.alpha_composite(t, (x, y))
    return t.width


def wrap(text: str, width: int) -> list[str]:
    """Split text into lines that fit `width` pixels in the HUD font."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and pixfont.text_width(trial) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _socket(size: int, icon: Image.Image, scale: int = 1, fill: str = "console_black") -> Image.Image:
    s = hud.panel(size, size, fill)
    ic = S.tight(icon)
    if scale > 1:
        ic = pix.scale(ic, scale)
    s.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
    return s


def _row(row: Row, credits: int, selected: bool) -> Image.Image:
    img = hud.panel(LIST_W, ROW_H - 2, "console_mid" if selected else "console_dark", 240)
    if selected:
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, LIST_W - 1, ROW_H - 3], outline=rgba("ion"))
    img.alpha_composite(_socket(21, hud.item_icon(row.kind)), (2, 2))
    _text(img, row.name, 28, 4, "hud_text" if row.owned or selected else "hud_dim")
    if row.level is not None:
        pips = hud.level_pips(row.level, row.levels, size=4, gap=2)
        img.alpha_composite(pips, (28, 15))
        lv = "MAX" if row.level >= row.levels else f"LV {row.level}"
        _text(img, lv, 28 + pips.width + 6, 14, "hud_dim")
    elif row.sub:
        _text(img, row.sub, 28, 14, "hud_dim")
    if row.tag is not None:
        p = pixfont.render(row.tag, "ion_hi" if row.tag == "FREE" else "hud_dim")
    elif row.price is None:
        p = pixfont.render("MAX" if row.level is not None else "OWNED", "hud_dim")
    else:
        p = pixfont.render(_money(row.price), "ore" if row.price <= credits else "console_edge")
    img.alpha_composite(p, (LIST_W - p.width - 6, 9))
    return img


def _step_card(step: Step, w: int, h: int, blink: bool) -> Image.Image:
    fill = {"owned": "console_mid", "next": "console_dark", "locked": "console_black"}[step.state]
    img = hud.panel(w, h, fill, 245)
    d = ImageDraw.Draw(img)
    edge = {"owned": "ion", "next": "ion_hi" if blink else "ion_dark", "locked": "console_edge"}[step.state]
    d.rectangle([0, 0, w - 1, h - 1], outline=rgba(edge))
    head = "hud_text" if step.state != "locked" else "hud_dim"
    _text(img, step.label, 4, 4, head)
    y = 14
    if step.art is not None:
        a = S.tight(step.art)
        img.alpha_composite(a, ((w - a.width) // 2, 14))
        y = 14 + a.height + 3
    for i, line in enumerate(step.value.split("\n") if step.value else []):
        t = pixfont.render(line, "ion_hi" if step.state == "next" else ("hud_text" if step.state == "owned" else "hud_dim"))
        img.alpha_composite(t, ((w - t.width) // 2, y + i * 9))
    return img


def _stat_bar(now: float, nxt: float, w: int = 48) -> tuple[Image.Image, Image.Image]:
    return (hud.bar(w, now, "hud_text", "console_mid"), hud.bar(w, nxt, "ion_hi", "console_mid"))


def detail_pane(det: Detail, credits: int, blink: bool = True, w: int = 190, h: int = 230,
                spots: dict | None = None) -> Image.Image:
    """The right-hand pane for the selected row: what it is, its levels as steps, what the next
    level changes, and the buy button. `spots` gets the button's box (x, y, w, h)."""
    img = hud.panel(w, h, "console_black", 240)
    y = 6
    _text(img, det.title, 8, y, "hud_text")
    _text(img, det.subtitle, 8, y + 10, "hud_dim")
    y += 24
    for line in wrap(" ".join(det.lines), w - 16):
        _text(img, line, 8, y, "hud_dim")
        y += 9
    y += 4
    n = len(det.steps)
    if n:
        gap = 4
        cw = (w - 16 - gap * (n - 1)) // n
        tallest = max((S.tight(s.art).height + 3 if s.art is not None else 0) for s in det.steps)
        ch = 16 + tallest + 9 * max(len(s.value.split("\n")) if s.value else 0 for s in det.steps) + 2
        if spots is not None:
            spots["steps"] = []
        for i, st in enumerate(det.steps):
            card = _step_card(st, cw, ch, blink)
            img.alpha_composite(card, (8 + i * (cw + gap), y))
            if spots is not None:
                spots["steps"].append((8 + i * (cw + gap), y, cw, ch + 12))
            if st.state == "owned":
                p = pixfont.render("OWNED", "ion")
            else:
                p = pixfont.render(_money(st.price), "ore" if st.price <= credits else "console_edge")
            img.alpha_composite(p, (8 + i * (cw + gap) + (cw - p.width) // 2, y + ch + 3))
        y += ch + 14
    for label, now, nxt in det.stats:
        _text(img, label, 8, y, "hud_dim")
        x = 70
        x += _text(img, now, x, y, "hud_text") + 4
        if nxt:
            x += _text(img, ">", x, y, "hud_dim") + 4
            _text(img, nxt, x, y, "ion_hi")
        y += 10
    for label, now, nxt in det.bars:
        _text(img, label, 8, y, "hud_dim")
        a, b = _stat_bar(now, nxt)
        img.alpha_composite(a, (66, y + 1))
        _text(img, ">", 66 + a.width + 4, y, "hud_dim")
        img.alpha_composite(b, (66 + a.width + 12, y + 1))
        y += 10
    # The buy button.
    affordable = det.price is not None and det.price <= credits
    btn = hud.panel(w - 16, 20, "console_mid" if affordable else "console_dark")
    bd = ImageDraw.Draw(btn)
    if affordable:
        bd.rectangle([0, 0, btn.width - 1, btn.height - 1], outline=rgba("ion"))
    _text(btn, det.buy, 6, 7, "hud_text" if affordable else "hud_dim")
    if affordable:
        p = pixfont.render(_money(det.price) if det.price else "FREE", "ore")
        key = pixfont.render("ENTER", "hud_dim")
        btn.alpha_composite(key, (btn.width - key.width - 6, 7))
        btn.alpha_composite(p, (btn.width - key.width - 12 - p.width, 7))
    elif det.price is not None:
        need = pixfont.render(f"NEED {_money(det.price - credits)} MORE", "console_edge")
        btn.alpha_composite(need, (btn.width - need.width - 6, 7))
    by = max(y + 6, h - 28)
    img.alpha_composite(btn, (8, by))
    if spots is not None:
        spots["buy"] = (8, by, btn.width, btn.height)
    return img


HINTS = [("1-3", "PAGE"), ("W/S", "PICK"), ("ENTER", "BUY"), ("E", "LEAVE")]


def station_panel(page: str, rows: list[Row], selected: int, det: Detail, credits: int,
                  warn: bool = False, blink: bool = True, spots: dict | None = None,
                  hints: list[tuple[str, str]] | None = None) -> Image.Image:
    """The whole station screen. `spots` gets the boxes (x, y, w, h) of its tabs, rows, the detail
    pane's level or tier cards ("steps") and the buy button, for the mouse. `hints` are the key hints
    along the bottom."""
    spots = {} if spots is None else spots
    spots["tabs"], spots["rows"] = [], []
    img = hud.panel(PANEL_W, PANEL_H, "console_dark", 238)
    d = ImageDraw.Draw(img)
    _text(img, "SPACE STATION", 8, 6, "hud_text")
    cr = pixfont.render(_money(credits), "ore")
    img.alpha_composite(cr, (PANEL_W - 8 - cr.width, 6))
    _text(img, "CR", PANEL_W - 8 - cr.width - 16, 6, "hud_dim")
    # Tabs.
    x = 6
    for i, p in enumerate(PAGES):
        on = p == page
        label = f"{i + 1} {PAGE_LABEL[p]}"
        tw = pixfont.text_width(label) + 16
        tab = hud.panel(tw, 15, "console_mid" if on else "console_black")
        td = ImageDraw.Draw(tab)
        if on:
            td.line([(1, 0), (tw - 2, 0)], fill=rgba("ion_hi"))
            td.line([(1, 1), (tw - 2, 1)], fill=rgba("ion"))
        _text(tab, label, 8, 5, "hud_text" if on else "hud_dim")
        img.alpha_composite(tab, (x, 20))
        spots["tabs"].append((x, 20, tw, 15))
        x += tw + 4
    d.line([(6, 35), (PANEL_W - 7, 35)], fill=rgba("console_edge"))
    if warn:
        msg = pixfont.render("ENEMIES NEAR - GAME STILL RUNNING", "danger_pink_hi" if blink else "danger_pink")
        strip = hud.panel(msg.width + 12, 13, "console_black")
        strip.alpha_composite(msg, (6, 3))
        img.alpha_composite(strip, ((PANEL_W - strip.width) // 2 + 4, 3))
    y = 40
    for i, row in enumerate(rows):
        img.alpha_composite(_row(row, credits, i == selected), (6, y))
        spots["rows"].append((6, y, LIST_W, ROW_H - 2))
        y += ROW_H
    pane_spots: dict = {}
    pane = detail_pane(det, credits, blink, w=PANEL_W - LIST_W - 18, h=PANEL_H - 40 - 18, spots=pane_spots)
    img.alpha_composite(pane, (LIST_W + 12, 40))
    bx, by, bw, bh = pane_spots["buy"]
    spots["buy"] = (LIST_W + 12 + bx, 40 + by, bw, bh)
    spots["steps"] = [(LIST_W + 12 + sx, 40 + sy, sw, sh) for sx, sy, sw, sh in pane_spots.get("steps", [])]
    # Key hints.
    x = 8
    for key, word in hints or HINTS:
        x += _text(img, key, x, PANEL_H - 12, "hud_text") + 4
        x += _text(img, word, x, PANEL_H - 12, "hud_dim") + 10
    return img


# ---------------------------------------------------------------- the three pages, as mocked up

def page_state(page: str) -> dict:
    """Example contents for each page, matching the starting prices in the design doc."""
    if page == "ship":
        credits = 1240
        rows = [Row("shield", "SHIELD", 900, level=1), Row("armor", "ARMOR", 300, level=0),
                Row("boost", "BOOST", 2250, level=2), Row("repair", "HEALTH", 100, sub="HULL 62%")]
        det = Detail("SHIELD", "LEVEL 1 OF 3",
                     ["SOAKS UP HITS, THEN RECHARGES", "A FEW SECONDS AFTER THE LAST ONE."],
                     [Step("LV1", "WEAK", 300, "owned", art=_strength(0.25)),
                      Step("LV2", "STRONG", 900, "next", art=_strength(0.55)),
                      Step("LV3", "TOUGHEST", 2700, "locked", art=_strength(1.0))],
                     bars=[("STRENGTH", 0.25, 0.55)], buy="BUY LV2", price=900)
        return dict(credits=credits, rows=rows, selected=0, det=det)
    if page == "weapons":
        credits = 1240
        rows = [Row("auto", "AUTO CANNON", 600, level=1), Row("sniper", "SNIPER", 900, level=1),
                Row("missiles", "MISSILES", 60, sub="4 LEFT  BUY 6"), Row("laser", "LASER", 1500, sub="3 CHARGES", owned=False)]
        det = Detail("SNIPER", "LEVEL 1 OF 3",
                     ["EACH LEVEL HITS 20% HARDER.", "LEVELS 2 AND 3 PIERCE MORE ENEMIES."],
                     [Step("LV1", "X1.2\nPIERCE 3", 300, "owned"), Step("LV2", "X1.44\nPIERCE 5", 900, "next"),
                      Step("LV3", "X1.73\nPIERCE 7", 2700, "locked")],
                     stats=[("DAMAGE", "X1.2", "X1.44"), ("PIERCE", "3", "5")], buy="BUY LV2", price=900)
        return dict(credits=credits, rows=rows, selected=1, det=det)
    credits = 3400
    rows = [Row("drill", "DRILL", 150, sub="0 CARRIED  3 OUT"), Row("mine", "MINE", 40, sub="2/5 CARRIED"),
            Row("sentry_auto", "AUTO SENTRY", 800, sub="FROM 800"), Row("sentry_sniper", "SNIPER SENTRY", 1600, sub="FROM 1,600"),
            Row("sentry_missile", "MISSILE SENTRY", 3200, sub="FROM 3,200")]
    det = Detail("AUTO SENTRY", "PICK A TIER",
                 ["PLACE IT ANYWHERE. IT NEVER MOVES,", "BUT ENEMIES CAN DESTROY IT."],
                 [Step("T1", "", 800, "locked", art=_tier_art("auto", 1)),
                  Step("T2", "", 1200, "next", art=_tier_art("auto", 2)),
                  Step("T3", "", 1800, "locked", art=_tier_art("auto", 3))],
                 buy="BUY T2", price=1200)
    return dict(credits=credits, rows=rows, selected=2, det=det, warn=True)


def _strength(v: float) -> Image.Image:
    return hud.bar(40, v, "ion", "console_mid")


def _tier_art(kind: str, tier: int) -> Image.Image:
    """A sentry over its health bar, for the tier cards."""
    s = S.tight(items.sentry(kind, tier))
    bar = items.struct_bar(items.SENTRY_HEALTH_BAR[tier], 1.0)
    out = Image.new("RGBA", (max(s.width, bar.width), s.height + 3 + bar.height), pix.CLEAR)
    out.alpha_composite(bar, ((out.width - bar.width) // 2, 0))
    out.alpha_composite(s, ((out.width - s.width) // 2, bar.height + 3))
    return pix.scale(out, 2)


def page_panel(page: str, blink: bool = True) -> Image.Image:
    st = page_state(page)
    return station_panel(page, st["rows"], st["selected"], st["det"], st["credits"], st.get("warn", False), blink)


def boost_upgrade_pane(blink: bool = True) -> Image.Image:
    """The upgrade panel on its own, for the boost at level 1."""
    det = Detail("BOOST", "LEVEL 1 OF 3",
                 ["HOLD SHIFT FOR A BURST OF SPEED.", "RECHARGES AFTER A SHORT PAUSE."],
                 [Step("LV1", "+20%", 250, "owned"), Step("LV2", "+40%", 750, "next"),
                  Step("LV3", "+80%", 2250, "locked")],
                 stats=[("TOP SPEED", "+20%", "+40%"), ("THRUST", "+20%", "+40%")], buy="BUY LV2", price=750)
    return detail_pane(det, 1240, blink, w=190, h=196)
