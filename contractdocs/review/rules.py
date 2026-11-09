"""규칙 기반 검출 — 같은 글이면 늘 같은 결과(결정론). 사장님 쪽(기본 '을') 관점으로 본다.
status: '확정'(점수에 들어감) / '후보'(봇이 원문을 읽고 확정·제외를 정한다; 점수에 안 들어감)."""
import re
from dataclasses import asdict, dataclass

CLAUSE_RE = re.compile(r"(?m)^\s*(?:#+\s*|\*\*)?\s*(제\s*\d+\s*조(?:\s*의\s*\d+)?)\s*[\(（]?\s*([^\)）\n*]{0,30})[\)）]?")
NEG = r"(하지\s*(아니|않)|되지\s*(아니|않)|지지\s*(아니|않)|서지\s*(아니|않)|부담하지|제외|배제)"


@dataclass
class Hit:
    id: str
    status: str
    clause: str
    quote: str
    note: str = ""

    def as_dict(self):
        return asdict(self)


A_ROLES = r"(발주자|발주사|도급인|위탁자|위임인|의뢰인|甲)"
B_ROLES = r"(수급인|수급사업자|수탁자|수임인|용역사|공급자|乙)"


def _aliases(t):
    """'(이하 "회사")' 같은 별칭을 갑·을로 맞춘다. 처음 나온 별칭 = 갑, 두 번째 = 을."""
    names = []
    for m in re.finditer(r"이하\s*[\"“'‘「]?\s*([가-힣A-Za-z]{1,10}?)\s*[\"”'’」]?\s*(?:이?라\s*(?:한다|함|칭)|\))", t):
        n = m.group(1)
        if n not in names:
            names.append(n)
    for n, party in zip(names[:2], ("갑", "을")):
        if n not in ("갑", "을"):
            t = re.sub(rf"(?<![가-힣]){re.escape(n)}(?=\s|[은는이가의에도과와만를을,·)」\"”'’]|에게|으로|로|$)", party, t)
    # 받침 없는 별칭('회사는')을 바꾸면 '갑는'이 되므로 조사를 맞춘다
    for p_ in ("갑", "을"):
        t = re.sub(rf"(?<![가-힣]){p_}(는|가|와|를)", lambda m: p_ + {"는": "은", "가": "이", "와": "과", "를": "을"}[m.group(1)], t)
    return t


def normalize(text: str, side: str = "을") -> str:
    t = text.replace("\r\n", "\n").replace("\u00a0", " ").replace("ㆍ", "·")
    t = _aliases(t)
    t = re.sub(rf"(?<![가-힣]){A_ROLES}", "갑", t)
    t = re.sub(rf"(?<![가-힣]){B_ROLES}", "을", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"([가-힣]) (다[.,])", r"\1\2", t)  # PDF 양쪽 정렬로 생긴 '배상한 다.' 같은 띄어쓰기
    # 문장 중간 줄바꿈(PDF 등) 이어 붙이기: 다음 줄이 조·항·호 머리가 아니면 붙인다
    t = re.sub(r"(?<![.다:\n])\n(?!\s*(제\s*\d+\s*조|[①-⑳]|\d+\.\s|[-•·]\s|\||#|\*\*|$))", " ", t)
    if side == "갑":  # 사장님이 갑이면 갑·을을 바꿔 읽는다
        t = re.sub(r"(?<![가-힣])갑", "\0", t)
        t = re.sub(r"(?<![가-힣])을", "갑", t).replace("\0", "을")
    return t


def clauses(text: str):
    ms = list(CLAUSE_RE.finditer(text))
    if not ms:
        return [("본문", "", text)]
    out = []
    if ms[0].start() > 0 and text[: ms[0].start()].strip():
        out.append(("전문", "", text[: ms[0].start()]))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        out.append((re.sub(r"\s+", "", m.group(1)), m.group(2).strip(), text[m.start():end]))
    return out


def sentences(text: str):
    res = []
    for cid, title, body in clauses(text):
        for s in re.split(r"(?<=다\.)\s+|(?<=\.)\s+(?=[가-힣①-⑳])|\n+|(?=[①-⑳])", body):
            s = re.sub(r"^\s*(#+\s*|\*\*)?제\s*\d+\s*조(\s*의\s*\d+)?\s*([\(（][^\)）]{0,30}[\)）])?\s*(\*\*)?", "", s)
            s = s.strip(" \t|*#>")
            if len(s) >= 4:
                res.append((cid, title, s))
    return res


def _q(s, n=160):
    return s if len(s) <= n else s[: n - 1] + "…"


def _party(pat):
    """패턴 속 '갑'·'을'은 당사자 표시만 잡는다(조사 '을'과 구분: 앞이 한글이 아니어야 함)."""
    return pat.replace("갑", "(?<![가-힣])갑").replace("을", "(?<![가-힣])을") if pat else pat


def _any(sents, pat, neg=None):
    pat, neg = _party(pat), _party(neg)
    out = []
    for cid, title, s in sents:
        if re.search(pat, s) and not (neg and re.search(neg, s)):
            out.append((cid, title, s))
    return out


BOTH = r"(을\s*(은|도|이|또한)|갑과\s*을|갑\s*[·및,]\s*을|을\s*[·및,]\s*갑|양\s*당사자|각\s*당사자|당사자\s*(일방|쌍방|중\s*어느)|쌍방|어느\s*(한쪽|당사자)|일방\s*당사자|각각)"
BREACH = r"(위반|불이행|이행하지|지체|파산|부도|회생|해산|압류)"


DEP_NEG = r"(없이|없다|없으며|지급하지\s*(아니|않)|(?<![\d,])0\s*원|영\s*원)"


def detect_toxic(sents):
    hits = []
    add = lambda i, st, c, s, note="": hits.append(Hit(i, st, c, _q(s), note))

    # ① 일방 해지권
    a = [x for x in _any(sents, r"갑\s*(은|이|만|의)[^.]*?(해지|해제)\s*(할\s*수\s*있|한다|권)")
         if re.search(r"(언제든|임의|일방적|사유\s*(없이|를\s*불문)|통지(로|하고|하여|후|함으로써))", x[2]) or not re.search(BREACH, x[2])]
    b = _any(sents, BOTH + r"[^.]*?(해지|해제)\s*(할\s*수\s*있|권)")
    if a and not b:
        add("①", "확정", a[0][0], a[0][2])

    # ② 무한 수정
    for c, _, s in _any(sents, r"(수정|보완|재작업|재제작)"):
        if re.search(r"(만족할\s*때까지|만족하는\s*(수준|때)|횟수\s*(에|의)?\s*(제한\s*없이|제한이\s*없|관계\s*없이|무관)|무제한|무한|무상으로[^.]*?(수정|보완)|추가\s*(비용|대금)\s*(없이|청구\s*없이)|요청하는\s*(경우|때)\s*(언제든지|즉시))", s):
            add("②", "확정", c, s)
            break

    # ③ 과도한 위약금
    pen = _any(sents, r"(위약금|위약벌|손해배상\s*예정|배상금)")
    for c, _, s in pen:
        pcts = [float(p) for p in re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로)", s)]
        if any(p > 30 for p in pcts) or re.search(r"(전액|배액|2배|두\s*배|\d+\s*배)", s):
            add("③", "확정", c, s, f"비율 {', '.join(f'{p:g}%' for p in pcts)}" if pcts else "")
            break
    else:
        if pen and all(re.search(_party(r"을\s*(은|이)"), s) for _, _, s in pen) and not any(re.search(_party(r"갑\s*(은|이)[^.]*위약"), s) for _, _, s in pen):
            add("③", "후보", pen[0][0], pen[0][2], "위약금이 을에게만 있습니다. 비율이 적정한지, 갑에게도 적용할지 보세요.")

    # ④ 무한 책임
    capped = _any(sents, r"(배상|책임)[^.]*?(한도|상한\s*(액|으로|을|은)|초과하지\s*(아니|않)|넘지\s*(아니|않)|에\s*한정|를\s*한도)")
    for c, _, s in _any(sents, r"(배상|책임|보상)", neg=r"(제외|포함하지|배상하지\s*(아니|않)|책임지지\s*(아니|않)|한도)"):
        if re.search(r"(일체의\s*(손해|책임)|모든\s*(손해|책임)|간접\s*(적\s*)?손해|결과적\s*손해|특별\s*손해|영업\s*(손실|손해|이익)|일실\s*(이익|수익)|무한\s*책임|전적으로\s*책임|명목\s*여하를\s*불문)", s) and not re.search(_party(r"^갑\s*(은|이)"), s):
            add("④", "후보" if capped else "확정", c, s, "다른 조항에 배상 한도가 있어 함께 읽어 보세요." if capped else "")
            break

    # ⑤ 일방 저작권 양도
    cr = _any(sents, r"(저작권|저작재산권|지식재산권|지적재산권|모든\s*권리|일체의\s*권리)[^.]*?갑[^.]*?(귀속|양도|소유|이전)")
    mitig = _any(sents, r"(별도\s*(협의|보상|대가|계약)|추가\s*(보상|대가)|포트폴리오|2차적\s*저작물|잔금[^.]*?(지급|완납)[^.]*?(후|때))")
    if cr and not mitig:
        add("⑤", "확정", cr[0][0], cr[0][2])

    # ⑥ 자동 갱신
    for c, _, s in _any(sents, r"(자동\s*(으로|적으로)?\s*(갱신|연장)|(갱신|연장)\s*된\s*것으로\s*본다|동일한\s*조건으로\s*(갱신|연장))",
                        neg=r"((갱신|연장)\s*(되지|하지)\s*(아니|않)|자동\s*(으로\s*)?종료|합의[^.]*?경우에\s*(만|한)|합의가\s*없으면|납기|일정|기한)"):
        if not re.search(r"(계약|존속|기간|만료)", s):
            continue
        add("⑥", "확정", c, s)
        break

    # ⑦ 상대방 본사 관할
    j = _any(sents, r"갑\s*의\s*(본점|본사|주소지|소재지|사무소|영업소)[^.]*?(법원|관할)")
    if j:
        add("⑦", "확정", j[0][0], j[0][2])
    else:
        j2 = _any(sents, r"[가-힣]+(지방법원|지법)[^.]*?(관할|전속|합의)|(관할|전속)[^.]*?[가-힣]+(지방법원|지법)")
        if j2:
            add("⑦", "후보", j2[0][0], j2[0][2], "정해 둔 법원이 사장님 사업장과 먼 곳인지 확인하세요.")

    # ⑧ 일방 수정권
    for c, _, s in _any(sents, r"갑\s*(은|이)[^.]*?(계약\s*(내용|조건)|본\s*계약|과업|업무\s*(의\s*)?(범위|내용)|대금|단가|일정|납기|사양|용역\s*내용)[^.]*?(변경|수정|조정|추가)\s*(할\s*수\s*있|한다)",
                        neg=r"(합의|동의|협의)"):
        add("⑧", "확정", c, s)
        break

    # ⑨ 일방 비밀유지
    o = _any(sents, r"을\s*(은|이|및)[^.]*?(비밀|기밀|누설)")
    both = _any(sents, r"(갑\s*(은|도|이|및)[^.]*?(비밀|기밀|누설)|(갑과\s*을|갑\s*[·및,]\s*을|양\s*당사자|각\s*당사자|쌍방|상호|당사자\s*쌍방|당사자는)[^.]*?(비밀|기밀|누설))")
    if o and not both:
        add("⑨", "확정", o[0][0], o[0][2])

    # ⑩ 연대보증
    for c, _, s in _any(sents, r"(연대\s*(보증|보증인|하여\s*(책임|변제|보증|이행|배상))|연대\s*책임|개인\s*(자격|재산)\s*(으로|으로서)?\s*(보증|책임))",
                        neg=r"((보증|책임)[^.]*?(부담하지|지지|서지|하지)\s*(아니|않)|요구하지\s*(아니|않))"):
        add("⑩", "확정", c, s, "연대보증이 보이면 서명 전 변호사 상담을 권합니다.")
        break

    # ⑪ 선급금 0원·후불 100%
    dep = _any(sents, r"(선급금|선금|계약금|착수금|선지급)", neg=DEP_NEG)
    pay = _any(sents, r"(대금|보수|용역료|용역비|금액|지급)")
    periodic = _any(sents, r"(매월|월\s*정액|월\s*[\d,]+\s*(원|만)|회당|1회\s*[\d,]+|매\s*회|시간당|1시간\s*[\d,]+)")
    if pay and not dep and periodic:
        add("⑪", "후보", periodic[0][0], periodic[0][2], "월·회 단위로 나눠 받는 구조라 못 받을 위험은 한 번 치로 줄어듭니다. 큰 금액이면 선급금을 넣을지 보세요.")
    elif pay and not dep:
        ex = _any(sents, r"(일시\s*(불|지급)|일괄\s*(지급|정산)|전액[^.]*?(검수|납품|완료|종료)[^.]*?(후|이후)|(검수|납품|완료)[^.]*?(후|이후)[^.]*?(전액|일괄|일시))")
        tgt = (ex or pay)[0]
        add("⑪", "확정", tgt[0], tgt[2], "선급금(계약금) 조항을 찾지 못했습니다.")

    # ⑫ 검수 권한 일방
    for c, _, s in _any(sents, r"(검수|검사|승인|인수|합격)"):
        if re.search(_party(r"(갑\s*의\s*(단독|일방적|자의적|전적인|재량|임의|주관적)|갑\s*이\s*(단독으로|일방적으로|임의로|전적으로|자유롭게)|갑\s*의\s*판단\s*에\s*따라|이의\s*를?\s*제기할\s*수\s*없|이의\s*없이|갑이\s*만족)"), s):
            add("⑫", "확정", c, s)
            break
    return hits


def _has(sents, pat, neg=None):
    return _any(sents, pat, neg)


INSPECT = r"(납품|인도|수령|제출|완료)[^.]*?\d+\s*일\s*(이내|안에|내)[^.]*?(검수|검사)|(검수|검사)\s*(결과|여부|기간|기한)[^.]*?\d+\s*일"


def check_essential(sents):
    rows = []
    specs = [
        ("업무 범위", r"(업무|용역|과업|작업)\s*(의\s*)?(범위|내용)|수행할\s*(업무|용역)|제공할\s*용역", r"(기타\s*(부수|부대|관련|갑이)|갑이\s*(지시|요청)하는\s*(일체|모든|기타)|일체의\s*업무)"),
        ("기간", r"(계약\s*기간|납기|납품\s*(기한|일)|\d{4}\s*[.년-]\s*\d{1,2}\s*[.월-]|부터[^.]*까지)", None),
        ("대금", r"([\d,]+\s*(원|만\s*원)|대금|보수|용역료|용역비)", None),
        ("수정·변경", r"(수정|변경)", None),
        ("저작권", r"(저작권|저작재산권|지식재산|지적재산)", None),
        ("해지", r"(해지|해제)", None),
        ("분쟁 해결", r"(관할|분쟁|중재|조정)", None),
    ]
    for name, pat, vague in specs:
        found = _has(sents, pat)
        clear = "—"
        if found:
            clear = "✅"
            if vague and _has(sents, vague):
                clear = "🟡 모호한 표현"
            if name == "대금" and not _has(sents, r"[\d,]+\s*(원|만\s*원)|%"):
                clear = "🟡 금액·비율 없음"
            if name == "기간" and not _has(sents, r"\d"):
                clear = "🟡 날짜 없음"
        rows.append({"name": name, "present": bool(found), "clear": clear, "where": found[0][0] if found else ""})
    return rows


def check_missing5(sents):
    dep = _has(sents, r"(선급금|선금|계약금|착수금|선지급)", DEP_NEG)
    m = [
        ("수정 횟수 제한", _has(sents, r"(수정|보완)[^.]*?\d+\s*회")),
        ("선급금 비율", dep),
        ("검수 기간", _has(sents, INSPECT)),
        ("자료 제공 책임", _has(sents, r"(자료|정보|소스|원고)[^.]*?(제공|전달|송부)")),
        ("비밀유지", _has(sents, r"(비밀|기밀|누설)")),
    ]
    return [{"name": n, "present": bool(f), "where": f[0][0] if f else ""} for n, f in m]


def check_payment5(sents, amount=None):
    pct = 0
    for _, _, s in _has(sents, r"(선급금|선금|계약금|착수금)", DEP_NEG):
        for p in re.findall(r"(\d+(?:\.\d+)?)\s*%", s):
            pct = max(pct, float(p))
    alltext = " ".join(s for _, _, s in sents)
    stages = len({m.group(0).replace(" ", "") for m in re.finditer(r"\d\s*차|중도금|잔금|선급금|계약금|착수금", alltext)})
    if re.search(r"(분할|나누어|매월|월\s*정액|회당|매\s*회)", alltext):
        stages = max(stages, 2)
    rows = [
        ("선금 30% 이상", pct >= 30, f"선급금 {pct:g}%" if pct else "선급금 비율 없음"),
        ("단계 지급", stages >= 2, "나눠 받는 구조" if stages >= 2 else "한 번에 받는 구조로 보임"),
        ("검수 기간", bool(_has(sents, INSPECT)), ""),
        ("지연 이자", bool(_has(sents, r"지연\s*(이자|손해금|배상금)|연\s*\d+(\.\d+)?\s*%")), ""),
        ("공정증서(큰 거래)", bool(_has(sents, r"공정증서|공증")), "1,000만 원 이상이면 검토" if not amount or amount >= 10_000_000 else "소액이면 선택"),
    ]
    return [{"name": n, "applied": ok, "note": note} for n, ok, note in rows]


def guess_amount(sents):
    best = None
    for _, _, s in _has(sents, r"(총|대금|보수|용역료|금액)"):
        for num, man in re.findall(r"([\d,]{2,})\s*(만\s*)?원", s):
            try:
                n = int(num.replace(",", "")) * (10000 if man else 1)
            except ValueError:
                continue
            best = max(best or 0, n)
    return best


def analyze(text, side="을"):
    t = normalize(text, side)
    ss = sentences(t)
    st = [(c, ti, f"{ti} {s}") for c, ti, s in ss]  # 필수·누락 점검은 조 제목도 함께 본다
    amt = guess_amount(ss)
    head = t[:300]
    kind = "nda" if re.search(r"비밀\s*유지\s*(계약|협약|약정)|NDA|Non-Disclosure", head, re.I) and not amt else "deal"
    hits = [h.as_dict() for h in detect_toxic(ss)]
    if side == "갑":  # 인용문은 원래 표기로 되돌린다
        for h in hits:
            q = re.sub(r"(?<![가-힣])갑", "\0", h["quote"])
            h["quote"] = re.sub(r"(?<![가-힣])을", "갑", q).replace("\0", "을")
    return {"side": side, "kind": kind, "clauses": len(clauses(t)), "toxic": hits,
            "essential": check_essential(st), "missing5": check_missing5(st), "payment5": check_payment5(ss, amt), "amount": amt}
