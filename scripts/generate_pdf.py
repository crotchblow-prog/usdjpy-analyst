#!/usr/bin/env python3
"""
generate_pdf.py — Convert USD/JPY markdown reports to professional styled PDF.

Uses reportlab. Markdown → parsed elements → styled PDF with embedded charts,
colored signal badges, navy cover banner, and financial-report typography.

Usage:
    python3 scripts/generate_pdf.py <markdown_file> [--type daily|weekly]

Examples:
    python3 scripts/generate_pdf.py ./output/daily/2026-03-30.md
    python3 scripts/generate_pdf.py ./output/weekly/2026-03-28.md --type weekly
"""

import argparse
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Page Dimensions ─────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
M_TOP = 1.8 * cm
M_BOTTOM = 1.5 * cm
M_LEFT = 2 * cm
M_RIGHT = 2 * cm
CONTENT_W = PAGE_W - M_LEFT - M_RIGHT

# ── Colors ──────────────────────────────────────────────────────────────────

NAVY = "#1a2332"
C = lambda h: colors.HexColor(h)  # shorthand
C_NAVY = C(NAVY)
C_WHITE = colors.white
C_BODY = C("#333333")
C_H3 = C("#444444")
C_BORDER = C("#dee2e6")
C_ALT = C("#f8f9fa")
C_GREEN = C("#28a745")
C_RED = C("#dc3545")
C_GRAY = C("#6c757d")
C_ORANGE = C("#fd7e14")
C_YELLOW = C("#ffc107")
C_BULL_BG = C("#d4edda")
C_BEAR_BG = C("#f8d7da")
C_NEUT_BG = C("#e9ecef")
C_FOOTER = C("#888888")
C_MUTED = C("#a0aec0")
C_REC_BG = C("#fafbfc")
C_BULL_FG = C("#155724")
C_BEAR_FG = C("#721c24")
C_NEUT_FG = C("#495057")
C_CRIT_BG = C("#8b0000")

# Signal keywords → hex color (longest first to prevent partial matches)
SIGNAL_KW = [
    ("STRONG BULLISH", "#28a745"), ("MODERATE BULLISH", "#28a745"),
    ("STRONG BEARISH", "#dc3545"), ("MODERATE BEARISH", "#dc3545"),
    ("NEUTRAL / NO EDGE", "#6c757d"),
    ("Golden Cross", "#28a745"), ("Death Cross", "#dc3545"),
    ("Above cloud", "#28a745"), ("Below cloud", "#dc3545"),
    ("Inside cloud", "#6c757d"),
    ("Above price", "#28a745"), ("Below price", "#dc3545"),
    ("BULLISH", "#28a745"), ("Bullish", "#28a745"),
    ("BEARISH", "#dc3545"), ("Bearish", "#dc3545"),
    ("CONFIRMED", "#28a745"), ("DIVERGENCE", "#fd7e14"),
    ("WIDENING", "#28a745"), ("NARROWING", "#dc3545"), ("STABLE", "#6c757d"),
    ("BREAKDOWN", "#dc3545"), ("Breakdown", "#dc3545"), ("CROWDED", "#dc3545"),
    ("CRITICAL", "#dc3545"), ("ELEVATED", "#fd7e14"),
    ("RISK-ON", "#28a745"), ("RISK-OFF", "#dc3545"),
    ("TRANSITIONAL", "#fd7e14"), ("DECORRELATED", "#6c757d"),
    ("Overbought", "#fd7e14"), ("Oversold", "#28a745"),
    ("Steepening", "#fd7e14"), ("Flattening", "#28a745"),
    ("TAILWIND", "#28a745"),
    ("NEUTRAL", "#6c757d"), ("Neutral", "#6c757d"),
]
BOLD_SIGNALS = {"BREAKDOWN", "Breakdown", "CROWDED", "CRITICAL", "ELEVATED"}

# Page-break heading patterns
DAILY_BREAK_RE = re.compile(r"^0[1-7]\s")
WEEKLY_BREAK_RE = re.compile(r"^0[1-7]\s")


# ── Text Helpers ────────────────────────────────────────────────────────────

def escape_xml(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def apply_signal_colors(text):
    """Wrap signal keywords with colored <font> tags."""
    for kw, hx in SIGNAL_KW:
        pat = re.compile(r"(?<![a-zA-Z/])" + re.escape(kw) + r"(?![a-zA-Z])")
        if pat.search(text):
            bold = "<b>" if kw in BOLD_SIGNALS else ""
            boldc = "</b>" if kw in BOLD_SIGNALS else ""
            text = pat.sub(f'<font color="{hx}">{bold}{kw}{boldc}</font>', text, count=1)
    return text


def apply_inline(text):
    """Convert markdown bold/italic/code to reportlab XML."""
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier" size="8">\1</font>', text)
    text = text.replace("[x]", "\u2611").replace("[ ]", "\u2610")
    return text


def fmt(raw):
    """Full pipeline: escape → signal colors → inline formatting."""
    return apply_inline(apply_signal_colors(escape_xml(raw)))


# ── Color Helpers ───────────────────────────────────────────────────────────

def bias_colors(text):
    up = text.upper()
    if "BULL" in up: return C_GREEN, C_WHITE
    if "BEAR" in up: return C_RED, C_WHITE
    if "CAUTION" in up: return C_ORANGE, C_WHITE
    return C_GRAY, C_WHITE


def direction_bg(text):
    up = text.upper().strip()
    if "BULL" in up: return C_BULL_BG
    if "BEAR" in up: return C_BEAR_BG
    if up == "N/A": return C_WHITE
    return C_NEUT_BG


def direction_fg(text):
    up = text.upper().strip()
    if "BULL" in up: return C_BULL_FG
    if "BEAR" in up: return C_BEAR_FG
    if up == "N/A": return C("#adb5bd")
    return C_NEUT_FG


# ── Metadata Extraction ────────────────────────────────────────────────────

def extract_metadata(md):
    m = {}
    t = re.search(r"^#\s+(.+?)(?:\s+—\s+(.+))?$", md, re.MULTILINE)
    m["title"] = t.group(1).strip() if t else "USD/JPY Report"
    m["date"] = (t.group(2) or "").strip() if t else ""
    for key, pat in [
        ("bias", r"\*\*Bias:\*\*\s*(.+?)(?:\s*\*\*|$)"),
        ("score", r"\*\*Weighted Score:\*\*\s*(.+?)(?:\s*\*\*|$)"),
        ("conviction", r"\*\*Conviction:\*\*\s*(.+?)(?:\s*\*\*|$)"),
        ("modules", r"\*\*Available Modules:\*\*\s*(.+?)(?:\s*\*\*|$)"),
    ]:
        s = re.search(pat, md, re.MULTILINE)
        m[key] = s.group(1).strip() if s else ""
    # Weekly format: blockquote with > **NEUTRAL** | Conviction: **MEDIUM** | Score: **+1/+12**
    if not m["bias"]:
        bq = re.search(r">\s*\*\*(\w+)\*\*\s*\|", md)
        if bq:
            m["bias"] = bq.group(1).strip()
    if not m["conviction"]:
        cv = re.search(r"Conviction:\s*\*\*(.+?)\*\*", md)
        if cv:
            m["conviction"] = cv.group(1).strip()
    if not m["score"]:
        sc = re.search(r"Score:\s*\*\*(.+?)\*\*", md)
        if sc:
            m["score"] = sc.group(1).strip()
    if not m["modules"]:
        mo = re.search(r"(?:coverage|modules):\s*\*\*(.+?)\*\*", md, re.IGNORECASE)
        if mo:
            m["modules"] = mo.group(1).strip()
    return m


# ── Styles ──────────────────────────────────────────────────────────────────

def _styles():
    s = {}
    s["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5,
                                leading=13, textColor=C_BODY, spaceAfter=2)
    s["h2"] = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14,
                              leading=18, textColor=C_NAVY, spaceBefore=4, spaceAfter=3)
    s["h3"] = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11,
                              leading=14, textColor=C_H3, spaceBefore=4, spaceAfter=2)
    s["caption"] = ParagraphStyle("cap", fontName="Helvetica-Oblique", fontSize=8,
                                   textColor=C_GRAY, alignment=TA_CENTER, spaceAfter=6)
    s["italic"] = ParagraphStyle("ital", fontName="Helvetica-Oblique", fontSize=7.5,
                                  textColor=C_FOOTER, spaceAfter=2)
    s["cell"] = ParagraphStyle("cell", fontName="Helvetica", fontSize=9,
                                leading=12, textColor=C_BODY)
    s["cell_b"] = ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=9,
                                  leading=12, textColor=C_BODY)
    s["cell_r"] = ParagraphStyle("cellr", fontName="Helvetica", fontSize=9,
                                  leading=12, textColor=C_BODY, alignment=TA_RIGHT)
    s["cell_rb"] = ParagraphStyle("cellrb", fontName="Helvetica-Bold", fontSize=9,
                                   leading=12, textColor=C_BODY, alignment=TA_RIGHT)
    s["hdr"] = ParagraphStyle("hdr", fontName="Helvetica-Bold", fontSize=9,
                               leading=12, textColor=C_WHITE)
    s["rec"] = ParagraphStyle("rec", fontName="Helvetica", fontSize=9.5,
                               leading=14, textColor=C_BODY)
    return s


# ── Special Builders ────────────────────────────────────────────────────────

def make_banner(meta):
    """Dark navy cover banner with prominent bias pill badge, 60px tall."""
    ts = ParagraphStyle("bt", fontName="Helvetica-Bold", fontSize=18,
                         leading=22, textColor=C_WHITE)
    ds = ParagraphStyle("bd", fontName="Helvetica", fontSize=11,
                         leading=14, textColor=C_MUTED)

    bias = meta.get("bias", "NEUTRAL")
    bg, fg = bias_colors(bias)

    # Large bias pill badge — 16pt bold
    bs = ParagraphStyle("bb", fontName="Helvetica-Bold", fontSize=16,
                         leading=20, textColor=fg, alignment=TA_CENTER)
    badge = Table([[Paragraph(bias.upper(), bs)]], colWidths=[180])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    # Info text beside badge — white 10pt
    parts = [p for p in [
        f'Conviction: {meta["conviction"]}' if meta.get("conviction") else "",
        f'Score: {meta["score"]}' if meta.get("score") else "",
        f'{meta["modules"]} modules' if meta.get("modules") else "",
    ] if p]
    info = Paragraph("&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts),
                      ParagraphStyle("bi", fontName="Helvetica", fontSize=10,
                                      leading=14, textColor=C_WHITE))

    badge_row = Table([[badge, info]], colWidths=[190, CONTENT_W - 200])
    badge_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (1, 0), (1, 0), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    banner = Table([
        [Paragraph(meta.get("title", ""), ts)],
        [Paragraph(meta.get("date", ""), ds)],
        [Spacer(1, 4)],
        [badge_row],
    ], colWidths=[CONTENT_W])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_NAVY),
        ("TOPPADDING", (0, 0), (0, 0), 14),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 1), (0, 1), 2),
        ("TOPPADDING", (0, 2), (0, 2), 0),
        ("BOTTOMPADDING", (0, 2), (0, 2), 0),
    ]))
    return banner


def make_h2_border(text, styles):
    """H2 heading with thin bottom border."""
    t = Table([[Paragraph(text, styles["h2"])]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, C_BORDER),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    t._h2_text = re.sub(r"<[^>]+>", "", text)
    return t


def make_rec_box(parts, bias):
    """Recommendation box with 4px colored left border + #fafbfc background."""
    styles = _styles()
    border_color = bias_colors(bias)[0]
    rows = [[Paragraph(p, styles["rec"])] for p in parts]
    t = Table(rows, colWidths=[CONTENT_W - 24])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_REC_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 4, border_color),
        ("TOPPADDING", (0, 0), (0, 0), 16),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
    ]))
    return t


def make_assessment(meta):
    """Overall assessment — same banner-style colored pill as cover."""
    bias = meta.get("bias", "NEUTRAL")
    bg, fg = bias_colors(bias)

    bs = ParagraphStyle("ab", fontName="Helvetica-Bold", fontSize=13,
                         leading=17, textColor=fg, alignment=TA_CENTER)
    badge = Table([[Paragraph(bias.upper(), bs)]], colWidths=[160])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    parts = []
    for key, label in [("conviction", "Conviction"), ("score", "Score"), ("modules", "Modules")]:
        v = meta.get(key, "")
        if v:
            parts.append(f"<b>{label}:</b> {escape_xml(v)}")
    info = Paragraph("&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts),
                      ParagraphStyle("ai", fontName="Helvetica", fontSize=10,
                                      leading=14, textColor=C_BODY))

    row = Table([[badge, info]], colWidths=[170, CONTENT_W - 180])
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return row


def _risk_border_color(level):
    """Return left-border color for risk alert level."""
    if level in ("CRITICAL", "ELEVATED"):
        return C_RED
    if level == "YES":
        return C_ORANGE
    if level == "NO":
        return C_GREEN
    return C_GRAY


def make_risk_alert(raw):
    """Styled risk alert row with colored pill badge + 4px colored left border."""
    styles = _styles()
    clean = raw.replace("**", "")

    level, lbg, lfg = None, C_NEUT_BG, C_GRAY
    for kw, bg, fg in [
        ("CRITICAL", C_CRIT_BG, C_WHITE), ("ELEVATED", C_RED, C_WHITE),
        ("YES", C_ORANGE, C_WHITE),
        ("NO", C_GREEN, C_WHITE),
        ("UNKNOWN", C_NEUT_BG, C_GRAY), ("N/A", C_NEUT_BG, C_GRAY),
    ]:
        if kw in clean:
            level, lbg, lfg = kw, bg, fg
            break

    if not level:
        return Paragraph(f"\u2022 {fmt(raw)}", styles["body"])

    # Pill badge
    bs = ParagraphStyle("rab", fontName="Helvetica-Bold", fontSize=8,
                         leading=11, textColor=lfg, alignment=TA_CENTER)
    badge = Table([[Paragraph(level, bs)]], colWidths=[70])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), lbg),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROUNDEDCORNERS", [3, 3, 3, 3]),
    ]))

    # Detail: remove checkbox + level keyword
    detail = re.sub(r"^\[([x ])\]\s*", "", clean)
    detail = re.sub(rf":\s*{re.escape(level)}", "", detail, count=1)
    detail = detail.strip()
    if detail.startswith("—"):
        detail = detail[1:].strip()

    border_c = _risk_border_color(level)
    row = Table([[badge, Paragraph(fmt(detail), styles["body"])]],
                 colWidths=[75, CONTENT_W - 85])
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 4, border_c),
    ]))
    return row


# ── Table Builder ───────────────────────────────────────────────────────────

def parse_table(lines):
    rows = []
    for line in lines:
        line = line.strip().strip("|")
        cells = [c.strip() for c in line.split("|")]
        rows.append(cells)
    return [r for r in rows if not all(re.match(r"^[-:]+$", c) for c in r)]


def _is_numeric(val):
    val = val.strip()
    if not val or val == "\u2014" or val == "—":
        return True
    return bool(re.match(r"^[+-]?\d", val))


def _col_widths(ncols, content_w, context, headers=None):
    if context in ("session_l", "session_r"):
        return [content_w * 0.55, content_w * 0.45]
    if ncols == 2:
        return [content_w * 0.45, content_w * 0.55]
    if ncols == 3:
        return [content_w * 0.28, content_w * 0.36, content_w * 0.36]
    if ncols == 4:
        return [content_w * 0.22, content_w * 0.26, content_w * 0.26, content_w * 0.26]
    if ncols == 5:
        return [content_w * 0.18] + [content_w * 0.205] * 4
    if ncols >= 6:
        # Checklist: first col is "#" (narrow)
        if context == "checklist" or (headers and headers[0].strip() == "#"):
            return [content_w * 0.04, content_w * 0.14, content_w * 0.22,
                    content_w * 0.12, content_w * 0.12, content_w * 0.36][:ncols]
        # Generic 6-col: balanced widths
        return [content_w / ncols] * ncols
    return [content_w / ncols] * ncols


def build_table(rows, content_w, context=None):
    """Build a styled table with signal colors and context-aware formatting."""
    if not rows or not rows[0]:
        return None

    styles = _styles()
    ncols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < ncols:
            r.append("")

    header = rows[0]

    # Detect special columns
    val_cols = set()
    dir_col = conf_col = impact_col = None
    for ci, h in enumerate(header):
        hl = h.lower().strip()
        if hl in ("current", "value", "signal"):
            val_cols.add(ci)
        if hl == "direction":
            dir_col = ci
        if hl == "confidence":
            conf_col = ci
        if hl == "impact":
            impact_col = ci

    # Detect numeric columns
    num_cols = set()
    for ci in range(1, ncols):
        vals = [rows[ri][ci] for ri in range(1, len(rows)) if ci < len(rows[ri])]
        if vals and sum(1 for v in vals if _is_numeric(v)) / len(vals) > 0.5:
            num_cols.add(ci)

    # Build cell paragraphs
    data = []
    for ri, row in enumerate(rows):
        styled = []
        for ci, cell in enumerate(row):
            ct = apply_signal_colors(escape_xml(cell))
            ct = apply_inline(ct)
            if ri == 0:
                styled.append(Paragraph(ct, styles["hdr"]))
            else:
                # Pick style
                if ci in val_cols and ci in num_cols:
                    st = styles["cell_rb"]
                elif ci in num_cols:
                    st = styles["cell_r"]
                elif ci in val_cols:
                    st = styles["cell_b"]
                else:
                    st = styles["cell"]
                # Checklist: direction cell text color
                if context == "checklist" and ci == dir_col:
                    fg = direction_fg(cell)
                    st = ParagraphStyle(f"cd{ri}{ci}", parent=st,
                                         textColor=fg, fontName="Helvetica-Bold")
                # Checklist confidence styling
                elif context == "checklist" and ci == conf_col:
                    cv = cell.strip().upper()
                    if cv in ("LOW", "L"):
                        st = ParagraphStyle(f"cm{ri}", parent=st,
                                             textColor=C("#adb5bd"))
                    elif cv in ("HIGH", "H"):
                        st = ParagraphStyle(f"ch{ri}", parent=st,
                                             fontName="Helvetica-Bold")
                styled.append(Paragraph(ct, st))
        data.append(styled)

    cw = _col_widths(ncols, content_w, context, headers=header)
    tbl = Table(data, colWidths=cw, repeatRows=1)

    sc = [
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for ri in range(1, len(data)):
        sc.append(("BACKGROUND", (0, ri), (-1, ri), C_ALT if ri % 2 == 0 else C_WHITE))

    # Checklist: colored direction backgrounds
    if context == "checklist" and dir_col is not None:
        for ri in range(1, len(rows)):
            d = rows[ri][dir_col].strip() if dir_col < len(rows[ri]) else ""
            sc.append(("BACKGROUND", (dir_col, ri), (dir_col, ri), direction_bg(d)))

    # Calendar: yellow left border for HIGH impact
    if context == "calendar" and impact_col is not None:
        for ri in range(1, len(rows)):
            imp = rows[ri][impact_col].strip() if impact_col < len(rows[ri]) else ""
            if imp.upper() == "HIGH":
                sc.append(("LINEBEFORE", (0, ri), (0, ri), 3, C_YELLOW))

    tbl.setStyle(TableStyle(sc))
    return tbl


def make_session_2col(rows, content_w):
    """Split Session Context table into two side-by-side mini-tables."""
    if len(rows) < 2:
        return build_table(rows, content_w)
    header = rows[0]
    data = rows[1:]
    mid = (len(data) + 1) // 2
    hw = content_w * 0.48
    left = build_table([header] + data[:mid], hw, "session_l")
    right = build_table([header] + data[mid:], hw, "session_r")
    w = Table([[left, right]], colWidths=[content_w * 0.49, content_w * 0.49])
    w.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return w


# ── Markdown Parser ─────────────────────────────────────────────────────────

def parse_markdown(md_text, base_dir, report_type, meta):
    styles = _styles()
    elements = []
    lines = md_text.split("\n")
    i = 0

    cur_h2 = ""
    cur_h3 = ""
    in_rec = False
    rec_parts = []
    in_risk = False

    def flush_rec():
        nonlocal in_rec, rec_parts
        if rec_parts:
            elements.append(("rec", make_rec_box(rec_parts, meta.get("bias", ""))))
            rec_parts = []
        in_rec = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
            elements.append(("spacer", Spacer(1, 2 * mm)))
            i += 1
            continue

        # H1 → Banner
        if stripped.startswith("# ") and not stripped.startswith("## "):
            elements.append(("banner", make_banner(meta)))
            elements.append(("spacer", Spacer(1, 4 * mm)))
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            flush_rec()
            heading = stripped[4:].strip()
            cur_h3 = heading
            in_risk = "Risk Alert" in heading

            if heading == "Recommendation":
                in_rec = True
                elements.append(("h3", Paragraph(fmt(heading), styles["h3"])))
                i += 1
                continue

            elements.append(("h3", Paragraph(fmt(heading), styles["h3"])))
            i += 1
            continue

        # H2
        if stripped.startswith("## "):
            flush_rec()
            heading = stripped[3:].strip()
            cur_h2 = heading
            cur_h3 = ""
            in_risk = False
            elements.append(("h2", make_h2_border(fmt(heading), styles)))
            i += 1
            continue

        # Image
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if m:
            alt_text = m.group(1)
            img_path = m.group(2)
            if not os.path.isabs(img_path):
                img_path = os.path.join(base_dir, img_path)
            if os.path.exists(img_path):
                ir = ImageReader(img_path)
                iw, ih = ir.getSize()
                aspect = ih / iw
                scale = 0.85 if report_type == "weekly" else 0.9
                max_frac = 0.35 if report_type == "weekly" else 0.42
                dw = CONTENT_W * scale
                dh = dw * aspect
                max_h = (PAGE_H - M_TOP - M_BOTTOM) * max_frac
                if dh > max_h:
                    dh = max_h
                    dw = dh / aspect
                img = Image(img_path, width=dw, height=dh)
                img.hAlign = "CENTER"

                # Chart container with border + background
                ct = Table([[img]], colWidths=[dw + 16])
                ct.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), C_ALT),
                    ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]))
                ct.hAlign = "CENTER"
                elements.append(("image", ct))
                if alt_text:
                    elements.append(("caption", Paragraph(alt_text, styles["caption"])))
            i += 1
            continue

        # Table
        if stripped.startswith("|"):
            tl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tl.append(lines[i])
                i += 1
            rows = parse_table(tl)

            ctx = None
            if "Session Context" in cur_h2:
                ctx = "session"
            elif "Signal Grid" in cur_h3:
                ctx = "checklist"
            elif "Calendar" in cur_h2:
                ctx = "calendar"

            if ctx == "session" and len(rows) > 1 and len(rows[0]) == 2:
                tbl = make_session_2col(rows, CONTENT_W)
            else:
                tbl = build_table(rows, CONTENT_W, context=ctx)
            if tbl:
                elements.append(("table", tbl))
            continue

        # Blockquote
        if stripped.startswith("> "):
            ql = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                ql.append(lines[i].strip().lstrip("> "))
                i += 1
            text = fmt(" ".join(ql))
            qs = ParagraphStyle("bq", parent=styles["body"],
                                 backColor=C("#eef2f7"), borderWidth=2,
                                 borderColor=C_NAVY, borderPadding=6, leftIndent=12)
            elements.append(("blockquote", Paragraph(text, qs)))
            continue

        # Bullet
        if re.match(r"^[-*]\s", stripped):
            bt = stripped[2:]
            if in_risk:
                elements.append(("risk", make_risk_alert(bt)))
            else:
                elements.append(("body", Paragraph(f"\u2022 {fmt(bt)}", styles["body"])))
            i += 1
            continue

        # Italic line
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            elements.append(("italic", Paragraph(apply_inline(escape_xml(stripped)),
                                                   styles["italic"])))
            i += 1
            continue

        # Paragraph
        pl = []
        while i < len(lines):
            l = lines[i].strip()
            if (not l or l.startswith("#") or l.startswith("|") or l.startswith(">")
                    or (l.startswith("!") and re.match(r"!\[", l))
                    or re.match(r"^-{3,}$", l) or re.match(r"^\*{3,}$", l)
                    or re.match(r"^[-*]\s", l)):
                break
            pl.append(l)
            i += 1

        if pl:
            raw = " ".join(pl)
            # Detect overall assessment line
            if "Bias:" in raw and "Weighted Score:" in raw and cur_h2.startswith("07"):
                elements.append(("assessment", make_assessment(meta)))
            elif in_rec:
                rec_parts.append(fmt(raw))
            else:
                elements.append(("body", Paragraph(fmt(raw), styles["body"])))

    flush_rec()
    return elements


# ── Page Template ───────────────────────────────────────────────────────────

class ReportTemplate:
    def __init__(self, title, date):
        self.title = title
        self.date = date

    def on_page(self, canvas, doc):
        canvas.saveState()
        # Header: navy line + title/date
        y = PAGE_H - M_TOP + 8
        canvas.setStrokeColor(C_NAVY)
        canvas.setLineWidth(0.75)
        canvas.line(M_LEFT, y, PAGE_W - M_RIGHT, y)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_NAVY)
        canvas.drawString(M_LEFT, y + 4, self.title)
        canvas.drawRightString(PAGE_W - M_RIGHT, y + 4, self.date)
        # Footer: navy line + sources/page
        y = M_BOTTOM - 4
        canvas.setStrokeColor(C_NAVY)
        canvas.line(M_LEFT, y, PAGE_W - M_RIGHT, y)
        canvas.setFont("Helvetica-Oblique", 7.5)
        canvas.setFillColor(C_FOOTER)
        canvas.drawString(M_LEFT, y - 10, "Data: FRED, Yahoo Finance, MOF Japan, CFTC")
        canvas.drawRightString(PAGE_W - M_RIGHT, y - 10, f"Page {doc.page}")
        canvas.restoreState()

    def on_first_page(self, canvas, doc):
        canvas.saveState()
        y = M_BOTTOM - 4
        canvas.setStrokeColor(C_NAVY)
        canvas.setLineWidth(0.75)
        canvas.line(M_LEFT, y, PAGE_W - M_RIGHT, y)
        canvas.setFont("Helvetica-Oblique", 7.5)
        canvas.setFillColor(C_FOOTER)
        canvas.drawString(M_LEFT, y - 10, "Data: FRED, Yahoo Finance, MOF Japan, CFTC")
        canvas.drawRightString(PAGE_W - M_RIGHT, y - 10, f"Page {doc.page}")
        canvas.restoreState()


# ── Main Conversion ─────────────────────────────────────────────────────────

def markdown_to_pdf(md_path, report_type="daily"):
    md_path = os.path.abspath(md_path)
    base_dir = os.path.dirname(md_path)
    pdf_path = os.path.splitext(md_path)[0] + ".pdf"

    with open(md_path, "r") as f:
        md_text = f.read()

    meta = extract_metadata(md_text)
    parsed = parse_markdown(md_text, base_dir, report_type, meta)

    break_re = DAILY_BREAK_RE if report_type == "daily" else WEEKLY_BREAK_RE
    # Conditional break: only start new page if <30% of usable height remains
    usable_h = PAGE_H - (M_TOP + 0.5 * cm) - (M_BOTTOM + 0.3 * cm)
    cond_break = CondPageBreak(usable_h * 0.30)

    flowables = []
    section = []
    first_h2 = False

    def flush():
        if not section:
            return
        keep, rest = [], []
        found = False
        for item in section:
            if not found:
                keep.append(item)
                if isinstance(item, Table):
                    found = True
            else:
                rest.append(item)
        if keep and len(keep) <= 6:
            flowables.append(KeepTogether(keep))
        else:
            flowables.extend(keep)
        flowables.extend(rest)

    for etype, fl in parsed:
        if etype == "h2":
            flush()
            section = []
            h2_text = getattr(fl, "_h2_text", "")
            if first_h2 and break_re.search(h2_text):
                flowables.append(CondPageBreak(usable_h * 0.30))
            first_h2 = True
            section.append(fl)
        else:
            section.append(fl)

    flush()

    tmpl = ReportTemplate(meta.get("title", "USD/JPY Report"), meta.get("date", ""))
    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        leftMargin=M_LEFT, rightMargin=M_RIGHT,
        topMargin=M_TOP + 0.5 * cm,
        bottomMargin=M_BOTTOM + 0.3 * cm,
    )
    doc.build(flowables, onFirstPage=tmpl.on_first_page, onLaterPages=tmpl.on_page)
    return pdf_path


# ══════════════════════════════════════════════════════════════════════════════
# SMC PDF — Custom layout for Module 08 Smart Money Concepts reports
# ══════════════════════════════════════════════════════════════════════════════

# ── Unified SMC Color Palette ────────────────────────────────────────────────
S_DARK      = C("#2D3436")   # Hero background, primary text
S_HERO_ALT  = C("#1B2838")   # Alternate hero bg
S_TEXT       = C("#2D3436")   # Primary text
S_TEXT2      = C("#636E72")   # Secondary text
S_BULL       = C("#27AE60")   # Bullish / long / confirmed
S_BEAR       = C("#E74C3C")   # Bearish / short / stop
S_NEUTRAL    = C("#95A5A6")   # Transitional / neutral
S_INTV       = C("#F39C12")   # Intervention / amber / warning
S_ROW_ALT    = C("#F8F9FA")   # Table alternating row
S_DIVIDER    = C("#DFE6E9")   # Borders, dividers
S_ENTRY_BG   = C("#F0F4F8")   # Entry plan background
S_TARGET     = C("#2980B9")   # Target / info blue

def _smc_grade_color(grade):
    if grade in ("A+", "A"):
        return S_BULL, C_WHITE
    if grade == "B":
        return S_INTV, S_DARK
    return S_BEAR, C_WHITE


def parse_smc_data(md_text):
    """Extract structured data from SMC markdown report."""
    d = {}

    # Direction + confidence
    m = re.search(r"\*\*Direction:\*\*\s*(\w+)", md_text)
    d["direction"] = m.group(1) if m else "NEUTRAL"
    m = re.search(r"\*\*Confidence:\*\*\s*(\w+)", md_text)
    d["confidence"] = m.group(1) if m else "LOW"

    # Report date
    m = re.search(r"\*\*Report Date:\*\*\s*([\d-]+)", md_text)
    d["report_date"] = m.group(1) if m else ""

    # 4H structure
    m = re.search(r"\*\*Market Structure:\*\*\s*(\w+)", md_text)
    d["structure_4h"] = m.group(1) if m else "UNKNOWN"

    # Last BOS/ChoCH
    m = re.search(r"\*\*Last BOS/ChoCH:\*\*\s*(.+?)$", md_text, re.MULTILINE)
    d["last_event"] = m.group(1).strip() if m else ""

    # Premium/Discount
    m = re.search(r"\*\*Premium/Discount:\*\*.*?\*\*(.+?)\*\*", md_text)
    d["pd_zone"] = m.group(1) if m else ""
    m = re.search(r"Price at ([\d.]+)", md_text)
    d["current_price"] = float(m.group(1)) if m else 0

    # Range
    m = re.search(r"\*\*Range:\*\*\s*([\d.]+)\s*—\s*([\d.]+)", md_text)
    d["range_low"] = float(m.group(1)) if m else 0
    d["range_high"] = float(m.group(2)) if m else 0

    # OTE
    m = re.search(r"\*\*OTE Zone:\*\*\s*([\d.]+)\s*—\s*([\d.]+)", md_text)
    d["ote_low"] = float(m.group(1)) if m else 0
    d["ote_high"] = float(m.group(2)) if m else 0

    # MTF alignment table
    d["mtf"] = []
    for m in re.finditer(r"\|\s*(4H|1H|15M|5M)\s*\|\s*(\w+)\s*\|", md_text):
        d["mtf"].append((m.group(1), m.group(2)))

    # Scenario
    m = re.search(r"\*\*Scenario (\w):\*\*\s*(.+?)$", md_text, re.MULTILINE)
    d["scenario_id"] = m.group(1) if m else ""
    d["scenario_name"] = m.group(2).strip() if m else ""
    m = re.search(r"\*\*Rationale:\*\*\s*(.+?)$", md_text, re.MULTILINE)
    d["scenario_rationale"] = m.group(1).strip() if m else ""
    m = re.search(r"\*\*Bias Alignment:\*\*\s*(.+?)$", md_text, re.MULTILINE)
    d["bias_alignment"] = m.group(1).strip() if m else ""

    # Entry zone
    m = re.search(r"\*\*Zone Type:\*\*\s*(.+?)$", md_text, re.MULTILINE)
    d["zone_type"] = m.group(1).strip() if m else ""
    m = re.search(r"\*\*Zone Range:\*\*\s*([\d.]+)\s*—\s*([\d.]+)", md_text)
    d["zone_bottom"] = float(m.group(1)) if m else None
    d["zone_top"] = float(m.group(2)) if m else None
    m = re.search(r"\*\*Distance from Current Price:\*\*\s*(\d+)", md_text)
    d["zone_distance"] = int(m.group(1)) if m else None

    # Confirmation
    m = re.search(r"### Confirmation.*?\n\n\*\*Status:\*\*\s*(\w+)", md_text, re.DOTALL)
    d["confirmation"] = m.group(1) if m else "PENDING"
    m = re.search(r"\*\*Detail:\*\*\s*(.+?)$", md_text, re.MULTILINE)
    d["confirmation_detail"] = m.group(1).strip() if m else ""

    # Entry plan
    d["entry"] = d["stop"] = d["t1_price"] = d["t2_price"] = None
    d["risk_pips"] = d["t1_rr"] = d["t2_rr"] = 0
    d["t1_type"] = d["t2_type"] = ""
    m = re.search(r"\|\s*Entry\s*\|\s*([\d.]+)", md_text)
    if m:
        d["entry"] = float(m.group(1))
    m = re.search(r"\|\s*Stop Loss\s*\|\s*([\d.]+).*?(\d+)\s*pips", md_text)
    if m:
        d["stop"] = float(m.group(1))
        d["risk_pips"] = int(m.group(2))
    m = re.search(r"\|\s*Target 1\s*\|\s*([\d.]+)\s*\(([^)]*)\).*?1:([\d.]+)", md_text)
    if m:
        d["t1_price"] = float(m.group(1))
        d["t1_type"] = m.group(2)
        d["t1_rr"] = float(m.group(3))
    m = re.search(r"\|\s*Target 2\s*\|\s*([\d.]+)\s*\(([^)]*)\).*?1:([\d.]+)", md_text)
    if m:
        d["t2_price"] = float(m.group(1))
        d["t2_type"] = m.group(2)
        d["t2_rr"] = float(m.group(3))

    # Confluence
    m = re.search(r"\*\*Confluence Score:\*\*\s*([\d.]+)\s*.*?Grade\s*\*\*(\w\+?)\*\*", md_text)
    d["confluence_score"] = float(m.group(1)) if m else 0
    d["grade"] = m.group(2) if m else "C"
    d["scoring_details"] = re.findall(r"^- (.+)$", md_text, re.MULTILINE)

    # Risk alerts
    d["risk_alerts"] = []
    in_risk = False
    for line in md_text.split("\n"):
        if "**Risk Alerts:**" in line:
            in_risk = True
            continue
        if in_risk:
            if line.strip().startswith("- ") and line.strip() != "- None":
                d["risk_alerts"].append(line.strip()[2:])
            elif not line.strip().startswith("-"):
                in_risk = False

    # Session plan
    m = re.search(r"\*\*Primary Session:\*\*\s*(.+?)$", md_text, re.MULTILINE)
    d["session_primary"] = m.group(1).strip() if m else ""
    d["sessions"] = {}
    for label in ["Tokyo", "London", "New York"]:
        m = re.search(rf"\*\*{label}\s*\([^)]+\):\*\*\s*(.+?)$", md_text, re.MULTILINE)
        if m:
            d["sessions"][label] = m.group(1).strip()

    # Invalidation
    d["invalidation"] = []
    in_inv = False
    for line in md_text.split("\n"):
        if "### Invalidation" in line:
            in_inv = True
            continue
        if in_inv:
            if line.strip().startswith("- "):
                d["invalidation"].append(line.strip()[2:])
            elif line.strip().startswith("---"):
                in_inv = False

    # Active zones — parse the full table
    d["active_zones"] = []
    zone_pat = re.compile(
        r"\|\s*(\w+)\s*\|\s*(.+?)\s*\|\s*([\d.]+-[\d.]+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|"
    )
    in_zones = False
    for line in md_text.split("\n"):
        if "### Active Zones" in line:
            in_zones = True
            continue
        if in_zones and line.strip().startswith("---"):
            in_zones = False
            continue
        if in_zones:
            m = zone_pat.match(line.strip())
            if m:
                lo, hi = m.group(3).split("-")
                d["active_zones"].append({
                    "tf": m.group(1), "type": m.group(2).strip(),
                    "low": float(lo), "high": float(hi),
                    "dir": m.group(4), "status": m.group(5),
                })

    # Liquidity levels
    d["liquidity"] = []
    liq_pat = re.compile(r"\|\s*([\d.]+)\s*\|\s*(\w+)\s*\|\s*(.+?)\s*\|")
    in_liq = False
    for line in md_text.split("\n"):
        if "### Key Liquidity" in line:
            in_liq = True
            continue
        if in_liq and line.strip().startswith("---"):
            in_liq = False
            continue
        if in_liq:
            m = liq_pat.match(line.strip())
            if m:
                d["liquidity"].append({
                    "price": float(m.group(1)),
                    "type": m.group(2),
                    "sig": m.group(3).strip(),
                })

    # Chart path — match the entry chart specifically (not playbook)
    m = re.search(r"!\[SMC Entry Chart\]\((.+?)\)", md_text)
    if not m:
        # Fallback: match any smc_entry_* image
        m = re.search(r"!\[.*?\]\((smc_entry_[^)]+)\)", md_text)
    d["chart_filename"] = m.group(1) if m else None

    # Playbook
    d["playbook"] = parse_playbook_data(md_text)
    m_pb = re.search(r"!\[Playbook\]\((.+?)\)", md_text)
    d["playbook_chart_filename"] = m_pb.group(1) if m_pb else None

    return d


def parse_playbook_data(md_text):
    """Extract playbook scenarios from markdown."""
    pb = {}

    # Check if section exists
    if "### Next 24h Playbook" not in md_text:
        return pb

    # Extract generated_at
    m = re.search(r"> Generated at (.+?) —", md_text)
    pb["generated_at"] = m.group(1).strip() if m else ""

    # Extract each scenario
    for label, key in [("Primary", "primary"), ("Alternative", "alternative"),
                        ("Tail Risk", "tail_risk")]:
        pattern = rf"#### {label}: (.+?) \((\d+)%\)"
        m = re.search(pattern, md_text)
        if not m:
            continue
        name = m.group(1)
        prob = m.group(2)

        # Find session lines and metadata between this header and the next #### or ###
        header_pos = m.end()
        next_section = re.search(r"\n(?:####|###) ", md_text[header_pos:])
        section_end = header_pos + next_section.start() if next_section else len(md_text)
        section_text = md_text[header_pos:section_end]

        sessions = {}
        for sess in ["Tokyo", "London", "New York"]:
            sm = re.search(rf"\*\*{sess}:\*\*\s*(.+?)$", section_text, re.MULTILINE)
            if sm:
                sessions[sess] = sm.group(1).strip()

        action = ""
        am = re.search(r"\*\*Action:\*\*\s*(.+?)$", section_text, re.MULTILINE)
        if am:
            action = am.group(1).strip()

        key_level = ""
        km = re.search(r"\*\*Key Level:\*\*\s*(.+?)(?:\s*\||\s*$)", section_text, re.MULTILINE)
        if km:
            key_level = km.group(1).strip()

        trigger = ""
        tm = re.search(r"\*\*Trigger:\*\*\s*(.+?)$", section_text, re.MULTILINE)
        if tm:
            trigger = tm.group(1).strip()

        invalidation = ""
        im = re.search(r"\*\*Invalidation:\*\*\s*(.+?)$", section_text, re.MULTILINE)
        if im:
            invalidation = im.group(1).strip()

        pb[key] = {
            "name": name,
            "probability": prob,
            "sessions": sessions,
            "action": action,
            "key_level": key_level,
            "trigger": trigger,
            "invalidation": invalidation,
        }

    return pb


def detect_contradictions(sd):
    """Detect logical contradictions in the SMC analysis."""
    warnings = []
    direction = sd["direction"]

    if direction == "LONG" and "PREMIUM" in sd.get("pd_zone", "").upper():
        warnings.append(
            f"LONG entry in {sd['pd_zone']} zone — price is in a strong short area"
        )
    elif direction == "SHORT" and "DISCOUNT" in sd.get("pd_zone", "").upper():
        warnings.append(
            f"SHORT entry in {sd['pd_zone']} zone — price is in a strong long area"
        )

    if direction == "LONG" and sd.get("structure_4h") in ("BEARISH", "TRANSITIONAL"):
        warnings.append(
            f"LONG entry but 4H structure is {sd['structure_4h']} — trend not confirmed"
        )
    elif direction == "SHORT" and sd.get("structure_4h") in ("BULLISH", "TRANSITIONAL"):
        warnings.append(
            f"SHORT entry but 4H structure is {sd['structure_4h']} — trend not confirmed"
        )

    ba = sd.get("bias_alignment", "")
    if "No" in ba and sd.get("entry") is not None:
        warnings.append(f"Bias alignment is \"{ba}\" — entry conflicts with scenario")

    if sd.get("confirmation") == "PENDING":
        warnings.append("PENDING — not active until 15M confirms")

    return warnings


def make_smc_hero(sd, contradictions):
    """Trading-card hero block: dark bg, direction, prices, grade, status."""
    grade = sd.get("grade", "C")
    direction = sd.get("direction", "NEUTRAL")
    is_pending = sd.get("confirmation") == "PENDING"
    is_weak = grade == "C" or len(contradictions) >= 3

    bg = S_DARK
    text_c = C_WHITE
    muted_c = C("#b2bec3") if not is_pending else C("#636E72")

    # Row 1: Direction arrow (28pt) + Grade badge + Status badge
    arrow = "\u25b2" if direction == "LONG" else "\u25bc" if direction == "SHORT" else "\u25c6"
    dir_s = ParagraphStyle("hd", fontName="Helvetica-Bold", fontSize=28,
                            leading=34, textColor=text_c)

    # Grade: large rounded square
    g_bg, g_fg = _smc_grade_color(grade)
    grade_s = ParagraphStyle("hg", fontName="Helvetica-Bold", fontSize=20,
                              leading=24, textColor=g_fg, alignment=TA_CENTER)
    grade_cell = Table([[Paragraph(grade, grade_s)]], colWidths=[44], rowHeights=[40])
    grade_cell.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), g_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))

    # Status badge: outlined for NOT ACTIVE, solid for CONFIRMED
    conf = sd.get("confirmation", "PENDING")
    if conf == "CONFIRMED":
        sb_bg, sb_fg, sb_border = S_BULL, C_WHITE, S_BULL
    else:
        sb_bg, sb_fg, sb_border = bg, S_BEAR, S_BEAR  # outlined red
    conf_label = "NOT ACTIVE" if is_pending else conf
    sb_s = ParagraphStyle("hs", fontName="Helvetica-Bold", fontSize=9,
                           leading=12, textColor=sb_fg, alignment=TA_CENTER)
    status_cell = Table([[Paragraph(conf_label, sb_s)]], colWidths=[90])
    status_cell.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), sb_bg),
        ("BOX", (0, 0), (-1, -1), 1.5, sb_border),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    row1 = Table([[Paragraph(f"{arrow} {direction}", dir_s), grade_cell, status_cell]],
                  colWidths=[CONTENT_W - 160, 56, 104])
    row1.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # Row 2: Entry | Stop | T1 in 18pt, evenly spaced
    price_parts = []
    if sd.get("entry"):
        price_parts.append(f"Entry {sd['entry']:.2f}")
    if sd.get("stop"):
        price_parts.append(f"Stop {sd['stop']:.2f}")
    if sd.get("t1_price"):
        price_parts.append(f"T1 {sd['t1_price']:.2f}")
    price_text = "&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;".join(price_parts) if price_parts else "No entry plan"
    price_s = ParagraphStyle("hp", fontName="Helvetica-Bold", fontSize=18,
                              leading=24, textColor=text_c if not is_pending else muted_c)

    # Row 3: Verdict line in 11pt light gray
    verdict_parts = [f"{grade}-grade {direction.lower()}"]
    if sd.get("entry"):
        verdict_parts[0] += f" from {sd['entry']:.2f}"
    if sd.get("risk_pips"):
        verdict_parts.append(f"{sd['risk_pips']}pip risk")
    if sd.get("t1_rr"):
        verdict_parts.append(f"{sd['t1_rr']:.1f}R to first target")
    verdict = ", ".join(verdict_parts)
    if is_weak:
        verdict = f'<font color="#E74C3C">WEAK SETUP \u2014 CONSIDER SKIPPING</font>&nbsp;&nbsp;|&nbsp;&nbsp;' + verdict
    verdict_s = ParagraphStyle("hv", fontName="Helvetica", fontSize=11,
                                leading=14, textColor=muted_c)

    hero = Table([
        [row1],
        [Paragraph(price_text, price_s)],
        [Paragraph(verdict, verdict_s)],
    ], colWidths=[CONTENT_W])
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("TOPPADDING", (0, 0), (0, 0), 16),
        ("TOPPADDING", (0, 1), (0, 1), 6),
        ("TOPPADDING", (0, 2), (0, 2), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return hero


def make_warning_box(contradictions):
    """Single warning container with left red border and bullet points."""
    if not contradictions:
        return []
    bullet_lines = "".join(
        f'<br/>\u26a0 {escape_xml(w)}' for w in contradictions
    )
    # Strip leading <br/>
    bullet_lines = bullet_lines[5:]
    ws = ParagraphStyle("wb", fontName="Helvetica", fontSize=9,
                         leading=13, textColor=S_BEAR)
    t = Table([[Paragraph(bullet_lines, ws)]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 3, S_BEAR),
        ("BACKGROUND", (0, 0), (-1, -1), C_WHITE),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return [t, Spacer(1, 3 * mm)]


def make_smc_section(title, color):
    """Section header: 14pt bold with colored left border."""
    s = ParagraphStyle("smch", fontName="Helvetica-Bold", fontSize=14,
                        leading=18, textColor=S_TEXT)
    t = Table([[Paragraph(title, s)]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 4, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def make_entry_plan_2col(sd, is_pending):
    """Two-column entry plan with #F0F4F8 background, 14pt bold prices."""
    text_c = S_NEUTRAL if is_pending else S_TEXT
    label_s = ParagraphStyle("epl", fontName="Helvetica", fontSize=9,
                              leading=12, textColor=S_TEXT2)
    val_s = ParagraphStyle("epv", fontName="Courier-Bold", fontSize=14,
                            leading=18, textColor=text_c)
    note_s = ParagraphStyle("epn", fontName="Helvetica", fontSize=9,
                             leading=12, textColor=S_TEXT2)

    def _cell(label, value, note=""):
        parts = [Paragraph(label, label_s), Paragraph(value, val_s)]
        if note:
            parts.append(Paragraph(note, note_s))
        return parts

    if not sd.get("entry"):
        no_s = ParagraphStyle("epno", fontName="Helvetica", fontSize=11,
                               leading=14, textColor=S_TEXT2)
        t = Table([[Paragraph("No valid entry zone identified", no_s)]], colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), S_ENTRY_BG),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        return t

    pending_tag = '<font color="#E74C3C"> NOT ACTIVE</font>' if is_pending else ""

    left = _cell("Direction", sd["direction"] + pending_tag)
    left += _cell("Entry", f"{sd['entry']:.2f}")
    left += _cell("Stop Loss", f"{sd['stop']:.2f}" if sd.get("stop") else "—",
                  f"{sd['risk_pips']} pips risk" if sd.get("risk_pips") else "")

    right = []
    if sd.get("t1_price"):
        right += _cell("Target 1", f"{sd['t1_price']:.2f}",
                        f"R:R 1:{sd['t1_rr']:.1f}  ({sd['t1_type']})")
    if sd.get("t2_price"):
        right += _cell("Target 2", f"{sd['t2_price']:.2f}",
                        f"R:R 1:{sd['t2_rr']:.1f}  ({sd['t2_type']})")
    if sd.get("risk_pips"):
        right += _cell("Risk", f"{sd['risk_pips']} pips", "")

    # Pad shorter column
    max_rows = max(len(left), len(right))
    while len(left) < max_rows:
        left.append(Paragraph("", label_s))
    while len(right) < max_rows:
        right.append(Paragraph("", label_s))

    rows = [[left[i], right[i]] for i in range(max_rows)]
    half_w = (CONTENT_W - 12) / 2
    t = Table(rows, colWidths=[half_w, half_w])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), S_ENTRY_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 16),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return t


def make_confluence_bar(score, max_score, grade):
    """Thin horizontal confluence bar, grade-colored."""
    from reportlab.graphics.shapes import Drawing, Rect, String

    bar_w = CONTENT_W * 0.65
    bar_h = 14
    fill_pct = min(score / max_score, 1.0) if max_score > 0 else 0

    g_bg, _ = _smc_grade_color(grade)

    d = Drawing(CONTENT_W, bar_h + 4)
    d.add(Rect(0, 2, bar_w, bar_h, fillColor=C("#DFE6E9"), strokeColor=None, strokeWidth=0))
    if fill_pct > 0:
        d.add(Rect(0, 2, bar_w * fill_pct, bar_h, fillColor=g_bg, strokeColor=None, strokeWidth=0))
    d.add(String(bar_w + 10, 4, f"{score:.1f} / {max_score}  \u2014  Grade {grade}",
                  fontName="Helvetica-Bold", fontSize=10, fillColor=S_TEXT))
    return d


def make_mtf_strip(mtf_rows, direction):
    """One-line MTF strip with colored circles and structure labels."""
    def _dot_hex(structure):
        su = structure.upper()
        aligned = (direction == "LONG" and su == "BULLISH") or \
                  (direction == "SHORT" and su == "BEARISH")
        opposed = (direction == "LONG" and su == "BEARISH") or \
                  (direction == "SHORT" and su == "BULLISH")
        if aligned:
            return "#27AE60"
        if opposed:
            return "#E74C3C"
        return "#95A5A6"

    tf_s = ParagraphStyle("mtf_tf", fontName="Helvetica-Bold", fontSize=9,
                           leading=12, textColor=S_TEXT2, alignment=TA_CENTER)
    dot_s = ParagraphStyle("mtf_d", fontName="Helvetica", fontSize=9,
                            leading=14, textColor=S_TEXT, alignment=TA_CENTER)

    header = [Paragraph(tf, tf_s) for tf, _ in mtf_rows]
    dots = []
    for _, struct in mtf_rows:
        dc = _dot_hex(struct)
        dots.append(Paragraph(
            f'<font color="{dc}" size="16">\u25cf</font><br/>{struct}', dot_s
        ))

    cw = CONTENT_W / max(len(mtf_rows), 1)
    t = Table([header, dots], colWidths=[cw] * len(mtf_rows))
    t.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, S_DIVIDER),
    ]))
    return t


def _liq_type_color(typ):
    """Return hex color for liquidity level type."""
    t = typ.upper()
    if "INTERVENTION" in t:
        return "#F39C12"
    if t in ("EQH", "EQL"):
        return "#2980B9"
    if t == "ROUND":
        return "#95A5A6"
    if "TOKYO" in t:
        return "#F39C12"
    return "#2D3436"


def make_liquidity_table(levels, current_price):
    """Clean liquidity table with type color-coding and price separator."""
    hdr_s = ParagraphStyle("lqh", fontName="Helvetica-Bold", fontSize=9,
                            leading=12, textColor=S_TEXT2)
    cell_s = ParagraphStyle("lqc", fontName="Courier", fontSize=9,
                             leading=12, textColor=S_TEXT)
    cell_b = ParagraphStyle("lqb", fontName="Courier-Bold", fontSize=9,
                             leading=12, textColor=S_TEXT)

    # Sort by price descending
    sorted_lvls = sorted(levels, key=lambda x: x["price"], reverse=True)

    data = [[Paragraph("Level", hdr_s), Paragraph("Type", hdr_s),
             Paragraph("Significance", hdr_s)]]

    separator_after = None  # row index after which to draw price separator
    for i, lv in enumerate(sorted_lvls):
        near = abs(lv["price"] - current_price) <= 0.30  # within 30 pips
        tc = _liq_type_color(lv["type"])
        ps = cell_b if near else cell_s
        type_s = ParagraphStyle(f"lqt{i}", fontName="Helvetica-Bold" if near else "Helvetica",
                                 fontSize=9, leading=12, textColor=C(tc))
        data.append([
            Paragraph(f"{lv['price']:.2f}", ps),
            Paragraph(escape_xml(lv["type"]), type_s),
            Paragraph(escape_xml(lv["sig"]), cell_s if not near else cell_b),
        ])
        # Find where current price sits
        if separator_after is None and lv["price"] < current_price:
            separator_after = len(data) - 2  # before this row

    cw = [CONTENT_W * 0.2, CONTENT_W * 0.25, CONTENT_W * 0.55]
    t = Table(data, colWidths=cw)
    sc = [
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, S_DIVIDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    # Alternating rows
    for ri in range(1, len(data)):
        sc.append(("BACKGROUND", (0, ri), (-1, ri), S_ROW_ALT if ri % 2 == 0 else C_WHITE))
    # Price separator line
    if separator_after and separator_after > 0:
        sc.append(("LINEBELOW", (0, separator_after), (-1, separator_after), 1.5, S_INTV))
    t.setStyle(TableStyle(sc))
    return t


def make_compact_box(title, content_text, border_color):
    """Compact reference box with colored left border."""
    title_s = ParagraphStyle("cbh", fontName="Helvetica-Bold", fontSize=10,
                              leading=13, textColor=S_TEXT)
    body_s = ParagraphStyle("cbb", fontName="Helvetica", fontSize=10,
                             leading=13, textColor=S_TEXT2)
    inner = Table([
        [Paragraph(f"<b>{escape_xml(title)}</b>", title_s)],
        [Paragraph(content_text, body_s)],
    ], colWidths=[CONTENT_W])
    inner.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 3, border_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return inner


def make_playbook_boxes(pb):
    """Render 3 color-coded scenario boxes for the PDF playbook section."""
    if not pb:
        return []

    flowables = []
    scenarios = [
        ("primary", S_BULL, "Primary"),
        ("alternative", S_TARGET, "Alternative"),
        ("tail_risk", S_BEAR, "Tail Risk"),
    ]

    title_s = ParagraphStyle("pb_title", fontName="Helvetica-Bold", fontSize=10,
                              leading=13, textColor=S_TEXT)
    body_s = ParagraphStyle("pb_body", fontName="Helvetica", fontSize=9,
                             leading=12, textColor=S_TEXT2)
    prob_s = ParagraphStyle("pb_prob", fontName="Helvetica-Bold", fontSize=10,
                             leading=13, textColor=S_TEXT2, alignment=TA_RIGHT)

    for key, color, label in scenarios:
        s = pb.get(key)
        if not s:
            continue

        # Title row: name left, probability right
        title_text = f"{label}: {escape_xml(s['name'])}"
        prob_text = f"{s['probability']}%"

        # Body: sessions + action, compact
        body_lines = []
        for sess_name in ["Tokyo", "London", "New York"]:
            sess_text = s.get("sessions", {}).get(sess_name, "")
            if sess_text:
                body_lines.append(f"<b>{sess_name}:</b> {escape_xml(sess_text)}")
        body_lines.append(f"<b>\u2192 Action:</b> {escape_xml(s.get('action', ''))}")
        if s.get("invalidation") and s["invalidation"] != "N/A — event-driven":
            body_lines.append(f"<b>\u2718 Invalidation:</b> {escape_xml(s['invalidation'])}")
        content = "<br/>".join(body_lines)

        # Build box with colored left border
        header_row = Table(
            [[Paragraph(title_text, title_s), Paragraph(prob_text, prob_s)]],
            colWidths=[CONTENT_W - 60, 50]
        )
        header_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))

        inner = Table([
            [header_row],
            [Paragraph(content, body_s)],
        ], colWidths=[CONTENT_W])
        inner.setStyle(TableStyle([
            ("LINEBEFORE", (0, 0), (0, -1), 3, color),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (0, 0), 4),
            ("TOPPADDING", (0, 1), (0, 1), 2),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
        ]))

        flowables.append(inner)
        flowables.append(Spacer(1, 2 * mm))

    return flowables


def make_zones_table(zones, current_price, direction):
    """Nearby/appendix zone table with color-coding and distance column."""
    hdr_s = ParagraphStyle("zth", fontName="Helvetica-Bold", fontSize=8,
                            leading=11, textColor=S_TEXT2)
    cell_s = ParagraphStyle("ztc", fontName="Helvetica", fontSize=8,
                             leading=11, textColor=S_TEXT)

    data = [[Paragraph(h, hdr_s) for h in ["TF", "Type", "Zone", "Dir", "Status", "Dist"]]]
    for z in zones:
        mid = (z["low"] + z["high"]) / 2
        dist_pips = round(abs(mid - current_price) * 100)
        is_intv = "INTERVENTION" in z.get("type", "").upper()
        d = z["dir"].upper()
        dir_hex = "#27AE60" if "BULL" in d or "LONG" in d else \
                  "#E74C3C" if "BEAR" in d or "SHORT" in d else "#636E72"
        dir_s = ParagraphStyle(f"zd{id(z)}", fontName="Helvetica", fontSize=8,
                                leading=11, textColor=C(dir_hex))
        data.append([
            Paragraph(z["tf"], cell_s),
            Paragraph(escape_xml(z["type"]), cell_s),
            Paragraph(f"{z['low']:.2f}-{z['high']:.2f}", cell_s),
            Paragraph(z["dir"], dir_s),
            Paragraph(z["status"], cell_s),
            Paragraph(f"{dist_pips}p", cell_s),
        ])

    cw = [CONTENT_W * 0.08, CONTENT_W * 0.28, CONTENT_W * 0.22,
          CONTENT_W * 0.12, CONTENT_W * 0.16, CONTENT_W * 0.14]
    t = Table(data, colWidths=cw, repeatRows=1)
    sc = [
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, S_DIVIDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for ri in range(1, len(data)):
        bg = S_ROW_ALT if ri % 2 == 0 else C_WHITE
        # Gold tint for intervention zones
        z = zones[ri - 1]
        if "INTERVENTION" in z.get("type", "").upper():
            bg = C("#FEF9E7")
        sc.append(("BACKGROUND", (0, ri), (-1, ri), bg))
    t.setStyle(TableStyle(sc))
    return t


# ── SMC PDF Assembly ─────────────────────────────────────────────────────────

def build_smc_pdf(md_text, base_dir, meta):
    """Build the complete SMC PDF with professional trading-card layout."""
    styles = _styles()
    sd = parse_smc_data(md_text)
    contradictions = detect_contradictions(sd)
    is_pending = sd.get("confirmation") == "PENDING"
    price = sd.get("current_price", 0)

    # Body style overrides for SMC
    body_s = ParagraphStyle("smc_body", fontName="Helvetica", fontSize=11,
                             leading=14, textColor=S_TEXT)
    small_s = ParagraphStyle("smc_small", fontName="Helvetica", fontSize=9,
                              leading=12, textColor=S_TEXT2)

    flowables = []

    # ═══════════════════════════════════════════════════════════════════════
    # PAGE 1 — THE TRADING CARD
    # ═══════════════════════════════════════════════════════════════════════

    # Hero block (top ~20%)
    flowables.append(make_smc_hero(sd, contradictions))
    flowables.append(Spacer(1, 3 * mm))

    # Warnings: single box, not stacked banners
    if contradictions:
        flowables.extend(make_warning_box(contradictions))

    # Chart — full width
    chart_file = sd.get("chart_filename")
    if chart_file:
        chart_path = os.path.join(base_dir, chart_file)
        if os.path.exists(chart_path):
            ir = ImageReader(chart_path)
            iw, ih = ir.getSize()
            aspect = ih / iw
            dw = CONTENT_W
            dh = dw * aspect
            max_h = (PAGE_H - M_TOP - M_BOTTOM) * 0.35
            if dh > max_h:
                dh = max_h
                dw = dh / aspect
            img = Image(chart_path, width=dw, height=dh)
            img.hAlign = "CENTER"
            flowables.append(img)
            flowables.append(Spacer(1, 4 * mm))

    # Entry plan — two-column
    flowables.append(make_entry_plan_2col(sd, is_pending))
    flowables.append(Spacer(1, 2 * mm))

    # Confluence bar
    flowables.append(make_confluence_bar(sd["confluence_score"], 6, sd["grade"]))
    # Scoring details in 9pt gray
    details = [d for d in sd.get("scoring_details", []) if d.startswith("+") or d.startswith("-")]
    if details:
        flowables.append(Spacer(1, 1 * mm))
        detail_text = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(escape_xml(d) for d in details[:6])
        flowables.append(Paragraph(detail_text, small_s))

    # ═══════════════════════════════════════════════════════════════════════
    # PAGE 2 — NEXT 24h PLAYBOOK + MTF + LIQUIDITY
    # ═══════════════════════════════════════════════════════════════════════
    flowables.append(PageBreak())

    # Playbook section
    pb = sd.get("playbook", {})
    if pb:
        flowables.append(make_smc_section("Next 24h Playbook", S_TARGET))
        flowables.append(Spacer(1, 2 * mm))

        gen_text = pb.get("generated_at", "")
        if gen_text:
            ts_s = ParagraphStyle("pb_ts", fontName="Helvetica", fontSize=8,
                                   leading=11, textColor=S_NEUTRAL)
            flowables.append(Paragraph(f"Generated at {escape_xml(gen_text)}", ts_s))
            flowables.append(Spacer(1, 2 * mm))

        flowables.extend(make_playbook_boxes(pb))
        flowables.append(Spacer(1, 2 * mm))

    # Playbook chart
    pb_chart = sd.get("playbook_chart_filename")
    if pb_chart:
        pb_chart_path = os.path.join(base_dir, pb_chart)
        if os.path.exists(pb_chart_path):
            ir = ImageReader(pb_chart_path)
            iw, ih = ir.getSize()
            aspect = ih / iw
            dw = CONTENT_W
            dh = dw * aspect
            max_h = (PAGE_H - M_TOP - M_BOTTOM) * 0.30
            if dh > max_h:
                dh = max_h
                dw = dh / aspect
            img = Image(pb_chart_path, width=dw, height=dh)
            img.hAlign = "CENTER"
            flowables.append(img)
            flowables.append(Spacer(1, 3 * mm))

    # MTF alignment strip
    if sd.get("mtf"):
        flowables.append(make_smc_section("MTF Alignment", S_TARGET))
        flowables.append(Spacer(1, 2 * mm))
        flowables.append(make_mtf_strip(sd["mtf"], sd["direction"]))
        flowables.append(Spacer(1, 3 * mm))

    # Key liquidity levels
    if sd.get("liquidity"):
        flowables.append(make_smc_section("Key Liquidity Levels", S_TARGET))
        flowables.append(Spacer(1, 2 * mm))
        flowables.append(make_liquidity_table(sd["liquidity"], price))
        flowables.append(Spacer(1, 3 * mm))

    # ═══════════════════════════════════════════════════════════════════════
    # PAGE 3 — CONTEXT & DETAILS
    # ═══════════════════════════════════════════════════════════════════════
    flowables.append(PageBreak())

    # 4H Structure — compact single-line box
    struct_line = (
        f"{escape_xml(sd.get('structure_4h', ''))} &nbsp;|&nbsp; "
        f"Last: {escape_xml(sd.get('last_event', ''))} &nbsp;|&nbsp; "
        f"{escape_xml(sd.get('pd_zone', ''))}"
    )
    flowables.append(make_compact_box("4H Structure", struct_line, S_TARGET))
    flowables.append(Spacer(1, 4 * mm))

    # Scenario + Risk + Session — stacked compact boxes with colored borders
    scen_text = escape_xml(sd.get("scenario_rationale", ""))
    if sd.get("bias_alignment"):
        scen_text += f"<br/>Bias Alignment: {escape_xml(sd['bias_alignment'])}"
    flowables.append(make_compact_box(
        f"Scenario {sd.get('scenario_id', '')}: {sd.get('scenario_name', '')}",
        scen_text, S_TARGET))
    flowables.append(Spacer(1, 2 * mm))

    if sd.get("risk_alerts"):
        alert_text = "<br/>".join(f"\u26a0 {escape_xml(a)}" for a in sd["risk_alerts"])
        flowables.append(make_compact_box("Risk Alerts", alert_text, S_BEAR))
        flowables.append(Spacer(1, 2 * mm))

    if sd.get("session_primary"):
        sess_text = f"Primary: {escape_xml(sd['session_primary'])}"
        for label, detail in sd.get("sessions", {}).items():
            sess_text += f"<br/>{escape_xml(label)}: {escape_xml(detail)}"
        flowables.append(make_compact_box("Session Plan", sess_text, S_BULL))
        flowables.append(Spacer(1, 2 * mm))

    # Invalidation — gray box, 9pt
    if sd.get("invalidation"):
        inv_text = "<br/>".join(f"\u2022 {escape_xml(item)}" for item in sd["invalidation"])
        inv_s = ParagraphStyle("inv", fontName="Helvetica", fontSize=9,
                                leading=12, textColor=S_TEXT2)
        inv_t = Table([[Paragraph(inv_text, inv_s)]], colWidths=[CONTENT_W])
        inv_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), S_ROW_ALT),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("ROUNDEDCORNERS", [3, 3, 3, 3]),
        ]))
        flowables.append(make_smc_section("Invalidation", S_NEUTRAL))
        flowables.append(Spacer(1, 1 * mm))
        flowables.append(inv_t)

    # ═══════════════════════════════════════════════════════════════════════
    # ZONES (flows naturally after page 2 content — no forced break)
    # ═══════════════════════════════════════════════════════════════════════

    # Nearby zones (within 100 pips)
    nearby = [z for z in sd["active_zones"]
              if abs((z["low"] + z["high"]) / 2 - price) <= 1.00]

    if nearby:
        usable_h = PAGE_H - (M_TOP + 0.5 * cm) - (M_BOTTOM + 0.3 * cm)
        flowables.append(CondPageBreak(usable_h * 0.25))
        flowables.append(Spacer(1, 4 * mm))
        flowables.append(make_smc_section(
            f"Nearby Zones ({len(nearby)} within 100 pips)", S_BULL))
        flowables.append(Spacer(1, 2 * mm))
        flowables.append(make_zones_table(nearby, price, sd["direction"]))
        flowables.append(Spacer(1, 5 * mm))
    elif sd["active_zones"]:
        flowables.append(Spacer(1, 5 * mm))
        flowables.append(Paragraph(
            f"No zones within 100 pips of {price:.2f} \u2014 see appendix.",
            small_s))

    # Full appendix: 4H + 1H only
    appendix_zones = [z for z in sd["active_zones"] if z["tf"] in ("4H", "1H")]
    if appendix_zones:
        # Separator
        flowables.append(Spacer(1, 3 * mm))
        rule_s = ParagraphStyle("apx_rule", fontName="Helvetica", fontSize=11,
                                 leading=14, textColor=S_NEUTRAL)
        flowables.append(Table([[""]], colWidths=[CONTENT_W], rowHeights=[1]))
        flowables[-1].setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, S_DIVIDER),
        ]))
        flowables.append(Spacer(1, 2 * mm))
        flowables.append(Paragraph(
            f"Zone Reference \u2014 4H &amp; 1H ({len(appendix_zones)} zones)", rule_s))
        flowables.append(Spacer(1, 3 * mm))
        flowables.append(make_zones_table(appendix_zones, price, sd["direction"]))

    # Footer
    flowables.append(Spacer(1, 6 * mm))
    footer_s = ParagraphStyle("smc_foot", fontName="Helvetica", fontSize=9,
                               leading=12, textColor=S_NEUTRAL)
    flowables.append(Paragraph(
        f"Generated: {meta.get('date', '')} &nbsp;|&nbsp; "
        f"Source: Module 07 from {sd.get('report_date', '')}",
        footer_s))

    return flowables


def markdown_to_pdf_smc(md_path):
    """SMC-specific PDF generation entry point."""
    md_path = os.path.abspath(md_path)
    base_dir = os.path.dirname(md_path)
    pdf_path = os.path.splitext(md_path)[0] + ".pdf"

    with open(md_path, "r") as f:
        md_text = f.read()

    meta = extract_metadata(md_text)
    # Enhance meta for SMC
    if not meta.get("title"):
        meta["title"] = "USD/JPY Smart Money Concepts"
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(md_path))
    if m and not meta.get("date"):
        meta["date"] = m.group(1)

    flowables = build_smc_pdf(md_text, base_dir, meta)

    tmpl = ReportTemplate(meta.get("title", "USD/JPY SMC"), meta.get("date", ""))
    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        leftMargin=M_LEFT, rightMargin=M_RIGHT,
        topMargin=M_TOP + 0.5 * cm,
        bottomMargin=M_BOTTOM + 0.3 * cm,
    )
    doc.build(flowables, onFirstPage=tmpl.on_first_page, onLaterPages=tmpl.on_page)
    return pdf_path


def main():
    parser = argparse.ArgumentParser(description="Convert USD/JPY report to styled PDF.")
    parser.add_argument("markdown_file", help="Path to .md report")
    parser.add_argument("--type", choices=["daily", "weekly", "smc"], default=None)
    args = parser.parse_args()
    if not os.path.exists(args.markdown_file):
        print(f"ERROR: File not found: {args.markdown_file}", file=sys.stderr)
        sys.exit(1)
    if args.type:
        rt = args.type
    elif "smc_" in os.path.basename(args.markdown_file):
        rt = "smc"
    elif "/weekly/" in args.markdown_file:
        rt = "weekly"
    else:
        rt = "daily"
    if rt == "smc":
        pdf_path = markdown_to_pdf_smc(args.markdown_file)
    else:
        pdf_path = markdown_to_pdf(args.markdown_file, rt)
    print(f"PDF generated: {pdf_path}")


if __name__ == "__main__":
    main()
