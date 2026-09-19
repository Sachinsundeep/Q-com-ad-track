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
import streamlit.components.v1 as components
import urllib.parse
from geopy.geocoders import Nominatim

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

# Master Bangalore Locality & Pincode Bi-directional Matrix
LOCATION_ALIASES = {
    "560021": ["560021", "jalahalli"],
    "jalahalli": ["560021", "jalahalli"],
    "560037": ["560037", "marathahalli"],
    "marathahalli": ["560037", "marathahalli"],
    "560103": ["560103", "bellandur"],
    "bellandur": ["560103", "bellandur"],
    "560038": ["560038", "indiranagar"],
    "indiranagar": ["560038", "indiranagar"],
    "560034": ["560034", "koramangala"],
    "koramangala": ["560034", "koramangala"],
    "560001": ["560001", "mg road"],
    "mg road": ["560001", "mg road"],
    "560076": ["560076", "btm", "btm layout"],
    "btm": ["560076", "btm", "btm layout"],
    "btm layout": ["560076", "btm", "btm layout"],
    "560068": ["560068", "electronic city", "bommanahalli"],
    "electronic city": ["560068", "electronic city"],
    "bommanahalli": ["560068", "bommanahalli"],
    "560066": ["560066", "whitefield"],
    "whitefield": ["560066", "whitefield"],
    "560004": ["560004", "basavanagudi"],
    "basavanagudi": ["560004", "basavanagudi"],
    "560040": ["560040", "vijayanagar", "vijay nagar"],
    "vijayanagar": ["560040", "vijayanagar", "vijay nagar"],
    "vijay nagar": ["560040", "vijayanagar", "vijay nagar"],
    "560056": ["560056", "ullal", "bangalore west"],
    "ullal": ["560056", "ullal", "bangalore west"],
    "560091": ["560091", "viswaneedam"],
    "viswaneedam": ["560091", "viswaneedam"],
    "560096": ["560096", "rajajinagar"],
    "rajajinagar": ["560096", "rajajinagar"]
}

LOCATION_COORDINATES = {
    "560021": ("13.0470976", "77.5476596", "Jalahalli (560021)"),
    "560037": ("12.959172", "77.697419", "Marathahalli (560037)"),
    "560103": ("12.926031", "77.676246", "Bellandur (560103)"),
    "560038": ("12.978369", "77.640835", "Indiranagar (560038)"),
    "560034": ("12.935242", "77.624480", "Koramangala (560034)"),
    "560001": ("12.971598", "77.594563", "MG Road (560001)"),
    "560076": ("12.916575", "77.610116", "BTM Layout (560076)"),
    "560068": ("12.899446", "77.625475", "Electronic City / Bommanahalli (560068)"),
    "560066": ("12.969819", "77.749972", "Whitefield (560066)"),
    "560004": ("12.943187", "77.573787", "Basavanagudi (560004)"),
    "560040": ("12.971900", "77.530500", "Vijayanagar (560040)"),
    "560056": ("12.955600", "77.498000", "Ullal (560056)"),
    "560091": ("12.990000", "77.510000", "Viswaneedam (560091)"),
    "560096": ("13.000000", "77.550000", "Rajajinagar (560096)")
}

def resolve_location_coordinates(loc_input: str):
    clean = str(loc_input).strip().lower()
    for pin, aliases in LOCATION_ALIASES.items():
        if clean in aliases or clean == pin:
            if pin in LOCATION_COORDINATES:
                return LOCATION_COORDINATES[pin]
    try:
        geolocator = Nominatim(user_agent="qcom_shelf_monitor_prod", timeout=4)
        target = f"{clean}, Bangalore, India" if not clean.isdigit() else f"{clean}, India"
        loc = geolocator.geocode(target)
        if loc:
            return str(loc.latitude), str(loc.longitude), f"{loc_input.title()}"
    except Exception:
        pass
    return "12.971598", "77.594563", f"{loc_input.title()}"

EXCLUDED_BRANDS = ["anandhaas", "shree anandhaas", "anandhas", "ananda dairy", "ananda"]

def is_my_brand(brand_name: str) -> bool:
    b = str(brand_name).strip().lower()
    for exc in EXCLUDED_BRANDS:
        if exc in b:
            return False
    return bool(re.search(r"\banand(\s+sweets)?\b", b) or re.search(r"\bchak(\s*now)?\b", b))

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
        loc = parts[2] if len(parts) > 2 else ""
        scan_time = data.get("timestamp", "")
        for item in data.get("items", []):
            all_rows.append({
                "Scan Timestamp": scan_time,
                "Platform": store,
                "Search Keyword": kw,
                "Location": loc,
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

# Pre-populate dynamic dropdown options from history
raw_hist = load_history()
hist_kws = sorted(list({k.split("_")[1] for k in raw_hist.keys() if len(k.split("_")) > 1}))
hist_locs = sorted(list({k.split("_")[2] for k in raw_hist.keys() if len(k.split("_")) > 2}))

if not hist_kws:
    hist_kws = ["mysore pak", "kaju katli", "besan laddu", "sweets"]
if not hist_locs:
    hist_locs = ["560091", "560021", "560103", "560034", "560056", "Ullal", "Koramangala"]

if "keyword_list" not in st.session_state:
    st.session_state.keyword_list = hist_kws

if "location_list" not in st.session_state:
    st.session_state.location_list = hist_locs

if "live_incoming_items" not in st.session_state:
    st.session_state.live_incoming_items = []

# Sidebar Controls
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
    st.subheader("🔄 Automated Poller")
    auto_monitor = st.checkbox("Enable Auto-Scan Loop", value=False)
    interval_mins = st.slider("Frequency (Minutes)", min_value=1, max_value=60, value=5)

st.title("Quick Commerce Shelf Monitor & Bidding Desk")
st.caption("Real-time shelf intelligence, algorithmic bidding desk & cannibalization defense for Anand Sweets & Chak Now.")

st_autorefresh(interval=30 * 1000, key="auto_refresher")

# Search Inputs
st.subheader("🎯 Monitoring Scope: Target Keywords & Locations")
col_sel1, col_sel2 = st.columns(2)

with col_sel1:
    selected_keywords = st.multiselect(
        "Active Search Keywords:",
        options=st.session_state.keyword_list,
        default=[st.session_state.keyword_list[0]] if st.session_state.keyword_list else ["mysore pak"]
    )
    with st.expander("➕ Add Custom Keyword"):
        new_kw = st.text_input("Enter new keyword (e.g. motichoor laddu, milk cake):").strip().lower()
        if st.button("Add Keyword") and new_kw:
            if new_kw not in st.session_state.keyword_list:
                st.session_state.keyword_list.append(new_kw)
                st.rerun()

with col_sel2:
    selected_locations = st.multiselect(
        "Active Locations / Pincodes:",
        options=st.session_state.location_list,
        default=[st.session_state.location_list[0]] if st.session_state.location_list else ["560091"]
    )
    with st.expander("➕ Add Custom Location or Pincode"):
        new_loc = st.text_input("Enter Locality Name or Pincode (e.g. Ullal, Vijay Nagar, 560040):").strip()
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

# Client-Side Execution Engine
query_params = st.query_params
if "client_payload" in query_params:
    try:
        raw_p = urllib.parse.unquote(query_params["client_payload"])
        parsed_items = json.loads(raw_p)
        if parsed_items:
            for item in parsed_items:
                item["Brand"] = extract_brand(item.get("Product Name", ""))
                item["Rank Shift"] = "New"
            
            history = load_history()
            now_str = datetime.now().strftime("%I:%M %p, %d %b")
            store_tag = str(parsed_items[0].get("Platform", "Blinkit")).lower()
            kw_tag = str(parsed_items[0].get("Search Term", "")).lower().strip()
            loc_tag = str(parsed_items[0].get("Location", "")).lower().strip()
            
            history[f"{store_tag}_{kw_tag}_{loc_tag}"] = {
                "timestamp": now_str,
                "items": parsed_items
            }
            save_history(history)
            st.session_state.live_incoming_items = parsed_items
            del st.query_params["client_payload"]
            st.rerun()
    except Exception as e:
        print(f"Error parsing client payload: {e}")

if fetch_btn:
    chosen_kw = selected_keywords[0] if selected_keywords else "mysore pak"
    chosen_loc = selected_locations[0] if selected_locations else "560091"
    lat, lon, label = resolve_location_coordinates(chosen_loc)

    js_trigger = f"""
    <script>
    (async function() {{
        const kw = "{chosen_kw}";
        const lat = "{lat}";
        const lon = "{lon}";
        const locStr = "{chosen_loc}";
        let extracted = [];

        try {{
            const url = "https://blinkit.com/v1/layout/search?q=" + encodeURIComponent(kw);
            const res = await fetch(url, {{
                headers: {{ "lat": lat, "lon": lon, "app_client": "consumer_web" }}
            }});
            if (res.ok) {{
                const data = await res.json();
                const widgets = (data.layout && data.layout.widgets) || [];
                let overall = 1, ad_r = 1, org_r = 1;
                for (const w of widgets) {{
                    const prods = (w.data && w.data.products) || [];
                    for (const p of prods) {{
                        const is_ad = Boolean(p.is_sponsored || p.ad_id);
                        extracted.push({{
                            "Platform": "Blinkit",
                            "Overall Shelf Pos": overall,
                            "Type": is_ad ? "Sponsored Ad" : "Organic",
                            "Placement Rank": is_ad ? ("Ad #" + ad_r++) : ("Org #" + org_r++),
                            "Product Name": p.name || "",
                            "Price": "₹" + (p.price || 0),
                            "Pack Size": p.unit || "Standard",
                            "Search Term": kw,
                            "Location": locStr,
                            "Location Name": "{label}"
                        }});
                        overall++;
                    }}
                }}
            }}
        }} catch(e) {{
            console.log("Client fetch error:", e);
        }}

        if (extracted.length > 0) {{
            const payload = encodeURIComponent(JSON.stringify(extracted));
            const currentUrl = new URL(window.parent.location.href);
            currentUrl.searchParams.set("client_payload", payload);
            window.parent.location.href = currentUrl.toString();
        }}
    }})();
    </script>
    """
    components.html(js_trigger, height=0)

# Unified Multi-Store Dataset Retrieval
history = load_history()
active_items = []
target_stores = [chosen_store.capitalize()] if store_scope == "Selected Storefront Only" else (active_platforms if active_platforms else ["Blinkit", "Zepto", "Instamart"])

for kw in selected_keywords:
    for loc in selected_locations:
        clean_kw = str(kw).lower().strip()
        clean_loc = str(loc).lower().strip()
        
        # Expand location aliases
        possible_loc_keys = [clean_loc]
        for pin_k, aliases in LOCATION_ALIASES.items():
            if clean_loc in aliases or clean_loc == pin_k:
                possible_loc_keys.extend(aliases)
                possible_loc_keys.append(pin_k)
        possible_loc_keys = list(set(possible_loc_keys))

        for st_name in target_stores:
            for cand_loc in possible_loc_keys:
                cache_key = f"{st_name.lower()}_{clean_kw}_{cand_loc}"
                if cache_key in history:
                    entry = history[cache_key]
                    _, _, loc_label = resolve_location_coordinates(cand_loc)
                    for item in entry.get("items", []):
                        copy_i = dict(item)
                        copy_i["Platform"] = st_name.capitalize()
                        copy_i["Search Term"] = clean_kw
                        copy_i["Location"] = loc
                        copy_i["Location Name"] = loc_label
                        copy_i["Rank Shift"] = "-"
                        active_items.append(copy_i)
                    break

# Auto-Platform Fallback: If filtered storefronts returned 0, retrieve from any available platform
if not active_items and selected_keywords and selected_locations:
    for kw in selected_keywords:
        for loc in selected_locations:
            clean_kw = str(kw).lower().strip()
            clean_loc = str(loc).lower().strip()
            
            possible_loc_keys = [clean_loc]
            for pin_k, aliases in LOCATION_ALIASES.items():
                if clean_loc in aliases or clean_loc == pin_k:
                    possible_loc_keys.extend(aliases)
                    possible_loc_keys.append(pin_k)
            possible_loc_keys = list(set(possible_loc_keys))

            for st_name in ["Zepto", "Blinkit", "Instamart"]:
                for cand_loc in possible_loc_keys:
                    cache_key = f"{st_name.lower()}_{clean_kw}_{cand_loc}"
                    if cache_key in history:
                        entry = history[cache_key]
                        _, _, loc_label = resolve_location_coordinates(cand_loc)
                        for item in entry.get("items", []):
                            copy_i = dict(item)
                            copy_i["Platform"] = st_name.capitalize()
                            copy_i["Search Term"] = clean_kw
                            copy_i["Location"] = loc
                            copy_i["Location Name"] = loc_label
                            copy_i["Rank Shift"] = "-"
                            active_items.append(copy_i)
                        break

# De-duplicate identical SKUs
seen_keys = set()
deduped_items = []
for it in active_items:
    ukey = f"{it.get('Platform')}_{it.get('Product Name')}_{it.get('Overall Shelf Pos')}"
    if ukey not in seen_keys:
        seen_keys.add(ukey)
        deduped_items.append(it)

# Alert Log Calculation
def generate_live_alerts(current_items, active_channels, scope_filter):
    if not current_items:
        return ["ℹ️ No records found matching the active filters."]

    alerts = []
    for card in current_items:
        c_pos = int(card.get("Overall Shelf Pos", 0))
        brand_name = card.get("Brand", "")
        p_name = card.get("Product Name", "")
        p_type = card.get("Type", "")
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
        if is_mine:
            alerts.append(f"🟢 **Tracked Listing**: {brand_name} '**{p_name}**' {type_tag} at **Pos #{c_pos}** on **{card.get('Platform')}** ({card.get('Search Term')} @ {card.get('Location')}).")
        else:
            alerts.append(f"⚠️ **Competitor Top Ad**: {brand_name} '**{p_name}**' {type_tag} secured **Pos #{c_pos}** on **{card.get('Platform')}**.")

    return alerts

active_alerts = generate_live_alerts(deduped_items, active_platforms, alert_scope)

with st.expander("🚨 Recent Incident & Alert Log", expanded=True):
    if active_alerts:
        for a in active_alerts[:15]:
            st.markdown(f"- {a}")
    else:
        st.write("No matching alert events for current selection.")

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
        if deduped_items:
            current_df = pd.DataFrame(deduped_items)
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

# Strategic Bidding Desk Matrix Engine
def compute_professional_bidding_matrix(items, enabled_platforms):
    if not items:
        return []

    matrix = []
    df_raw = pd.DataFrame(items)
    grouped = df_raw.groupby(["Platform", "Search Term", "Location"])
    normalized_enabled = [p.capitalize() for p in enabled_platforms] if enabled_platforms else ["Blinkit", "Zepto", "Instamart"]

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

if deduped_items:
    df = pd.DataFrame(deduped_items)
    kw_str = ", ".join([k.title() for k in selected_keywords])
    loc_str = ", ".join([l.title() for l in selected_locations])
    st.success(f"Displaying {len(df)} storefront listings for **{kw_str}** at **{loc_str}**.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Tracked Items", len(df))
    ad_count = len(df[df["Type"] == "Sponsored Ad"])
    m2.metric("Overall Ad Load (SOV)", f"{(ad_count / len(df) * 100):.1f}%" if len(df) > 0 else "0%")
    m3.metric("Target Brands Detected", len(df[df["Brand"].apply(is_my_brand)]))
    m4.metric("Storefronts In View", ", ".join(df["Platform"].unique()))

    st.divider()

    st.subheader("💡 Professional Quick Commerce Bidding Desk")
    bidding_matrix = compute_professional_bidding_matrix(deduped_items, suggest_platforms)

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
        st.info("No target brand items requiring bidding intervention on the active platforms.")

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
            st.info("No sponsored ads present in current selection.")

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

    cols_order = ["Product Name", "Brand", "Overall Shelf Pos", "Type", "Price", "Platform", "Search Term", "Location", "Location Name", "Rank Shift"]
    existing_cols = [c for c in cols_order if c in df.columns]

    st.dataframe(df[existing_cols].style.apply(style_full, axis=1), height=550, **WIDTH_KWARG)
else:
    st.warning("No listings found matching your selected Keyword and Location. Enter a keyword/location above and click '🚀 Fetch Shelf Now'.")
