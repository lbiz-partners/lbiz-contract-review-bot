"""계약서 도우미 명령
  python3 -m contractdocs check  입력.json                  # 입력 점검만(빈칸·민감정보·위험한 값)
  python3 -m contractdocs make   입력.json [출력폴더] [--no-pdf]
  python3 -m contractdocs review 계약서.(txt|md|docx|pdf|hwpx|hwp) [출력폴더] [--side 을|갑] [--confirm ①,④] [--reject ⑪] [--no-pdf]
  python3 -m contractdocs score  --confirmed "①,④,⑩"
  python3 -m contractdocs laws                               # 근거 조문 대조표
"""
import json
import sys
from pathlib import Path


def _opt(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else default
    return default


def _pos(argv):
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in ("--side", "--confirm", "--reject", "--confirmed"):
            skip = True
            continue
        if not a.startswith("--"):
            out.append(a)
    return out


def main(argv):
    if not argv or argv[0] not in ("check", "make", "review", "score", "laws"):
        print(__doc__)
        return 2
    cmd, pos = argv[0], _pos(argv[1:])
    if cmd == "score":
        from .review.score import score_confirmed
        ids = [x for x in (_opt(argv, "--confirmed", "") or "").replace(" ", "").split(",") if x]
        print(json.dumps(score_confirmed(ids), ensure_ascii=False, indent=2))
        return 0
    if cmd == "laws":
        from .laws import table_rows
        for r in table_rows():
            print(f"{'✅' if r['verified'] else '[확인 필요]'} {r['law']} {r['jo']}({r['title']}) — {r['source']}")
        return 0
    if cmd in ("check", "make"):
        from . import checks
        from .generate import Blocked, generate
        data = json.load(open(pos[0], encoding="utf-8"))
        if cmd == "check":
            rep = checks.check(data)
            for f in rep.findings:
                print(f"[{f.level}] {f.msg}" + (f" — {f.basis}" if f.basis else ""))
            return 1 if rep.codes("error") else 0
        try:
            out = generate(data, pos[1] if len(pos) > 1 else "out", pdf="--no-pdf" not in argv)
        except Blocked as b:
            for f in b.report.findings:
                print(f"[{f.level}] {f.msg}")
            print("민감정보 등이 있어 서류를 만들지 않았습니다.")
            return 3
        print(json.dumps({k: out[k] for k in out if k != "report"}, ensure_ascii=False, indent=2))
        return 0
    from .review.extract import ExtractError
    from .review.report import review, write
    src = Path(pos[0])
    conf = [x for x in (_opt(argv, "--confirm", "") or "").split(",") if x]
    rej = [x for x in (_opt(argv, "--reject", "") or "").split(",") if x]
    try:
        res = review(src, side=_opt(argv, "--side", "을"), confirm=conf, reject=rej)
    except ExtractError as e:
        print(f"파일을 읽지 못했습니다: {e}")
        return 4
    out = write(res, pos[1] if len(pos) > 1 else "out", src.stem, pdf="--no-pdf" not in argv)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
