"""자동 시험: python3 -m unittest discover -s tests -v  (build 폴더에서)"""
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contractdocs import checks  # noqa: E402
from contractdocs.docx_builder import DISCLAIMER, Doc  # noqa: E402
from contractdocs.generate import Blocked, generate  # noqa: E402
from contractdocs.laws import LAWS, cite  # noqa: E402
from contractdocs.render import docx_to_pdf, pdf_fonts, pdf_text  # noqa: E402
from contractdocs.review import catalog  # noqa: E402
from contractdocs.review.extract import extract  # noqa: E402
from contractdocs.review.report import review, to_md, write  # noqa: E402
from contractdocs.review.score import IDS, score_confirmed  # noqa: E402

S = ROOT / "samples"
ORIG_SCORE = Path(os.environ.get("ORIG_SCORE_PY", "/nonexistent/score.py"))
EXPECT = {"sample1_web_design.txt": (["①", "②", "⑪", "⑫"], 68, "🔴 위험"),
          "sample2_consulting.docx": (["③", "⑥", "⑦", "⑨"], 44, "🟡 주의"),
          "sample3_app_dev.pdf": (["④", "⑤", "⑧", "⑩"], 68, "🔴 위험")}


def load(name):
    return json.loads((S / "input" / name).read_text(encoding="utf-8"))


def ids(text, side="을"):
    return review(text, side=side, is_text=True)["final_ids"]


class TestScore(unittest.TestCase):
    @unittest.skipUnless(ORIG_SCORE.exists(), "원본 score.py 없음")
    def test_same_as_original_for_all_4096_combinations(self):
        spec = importlib.util.spec_from_file_location("orig", ORIG_SCORE)
        orig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(orig)
        for n in range(13):
            for combo in itertools.combinations(IDS, n):
                a, b = score_confirmed(list(combo)), orig.score_confirmed(list(combo))
                self.assertEqual((a["점수"], a["등급"], a["변호사_검토_필수"]), (b["점수"], b["등급"], b["변호사_검토_필수"]), combo)

    def test_numbers_and_unknown(self):
        r = score_confirmed(["1", "④", "10", "x"])
        self.assertEqual(r["점수"], 60)
        self.assertEqual(r["등급"], "🔴 위험")  # 🔴 2건 이상 floor
        self.assertEqual(r["미인식_입력"], ["x"])


class TestReviewSamples(unittest.TestCase):
    def test_three_samples(self):
        for name, (exp, pts, grade) in EXPECT.items():
            r = review(S / "review" / name)
            self.assertEqual(r["final_ids"], exp, name)
            self.assertEqual(r["score"]["점수"], pts, name)
            self.assertEqual(r["score"]["등급"], grade, name)
            self.assertTrue(r["score"]["변호사_검토_필수"], name)

    def test_deterministic_repeat(self):
        for name in EXPECT:
            a = json.dumps(review(S / "review" / name), ensure_ascii=False, sort_keys=True)
            b = json.dumps(review(S / "review" / name), ensure_ascii=False, sort_keys=True)
            self.assertEqual(a, b)

    def test_same_result_across_formats(self):
        txt = (S / "review" / "sample1_web_design.txt").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as td:
            d = Doc("웹사이트 디자인 외주계약서", disclaimer=None)
            for line in txt.splitlines()[1:]:
                d.para(line)
            dx = Path(td) / "s1.docx"
            d.save(dx)
            pdf = docx_to_pdf(dx, td)
            base = review(S / "review" / "sample1_web_design.txt")["final_ids"]
            self.assertEqual(review(dx)["final_ids"], base)
            self.assertEqual(review(pdf)["final_ids"], base)

    def test_bot_adjustment_is_recorded(self):
        r = review(S / "review" / "sample1_web_design.txt", confirm=["⑦"], reject=["⑪"])
        self.assertEqual(r["final_ids"], ["①", "②", "⑦", "⑫"])
        self.assertIn("원문을 읽고 조정함", to_md(r))


class TestRules(unittest.TestCase):
    def test_negations_not_flagged(self):
        self.assertNotIn("⑩", ids("제1조(책임) 을의 대표자 개인은 연대보증을 하지 아니한다."))
        self.assertNotIn("⑥", ids("제1조(기간) 본 계약은 자동으로 갱신되지 아니한다."))
        self.assertNotIn("④", ids("제1조(손해배상) 간접 손해와 결과적 손해는 배상 범위에서 제외한다."))

    def test_positive_patterns(self):
        self.assertIn("⑩", ids("제1조(보증) 을의 대표자는 을과 연대하여 책임을 진다."))
        self.assertIn("⑥", ids("제1조(기간) 계약 만료 시 별도 통지가 없으면 계약은 자동 연장된다."))
        self.assertIn("③", ids("제1조(위약금) 을이 위반하면 대금의 50%를 위약금으로 지급한다."))
        self.assertIn("⑪", ids("제1조(대금) 대금 300만원은 선급금 없이 납품 후 일괄 지급한다."))

    def test_particle_eul_is_not_party(self):
        # '계약을 이행' 의 '을'을 당사자 을로 읽으면 ⑨ 판단이 틀어진다
        self.assertIn("⑨", ids("제1조(비밀) 을은 계약을 이행하며 알게 된 비밀을 누설하지 아니한다."))
        self.assertNotIn("⑨", ids("제1조(비밀) 갑과 을은 계약을 이행하며 알게 된 비밀을 누설하지 아니한다."))

    def test_side_swap(self):
        t = "제1조(해지) 을은 언제든지 통지로 본 계약을 해지할 수 있다."
        self.assertNotIn("①", ids(t, side="을"))
        r = review(t, side="갑", is_text=True)
        self.assertIn("①", r["final_ids"])
        self.assertIn("을은 언제든지", r["toxic"][0]["quote"])  # 인용은 원래 표기

    def test_alias_names(self):
        t = '주식회사 가(이하 "회사")와 나(이하 "용역사")는 계약한다. 제1조(해지) 회사는 언제든지 본 계약을 해지할 수 있다.'
        self.assertIn("①", ids(t))

    def test_hwpx(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.hwpx"
            body = ('<hs:sec xmlns:hs="s" xmlns:hp="p"><hp:p><hp:run><hp:t>제1조(보증) 을의 대표자는 개인 자격으로 연대보증한다.</hp:t></hp:run></hp:p></hs:sec>')
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("mimetype", "application/hwp+zip")
                z.writestr("Contents/section0.xml", body)
            self.assertIn("연대보증", extract(p))
            self.assertIn("⑩", review(p)["final_ids"])


class TestGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp()
        cls.out = {k: generate(load(f"{k}.json"), Path(cls.td) / k) for k in ("outsourcing", "service", "nda")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.td, ignore_errors=True)

    def test_files_and_korean_font(self):
        for k, o in self.out.items():
            for key in ("docx", "md", "pdf"):
                self.assertTrue(Path(o[key]).exists(), (k, key))
            self.assertTrue(o["png"], k)
            fonts = pdf_fonts(o["pdf"])
            self.assertRegex(fonts, r"(NotoSansCJK|Nanum|Malgun)", k)
            txt = re.sub(r"\s+", "", pdf_text(o["pdf"]))
            self.assertIn("제1조", txt)
            self.assertNotIn("\ufffd", txt)

    def test_disclaimer_once(self):
        for k, o in self.out.items():
            txt = re.sub(r"\s+", "", pdf_text(o["pdf"]))
            self.assertEqual(txt.count("변호사검토전참고용초안"), 1, k)
            self.assertEqual(Path(o["md"]).read_text(encoding="utf-8").count("변호사 검토 전 참고용 초안"), 1, k)

    def test_generated_contracts_have_no_toxic_clause(self):
        for k, o in self.out.items():
            r = review(o["docx"])
            self.assertEqual(r["final_ids"], [], k)
        r = review(self.out["outsourcing"]["docx"])
        self.assertTrue(all(e["present"] and e["clear"] == "✅" for e in r["essential"]))
        self.assertTrue(all(m["present"] for m in r["missing5"]))

    def test_amount_split(self):
        md = Path(self.out["outsourcing"]["md"]).read_text(encoding="utf-8")
        for amt in ("1,980,000원", "3,300,000원", "1,320,000원"):
            self.assertIn(amt, md)

    def test_blanks_when_missing(self):
        d = load("outsourcing.json")
        d.pop("revisions")
        d["party_b"].pop("ceo")
        rep = checks.check(d)
        self.assertIn("REVISIONS", rep.codes("missing"))
        with tempfile.TemporaryDirectory() as td:
            o = generate(d, td, pdf=False)
            self.assertIn("＿＿＿＿＿＿회", Path(o["md"]).read_text(encoding="utf-8"))

    def test_sensitive_blocked(self):
        d = load("nda.json")
        d["party_b"]["memo"] = "대표 주민번호 900101-1234567"
        with tempfile.TemporaryDirectory() as td, self.assertRaises(Blocked):
            generate(d, td, pdf=False)
        d = load("nda.json")
        d["account_password"] = "1234"
        self.assertIn("SENSITIVE_SECRET", checks.check(d).codes("error"))

    def test_input_warnings(self):
        d = load("outsourcing.json")
        d["payment_split"] = [10, 90]
        d["penalty_pct"] = 100
        rep = checks.check(d)
        self.assertIn("DEPOSIT_LOW", rep.codes("warn"))
        self.assertIn("PENALTY_HIGH", rep.codes("warn"))
        d["payment_split"] = [30, 30, 30]
        self.assertIn("SPLIT_SUM", checks.check(d).codes("error"))


class TestLaws(unittest.TestCase):
    def test_catalog_basis_all_known(self):
        for i, c in catalog.TOXIC.items():
            for k in c["basis"]:
                self.assertIn(k, LAWS, (i, k))
                self.assertTrue(LAWS[k][4], f"{i} 근거 {k} 가 원문 대조 안 됨")

    def test_unverified_gets_tag(self):
        unverified = [k for k, v in LAWS.items() if not v[4]]
        self.assertTrue(unverified)
        for k in unverified:
            self.assertTrue(cite(k).endswith("[확인 필요]"))
        self.assertTrue(cite("없는법99").endswith("[확인 필요]"))

    def test_report_tags_every_basis(self):
        md = to_md(review(S / "review" / "sample3_app_dev.pdf"))
        for line in md.splitlines():
            if line.startswith("- ") and " — " in line and ("법 제" in line or "법률" in line) and "조(" in line:
                self.assertTrue("원문 대조 ✅" in line or "[확인 필요]" in line, line)

    def test_known_corrections(self):
        self.assertNotIn("공증인법", json.dumps(LAWS, ensure_ascii=False))
        self.assertNotIn("저작권법 위반", json.dumps(catalog.TOXIC, ensure_ascii=False))


class TestDrafts(unittest.TestCase):
    def test_bot_text_rules(self):
        files = list((ROOT / "skills").rglob("SKILL.md")) + [ROOT / "bot_instructions.md"]
        self.assertEqual(len(files), 3)
        for f in files:
            t = f.read_text(encoding="utf-8")
            body = "\n".join(l for l in t.splitlines() if "쓰지 않는다" not in l)  # 금지 규칙 줄 자체는 빼고 본다
            self.assertNotIn("대가 없이", body, f)
            self.assertNotIn("무료 법률", body, f)
            self.assertIn("변호사 검토 전 참고용 초안", t, f) if f.name == "bot_instructions.md" else None
            for url in re.findall(r"https?://[^\s)>\]」\"']+", t):
                self.assertTrue(url.startswith(("https://www.youtube.com/@leesangsu-briefing", "https://lbiz-partners.com/blog/ai-contract-review-toxic-clause-2026", "https://www.law.go.kr", "https://github.com/lbiz-partners/lbiz-contract-review-bot")), (f, url))
        for f in (ROOT / "skills").rglob("SKILL.md"):
            self.assertTrue(f.read_text(encoding="utf-8").startswith("---\nname:"), f)


if __name__ == "__main__":
    unittest.main()
