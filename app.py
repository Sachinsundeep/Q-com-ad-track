import streamlit as st
import pandas as pd
import subprocess
import json
import io
import re
import os
import sys
import time
from datetime import datetime
import altair as alt
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Quick Commerce Live Shelf Monitor & Bidding Desk",
    page_icon="⚡",
    layout="wide"
)

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

PINCODE_MAP = {
    "560021": {"name": "Jalahalli", "lat": "13.0470976", "lon": "77.5476596"},
    "560037": {"name": "Marathahalli", "lat": "12.959172", "lon": "77.697419"},
    "560103": {"name": "Bellandur", "lat": "12.926031", "lon": "77.676246"},
    "560038": {"name": "Indiranagar", "lat": "12.978369", "lon": "77.640835"},
    "560034": {"name": "Koramangala", "lat": "12.935242", "lon": "77.624480"},
    "560001": {"name": "MG Road", "lat": "12.971598", "lon": "77.594563"},
    "560076": {"name": "BTM Layout", "lat": "12.916575", "lon": "77.610116"},
    "560068": {"name": "Electronic City", "lat": "12.899446", "lon": "77.625475"},
    "560066": {"name": "Whitefield", "lat": "12.969819", "lon": "77.749972"},
    "560004": {"name": "Basavanagudi", "lat": "12.943187", "lon": "77.573787"},
    "560056": {"name": "Bangalore West", "lat": "12.971598", "lon": "77.594563"},
    "560091": {"name": "Viswaneedam", "lat": "12.990000", "lon": "77.510000"},
    "560096": {"name": "Rajajinagar", "lat": "13.000000", "lon": "77.550000"}
}

def resolve_location(pincode: str):
    clean = str(pincode).strip()
    if clean in PINCODE_MAP:
        loc = PINCODE_MAP[clean]
        return loc["lat"], loc["lon"], f"{loc['name']} ({clean})"
    return "13.0470976", "77.5476596", f"Pincode {clean}"

EXCLUDED_BRANDS = ["anandhaas", "shree anandhaas", "anandhas", "ananda dairy", "ananda"]

def is_my_brand(brand_name: str) -> bool:
    b = str(brand_name).strip().lower()
    for exc in EXCLUDED_BRANDS:
        if exc in b:
            return False
    is_anand = bool(re.search(r"\banand(\s+sweets)?\b", b))
    is_chaknow = bool(re.search(r"\bchak(\s*now)?\b", b))
    return is_anand or is_chaknow

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

# Session state setup
if "live_shelf_items" not in st.session_state:
    st.session_state.live_shelf_items = []

if "last_queried_target" not in st.session_state:
    st.session_state.last_queried_target = ""

if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = time.time()

# Sidebar
with st.sidebar:
    st.header("⚡ Scraping Mode")
    source_mode = st.radio(
        "Data Source Selection:",
        ["⚡ Live Real-Time Scan (Direct Storefront)", "📁 Saved History / Cache"],
        index=0
    )

    st.divider()
    st.header("🔔 Alert Channels")
    alert_blinkit = st.checkbox("Blinkit Alerts", value=True)
    alert_zepto = st.checkbox("Zepto Alerts", value=True)
    alert_instamart = st.checkbox("Instamart Alerts", value=True)
    
    active_platforms = []
    if alert_blinkit: active_platforms.append("Blinkit")
    if alert_zepto: active_platforms.append("Zepto")
    if alert_instamart: active_platforms.append("Instamart")

    st.divider()
    st.header("💡 Bidding Engine Filter")
    suggest_blinkit = st.checkbox("Blinkit Ads", value=True)
    suggest_zepto = st.checkbox("Zepto Brand Engine", value=True)
    suggest_instamart = st.checkbox("Swiggy Ads", value=True)

    suggest_platforms = []
    if suggest_blinkit: suggest_platforms.append("Blinkit")
    if suggest_zepto: suggest_platforms.append("Zepto")
    if suggest_instamart: suggest_platforms.append("Instamart")

    st.divider()
    st.subheader("🔄 Automated Background Poller")
    auto_monitor = st.checkbox("Enable Auto-Scan Loop", value=False)
    interval_mins = st.slider("Frequency (Minutes)", min_value=1, max_value=60, value=5)

st.title("Quick Commerce Real-Time Shelf Monitor & Bidding Desk")
st.caption("Live storefront extraction & automated algorithmic bidding recommendations for Anand Sweets and Chak Now.")

st_autorefresh(interval=30 * 1000, key="auto_scan_ticker")

# User Input Controls
st.subheader("🔍 Live Search & Location Entry")
c_kw, c_pin = st.columns([2, 1])

with c_kw:
    typed_keyword = st.text_input(
        "Enter Search Keyword:",
        value="besan laddu",
        placeholder="Type any product (e.g. kaju katli, mysore pak, motichoor laddu, milk cake)..."
    ).strip().lower()

with c_pin:
    typed_pincode = st.text_input(
        "Enter 6-Digit Pincode:",
        value="560021",
        placeholder="e.g. 560021, 560103, 560034, 560037..."
    ).strip()

c_plat, c_act = st.columns([2, 1])
with c_plat:
    chosen_platform = st.selectbox("Storefront Target", ["Blinkit", "Zepto", "Instamart", "All Storefronts"])
with c_act:
    st.write("")
    st.write("")
    trigger_live_fetch = st.button("🚀 Fetch Live Shelf Now", type="primary", **WIDTH_KWARG)

def execute_single_scan(store_name, kw, pin):
    lat, lon, label = resolve_location(pin)
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_blinkit.py")
    cmd = [sys.executable, script_path, str(store_name).lower(), str(kw), str(lat), str(lon)]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        json_match = re.search(r"__JSON_START__(.*?)__JSON_END__", proc.stdout, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
            return data, label, None
        else:
            return [], label, f"Scraper returned no data. Ensure Chrome is running on Port 9222.\nOutput: {proc.stdout[:250]}"
    except Exception as e:
        return [], label, f"Execution Error: {str(e)}"

# Trigger Scan Conditions
current_time = time.time()
elapsed_time = current_time - st.session_state.last_scan_time
required_interval = interval_mins * 60

is_auto_due = auto_monitor and (elapsed_time > required_interval)
should_scan = trigger_live_fetch or is_auto_due

if should_scan and source_mode.startswith("⚡"):
    if is_auto_due:
        st.session_state.last_scan_time = current_time

    if not typed_keyword:
        st.warning("⚠️ Please enter a search keyword.")
    elif len(typed_pincode) < 6:
        st.warning("⚠️ Please enter a valid 6-digit pincode.")
    else:
        target_stores = ["Blinkit", "Zepto", "Instamart"] if chosen_platform == "All Storefronts" else [chosen_platform]
        history = load_history()
        current_time_str = datetime.now().strftime("%I:%M %p, %d %b")
        live_results = []
        errors = []

        with st.spinner(f"Connecting to live Chrome CDP session to scan '{typed_keyword}' at {typed_pincode}..."):
            for st_name in target_stores:
                scanned_cards, loc_label, err = execute_single_scan(st_name, typed_keyword, typed_pincode)
                if err:
                    errors.append(f"**[{st_name}]**: {err}")
                if not scanned_cards:
                    continue

                cache_key = f"{st_name.lower()}_{typed_keyword.lower().strip()}_{typed_pincode.strip()}"
                prev_scan = history.get(cache_key, None)
                prev_lookup = {}
                if prev_scan:
                    for p in prev_scan.get("items", []):
                        p_clean = str(p.get("Product Name", "")).strip().lower()
                        p_type = str(p.get("Type", "")).strip().lower()
                        prev_lookup[f"{p_clean}::{p_type}"] = p.get("Overall Shelf Pos")

                for card in scanned_cards:
                    card["Platform"] = st_name.capitalize()
                    card["Search Term"] = typed_keyword
                    card["Pincode"] = typed_pincode
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

                    live_results.append(card)

                # Update cache
                history[cache_key] = {
                    "timestamp": current_time_str,
                    "items": [{
                        "Product Name": c["Product Name"],
                        "Brand": c["Brand"],
                        "Overall Shelf Pos": c["Overall Shelf Pos"],
                        "Type": c["Type"],
                        "Price": c["Price"]
                    } for c in scanned_cards]
                }

        if live_results:
            save_history(history)
            st.session_state.live_shelf_items = live_results
            st.session_state.last_queried_target = f"{typed_keyword.title()} @ {typed_pincode} ({chosen_platform})"
            st.rerun()
        else:
            st.error("No items returned from the live scraper. Check if Chrome Debugging is running on port 9222.")
            if errors:
                for er in errors:
                    st.markdown(er)

# Resolve Display Dataset
if source_mode.startswith("⚡"):
    display_data = st.session_state.live_shelf_items
    data_label = f"Live Extracted Placements: {st.session_state.last_queried_target}" if st.session_state.last_queried_target else "No live query triggered yet. Click 'Fetch Live Shelf Now' above."
else:
    history = load_history()
    cache_key = f"{chosen_platform.lower()}_{typed_keyword.lower().strip()}_{typed_pincode.strip()}"
    cached_entry = history.get(cache_key, None)
    if cached_entry:
        items = cached_entry.get("items", [])
        for it in items:
            it["Platform"] = chosen_platform.capitalize()
            it["Search Term"] = typed_keyword
            it["Pincode"] = typed_pincode
            it["Location Name"] = resolve_location(typed_pincode)[2]
            it["Rank Shift"] = "-"
            it["Placement Rank"] = f"Pos #{it.get('Overall Shelf Pos', '-')}"
        display_data = items
        data_label = f"Displaying Cache for '{typed_keyword}' @ {typed_pincode} ({cached_entry.get('timestamp', 'Prior')})"
    else:
        display_data = []
        data_label = f"No historical scan found for '{typed_keyword}' at pincode '{typed_pincode}' on {chosen_platform}."

# UI Render
st.divider()

if display_data:
    df = pd.DataFrame(display_data)
    st.success(f"{data_label} — Found {len(df)} listings.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tracked Placements", len(df))
    ad_count = len(df[df["Type"] == "Sponsored Ad"])
    m2.metric("Ad Load (SOV)", f"{(ad_count / len(df) * 100):.1f}%" if len(df) > 0 else "0%")
    m3.metric("Target Brands (Anand / Chak Now)", len(df[df["Brand"].apply(is_my_brand)]))
    m4.metric("Storefront Target", df["Platform"].iloc[0] if not df.empty else "N/A")

    st.divider()

    # Bidding Desk
    st.subheader("💡 Actionable Bidding Plan (Live Storefront Feed)")
    
    def compute_live_bidding_matrix(records, platforms):
        matrix = []
        raw = pd.DataFrame(records)
        grouped = raw.groupby(["Platform", "Search Term", "Pincode"])
        norm_plats = [p.capitalize() for p in platforms]

        for (plat, kw, pin), group in grouped:
            if str(plat).capitalize() not in norm_plats:
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
                rationale = "Listing maintains acceptable positioning."

                if is_ad and top_org_pos <= 3:
                    action_badge = "🛑 PAUSE / REDUCE CPC"
                    priority = "CRITICAL"
                    target_placement = f"Organic Top-3 Locked (Pos #{top_org_pos})"
                    cpc_shift = "-30% to -40% CPC Reduction"
                    budget_advice = "Reallocate 50% Budget to Deficit Dark Stores"
                    rationale = f"Organic listing '{top_org_item['Product Name']}' is secured at Pos #{top_org_pos}. Paying for an ad cannibalizes free organic conversions."

                elif is_ad and pos > 4:
                    action_badge = "🚀 BOOST BID (SURGE TO ROW 1)"
                    priority = "CRITICAL"
                    target_placement = "Top-of-Fold Row 1 (Pos 1–4)"
                    cpc_shift = "+20% to +30% Bid Surge"
                    budget_advice = "Increase Daily Budget Cap (+20%)"
                    rationale = f"Ad cleared at Pos #{pos} (Row 2+). Click-through rate decays significantly below Row 1."

                elif comp_slot1 is not None and (pos > int(comp_slot1["Overall Shelf Pos"])):
                    action_badge = "🛡️ DEFENSIVE COUNTER-BID"
                    priority = "HIGH"
                    target_placement = "Capture Ad Slot #1 (Pos 1–2)"
                    cpc_shift = "+15% to +20% Surge"
                    budget_advice = "Increase Daily Budget Cap (+15%)"
                    rationale = f"Competitor '{comp_slot1['Brand']}' took Ad Slot #{comp_slot1['Overall Shelf Pos']}. Outbid to protect customer demand."

                elif not is_ad and pos >= 4:
                    action_badge = "📢 ACTIVATE SPONSORED BID"
                    priority = "HIGH"
                    target_placement = "Sponsored Slot #1 or #2"
                    cpc_shift = "Set Category Benchmark CPC"
                    budget_advice = "Open Dedicated Campaign Line"
                    rationale = f"Organic visibility is drifting at Pos #{pos}. Activating a sponsored ad pushes this SKU back to the first row."

                elif is_ad and pos <= 3:
                    action_badge = "🟢 LOCK TOP POSITION"
                    priority = "MEDIUM"
                    target_placement = f"Hold Slot #{pos}"
                    cpc_shift = "Test -5% Decrement"
                    budget_advice = "Sustain Current Cap"
                    rationale = "Holding premium ad placement. Incrementally shave CPC by 5% to discover lowest winning clearing bid."

                matrix.append({
                    "Urgency": priority,
                    "Platform": plat,
                    "Keyword": kw,
                    "Pincode": pin,
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

    bidding_matrix = compute_live_bidding_matrix(display_data, suggest_platforms)

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
                b_df.to_excel(writer, index=False, sheet_name='LiveBiddingPlan')
            st.download_button(
                "📥 Export Live Bidding Action Sheet (.xlsx)",
                data=bid_buf.getvalue(),
                file_name="qcom_live_bidding_plan.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                **WIDTH_KWARG
            )

        st.dataframe(b_df.style.apply(style_bidding_table, axis=1), height=280, **WIDTH_KWARG)
    else:
        st.info("No target brand items requiring bidding intervention in this live storefront scan.")

    st.divider()

    # Master Table
    st.subheader("📋 Real-Time Storefront Shelf Inventory")

    def style_full(row):
        is_mine = is_my_brand(row.get("Brand", ""))
        is_ad = row.get("Type", "") == "Sponsored Ad"
        if is_mine and is_ad:
            return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row)
        elif is_mine:
            return ['background-color: #dcfce7; color: #166534; font-weight: bold;'] * len(row)
        elif is_ad:
            return ['background-color: #fef08a; color: #854d0e; font-weight: bold;'] * len(row)
        return [''] * len(row)

    cols_order = ["Product Name", "Brand", "Overall Shelf Pos", "Placement Rank", "Type", "Price", "Platform", "Search Term", "Pincode", "Location Name", "Rank Shift"]
    existing_cols = [c for c in cols_order if c in df.columns]

    st.dataframe(df[existing_cols].style.apply(style_full, axis=1), height=500, **WIDTH_KWARG)

else:
    st.info(f"{data_label}")
