"""입력 JSON 하나 → 점검 결과 + DOCX + MD (+PDF/PNG). 노무 봇(nomudocs.generate)과 같은 흐름."""
import json
from pathlib import Path

from . import __version__, checks, tool_version_label
from .docx_builder import BLANK, DISCLAIMER, Doc, v, ymd
from .laws import cite
from .render import docx_to_pdf, pdf_to_png
from .templates import BUILDERS

NAMES = {"outsourcing": "외주용역계약서", "service": "용역계약서", "nda": "비밀유지계약서"}
BASIS = {  # 작성 메모에 붙일 근거(모두 원문 대조된 키)
    "outsourcing": ["민법664", "민법665", "민법544", "민법673", "민법393", "민법398", "저작권법45", "상법54", "민소법29"],
    "service": ["민법689", "민법393", "민법398", "상법54", "민소법29"],
    "nda": ["부경법2", "부경법10", "민법390", "민소법29"],
}


class Blocked(Exception):
    def __init__(self, report):
        super().__init__("민감정보가 있어 서류를 만들지 않았습니다.")
        self.report = report


def build_docx(spec, path):
    doc = Doc(spec["title"])
    doc.para(spec["preamble"])
    for i, (title, items) in enumerate(spec["articles"], 1):
        doc.article(i, title, items)
    doc.para("")
    doc.para(spec["closing"])
    doc.para(ymd(spec.get("date")), align="center", bold=True)
    rows = [["구분"] + [lab for lab, _ in spec["parties"]]]
    for key, label in (("name", "상호(성명)"), ("ceo", "대표자"), ("address", "주소"), ("biz_no", "사업자등록번호")):
        rows.append([label] + [v(p.get(key)) + ("  (인)" if key == "ceo" else "") for _, p in spec["parties"]])
    doc.table(rows, widths_mm=[30, 70, 70])
    doc.para("")
    doc.para(tool_version_label(), size=8, color=(120, 120, 120))
    doc.save(path)


def build_md(spec):
    circ = "①②③④⑤⑥⑦⑧⑨⑩"
    out = [f"> ⚖️ {DISCLAIMER}", "", f"# {spec['title']}", "", spec["preamble"], ""]
    for i, (title, items) in enumerate(spec["articles"], 1):
        out.append(f"**제{i}조 ({title})**")
        for j, it in enumerate(items):
            subs = []
            if isinstance(it, tuple):
                it, subs = it
            out.append(f"{circ[j] + ' ' if len(items) > 1 else ''}{it}")
            out += [f"   {k}. {s}" for k, s in enumerate(subs, 1)]
        out.append("")
    out += [spec["closing"], "", ymd(spec.get("date")), ""]
    out.append("| 구분 | " + " | ".join(l for l, _ in spec["parties"]) + " |")
    out.append("|---|" + "---|" * len(spec["parties"]))
    for key, label in (("name", "상호(성명)"), ("ceo", "대표자"), ("address", "주소"), ("biz_no", "사업자등록번호")):
        out.append(f"| {label} | " + " | ".join(v(p.get(key)) + (" (인)" if key == "ceo" else "") for _, p in spec["parties"]) + " |")
    out += ["", tool_version_label()]
    return "\n".join(out) + "\n"


def notes_md(data, rep, files):
    icon = {"missing": "[빈칸]", "error": "[고쳐야 함]", "warn": "[다시 보기]", "info": "[참고]"}
    lines = [f"# 작성 메모 — {NAMES[data['doc']]}", "", "## 입력 점검"]
    lines += [f"- {icon[f.level]} {f.msg}" + (f" — {f.basis}" if f.basis else "") for f in rep.findings] or ["- 빠진 칸 없음"]
    lines += ["", "## 이 양식에 들어간 안전장치", "- 양쪽 모두 해지권, 서면 합의로만 계약 변경, 손해배상 한도, 상호 비밀유지",
              "- (외주) 선급금·단계 지급, 검수 기한과 미통보 시 합격 간주, 수정 횟수 제한, 지연이자", "",
              "## 참고 조문 (법제처 원문 대조)"]
    lines += [f"- {cite(k)}" for k in BASIS[data["doc"]]]
    lines += ["", "## 서명 전 확인", "- [ ] 빈칸(＿＿)을 모두 채웠나요?", "- [ ] 상대방과 조건을 합의했나요?",
              "- [ ] 금액이 크거나 조건이 복잡하면 변호사 검토를 받았나요?", "", "만든 파일: " + ", ".join(Path(f).name for f in files if f),
              "", tool_version_label()]
    return "\n".join(lines) + "\n"


def generate(data, outdir, stem=None, pdf=True, png=True):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rep = checks.check(data)
    if "DOC_KIND" in rep.codes("error") or any(c.startswith("SENSITIVE_") and c != "SENSITIVE_ACCOUNT" for c in rep.codes("error")):
        raise Blocked(rep)
    safe = checks.mask(data)
    spec = BUILDERS[data["doc"]](safe)
    spec["date"] = safe.get("contract_date")
    stem = stem or NAMES[data["doc"]]
    dx, md = outdir / f"{stem}.docx", outdir / f"{stem}.md"
    build_docx(spec, dx)
    md.write_text(build_md(spec), encoding="utf-8")
    out = {"docx": str(dx), "md": str(md), "report": rep.as_dict(), "tool_version": __version__}
    if pdf:
        p = docx_to_pdf(dx, outdir)
        out["pdf"] = str(p)
        if png:
            out["png"] = [str(x) for x in pdf_to_png(p)]
    (outdir / f"{stem}.작성메모.md").write_text(notes_md(data, rep, [out.get("docx"), out.get("pdf")]), encoding="utf-8")
    (outdir / f"{stem}.점검결과.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
