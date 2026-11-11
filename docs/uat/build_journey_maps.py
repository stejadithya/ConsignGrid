"""Build the TyreGrow UAT journey-map PDFs (fillable on screen, printable on paper).

    pip install reportlab
    python docs/uat/build_journey_maps.py            # writes docs/uat/*.pdf

Outputs: the complete edition plus one edition per role (only that role's steps to tick).
Content lives in journeys.py; this file only does layout.
"""

import os
import sys
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, Flowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

sys.path.insert(0, os.path.dirname(__file__))
from journeys import BIG_PICTURE, JOURNEYS, LANES, ROLE_CARDS, ROLE_ORDER, ROLES  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
VERSION = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "VERSION")).read().strip()
TODAY = date.today().strftime("%d %B %Y")

# ---------------------------------------------------------------- fonts & colours
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("Sans", f"{FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", f"{FONT_DIR}/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans", boldItalic="Sans-Bold")

INK = colors.HexColor("#18181b")
SOFT = colors.HexColor("#52525b")
FAINT = colors.HexColor("#8a8a93")
LINE = colors.HexColor("#e4e4e0")
CANVAS = colors.HexColor("#f6f6f3")
BRAND = colors.HexColor("#fdda00")
BRAND_SOFT = colors.HexColor("#fff8d6")
CHARCOAL = colors.HexColor("#1c1c1f")
OK = colors.HexColor("#15803d")


def hexc(h):
    return colors.HexColor(h)


def tint(h, t=0.88):
    c = colors.HexColor(h)
    return colors.Color(c.red + (1 - c.red) * t, c.green + (1 - c.green) * t, c.blue + (1 - c.blue) * t)


S = {
    "title": ParagraphStyle("title", fontName="Sans-Bold", fontSize=28, leading=34, textColor=INK),
    "subtitle": ParagraphStyle("subtitle", fontName="Sans", fontSize=13, leading=19, textColor=SOFT),
    "h1": ParagraphStyle("h1", fontName="Sans-Bold", fontSize=18, leading=23, textColor=INK, spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=12, leading=16, textColor=INK, spaceBefore=8, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Sans", fontSize=9.5, leading=13.5, textColor=INK),
    "soft": ParagraphStyle("soft", fontName="Sans", fontSize=9, leading=13, textColor=SOFT),
    "small": ParagraphStyle("small", fontName="Sans", fontSize=8, leading=10.5, textColor=INK),
    "smallsoft": ParagraphStyle("smallsoft", fontName="Sans", fontSize=7.5, leading=10, textColor=SOFT),
    "th": ParagraphStyle("th", fontName="Sans-Bold", fontSize=7.5, leading=9.5, textColor=colors.white),
    "cell_c": ParagraphStyle("cell_c", fontName="Sans-Bold", fontSize=9, leading=11, textColor=INK, alignment=TA_CENTER),
}

PAGE_W, PAGE_H = A4
MARGIN = 36
FRAME_W = PAGE_W - 2 * MARGIN


def P(text, style="body"):
    return Paragraph(text, S[style] if isinstance(style, str) else style)


# ---------------------------------------------------------------- form-field flowables
class Field(Flowable):
    """A fillable text box (prints as an empty box)."""

    def __init__(self, name, width, height=16, multiline=False, tooltip=None):
        super().__init__()
        self.name, self.width, self.height, self.multiline, self.tooltip = name, width, height, multiline, tooltip

    def draw(self):
        self.canv.acroForm.textfield(
            name=self.name, tooltip=self.tooltip or self.name, x=0, y=0, width=self.width, height=self.height,
            fontName="Helvetica", fontSize=8 if self.multiline else 9, borderWidth=0.6, borderColor=FAINT,
            fillColor=colors.white, textColor=INK, forceBorder=True, relative=True,
            fieldFlags="multiline" if self.multiline else "")


class Result(Flowable):
    """Two exclusive choices: Works / Issue (radio buttons, printable as boxes)."""

    def __init__(self, name, width=58, height=30, labels=("Works", "Issue")):
        super().__init__()
        self.name, self.width, self.height, self.labels = name, width, height, labels

    def draw(self):
        c = self.canv
        for i, (label, style, value) in enumerate(zip(self.labels, ("check", "cross"), ("yes", "no"), strict=False)):
            y = self.height - 13 - i * 15
            c.acroForm.radio(name=self.name, value=value, selected=False, x=0, y=y, size=11, buttonStyle=style,
                             shape="square", borderWidth=0.8, borderColor=SOFT, fillColor=colors.white,
                             textColor=OK if value == "yes" else colors.HexColor("#b42318"), forceBorder=True,
                             relative=True, tooltip=f"{self.name}: {label}")
            c.setFont("Sans", 7.5)
            c.setFillColor(INK)
            c.drawString(15, y + 2.5, label)


# ---------------------------------------------------------------- diagrams
def _lines(text, font, size, width):
    return simpleSplit(text, font, size, width)


def _arrow(c, x1, y1, x2, y2, color):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.1)
    c.line(x1, y1, x2, y2)
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    L = 5
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - L * math.cos(ang - 0.45), y2 - L * math.sin(ang - 0.45))
    p.lineTo(x2 - L * math.cos(ang + 0.45), y2 - L * math.sin(ang + 0.45))
    p.close()
    c.drawPath(p, fill=1, stroke=0)


class Swimlane(Flowable):
    """Vertical swimlanes (one column per person); numbered steps flow top to bottom."""

    HEADER = 30
    PILL = 18
    GAP = 13

    def __init__(self, journey, highlight=None):
        super().__init__()
        self.j, self.highlight = journey, highlight
        self.width = FRAME_W
        n = len(journey["lanes"])
        self.lane_w = self.width / n
        self.box_w = min(150, self.lane_w - 18)
        self.rows = []
        for st in journey["steps"]:
            lines = _lines(st["short"], "Sans", 8, self.box_w - 26)
            self.rows.append((st, lines, max(28, 10 + 10.5 * len(lines))))
        self.height = self.HEADER + 10 + self.PILL + self.GAP + sum(h + self.GAP for _, _, h in self.rows) + self.PILL + 6

    def _faded(self, lane_key):
        return self.highlight is not None and self.highlight not in LANES[lane_key][2] and lane_key != "SYS"

    def draw(self):
        c = self.canv
        lanes = self.j["lanes"]
        top = self.height
        # lane backgrounds and headers
        for i, key in enumerate(lanes):
            label, col, _ = LANES[key]
            x = i * self.lane_w
            faded = self._faded(key)
            c.setFillColor(colors.HexColor("#fafaf8") if i % 2 == 0 else colors.white)
            c.setStrokeColor(LINE)
            c.setLineWidth(0.6)
            c.rect(x, 0, self.lane_w, top, fill=1, stroke=1)
            c.setFillColor(tint(col, 0.93) if faded else (tint(col, 0.55) if key == "SYS" else hexc(col)))
            c.rect(x, top - self.HEADER, self.lane_w, self.HEADER, fill=1, stroke=0)
            c.setFillColor(FAINT if faded else (INK if key == "SYS" else colors.white))
            lines = _lines(label, "Sans-Bold", 8, self.lane_w - 10)
            ty = top - self.HEADER / 2 + (len(lines) - 1) * 4.5 - 3
            for ln in lines:
                c.setFont("Sans-Bold", 8)
                c.drawCentredString(x + self.lane_w / 2, ty, ln)
                ty -= 9
        cx = lambda key: (lanes.index(key) + 0.5) * self.lane_w  # noqa: E731
        y = top - self.HEADER - 10
        # start pill
        first_lane = self.rows[0][0]["lane"]
        self._pill(c, cx(first_lane), y - self.PILL / 2, "START", OK)
        prev = (cx(first_lane), y - self.PILL)
        y -= self.PILL + self.GAP
        boxes = []
        for idx, (st, lines, h) in enumerate(self.rows, start=1):
            x_c = cx(st["lane"])
            boxes.append((st, lines, h, x_c, y))
            self._link(c, prev, (x_c, y))
            prev = (x_c, y - h)
            y -= h + self.GAP
        self._link(c, prev, (cx(self.rows[-1][0]["lane"]), y))
        self._pill(c, cx(self.rows[-1][0]["lane"]), y - self.PILL / 2, "END", CHARCOAL)
        for idx, (st, lines, h, x_c, y_top) in enumerate(boxes, start=1):
            self._box(c, idx, st, lines, h, x_c, y_top)

    def _link(self, c, a, b):
        (x1, y1), (x2, y2) = a, b
        col = colors.HexColor("#9a9aa2")
        if abs(x1 - x2) < 1:
            _arrow(c, x1, y1, x2, y2 + 0.5, col)
        else:
            mid = (y1 + y2) / 2
            c.setStrokeColor(col)
            c.setLineWidth(1.1)
            c.line(x1, y1, x1, mid)
            c.line(x1, mid, x2, mid)
            _arrow(c, x2, mid, x2, y2 + 0.5, col)

    def _pill(self, c, x, y_mid, text, col):
        w = 46
        c.setFillColor(col)
        c.roundRect(x - w / 2, y_mid - self.PILL / 2, w, self.PILL, self.PILL / 2, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Sans-Bold", 7.5)
        c.drawCentredString(x, y_mid - 2.7, text)

    def _box(self, c, idx, st, lines, h, x_c, y_top):
        key = st["lane"]
        col = LANES[key][1]
        faded = self._faded(key)
        x = x_c - self.box_w / 2
        c.setFillColor(colors.white)
        c.setStrokeColor(tint(col, 0.6) if faded else hexc(col))
        c.setLineWidth(0.6 if faded else 1.2)
        if key == "SYS":
            c.setDash(3, 2)
        c.roundRect(x, y_top - h, self.box_w, h, 6, fill=1, stroke=1)
        c.setDash()
        # number badge
        c.setFillColor(tint(col, 0.6) if faded else hexc(col))
        c.circle(x + 11, y_top - h / 2, 7.5, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Sans-Bold", 7.5)
        c.drawCentredString(x + 11, y_top - h / 2 - 2.6, str(idx))
        c.setFillColor(FAINT if faded else INK)
        c.setFont("Sans", 8)
        ty = y_top - h / 2 + (len(lines) - 1) * 5.25 - 2.8
        for ln in lines:
            c.drawString(x + 23, ty, ln)
            ty -= 10.5


class BigPicture(Flowable):
    """How the journeys connect, from supplier to invoice."""

    def __init__(self):
        super().__init__()
        self.width, self.height = FRAME_W, 430

    def draw(self):
        c = self.canv
        bw, bh = 150, 58
        W = self.width
        pos = {  # centre positions
            "setup": (W / 2, 395), "supplier": (W / 2 - 170, 300), "order": (W / 2, 300), "find": (W / 2 + 170, 300),
            "sell": (W / 2, 195), "check": (W / 2 + 170, 195), "invoice": (W / 2, 90), "see": (W / 2 - 170, 90),
        }
        accent = {"setup": "#52525b", "supplier": "#b45309", "order": "#1d5fbf", "find": "#7c3aed", "sell": "#15803d",
                  "check": "#15803d", "invoice": "#1d5fbf", "see": "#8a8a93"}
        arrows = [("setup", "order", "s"), ("supplier", "order", "h"), ("find", "order", "h"), ("order", "sell", "v"),
                  ("check", "sell", "h"), ("sell", "invoice", "v"), ("check", "invoice", "d")]
        g = colors.HexColor("#9a9aa2")
        for a, b, kind in arrows:
            (x1, y1), (x2, y2) = pos[a], pos[b]
            if kind in ("v", "s"):
                _arrow(c, x1, y1 - bh / 2, x2, y2 + bh / 2 + 1, g)
            elif kind == "h":
                sx = x1 + (bw / 2 if x2 > x1 else -bw / 2)
                ex = x2 - (bw / 2 if x2 > x1 else -bw / 2)
                _arrow(c, sx, y1, ex + (-1 if x2 > x1 else 1), y2, g)
            else:
                c.setStrokeColor(g)
                c.setLineWidth(1.1)
                c.line(x1, y1 - bh / 2, x1, y2)
                _arrow(c, x1, y2, x2 + bw / 2 + 1, y2, g)
        # replacement loop: sell -> order (dashed)
        lx = pos["sell"][0] - 45
        c.setDash(3, 2)
        c.setStrokeColor(g)
        c.line(lx, pos["sell"][1] + bh / 2, lx, pos["order"][1] - bh / 2 + 6)
        c.setDash()
        _arrow(c, lx, pos["order"][1] - bh / 2 + 6, lx, pos["order"][1] - bh / 2 - 0.5, g)
        c.setFont("Sans", 7)
        c.setFillColor(SOFT)
        c.drawRightString(lx - 5, (pos["sell"][1] + pos["order"][1]) / 2 - 3, "automatic replacement")
        for key, label, jn in BIG_PICTURE["boxes"]:
            x, y = pos[key]
            col = accent[key]
            c.setFillColor(colors.white)
            c.setStrokeColor(hexc(col))
            c.setLineWidth(1.4)
            c.roundRect(x - bw / 2, y - bh / 2, bw, bh, 8, fill=1, stroke=1)
            c.setFillColor(hexc(col))
            c.roundRect(x - bw / 2, y + bh / 2 - 14, bw, 14, 8, fill=1, stroke=0)
            c.rect(x - bw / 2, y + bh / 2 - 14, bw, 7, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont("Sans-Bold", 7.5)
            c.drawCentredString(x, y + bh / 2 - 10.5, f"Journey {jn}")
            c.setFillColor(INK)
            c.setFont("Sans-Bold", 8.5)
            ty = y + 4
            for ln in label.split("\n"):
                c.drawCentredString(x, ty, ln)
                ty -= 11
        c.setFont("Sans", 7.5)
        c.setFillColor(SOFT)
        c.drawCentredString(W / 2, 10, "Arrows show what usually happens next. Journey 1 (signing in) and 11 (checking) apply everywhere.")


# ---------------------------------------------------------------- building blocks
def role_chip_text(keys):
    parts = []
    for k in keys:
        r = ROLES[k]
        parts.append(f'<font color="{r["color"]}"><b>■</b></font> {r["name"]}')
    return "   ".join(parts)


def journey_roles(j):
    out = []
    for st in j["steps"]:
        for k in (ROLE_ORDER if "ALL" in st["who"] else shown_roles(st)):
            if k not in out:
                out.append(k)
    return [k for k in ROLE_ORDER if k in out]


def step_roles(st):
    return set(ROLE_ORDER) if "ALL" in st["who"] else set(st["who"])


def shown_roles(st):
    """Roles to print for a step. The Administrator can do every step, so it is shown only where it is their job."""
    keys = [k for k in ROLE_ORDER if k in st["who"]]
    admin_job = "ADM" in LANES[st["lane"]][2] and st["lane"] != "STAFF"
    return [k for k in keys if k != "ADM" or admin_job or keys == ["ADM"]]


def who_text(st):
    if "ALL" in st["who"]:
        return "Everyone"
    if st["lane"] == "SYS":
        return "App (automatic)<br/><font size=6.5 color='#52525b'>check: " + ", ".join(
            ROLES[k]["short"] for k in shown_roles(st)) + "</font>"
    return "<br/>".join(f'<font color="{ROLES[k]["color"]}">■</font> {ROLES[k]["short"]}' for k in shown_roles(st))


def header_band(num, title):
    t = Table([[P(f'<font color="#1c1c1f"><b>{num}</b></font>', ParagraphStyle(
        "n", fontName="Sans-Bold", fontSize=20, leading=22, alignment=TA_CENTER)), P(title, "h1")]],
        colWidths=[44, FRAME_W - 44], rowHeights=[40])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), BRAND), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (1, 0), (1, 0), 10), ("BACKGROUND", (1, 0), (1, 0), CANVAS)]))
    return t


def start_end(j):
    t = Table([[P("<b>STARTS WHEN</b>", "smallsoft"), P("<b>ENDS WHEN</b>", "smallsoft")],
               [P(j["starts"], "body"), P(j["ends"], "body")]], colWidths=[FRAME_W / 2] * 2)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#ecfdf3")), ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f1f1ef")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, OK), ("LINEBEFORE", (1, 0), (1, -1), 3, CHARCOAL),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 1), (-1, 1), 7), ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def checklist(j, jn, prefix, role=None):
    cols = [22, 62, 168, 140, 56, FRAME_W - 22 - 62 - 168 - 140 - 56]
    head = [P(h, "th") for h in ("#", "Who", "What to do (and where)", "What you should see", "Result", "Comments")]
    rows = [head]
    for i, st in enumerate(j["steps"], start=1):
        if role and role not in step_roles(st):
            continue
        rows.append([P(f"<b>{i}</b>", "cell_c"), P(who_text(st), "small"), P(st["do"], "small"), P(st["see"], "small"),
                     Result(f"{prefix}j{jn}_s{i}_result"), Field(f"{prefix}j{jn}_s{i}_comment", cols[5] - 8, 34, True)])
    if len(rows) == 1:
        return None
    t = Table(rows, colWidths=cols, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), CHARCOAL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.5, LINE), ("TOPPADDING", (0, 0), (-1, -1), 5),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 4),
             ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    for r in range(1, len(rows)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#fbfbf9")))
    t.setStyle(TableStyle(style))
    return t


def signoff(jn, prefix):
    res = Result(f"{prefix}j{jn}_overall", width=150, height=30, labels=("Journey works end to end", "Journey has issues"))
    t = Table([[P("<b>Journey sign-off</b>", "small"), res, P("Tester", "smallsoft"), Field(f"{prefix}j{jn}_tester", 100),
                P("Date", "smallsoft"), Field(f"{prefix}j{jn}_date", 62)]],
              colWidths=[80, 156, 38, 108, 30, FRAME_W - 412])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, BRAND), ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def cover(story, edition, prefix, role=None):
    story.append(Spacer(1, 40))
    band = Table([[""]], colWidths=[60], rowHeights=[8])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND)]))
    band.hAlign = "LEFT"
    story += [band, Spacer(1, 14), P("TyreGrow", "subtitle"), P("UAT Journey Maps", "title"), Spacer(1, 6),
              P(edition, ParagraphStyle("ed", parent=S["subtitle"], textColor=INK, fontName="Sans-Bold")), Spacer(1, 4),
              P(f"Your step-by-step guide for testing the app · version {VERSION} · {TODAY}", "subtitle"), Spacer(1, 26)]
    t = Table([[P("Tester name", "smallsoft"), Field(f"{prefix}tester_name", 190), P("Role tested", "smallsoft"),
                Field(f"{prefix}tester_role", 150)],
               [P("Date started", "smallsoft"), Field(f"{prefix}date_started", 190), P("Date finished", "smallsoft"),
                Field(f"{prefix}date_finished", 150)]],
              colWidths=[74, 200, 74, FRAME_W - 348], rowHeights=[26, 26])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [t, Spacer(1, 22), P("How to use this document", "h2")]
    howto = [
        ("1", "Read <b>Who's who</b> to see what each person is responsible for, and the <b>big picture</b> of how the journeys connect."),
        ("2", "Each journey shows <b>where it starts</b>, <b>where it ends</b> and a <b>flow diagram</b>: one column per person, numbered boxes in order. "
              "Dashed boxes are things the app does by itself."),
        ("3", "Follow the numbered steps in the app. The <b>bold words</b> are menu items, buttons or fields you will see on screen."),
        ("4", "For every step, tick <b>Works</b> if you saw what is described, or <b>Issue</b> if not, and write what happened in <b>Comments</b>. "
              "Then sign off the journey."),
        ("5", "On screen: click the boxes and type, then <b>save the PDF</b> and send it back. On paper: print and tick with a pen."),
        ("6", "Found something odd? Also tell us in the app: your name (top right) → <b>Pilot feedback</b>."),
    ]
    if role:
        howto.insert(3, ("★", f"This edition lists only the steps a <b>{ROLES[role]['name']}</b> does or checks. The diagrams still "
                              "show the whole journey so you know what happens before and after you."))
    ht = Table([[P(f"<b>{n}</b>", "cell_c"), P(txt, "body")] for n, txt in howto], colWidths=[24, FRAME_W - 24])
    ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            ("BACKGROUND", (0, 0), (0, -1), BRAND_SOFT)]))
    story += [ht, Spacer(1, 14)]
    tip = Table([[P("<b>Tips for testers.</b> Use the test logins you were given. The warehouse starts with 10 of every tyre. "
                    "Write down document numbers you see (SRQ-, DEL-, SAL-, TRF-, INV-, STK-); they help us find the record. "
                    "Some journeys need two people (e.g. a Dealer and a Warehouse Manager): agree a time to test them together.", "soft")]],
                colWidths=[FRAME_W])
    tip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CANVAS), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                             ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [tip, PageBreak()]


def whos_who(story, role=None):
    story += [P("Who's who", "h1"), P("The six roles in TyreGrow, what they look after, and what they cannot do.", "soft"),
              Spacer(1, 8)]
    keys = [role] if role else ROLE_ORDER
    for k in keys:
        r, card = ROLES[k], ROLE_CARDS[k]
        does = "".join(f"• {d}<br/>" for d in card["does"])
        cannot = "".join(f"• {d}<br/>" for d in card["cannot"])
        t = Table([[P(f'<font color="white"><b>{r["name"]}</b></font>', "body"), P(card["summary"], "body")],
                   [P("<b>Does</b>", "smallsoft"), P(does, "small")],
                   [P("<b>Cannot</b>", "smallsoft"), P(cannot, "small")]], colWidths=[118, FRAME_W - 118])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), hexc(r["color"])), ("BACKGROUND", (1, 0), (1, 0), tint(r["color"], 0.9)),
                               ("BOX", (0, 0), (-1, -1), 0.6, hexc(r["color"])), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story += [KeepTogether([t]), Spacer(1, 7)]
    # participation matrix
    story += [CondPageBreak(260), P("Who takes part in which journey", "h2"),
              P("<b>●</b> does steps in this journey   <b>○</b> is notified or checks results.   "
                "The Administrator can step in on any journey.", "smallsoft"), Spacer(1, 4)]
    head = [P("Journey", "th")] + [P(ROLES[k]["short"], "th") for k in ROLE_ORDER]
    rows = [head]
    for jn, j in enumerate(JOURNEYS, start=1):
        doers = set()
        checkers = set()
        for st in j["steps"]:
            if st["lane"] == "SYS":
                checkers.update(shown_roles(st) if "ALL" not in st["who"] else ROLE_ORDER)
            else:
                doers.update(ROLE_ORDER if "ALL" in st["who"] else LANES[st["lane"]][2])
        cells = []
        for k in ROLE_ORDER:
            mark = "●" if k in doers else ("○" if k in checkers else "")
            cells.append(P(f'<font color="{ROLES[k]["color"]}">{mark}</font>', "cell_c"))
        rows.append([P(f"<b>{jn}</b>  {j['title']}", "small")] + cells)
    t = Table(rows, colWidths=[FRAME_W - 5 * 52] + [52] * 5, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), CHARCOAL), ("GRID", (0, 0), (-1, -1), 0.5, LINE),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if role:
        ci = 1 + ROLE_ORDER.index(role)
        st.append(("BACKGROUND", (ci, 1), (ci, -1), tint(ROLES[role]["color"], 0.88)))
    t.setStyle(TableStyle(st))
    story += [t, PageBreak()]


def big_picture(story):
    story += [P("The big picture", "h1"),
              P("From tyres arriving at the warehouse to dealers selling them and being invoiced. "
                "Each box is one or more journeys in this document.", "soft"), Spacer(1, 10), BigPicture(), Spacer(1, 10)]
    head = [P(h, "th") for h in ("#", "Journey", "Starts when", "Ends when")]
    rows = [head] + [[P(f"<b>{i}</b>", "cell_c"), P(f"<b>{j['title']}</b>", "small"), P(j["starts"], "small"), P(j["ends"], "small")]
                     for i, j in enumerate(JOURNEYS, start=1)]
    t = Table(rows, colWidths=[26, 150, (FRAME_W - 176) / 2, (FRAME_W - 176) / 2], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), CHARCOAL), ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story += [PageBreak(), P("All journeys at a glance", "h1"), Spacer(1, 4), t, PageBreak()]


def journey_section(story, jn, j, prefix, role=None):
    table = checklist(j, jn, prefix, role)
    if role and table is None:
        return False
    story += [header_band(jn, j["title"]), Spacer(1, 6), P(j["purpose"], "soft"), Spacer(1, 4),
              P("<b>People in this journey:</b>  " + role_chip_text(journey_roles(j)), "small"), Spacer(1, 6),
              start_end(j), Spacer(1, 8), Swimlane(j, highlight=role)]
    if j.get("note"):
        story += [Spacer(1, 6), P("<b>Also:</b> " + j["note"], "smallsoft")]
    # Keep the checklist under the diagram when it fits whole; otherwise start it on a fresh page.
    rows = len(table._cellvalues) - 1
    story += [Spacer(1, 12), CondPageBreak(110 + 72 * rows), P(f"Journey {jn} · {j['title']}: checklist", "h2")]
    if role:
        story.append(P(f"Only the steps a {ROLES[role]['name']} does or checks are listed. Step numbers match the diagram.", "smallsoft"))
    story += [Spacer(1, 4), table, Spacer(1, 10), signoff(jn, prefix), PageBreak()]
    return True


def footer(edition):
    def draw(c, doc):
        c.saveState()
        c.setFont("Sans", 7.5)
        c.setFillColor(FAINT)
        c.drawString(MARGIN, 20, f"TyreGrow UAT Journey Maps · {edition}")
        c.drawRightString(PAGE_W - MARGIN, 20, f"Page {doc.page}")
        c.setFillColor(BRAND)
        c.rect(0, PAGE_H - 6, PAGE_W, 6, fill=1, stroke=0)
        c.restoreState()
    return draw


def build(filename, edition, role=None):
    prefix = (role or "all").lower() + "_"
    doc = SimpleDocTemplate(os.path.join(OUT, filename), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=40, title=f"TyreGrow UAT Journey Maps — {edition}",
                            author="TyreGrow", subject="User acceptance testing: journeys, responsibilities and checklists")
    story = []
    cover(story, edition, prefix, role)
    whos_who(story, role)
    big_picture(story)
    included = []
    for jn, j in enumerate(JOURNEYS, start=1):
        if journey_section(story, jn, j, prefix, role):
            included.append(jn)
    while story and isinstance(story[-1], PageBreak):
        story.pop()
    doc.build(story, onFirstPage=footer(edition), onLaterPages=footer(edition))
    return included


if __name__ == "__main__":
    print("Complete:", build("TyreGrow-UAT-Journey-Maps.pdf", "Complete edition (all roles)"))
    for k in ROLE_ORDER:
        name = ROLES[k]["name"]
        print(name + ":", build(f"TyreGrow-UAT-Journey-Maps-{name.replace(' ', '-')}.pdf", f"{name} edition", role=k))
