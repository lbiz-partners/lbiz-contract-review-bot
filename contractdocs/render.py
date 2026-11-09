"""DOCX → PDF(LibreOffice) → PNG(pdftoppm). 노무 봇과 같은 방식. 글꼴 별칭은 render/fonts.conf."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

FONTS_CONF = Path(__file__).resolve().parent.parent / "render" / "fonts.conf"


def docx_to_pdf(docx, outdir) -> Path:
    docx, outdir = Path(docx), Path(outdir)
    env = dict(os.environ)
    if FONTS_CONF.exists():
        env["FONTCONFIG_FILE"] = str(FONTS_CONF)
    profile = tempfile.mkdtemp(prefix="lo-legal-")
    try:
        subprocess.run(["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf",
                        "--outdir", str(outdir), str(docx)], check=True, capture_output=True, timeout=180, env=env)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return outdir / (docx.stem + ".pdf")


def pdf_to_png(pdf, dpi=100) -> list:
    pdf = Path(pdf)
    prefix = pdf.with_suffix("")
    for old in pdf.parent.glob(prefix.name + "-*.png"):
        old.unlink()
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), str(pdf), str(prefix)], check=True, capture_output=True, timeout=120)
    return sorted(pdf.parent.glob(prefix.name + "-*.png"))


def pdf_fonts(pdf) -> str:
    return subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout


def pdf_text(pdf) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
