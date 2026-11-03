"""Draws the software-engineering diagrams of Sentinel HITL IDS as SVG files.

    python docs/diagrams/make_diagrams.py      (then render_pngs.ps1 makes the PNGs)

Diagrams: use case, activity (swimlanes), DFD level 0 (context), DFD level 1, COCOMO sheet.
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent
FONT = "Arial, Helvetica, sans-serif"
INK, MUTED, LINE = "#1b1f24", "#5b6470", "#2f3a46"
BLUE, BLUE_BG = "#1f5fad", "#e8f0fb"
ORANGE, ORANGE_BG = "#c2410c", "#fff1e8"
GREEN, GREEN_BG = "#15803d", "#e9f7ee"
GREY_BG = "#f4f6f8"


class SVG:
    def __init__(self, w, h, title):
        self.w, self.h, self.parts = w, h, []
        self.text(w / 2, 40, title, size=24, weight="700", anchor="middle")

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=15, weight="400", anchor="middle", color=INK, italic=False):
        lines = s.split("\n")
        y0 = y - (len(lines) - 1) * size * 0.6
        for i, line in enumerate(lines):
            style = ' font-style="italic"' if italic else ""
            self.add(f'<text x="{x}" y="{y0 + i * size * 1.2 + size * 0.35}" font-size="{size}" font-weight="{weight}" '
                     f'text-anchor="{anchor}" fill="{color}"{style}>{esc(line)}</text>')

    def rect(self, x, y, w, h, fill="#fff", stroke=LINE, rx=0, sw=1.6, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def label_box(self, x, y, s, size=13, color=MUTED):
        """Small label with a white background (for arrow captions)."""
        lines = s.split("\n")
        w = max(len(l) for l in lines) * size * 0.56 + 10
        h = len(lines) * size * 1.2 + 4
        self.add(f'<rect x="{x - w / 2}" y="{y - h / 2}" width="{w}" height="{h}" fill="#fff" opacity="0.92"/>')
        self.text(x, y, s, size=size, color=color)

    def arrow(self, pts, label=None, dashed=False, color=LINE, lab_at=0.5, lab_dx=0, lab_dy=0, head=True, size=13):
        d = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(pts))
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        mk = ' marker-end="url(#arr)"' if head else ""
        self.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6"{dash}{mk}/>')
        if label:
            # position along the polyline
            seg = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
            lens = [math.dist(a, b) for a, b in seg]
            target = sum(lens) * lab_at
            for (a, b), L in zip(seg, lens):
                if target <= L or (a, b) == seg[-1]:
                    t = target / L if L else 0
                    x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                    break
                target -= L
            self.label_box(x + lab_dx, y + lab_dy, label, size=size)

    def save(self, name):
        defs = ('<defs><marker id="arr" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="9" markerHeight="9" '
                f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker>'
                '<marker id="open" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" '
                f'orient="auto-start-reverse"><path d="M0,0 L11,6 L0,12" fill="none" stroke="{LINE}" stroke-width="1.5"/></marker>'
                '<marker id="tri" viewBox="0 0 14 14" refX="13" refY="7" markerWidth="16" markerHeight="16" '
                f'orient="auto-start-reverse"><path d="M0,0 L13,7 L0,14 z" fill="#fff" stroke="{LINE}" stroke-width="1.5"/></marker></defs>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
               f'font-family="{FONT}">{defs}<rect width="100%" height="100%" fill="#ffffff"/>' + "".join(self.parts) + "</svg>")
        (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
        print("wrote", name)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ======================================================================= USE CASE
def use_case():
    H = 1130
    g = SVG(1500, H, "Use Case Diagram: Sentinel HITL Intrusion Detection System")
    OY = 70          # everything below the generalization arrow is shifted down by this much
    g.add(f'<g transform="translate(0,{OY})">')

    def actor(x, y, name, sub=""):
        g.add(f'<circle cx="{x}" cy="{y - 52}" r="16" fill="#fff" stroke="{INK}" stroke-width="2"/>'
              f'<path d="M{x},{y - 36} L{x},{y + 6} M{x - 28},{y - 22} L{x + 28},{y - 22} M{x},{y + 6} L{x - 22},{y + 44} '
              f'M{x},{y + 6} L{x + 22},{y + 44}" stroke="{INK}" stroke-width="2" fill="none"/>')
        g.text(x, y + 66, name, size=16, weight="700")
        if sub:
            g.text(x, y + 86, sub, size=12, color=MUTED)

    def uc(x, y, s, w=300, fill="#fff"):
        g.add(f'<ellipse cx="{x}" cy="{y}" rx="{w / 2}" ry="30" fill="{fill}" stroke="{LINE}" stroke-width="1.6"/>')
        g.text(x, y, s, size=14)
        return (x, y, w / 2)

    def link(ax, ay, u, side):
        x, y, rx = u
        g.add(f'<line x1="{ax}" y1="{ay}" x2="{x + side * rx}" y2="{y}" stroke="{LINE}" stroke-width="1.4"/>')

    g.rect(330, 72, 840, 980, fill=GREY_BG, stroke=INK, rx=10, sw=2)
    g.text(750, 98, "Sentinel HITL IDS (web portal)", size=17, weight="700")

    login = uc(750, 150, "Log in", w=200, fill=BLUE_BG)
    A = {
        "dash": uc(545, 240, "View live dashboard"),
        "review": uc(545, 330, "Review uncertain alert"),
        "sim": uc(545, 420, "View similar incidents"),
        "decide": uc(545, 510, "Record decision with\ncontext & evidence"),
        "fp": uc(545, 600, "Mark false positive"),
        "kr": uc(545, 690, "Search Knowledge Repository"),
        "olap": uc(545, 780, "Analyse data warehouse\n(OLAP cube)"),
    }
    D = {
        "replay": uc(955, 240, "Control traffic replay"),
        "upload": uc(955, 320, "Upload traffic CSV"),
        "verify": uc(955, 400, "Verify analyst feedback"),
        "retrain": uc(955, 480, "Run controlled retraining"),
        "deploy": uc(955, 560, "Approve / deploy /\nroll back model"),
        "eval": uc(955, 640, "View evaluation"),
        "users": uc(955, 720, "Manage users & roles"),
        "audit": uc(955, 800, "View audit log"),
        "switch": uc(955, 880, "Switch warehouse On/Off"),
    }
    classify = uc(955, 990, "Classify & route flow", w=270, fill=ORANGE_BG)
    about = uc(545, 900, "View About page", w=230)

    actor(150, 380, "Security Analyst", "analyst")
    actor(1350, 470, "Administrator", "admin")
    actor(150, 880, "Visitor", "no login")
    g.rect(1260, 950, 180, 80, fill=ORANGE_BG, stroke=ORANGE, rx=4, sw=1.8)
    g.text(1350, 975, "«system»", size=12, color=ORANGE)
    g.text(1350, 1000, "Traffic Source", size=15, weight="700")
    g.text(1350, 1018, "(replay / CSV)", size=12, color=MUTED)

    for u in A.values():
        link(178, 360, u, -1)
    link(178, 360, login, -1)
    for u in D.values():
        link(1322, 450, u, 1)
    link(1322, 450, login, 1)
    link(178, 900, about, -1)
    g.add(f'<line x1="1260" y1="990" x2="1090" y2="990" stroke="{LINE}" stroke-width="1.4"/>')

    # «include» / «extend» (dashed, open arrowhead towards the included / extended use case)
    def dashed(pts, label, lx, ly):
        d = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y) in enumerate(pts))
        g.add(f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="1.5" stroke-dasharray="7 5" marker-end="url(#open)"/>')
        g.label_box(lx, ly, label, size=12)

    dashed([(545, 360), (545, 390)], "«include»", 650, 375)                         # review -> similar
    dashed([(695, 330), (735, 330), (735, 510), (697, 510)], "«include»", 735, 470)  # review -> decide
    dashed([(470, 574), (470, 538)], "«extend»", 400, 556)                           # false positive -> decide
    dashed([(805, 240), (770, 240), (770, 990), (822, 990)], "«include»", 770, 940)  # replay -> classify
    dashed([(955, 450), (955, 430)], "«include»", 1060, 440)                          # retraining -> verify
    g.add("</g>")

    # generalization: an administrator can do everything an analyst can (hollow triangle at the analyst)
    ax_head, ad_head = 380 + OY - 70, 470 + OY - 70
    g.add(f'<path d="M1350,{ad_head} L1350,64 L150,64 L150,{ax_head}" fill="none" stroke="{LINE}" stroke-width="1.6" marker-end="url(#tri)"/>')
    g.label_box(750, 64, "generalization: Administrator can also do everything a Security Analyst can", size=12)
    g.save("use_case_diagram")


# ======================================================================= ACTIVITY
def activity():
    W, H = 1520, 1720
    g = SVG(W, H, "Activity Diagram: life of a network flow in Sentinel (with swimlanes)")
    lanes = [("Traffic Replay", 0, 300, ORANGE_BG), ("Detection Engine (AI model + router)", 300, 760, BLUE_BG),
             ("Security Analyst", 760, 1130, GREEN_BG), ("Administrator", 1130, 1520, GREY_BG)]
    for name, x0, x1, bg in lanes:
        g.rect(x0 + 6, 66, x1 - x0 - 12, H - 80, fill=bg, stroke="#9aa5b1", sw=1.2)
        g.rect(x0 + 6, 66, x1 - x0 - 12, 40, fill="#ffffff", stroke="#9aa5b1", sw=1.2)
        g.text((x0 + x1) / 2, 86, name, size=16, weight="700")

    def act(x, y, s, w=250, h=56):
        g.rect(x - w / 2, y - h / 2, w, h, fill="#fff", stroke=LINE, rx=18)
        g.text(x, y, s, size=14)
        return x, y, w / 2, h / 2

    def dia(x, y, s, r=46):
        g.add(f'<path d="M{x},{y - r} L{x + r * 1.5},{y} L{x},{y + r} L{x - r * 1.5},{y} Z" fill="#fff" stroke="{LINE}" stroke-width="1.6"/>')
        g.text(x, y, s, size=13)
        return x, y, r * 1.5, r

    def start(x, y):
        g.add(f'<circle cx="{x}" cy="{y}" r="14" fill="{INK}"/>')

    def end(x, y):
        g.add(f'<circle cx="{x}" cy="{y}" r="16" fill="#fff" stroke="{INK}" stroke-width="2"/><circle cx="{x}" cy="{y}" r="9" fill="{INK}"/>')

    def merge(x, y, r=18):
        g.add(f'<path d="M{x},{y - r} L{x + r},{y} L{x},{y + r} L{x - r},{y} Z" fill="#fff" stroke="{LINE}" stroke-width="1.6"/>')

    def bar(x, y, w=160):
        g.rect(x - w / 2, y - 4, w, 8, fill=INK, stroke=INK)

    AX = 1325  # admin lane centre
    start(AX, 140)
    a_start = act(AX, 210, "Start traffic replay\n(batch size, speed)")
    g.arrow([(AX, 154), (AX, 182)])
    send = act(150, 300, "Send next batch\nof flows", w=230)
    g.arrow([(AX, 238), (AX, 262), (150, 262), (150, 272)])
    pre = act(530, 390, "Pre-process flow\n(64 features, scaling)")
    g.arrow([(150, 328), (150, 390), (405, 390)])
    pred = act(530, 480, "CNN-LSTM predicts\nattack class")
    g.arrow([(530, 418), (530, 452)])
    unc = act(530, 570, "Compute entropy, distance\n& Random Forest opinion", w=290)
    g.arrow([(530, 508), (530, 542)])
    d1 = dia(530, 670, "Uncertain?")
    g.arrow([(530, 598), (530, 624)])
    d2 = dia(420, 790, "Attack?", r=40)
    g.arrow([(461, 670), (420, 670), (420, 750)], label="no", lab_at=0.25)
    alert = act(420, 900, "Raise confident\nalert", w=170)
    close = act(640, 900, "Auto-close\n(count only)", w=170)
    g.arrow([(420, 830), (420, 872)], label="yes", lab_dx=-24)
    g.arrow([(480, 790), (640, 790), (640, 872)], label="no", lab_at=0.3)
    merge_y = 990
    merge(520, merge_y)
    g.arrow([(420, 928), (420, merge_y), (502, merge_y)])
    g.arrow([(640, 928), (640, merge_y), (538, merge_y)])
    stats = act(520, 1070, "Update live traffic\nstatistics", w=230)
    g.arrow([(520, 1008), (520, 1042)])
    d3 = dia(520, 1180, "More flows?", r=42)
    g.arrow([(520, 1098), (520, 1138)])
    # loop back to the replay for the next batch
    g.arrow([(457, 1180), (20, 1180), (20, 300), (35, 300)], label="yes", lab_at=0.18)
    end(520, 1290)
    g.arrow([(520, 1222), (520, 1272)], label="no", lab_dx=20)

    # uncertain -> analyst
    rev = act(945, 670, "Open review alert: context,\nverdict, evidence, similar cases", w=320, h=64)
    g.arrow([(599, 670), (785, 670)], label="yes", lab_at=0.4)
    d4 = dia(945, 790, "Malicious?", r=42)
    g.arrow([(945, 702), (945, 748)])
    mal = act(860, 900, "Record attack class\n+ reason", w=170)
    fp = act(1035, 900, "Mark false positive\n+ reason", w=170)
    g.arrow([(882, 790), (860, 790), (860, 872)], label="yes", lab_at=0.5, lab_dx=-30)
    g.arrow([(1008, 790), (1035, 790), (1035, 872)], label="no", lab_at=0.5, lab_dx=28)
    merge(945, 980)
    g.arrow([(860, 928), (860, 980), (927, 980)])
    g.arrow([(1035, 928), (1035, 980), (963, 980)])
    kr = act(945, 1060, "Save decision to\nKnowledge Repository", w=250)
    g.arrow([(945, 998), (945, 1032)])

    # admin
    ver = act(AX, 1060, "Verify feedback", w=220)
    g.arrow([(1070, 1060), (1215, 1060)])
    d5 = dia(AX, 1170, "≥ 20 verified?", r=44)
    g.arrow([(AX, 1088), (AX, 1126)])
    g.arrow([(AX + 66, 1170), (1490, 1170), (1490, 1060), (1435, 1060)], label="no: wait for\nmore decisions", lab_at=0.3, size=12)
    ret = act(AX, 1280, "Retrain candidate model\n(feedback + 200k old rows)", w=290)
    g.arrow([(AX, 1214), (AX, 1252)], label="yes", lab_dx=24)
    evl = act(AX, 1375, "Evaluate against criteria\nfixed before training", w=290)
    g.arrow([(AX, 1308), (AX, 1347)])
    d6 = dia(AX, 1475, "Passed?", r=40)
    g.arrow([(AX, 1403), (AX, 1435)])
    dep = act(1425, 1590, "Approve & deploy\n(rollback possible)", w=170)
    rej = act(1230, 1590, "Reject candidate\n(keep current)", w=170)
    g.arrow([(AX + 60, 1475), (1425, 1475), (1425, 1562)], label="yes", lab_at=0.3)
    g.arrow([(AX - 60, 1475), (1230, 1475), (1230, 1562)], label="no", lab_at=0.3)
    end(1425, 1680)
    g.arrow([(1425, 1618), (1425, 1662)])
    end(1230, 1680)
    g.arrow([(1230, 1618), (1230, 1662)])
    g.save("activity_diagram")


# ======================================================================= DFD
def entity(g, x, y, s, w=220, h=70):
    g.rect(x - w / 2, y - h / 2, w, h, fill=GREY_BG, stroke=INK, sw=2)
    g.text(x, y, s, size=15, weight="700")


def process(g, x, y, num, s, w=230, h=86):
    g.rect(x - w / 2, y - h / 2, w, h, fill=BLUE_BG, stroke=BLUE, rx=16, sw=2)
    g.add(f'<line x1="{x - w / 2}" y1="{y - h / 2 + 26}" x2="{x + w / 2}" y2="{y - h / 2 + 26}" stroke="{BLUE}" stroke-width="1.4"/>')
    g.text(x, y - h / 2 + 14, num, size=13, weight="700", color=BLUE)
    g.text(x, y + 12, s, size=14)


def store(g, x, y, num, s, w=240, h=40):
    x0 = x - w / 2
    g.add(f'<path d="M{x0 + w},{y - h / 2} L{x0},{y - h / 2} L{x0},{y + h / 2} L{x0 + w},{y + h / 2}" fill="{ORANGE_BG}" stroke="{ORANGE}" stroke-width="1.8"/>')
    g.add(f'<rect x="{x0 + 1}" y="{y - h / 2 + 1}" width="{w - 2}" height="{h - 2}" fill="{ORANGE_BG}"/>')
    g.add(f'<path d="M{x0 + w},{y - h / 2} L{x0},{y - h / 2} L{x0},{y + h / 2} L{x0 + w},{y + h / 2}" fill="none" stroke="{ORANGE}" stroke-width="1.8"/>')
    g.add(f'<line x1="{x0 + 48}" y1="{y - h / 2}" x2="{x0 + 48}" y2="{y + h / 2}" stroke="{ORANGE}" stroke-width="1.4"/>')
    g.text(x0 + 24, y, num, size=13, weight="700", color=ORANGE)
    g.text(x0 + 48 + (w - 48) / 2, y, s, size=14)


def dfd0():
    g = SVG(1400, 820, "Data Flow Diagram: Level 0 (Context Diagram)")
    cx, cy = 700, 430
    g.add(f'<circle cx="{cx}" cy="{cy}" r="150" fill="{BLUE_BG}" stroke="{BLUE}" stroke-width="2.5"/>')
    g.text(cx, cy - 40, "0", size=18, weight="700", color=BLUE)
    g.text(cx, cy + 5, "Sentinel HITL\nIntrusion Detection\nSystem", size=19, weight="700")
    entity(g, 150, 250, "Network Traffic\nSource")
    entity(g, 150, 620, "CIC-IDS2017\nDataset")
    entity(g, 1250, 250, "Security\nAnalyst")
    entity(g, 1250, 620, "Administrator")
    # traffic source
    g.arrow([(260, 240), (575, 345)], label="network flows\n(replay / uploaded CSV)", lab_at=0.45, lab_dy=-28)
    # dataset
    g.arrow([(260, 610), (566, 500)], label="training & benchmark data\n(70/15/15 split)", lab_at=0.45, lab_dy=26)
    # analyst
    g.arrow([(838, 360), (1140, 225)], label="alerts, review queue,\nsimilar incidents", lab_at=0.5, lab_dy=-30)
    g.arrow([(1140, 285), (850, 405)], label="verdict, reason, context,\nevidence, KR searches", lab_at=0.5, lab_dy=30)
    # admin
    g.arrow([(1140, 590), (848, 470)], label="replay control, verification,\nretrain / deploy / rollback,\nuser management", lab_at=0.5, lab_dy=-34)
    g.arrow([(830, 510), (1140, 650)], label="evaluation reports, model status,\naudit log, system health", lab_at=0.55, lab_dy=34)
    g.text(700, 790, "Level 0 shows the whole system as ONE process and only its exchanges with outside entities.",
           size=14, color=MUTED, italic=True)
    g.save("dfd_level0")


def dfd1():
    g = SVG(1940, 1340, "Data Flow Diagram: Level 1")
    EW = 180
    entity(g, 110, 300, "Network Traffic\nSource", w=EW)
    entity(g, 110, 470, "CIC-IDS2017\nDataset", w=EW)
    entity(g, 1760, 300, "Security\nAnalyst", w=EW)
    entity(g, 1760, 820, "Administrator", w=EW)

    PW = 220
    process(g, 1460, 120, "1.0", "Authenticate user", w=PW)
    process(g, 380, 300, "2.0", "Replay / import\ntraffic", w=PW)
    process(g, 650, 300, "3.0", "Classify flow\n(CNN-LSTM)", w=PW)
    process(g, 920, 300, "4.0", "Route by\nuncertainty", w=PW)
    process(g, 1190, 300, "5.0", "Review alert &\nrecord decision", w=PW)
    process(g, 1460, 640, "6.0", "Search Knowledge\nRepository", w=PW)
    process(g, 1190, 820, "7.0", "Verify feedback\n& retrain model", w=PW)
    process(g, 650, 980, "8.0", "Approve / deploy /\nroll back model", w=PW)
    process(g, 1190, 1170, "9.0", "Evaluate &\naudit report", w=PW)

    SW = 200
    store(g, 1460, 215, "D1", "Users & sessions", w=SW)
    store(g, 380, 470, "D2", "Replay & training", w=180)
    store(g, 650, 470, "D3", "Model registry", w=SW)
    store(g, 920, 470, "D4", "Alerts", w=SW)
    store(g, 1190, 470, "D5", "Analyst feedback", w=SW)
    store(g, 1460, 470, "D6", "Knowledge Repo", w=SW)
    store(g, 880, 1170, "D7", "Traffic statistics", w=SW)
    store(g, 1190, 1280, "D8", "Audit log", w=SW)

    A = g.arrow
    # authentication
    A([(1700, 265), (1572, 140)], label="login", lab_at=0.45, lab_dx=18, lab_dy=-10)
    A([(1850, 800), (1890, 800), (1890, 100), (1572, 100)], label="login", lab_at=0.85, lab_dy=-14)
    A([(1460, 163), (1460, 195)])
    # detection pipeline
    A([(200, 300), (268, 300)], label="flows", lab_dy=-16)
    A([(200, 470), (290, 470)], label="splits", lab_dy=-16)
    A([(380, 450), (380, 345)], label="test flows", lab_dx=-48, lab_at=0.5)
    A([(492, 300), (538, 300)])
    g.label_box(515, 276, "features", size=12)
    A([(762, 300), (808, 300)])
    g.label_box(785, 270, "class +\nscores", size=12)
    A([(1032, 300), (1078, 300)])
    g.label_box(1055, 270, "review\nitems", size=12)
    A([(650, 450), (650, 345)], label="active model", lab_dx=52)
    A([(920, 345), (920, 450)], label="alerts", lab_dx=30)
    # analyst
    A([(1302, 290), (1668, 290)], label="alert details, similar incidents", lab_at=0.5, lab_dy=-14)
    A([(1668, 320), (1302, 320)], label="verdict, reason, evidence", lab_at=0.5, lab_dy=14)
    A([(1190, 345), (1190, 450)], label="decision", lab_dx=40)
    A([(1250, 345), (1250, 400), (1460, 400), (1460, 450)], label="incident", lab_at=0.55, lab_dy=-12)
    A([(1460, 490), (1460, 597)], label="past incidents", lab_dx=-62)
    A([(1700, 337), (1700, 620), (1572, 620)], label="search", lab_at=0.35, lab_dx=30)
    A([(1572, 660), (1790, 660), (1790, 337)], label="results", lab_at=0.55, lab_dx=36)
    # replay counts
    A([(470, 345), (470, 405), (515, 405), (515, 1170), (778, 1170)], label="batch counts", lab_at=0.55, lab_dx=-50)
    # retraining
    A([(380, 490), (380, 760), (1100, 760), (1100, 777)], label="200k training rows + benchmark", lab_at=0.42, lab_dy=-14)
    A([(1190, 490), (1190, 777)], label="verified\nfeedback", lab_dx=48, lab_at=0.55)
    A([(1668, 820), (1302, 820)], label="verify, start retraining", lab_dy=-14)
    A([(1078, 850), (820, 850), (820, 980), (762, 980)], label="candidate +\nresults", lab_at=0.3, lab_dy=-26)
    A([(650, 937), (650, 490)], label="new active\nversion", lab_at=0.25, lab_dx=-52)
    A([(1760, 857), (1760, 1080), (700, 1080), (700, 1023)], label="approve / deploy / roll back", lab_at=0.45, lab_dy=-14)
    A([(600, 1023), (600, 1280), (1088, 1280)], label="admin actions", lab_at=0.75, lab_dy=-14)
    # evaluation & audit
    A([(982, 1170), (1078, 1170)], label="live counts", lab_dy=-16)
    A([(1190, 1260), (1190, 1215)], label="actions", lab_dx=40)
    A([(1302, 1170), (1820, 1170), (1820, 857)], label="evaluation, audit log,\nmodel status", lab_at=0.35, lab_dy=-24)
    g.text(970, 1325, "Rounded boxes = processes · open boxes = data stores · grey boxes = external entities",
           size=14, color=MUTED, italic=True)
    g.save("dfd_level1")


def cocomo():
    K = 7.737
    modes = [("Organic", 2.4, 1.05, 2.5, 0.38), ("Semi-detached", 3.0, 1.12, 2.5, 0.35),
             ("Embedded", 3.6, 1.20, 2.5, 0.32)]
    res = []
    for m, a, b, c, d in modes:
        E = a * K ** b
        D = c * E ** d
        res.append((m, a, b, c, d, E, D, E / D))
    drivers = [("RELY", "Required reliability", "High", 1.15), ("DATA", "Database size", "High", 1.08),
               ("CPLX", "Product complexity", "High", 1.15), ("VIRT", "Platform volatility", "Low", 0.87),
               ("AEXP", "Application experience", "Low", 1.13), ("MODP", "Modern practices", "High", 0.91),
               ("TOOL", "Software tools", "High", 0.91)]
    eaf = 1.0
    for *_, v in drivers:
        eaf *= v
    Ei = 3.2 * K ** 1.05 * eaf
    Di = 2.5 * Ei ** 0.38

    g = SVG(1500, 1340, "COCOMO Estimation: Sentinel HITL IDS")
    g.text(750, 72, "COnstructive COst MOdel (Boehm, 1981): estimates effort, duration and team size from program size",
           size=14, color=MUTED)

    # size box
    g.rect(40, 100, 1420, 92, fill=BLUE_BG, stroke=BLUE, rx=10)
    g.text(70, 128, "Project size (KLOC = thousands of delivered source lines, blank lines and comments excluded)", size=15, weight="700", anchor="start")
    g.text(70, 160, "Backend Python 3,534 + scripts 1,256 + React frontend 2,947 = 7,737 lines  →  KLOC = 7.737     "
           "(549 test lines not counted)", size=15, anchor="start")

    # formulas
    g.rect(40, 210, 690, 250, fill="#fff", stroke=LINE, rx=10)
    g.text(70, 238, "Basic COCOMO formulas", size=17, weight="700", anchor="start")
    for i, line in enumerate(["Effort      E = a × (KLOC)^b          person-months (PM)",
                              "Duration    D = c × (E)^d             months",
                              "People      P = E / D                 average team size",
                              "Productivity    = LOC / E             lines per person-month"]):
        g.add(f'<text x="70" y="{278 + i * 34}" font-size="16" font-family="Consolas, monospace" fill="{INK}" xml:space="preserve">{esc(line)}</text>')
    g.text(70, 430, "Intermediate COCOMO:  E = a × (KLOC)^b × EAF   (EAF = product of 15 cost-driver multipliers)",
           size=14, color=MUTED, anchor="start")

    # coefficient table
    g.rect(770, 210, 690, 250, fill="#fff", stroke=LINE, rx=10)
    g.text(800, 238, "Coefficients by project type", size=17, weight="700", anchor="start")
    cols = [800, 970, 1050, 1130, 1210, 1290]
    for x, h in zip(cols, ["Type", "a", "b", "c", "d", "a (intermed.)"]):
        g.text(x, 275, h, size=14, weight="700", anchor="start")
    g.add(f'<line x1="800" y1="288" x2="1430" y2="288" stroke="{LINE}"/>')
    inter = {"Organic": 3.2, "Semi-detached": 3.0, "Embedded": 2.8}
    for i, (m, a, b, c, d, *_r) in enumerate(res):
        y = 318 + i * 34
        for x, v in zip(cols, [m, f"{a}", f"{b}", f"{c}", f"{d}", f"{inter[m]}"]):
            g.text(x, y, v, size=15, anchor="start", weight="700" if (m == "Organic" and x == 800) else "400")
    g.text(800, 430, "Organic: small team, familiar problem · Semi-detached: mixed · Embedded: tight constraints",
           size=13, color=MUTED, anchor="start")

    # our calculation
    g.rect(40, 480, 1420, 250, fill=GREEN_BG, stroke=GREEN, rx=10)
    g.text(70, 510, "Our project, Basic COCOMO in ORGANIC mode (2-person student team, well-understood tools)",
           size=17, weight="700", anchor="start")
    o = res[0]
    lines = [f"E = 2.4 × (7.737)^1.05 = 2.4 × 8.570 = {o[5]:.2f} person-months",
             f"D = 2.5 × ({o[5]:.2f})^0.38 = {o[6]:.2f} months",
             f"P = {o[5]:.2f} / {o[6]:.2f} = {o[7]:.2f}  ≈ 3 people",
             f"Productivity = 7,737 / {o[5]:.2f} ≈ {7737 / o[5]:.0f} LOC per person-month"]
    for i, line in enumerate(lines):
        g.add(f'<text x="70" y="{552 + i * 36}" font-size="17" font-family="Consolas, monospace" fill="{INK}" xml:space="preserve">{esc(line)}</text>')
    g.text(900, 595, "Reading it: about 21 person-months of work,", size=15, anchor="start")
    g.text(900, 622, "i.e. ~3 people for ~8 months. Our 2-person team", size=15, anchor="start")
    g.text(900, 649, "fits this, given the model and data work were", size=15, anchor="start")
    g.text(900, 676, "spread over the semester.", size=15, anchor="start")

    # comparison chart (one measure: effort)
    g.rect(40, 750, 690, 310, fill="#fff", stroke=LINE, rx=10)
    g.text(70, 780, "Effort by project type (person-months)", size=17, weight="700", anchor="start")
    maxE = max(r[5] for r in res)
    colors = [GREEN, "#c98500", ORANGE]
    for i, r in enumerate(res):
        y = 820 + i * 74
        w = 290 * r[5] / maxE
        g.text(70, y + 18, r[0], size=15, anchor="start")
        g.rect(210, y, w, 34, fill=colors[i], stroke=colors[i], rx=4)
        g.text(220 + w, y + 18, f"{r[5]:.1f} PM · {r[6]:.1f} mo · {r[7]:.1f} people", size=14, anchor="start")
    g.text(70, 1040, "Same 7.7 KLOC: the stricter the project type, the more effort.", size=13, color=MUTED, anchor="start")

    # intermediate
    g.rect(770, 750, 690, 310, fill="#fff", stroke=LINE, rx=10)
    g.text(800, 780, "Intermediate COCOMO (organic, a = 3.2), cost drivers", size=17, weight="700", anchor="start")
    for i, (code, name, rating, v) in enumerate(drivers):
        y = 815 + i * 27
        g.text(800, y, code, size=14, weight="700", anchor="start")
        g.text(870, y, name, size=14, anchor="start")
        g.text(1120, y, rating, size=14, anchor="start")
        g.text(1200, y, f"{v:.2f}", size=14, anchor="start")
    g.text(800, 1012, "Other 8 drivers Nominal (1.00).", size=13, color=MUTED, anchor="start")
    g.text(800, 1040, f"EAF = {eaf:.3f}   →   E = 3.2 × 8.570 × {eaf:.3f} = {Ei:.1f} PM,   D = {Di:.1f} months",
           size=14, weight="700", anchor="start")

    g.rect(40, 1080, 1420, 230, fill=GREY_BG, stroke=LINE, rx=10)
    g.text(70, 1110, "Why these ratings", size=17, weight="700", anchor="start")
    notes = ["RELY High: a missed attack or wrong deployment is costly, hence the human review and gated retraining.",
             "DATA High: 1.7 million flows (about 1 GB raw).    CPLX High: deep learning + uncertainty routing + full web portal.",
             "AEXP Low: first intrusion-detection project for the team.    VIRT Low: stable Python / PyTorch / React stack.",
             "MODP, TOOL High: version control, automated tests (23), modern libraries and IDE.",
             "Values are estimates for the report; COCOMO predicts typical industry effort, not our actual hours."]
    for i, n in enumerate(notes):
        g.text(70, 1145 + i * 32, n, size=14, anchor="start")
    g.save("cocomo_estimation")


if __name__ == "__main__":
    use_case()
    activity()
    dfd0()
    dfd1()
    cocomo()
