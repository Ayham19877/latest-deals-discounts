#!/usr/bin/env python3
"""
Latest Deals & Discounts - discovery sync (v1).

Discovery source: DealForager deals page, used ONLY as a discovery signal
for which products are currently discounted. We do NOT copy DealForager
branding, layout, disclosure text, or their affiliate tag.

Output: deals.json in the Latest Deals & Discounts format:
  - title: the Amazon product title (factual product data)
  - category: Amazon category as shown on the discovery page
  - price / discount_percent: as discovered at pull time, NOT a live
    Amazon-verified Warehouse price. Warehouse stock is one-of-one and
    changes fast; the buyer must check the Used offer on Amazon.
  - amazon_url: Amazon search for the exact product title, tagged with
    the site's own Associates tag (latestdealsdi-20). Search links are
    used because the discovery page's own Amazon links carry another
    affiliate's tag and must never be reused.
  - verified_on_amazon: false for every synced deal.

Safety rules (do not weaken):
  - Never overwrite deals.json with fewer than 5 deals.
  - Never write a dealforager-20 / slicinc-20 tag.
  - Keep a backup copy (deals.json.bak) before overwriting.
  - De-duplicate by slugified title.
  - If parsing fails, exit non-zero WITHOUT touching deals.json.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

SOURCE_URL = "https://dealforager.com/deals"
TAG = "latestdealsdi-20"
MIN_DEALS = 5

CAT_IMAGES = {
    "Electronics": "assets/cat-electronics.webp",
    "Home & Kitchen": "assets/cat-kitchen.webp",
    "Tools & Home Improvement": "assets/cat-tools.webp",
    "Sports & Outdoors": "assets/cat-sports.webp",
    "Clothing, Shoes, & Jewelry": "assets/cat-clothing.webp",
    "Garden & Outdoor": "assets/cat-garden.webp",
    "Cell Phones & Accessories": "assets/cat-computers.webp",
    "Office Products": "assets/cat-office.webp",
    "Baby": "assets/cat-baby.webp",
    "Industrial & Scientific": "assets/cat-industrial.webp",
}


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:80] or "deal"


def parse_deals(html):
    """Best-effort parser for the discovery page.

    Strategy: find blocks that contain a discount line, a category line,
    a product title and a $ price. This is intentionally tolerant of
    layout changes: if the structure changes, we return few/no deals and
    the caller refuses to overwrite, rather than publishing garbage.
    """
    # Strip tags to text lines, preserving order
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    deals = []
    i = 0
    while i < len(lines):
        m = re.match(r">\s*(\d+)% off", lines[i])
        if not m:
            i += 1
            continue
        discount = int(m.group(1))
        # Next non-trivial lines: category, then title, then price
        rest = lines[i + 1 : i + 6]
        if len(rest) < 3:
            break
        category = rest[0]
        title = rest[1]
        price_m = None
        for ln in rest[2:]:
            price_m = re.match(r"\$([\d,]+\.\d{2})", ln)
            if price_m:
                break
        if not title or len(title) < 10 or not price_m:
            i += 1
            continue
        price = float(price_m.group(1).replace(",", ""))
        slug = slugify(title)
        deals.append({
            "id": f"df-{slug}",
            "title": title,
            "title_en": title,
            "category": category,
            "condition": "Warehouse deal",
            "currency": "USD",
            "price": price,
            "new_price": None,
            "discount_percent": discount,
            "deal_rating": None,
            "amazon_url": f"https://www.amazon.com/s?k={quote_plus(title)}&tag={TAG}",
            "image": CAT_IMAGES.get(category, "assets/cat-electronics.webp"),
            "posted_at": "",
            "updated": "",
            "verified_on_amazon": False,
            "discovery_source": "dealforager-discovery-only",
        })
        i += 1
    # De-duplicate by id, keep first
    seen = set()
    out = []
    for d in deals:
        if d["id"] not in seen:
            seen.add(d["id"])
            out.append(d)
    return out


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("deals.json")
    req = Request(SOURCE_URL, headers={"User-Agent": "LatestDealsDiscountsSync/1.0"})
    with urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", "ignore")
    deals = parse_deals(html)
    print(f"parsed {len(deals)} deals from discovery page")
    if len(deals) < MIN_DEALS:
        print(f"REFUSING to overwrite: only {len(deals)} deals (< {MIN_DEALS})", file=sys.stderr)
        return 2
    for d in deals:
        assert "dealforager-20" not in d["amazon_url"]
        assert TAG in d["amazon_url"]
    # Date stamps
    from datetime import date
    today = date.today().isoformat()
    for d in deals:
        d["posted_at"] = today
        d["updated"] = today
    payload = {
        "service": "Latest Deals & Discounts",
        "feed": "Latest Deals & Discounts — Amazon Warehouse (Amazon Resale) picks",
        "source_store": "Amazon Resale (formerly Amazon Warehouse Deals)",
        "updated": today,
        "sync": "auto-discovery-sync-v1, every 6 hours via GitHub Actions. Prices are as discovered at pull time, not live Amazon-verified prices; check the Used offer on Amazon before buying. Warehouse stock is one-of-one.",
        "note": "Prices/discounts are discovery values at last pull time. Open the Amazon link, then pick a Used offer sold by Amazon Resale / Amazon Warehouse and read the seller condition note before buying.",
        "deals": deals,
    }
    if out_path.exists():
        out_path.rename(out_path.with_suffix(".json.bak"))
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"wrote {len(deals)} deals to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
