"""Offline tests: run with  python -m unittest scraper/test_scrape.py  (no internet needed)."""
import os, sys, unittest
from datetime import date, datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BOT_CONTACT_EMAIL"] = "test@example.com"
import scrape as S

RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Jobs</title>
<item><title>Accounts Clerk &amp; Cashier</title><link>https://www.govt.lc/jobs/accounts-clerk</link>
<pubDate>{recent}</pubDate><description>&lt;p&gt;Applications must be submitted by 30 {fut}.&lt;/p&gt;</description></item>
<item><title>Old Vacancy</title><link>https://www.govt.lc/jobs/old</link><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate><description>Closing date: 5 January 2024</description></item>
<item><title>Undated and stale</title><link>https://www.govt.lc/jobs/stale</link><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item>
</channel></rss>"""
ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Scholarship call</title>
<link rel="alternate" href="https://example.org/s1"/><updated>2026-10-01T10:00:00Z</updated><summary>Deadline: 2026-12-15</summary></entry></feed>"""
LIST_HTML = """<html><body><nav><a href="/">Home page</a></nav>
<a href="/News/Latest/National-Development-Scholarships-2026.aspx">National Development Scholarships 2026</a>
<a href="/News/Latest/National-Development-Scholarships-2026.aspx">Read more</a>
<a href="/News/Latest/Summer-School-2026.aspx">Summer School 2026 announced</a>
<a href="/News/Latest/Old-Scholarship.aspx">Old Scholarship offered by Rotary</a>
<a href="javascript:void(0)">Scholarships menu</a></body></html>"""


class FakeFetcher:
    def __init__(self, pages): self.pages, self.calls = pages, []
    def get(self, url, render=False):
        self.calls.append(url)
        if url not in self.pages: raise RuntimeError("404")
        return self.pages[url]


def fresh_log(): return {"known": 0, "expired": 0, "no_date": 0, "notes": []}
DEFAULTS = {"max_age_days": 60, "max_detail_fetches": 15, "max_new_per_source": 25, "request_delay_seconds": 3}
TODAY = datetime.now(S.AST).date()


class T(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(S.first_date("on 27 February 2026"), date(2026, 2, 27))
        self.assertEqual(S.first_date("Friday September 16th, 2022"), date(2022, 9, 16))
        self.assertEqual(S.first_date("2026-12-15"), date(2026, 12, 15))
        self.assertIsNone(S.first_date("31 February 2026"))
        self.assertEqual(S.find_deadline("no later than August 26 2024 at noon"), date(2024, 8, 26))
        self.assertEqual(S.find_deadline("DEADLINE to apply is on or before 20 April 2026."), date(2026, 4, 20))
        self.assertIsNone(S.find_deadline("Published 5 May 2026 with no closing info"))

    def test_feeds(self):
        items = S.parse_feed(RSS.format(recent="Mon, 01 Jan 2024 10:00:00 GMT", fut="December 2031"))
        self.assertEqual(items[0]["title"], "Accounts Clerk & Cashier")
        self.assertIn("30 December 2031", items[0]["hint"])
        a = S.parse_feed(ATOM)
        self.assertEqual((a[0]["link"], a[0]["pub"].year), ("https://example.org/s1", 2026))

    def test_links(self):
        links = S.parse_links(LIST_HTML, "https://mes.gov.bb/News/Latest/?y=2026", r"/News/Latest/[^/?#]+\.aspx")
        titles = sorted(l["title"] for l in links)
        self.assertEqual(len(links), 3)
        self.assertIn("National Development Scholarships 2026", titles)       # the longer title wins over "Read more"
        self.assertNotIn("Read more", titles)

    def test_canon_and_id(self):
        a = S.external_id("x", "HTTPS://Example.com/a/?utm_source=z#frag")
        b = S.external_id("x", "https://example.com/a")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("x:") and len(a) <= 120)

    def test_build_row_rss_future_deadline(self):
        src = {"id": "lc-jobs", "country_code": "lc", "category": "Jobs", "name": "Gov of Saint Lucia", "type": "rss"}
        cand = {"title": "Accounts Clerk", "link": "https://www.govt.lc/jobs/clerk", "pub": None,
                "hint": "Applications must be submitted by 30 December 2099."}
        row = S.build_row(src, cand, TODAY, DEFAULTS, FakeFetcher({}), {"left": 5}, set(), fresh_log())
        self.assertEqual((row["status"], row["category"], row["country_code"]), ("Pending", "Jobs", "lc"))
        self.assertTrue(row["expires_at"].startswith("2099-12-31") or row["expires_at"].startswith("2099-12-30"))
        self.assertIn("Closing date: 30 December 2099", row["description"])
        self.assertNotIn("submitted by", row["description"])                 # no copied source text
        self.assertTrue(3 <= len(row["description"]) <= 1500 and 3 <= len(row["title"]) <= 120)

    def test_skips(self):
        src = {"id": "s", "country_code": "bb", "category": "Education", "name": "X", "type": "rss"}
        log = fresh_log()
        past = {"title": "Old scholarship", "link": "https://x/1", "pub": None, "hint": "Deadline: 1 March 2020"}
        self.assertIsNone(S.build_row(src, past, TODAY, DEFAULTS, FakeFetcher({}), {"left": 0}, set(), log)); self.assertEqual(log["expired"], 1)
        undated = {"title": "Undated notice", "link": "https://x/2", "pub": None, "hint": ""}
        self.assertIsNone(S.build_row(src, undated, TODAY, DEFAULTS, FakeFetcher({}), {"left": 0}, set(), log)); self.assertEqual(log["no_date"], 1)
        stale = {"title": "Stale notice", "link": "https://x/3", "pub": datetime.now(timezone.utc) - timedelta(days=200), "hint": ""}
        self.assertIsNone(S.build_row(src, stale, TODAY, DEFAULTS, FakeFetcher({}), {"left": 0}, set(), log))
        fresh = {"title": "Fresh notice", "link": "https://x/4", "pub": datetime.now(timezone.utc) - timedelta(days=3), "hint": ""}
        self.assertIsNotNone(S.build_row(src, fresh, TODAY, DEFAULTS, FakeFetcher({}), {"left": 0}, set(), log))
        known = {S.external_id("s", "https://x/4")}
        self.assertIsNone(S.build_row(src, fresh, TODAY, DEFAULTS, FakeFetcher({}), {"left": 0}, known, log)); self.assertEqual(log["known"], 1)

    def test_html_source_detail_page_deadline(self):
        src = {"id": "bb-mes", "country_code": "bb", "category": "Education", "name": "Barbados MoE", "type": "html_links",
               "fetch_details": True, "title_keywords": "scholarship"}
        detail = "<html><body><nav>menu</nav><p>Forms must be submitted no later than 15 December 2099.</p></body></html>"
        f = FakeFetcher({"https://mes.gov.bb/News/Latest/a.aspx": detail}); budget = {"left": 2}
        row = S.build_row(src, {"title": "National Development Scholarships 2099", "link": "https://mes.gov.bb/News/Latest/a.aspx", "pub": None, "hint": ""},
                          TODAY, DEFAULTS, f, budget, set(), fresh_log())
        self.assertEqual(budget["left"], 1)
        self.assertIn("15 December 2099", row["description"])
        self.assertIsNone(S.build_row(src, {"title": "Summer School", "link": "https://mes.gov.bb/News/Latest/b.aspx", "pub": None, "hint": ""},
                                      TODAY, DEFAULTS, f, budget, set(), fresh_log()))   # keyword filter

    def test_auto_category(self):
        self.assertEqual(S.classify("Cuba Scholarship announcement"), "Education")
        self.assertEqual(S.classify("Career Opportunity - CEO"), "Jobs")
        self.assertIsNone(S.classify("Gas prices for June"))

    def test_hostile_title_is_inert(self):
        t = S.clean_text("<script>alert(1)</script>Vacancy &lt;b&gt;x&lt;/b&gt;\x00\x07 Officer")
        self.assertNotIn("<", t); self.assertNotIn("\x00", t)

    def test_year_urls(self):
        src = {"urls": ["https://mes.gov.bb/News/Latest/?y={year}"]}
        self.assertEqual(len(S.candidate_urls(src, date(2026, 10, 12))), 1)
        self.assertEqual(len(S.candidate_urls(src, date(2026, 1, 5))), 2)

    def test_config_valid(self):
        import json
        cfg = json.load(open(os.path.join(os.path.dirname(S.__file__), "sources.json")))
        ids = [s["id"] for s in cfg["sources"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in cfg["sources"]:
            self.assertIn(s["category"], ("Jobs", "Education", "Major news", "Sports", "auto"))
            self.assertIn(s["country_code"], ("lc", "gd", "bb", "jm", "tt", "gy", "vc"))
        self.assertFalse([s for s in cfg["sources"] if s.get("third_party") and s.get("enabled")])
        self.assertFalse([s["id"] for s in cfg["sources"] if s.get("unverified") and s.get("enabled")])   # untested sources stay off until a dry run

    def test_news_item_is_pending_and_honest(self):
        src = {"id": "jm-opm-news", "country_code": "jm", "category": "Major news", "name": "Office of the Prime Minister, Jamaica",
               "type": "rss", "title_keywords": "drought|water", "max_age_days": 21}
        pub = datetime.now(timezone.utc) - timedelta(days=2)
        cand = {"title": "Government expands drought response", "link": "https://opm.gov.jm/government-expands-drought-response/", "pub": pub, "hint": ""}
        row = S.build_row(src, cand, TODAY, DEFAULTS, FakeFetcher({}), {"left": 5}, set(), fresh_log())
        self.assertEqual((row["status"], row["category"], row["country_code"]), ("Pending", "Major news", "jm"))
        self.assertIn("News item listed by Office of the Prime Minister, Jamaica.", row["description"])
        self.assertNotIn("how to apply", row["description"])                  # a news story is not a vacancy
        self.assertNotIn("check the official notice before applying", row["description"])
        expires = datetime.fromisoformat(row["expires_at"])
        self.assertTrue(timedelta(days=18) < expires - datetime.now(timezone.utc) < timedelta(days=20))   # published 2 days ago + 21 days
        old = dict(cand, pub=datetime.now(timezone.utc) - timedelta(days=40), link="https://opm.gov.jm/old-drought-story/")
        self.assertIsNone(S.build_row(src, old, TODAY, DEFAULTS, FakeFetcher({}), {"left": 5}, set(), fresh_log()))   # too old: skipped
        off_topic = dict(cand, title="Prime Minister attends ceremony", link="https://opm.gov.jm/ceremony/")
        self.assertIsNone(S.build_row(src, off_topic, TODAY, DEFAULTS, FakeFetcher({}), {"left": 5}, set(), fresh_log()))   # keyword filter

    def test_job_wording_unchanged(self):
        src = {"id": "lc-jobs", "country_code": "lc", "category": "Jobs", "name": "Gov of Saint Lucia", "type": "rss"}
        d = S.make_description(src, "Jobs", None)
        self.assertTrue(d.startswith("Vacancy notice listed by Gov of Saint Lucia."))
        self.assertIn("how to apply", d)


if __name__ == "__main__":
    unittest.main()
