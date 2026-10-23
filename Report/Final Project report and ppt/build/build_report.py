"""Builds the SonicVitals final report into the university template (Project Report Format-2026-AWS.docx).

    python build_report.py            # writes ../SonicVitals_Final_Project_Report.docx and .pdf

Two passes: the first renders the document to PDF to find the page of every heading, the second writes the
contents page with those page numbers.
"""
import copy
import io
import os
import re
import subprocess
import sys

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import report_content as rc  # noqa: E402

TEMPLATE = '/Users/pratikkumar/Downloads/Project Report Format-2026-AWS.docx'
OUT_DIR = os.path.dirname(HERE)
OUT = os.path.join(OUT_DIR, 'SonicVitals_Final_Project_Report.docx')
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
SOFFICE = ('/Users/pratikkumar/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/'
           'f60764cc-15a7-40dd-9c7a-d92c406e07b4/10c211b4-b59a-44b4-bd1a-2292c6919fbb/skills/docx/scripts/office/soffice.py')
FONT = 'Times New Roman'
TEXT_W_CM = 15.8                 # A4 width minus the template margins (2.96 + 1.94 cm)
MAX_FIG_H_CM = 17.5


# ---------------------------------------------------------------- helpers
def set_run_font(run, size=12, bold=None, italic=None, name=FONT, color=None):
    run.font.name = name
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), name)
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def set_text(p, text, size=None, bold=None, highlight=False):
    """Replace a template paragraph's text, keeping its first run's formatting."""
    runs = p.runs
    if not runs:
        r = p.add_run(text)
    else:
        r = runs[0]
        r.text = text
        for extra in runs[1:]:
            extra._element.getparent().remove(extra._element)
    if size:
        r.font.size = Pt(size)
    if bold is not None:
        r.bold = bold
    if highlight:
        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return r


def spacing(p, line=1.5, before=0, after=6):
    pf = p.paragraph_format
    pf.line_spacing = line
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)


class Numbering:
    """Bullet and [n] reference list definitions added to the template's numbering part."""

    def __init__(self, doc):
        self.el = doc.part.numbering_part.element
        self.next_abs = max([int(a.get(qn('w:abstractNumId'))) for a in self.el.findall(qn('w:abstractNum'))] + [0]) + 1
        self.next_num = max([int(n.get(qn('w:numId'))) for n in self.el.findall(qn('w:num'))] + [0]) + 1

    def _add(self, fmt, text, font=None, left=720, hanging=360):
        a = self.next_abs
        rpr = f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:hint="default"/></w:rPr>' if font else ''
        abstract = parse_xml(
            f'<w:abstractNum {nsdecls("w")} w:abstractNumId="{a}"><w:multiLevelType w:val="singleLevel"/>'
            f'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/>'
            f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{left}" w:hanging="{hanging}"/></w:pPr>{rpr}</w:lvl>'
            f'</w:abstractNum>')
        first_num = self.el.find(qn('w:num'))
        if first_num is not None:
            first_num.addprevious(abstract)
        else:
            self.el.append(abstract)
        n = self.next_num
        self.el.append(parse_xml(f'<w:num {nsdecls("w")} w:numId="{n}"><w:abstractNumId w:val="{a}"/></w:num>'))
        self.next_abs += 1
        self.next_num += 1
        return n

    def bullet(self):
        return self._add('bullet', '•', font='Arial')

    def refs(self):
        return self._add('decimal', '[%1]', left=567, hanging=567)


def apply_num(p, num_id):
    ppr = p._p.get_or_add_pPr()
    numpr = parse_xml(f'<w:numPr {nsdecls("w")}><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>')
    ppr.insert(0, numpr) if ppr.find(qn('w:pStyle')) is None else ppr.find(qn('w:pStyle')).addnext(numpr)


def table_borders(table):
    tblpr = table._tbl.tblPr
    borders = parse_xml(f'<w:tblBorders {nsdecls("w")}>' + ''.join(
        f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
        for e in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>')
    tblpr.append(borders)


def shade(cell, color='E7EEEA'):
    cell._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{color}"/>'))


def extract_code(path, name, max_lines=60):
    """Source of a Python def/class (or a C function) by name, trimmed to max_lines."""
    lines = open(path).read().split('\n')
    start = next(i for i, l in enumerate(lines) if re.match(rf'\s*(def|class)\s+{re.escape(name)}\b', l)
                 or re.match(rf'^\w[\w\s\*]*\b{re.escape(name)}\s*\(', l))
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for l in lines[start + 1:]:
        if path.endswith('.py'):
            if l.strip() and (len(l) - len(l.lstrip())) <= indent and not l.lstrip().startswith((')', ']', '#')):
                break
        else:
            out.append(l)
            if l.startswith('}'):
                break
            continue
        out.append(l)
    while out and not out[-1].strip():
        out.pop()
    if len(out) > max_lines:
        out = out[:max_lines] + ['    # ... (continues)']
    return out


# ---------------------------------------------------------------- document assembly
class Report:
    def __init__(self, page_numbers=None):
        self.doc = docx.Document(TEMPLATE)
        self.pages = page_numbers or {}
        self.num = Numbering(self.doc)
        self.bullet_id = self.num.bullet()
        self.toc = []                       # (level, text) in order

    # -- template parts
    def cover_and_summary(self):
        """Cover page in the school's layout (title, degree, students, guide, logo, date), then the summary."""
        body = list(self.doc.element.body.iterchildren())
        logo = body[22]                          # the template's VIT logo paragraph (removed below)
        summary_head, summary = body[30], body[32]
        for i in list(range(0, 30)) + [33, 34]:
            body[i].getparent().remove(body[i])

        def line(runs, size, bold=False, italic=False, after=0, before=0):
            para = self.doc.add_paragraph()
            summary_head.addprevious(para._p)
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            spacing(para, 1.0, before, after)
            for text, hl in runs:
                r = para.add_run(text)
                set_run_font(r, size, bold=bold, italic=italic)
                if hl:
                    r.font.highlight_color = WD_COLOR_INDEX.YELLOW
            return para

        line([(rc.TITLE, False)], 18, bold=True, after=66)
        line([('Submitted in partial fulfillment of the requirements for the degree of', False)], 14, italic=True, after=18)
        line([('Bachelor of Technology', False)], 21, bold=True, after=4)
        line([('School of Electronics Engineering (SENSE)', False)], 21, bold=True, after=64)
        line([('by', False)], 14, italic=True, after=10)
        for name in ('Pratik Kumar (24BML0027)', 'Uday Krishan Khandelwal (24BML0012)', 'Janhavee Dhote (24BML0120)'):
            line([(name, False)], 15, bold=True, after=8)
        line([('Under the guidance of', False)], 15, bold=True, before=56, after=14)
        line([('Jeeva J. B.', False)], 15, bold=True, after=6)
        line([('Professor Grade 1, SENSE', False)], 13)
        # the template's logo floats; place the same picture inline and centred so it keeps its own space
        rid = logo.find('.//' + qn('a:blip')).get(qn('r:embed'))
        lp = line([], 12, before=44, after=40)
        lp.add_run().add_picture(io.BytesIO(self.doc.part.related_parts[rid].blob), width=Cm(6.67))
        line([('October 2026', False)], 14)

        # executive summary starts on its own page: one paragraph, TNR 12, 1.15 spacing
        docx.text.paragraph.Paragraph(summary_head, self.doc._body).paragraph_format.page_break_before = True
        p = docx.text.paragraph.Paragraph(summary, self.doc._body)
        r = set_text(p, rc.EXEC_SUMMARY)
        set_run_font(r, 12)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        spacing(p, 1.15, 0, 6)

    def _mark_placeholders(self, paras, pattern=r'\[Register Number\]'):
        for p in paras:
            text = p.text
            m = re.search(pattern, text)
            if not m:
                continue
            base = p.runs[0]
            base.text = text[:m.start()]
            hl = copy.deepcopy(base._element)
            base._element.addnext(hl)
            hl_run = docx.text.run.Run(hl, p)
            hl_run.text = m.group(0)
            hl_run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            tail = copy.deepcopy(base._element)
            hl.addnext(tail)
            docx.text.run.Run(tail, p).text = text[m.end():]

    def strip_template_body(self):
        """Remove the template's sample contents list, introduction and references (kept: cover, summary,
        the section breaks and the final section properties)."""
        body = self.doc.element.body
        kids = list(body.iterchildren())
        # locate the contents heading paragraph and the section break that ends the contents page
        idx_contents = next(i for i, k in enumerate(kids) if 'CONTENTS' in ''.join(t.text or '' for t in k.iter(qn('w:t'))))
        sect_breaks = [i for i, k in enumerate(kids) if k.tag == qn('w:p') and k.find('.//' + qn('w:sectPr')) is not None]
        end_contents = next(i for i in sect_breaks if i > idx_contents)
        self.contents_anchor = kids[end_contents]
        for k in kids[idx_contents:end_contents]:
            body.remove(k)
        for k in kids[end_contents + 1:]:
            if k.tag != qn('w:sectPr'):
                body.remove(k)

    def contents(self):
        anchor = self.contents_anchor
        def add(text, level, page, bold=False):
            p = self.doc.add_paragraph()
            anchor.addprevious(p._p)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(TEXT_W_CM - 0.2), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            p.paragraph_format.left_indent = Cm({1: 0, 2: 0.6, 3: 1.2}[level])
            r = p.add_run(f'{text}\t{page}')
            set_run_font(r, 12 if level == 1 else 11, bold=bold)
            spacing(p, 1.15, 0, 3 if level == 1 else 0)
        h = self.doc.add_paragraph()
        anchor.addprevious(h._p)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(h.add_run('CONTENTS'), 16, bold=True)
        spacing(h, 1.15, 0, 12)
        add('Executive Summary', 1, 'ii', bold=True)
        for level, text in self.toc:
            if level <= 2:
                add(text, level, self.pages.get(text, '00'), bold=(level == 1))

    # -- content blocks
    def h1(self, text):
        p = self.doc.add_paragraph(style='Heading 1')
        p.paragraph_format.page_break_before = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.add_run(text), 16, bold=True)
        spacing(p, 1.15, 0, 14)
        self.toc.append((1, text))

    def h2(self, text):
        p = self.doc.add_paragraph(style='Heading 2')
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.keep_with_next = True
        set_run_font(p.add_run(text), 14, bold=True)
        spacing(p, 1.15, 10, 6)
        self.toc.append((2, text))

    def h3(self, text):
        p = self.doc.add_paragraph(style='Heading 3')
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.keep_with_next = True
        set_run_font(p.add_run(text), 12, bold=True)
        spacing(p, 1.15, 8, 4)
        self.toc.append((3, text))

    def para(self, text):
        p = self.doc.add_paragraph(style='Body Text')
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        set_run_font(p.add_run(text), 12)
        spacing(p, 1.5, 0, 6)

    def bullets(self, items):
        for it in items:
            p = self.doc.add_paragraph(style='List Paragraph')
            apply_num(p, self.bullet_id)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            set_run_font(p.add_run(it), 12)
            spacing(p, 1.5, 0, 3)

    def eq(self, text):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(p.add_run(text), 12, italic=True)
        spacing(p, 1.15, 2, 8)

    def fig(self, path, caption, width_cm):
        w, h = Image.open(path).size
        width = min(width_cm, TEXT_W_CM, MAX_FIG_H_CM * w / h)
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(path, width=Cm(width))
        spacing(p, 1.0, 6, 2)
        c = self.doc.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_run_font(c.add_run(caption), 10.5, bold=True)
        spacing(c, 1.15, 0, 10)

    def table(self, caption, rows, widths):
        c = self.doc.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        c.paragraph_format.keep_with_next = True
        set_run_font(c.add_run(caption), 10.5, bold=True)
        spacing(c, 1.15, 6, 4)
        t = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        table_borders(t)
        scale = min(1.0, TEXT_W_CM / sum(widths))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                cell = t.cell(i, j)
                cell.width = Cm(widths[j] * scale)
                p = cell.paragraphs[0]
                bold = i == 0 or (row[0] in ('Total',) and j in (0, 2)) or 'SonicVitals (gated)' in row[0]
                set_run_font(p.add_run(str(val)), 10, bold=bold)
                spacing(p, 1.0, 1, 1)
                if i == 0:
                    shade(cell)
        after = self.doc.add_paragraph()
        spacing(after, 1.0, 0, 4)

    def references(self):
        self.h1('10. REFERENCES')
        ref_id = self.num.refs()
        for ref in rc.REFERENCES:
            p = self.doc.add_paragraph(style='List Paragraph')
            apply_num(p, ref_id)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            set_run_font(p.add_run(ref), 11)
            spacing(p, 1.15, 0, 4)

    def appendix(self):
        self.h1('APPENDIX-1: SOURCE CODE (KEY FUNCTIONS)')
        self.para('The complete source code (firmware, Python engine, dashboard, benchmark and 79 automated tests) is '
                  'part of the project repository. The listings below show the core of the signal processing.')
        listings = [
            ('A1.1 CHROM pulse extraction (backend/vitals_dsp.py)', os.path.join(REPO, 'backend', 'vitals_dsp.py'), 'chrom_pulse', 30),
            ('A1.2 de Haan signal-to-noise ratio (backend/vitals_dsp.py)', os.path.join(REPO, 'backend', 'vitals_dsp.py'), 'dehaan_snr', 20),
            ('A1.3 Robust consensus of all methods (backend/display_stabilizer.py)', os.path.join(REPO, 'backend', 'display_stabilizer.py'), 'robust_consensus', 30),
        ]
        for title, path, name, n in listings:
            self.h3(title)
            try:
                code = extract_code(path, name, n)
            except StopIteration:
                continue
            for line in code:
                p = self.doc.add_paragraph()
                r = p.add_run(line.replace('\t', '    ') or ' ')
                set_run_font(r, 8, name='Courier New')
                spacing(p, 1.0, 0, 0)

    def page_numbers(self):
        sec = self.doc.sections[-1]
        sec.footer.is_linked_to_previous = False
        pg = sec._sectPr.find(qn('w:pgNumType'))
        if pg is None:
            pg = parse_xml(f'<w:pgNumType {nsdecls("w")} w:start="1"/>')
            sec._sectPr.append(pg)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = fp.add_run()
        for x in (f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>', f'<w:instrText {nsdecls("w")} xml:space="preserve"> PAGE </w:instrText>',
                  f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'):
            r._r.append(parse_xml(x))
        set_run_font(r, 11)
        sec.footer_distance = Cm(0.3)

    def build(self):
        self.cover_and_summary()
        self.strip_template_body()
        for block in rc.CONTENT:
            kind = block[0]
            if kind == 'h1':
                self.h1(block[1])
            elif kind == 'h2':
                self.h2(block[1])
            elif kind == 'h3':
                self.h3(block[1])
            elif kind == 'p':
                self.para(block[1])
            elif kind == 'bullets':
                self.bullets(block[1])
            elif kind == 'eq':
                self.eq(block[1])
            elif kind == 'fig':
                self.fig(block[1], block[2], block[3])
            elif kind == 'table':
                self.table(block[1], block[2], block[3])
        self.references()
        self.appendix()
        self.page_numbers()
        self.contents()
        self.doc.save(OUT)
        return OUT


def render_pdf(path):
    """docx -> pdf through Apple Pages (pages_pdf.sh); Word and LibreOffice are not installed on this Mac."""
    pdf = os.path.splitext(path)[0] + '.pdf'
    subprocess.run([os.path.join(HERE, 'pages_pdf.sh'), path, pdf], check=True, capture_output=True)
    return pdf


def heading_pages(pdf, toc):
    """Printed page number of every heading (numbering restarts at 1 on the first chapter page)."""
    import fitz
    doc = fitz.open(pdf)
    texts = [doc[i].get_text() for i in range(len(doc))]
    norm = lambda s: re.sub(r'\s+', ' ', s).strip()
    first = next(i for i, t in enumerate(texts) if 'CONTENTS' in t) + 1      # skip the contents page itself
    pages, start, k = {}, None, first
    for level, text in toc:
        for i in range(k, len(texts)):
            if norm(text) in norm(texts[i]) and (start is not None or level == 1):
                if start is None:
                    start = i
                pages[text] = i - start + 1
                k = i
                break
    return pages, len(doc)


if __name__ == '__main__':
    first = Report()
    out = first.build()
    pages, n = heading_pages(render_pdf(out), first.toc)
    final = Report(pages)
    final.build()
    pdf = render_pdf(OUT)
    pages2, n2 = heading_pages(pdf, final.toc)
    print(f'{OUT}\n{pdf}\n{n2} PDF pages; contents numbers stable: {pages == pages2}')
