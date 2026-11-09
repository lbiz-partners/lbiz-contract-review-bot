"""계약서 파일 → 텍스트. txt/md, docx, pdf(pdftotext), hwpx(내장 해석), hwp(pyhwp 의 hwp5txt 가 있으면)."""
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


class ExtractError(Exception):
    pass


def _read_text(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ExtractError("글자 인코딩을 알 수 없습니다.")


def _docx(p: Path) -> str:
    from docx import Document
    d = Document(str(p))
    out = [para.text for para in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            out.append(" | ".join(c.text for c in row.cells))
    return "\n".join(out)


def _pdf(p: Path) -> str:
    r = subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise ExtractError("PDF에서 글자를 꺼내지 못했습니다.")
    if len(r.stdout.strip()) < 20:
        raise ExtractError("PDF에 글자 층이 없습니다(스캔본일 수 있음). 글자가 있는 파일이나 사진 속 문장을 붙여 넣어 주세요.")
    return r.stdout


def _hwpx(p: Path) -> str:
    with zipfile.ZipFile(p) as z:
        secs = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n))
        if not secs:
            raise ExtractError("HWPX 본문을 찾지 못했습니다.")
        out = []
        for n in secs:
            xml = z.read(n).decode("utf-8")
            for para in re.findall(r"<hp:p\b.*?</hp:p>", xml, flags=re.S):
                out.append("".join(re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", para, flags=re.S)))
        return "\n".join(_unesc(x) for x in out)


def _unesc(s):
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


def _hwp(p: Path) -> str:
    exe = shutil.which("hwp5txt") or str(Path(sys.executable).parent / "hwp5txt")
    if not Path(exe).exists():
        raise ExtractError("HWP를 읽는 도구(pyhwp)가 없습니다. 한글에서 PDF나 DOCX로 저장해 올려 주세요.")
    r = subprocess.run([exe, str(p)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not r.stdout.strip():
        raise ExtractError("HWP를 읽지 못했습니다. 한글에서 PDF나 DOCX로 저장해 올려 주세요.")
    return r.stdout


def extract(path) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".txt", ".md", ""):
        return _read_text(p)
    if ext == ".docx":
        return _docx(p)
    if ext == ".pdf":
        return _pdf(p)
    if ext == ".hwpx":
        return _hwpx(p)
    if ext == ".hwp":
        return _hwp(p)
    raise ExtractError(f"{ext} 파일은 아직 못 읽습니다. PDF·DOCX·TXT로 올려 주세요.")
