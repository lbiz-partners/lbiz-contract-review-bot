"""점검 결과 → 리포트(MD, DOCX→PDF). 면책 고지는 맨 위 한 번만."""
import json
from pathlib import Path

from .. import __version__, tool_version_label
from ..docx_builder import Doc
from ..laws import LAWS, cite
from ..render import docx_to_pdf, pdf_to_png
from . import catalog, rules
from .extract import extract
from .score import IDS, normalize, score_confirmed

DISCLAIMER = "변호사 검토 전 참고용 초안입니다. 사장님이 올린 계약서를 정해진 점검표로 기계적으로 살펴본 결과이며, 법률 자문이 아닙니다. 분쟁·소송·최종 판단은 변호사와 상담하세요."


def review(path_or_text, side="을", confirm=(), reject=(), is_text=False):
    text = path_or_text if is_text else extract(path_or_text)
    res = rules.analyze(text, side)
    auto = [h["id"] for h in res["toxic"] if h["status"] == "확정"]
    conf = [normalize(x) for x in confirm if normalize(x)]
    rej = [normalize(x) for x in reject if normalize(x)]
    final = [i for i in IDS if (i in auto or i in conf) and i not in rej]
    res["adjust"] = {"confirm": conf, "reject": rej}
    res["final_ids"] = final
    res["score"] = score_confirmed(final)
    return res


def _basis_lines(keys):
    out = []
    for k in keys:
        law = LAWS.get(k)
        tag = "원문 대조 ✅" if law and law[4] else "[확인 필요]"
        out.append(f"{cite(k)} — {law[3] if law else ''} ({tag})")
    return out


def to_md(res, name="계약서"):
    sc = res["score"]
    L = [f"> ⚖️ {DISCLAIMER}", "", f"# 계약서 점검 리포트 — {name}", "",
         f"- 관점: 사장님 = **{res['side']}**",
         f"- 위험 점수: **{sc['점수']}점 / 100 · {sc['등급']}** (같은 계약서면 늘 같은 점수)",
         f"- 독소 확정 {len(res['final_ids'])}건: " + (", ".join(f"{i} {catalog.TOXIC[i]['name']}" for i in res["final_ids"]) or "없음"),
         f"- {'서명 전 변호사 검토를 권합니다.' if sc['변호사_검토_필수'] else '협상으로 고칠 수 있는 수준입니다.'}",
         f"- {tool_version_label()}"]
    if res["adjust"]["confirm"] or res["adjust"]["reject"]:
        L.append(f"- 원문을 읽고 조정함: 추가 {res['adjust']['confirm'] or '없음'} / 제외 {res['adjust']['reject'] or '없음'}")
    L += ["", "## 독소조항 12종 점검표", "", "| # | 항목 | 결과 | 위험 | 위치 |", "|---|---|---|---|---|"]
    byid = {}
    for h in res["toxic"]:
        byid.setdefault(h["id"], h)
    for i in IDS:
        h = byid.get(i)
        st = "확정" if i in res["final_ids"] else ("후보(확인 필요)" if h and h["status"] == "후보" and i not in res["adjust"]["reject"] else "없음")
        L.append(f"| {i} | {catalog.TOXIC[i]['name']} | {st} | {catalog.TOXIC[i]['risk'] if st != '없음' else '—'} | {h['clause'] if h else ''} |")
    L += ["", "## 고칠 곳과 제안 문장", ""]
    if not res["final_ids"]:
        L.append("확정된 독소조항이 없습니다.")
    for i in res["final_ids"]:
        c, h = catalog.TOXIC[i], byid.get(i)
        L += [f"### {i} {c['name']} {c['risk']}", ""]
        if h:
            L += [f"**지금 문장 ({h['clause']})**", f"> {h['quote']}", ""]
        L += [f"**왜 위험한가요?** {c['why']}", "", "**참고 조문**"]
        L += [f"- {x}" for x in _basis_lines(c["basis"])]
        L += ["", "**이렇게 고쳐 보세요**"] + [f"> {x}" for x in c["fix"]]
        L += ["", f"**말하는 방법** — 부드럽게: \"{c['soft']}\" / 분명하게: \"{c['firm']}\"", ""]
    cands = [h for h in res["toxic"] if h["status"] == "후보" and h["id"] not in res["final_ids"] and h["id"] not in res["adjust"]["reject"]]
    if cands:
        L += ["## 원문을 한 번 더 볼 곳 (점수에 넣지 않음)", ""]
        L += [f"- {h['id']} {catalog.TOXIC[h['id']]['name']} ({h['clause']}): \"{h['quote']}\" — {h['note']}" for h in cands]
        L.append("")
    if res.get("kind") == "nda":
        L += ["## 비밀유지계약 기본 확인", "", "비밀유지계약이라 7대 필수 조항·미수금 장치 점검은 하지 않았습니다. 양쪽 모두 의무가 있는지(⑨), 기간·예외·반환 조항이 있는지 직접 확인해 보세요.", ""]
        return _tail(L, res)
    L += ["## 7대 필수 조항", "", "| 조항 | 있음 | 명확 | 위치 | 없거나 모호하면 |", "|---|---|---|---|---|"]
    for r, (n, tip, key) in zip(res["essential"], catalog.ESSENTIAL):
        L.append(f"| {n} | {'✅' if r['present'] else '❌'} | {r['clear']} | {r['where']} | {'' if r['present'] and r['clear'] == '✅' else tip} |")
    L += ["", "## 자주 빠지는 5가지", "", "| 조항 | 있음 | 없으면 넣을 문장 |", "|---|---|---|"]
    for r, (n, ex) in zip(res["missing5"], catalog.MISSING5):
        L.append(f"| {n} | {'✅' if r['present'] else '❌'} | {'' if r['present'] else ex} |")
    L += ["", "## 미수금 막는 5가지 장치", "", "| 장치 | 적용 | 메모 |", "|---|---|---|"]
    for r, (n, key) in zip(res["payment5"], catalog.PAYMENT5):
        L.append(f"| {n} | {'✅' if r['applied'] else '❌'} | {r['note']}{(' · ' + cite(key)) if key and not r['applied'] else ''} |")
    return _tail(L, res)


def _tail(L, res):
    L += ["", "## 변호사에게 꼭 물어볼 것", ""]
    qs = []
    if "⑩" in res["final_ids"]:
        qs.append("대표 개인 연대보증을 빼지 못하면 서명해도 되는지")
    if "④" in res["final_ids"] or "③" in res["final_ids"]:
        qs.append("배상·위약금 한도를 얼마로 정하는 게 우리 업종에 맞는지")
    qs += ["이 계약서가 약관규제법·하도급법 적용 대상인지", "이미 서명했다면 지금이라도 고칠 수 있는지"]
    L += [f"{n}. {q}" for n, q in enumerate(qs, 1)]
    L += ["", "## 적용 범위 안내", "", catalog.APPLICABILITY, ""]
    return "\n".join(L) + "\n"


def to_docx(md_text, path):
    """MD 리포트를 같은 내용의 DOCX로(간단 변환: 제목·표·인용·목록)."""
    lines = md_text.splitlines()
    first = lines[0].lstrip("> ⚖️").strip() if lines and lines[0].startswith(">") else None
    title = next((l[2:] for l in lines if l.startswith("# ")), "계약서 점검 리포트")
    doc = Doc(title, disclaimer=first)
    table = []

    def flush():
        if table:
            rows = [r for r in table if not set(r.replace("|", "").strip()) <= set("-: ")]
            doc.table([[c.strip().replace("**", "") for c in r.strip().strip("|").split("|")] for r in rows], size=8.5)
            table.clear()

    for l in lines[1:]:
        if l.startswith("|"):
            table.append(l)
            continue
        flush()
        if l.startswith("# ") or not l.strip():
            continue
        if l.startswith("### "):
            doc.heading(l[4:], size=10.5)
        elif l.startswith("## "):
            doc.heading(l[3:], size=12)
        elif l.startswith("> "):
            doc.para(l[2:].replace("**", ""), indent_mm=6, color=(40, 70, 130))
        elif l.startswith("- "):
            doc.para("• " + l[2:].replace("**", ""), indent_mm=2)
        else:
            doc.para(l.replace("**", ""))
    flush()
    doc.save(path)


def write(res, outdir, stem, name=None, pdf=True, png=True):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    md = to_md(res, name or stem)
    mdp = outdir / f"{stem}.점검리포트.md"
    mdp.write_text(md, encoding="utf-8")
    out = {"md": str(mdp), "score": res["score"], "final_ids": res["final_ids"], "tool_version": __version__}
    dx = outdir / f"{stem}.점검리포트.docx"
    to_docx(md, dx)
    out["docx"] = str(dx)
    if pdf:
        p = docx_to_pdf(dx, outdir)
        out["pdf"] = str(p)
        if png:
            out["png"] = [str(x) for x in pdf_to_png(p)]
    (outdir / f"{stem}.점검결과.json").write_text(json.dumps({**res, "files": out}, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
