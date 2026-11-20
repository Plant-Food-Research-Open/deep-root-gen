#!/usr/bin/env python3
"""Typeset the maintained input-layer guide for offline printing.

Requires ReportLab. Render diagrams first with render_input_diagrams.mjs.
This script reads public documentation only and does not import the model.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/INPUT_LAYERS_AND_MODEL_FLOW.md"
FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")
INK = colors.HexColor("#193449")
ACCENT = colors.HexColor("#27626B")
MUTED = colors.HexColor("#566574")
RULE = colors.HexColor("#CDD7DF")
PALE = colors.HexColor("#EBF2F5")


def register_fonts():
    for name, filename in [
        ("Body", "DejaVuSans.ttf"), ("Body-Bold", "DejaVuSans-Bold.ttf"),
        ("Body-Italic", "DejaVuSans-Oblique.ttf"),
        ("Body-BoldItalic", "DejaVuSans-BoldOblique.ttf"),
        ("Code", "DejaVuSansMono.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(FONT_ROOT / filename)))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold",
                                  italic="Body-Italic", boldItalic="Body-BoldItalic")


def inline(text, code_size=8.3):
    """Convert the small inline Markdown subset, preserving local source links."""
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", " - ")
    saved = []

    def stash(value):
        key = f"ZZINLINE{len(saved)}ZZ"
        saved.append(value)
        return key

    def link(m):
        label, target = m.groups()
        if not target.startswith(("http://", "https://")):
            rel, _, anchor = target.partition("#")
            absolute = (SOURCE.parent / rel).resolve()
            target = absolute.as_uri() + ("#" + anchor if anchor else "")
        return stash(f'<link href="{html.escape(target, quote=True)}" color="#27626B">'
                     f'{html.escape(label)}</link>')

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"`([^`]+)`", lambda m: stash(
        f'<font name="Code" size="{code_size}">{html.escape(m[1])}</font>'), text)
    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    for i, value in enumerate(saved):
        text = text.replace(f"ZZINLINE{i}ZZ", value)
    return text


def styles():
    common = dict(fontName="Body", textColor=INK, splitLongWords=True)
    return {
        "body": ParagraphStyle("BodyText", fontSize=9.5, leading=13.5,
                               spaceAfter=7, **common),
        "title": ParagraphStyle("DocTitle", fontName="Body-Bold", fontSize=23,
                                leading=28, textColor=INK, spaceAfter=10),
        "subtitle": ParagraphStyle("Subtitle", fontSize=10.3, leading=15,
                                   spaceAfter=14, **common),
        "h2": ParagraphStyle("Section", fontName="Body-Bold", fontSize=14,
                             leading=18, textColor=ACCENT, spaceBefore=13,
                             spaceAfter=8, keepWithNext=True),
        "h3": ParagraphStyle("Subsection", fontName="Body-Bold", fontSize=11,
                             leading=15, textColor=INK, spaceBefore=10,
                             spaceAfter=7, keepWithNext=True),
        "cell": ParagraphStyle("Cell", fontSize=8.45, leading=11.6,
                               spaceAfter=0, **common),
        "head": ParagraphStyle("TableHead", fontName="Body-Bold", fontSize=8.5,
                               leading=11.6, textColor=INK),
        "caption": ParagraphStyle("Caption", fontName="Body", fontSize=8,
                                  leading=11, textColor=MUTED, spaceAfter=8),
        "code": ParagraphStyle("CodeBlock", fontName="Code", fontSize=8.2,
                               leading=12, textColor=INK, spaceAfter=10,
                               backColor=PALE, borderPadding=9),
    }


class PrintGuide(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in {"Section", "Subsection"}:
            title = flowable.getPlainText()
            key = "section-" + hashlib.sha1(title.encode()).hexdigest()[:12]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, 0 if flowable.style.name == "Section" else 1)


def footer(canvas, doc):
    w, h = canvas._pagesize
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.45)
    canvas.line(16 * mm, 14 * mm, w - 16 * mm, 14 * mm)
    canvas.setFont("Body", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(16 * mm, 10 * mm, "DeepRootGen | Input layers and model flow | 17 November 2026")
    canvas.drawRightString(w - 16 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


def make_table(raw, width, st):
    rows = [[x.strip() for x in line.strip().strip("|").split("|")] for line in raw]
    rows = [r for r in rows if not all(re.fullmatch(r"[-: ]+", c) for c in r)]
    n = len(rows[0])
    weights = {
        2: [0.30, 0.70],
        3: [0.19, 0.36, 0.45],
        4: [0.18, 0.27, 0.27, 0.28],
    }.get(n, [1 / n] * n)
    if rows[0][0] in {"Input validator", "Component"}:
        weights = [0.19, 0.27, 0.27, 0.27]
    cells = [[Paragraph(inline(cell, 7.8), st["head" if i == 0 else "cell"])
              for cell in row] for i, row in enumerate(rows)]
    vertical_padding = 5 if rows[0][0] == "Comparison route" else 6
    table = Table(cells, colWidths=[width * x for x in weights], repeatRows=1,
                  hAlign="LEFT", splitByRow=1, spaceAfter=12)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, ACCENT),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
    ]))
    return table


def build(output, diagram_dir):
    register_fonts()
    st = styles()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = diagram_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    diagrams = manifest["diagrams"] if isinstance(manifest, dict) else manifest
    text = SOURCE.read_text()
    lines = text.splitlines()
    width, height = A4
    usable = width - 32 * mm
    doc = PrintGuide(str(output), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                     topMargin=17 * mm, bottomMargin=19 * mm,
                     title="DeepRootGen: Input layers and model flow",
                     author="DeepRootGen project documentation", subject="Current model architecture and parameter crosswalk")
    doc.addPageTemplates([
        PageTemplate(id="portrait", frames=[Frame(16 * mm, 19 * mm, usable, height - 36 * mm,
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=footer, pagesize=A4),
        PageTemplate(id="landscape", frames=[Frame(16 * mm, 19 * mm, height - 32 * mm, width - 36 * mm,
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=footer, pagesize=landscape(A4)),
    ])
    story = [Paragraph("DeepRootGen", st["title"]),
             Paragraph("Input layers, model flow and important parameters", st["subtitle"]),
             Paragraph("PRINT EDITION  |  17 NOVEMBER 2026  |  SOURCE ff1a1df", st["caption"]),
             Paragraph("Four full-page flow diagrams follow the reference text. Figure references below link directly to them.", st["caption"])]
    i = 1
    chart = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```mermaid"):
            j = i + 1
            while j < len(lines) and lines[j] != "```":
                j += 1
            story.append(Paragraph(
                f'<link href="#figure{chart+1}" color="#27626B"><b>See Figure {chart+1}: '
                f'{html.escape(diagrams[chart]["title"])}</b></link> in the diagram section.', st["caption"]))
            chart += 1
            i = j + 1
            continue
        if line.startswith("```"):
            j = i + 1
            code = []
            while j < len(lines) and lines[j] != "```":
                code.append(html.escape(lines[j]))
                j += 1
            story.append(Paragraph("<br/>".join(code), st["code"]))
            i = j + 1
            continue
        if line.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            story.append(make_table(lines[i:j], usable, st))
            i = j
            continue
        if line.startswith("## "):
            story.append(Paragraph(inline(line[3:]), st["h2"]))
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), st["h3"]))
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j].strip() and not lines[j].startswith(("#", "|", "```")):
            j += 1
        paragraph = " ".join(lines[i:j])
        style = st["caption"] if paragraph.startswith("Use [MODEL_REVIEW_GUIDE]") else st["body"]
        story.append(Paragraph(inline(paragraph), style))
        i = j
    assert chart == 4, f"Expected four diagrams, got {chart}"
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    for number, item in enumerate(diagrams, 1):
        image_path = Path(item.get("path", item.get("png", "")))
        if not image_path.is_absolute():
            image_path = diagram_dir / image_path
        orientation = item.get("orientation", "portrait")
        ps = landscape(A4) if orientation == "landscape" else A4
        available_w, available_h = ps[0] - 32 * mm, ps[1] - 36 * mm - 48
        picture = Image(str(image_path))
        factor = min(available_w / picture.imageWidth, available_h / picture.imageHeight)
        picture.drawWidth = picture.imageWidth * factor
        picture.drawHeight = picture.imageHeight * factor
        story.extend([
            NextPageTemplate(orientation), PageBreak(),
            Paragraph(f'<a name="figure{number}"/>Figure {number}. {item["title"]}', st["h2"]), picture,
            Spacer(1, 7), Paragraph("Arrows show the implemented sequence; observation inputs and targets remain separate.", st["caption"])])
    doc.build(story)
    receipt = {"source": str(SOURCE), "source_sha256": digest,
               "pdf": str(output.resolve()), "pdf_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
               "diagram_manifest": str(manifest_path), "diagram_count": chart,
               "code_revision_reviewed": "ff1a1df17381de3907f9799a56fb8f62008f6b47",
               "model_executed": False}
    output.with_suffix(".provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/pdf/DeepRootGen_Input_Layers_and_Model_Flow.pdf")
    parser.add_argument("--diagrams", type=Path, default=ROOT / "tmp/pdfs/input_layers/diagrams")
    args = parser.parse_args()
    build(args.output, args.diagrams)
