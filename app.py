import streamlit as st
import pandas as pd
import json
import io
import re
import os
import sys
import time
from datetime import datetime
import altair as alt
from streamlit_autorefresh import st_autorefresh
import urllib.parse
from curl_cffi import requests

st.set_page_config(
    page_title="Quick Commerce Shelf Monitor & Bidding Desk",
    page_icon="⚡",
    layout="wide"
)

# Streamlit width compatibility
def df_width():
    try:
        ver = tuple(map(int, st.__version__.split(".")[:2]))
        if ver >= (1, 40):
            return {"width": "stretch"}
    except Exception:
        pass
    return {"use_container_width": True}

WIDTH_KWARG = df_width()
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shelf_history.json")

LOCATION_LOOKUP = {
    # Pincodes & Bangalore Localities
    "560021": {"name": "Jalahalli", "lat": "13.0470976", "lon": "77.5476596"},
    "jalahalli": {"name": "Jalahalli", "lat": "13.0470976", "lon": "77.5476596"},
    "560037": {"name": "Marathahalli", "lat": "12.959172", "lon": "77.697419"},
    "marathahalli": {"name": "Marathahalli", "lat": "12.959172", "lon": "77.697419"},
    "560103": {"name": "Bellandur", "lat": "12.926031", "lon": "77.676246"},
    "bellandur": {"name": "Bellandur", "lat": "12.926031", "lon": "77.676246"},
    "560038": {"name": "Indiranagar", "lat": "12.978369", "lon": "77.640835"},
    "indiranagar": {"name": "Indiranagar", "lat": "12.978369", "lon": "77.640835"},
    "560034": {"name": "Koramangala", "lat": "12.935242", "lon": "77.624480"},
    "koramangala": {"name": "Koramangala", "lat": "12.935242", "lon": "77.624480"},
    "560001": {"name": "MG Road", "lat": "12.971598", "lon": "77.594563"},
    "mg road": {"name": "MG Road", "lat": "12.971598", "lon": "77.594563"},
    "560076": {"name": "BTM Layout", "lat": "12.916575", "lon": "77.610116"},
    "btm": {"name": "BTM Layout", "lat": "12.916575", "lon": "77.610116"},
    "btm layout": {"name": "BTM Layout", "lat": "12.916575", "lon": "77.610116"},
    "560068": {"name": "Electronic City", "lat": "12.899446", "lon": "77.625475"},
    "electronic city": {"name": "Electronic City", "lat": "12.899446", "lon": "77.625475"},
    "560066": {"name": "Whitefield", "lat": "12.969819", "lon": "77.749972"},
    "whitefield": {"name": "Whitefield", "lat": "12.969819", "lon": "77.749972"},
    "560004": {"name": "Basavanagudi", "lat": "12.943187", "lon": "77.573787"},
    "basavanagudi": {"name": "Basavanagudi", "lat": "12.943187", "lon": "77.573787"},
    "560040": {"name": "Vijayanagar", "lat": "12.9719", "lon": "77.5305"},
    "vijayanagar": {"name": "Vijayanagar", "lat": "12.9719", "lon": "77.5305"},
    "vijay nagar": {"name": "Vijayanagar", "lat": "12.9719", "lon": "77.5305"},
    "560068": {"name": "Bommanahalli", "lat": "12.9029", "lon": "77.6242"},
    "bommanahalli": {"name": "Bommanahalli", "lat": "12.9029", "lon": "77.6242"},
    "560091": {"name": "Viswaneedam", "lat": "12.990000", "lon": "77.510000"}
}

def resolve_location(user_input: str):
    clean = str(user_input).strip().lower()
    if clean in LOCATION_LOOKUP:
        loc = LOCATION_LOOKUP[clean]
        return loc["lat"], loc["lon"], f"{loc['name']} ({clean})"
    # Numeric 6-digit fallback
    if re.match(r"^\d{6}$", clean):
        return "13.0470976", "77.5476596", f"Pincode ({clean})"
    # Generalized Bangalore centroid fallback
    return "12.971598", "77.594563", f"{user_input.title()} (Bangalore)"

EXCLUDED_BRANDS = ["anandhaas", "shree anandhaas", "anandhas", "ananda dairy", "ananda"]

def is_my_brand(brand_name: str) -> bool:
    b = str(brand_name).strip().lower()
    for exc in EXCLUDED_BRANDS:
        if exc in b:
            return False
    is_anand = bool(re.search(r"\banand(\s+sweets)?\b", b))
    is_chaknow = bool(re.search(r"\bchak(\s*now)?\b", b))
    return is_anand or is_chaknow

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

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_history(history_data):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving history: {e}")

def export_history_to_excel():
    history = load_history()
    all_rows = []
    for key, data in history.items():
        parts = key.split("_")
        store = parts[0].capitalize()
        kw = parts[1] if len(parts) > 1 else ""
        pin = parts[2] if len(parts) > 2 else ""
        scan_time = data.get("timestamp", "")
        for item in data.get("items", []):
            all_rows.append({
                "Scan Timestamp": scan_time,
                "Platform": store,
                "Search Keyword": kw,
                "Location": pin,
                "Overall Shelf Pos": item.get("Overall Shelf Pos"),
                "Type": item.get("Type"),
                "Brand": item.get("Brand"),
                "Product Name": item.get("Product Name"),
                "Price": item.get("Price"),
                "Target Brand Flag": "YES" if is_my_brand(item.get("Brand", "")) else "NO"
            })
    df_all = pd.DataFrame(all_rows)
    if df_all.empty:
        df_all = pd.DataFrame(columns=["Scan Timestamp", "Platform", "Search Keyword", "Location", "Overall Shelf Pos", "Type", "Brand", "Product Name", "Price"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_all.to_excel(writer, index=False, sheet_name='Historical Scans')
        df_targets = df_all[df_all["Target Brand Flag"] == "YES"]
        df_targets.to_excel(writer, index=False, sheet_name='Target Brands Shift Log')
    return buf.getvalue()

def fetch_live_platform_data(store: str, query: str, lat: str, lon: str):
    results = []
    store = store.lower()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "accept": "application/json, text/plain, */*",
        "lat": str(lat),
        "lon": str(lon),
        "app_client": "consumer_web"
    }
    
    if store == "blinkit":
        url = f"https://blinkit.com/v1/layout/search?q={urllib.parse.quote(query)}"
        try:
            r = requests.get(url, headers=headers, impersonate="chrome124", timeout=12)
            if r.status_code == 200:
                data = r.json()
                widgets = data.get("layout", {}).get("widgets", [])
                overall, ad_r, org_r = 1, 1, 1
                for w in widgets:
                    for prod in w.get("data", {}).get("products", []):
                        name = prod.get("name", "").strip()
                        if not name: continue
                        is_ad = bool(prod.get("is_sponsored", False) or prod.get("ad_id"))
                        price = f"₹{prod.get('price', 0)}"
                        pack = prod.get("unit", "Standard")
                        brand = extract_brand(name)
                        results.append({
                            "Overall Shelf Pos": overall,
                            "Type": "Sponsored Ad" if is_ad else "Organic",
                            "Placement Rank": f"Ad #{ad_r}" if is_ad else f"Org #{org_r}",
                            "Product Name": name,
                            "Brand": brand,
                            "Price": price,
                            "Pack Size": pack
                        })
                        if is_ad: ad_r += 1
                        else: org_r += 1
                        overall += 1
        except Exception:
            pass

    elif store == "zepto":
        url = f"https://api.zeptonow.com/api/v3/search?query={urllib.parse.quote(query)}&pageNumber=1&mode=MANUAL"
        z_headers = dict(headers)
        z_headers["store-id"] = "34774f44-f41c-4bde-993b-8e93684ff94f"
        z_headers["compatible_mode"] = "true"
        try:
            r = requests.get(url, headers=z_headers, impersonate="chrome124", timeout=12)
            if r.status_code == 200:
                data = r.json()
                overall, ad_r, org_r = 1, 1, 1
                for block in data.get("layout", []):
                    for item in block.get("data", {}).get("resolver", {}).get("data", {}).get("items", []):
                        prod = item.get("product", {})
                        name = prod.get("name", "").strip()
                        if not name: continue
                        is_ad = bool(item.get("isSponsored", False) or prod.get("isSponsored", False))
                        mrp = prod.get("discountedSellingPrice", 0) / 100
                        price = f"₹{int(mrp)}" if mrp else "₹99"
                        pack = prod.get("unit", "Standard")
                        brand = extract_brand(name)
                        results.append({
                            "Overall Shelf Pos": overall,
                            "Type": "Sponsored Ad" if is_ad else "Organic",
                            "Placement Rank": f"Ad #{ad_r}" if is_ad else f"Org #{org_r}",
                            "Product Name": name,
                            "Brand": brand,
                            "Price": price,
                            "Pack Size": pack
                        })
                        if is_ad: ad_r += 1
                        else: org_r += 1
                        overall += 1
        except Exception:
            pass

    elif store == "instamart":
        url = f"https://www.swiggy.com/api/instamart/search?query={urllib.parse.quote(query)}&lat={lat}&lng={lon}"
        try:
            r = requests.get(url, headers=headers, impersonate="chrome124", timeout=12)
            if r.status_code == 200:
                data = r.json()
                overall, ad_r, org_r = 1, 1, 1
                for widget in data.get("data", {}).get("widgets", []):
                    for prod in widget.get("data", {}).get("nodes", []):
                        name = prod.get("display_name", "").strip()
                        if not name: continue
                        is_ad = bool(prod.get("is_sponsored", False) or prod.get("ad_info"))
                        price_val = prod.get("price", {}).get("offer_price", 0)
                        price = f"₹{price_val}" if price_val else "₹99"
                        pack = prod.get("quantity", "Standard")
                        brand = extract_brand(name)
                        results.append({
                            "Overall Shelf Pos": overall,
                            "Type": "Sponsored Ad" if is_ad else "Organic",
                            "Placement Rank": f"Ad #{ad_r}" if is_ad else f"Org #{org_r}",
                            "Product Name": name,
                            "Brand": brand,
                            "Price": price,
                            "Pack Size": pack
                        })
                        if is_ad: ad_r += 1
                        else: org_r += 1
                        overall += 1
        except Exception:
            pass

    return results

# Session State Setup
if "keyword_list" not in st.session_state:
    st.session_state.keyword_list = ["kaju katli", "mysore pak", "besan laddu"]

if "location_list" not in st.session_state:
    st.session_state.location_list = ["560021", "560037", "560103", "Koramangala", "Indiranagar", "Whitefield", "Vijay Nagar", "Bommanahalli"]

if "shelf_data" not in st.session_state:
    st.session_state.shelf_data = []

if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = time.time()

# Sidebar
with st.sidebar:
    st.header("🔔 Alert Channels")
    alert_blinkit = st.checkbox("Blinkit Alerts", value=True)
    alert_zepto = st.checkbox("Zepto Alerts", value=True)
    alert_instamart = st.checkbox("Instamart Alerts", value=True)
    
    active_platforms = []
    if alert_blinkit: active_platforms.append("Blinkit")
    if alert_zepto: active_platforms.append("Zepto")
    if alert_instamart: active_platforms.append("Instamart")

    st.divider()
    st.subheader("🎯 Shift Alert Scope")
    alert_scope = st.radio(
        "Evaluate rank shifts for:",
        ["My Brands Only", "Top-5 Competitor Ads Only", "Both (Full Visibility)"],
        index=0
    )

    st.divider()
    st.header("💡 Bidding Engine Filter")
    suggest_blinkit = st.checkbox("Blinkit (Brands Central)", value=True)
    suggest_zepto = st.checkbox("Zepto Brand Engine", value=True)
    suggest_instamart = st.checkbox("Swiggy Ads", value=True)

    suggest_platforms = []
    if suggest_blinkit: suggest_platforms.append("Blinkit")
    if suggest_zepto: suggest_platforms.append("Zepto")
    if suggest_instamart: suggest_platforms.append("Instamart")

    st.divider()
    st.subheader("🔄 Live Polling")
    auto_monitor = st.checkbox("Enable Auto-Scan Loop", value=False)
    interval_mins = st.slider("Frequency (Minutes)", min_value=1, max_value=60, value=5)

st.title("Quick Commerce Shelf Monitor & Bidding Desk")
st.caption("Algorithmic bidding recommendations, cannibalization defense, and shelf-share analytics for Anand Sweets & Chak Now.")

st_autorefresh(interval=30 * 1000, key="auto_scan_ticker")

def generate_live_alerts(current_items, active_channels, scope_filter):
    if not active_channels:
        return ["ℹ️ All platform alerts are currently toggled off in the sidebar."]

    history = load_history()
    alerts = []

    for card in current_items:
        platform = card.get("Platform", "").capitalize()
        if platform not in [c.capitalize() for c in active_channels]:
            continue

        kw = card.get("Search Term", "")
        pin = card.get("Location", "")
        store_key = platform.lower()
        cache_key = f"{store_key}_{str(kw).lower().strip()}_{str(pin).lower().strip()}"
        
        prev_scan = history.get(cache_key, None)
        prev_time = prev_scan.get("timestamp", "prior scan") if prev_scan else ""
        
        prev_lookup = {}
        if prev_scan:
            for p in prev_scan.get("items", []):
                p_clean = str(p.get("Product Name", "")).strip().lower()
                p_type = str(p.get("Type", "")).strip().lower()
                prev_lookup[f"{p_clean}::{p_type}"] = p.get("Overall Shelf Pos")

        p_name = str(card.get("Product Name", "")).strip()
        p_type = str(card.get("Type", "")).strip()
        item_key = f"{p_name.lower()}::{p_type.lower()}"
        
        c_pos = int(card.get("Overall Shelf Pos", 0))
        brand_name = card.get("Brand", "")
        is_mine = is_my_brand(brand_name)
        is_ad = p_type == "Sponsored Ad"

        qualifies = False
        if scope_filter == "My Brands Only" and is_mine:
            qualifies = True
        elif scope_filter == "Top-5 Competitor Ads Only" and is_ad and not is_mine and c_pos <= 5:
            qualifies = True
        elif scope_filter == "Both (Full Visibility)":
            if is_mine or (is_ad and not is_mine and c_pos <= 5):
                qualifies = True

        if not qualifies:
            continue

        type_tag = "*(Sponsored Ad)*" if is_ad else "*(Organic)*"

        if item_key in prev_lookup:
            old_pos = int(prev_lookup[item_key])
            delta = old_pos - c_pos
            if delta > 0:
                alerts.append(
                    f"🟢 **Rank Gain**: {brand_name} item '**{p_name}**' {type_tag} gained from **Pos #{old_pos}** ➔ **Pos #{c_pos}** (+{delta}) on **{platform}** ({kw} @ {pin}, vs. {prev_time})."
                )
            elif delta < 0:
                alerts.append(
                    f"🔻 **Rank Drop**: {brand_name} item '**{p_name}**' {type_tag} dropped from **Pos #{old_pos}** ➔ **Pos #{c_pos}** ({delta}) on **{platform}** ({kw} @ {pin}, vs. {prev_time})."
                )
            else:
                if is_mine:
                    alerts.append(
                        f"⚪ **Maintained**: {brand_name} item '**{p_name}**' {type_tag} held **Pos #{c_pos}** on **{platform}** ({kw} @ {pin}, unchanged since {prev_time})."
                    )
        else:
            if is_mine:
                alerts.append(
                    f"🟢 **Rank Track**: {brand_name} item '**{p_name}**' {type_tag} at **Pos #{c_pos}** (**{card.get('Placement Rank', '')}**) on **{platform}** ({kw} @ {pin})."
                )

    return alerts

active_alerts = generate_live_alerts(st.session_state.shelf_data, active_platforms, alert_scope)

with st.expander("🚨 Recent Background Incident & Alert Log", expanded=True):
    if active_alerts:
        for a in active_alerts:
            st.markdown(f"- {a}")
    else:
        if st.session_state.shelf_data:
            st.write("No matching incidents for the active alert filters.")
        else:
            st.write("No scans recorded yet. Enter location and click 'Fetch Shelf Now' below.")

    st.divider()
    st.markdown("**Export Comprehensive Shelf & Shift Data:**")
    dl_c1, dl_c2 = st.columns([1.5, 1.5])
    with dl_c1:
        excel_history_data = export_history_to_excel()
        st.download_button(
            "📊 Download Shelf History (.xlsx)",
            data=excel_history_data,
            file_name="shelf_history_master.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            **WIDTH_KWARG
        )
    with dl_c2:
        if st.session_state.shelf_data:
            current_df = pd.DataFrame(st.session_state.shelf_data)
            csv_data = current_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download Current Scan (.csv)",
                data=csv_data,
                file_name="shelf_current.csv",
                mime="text/csv",
                **WIDTH_KWARG
            )
        else:
            st.button("📥 Download Current Scan (.csv)", disabled=True, **WIDTH_KWARG)

st.subheader("🎯 Monitoring Scope: Target Keywords & Locations")
col_sel1, col_sel2 = st.columns(2)

with col_sel1:
    selected_keywords = st.multiselect(
        "Active Search Keywords:",
        options=st.session_state.keyword_list,
        default=[st.session_state.keyword_list[0]] if st.session_state.keyword_list else []
    )
    with st.expander("➕ Add Custom Keyword"):
        new_kw = st.text_input("Enter new keyword (e.g. motichoor laddu):").strip().lower()
        if st.button("Add Keyword") and new_kw:
            if new_kw not in st.session_state.keyword_list:
                st.session_state.keyword_list.append(new_kw)
                st.rerun()

with col_sel2:
    selected_locations = st.multiselect(
        "Active Locations / Pincodes:",
        options=st.session_state.location_list,
        default=[st.session_state.location_list[0]] if st.session_state.location_list else []
    )
    with st.expander("➕ Add Custom Location or Pincode"):
        new_loc = st.text_input("Enter Locality Name or Pincode (e.g. Vijay Nagar, 560040):").strip()
        if st.button("Add Location") and new_loc:
            if new_loc not in st.session_state.location_list:
                st.session_state.location_list.append(new_loc)
                st.rerun()

c_scope, c_store, c_fetch = st.columns([3, 3, 2])
with c_scope:
    store_scope = st.selectbox("Storefront Scope", ["All Enabled Storefronts", "Selected Storefront Only"])
with c_store:
    chosen_store = st.selectbox("Active Store", ["Blinkit", "Zepto", "Instamart"])
with c_fetch:
    st.write("")
    st.write("")
    fetch_btn = st.button("🚀 Fetch Shelf Now", type="primary", **WIDTH_KWARG)

# Background timer
current_time = time.time()
elapsed_time = current_time - st.session_state.last_scan_time
required_interval = interval_mins * 60

if auto_monitor:
    remaining_time = max(0, int(required_interval - elapsed_time))
    st.info(f"⏳ Background auto-scan active. Next scan in: {remaining_time // 60}m {remaining_time % 60}s")

trigger_scan = fetch_btn or (auto_monitor and elapsed_time > required_interval)

if trigger_scan:
    if auto_monitor and elapsed_time > required_interval:
        st.session_state.last_scan_time = current_time

    platforms_to_scan = [chosen_store.capitalize()] if store_scope == "Selected Storefront Only" else [p.capitalize() for p in active_platforms]

    if not selected_keywords:
        st.warning("⚠️ Please select at least one keyword above.")
    elif not selected_locations:
        st.warning("⚠️ Please select at least one location/pincode above.")
    else:
        history = load_history()
        current_time_str = datetime.now().strftime("%I:%M %p, %d %b")
        collected_items = []

        with st.spinner("Executing live extraction using client network..."):
            for store in platforms_to_scan:
                for kw in selected_keywords:
                    for loc in selected_locations:
                        lat, lon, loc_label = resolve_location(loc)
                        
                        # 1. Direct fetch using client network
                        items = fetch_live_platform_data(store, kw, lat, lon)
                        
                        # 2. Local fallback if external connection is blocked
                        if not items:
                            cache_key = f"{store.lower()}_{str(kw).lower().strip()}_{str(loc).lower().strip()}"
                            if cache_key in history:
                                items = history[cache_key].get("items", [])

                        if not items:
                            continue

                        cache_key = f"{store.lower()}_{str(kw).lower().strip()}_{str(loc).lower().strip()}"
                        prev_scan = history.get(cache_key, None)
                        prev_lookup = {}
                        if prev_scan:
                            for p in prev_scan.get("items", []):
                                p_clean = str(p.get("Product Name", "")).strip().lower()
                                p_type = str(p.get("Type", "")).strip().lower()
                                prev_lookup[f"{p_clean}::{p_type}"] = p.get("Overall Shelf Pos")

                        for card in items:
                            card["Platform"] = store.capitalize()
                            card["Search Term"] = kw
                            card["Location"] = loc
                            card["Location Name"] = loc_label

                            p_name = str(card.get("Product Name", "")).strip()
                            p_type = str(card.get("Type", "")).strip()
                            item_key = f"{p_name.lower()}::{p_type.lower()}"
                            c_pos = int(card["Overall Shelf Pos"])

                            if item_key in prev_lookup:
                                old_pos = int(prev_lookup[item_key])
                                delta = old_pos - c_pos
                                card["Rank Shift"] = f"{'+' if delta > 0 else ''}{delta}" if delta != 0 else "-"
                            else:
                                card["Rank Shift"] = "New"

                            collected_items.append(card)

                        history[cache_key] = {
                            "timestamp": current_time_str,
                            "items": [{
                                "Product Name": c["Product Name"],
                                "Brand": c["Brand"],
                                "Overall Shelf Pos": c["Overall Shelf Pos"],
                                "Type": c["Type"],
                                "Price": c["Price"]
                            } for c in items]
                        }

        if collected_items:
            save_history(history)
            st.session_state.shelf_data = collected_items
            st.rerun()
        else:
            st.error("No items returned from storefront scanner. Check network permissions or try another locality.")

def compute_professional_bidding_matrix(items, enabled_platforms):
    if not items:
        return []

    matrix = []
    df_raw = pd.DataFrame(items)
    grouped = df_raw.groupby(["Platform", "Search Term", "Location"])

    normalized_enabled = [p.capitalize() for p in enabled_platforms]

    for (plat, kw, loc), group in grouped:
        if str(plat).capitalize() not in normalized_enabled:
            continue

        my_skus = group[group["Brand"].apply(is_my_brand)]
        competitors = group[~group["Brand"].apply(is_my_brand)]

        my_organic = my_skus[my_skus["Type"] == "Organic"]
        top_org_pos = my_organic["Overall Shelf Pos"].min() if not my_organic.empty else 999
        top_org_item = my_organic[my_organic["Overall Shelf Pos"] == top_org_pos].iloc[0] if not my_organic.empty else None

        comp_ads = competitors[competitors["Type"] == "Sponsored Ad"]
        comp_slot1 = comp_ads[comp_ads["Overall Shelf Pos"] <= 2].iloc[0] if not comp_ads[comp_ads["Overall Shelf Pos"] <= 2].empty else None

        for _, row in my_skus.iterrows():
            title = row["Product Name"]
            pos = int(row["Overall Shelf Pos"])
            is_ad = row["Type"] == "Sponsored Ad"
            shift = row.get("Rank Shift", "-")

            action_badge = "⚪ MAINTAIN BID"
            priority = "LOW"
            target_placement = "Sustain Placement"
            cpc_shift = "Hold (0%)"
            budget_advice = "Normal Daily Cap"
            rationale = "Listing maintains acceptable positioning without immediate auction threat."

            if is_ad and top_org_pos <= 3:
                action_badge = "🛑 PAUSE / REDUCE CPC"
                priority = "CRITICAL"
                target_placement = f"Organic Top-3 Locked (Pos #{top_org_pos})"
                cpc_shift = "-30% to -40% CPC Reduction"
                budget_advice = "Reallocate 50% Budget to Deficit Dark Stores"
                rationale = f"Organic listing '{top_org_item['Product Name']}' is secured at Pos #{top_org_pos}. Paying for an ad here cannibalizes free organic conversions."

            elif is_ad and pos > 4:
                action_badge = "🚀 BOOST BID (SURGE TO ROW 1)"
                priority = "CRITICAL"
                target_placement = "Top-of-Fold Row 1 (Pos 1–4)"
                cpc_shift = "+20% to +30% Bid Surge"
                budget_advice = "Increase Daily Budget Cap (+20%)"
                rationale = f"Ad cleared at Pos #{pos} (Row 2+). Click-through rate decays by >70% below Row 1. Surge bid to win Slot 1–4."

            elif comp_slot1 is not None and (pos > int(comp_slot1["Overall Shelf Pos"])):
                action_badge = "🛡️ DEFENSIVE COUNTER-BID"
                priority = "HIGH"
                target_placement = "Capture Ad Slot #1 (Pos 1–2)"
                cpc_shift = "+15% to +20% Surge"
                budget_advice = "Increase Daily Budget Cap (+15%)"
                rationale = f"Competitor '{comp_slot1['Brand']}' took Ad Slot #{comp_slot1['Overall Shelf Pos']}. Outbid to protect purchase intent."

            elif not is_ad and pos >= 4:
                action_badge = "📢 ACTIVATE SPONSORED BID"
                priority = "HIGH"
                target_placement = "Sponsored Slot #1 or #2"
                cpc_shift = "Set Category Benchmark CPC"
                budget_advice = "Open Dedicated Campaign Line"
                rationale = f"Organic visibility is drifting at Pos #{pos}. Activating a targeted ad will push this SKU back to row 1."

            elif is_ad and pos <= 3:
                action_badge = "🟢 LOCK TOP POSITION"
                priority = "MEDIUM"
                target_placement = f"Hold Slot #{pos}"
                cpc_shift = "Test -5% Decrement"
                budget_advice = "Sustain Current Cap"
                rationale = "Holding premium ad placement. Incrementally shave CPC by 5% to discover minimum winning auction clearing price."

            matrix.append({
                "Urgency": priority,
                "Platform": plat,
                "Keyword": kw,
                "Location": loc,
                "Target SKU": title,
                "Current Position": f"Pos #{pos} ({row.get('Placement Rank', '')})",
                "Shift": shift,
                "Recommended Action": action_badge,
                "Target Placement": target_placement,
                "Suggested CPC Shift": cpc_shift,
                "Budget Sizing": budget_advice,
                "Commercial Rationale": rationale
            })

    return matrix

if st.session_state.shelf_data:
    df = pd.DataFrame(st.session_state.shelf_data)
    st.success(f"Displaying {len(df)} total product placements.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Tracked Items", len(df))
    ad_count = len(df[df["Type"] == "Sponsored Ad"])
    m2.metric("Overall Ad Load (SOV)", f"{(ad_count / len(df) * 100):.1f}%" if len(df) > 0 else "0%")
    m3.metric("Target Brands Detected", len(df[df["Brand"].apply(is_my_brand)]))
    m4.metric("Locations Scanned", len(df["Location"].unique()) if "Location" in df.columns else 1)

    st.divider()

    st.subheader("💡 Professional Quick Commerce Bidding Desk")
    bidding_matrix = compute_professional_bidding_matrix(st.session_state.shelf_data, suggest_platforms)

    if bidding_matrix:
        b_df = pd.DataFrame(bidding_matrix)

        def style_bidding_table(row):
            action = row["Recommended Action"]
            urgency = row["Urgency"]
            if "PAUSE" in action or urgency == "CRITICAL":
                return ['background-color: #fce8e6; color: #a51d24; font-weight: bold;'] * len(row)
            elif "BOOST" in action or "DEFENSIVE" in action:
                return ['background-color: #e8f0fe; color: #1967d2; font-weight: bold;'] * len(row)
            elif "ACTIVATE" in action:
                return ['background-color: #fef7e0; color: #b06000; font-weight: bold;'] * len(row)
            return [''] * len(row)

        c_export_bid, _ = st.columns([2.8, 7.2])
        with c_export_bid:
            bid_buf = io.BytesIO()
            with pd.ExcelWriter(bid_buf, engine='openpyxl') as writer:
                b_df.to_excel(writer, index=False, sheet_name='ActionableBiddingPlan')
            st.download_button(
                "📥 Export Bidding Action Sheet (.xlsx)",
                data=bid_buf.getvalue(),
                file_name="qcom_bidding_action_plan.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                **WIDTH_KWARG
            )

        st.dataframe(b_df.style.apply(style_bidding_table, axis=1), height=310, **WIDTH_KWARG)
    else:
        st.info("No target brand items requiring bidding intervention on the selected platforms.")

    st.divider()

    st.subheader("🎯 Sponsored Placements & Top-of-Fold Takeovers")
    c_ad_tbl, c_top_tbl = st.columns([3, 2])

    with c_ad_tbl:
        st.markdown("**Identified Sponsored Placements**")
        s_df = df[df["Type"] == "Sponsored Ad"]
        if not s_df.empty:
            cols = ["Platform", "Location", "Overall Shelf Pos", "Placement Rank", "Brand", "Product Name", "Price"]
            display_s_df = s_df[[c for c in cols if c in s_df.columns]].reset_index(drop=True)

            def style_sponsored(row):
                if is_my_brand(row["Brand"]):
                    return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row)
                return [''] * len(row)

            st.dataframe(display_s_df.style.apply(style_sponsored, axis=1), height=230, **WIDTH_KWARG)
        else:
            st.info("No sponsored ads present on current selections.")

    with c_top_tbl:
        st.markdown("**Top-of-Fold (Slots 1 to 4)**")
        top_group_cols = [c for c in ["Platform", "Search Term", "Location"] if c in df.columns]
        top4_df = df.groupby(top_group_cols).head(4)[["Platform", "Overall Shelf Pos", "Type", "Brand", "Product Name"]]

        def style_top(row):
            is_mine = is_my_brand(row["Brand"])
            is_ad = row["Type"] == "Sponsored Ad"
            if is_mine and is_ad:
                return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row)
            elif is_mine:
                return ['background-color: #dcfce7; color: #166534; font-weight: bold;'] * len(row)
            elif is_ad:
                return ['background-color: #fef08a; color: #854d0e; font-weight: bold;'] * len(row)
            return [''] * len(row)

        st.dataframe(top4_df.style.apply(style_top, axis=1), height=230, **WIDTH_KWARG)

    st.divider()

    st.subheader("📊 Brand Shelf Share (Target vs. Competitors)")
    brand_counts = df["Brand"].value_counts().reset_index()
    brand_counts.columns = ["Brand", "Count"]
    brand_counts["Classification"] = brand_counts["Brand"].apply(
        lambda b: "My Brand (Anand / Chak Now)" if is_my_brand(b) else "Competitor"
    )

    chart = alt.Chart(brand_counts).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X('Brand:N', sort='-y', title="Brand"),
        y=alt.Y('Count:Q', title="SKUs on Shelf"),
        color=alt.Color(
            'Classification:N',
            scale=alt.Scale(
                domain=['My Brand (Anand / Chak Now)', 'Competitor'],
                range=['#28a745', '#4a5568']
            ),
            legend=alt.Legend(title="Ownership")
        ),
        tooltip=['Brand', 'Count', 'Classification']
    ).properties(height=320)

    st.altair_chart(chart, **WIDTH_KWARG)

    st.divider()

    st.subheader("📋 Complete Master Shelf Inventory")
    c_dl1, c_dl2, _ = st.columns([1.5, 1.5, 7])
    with c_dl1:
        st.download_button(
            "📥 Export Current Shelf (.csv)",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name="current_shelf.csv",
            mime="text/csv"
        )
    with c_dl2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='CurrentShelf')
        st.download_button(
            "📊 Export Current Shelf (.xlsx)",
            data=buf.getvalue(),
            file_name="current_shelf.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def style_full(row):
        is_mine = is_my_brand(row["Brand"])
        is_ad = row["Type"] == "Sponsored Ad"
        if is_mine and is_ad:
            return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row)
        elif is_mine:
            return ['background-color: #dcfce7; color: #166534; font-weight: bold;'] * len(row)
        elif is_ad:
            return ['background-color: #fef08a; color: #854d0e; font-weight: bold;'] * len(row)
        return [''] * len(row)

    st.dataframe(df.style.apply(style_full, axis=1), height=550, **WIDTH_KWARG)
