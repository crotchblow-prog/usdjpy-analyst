#!/usr/bin/env python3
"""
Generate a PDF from a USD/JPY daily/weekly markdown report.

Usage:
    from generate_pdf import markdown_to_pdf
    markdown_to_pdf("./output/daily/2026-03-30.md", "./output/daily/2026-03-30.pdf")

Or standalone:
    python3 generate_pdf.py ./output/daily/2026-03-30.md
"""

import re
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, HRFlowable, KeepTogether,
)


# ── Styles ────────────────────────────────────────────────────────────────────

def build_styles():
    ss = getSampleStyleSheet()

    ss.add(ParagraphStyle(
        "ReportTitle", parent=ss["Title"],
        fontSize=18, leading=22, spaceAfter=4,
        textColor=HexColor("#1a1a2e"),
    ))
    ss.add(ParagraphStyle(
        "BiasBar", parent=ss["Normal"],
        fontSize=11, leading=14, spaceAfter=8,
        textColor=HexColor("#444"), backColor=HexColor("#f0f4f8"),
        borderPadding=(6, 8, 6, 8),
    ))
    ss.add(ParagraphStyle(
        "H2", parent=ss["Heading2"],
        fontSize=13, leading=16, spaceBefore=8, spaceAfter=6,
        textColor=HexColor("#1a1a2e"), borderWidth=0,
    ))
    ss.add(ParagraphStyle(
        "H3", parent=ss["Heading3"],
        fontSize=11, leading=14, spaceBefore=8, spaceAfter=4,
        textColor=HexColor("#333"),
    ))
    ss.add(ParagraphStyle(
        "Body", parent=ss["Normal"],
        fontSize=9, leading=12, spaceAfter=4,
        textColor=HexColor("#333"),
    ))
    ss.add(ParagraphStyle(
        "BodyBold", parent=ss["Normal"],
        fontSize=9, leading=12, spaceAfter=4,
        textColor=HexColor("#222"),
    ))
    ss.add(ParagraphStyle(
        "Blockquote", parent=ss["Normal"],
        fontSize=9.5, leading=13, spaceAfter=6,
        textColor=HexColor("#1a1a2e"), backColor=HexColor("#eef2f7"),
        borderPadding=(6, 8, 6, 8), leftIndent=8,
    ))
    ss.add(ParagraphStyle(
        "SmallItalic", parent=ss["Normal"],
        fontSize=8, leading=10, spaceAfter=2,
        textColor=HexColor("#777"), fontName="Helvetica-Oblique",
    ))
    ss.add(ParagraphStyle(
        "Footer", parent=ss["Normal"],
        fontSize=7, leading=9,
        textColor=HexColor("#999"), alignment=TA_CENTER,
    ))
    ss.add(ParagraphStyle(
        "TableCell", parent=ss["Normal"],
        fontSize=8, leading=10, textColor=HexColor("#333"),
    ))
    ss.add(ParagraphStyle(
        "TableHeader", parent=ss["Normal"],
        fontSize=8, leading=10, textColor=white,
        fontName="Helvetica-Bold",
    ))
    return ss


# ── Markdown → Flowables ──────────────────────────────────────────────────────

def inline_fmt(text):
    """Convert markdown inline formatting to reportlab XML."""
    # Escape bare ampersands for reportlab XML (but not already-escaped ones)
    text = re.sub(r'&(?!amp;|lt;|gt;|quot;|#)', '&amp;', text)
    # Bold+italic
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    # Bold
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Italic
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    # Inline code
    text = re.sub(r'`(.+?)`', r'<font face="Courier" size="8">\1</font>', text)
    return text


def parse_table(lines, styles):
    """Parse markdown table lines into a reportlab Table flowable."""
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    # Remove separator row (---|----|---)
    rows = [r for r in rows if not all(re.match(r'^[-:]+$', c) for c in r)]
    if not rows:
        return None

    # Build table data with Paragraphs
    table_data = []
    for i, row in enumerate(rows):
        style = styles["TableHeader"] if i == 0 else styles["TableCell"]
        table_data.append([Paragraph(inline_fmt(c), style) for c in row])

    n_cols = max(len(r) for r in table_data)
    avail  = A4[0] - 2 * 18 * mm
    col_w  = avail / n_cols

    t = Table(table_data, colWidths=[col_w] * n_cols, repeatRows=1)

    header_bg = HexColor("#2c3e50")
    alt_bg    = HexColor("#f8f9fa")

    style_cmds = [
        ("BACKGROUND",  (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR",   (0, 0), (-1, 0), white),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("GRID",        (0, 0), (-1, -1), 0.4, HexColor("#ddd")),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Alternate row shading
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), alt_bg))

    t.setStyle(TableStyle(style_cmds))
    return t


def _is_keep_together(stripped):
    """Return True if this ## heading should start a KeepTogether group.

    Modules 01, 03 get KeepTogether so header+table+narrative+chart stay on
    one page.  Module 05 flows freely so its content can share a page with
    the checklist.  Module 07 and Bottom Line also flow freely.
    """
    if not stripped.startswith("## "):
        return False
    text = stripped[3:].strip()
    if re.match(r'^\d{2}\s*[—–-]', text):
        # Only 01-04 keep together; 05, 06, 07 flow freely
        return text[:2] in ("01", "02", "03", "04")
    for kw in ("At a Glance", "Risk Alerts", "vs Yesterday"):
        if text.startswith(kw):
            return True
    return False


def markdown_to_flowables(md_text, output_dir, styles):
    """Convert markdown text into a list of reportlab flowables.

    Module sections (## 01 — … through the next ---) are wrapped in
    KeepTogether so header + table + narrative + chart stay on one page.
    """
    flowables = []
    lines = md_text.split("\n")
    i = 0
    table_buf = []

    # Accumulator for the current module section being grouped
    section_buf = []     # list of flowables for the current KeepTogether group
    in_section = False   # True while collecting a module section

    def flush_table():
        nonlocal table_buf
        if table_buf:
            t = parse_table(table_buf, styles)
            if t:
                _append(t)
                _append(Spacer(1, 4 * mm))
            table_buf = []

    def _append(item):
        """Append a flowable to the section buffer or the top-level list."""
        if in_section:
            section_buf.append(item)
        else:
            flowables.append(item)

    def flush_section():
        """Wrap accumulated section flowables in KeepTogether."""
        nonlocal section_buf, in_section
        if section_buf:
            flowables.append(KeepTogether(section_buf))
            section_buf = []
        in_section = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blank line
        if not stripped:
            flush_table()
            i += 1
            continue

        # Table row
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_buf.append(stripped)
            i += 1
            continue
        else:
            flush_table()

        # Horizontal rule — acts as section separator
        if re.match(r'^---+$', stripped):
            flush_table()
            flush_section()
            flowables.append(HRFlowable(
                width="100%", thickness=0.5,
                color=HexColor("#ddd"), spaceAfter=2, spaceBefore=2,
            ))
            i += 1
            continue

        # H1 title
        if stripped.startswith("# ") and not stripped.startswith("##"):
            # Skip — we use header/footer instead
            i += 1
            continue

        # H2 — start a new KeepTogether group only for chart-bearing modules
        if stripped.startswith("## "):
            flush_table()
            flush_section()
            if _is_keep_together(stripped):
                in_section = True
            _append(Spacer(1, 2 * mm))
            text = inline_fmt(stripped[3:])
            _append(Paragraph(text, styles["H2"]))
            i += 1
            continue

        # Blockquote (bias bar or narrative)
        if stripped.startswith("> "):
            text = inline_fmt(stripped[2:])
            _append(Paragraph(text, styles["Blockquote"]))
            i += 1
            continue

        # H3
        if stripped.startswith("### "):
            text = inline_fmt(stripped[4:])
            _append(Paragraph(text, styles["H3"]))
            i += 1
            continue

        # Image
        img_match = re.match(r'!\[.*?\]\((.+?)\)', stripped)
        if img_match:
            img_file = output_dir / img_match.group(1)
            if img_file.exists():
                avail_w = A4[0] - 2 * 18 * mm
                img = Image(str(img_file), width=avail_w, height=avail_w * 0.42)
                img.hAlign = "CENTER"
                _append(Spacer(1, 1 * mm))
                _append(img)
                _append(Spacer(1, 1 * mm))
            i += 1
            continue

        # Italic-only line (data source notes)
        if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
            text = inline_fmt(stripped)
            _append(Paragraph(text, styles["SmallItalic"]))
            i += 1
            continue

        # Bold lines (like **Bias: BULL** | Confidence: M)
        if stripped.startswith("**"):
            text = inline_fmt(stripped)
            _append(Paragraph(text, styles["BodyBold"]))
            i += 1
            continue

        # Regular paragraph
        text = inline_fmt(stripped)
        _append(Paragraph(text, styles["Body"]))
        i += 1

    flush_table()
    flush_section()
    return flowables


# ── PDF Build ─────────────────────────────────────────────────────────────────

def markdown_to_pdf(md_path, pdf_path=None):
    md_path = Path(md_path)
    if pdf_path is None:
        pdf_path = md_path.with_suffix(".pdf")
    else:
        pdf_path = Path(pdf_path)

    output_dir = md_path.parent
    md_text = md_path.read_text(encoding="utf-8")

    # Extract date and report type from filename/content
    report_date = md_path.stem  # e.g. "2026-03-30"
    report_type = "Weekly" if "weekly" in str(md_path.parent).lower() or "Weekly" in md_text[:200] else "Daily"
    header_text = f"USD/JPY {report_type} Analysis — {report_date}"
    footer_text = "Data: FRED, MOF Japan, Yahoo Finance | TZ: JST"

    styles = build_styles()

    def header_footer(canvas, doc):
        canvas.saveState()
        # Header
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(HexColor("#666"))
        canvas.drawString(18 * mm, A4[1] - 12 * mm, header_text)
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 12 * mm, report_date)
        canvas.setStrokeColor(HexColor("#ddd"))
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, A4[1] - 14 * mm, A4[0] - 18 * mm, A4[1] - 14 * mm)

        # Footer
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(HexColor("#999"))
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.drawString(18 * mm, 10 * mm, footer_text)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )

    flowables = markdown_to_flowables(md_text, output_dir, styles)
    doc.build(flowables, onFirstPage=header_footer, onLaterPages=header_footer)
    return pdf_path


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 generate_pdf.py <report.md> [output.pdf]")
        sys.exit(1)

    md   = sys.argv[1]
    pdf  = sys.argv[2] if len(sys.argv) > 2 else None
    path = markdown_to_pdf(md, pdf)
    print(f"PDF saved: {path}")
