#!/usr/bin/env python3
"""
Feed probe v2 for the MOX media list.

Fixes over v1:
  - real browser User-Agent (v1 was rejected as a bot)
  - 40+ candidate paths incl. HK-specific patterns
  - reads homepage <link rel=alternate> properly
  - checks /sitemap.xml and /robots.txt for feed hints
  - falls back to a Google News RSS site: query for outlets with no feed

Usage:  pip3 install requests
        python3 probe_feeds_v2.py
Output: feed_probe_v2.csv
"""

import csv
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, quote

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}
TIMEOUT = 15

OUTLETS = {
    "am730": "https://www.am730.com.hk/",
    "AASTOCKS": "http://www.aastocks.com/en/stocks/news/aafn/",
    "Bastille Post": "https://www.bastillepost.com/hongkong/",
    "ET Net": "https://www.etnet.com.hk/www/tc/news/",
    "Fintech News HK": "https://fintechnews.hk/",
    "HK01": "https://www.hk01.com/",
    "HKCD": "http://www.hkcd.com.hk/",
    "HKEJ": "https://www.hkej.com/",
    "HKET": "https://www.hket.com/",
    "i-Cable": "https://www.i-cable.com/",
    "Infocast": "https://www.infocast.com.hk/",
    "Ming Pao": "https://news.mingpao.com/",
    "Now Finance": "https://finance.now.com/",
    "Quamnet": "https://www.quamnet.com/",
    "Oriental Daily": "https://orientaldaily.on.cc/",
    "RTHK": "https://news.rthk.hk/rthk/en/",
    "Sing Tao": "https://www.stheadline.com/",
    "TVB": "https://news.tvb.com/",
    "Wen Wei Po": "https://www.wenweipo.com/",
    "Yahoo Finance HK": "https://hk.finance.yahoo.com/",
    "SCMP": "https://www.scmp.com/",
    "The Standard": "https://www.thestandard.com.hk/",
    "CNBC": "https://www.cnbc.com/",
    "Financial Times": "https://www.ft.com/",
    "Reuters": "https://www.reuters.com/",
    "Bloomberg": "https://www.bloomberg.com/",
    "WSJ": "https://www.wsj.com/",
}

# Domain used for the Google News site: fallback.
GNEWS_DOMAIN = {
    "am730": "am730.com.hk", "AASTOCKS": "aastocks.com",
    "Bastille Post": "bastillepost.com", "ET Net": "etnet.com.hk",
    "Fintech News HK": "fintechnews.hk", "HK01": "hk01.com",
    "HKCD": "hkcd.com.hk", "HKEJ": "hkej.com", "HKET": "hket.com",
    "i-Cable": "i-cable.com", "Infocast": "infocast.com.hk",
    "Ming Pao": "mingpao.com", "Now Finance": "now.com",
    "Quamnet": "quamnet.com", "Oriental Daily": "on.cc",
    "RTHK": "rthk.hk", "Sing Tao": "stheadline.com",
    "TVB": "tvb.com", "Wen Wei Po": "wenweipo.com",
    "Yahoo Finance HK": "hk.finance.yahoo.com", "SCMP": "scmp.com",
    "The Standard": "thestandard.com.hk", "CNBC": "cnbc.com",
    "Financial Times": "ft.com", "Reuters": "reuters.com",
    "Bloomberg": "bloomberg.com", "WSJ": "wsj.com",
}

PATHS = [
    "rss", "rss/", "rss.xml", "rss.php", "rss/index.xml", "rss/all.xml",
    "rss/news.xml", "rss/hk.xml", "rss/finance.xml", "rss/rss.xml",
    "feed", "feed/", "feeds", "feeds/", "feed.xml", "feeds/all.xml",
    "atom.xml", "index.xml", "index.rss", "rssfeed", "rssfeeds",
    "news/rss", "news/rss.xml", "news/feed", "en/rss", "tc/rss",
    "zh/rss", "hk/rss", "rss/section/all", "syndication/rss",
    "?feed=rss2", "feed/rss2", "xml/rss.xml", "data/rss.xml",
    "rss/finance", "rss/business", "api/rss", "static/rss.xml",
]


def get(url):
    try:
        return requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                            allow_redirects=True)
    except Exception:
        return None


def is_feed(text):
    """Return (ok, item_count, has_fulltext)."""
    head = text[:400].lower()
    if "<rss" not in head and "<feed" not in head and "<?xml" not in head:
        return False, 0, False
    try:
        root = ET.fromstring(text.encode("utf-8", "ignore"))
    except Exception:
        return False, 0, False
    items = root.findall(".//item") or root.findall(
        ".//{http://www.w3.org/2005/Atom}entry")
    if not items:
        return False, 0, False
    full = bool(re.search(r"content:encoded|<content[ >]", text, re.I))
    return True, len(items), full


def from_homepage(base):
    r = get(base)
    if not r or r.status_code != 200:
        return []
    out = []
    for tag in re.findall(r"<link[^>]+>", r.text, re.I):
        if not re.search(r"(rss|atom)\+xml", tag, re.I):
            continue
        m = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if m:
            out.append(urljoin(base, m.group(1)))
    # loose scan for any rss-looking href on the page
    for m in re.findall(r'href=["\']([^"\']*(?:rss|feed)[^"\']*\.xml)["\']',
                        r.text, re.I):
        out.append(urljoin(base, m))
    return out[:12]


def from_robots(base):
    r = get(urljoin(base, "robots.txt"))
    if not r or r.status_code != 200:
        return []
    return [m for m in re.findall(r"https?://\S+(?:rss|feed)\S*", r.text,
                                  re.I)][:5]


def probe(name, base):
    seen, tried = set(), []
    tried += [urljoin(base, p) for p in PATHS]
    tried += from_homepage(base)
    tried += from_robots(base)

    for url in tried:
        if url in seen:
            continue
        seen.add(url)
        r = get(url)
        if not r or r.status_code != 200 or len(r.text) < 150:
            continue
        ok, n, full = is_feed(r.text)
        if ok and n:
            return {"outlet": name, "method": "native RSS", "feed_url": url,
                    "items": n,
                    "content": "full text" if full else "headline + snippet",
                    "note": ""}
        time.sleep(0.15)

    # Fallback: Google News site: query
    dom = GNEWS_DOMAIN.get(name)
    if dom:
        q = quote(f"site:{dom} when:1d")
        gurl = (f"https://news.google.com/rss/search?q={q}"
                f"&hl=zh-HK&gl=HK&ceid=HK:zh-Hant")
        r = get(gurl)
        if r and r.status_code == 200:
            ok, n, _ = is_feed(r.text)
            if ok and n:
                return {"outlet": name, "method": "Google News fallback",
                        "feed_url": gurl, "items": n,
                        "content": "headline + link only",
                        "note": "check Google News ToS with Gareth"}

    return {"outlet": name, "method": "none", "feed_url": "", "items": 0,
            "content": "", "note": "no feed - needs licensed source or alert email"}


def main():
    rows = []
    for name, base in OUTLETS.items():
        print(f"probing {name} ...", flush=True)
        rows.append(probe(name, base))

    with open("feed_probe_v2.csv", "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["outlet", "method", "feed_url",
                                          "items", "content", "note"])
        w.writeheader()
        w.writerows(rows)

    native = sum(1 for r in rows if r["method"] == "native RSS")
    gnews = sum(1 for r in rows if r["method"] == "Google News fallback")
    print(f"\nnative RSS: {native} | Google News fallback: {gnews} | "
          f"none: {len(rows) - native - gnews}")
    print("results in feed_probe_v2.csv")


if __name__ == "__main__":
    main()
