#!/usr/bin/env python3
"""
Isle Connect weekly importer: jobs, scholarships and news headlines from official sources.

What it stores per notice (and nothing more):
  - the notice headline (shortened to 120 characters)
  - a link back to the official source, and the source name
  - a closing date, if one is stated
  - a short sentence written by this script (NOT copied from the source)
Everything is saved with status 'Pending', so you review it in your admin before it goes live.

Politeness / legal safeguards built in:
  - checks robots.txt for every host and skips anything disallowed or unverifiable
  - identifies itself with a User-Agent and your contact email
  - waits between requests (at least 3 s, or the site's crawl-delay if larger)
  - small page-size limit, small number of pages per run
  - never copies page text into your database; page text is only read to find a closing date
This is not legal advice: you are responsible for checking each site's terms.
"""
import argparse, hashlib, html, json, os, re, sys, time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib import robotparser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
AST = timezone(timedelta(hours=-4))          # Barbados, Saint Lucia and Grenada
MAX_BYTES = 2_000_000


def make_user_agent():
    site = os.environ.get("SITE_URL", "").strip() or "https://example.com"
    contact = os.environ.get("BOT_CONTACT_EMAIL", "").strip()
    return f"IsleConnectBot/1.0 (+{site}; {contact})"


class Blocked(Exception):
    """robots.txt (or the lack of a readable robots.txt) says do not fetch."""


# ---------------------------------------------------------------- fetching
class Fetcher:
    def __init__(self, delay=3.0, user_agent=None):
        self.delay = float(delay)
        self.ua = user_agent or make_user_agent()
        self.last = {}
        self.robots = {}
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": self.ua,
                               "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml;q=0.9,*/*;q=0.5"})

    def _wait(self, host, extra=0.0):
        gap = max(self.delay, extra)
        elapsed = time.time() - self.last.get(host, 0)
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self.last[host] = time.time()

    def _robots_for(self, url):
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base in self.robots:
            return self.robots[base]
        rp = robotparser.RobotFileParser()
        result = None
        try:
            self._wait(p.netloc)
            r = self.s.get(base + "/robots.txt", timeout=20)
            if r.status_code in (404, 410):
                rp.parse([]); result = rp                      # no robots.txt: allowed
            elif r.status_code == 200:
                rp.parse(r.text.splitlines()); result = rp
            elif r.status_code in (401, 403):
                result = False                                  # be conservative
        except requests.RequestException:
            result = None
        self.robots[base] = result
        return result

    def check_allowed(self, url):
        rp = self._robots_for(url)
        if rp is None:
            raise Blocked("could not read robots.txt, skipped to be safe")
        if rp is False:
            raise Blocked("robots.txt is not accessible (401/403), skipped to be safe")
        if not rp.can_fetch(self.ua, url):
            raise Blocked("disallowed by robots.txt")
        return rp.crawl_delay(self.ua) or 0

    def get(self, url, render=False):
        crawl_delay = self.check_allowed(url)
        host = urlparse(url).netloc
        last_err = None
        for attempt in range(2):
            self._wait(host, crawl_delay)
            try:
                if render:
                    return render_page(url, self.ua)
                r = self.s.get(url, timeout=30, stream=True)
                if r.status_code >= 500:
                    raise requests.RequestException(f"HTTP {r.status_code}")
                r.raise_for_status()
                data = b""
                for chunk in r.iter_content(65536):
                    data += chunk
                    if len(data) > MAX_BYTES:
                        break
                return data.decode(r.encoding or "utf-8", errors="replace")
            except (requests.RequestException, RuntimeError) as e:
                last_err = e
                time.sleep(2)
        raise RuntimeError(f"fetch failed: {last_err}")


def render_page(url, ua):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("this source needs a browser: pip install playwright && playwright install chromium")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=ua)
        page.goto(url, wait_until="networkidle", timeout=45000)
        content = page.content()
        browser.close()
        return content


# ---------------------------------------------------------------- text helpers
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(s):
    s = html.unescape(s or "")
    if "<" in s:
        s = BeautifulSoup(s, "html.parser").get_text(" ")
    s = CTRL.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def truncate(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def canon(url):
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_")]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", urlencode(q), ""))


def external_id(source_id, url):
    return f"{source_id}:{hashlib.sha1(canon(url).encode()).hexdigest()[:20]}"


# ---------------------------------------------------------------- dates
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_RES = [
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}\.?,?\s+(\d{{4}})\b", re.I), "dmy"),
    (re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I), "mdy"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
]
_DEADLINE = re.compile(
    r"(deadline|closing\s+date|closes?\b|close\s+on|no\s+later\s+than|on\s+or\s+before|apply\s+by|"
    r"submitted\s+by|submission\s+is|due\s+date|must\s+(?:be\s+)?(?:received|submitted)|should\s+reach)", re.I)


def first_date(text):
    best = None
    for rx, kind in _DATE_RES:
        m = rx.search(text)
        if not m:
            continue
        try:
            if kind == "dmy":
                d = date(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
            elif kind == "mdy":
                d = date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
            else:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if best is None or m.start() < best[0]:
            best = (m.start(), d)
    return best[1] if best else None


def find_deadline(text):
    """Latest date mentioned shortly after a deadline-type phrase."""
    latest = None
    for m in _DEADLINE.finditer(text or ""):
        d = first_date(text[m.end(): m.end() + 120])
        if d and (latest is None or d > latest):
            latest = d
    return latest


def parse_when(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------- parsing
def _local(tag):
    return tag.split("}")[-1]


def parse_feed(xml_text):
    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_text or "")
    root = ET.fromstring(xml_text.encode("utf-8"))
    items = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        kids = {}
        links = []
        for c in el:
            name = _local(c.tag)
            kids.setdefault(name, c)
            if name == "link":
                links.append(c)
        link = ""
        for c in links:                                   # RSS text link, or Atom href
            href = (c.get("href") or c.text or "").strip()
            if href and (c.get("rel") in (None, "alternate")):
                link = href
                break
        if not link and "guid" in kids and (kids["guid"].text or "").startswith("http"):
            link = kids["guid"].text.strip()
        txt = lambda k: clean_text(kids[k].text) if k in kids and kids[k].text else ""
        pub = next((txt(k) for k in ("pubDate", "published", "updated", "date") if txt(k)), "")
        hint = next((txt(k) for k in ("description", "summary", "content", "encoded") if txt(k)), "")
        items.append({"title": txt("title"), "link": link, "pub": parse_when(pub), "hint": hint})
    return items


_GENERIC = re.compile(r"^(read more|more|click here|download|view|details|learn more|apply|continue reading)\W*$", re.I)


def parse_links(html_text, base_url, include=None, exclude=None):
    soup = BeautifulSoup(html_text or "", "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urljoin(base_url, href)
        if urlparse(url).scheme not in ("http", "https"):
            continue
        if include and not re.search(include, url, re.I):
            continue
        if exclude and re.search(exclude, url, re.I):
            continue
        title = clean_text(a.get_text(" "))
        if len(title) < 8 or _GENERIC.match(title):
            continue
        key = canon(url)
        if key not in found or len(title) > len(found[key]["title"]):
            found[key] = {"title": title, "link": url, "pub": None, "hint": ""}
    return list(found.values())


def page_text(html_text):
    soup = BeautifulSoup(html_text or "", "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    return clean_text(soup.get_text(" "))


# ---------------------------------------------------------------- classification & rows
_JOBS = re.compile(r"vacanc|career|recruit|job|position|hiring|appointment|post of|internship", re.I)
_EDU = re.compile(r"scholarship|bursar|grant|award|fellowship|exhibition|study|tuition", re.I)


def classify(text):
    if _EDU.search(text):
        return "Education"
    if _JOBS.search(text):
        return "Jobs"
    return None


KINDS = {"Jobs": "Vacancy notice", "Education": "Scholarship or education notice",
         "Major news": "News item", "Sports": "Sports item"}


def make_description(src, category, deadline):
    kind = src.get("kind") or KINDS.get(category, "Notice")
    parts = [f"{kind} listed by {src['name']}."]
    if deadline:
        parts.append(f"Closing date: {deadline.day} {deadline.strftime('%B %Y')}.")
    if category in ("Jobs", "Education"):
        parts.append("Open the source link for the full details and how to apply. "
                     "Imported automatically, so please check the official notice before applying.")
    else:
        parts.append("Open the source link to read the full story. "
                     "Imported automatically, so please check the source.")
    return " ".join(parts)


def end_of_day(d):
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=AST)


def build_row(src, cand, today, defaults, fetcher, budget, known, log):
    """Returns a row dict, or None (reason is logged)."""
    title = clean_text(cand["title"])
    if len(title) < 3:
        return None
    kw = src.get("title_keywords")
    if kw and not re.search(kw, title, re.I):
        return None
    ext = external_id(src["id"], cand["link"])
    if ext in known:
        log["known"] += 1
        return None
    category = src.get("category")
    if category in (None, "auto"):
        category = classify(title + " " + cand.get("hint", ""))
        if category is None:
            return None

    deadline = find_deadline(title + " . " + cand.get("hint", ""))
    pub = cand.get("pub")
    if deadline is None and src.get("fetch_details") and budget["left"] > 0:
        budget["left"] -= 1
        try:
            deadline = find_deadline(page_text(fetcher.get(cand["link"], render=False)))
        except (Blocked, RuntimeError) as e:
            log["notes"].append(f"detail page skipped ({cand['link']}): {e}")

    max_age = int(src.get("max_age_days", defaults["max_age_days"]))
    now = datetime.now(timezone.utc)
    if deadline is not None:
        if deadline < today:
            log["expired"] += 1
            return None
        expires = end_of_day(deadline)
    elif pub is not None and (now - pub) <= timedelta(days=max_age):
        expires = pub + timedelta(days=max_age)
    else:
        log["no_date"] += 1                                    # no deadline and not clearly recent
        return None

    return {
        "country_code": src["country_code"],
        "title": truncate(title, 120),
        "category": category,
        "description": make_description(src, category, deadline),
        "contact": None,
        "status": "Pending",
        "source_name": truncate(src["name"], 200),
        "source_url": cand["link"][:1000],
        "external_id": ext,
        "expires_at": expires.astimezone(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------- collection
def candidate_urls(src, today):
    years = [today.year] + ([today.year - 1] if today.month == 1 else [])
    urls = []
    for u in src.get("urls", []):
        urls += [u.format(year=y) for y in years] if "{year}" in u else [u]
    return urls


def collect(src, fetcher, today):
    if src["type"] == "rss":
        return [i for i in parse_feed(fetcher.get(src["url"])) if i["link"] and i["title"]]
    cands = {}
    for url in candidate_urls(src, today):
        try:
            page = fetcher.get(url, render=bool(src.get("render")))
        except (Blocked, RuntimeError) as e:
            if len(candidate_urls(src, today)) == 1:
                raise
            continue
        for c in parse_links(page, url, src.get("link_include"), src.get("link_exclude")):
            cands.setdefault(canon(c["link"]), c)
    return list(cands.values())


# ---------------------------------------------------------------- database
def db_headers(key, prefer=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def known_ids(base, key, source_id):
    r = requests.get(f"{base}/rest/v1/posts", headers=db_headers(key), timeout=30,
                     params={"select": "external_id", "external_id": f"like.{source_id}:*", "limit": "2000"})
    r.raise_for_status()
    return {row["external_id"] for row in r.json()}


def insert_rows(base, key, rows):
    if not rows:
        return 0
    r = requests.post(f"{base}/rest/v1/posts", headers=db_headers(key, "resolution=ignore-duplicates,return=representation"),
                      params={"on_conflict": "external_id"}, data=json.dumps(rows), timeout=60)
    r.raise_for_status()
    return len(r.json())


# ---------------------------------------------------------------- main
def run(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show what would be saved, write nothing")
    ap.add_argument("--only", help="run just this source id (also runs it if it is disabled)")
    ap.add_argument("--list", action="store_true", help="list sources and exit")
    ap.add_argument("--config", default=os.path.join(HERE, "sources.json"))
    args = ap.parse_args(argv)

    cfg = json.load(open(args.config, encoding="utf-8"))
    defaults, sources = cfg["defaults"], cfg["sources"]
    if args.list:
        for s in sources:
            print(f"{'ON ' if s.get('enabled') else 'off'}  {s['id']:<22} {s['country_code']}  {s['category']:<9} {s['name']}")
        return 0
    if not os.environ.get("BOT_CONTACT_EMAIL", "").strip():
        print("Set BOT_CONTACT_EMAIL (a real address websites can contact). Refusing to run without it.", file=sys.stderr)
        return 1
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not args.dry_run and not (base and key):
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or use --dry-run).", file=sys.stderr)
        return 1

    fetcher = Fetcher(delay=defaults["request_delay_seconds"])
    today = datetime.now(AST).date()
    lines, failures, ran, total_new = [], 0, 0, 0
    for src in sources:
        if args.only:
            if src["id"] != args.only:
                continue
        elif not src.get("enabled"):
            continue
        ran += 1
        log = {"known": 0, "expired": 0, "no_date": 0, "notes": []}
        try:
            cands = collect(src, fetcher, today)
            known = set() if args.dry_run else known_ids(base, key, src["id"])
            budget = {"left": int(src.get("max_detail_fetches", defaults["max_detail_fetches"]))}
            rows = []
            for c in cands:
                row = build_row(src, c, today, defaults, fetcher, budget, known, log)
                if row:
                    rows.append(row)
                if len(rows) >= int(src.get("max_new_per_source", defaults["max_new_per_source"])):
                    log["notes"].append("reached the per-run cap; the rest will be picked up next week")
                    break
            new = len(rows) if args.dry_run else insert_rows(base, key, rows)
            total_new += new
            lines.append(f"| {src['id']} | {len(cands)} found | {new} {'would be added' if args.dry_run else 'added'} | "
                         f"{log['known']} already saved, {log['expired']} expired, {log['no_date']} skipped (no clear date) |")
            for r in rows if args.dry_run else []:
                print(f"  [{r['category']}] {r['title']}  ->  {r['source_url']}  (expires {r['expires_at'][:10]})")
            for n in log["notes"]:
                print(f"::notice::{src['id']}: {n}")
        except Blocked as e:
            failures += 1
            lines.append(f"| {src['id']} | skipped | 0 | {e} |")
            print(f"::warning::{src['id']}: {e}")
        except Exception as e:                                  # keep going: one broken site must not stop the rest
            failures += 1
            lines.append(f"| {src['id']} | FAILED | 0 | {type(e).__name__}: {e} |")
            print(f"::warning::{src['id']} failed: {type(e).__name__}: {e}")

    mode = "DRY RUN" if args.dry_run else "LIVE"
    report = [f"### Isle Connect import ({mode})", "", "| Source | Result | New posts | Details |", "|---|---|---|---|", *lines,
              "", f"Total new posts waiting for review: **{total_new}**"]
    print("\n".join(report))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
    return 2 if ran and failures == ran else 0


if __name__ == "__main__":
    sys.exit(run())
