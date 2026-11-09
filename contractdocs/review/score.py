#!/usr/bin/env python3
"""독소조항 위험도 결정론 채점 — legal v3.4.0 scripts/score.py 와 같은 공식(시험이 원본과 전수 대조).
  🔴 확정 1건 = 20(15 + 빨강영역 가산 5), 🟡 = 8, 상한 100. 0~30 🟢 / 31~60 🟡 / 61~100 🔴.
  🔴 floor: 🔴 1건 → 최소 🟡, 2건 이상 → 🔴. 🔴 1건 이상이면 변호사 검토 권고(True).
순수함수 — 네트워크·난수·시간 의존 없음."""
from __future__ import annotations

import argparse
import json
import sys

TOXIC = {
    "①": ("일방 해지권", "🔴"), "②": ("무한 수정 요청", "🔴"), "③": ("과도한 위약금", "🔴"),
    "④": ("무한 책임", "🔴"), "⑤": ("일방 저작권 양도", "🟡"), "⑥": ("자동 갱신 + 단축 통지", "🟡"),
    "⑦": ("상대방 본사 관할", "🟡"), "⑧": ("일방 수정권", "🔴"), "⑨": ("일방 비밀유지 의무", "🟡"),
    "⑩": ("연대보증", "🔴"), "⑪": ("선급금 0원·후불 100%", "🟡"), "⑫": ("검수 권한 일방", "🔴"),
}
IDS = list(TOXIC)
_NUM2CIRCLE = {str(i): c for i, c in enumerate(IDS, start=1)}
RED = {k for k, (_, r) in TOXIC.items() if r == "🔴"}
RED_WEIGHT, YELLOW_WEIGHT = 20, 8


def normalize(token: str) -> str | None:
    t = token.strip().strip(".)·号 ")
    if t in TOXIC:
        return t
    return _NUM2CIRCLE.get(t)


def score_confirmed(confirmed_ids: list[str]) -> dict:
    seen, unknown = [], []
    for raw in confirmed_ids:
        cid = normalize(raw)
        if cid is None:
            if raw.strip():
                unknown.append(raw.strip())
        elif cid not in seen:
            seen.append(cid)
    breakdown, score = [], 0
    for cid in seen:
        name, risk = TOXIC[cid]
        w = RED_WEIGHT if cid in RED else YELLOW_WEIGHT
        score += w
        breakdown.append({"id": cid, "name": name, "risk": risk, "weight": w})
    score = min(score, 100)
    base_idx = 0 if score <= 30 else (1 if score <= 60 else 2)
    red_count = sum(1 for b in breakdown if b["risk"] == "🔴")
    floor_idx = 2 if red_count >= 2 else (1 if red_count >= 1 else 0)
    grade_idx = max(base_idx, floor_idx)
    lawyer = score >= 61 or red_count > 0
    if lawyer:
        reason = "🔴 위험 등급" if grade_idx == 2 else f"🔴 독소 {red_count}건 — 서명 전 변호사 검토 권고"
    else:
        reason = "협상 권고 수준"
    return {"점수": score, "등급": ["🟢 양호", "🟡 주의", "🔴 위험"][grade_idx], "확정_독소": breakdown,
            "변호사_검토_필수": lawyer, "사유": reason, "미인식_입력": unknown}


def main() -> int:
    ap = argparse.ArgumentParser(description="독소조항 위험도 결정론 채점")
    ap.add_argument("--confirmed", required=True, help='확정 독소 id, 쉼표 구분. 예: "①,④,⑩" 또는 "1,4,10"')
    a = ap.parse_args()
    print(json.dumps(score_confirmed([x for x in a.confirmed.replace(" ", "").split(",") if x]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
