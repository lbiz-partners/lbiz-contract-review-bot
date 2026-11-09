"""계약서 도우미 — 계약서 초안 생성기(make)와 독소조항 점검기(review). 결정론: 같은 입력이면 같은 결과."""
from pathlib import Path

def _read_version():
    p = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return p.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"

__version__ = _read_version()


def tool_version_label():
    """결과물(초안·리포트)에 찍는 짧은 판 표시. 예: 도구 판 v1.2"""
    return f"도구 판 v{__version__}"
