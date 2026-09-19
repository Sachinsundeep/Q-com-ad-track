import os
import sys
import json
import urllib.parse
import traceback
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright

KNOWN_BRANDS = [
    "Shree Anandhaas", "Anandhaas", "Anand Sweets", "Chak Now", "Chaknow",
    "Sweet Karam Coffee", "Eat Better Co", "GO DESi", "Modern Kitchens",
    "Paaramparik Naturals", "From Granny", "Let's Try", "Paper Boat",
    "Karachi Bakery", "Lal Sweets", "Gowardhan Khushiya", "iD Fresh",
    "4700BC", "Open Secret", "The Whole Truth", "Bikaji", "Haldiram's",
    "Too Yumm!", "Beyond Snack", "Uncle Chipps", "Lay's",
    "Farmley", "NOICE", "A2B", "Amul", "MTR", "Gits",
    "Bolas", "Wholicious", "Daadi's", "Bikano", "Lal", "GRB", "Artinci", "Unibic", "Masqa",
    "Cadbury", "Nestle", "Snickers", "Hershey's", "Galaxy", "Ferrero", "Luvit", "Fabelle"
]

def extract_brand(title: str) -> str:
    clean = title.strip()
    for kb in KNOWN_BRANDS:
        if kb.lower() in clean.lower():
            if kb in ["Lal", "Lal Sweets"]:
                return "Lal Sweets"
            if kb.lower() in ["chak now", "chaknow"]:
                return "Chak Now"
            return kb

    if " by " in clean.lower():
        parts = clean.split(" By ") if " By " in clean else clean.split(" by ")
        return parts[-1].split("|")[0].split("-")[0].strip()

    if " | " in clean:
        return clean.split(" | ")[0].strip()
    if " - " in clean:
        return clean.split(" - ")[0].strip()

    words = clean.split()
    if len(words) >= 2 and len(words[0]) <= 3:
        return f"{words[0]} {words[1]}"
    return words[0] if words else "Generic"


async def get_or_reuse_page(context, target_domain: str):
    pages = context.pages
    for p in pages:
        if target_domain in p.url.lower():
            return p
    for p in pages:
        if p.url in ["about:blank", "chrome://newtab/", ""]:
            return p
    return await context.new_page()


# =====================================================================
# 1. ZEPTO SCRAPER
# =====================================================================
async def scan_zepto(search_query, lat="13.0470976", lon="77.5476596"):
    results = []
    encoded_query = urllib.parse.quote(search_query.strip())
    target_lat = float(lat) if lat else 13.0470976
    target_lon = float(lon) if lon else 77.5476596
    store_id = "34774f44-f41c-4bde-993b-8e93684ff94f"

    async with async_playwright() as p:
        page = None
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            for p_elem in context.pages:
                if "zepto.com" in p_elem.url:
                    page = p_elem
                    break
            if not page:
                page = await context.new_page()
            await page.goto(f"https://www.zepto.com/search?query={encoded_query}", wait_until="domcontentloaded", timeout=35000)
        except Exception:
            user_data_dir = os.path.join(os.path.expanduser("~"), ".zepto_playwright_profile")
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                channel="chrome",
                viewport={"width": 1440, "height": 900},
                geolocation={"latitude": target_lat, "longitude": target_lon},
                permissions=["geolocation"],
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            await context.add_cookies([
                {"name": "user_position", "value": f"%7B%22latitude%22%3A{target_lat}%2C%22longitude%22%3A{target_lon}%7D", "domain": ".zepto.com", "path": "/"},
                {"name": "prev_store_id", "value": store_id, "domain": ".zepto.com", "path": "/"},
                {"name": "isLocationSet", "value": "true", "domain": ".zepto.com", "path": "/"}
            ])
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(f"https://www.zepto.com/search?query={encoded_query}", wait_until="domcontentloaded", timeout=35000)

        try:
            await page.wait_for_selector('a[href*="/pn/"], a[href*="/p/"]', timeout=8000)
        except Exception:
            pass

        await page.wait_for_timeout(2500)

        raw_items = await page.evaluate(r"""() => {
            const allLinks = Array.from(document.querySelectorAll('a[href*="/pn/"], a[href*="/p/"]'));
            const cardMap = new Map();

            allLinks.forEach(a => {
                let tile = a;
                for (let i = 0; i < 4; i++) {
                    if (tile.parentElement && tile.parentElement !== document.body) {
                        const count = tile.parentElement.querySelectorAll('a[href*="/pn/"], a[href*="/p/"]').length;
                        if (count > 1) break;
                        tile = tile.parentElement;
                    }
                }

                if (!tile || cardMap.has(tile)) return;
                const rect = tile.getBoundingClientRect();
                const docTop = rect.top + window.scrollY;
                const docLeft = rect.left + window.scrollX;

                if (rect.width >= 70 && rect.height >= 120 && docTop > 50) {
                    cardMap.set(tile, {
                        el: tile,
                        href: (a.getAttribute('href') || '').split('?')[0],
                        rawHref: a.getAttribute('href') || '',
                        x: Math.round(docLeft),
                        y: Math.round(docTop)
                    });
                }
            });

            const cards = Array.from(cardMap.values());
            if (cards.length === 0) return [];

            cards.sort((a, b) => a.y - b.y);
            const rows = [];
            cards.forEach(card => {
                let r = rows.find(row => Math.abs(row.y - card.y) <= 70);
                if (!r) {
                    r = { y: card.y, items: [] };
                    rows.push(r);
                }
                r.items.push(card);
            });

            rows.sort((a, b) => a.y - b.y);
            const ordered = [];
            rows.forEach(r => {
                r.items.sort((a, b) => a.x - b.x);
                ordered.push(...r.items);
            });

            return ordered.map(item => {
                const c = item.el;
                const text = c.innerText || "";
                const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

                const textHasAd = lines.some(l => /^ad$/i.test(l) \vert{}\vert{} /^sponsored$/i.test(l));

                const imgHasAd = Array.from(c.querySelectorAll('img')).some(img => {
                    const src = (img.getAttribute('src') || '').toLowerCase();
                    const alt = (img.getAttribute('alt') || '').toLowerCase();
                    return src.includes('ad.') || src.includes('/ad-') || alt === 'ad' || alt.includes('sponsored');
                });

                const attrHasAd = Boolean(c.querySelector('[data-testid*="ad"], [data-testid*="sponsored"], [aria-label*="ad"], [aria-label*="sponsored"]'));
                const urlHasAd = /[?&](ad|sponsored|campaign_id)=/i.test(item.rawHref);
                const isAd = textHasAd || imgHasAd || attrHasAd || urlHasAd;

                let title = "";
                const directTitle = c.querySelector('h5, h4, [data-testid*="product-card-name"], [data-testid*="name"], [data-testid*="title"], [class*="product-title"]');
                if (directTitle && directTitle.innerText.trim().length > 3 && !directTitle.innerText.includes("₹")) {
                    title = directTitle.innerText.trim();
                } else {
                    title = lines.find(l => 
                        l !== "ADD" && !/^off$/i.test(l) && !/^ad$/i.test(l) && !/^sponsored$/i.test(l) &&
                        !l.includes("₹") && !/\b\d+%\s*OFF\b/i.test(l) && !/\bmins?\b/i.test(l) &&
                        !/^\(?\s*\d+(\.\d+)?[kK]?\s*\)?$/.test(l) && !/^[★☆\d\.\s\(\)]+$/.test(l) &&
                        !/^\d+\s*pack/i.test(l) && !/^\d+\s*(g|kg|ml|l|pcs|units)$/i.test(l) && 
                        l.toLowerCase() !== "sold out" && l.length > 3
                    ) || "";
                }

                if (!title || /^off$/i.test(title) || title === "ADD") {
                    const slug = item.href.split(/\/pn\/|\/p\//)[1] || "";
                    title = slug.split('/')[0].split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                }

                const price = lines.find(l => l.includes("₹")) || "N/A";
                const pack = lines.find(l => 
                    /^\d+\s*pack/i.test(l) || /\b\d+\s*(g|kg|ml|l|pcs|units)\b/i.test(l) || /\(\d+\s*(g\vert{}kg\vert{}ml\vert{}l)\)/i.test(l)
                ) || "Standard";

                const pid = item.href.split('/').filter(Boolean).pop() || ("zep_" + Math.random().toString(36).substr(2, 7));
                return { id: pid, title: title, price: price, pack: pack, is_ad: isAd };
            });
        }""")

    ad_rank, org_rank, overall = 1, 1, 1
    for card in (raw_items or []):
        clean_title = card["title"].strip()
        if len(clean_title) > 2 and clean_title.lower() != "off":
            brand = extract_brand(clean_title)
            results.append({
                "Platform": "Zepto",
                "Overall Shelf Pos": overall,
                "Type": "Sponsored Ad" if card["is_ad"] else "Organic",
                "Placement Rank": f"Ad #{ad_rank}" if card["is_ad"] else f"Org #{org_rank}",
                "Product Name": clean_title,
                "Brand": brand,
                "Price": card["price"],
                "Pack Size": card["pack"],
                "Product ID": card["id"]
            })
            if card["is_ad"]:
                ad_rank += 1
            else:
                org_rank += 1
            overall += 1

    return results


# =====================================================================
# 2. BLINKIT SCRAPER
# =====================================================================
async def scan_blinkit(search_query, lat="13.0470976", lon="77.5476596"):
    results = []
    encoded_query = urllib.parse.quote(search_query.strip())
    target_lat = float(lat) if lat else 13.0470976
    target_lon = float(lon) if lon else 77.5476596

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        page = None
        for p_elem in context.pages:
            if "blinkit.com" in p_elem.url.lower():
                page = p_elem
                break
        if not page:
            page = await context.new_page()

        await page.bring_to_front()

        try:
            await context.add_cookies([
                {"name": "lat", "value": str(target_lat), "domain": ".blinkit.com", "path": "/"},
                {"name": "lon", "value": str(target_lon), "domain": ".blinkit.com", "path": "/"},
                {"name": "gr_lat", "value": str(target_lat), "domain": ".blinkit.com", "path": "/"},
                {"name": "gr_lon", "value": str(target_lon), "domain": ".blinkit.com", "path": "/"}
            ])
        except Exception:
            pass

        await page.goto(f"https://blinkit.com/s/?q={encoded_query}", wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_selector('div:has-text("ADD"), [data-testid*="product"]', timeout=8000)
        except Exception:
            pass

        await asyncio.sleep(2.5)

        raw_items = await page.evaluate(r"""() => {
            const addButtons = Array.from(document.querySelectorAll('*'))
                .filter(el => el.children.length === 0 && (el.innerText || "").trim() === 'ADD');

            const cardMap = new Map();
            addButtons.forEach(btn => {
                let tile = btn.parentElement;
                while (tile && tile.parentElement && tile.parentElement !== document.body) {
                    if (Array.from(tile.parentElement.querySelectorAll('*')).filter(e => e.children.length === 0 && (e.innerText || "").trim() === 'ADD').length > 1) break;
                    tile = tile.parentElement;
                }
                if (!tile || cardMap.has(tile)) return;
                const rect = tile.getBoundingClientRect();
                if (rect.width >= 90 && rect.height >= 160 && (rect.top + window.scrollY) > 60) {
                    cardMap.set(tile, {
                        el: tile,
                        x: Math.round(rect.left + window.scrollX),
                        y: Math.round(rect.top + window.scrollY)
                    });
                }
            });

            const cards = Array.from(cardMap.values());
            cards.sort((a, b) => (Math.abs(a.y - b.y) > 60 ? a.y - b.y : a.x - b.x));

            return cards.map(item => {
                const c = item.el;
                const imgs = Array.from(c.querySelectorAll('img')).map(img => img.getAttribute('src') || '');
                const hasAdImage = imgs.some(src => src.includes('ad_without_bg') || src.includes('/ui/ad'));

                const allTexts = (c.innerText || '').split('\n').map(s => s.trim());
                const hasAdText = allTexts.some(t => t === 'Ad' || t === 'AD' || t === 'Sponsored');
                const isAd = hasAdImage || hasAdText;

                const lines = allTexts.filter(Boolean);
                let title = lines.find(l => 
                    l !== "ADD" && l !== "Ad" && l !== "AD" &&
                    !l.toLowerCase().includes("showing results") && !l.includes("₹") && 
                    !/\b\d+%\s*OFF\b/i.test(l) && !/\bmins?\b/i.test(l) && 
                    !/^\d+\s*(g|kg|ml|l|pcs|units|pack)$/i.test(l) && l.length > 3
                ) || "Product";

                const price = lines.find(l => l.startsWith("₹")) || lines.find(l => l.includes("₹")) || "₹100";
                const pack = lines.find(l => /\b\d+\s*(g|kg|ml|l|pcs|units)\b/i.test(l) || /^\d+\s*pack/i.test(l)) || "Standard";

                return { id: "blk_" + Math.random().toString(36).substr(2, 9), title: title, price: price, pack: pack, is_ad: isAd };
            });
        }""")

    ad_rank, org_rank, overall = 1, 1, 1
    for card in (raw_items or []):
        clean_title = card["title"].strip()
        if len(clean_title) > 2 and "showing results" not in clean_title.lower():
            brand = extract_brand(clean_title)
            results.append({
                "Platform": "Blinkit",
                "Overall Shelf Pos": overall,
                "Type": "Sponsored Ad" if card["is_ad"] else "Organic",
                "Placement Rank": f"Ad #{ad_rank}" if card["is_ad"] else f"Org #{org_rank}",
                "Product Name": clean_title,
                "Brand": brand,
                "Price": card["price"],
                "Pack Size": card["pack"],
                "Product ID": card["id"]
            })
            if card["is_ad"]:
                ad_rank += 1
            else:
                org_rank += 1
            overall += 1
    return results


# =====================================================================
# 3. INSTAMART SCRAPER
# =====================================================================
async def scan_instamart(search_query, lat="13.0470976", lon="77.5476596"):
    results = []
    encoded_query = urllib.parse.quote(search_query.strip())
    target_lat = float(lat) if lat else 13.0470976
    target_lon = float(lon) if lon else 77.5476596

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = await get_or_reuse_page(context, "swiggy.com")

        target_url = f"https://www.swiggy.com/instamart/search?custom_back=true&query={encoded_query}"
        await page.goto(target_url, wait_until="load", timeout=45000)

        loc_cookie_val = json.dumps({"address": "Bangalore", "lat": target_lat, "lng": target_lon})
        try:
            await context.add_cookies([
                {"name": "userLocation", "value": urllib.parse.quote(loc_cookie_val), "domain": ".swiggy.com", "path": "/"},
                {"name": "lat", "value": str(target_lat), "domain": ".swiggy.com", "path": "/"},
                {"name": "lng", "value": str(target_lon), "domain": ".swiggy.com", "path": "/"}
            ])
            await page.evaluate(f"""() => {{
                localStorage.setItem('userLocation', JSON.stringify({{"lat": {target_lat}, "lng": {target_lon}, "address": "Bangalore"}}));
            }}""")
        except Exception:
            pass

        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

        await asyncio.sleep(2.0)

        for _ in range(4):
            try:
                await page.evaluate("() => window.scrollBy(0, 700);")
                await asyncio.sleep(0.6)
            except Exception:
                await asyncio.sleep(0.5)
                break

        try:
            await page.evaluate("() => window.scrollTo(0, 0);")
        except Exception:
            pass
        await asyncio.sleep(1.0)

        raw_items = await page.evaluate(r"""() => {
            const allCards = Array.from(document.querySelectorAll(
                '[data-testid*="item-collection-card"], [data-testid*="product-card"], div[class*="_3Rr1X"], div[class*="ProductCard"], div[data-testid*="itemCard"]'
            ));

            const gridCards = allCards.filter(tile => {
                let ancestor = tile.parentElement;
                while (ancestor && ancestor !== document.body) {
                    const style = window.getComputedStyle(ancestor);
                    if (style.overflowX === 'scroll' || style.overflowX === 'auto') return false;
                    const cls = String(ancestor.className || '').toLowerCase();
                    if (cls.includes('carousel') || cls.includes('slider') || cls.includes('horizontal')) return false;
                    ancestor = ancestor.parentElement;
                }

                const r = tile.getBoundingClientRect();
                return r.width >= 80 && r.height >= 110;
            });

            const cardMap = new Map();
            gridCards.forEach(tile => {
                const rect = tile.getBoundingClientRect();
                const key = `${Math.round(rect.left + window.scrollX)}_${Math.round(rect.top + window.scrollY)}`;
                if (!cardMap.has(key)) {
                    cardMap.set(key, {
                        el: tile,
                        x: Math.round(rect.left + window.scrollX),
                        y: Math.round(rect.top + window.scrollY)
                    });
                }
            });

            const cards = Array.from(cardMap.values());
            cards.sort((a, b) => (Math.abs(a.y - b.y) > 40 ? a.y - b.y : a.x - b.x));

            return cards.map(c => {
                const tile = c.el;
                const fullText = (tile.innerText || "");
                const lines = fullText.split('\n').map(l => l.trim()).filter(Boolean);

                const allInner = Array.from(tile.querySelectorAll('*'));
                let isAd = lines.some(l => l === "Ad" || l === "AD" || l === "Sponsored") ||
                           allInner.some(e => {
                               const t = (e.innerText || e.textContent || '').trim();
                               return t === "Ad" || t === "AD" || t === "Sponsored";
                           });

                if (!isAd && tile.parentElement) {
                    const pText = (tile.parentElement.innerText || '');
                    if (/\bAd\b/.test(pText)) isAd = true;
                }

                let title = lines.find(l => 
                    l !== "Ad" && l !== "AD" && l !== "+" && l !== "ADD" &&
                    !l.toLowerCase().includes("switch") && !l.toLowerCase().includes("mins") &&
                    !/\b\d+%\s*OFF\b/i.test(l) &&
                    !/^\d+(\.\d+)?\s*(g|kg|ml|l|pcs|units|pack)$/i.test(l) &&
                    !/^\d{2,4}$/.test(l) && l.length > 3
                ) || "Product";

                title = title.replace(/^SOLD\s*OUT\s*/i, '').trim();

                const matchedPack = lines.find(l => /^\d+(\.\d+)?\s*(g|kg|ml|l|pcs|units|pack)$/i.test(l) || /^\d+\s*x\s*\d+/i.test(l));
                const pack = matchedPack || (lines.find(l => /\b\d+\s*(g|kg|ml|l)\b/i.test(l)) || "Standard");

                let price = "N/A";

                for (const l of lines) {
                    const allMatches = Array.from(l.matchAll(/(?:₹|Rs\.?)\s*(\d+)/gi));
                    if (allMatches.length > 0) {
                        price = `₹${allMatches[0][1]}`;
                        break;
                    }
                }

                if (price === "N/A") {
                    const offMatch = fullText.match(/\d+%\s*OFF[\s\n\r]*₹?\s*(\d+)/i);
                    if (offMatch) {
                        price = `₹${offMatch[1]}`;
                    }
                }

                if (price === "N/A") {
                    for (const el of allInner) {
                        if (el.children.length === 0) {
                            const txt = (el.innerText || el.textContent || '').trim();
                            const m = txt.match(/^₹?\s*(\d{2,4})$/);
                            if (m) {
                                const style = window.getComputedStyle(el);
                                const isCrossed = style.textDecoration.includes('line-through') || (el.parentElement && window.getComputedStyle(el.parentElement).textDecoration.includes('line-through'));
                                if (!isCrossed && Number(m[1]) >= 15 && Number(m[1]) <= 5000) {
                                    price = `₹${m[1]}`;
                                    break;
                                }
                            }
                        }
                    }
                }

                if (price === "N/A") {
                    for (let i = 0; i < lines.length; i++) {
                        if (/^\d{2,4}$/.test(lines[i])) {
                            const val = Number(lines[i]);
                            if (val >= 20 && val <= 4000) {
                                price = `₹${val}`;
                                break;
                            }
                        }
                    }
                }

                return { id: "im_" + Math.random().toString(36).substr(2, 8), title: title, price: price, pack: pack, is_ad: isAd };
            });
        }""")

    seen_records = set()
    ad_rank, org_rank, overall = 1, 1, 1
    for card in (raw_items or []):
        clean_title = card["title"].strip()
        if "explore" in clean_title.lower() or len(clean_title) <= 3 or clean_title.upper() == "SOLD OUT":
            continue

        record_key = f"{clean_title.lower()}::{card['is_ad']}"
        if record_key not in seen_records:
            seen_records.add(record_key)
            brand = extract_brand(clean_title)
            results.append({
                "Platform": "Instamart",
                "Overall Shelf Pos": overall,
                "Type": "Sponsored Ad" if card["is_ad"] else "Organic",
                "Placement Rank": f"Ad #{ad_rank}" if card["is_ad"] else f"Org #{org_rank}",
                "Product Name": clean_title,
                "Brand": brand,
                "Price": card["price"],
                "Pack Size": card["pack"],
                "Product ID": card["id"]
            })
            if card["is_ad"]:
                ad_rank += 1
            else:
                org_rank += 1
            overall += 1
    return results


if __name__ == "__main__":
    platform = sys.argv[1].lower() if len(sys.argv) > 1 else "blinkit"
    q = sys.argv[2] if len(sys.argv) > 2 else "kaju katli"
    lat = sys.argv[3] if len(sys.argv) > 3 else "13.0470976"
    lon = sys.argv[4] if len(sys.argv) > 4 else "77.5476596"

    try:
        if platform == "zepto":
            data = asyncio.run(scan_zepto(q, lat, lon))
        elif platform == "instamart":
            data = asyncio.run(scan_instamart(q, lat, lon))
        else:
            data = asyncio.run(scan_blinkit(q, lat, lon))
    except Exception as e:
        print(f"[TEST_BLINKIT ERROR]: {traceback.format_exc()}", file=sys.stderr)
        data = []

    print("__JSON_START__" + json.dumps(data, ensure_ascii=False) + "__JSON_END__", flush=True)
