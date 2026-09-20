import sys
import os
import json
import asyncio
import urllib.parse
from datetime import datetime
from playwright.async_api import async_playwright

HISTORY_FILE = "shelf_history.json"

KNOWN_BRANDS = [
    "Shree Anandhaas", "Anandhaas", "Anand Sweets", "Chak Now", "Chaknow",
    "Sweet Karam Coffee", "Eat Better Co", "GO DESi", "Modern Kitchens",
    "Paaramparik Naturals", "From Granny", "Let's Try", "Paper Boat",
    "Karachi Bakery", "Lal Sweets", "Gowardhan Khushiya", "iD Fresh",
    "4700BC", "Open Secret", "The Whole Truth", "Bikaji", "Haldiram's",
    "Too Yumm!", "Beyond Snack", "Uncle Chipps", "Lay's",
    "Farmley", "NOICE", "A2B", "Amul", "MTR", "Gits",
    "Bolas", "Wholicious", "Daadi's", "Bikano", "Lal", "GRB", "Artinci", "Unibic", "Masqa"
]

def extract_brand(title: str) -> str:
    clean = title.strip()
    for kb in KNOWN_BRANDS:
        if kb.lower() in clean.lower():
            if kb in ["Lal", "Lal Sweets"]: return "Lal Sweets"
            if kb.lower() in ["chak now", "chaknow"]: return "Chak Now"
            return kb
    if " by " in clean.lower():
        parts = clean.split(" By ") if " By " in clean else clean.split(" by ")
        return parts[-1].split("|")[0].split("-")[0].strip()
    return clean.split()[0] if clean.split() else "Generic"

async def scrape_blinkit_live(query, lat, lon):
    results = []
    encoded_q = urllib.parse.quote(query.strip())
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )
        await context.add_cookies([
            {"name": "lat", "value": str(lat), "domain": ".blinkit.com", "path": "/"},
            {"name": "lon", "value": str(lon), "domain": ".blinkit.com", "path": "/"},
            {"name": "gr_lat", "value": str(lat), "domain": ".blinkit.com", "path": "/"},
            {"name": "gr_lon", "value": str(lon), "domain": ".blinkit.com", "path": "/"}
        ])
        page = await context.new_page()
        url = f"https://blinkit.com/s/?q={encoded_q}"
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_selector('div:has-text("ADD")', timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(2)

        raw_items = await page.evaluate(r'''() => {
            const btns = Array.from(document.querySelectorAll('*')).filter(el => el.children.length === 0 && (el.innerText || "").trim() === 'ADD');
            const cardMap = new Map();
            btns.forEach(btn => {
                let tile = btn.parentElement;
                while (tile && tile.parentElement && tile.parentElement !== document.body) {
                    if (Array.from(tile.parentElement.querySelectorAll('*')).filter(e => e.children.length === 0 && (e.innerText || "").trim() === 'ADD').length > 1) break;
                    tile = tile.parentElement;
                }
                if (!tile || cardMap.has(tile)) return;
                const r = tile.getBoundingClientRect();
                if (r.width >= 80 && r.height >= 140) {
                    cardMap.set(tile, { el: tile, x: Math.round(r.left), y: Math.round(r.top) });
                }
            });
            const cards = Array.from(cardMap.values()).sort((a, b) => (Math.abs(a.y - b.y) > 60 ? a.y - b.y : a.x - b.x));
            return cards.map(c => {
                const text = c.el.innerText || "";
                const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
                const hasAd = lines.some(l => l === "Ad" || l === "AD" || l === "Sponsored") || Array.from(c.el.querySelectorAll('img')).some(i => (i.src || '').includes('ad_without_bg'));
                const title = lines.find(l => l !== "ADD" && l !== "Ad" && l !== "AD" && !l.includes("₹") && !/\b\d+%\s*OFF\b/i.test(l) && l.length > 3) || "Product";
                const price = lines.find(l => l.includes("₹")) || "₹100";
                return { title: title, price: price, is_ad: hasAd };
            });
        }''')
        await browser.close()

    ad_r, org_r, overall = 1, 1, 1
    for item in raw_items:
        results.append({
            "Overall Shelf Pos": overall,
            "Type": "Sponsored Ad" if item["is_ad"] else "Organic",
            "Placement Rank": f"Ad #{ad_r}" if item["is_ad"] else f"Org #{org_r}",
            "Product Name": item["title"],
            "Brand": extract_brand(item["title"]),
            "Price": item["price"]
        })
        if item["is_ad"]: ad_r += 1
        else: org_r += 1
        overall += 1
    return results

def main():
    store = sys.argv[1].lower() if len(sys.argv) > 1 else "blinkit"
    kw = sys.argv[2] if len(sys.argv) > 2 else "mysore pak"
    lat = sys.argv[3] if len(sys.argv) > 3 else "13.0470976"
    lon = sys.argv[4] if len(sys.argv) > 4 else "77.5476596"
    loc_tag = sys.argv[5] if len(sys.argv) > 5 else "560021"

    data = asyncio.run(scrape_blinkit_live(kw, lat, lon))
    if not data:
        print("No items returned.")
        return

    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    cache_key = f"{store}_{kw.lower().strip()}_{loc_tag.lower().strip()}"
    history[cache_key] = {
        "timestamp": datetime.now().strftime("%I:%M %p, %d %b"),
        "items": data
    }

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"Successfully saved {len(data)} items for {cache_key}.")

if __name__ == "__main__":
    main()
