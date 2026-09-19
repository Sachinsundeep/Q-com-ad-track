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

# Core Known Bangalore Hotspots (Instant Fallback Cache)
KNOWN_LOCALITIES = {
    "560021": ("13.0470976", "77.5476596", "Jalahalli (560021)"),
    "jalahalli": ("13.0470976", "77.5476596", "Jalahalli"),
    "560037": ("12.959172", "77.697419", "Marathahalli (560037)"),
    "marathahalli": ("12.959172", "77.697419", "Marathahalli"),
    "560103": ("12.926031", "77.676246", "Bellandur (560103)"),
    "bellandur": ("12.926031", "77.676246", "Bellandur"),
    "560038": ("12.978369", "77.640835", "Indiranagar (560038)"),
    "indiranagar": ("12.978369", "77.640835", "Indiranagar"),
    "560034": ("12.935242", "77.624480", "Koramangala (560034)"),
    "koramangala": ("12.935242", "77.624480", "Koramangala"),
    "560001": ("12.971598", "77.594563", "MG Road (560001)"),
    "mg road": ("12.971598", "77.594563", "MG Road"),
    "560076": ("12.916575", "77.610116", "BTM Layout (560076)"),
    "btm": ("12.916575", "77.610116", "BTM Layout"),
    "btm layout": ("12.916575", "77.610116", "BTM Layout"),
    "560068": ("12.899446", "77.625475", "Electronic City (560068)"),
    "electronic city": ("12.899446", "77.625475", "Electronic City"),
    "560066": ("12.969819", "77.749972", "Whitefield (560066)"),
    "whitefield": ("12.969819", "77.749972", "Whitefield"),
    "560004": ("12.943187", "77.573787", "Basavanagudi (560004)"),
    "basavanagudi": ("12.943187", "77.573787", "Basavanagudi"),
    "560040": ("12.971900", "77.530500", "Vijayanagar (560040)"),
    "vijayanagar": ("12.971900", "77.530500", "Vijayanagar"),
    "vijay nagar": ("12.971900", "77.530500", "Vijayanagar"),
    "560056": ("12.955600", "77.498000", "Ullal (560056)"),
    "ullal": ("12.955600", "77.498000", "Ullal"),
    "bommanahalli": ("12.902900", "77.624200", "Bommanahalli"),
    "560091": ("12.990000", "77.510000", "Viswaneedam (560091)"),
    "rajajinagar": ("13.000000", "77.550000", "Rajajinagar")
}

@st.cache_data(show_spinner=False, ttl=86400)
def resolve_any_location(query_text: str):
    clean = str(query_text).strip().lower()
    if clean in KNOWN_LOCALITIES:
        return KNOWN_LOCALITIES[clean]

    # Dynamic OpenStreetMap geocode for arbitrary localities or pincodes
    try:
        geolocator = Nominatim(user_agent="qcom_shelf_monitor_prod", timeout=5)
        # Search with Bangalore suffix for locality names unless full address is provided
        search_target = f"{clean}, Bangalore, India" if not clean.isdigit() else f"{clean}, India"
        loc = geolocator.geocode(search_target)
        if loc:
            return str(loc.latitude), str(loc.longitude), f"{query_text.title()}"
    except Exception:
        pass

    # Default Bangalore Central Coordinates Fallback
    return "12.971598", "77.594563", f"{query_text.title()} (Bangalore)"

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

# Session State Setup
if "keyword_list" not in st.session_state:
    st.session_state.keyword_list = ["mysore pak", "kaju katli", "besan laddu"]

if "location_list" not in st.session_state:
    st.session_state.location_list = ["560091", "Ullal", "Koramangala", "Vijay Nagar", "560021", "Bellandur"]

if "active_scan_results" not in st.session_state:
    st.session_state.active_scan_results = []

if "last_queried_string" not in st.session_state:
    st.session_state.last_queried_string = ""

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
    st.subheader("🔄 Live Polling")
    auto_monitor = st.checkbox("Enable Auto-Scan Loop", value=False)
    interval_mins = st.slider("Frequency (Minutes)", min_value=1, max_value=60, value=5)

st.title("Quick Commerce Shelf Monitor & Bidding Desk")
st.caption("Universal dynamic live search, algorithmic bidding desk & cannibalization defense.")

st_autorefresh(interval=30 * 1000, key="auto_refresh_tick")

# Input Search Fields
st.subheader("🎯 Monitoring Scope: Target Keywords & Locations")
col_sel1, col_sel2 = st.columns(2)

with col_sel1:
    selected_keywords = st.multiselect(
        "Active Search Keywords:",
        options=st.session_state.keyword_list,
        default=[st.session_state.keyword_list[0]] if st.session_state.keyword_list else []
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
        default=[st.session_state.location_list[0]] if st.session_state.location_list else []
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

# Handle Client-Side Scraped Data Payload from Browser
query_params = st.query_params
if "live_scraped_json" in query_params:
    try:
        raw_json_str = urllib.parse.unquote(query_params["live_scraped_json"])
        incoming_items = json.loads(raw_json_str)
        if incoming_items:
            for it in incoming_items:
                it["Brand"] = extract_brand(it.get("Product Name", ""))
                it["Rank Shift"] = "New"
            
            # Save into JSON master history
            history = load_history()
            now_str = datetime.now().strftime("%I:%M %p, %d %b")
            store_tag = incoming_items[0].get("Platform", "Blinkit").lower()
            kw_tag = str(incoming_items[0].get("Search Term", "")).lower().strip()
            loc_tag = str(incoming_items[0].get("Location", "")).lower().strip()
            
            history[f"{store_tag}_{kw_tag}_{loc_tag}"] = {
                "timestamp": now_str,
                "items": incoming_items
            }
            save_history(history)
            
            st.session_state.active_scan_results = incoming_items
            st.session_state.last_queried_string = f"{kw_tag.title()} @ {loc_tag.title()}"
            del st.query_params["live_scraped_json"]
            st.rerun()
    except Exception as e:
        print(f"Error parsing incoming client payload: {e}")

# Triggering Search
if fetch_btn:
    chosen_kw = selected_keywords[0] if selected_keywords else "mysore pak"
    chosen_loc = selected_locations[0] if selected_locations else "560091"
    lat, lon, resolved_label = resolve_any_location(chosen_loc)
    target_stores_to_call = [chosen_store] if store_scope == "Selected Storefront Only" else active_platforms

    # Inject client-side execution block to query via user's connection
    client_exec_html = f"""
    <script>
    (async function() {{
        const kw = "{chosen_kw}";
        const lat = "{lat}";
        const lon = "{lon}";
        const locLabel = "{chosen_loc}";
        let collected = [];

        try {{
            // Query Blinkit via user's browser network
            const blinkitUrl = "https://blinkit.com/v1/layout/search?q=" + encodeURIComponent(kw);
            const res = await fetch(blinkitUrl, {{
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
                        collected.push({{
                            "Platform": "Blinkit",
                            "Overall Shelf Pos": overall,
                            "Type": is_ad ? "Sponsored Ad" : "Organic",
                            "Placement Rank": is_ad ? ("Ad #" + ad_r++) : ("Org #" + org_r++),
                            "Product Name": p.name || "",
                            "Price": "₹" + (p.price || 0),
                            "Pack Size": p.unit || "Standard",
                            "Search Term": kw,
                            "Location": locLabel,
                            "Location Name": "{resolved_label}"
                        }});
                        overall++;
                    }}
                }}
            }}
        }} catch(err) {{
            console.log("Client fetch error: ", err);
        }}

        if (collected.length > 0) {{
            const payload = encodeURIComponent(JSON.stringify(collected));
            const targetUrl = new URL(window.parent.location.href);
            targetUrl.searchParams.set("live_scraped_json", payload);
            window.parent.location.href = targetUrl.toString();
        }}
    }})();
    </script>
    """
    components.html(client_exec_html, height=0)

    # Check local fallback records if client bridge is blocked
    history = load_history()
    matched_fallback = []
    for st_name in target_stores_to_call:
        ckey = f"{st_name.lower()}_{str(chosen_kw).lower().strip()}_{str(chosen_loc).lower().strip()}"
        if ckey in history:
            for item in history[ckey].get("items", []):
                copy_item = dict(item)
                copy_item["Platform"] = st_name.capitalize()
                copy_item["Search Term"] = chosen_kw
                copy_item["Location"] = chosen_loc
                copy_item["Location Name"] = resolved_label
                copy_item["Rank Shift"] = "-"
                matched_fallback.append(copy_item)

    if matched_fallback:
        st.session_state.active_scan_results = matched_fallback
        st.session_state.last_queried_string = f"{chosen_kw.title()} @ {chosen_loc.title()}"
        st.rerun()

# Ensure Active Filter Matching: Only load items that match the active inputs
current_items_in_view = []
if st.session_state.active_scan_results:
    for item in st.session_state.active_scan_results:
        item_kw = str(item.get("Search Term", "")).lower().strip()
        item_loc = str(item.get("Location", "")).lower().strip()
        kw_match = any(item_kw == str(k).lower().strip() for k in selected_keywords)
        loc_match = any(item_loc == str(l).lower().strip() for l in selected_locations)
        if kw_match and loc_match:
            current_items_in_view.append(item)

# If empty, perform direct lookup from history matching the selected scopes
if not current_items_in_view:
    history = load_history()
    target_stores_to_call = [chosen_store] if store_scope == "Selected Storefront Only" else active_platforms
    for st_name in target_stores_to_call:
        for kw in selected_keywords:
            for loc in selected_locations:
                ckey = f"{st_name.lower()}_{str(kw).lower().strip()}_{str(loc).lower().strip()}"
                if ckey in history:
                    _, _, r_label = resolve_any_location(loc)
                    for c in history[ckey].get("items", []):
                        ci = dict(c)
                        ci["Platform"] = st_name.capitalize()
                        ci["Search Term"] = kw
                        ci["Location"] = loc
                        ci["Location Name"] = r_label
                        ci["Rank Shift"] = "-"
                        current_items_in_view.append(ci)

# Incident Alerts Processing
def generate_live_alerts(current_items, active_channels, scope_filter):
    if not active_channels:
        return ["ℹ️ All platform alerts are currently toggled off in the sidebar."]

    alerts = []
    for card in current_items:
        platform = card.get("Platform", "").capitalize()
        if platform not in [c.capitalize() for c in active_channels]:
            continue

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
            alerts.append(f"🟢 **Tracked Listing**: {brand_name} '**{p_name}**' {type_tag} at **Pos #{c_pos}** on **{platform}** ({card.get('Search Term')} @ {card.get('Location')}).")
        else:
            alerts.append(f"⚠️ **Competitor Top Ad**: {brand_name} '**{p_name}**' {type_tag} secured **Pos #{c_pos}** on **{platform}**.")

    return alerts

active_alerts = generate_live_alerts(current_items_in_view, active_platforms, alert_scope)

with st.expander("🚨 Recent Incident & Alert Log", expanded=True):
    if active_alerts:
        for a in active_alerts[:15]:
            st.markdown(f"- {a}")
    else:
        st.write("No matching incidents for current scope selection.")

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
        if current_items_in_view:
            current_df = pd.DataFrame(current_items_in_view)
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

# Strategic Bidding Engine
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

# UI Render Layer
if current_items_in_view:
    df = pd.DataFrame(current_items_in_view)
    kw_str = ", ".join([k.title() for k in selected_keywords])
    loc_str = ", ".join([l.title() for l in selected_locations])
    st.success(f"Displaying {len(df)} matching storefront listings for **{kw_str}** at **{loc_str}**.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Tracked Items", len(df))
    ad_count = len(df[df["Type"] == "Sponsored Ad"])
    m2.metric("Overall Ad Load (SOV)", f"{(ad_count / len(df) * 100):.1f}%" if len(df) > 0 else "0%")
    m3.metric("Target Brands Detected", len(df[df["Brand"].apply(is_my_brand)]))
    m4.metric("Locations In View", len(df["Location"].unique()))

    st.divider()

    st.subheader("💡 Professional Quick Commerce Bidding Desk")
    bidding_matrix = compute_professional_bidding_matrix(current_items_in_view, suggest_platforms)

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
        st.info("No target brand items requiring bidding intervention for the selected scope.")

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

    cols_order = ["Product Name", "Brand", "Overall Shelf Pos", "Type", "Price", "Platform", "Search Term", "Location", "Rank Shift"]
    existing_cols = [c for c in cols_order if c in df.columns]

    st.dataframe(df[existing_cols].style.apply(style_full, axis=1), height=550, **WIDTH_KWARG)
else:
    st.warning("No listings found matching your selected Keyword and Location. Click '🚀 Fetch Shelf Now' to retrieve data.")
