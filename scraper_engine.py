import json
import re
import urllib.parse
from curl_cffi import requests

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

EXCLUDED_BRANDS = ["anandhaas", "shree anandhaas", "anandhas", "ananda dairy", "ananda"]

def is_my_brand(brand_name: str) -> bool:
    b = str(brand_name).strip().lower()
    for exc in EXCLUDED_BRANDS:
        if exc in b:
            return False
    is_anand = bool(re.search(r"\banand(\s+sweets)?\b", b))
    is_chaknow = bool(re.search(r"\bchak(\s*now)?\b", b))
    return is_anand or is_chaknow

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


def fetch_blinkit_live(query: str, lat: str = "13.0470976", lon: str = "77.5476596"):
    results = []
    encoded_q = urllib.parse.quote(query.strip())
    
    # Primary & Mirror Relay Endpoints
    target_urls = [
        f"https://blinkit.com/v1/layout/search?q={encoded_q}",
        f"https://api.allorigins.win/raw?url={urllib.parse.quote(f'https://blinkit.com/v1/layout/search?q={encoded_q}')}"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "lat": str(lat),
        "lon": str(lon),
        "app_client": "consumer_web",
        "accept": "application/json, text/plain, */*"
    }

    for url in target_urls:
        try:
            r = requests.get(url, headers=headers, impersonate="chrome124", timeout=10)
            if r.status_code == 200:
                data = r.json()
                widgets = data.get("layout", {}).get("widgets", [])
                overall_pos = 1
                ad_rank, org_rank = 1, 1

                for w in widgets:
                    for product in w.get("data", {}).get("products", []):
                        title = product.get("name", "").strip()
                        if not title:
                            continue

                        is_ad = product.get("is_sponsored", False) or (product.get("ad_id") is not None)
                        price = f"₹{product.get('price', 0)}"
                        pack = product.get("unit", "Standard")
                        brand = extract_brand(title)

                        results.append({
                            "Platform": "Blinkit",
                            "Overall Shelf Pos": overall_pos,
                            "Placement Rank": f"Ad #{ad_rank}" if is_ad else f"Org #{org_rank}",
                            "Type": "Sponsored Ad" if is_ad else "Organic",
                            "Product Name": title,
                            "Brand": brand,
                            "Price": price,
                            "Pack Size": pack
                        })
                        if is_ad:
                            ad_rank += 1
                        else:
                            org_rank += 1
                        overall_pos += 1

                if results:
                    break
        except Exception:
            continue

    return results


def fetch_zepto_live(query: str, lat: str = "13.0470976", lon: str = "77.5476596"):
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "accept": "application/json, text/plain, */*",
        "store-id": "34774f44-f41c-4bde-993b-8e93684ff94f",
        "compatible_mode": "true"
    }
    url = f"https://api.zeptonow.com/api/v3/search?query={urllib.parse.quote(query)}&pageNumber=1&mode=MANUAL"

    try:
        r = requests.get(url, headers=headers, impersonate="chrome124", timeout=10)
        if r.status_code == 200:
            data = r.json()
            layout = data.get("layout", [])
            overall_pos = 1
            ad_rank, org_rank = 1, 1

            for block in layout:
                items = block.get("data", {}).get("resolver", {}).get("data", {}).get("items", [])
                for item in items:
                    product = item.get("product", {})
                    title = product.get("name", "").strip()
                    if not title:
                        continue

                    is_ad = item.get("isSponsored", False) or product.get("isSponsored", False)
                    mrp = product.get("discountedSellingPrice", 0) / 100
                    price = f"₹{int(mrp)}" if mrp else "₹99"
                    pack = product.get("unit", "Standard")
                    brand = extract_brand(title)

                    results.append({
                        "Platform": "Zepto",
                        "Overall Shelf Pos": overall_pos,
                        "Placement Rank": f"Ad #{ad_rank}" if is_ad else f"Org #{org_rank}",
                        "Type": "Sponsored Ad" if is_ad else "Organic",
                        "Product Name": title,
                        "Brand": brand,
                        "Price": price,
                        "Pack Size": pack
                    })
                    if is_ad:
                        ad_rank += 1
                    else:
                        org_rank += 1
                    overall_pos += 1
    except Exception:
        pass

    return results


def fetch_instamart_live(query: str, lat: str = "13.0470976", lon: str = "77.5476596"):
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "accept": "application/json, text/plain, */*"
    }
    encoded = urllib.parse.quote(query)
    url = f"https://www.swiggy.com/api/instamart/search?query={encoded}&lat={lat}&lng={lon}"

    try:
        r = requests.get(url, headers=headers, impersonate="chrome124", timeout=10)
        if r.status_code == 200:
            data = r.json()
            cards = data.get("data", {}).get("widgets", [])
            overall_pos = 1
            ad_rank, org_rank = 1, 1

            for c in cards:
                for prod in c.get("data", {}).get("nodes", []):
                    title = prod.get("display_name", "").strip()
                    if not title:
                        continue

                    is_ad = prod.get("is_sponsored", False) or (prod.get("ad_info") is not None)
                    price_val = prod.get("price", {}).get("offer_price", 0)
                    price = f"₹{price_val}" if price_val else "₹99"
                    pack = prod.get("quantity", "Standard")
                    brand = extract_brand(title)

                    results.append({
                        "Platform": "Instamart",
                        "Overall Shelf Pos": overall_pos,
                        "Placement Rank": f"Ad #{ad_rank}" if is_ad else f"Org #{org_rank}",
                        "Type": "Sponsored Ad" if is_ad else "Organic",
                        "Product Name": title,
                        "Brand": brand,
                        "Price": price,
                        "Pack Size": pack
                    })
                    if is_ad:
                        ad_rank += 1
                    else:
                        org_rank += 1
                    overall_pos += 1
    except Exception:
        pass

    return results
