"""DOCX 공통 부품 (노무 서류 봇 nomudocs/docx_builder.py 와 같은 규칙).
글꼴은 '맑은 고딕'으로 적고, 박스에서 PDF로 바꿀 때는 render/fonts.conf 별칭으로 Noto Sans CJK KR 로 그린다.
면책 고지는 문서 맨 위에 한 번만 넣는다(쪽마다 반복하는 바닥글을 쓰지 않는다)."""
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

FONT = "맑은 고딕"
BLANK = "＿＿＿＿＿＿"  # 손으로 채울 빈칸
DISCLAIMER = "변호사 검토 전 참고용 초안입니다. 사장님이 직접 입력한 내용으로 만든 양식이며, 서명 전 변호사 검토를 권합니다."


def set_font(run, size=None, bold=None, color=None):
    run.font.name = FONT
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    for k in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(k), FONT)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def _shade(cell, hex_fill):
    tcPr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


class Doc:
    def __init__(self, title, disclaimer=DISCLAIMER, base_size=10):
        self.d = Document()
        st = self.d.styles["Normal"]
        st.font.name = FONT
        st.font.size = Pt(base_size)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        pf = st.paragraph_format
        pf.space_after = Pt(3)
        pf.line_spacing = 1.25
        sec = self.d.sections[0]
        sec.page_width, sec.page_height = Mm(210), Mm(297)
        sec.left_margin = sec.right_margin = Mm(20)
        sec.top_margin, sec.bottom_margin = Mm(18), Mm(18)
        if disclaimer:
            self.notice(disclaimer)
        self.title(title)

    def notice(self, text):
        t = self.d.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        c = t.cell(0, 0)
        _shade(c, "F3F3F3")
        p = c.paragraphs[0]
        set_font(p.add_run("⚖ " + text), size=8.5, color=(80, 80, 80))
        self.d.add_paragraph()

    def title(self, text):
        p = self.d.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_font(p.add_run(text), size=17, bold=True)
        p.paragraph_format.space_after = Pt(10)

    def para(self, text, size=None, bold=False, align=None, indent_mm=0, color=None):
        p = self.d.add_paragraph()
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "right":
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if indent_mm:
            p.paragraph_format.left_indent = Mm(indent_mm)
        set_font(p.add_run(text), size=size, bold=bold, color=color)
        return p

    def heading(self, text, size=11.5):
        p = self.d.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.keep_with_next = True
        set_font(p.add_run(text), size=size, bold=True)

    def article(self, no, title, items):
        """제N조(제목) + 항 목록. items: str 또는 (str, [하위 목록])."""
        self.heading(f"제{no}조 ({title})", size=10.5)
        circ = "①②③④⑤⑥⑦⑧⑨⑩"
        multi = len(items) > 1
        for i, it in enumerate(items):
            subs = []
            if isinstance(it, tuple):
                it, subs = it
            self.para((circ[i] + " " if multi else "") + it, indent_mm=2)
            for j, s in enumerate(subs, 1):
                self.para(f"{j}. {s}", indent_mm=8)

    def table(self, rows, widths_mm=None, header=True, size=9):
        t = self.d.add_table(rows=len(rows), cols=len(rows[0]))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                cell = t.cell(r, c)
                cell.text = ""
                set_font(cell.paragraphs[0].add_run(str(val)), size=size, bold=(header and r == 0))
                if header and r == 0:
                    _shade(cell, "E8EEF7")
                if widths_mm:
                    cell.width = Mm(widths_mm[c])
        self.d.add_paragraph()
        return t

    def save(self, path):
        self.d.save(path)


def v(x, unit="", empty=BLANK):
    if x is None or x == "" or x == []:
        return empty
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return (f"{int(x):,}" if float(x).is_integer() else f"{x:,}") + unit
    return str(x) + unit


def won(x):
    return v(x, "원")


def ymd(s, empty=BLANK):
    if not s:
        return f"{empty}년 　월 　일"
    y, m, d = str(s)[:10].split("-")
    return f"{int(y)}년 {int(m)}월 {int(d)}일"
