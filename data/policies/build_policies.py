"""
Render synthetic medical policy PDFs for VERITY.

    python3 data/policies/build_policies.py [outdir]

Produces a real, section-numbered PDF per policy so that AI_PARSE_DOCUMENT
has genuine document structure to recover. We deliberately do NOT shortcut
straight to text: exercising the parser on real PDFs is an explicit
requirement of the challenge brief.

Every page carries a synthetic-document watermark and the fictional-payer
notice. Do not remove them.
"""

import os
import sys

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from policy_defs import ALL_POLICIES, WATERMARK  # noqa: E402

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#6b6b6b")
RULE = colors.HexColor("#c8c8c8")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=ss["Normal"], fontName="Helvetica-Bold",
            fontSize=15, leading=19, spaceAfter=4, textColor=INK,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=ss["Normal"], fontName="Helvetica",
            fontSize=10.5, leading=14, textColor=MUTED, spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "h1", parent=ss["Normal"], fontName="Helvetica-Bold",
            fontSize=11.5, leading=15, spaceBefore=16, spaceAfter=7, textColor=INK,
        ),
        "h2": ParagraphStyle(
            "h2", parent=ss["Normal"], fontName="Helvetica-Bold",
            fontSize=10, leading=13, spaceBefore=11, spaceAfter=5, textColor=INK,
        ),
        "body": ParagraphStyle(
            "body", parent=ss["Normal"], fontName="Helvetica",
            fontSize=9.5, leading=13.5, spaceAfter=7, textColor=INK,
        ),
        "notice": ParagraphStyle(
            "notice", parent=ss["Normal"], fontName="Helvetica-Bold",
            fontSize=7.5, leading=10, alignment=TA_CENTER,
            textColor=colors.HexColor("#8a1c1c"),
        ),
    }


def _decorate(canvas, doc):
    """Watermark + footer on every page."""
    canvas.saveState()
    w, h = LETTER

    # Diagonal watermark
    canvas.setFont("Helvetica-Bold", 38)
    canvas.setFillColor(colors.Color(0.86, 0.86, 0.86, alpha=0.42))
    canvas.translate(w / 2.0, h / 2.0)
    canvas.rotate(38)
    canvas.drawCentredString(0, 0, "SYNTHETIC")
    canvas.drawCentredString(0, -46, "DEMONSTRATION ONLY")
    canvas.restoreState()

    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.9 * inch, 0.78 * inch, w - 0.9 * inch, 0.78 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.9 * inch, 0.6 * inch, WATERMARK)
    canvas.drawRightString(w - 0.9 * inch, 0.6 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _meta_table(p):
    rows = [
        ["Policy Number", p["policy_id"], "Version", p["version"]],
        ["Line of Business", p["lob"], "Effective Date", p["effective_date"]],
        ["Next Review", p["review_date"], "Supersedes",
         f"v{p['supersedes_version']} ({p['supersedes_effective_date']})"],
    ]
    t = Table(rows, colWidths=[1.15 * inch, 2.15 * inch, 1.15 * inch, 2.15 * inch])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f2f2")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f2f2f2")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def build(policy, outdir):
    st = _styles()
    path = os.path.join(outdir, f"{policy['policy_id']}.pdf")

    doc = BaseDocTemplate(
        path, pagesize=LETTER,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.85 * inch, bottomMargin=1.0 * inch,
        title=f"{policy['policy_id']} {policy['title']}",
        author=policy["payer"],
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_decorate)])

    story = [
        Paragraph(
            "NOTICE: This document is entirely synthetic. &quot;Meridian Health Plan&quot; is a "
            "fictional payer. This policy was generated for a hackathon demonstration and "
            "does not reflect the coverage criteria of any real insurer.",
            st["notice"],
        ),
        Spacer(1, 14),
        Paragraph(policy["payer"], st["subtitle"]),
        Paragraph(f"Medical Policy {policy['policy_id']}", st["title"]),
        Paragraph(policy["title"], st["subtitle"]),
        _meta_table(policy),
        Spacer(1, 6),
    ]

    for sec in policy["sections"]:
        block = [Paragraph(f"{sec['ref']}. {sec['heading']}", st["h1"])]
        for para in sec.get("body", []):
            block.append(Paragraph(para, st["body"]))
        # Keep a heading with its first paragraph so sections don't strand.
        story.append(KeepTogether(block[:2]) if len(block) > 1 else block[0])
        for para in sec.get("body", [])[1:]:
            story.append(Paragraph(para, st["body"]))

        for sub in sec.get("subsections", []):
            sub_block = [Paragraph(f"{sub['ref']} {sub['heading']}", st["h2"])]
            if sub.get("body"):
                sub_block.append(Paragraph(sub["body"][0], st["body"]))
            story.append(KeepTogether(sub_block))
            for para in sub.get("body", [])[1:]:
                story.append(Paragraph(para, st["body"]))

    doc.build(story)
    return path


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(outdir, exist_ok=True)
    for p in ALL_POLICIES:
        print("wrote", build(p, outdir))


if __name__ == "__main__":
    main()
