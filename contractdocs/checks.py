"""입력 점검 — 빈칸·민감정보·위험한 선택값. 판정이 아니라 '다시 보시라'는 알림이다.
level: missing(빈칸으로 인쇄됨) / error(그대로 만들면 안 됨) / warn(다시 보기) / info(참고)"""
import re
from dataclasses import asdict, dataclass, field

from .laws import cite

DOC_KINDS = {"outsourcing": "외주용역계약서", "service": "용역(컨설팅·강의)계약서", "nda": "상호 비밀유지계약서"}

RRN = re.compile(r"(?<!\d)\d{6}\s*-?\s*[1-8]\d{6}(?!\d)")
CARD = re.compile(r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)")
SECRET_KEYS = re.compile(r"비밀번호|password|passwd|pin|보안카드|otp|cvc|cvv", re.I)
ACCOUNT_KEYS = re.compile(r"계좌|account", re.I)


@dataclass
class Finding:
    level: str
    code: str
    msg: str
    basis: str = ""


@dataclass
class Report:
    findings: list = field(default_factory=list)

    def add(self, level, code, msg, basis=""):
        self.findings.append(Finding(level, code, msg, basis))

    def need(self, value, code, label):
        if value in (None, "", [], {}):
            self.add("missing", code, f"'{label}' 칸이 비어 있어 빈칸으로 인쇄됩니다.")
            return False
        return True

    def codes(self, level=None):
        return [f.code for f in self.findings if level is None or f.level == level]

    def as_dict(self):
        return {"findings": [asdict(f) for f in self.findings]}


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, x in obj.items():
            yield from _walk(x, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            yield from _walk(x, f"{path}[{i}]")
    else:
        yield path, obj


def sensitive(data, rep):
    for path, val in _walk(data):
        key = path.rsplit(".", 1)[-1]
        s = "" if val is None else str(val)
        if SECRET_KEYS.search(key) and s:
            rep.add("error", "SENSITIVE_SECRET", f"'{path}'에 비밀번호류 값이 있습니다. 계약서에는 필요 없으니 지워 주세요.")
        if RRN.search(s):
            rep.add("error", "SENSITIVE_RRN", f"'{path}'에 주민등록번호로 보이는 숫자가 있습니다. 계약서에는 넣지 않습니다.")
        if CARD.search(s):
            rep.add("error", "SENSITIVE_CARD", f"'{path}'에 카드번호로 보이는 숫자가 있습니다.")
        if ACCOUNT_KEYS.search(key) and s:
            rep.add("warn", "SENSITIVE_ACCOUNT", f"'{path}' 계좌번호는 계약서에 꼭 필요하지 않아 가려서 인쇄합니다.")


def mask(data):
    if isinstance(data, dict):
        return {k: ("***(가림)" if ACCOUNT_KEYS.search(k) and v else mask(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [mask(x) for x in data]
    return data


def splits(data):
    sp = data.get("payment_split") or [30, 50, 20]
    total = data.get("total")
    if not isinstance(total, (int, float)):
        return sp, [None] * len(sp)
    amts = [int(total * p // 100) for p in sp]
    amts[-1] = int(total) - sum(amts[:-1])
    return sp, amts


def check(data):
    rep = Report()
    doc = data.get("doc")
    if doc not in DOC_KINDS:
        rep.add("error", "DOC_KIND", f"doc 값은 {', '.join(DOC_KINDS)} 중 하나여야 합니다.")
        return rep
    sensitive(data, rep)
    a, b = data.get("party_a") or {}, data.get("party_b") or {}
    rep.need(a.get("name"), "A_NAME", "갑 회사명")
    rep.need(b.get("name"), "B_NAME", "을 회사명(성명)")
    rep.need(data.get("contract_date"), "DATE", "계약일")
    if data.get("my_side") not in (None, "갑", "을"):
        rep.add("error", "SIDE", "my_side 는 '갑' 또는 '을'이어야 합니다.")
    if doc == "nda":
        rep.need(data.get("purpose"), "PURPOSE", "협의 목적(본건)")
        if (data.get("term_years") or 2) > 5:
            rep.add("warn", "NDA_LONG", "비밀유지 기간이 5년을 넘습니다. 너무 길면 부담이 될 수 있어 다시 보세요.")
        return rep
    # 외주·용역 공통
    rep.need(data.get("start"), "START", "시작일")
    rep.need(data.get("end"), "END", "종료일(납기)")
    pay_mode = data.get("pay_mode", "milestone")
    if doc == "outsourcing" or pay_mode == "milestone":
        rep.need(data.get("total"), "TOTAL", "총 대금")
        sp, _ = splits(data)
        if sum(sp) != 100:
            rep.add("error", "SPLIT_SUM", f"단계 지급 비율의 합이 {sum(sp)}%입니다. 100%가 되게 고쳐 주세요.")
        elif sp[0] < 30:
            rep.add("warn", "DEPOSIT_LOW", f"선급금이 {sp[0]}%입니다. 미수금을 막으려면 30% 이상을 권합니다.")
        if isinstance(data.get("total"), (int, float)) and data["total"] >= 10_000_000:
            rep.add("info", "NOTARY", "1,000만 원 이상 거래라 강제집행 승낙 문구가 들어간 공정증서를 따로 만들지 검토해 보세요.", cite("민집법56"))
    if doc == "outsourcing":
        rep.need(data.get("scope"), "SCOPE", "업무 범위")
        rep.need(data.get("revisions"), "REVISIONS", "수정 허용 횟수")
        rep.need(data.get("inspection_days"), "INSPECT", "검수 기간(일)")
    else:
        rep.need(data.get("services"), "SCOPE", "용역 범위")
    pen = data.get("penalty_pct", 30)
    if pen > 30:
        rep.add("warn", "PENALTY_HIGH", f"위약금 한도 {pen}%는 과하다는 다툼이 생길 수 있습니다(법원 감액 가능).", cite("민법398"))
    if data.get("late_interest_pct", 6) > 24:
        rep.add("warn", "LATE_HIGH", "지연이자율이 높습니다. 다시 보세요.")
    return rep
