import streamlit as st
import pandas as pd
import json
import io
import os
import time
from datetime import datetime
import altair as alt
from streamlit_autorefresh import st_autorefresh

from scraper_engine import (
    fetch_blinkit_live,
    fetch_zepto_live,
    fetch_instamart_live,
    is_my_brand
)

st.set_page_config(
    page_title="Quick Commerce Real-Time Shelf Monitor",
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
    "560004": {"name": "Basavanagudi", "lat": "12.943187", "lon": "77.573787"}
}

def resolve_location(pincode: str):
    clean = str(pincode).strip()
    if clean in PINCODE_MAP:
        loc = PINCODE_MAP[clean]
        return loc["lat"], loc["lon"], f"{loc['name']} ({clean})"
    return "13.0470976", "77.5476596", f"Pincode {clean}"

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

if "current_view_items" not in st.session_state:
    st.session_state.current_view_items = []
if "last_query_label" not in st.session_state:
    st.session_state.last_query_label = ""
if "last_scan_time" not in st.session_state:
    st.session_state.last_scan_time = time.time()

# Sidebar
with st.sidebar:
    st.header("⚡ Storefront Selection")
    active_blinkit = st.checkbox("Blinkit", value=True)
    active_zepto = st.checkbox("Zepto", value=True)
    active_instamart = st.checkbox("Swiggy Instamart", value=True)

    enabled_platforms = []
    if active_blinkit: enabled_platforms.append("Blinkit")
    if active_zepto: enabled_platforms.append("Zepto")
    if active_instamart: enabled_platforms.append("Instamart")

    st.divider()
    st.subheader("🔄 Automated Background Refresh")
    auto_monitor = st.checkbox("Enable Live Loop", value=False)
    interval_mins = st.slider("Interval (Minutes)", min_value=1, max_value=30, value=5)

st.title("Quick Commerce Shelf Monitor & Bidding Desk")
st.caption("Live storefront extraction & strategic bidding actions for Anand Sweets & Chak Now.")

st_autorefresh(interval=30 * 1000, key="auto_refresh_loop")

# Search controls
col_search, col_pin, col_btn = st.columns([3, 2, 2])

with col_search:
    target_kw = st.text_input("Product Search Term:", value="kaju katli", placeholder="Type keyword (e.g. mysore pak, besan laddu)...").strip().lower()

with col_pin:
    target_pin = st.text_input("Target 6-Digit Pincode:", value="560021", placeholder="e.g. 560021, 560103, 560034").strip()

with col_btn:
    st.write("")
    st.write("")
    fetch_btn = st.button("🚀 Fetch Live Shelf Now", type="primary", **WIDTH_KWARG)

# Execution logic
current_time = time.time()
elapsed = current_time - st.session_state.last_scan_time
interval_sec = interval_mins * 60
auto_due = auto_monitor and (elapsed > interval_sec)

should_run = fetch_btn or auto_due

if should_run:
    if auto_due:
        st.session_state.last_scan_time = current_time

    if not target_kw:
        st.warning("⚠️ Please enter a valid product keyword.")
    elif len(target_pin) < 6:
        st.warning("⚠️ Please provide a 6-digit Bangalore pincode.")
    else:
        lat, lon, loc_label = resolve_location(target_pin)
        collected_live = []

        with st.spinner(f"Connecting to live storefronts for '{target_kw}' at {loc_label}..."):
            if "Blinkit" in enabled_platforms:
                b_items = fetch_blinkit_live(target_kw, lat, lon)
                for item in b_items:
                    item["Search Term"] = target_kw
                    item["Pincode"] = target_pin
                    item["Location Name"] = loc_label
                    collected_live.append(item)

            if "Zepto" in enabled_platforms:
                z_items = fetch_zepto_live(target_kw, lat, lon)
                for item in z_items:
                    item["Search Term"] = target_kw
                    item["Pincode"] = target_pin
                    item["Location Name"] = loc_label
                    collected_live.append(item)

            if "Instamart" in enabled_platforms:
                i_items = fetch_instamart_live(target_kw, lat, lon)
                for item in i_items:
                    item["Search Term"] = target_kw
                    item["Pincode"] = target_pin
                    item["Location Name"] = loc_label
                    collected_live.append(item)

        if collected_live:
            history = load_history()
            now_str = datetime.now().strftime("%I:%M %p, %d %b")

            for card in collected_live:
                store_key = card["Platform"].lower()
                ckey = f"{store_key}_{target_kw}_{target_pin}"
                prev_scan = history.get(ckey, None)
                
                prev_pos = None
                if prev_scan:
                    for p in prev_scan.get("items", []):
                        if p.get("Product Name", "").strip().lower() == card["Product Name"].strip().lower():
                            prev_pos = p.get("Overall Shelf Pos")
                            break
                
                if prev_pos is not None:
                    delta = int(prev_pos) - int(card["Overall Shelf Pos"])
                    card["Rank Shift"] = f"{'+' if delta > 0 else ''}{delta}" if delta != 0 else "-"
                else:
                    card["Rank Shift"] = "New"

            for store_name in enabled_platforms:
                s_lower = store_name.lower()
                ckey = f"{s_lower}_{target_kw}_{target_pin}"
                store_skus = [c for c in collected_live if c["Platform"].lower() == s_lower]
                if store_skus:
                    history[ckey] = {
                        "timestamp": now_str,
                        "items": store_skus
                    }
            save_history(history)

            st.session_state.current_view_items = collected_live
            st.session_state.last_query_label = f"🟢 LIVE Storefront Scan: '{target_kw.title()}' at {loc_label}"
            st.rerun()
        else:
            # Check for existing data in history matching the requested keyword
            history = load_history()
            fallback_items = []
            matched_time = ""
            for store_name in enabled_platforms:
                ckey = f"{store_name.lower()}_{target_kw}_{target_pin}"
                cached = history.get(ckey, None)
                if cached:
                    matched_time = cached.get("timestamp", "")
                    for it in cached.get("items", []):
                        it_copy = dict(it)
                        it_copy["Platform"] = store_name
                        it_copy["Search Term"] = target_kw
                        it_copy["Pincode"] = target_pin
                        it_copy["Location Name"] = loc_label
                        it_copy["Rank Shift"] = "-"
                        fallback_items.append(it_copy)
            
            if fallback_items:
                st.session_state.current_view_items = fallback_items
                st.session_state.last_query_label = f"📁 Database Scan: '{target_kw.title()}' at {loc_label} ({matched_time})"
                st.rerun()
            else:
                # Clear stale memory from previous queries
                st.session_state.current_view_items = []
                st.session_state.last_query_label = f"⚠️ No listings found for '{target_kw}' at Pincode {target_pin} on {', '.join(enabled_platforms)}."
                st.rerun()
# Rendering layer
st.divider()

if st.session_state.current_view_items:
    df = pd.DataFrame(st.session_state.current_view_items)
    st.success(f"**{st.session_state.last_query_label}** — {len(df)} total items on shelf.")

    # Metric blocks
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tracked Listings", len(df))
    ad_count = len(df[df["Type"] == "Sponsored Ad"])
    m2.metric("Ad Load (SOV)", f"{(ad_count / len(df) * 100):.1f}%" if len(df) > 0 else "0%")
    m3.metric("Target Brands (Anand / Chak Now)", len(df[df["Brand"].apply(is_my_brand)]))
    m4.metric("Platforms Active", ", ".join(df["Platform"].unique()))

    st.divider()

    # Bidding desk
    st.subheader("💡 Strategic Bidding Desk")

    def generate_bidding_matrix(records):
        matrix = []
        raw = pd.DataFrame(records)
        grouped = raw.groupby(["Platform", "Search Term", "Pincode"])

        for (plat, kw, pin), group in grouped:
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
                rationale = "Listing maintains acceptable positioning without auction threats."

                if is_ad and top_org_pos <= 3:
                    action_badge = "🛑 PAUSE / REDUCE CPC"
                    priority = "CRITICAL"
                    target_placement = f"Organic Locked (Pos #{top_org_pos})"
                    cpc_shift = "-30% to -40% CPC"
                    rationale = f"Organic SKU '{top_org_item['Product Name']}' holds Pos #{top_org_pos}. Paid ad cannibalizes organic conversions."

                elif is_ad and pos > 4:
                    action_badge = "🚀 BOOST BID (SURGE TO ROW 1)"
                    priority = "CRITICAL"
                    target_placement = "Top-of-Fold Row 1 (Pos 1–4)"
                    cpc_shift = "+20% to +30% Bid Surge"
                    rationale = f"Ad cleared at Pos #{pos} (Row 2+). Surge bid to restore top-row presence."

                elif comp_slot1 is not None and (pos > int(comp_slot1["Overall Shelf Pos"])):
                    action_badge = "🛡️ DEFENSIVE COUNTER-BID"
                    priority = "HIGH"
                    target_placement = "Capture Ad Slot #1 (Pos 1–2)"
                    cpc_shift = "+15% to +20% Surge"
                    rationale = f"Competitor '{comp_slot1['Brand']}' took Ad Slot #{comp_slot1['Overall Shelf Pos']}. Counter-bid to protect intent."

                elif not is_ad and pos >= 4:
                    action_badge = "📢 ACTIVATE SPONSORED BID"
                    priority = "HIGH"
                    target_placement = "Sponsored Slot #1 or #2"
                    cpc_shift = "Set Benchmark CPC"
                    rationale = f"Organic rank at Pos #{pos} is drifting. Activate ad to win Row 1."

                elif is_ad and pos <= 3:
                    action_badge = "🟢 LOCK TOP POSITION"
                    priority = "MEDIUM"
                    target_placement = f"Hold Slot #{pos}"
                    cpc_shift = "Test -5% Decrement"
                    rationale = "Top ad position secured. Incrementally shave CPC to find minimum clearing price."

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
                    "Strategic Rationale": rationale
                })
        return matrix

    matrix_data = generate_bidding_matrix(st.session_state.current_view_items)
    if matrix_data:
        b_df = pd.DataFrame(matrix_data)

        def style_bidding(row):
            action = row["Recommended Action"]
            if "PAUSE" in action or row["Urgency"] == "CRITICAL":
                return ['background-color: #fce8e6; color: #a51d24; font-weight: bold;'] * len(row)
            elif "BOOST" in action or "DEFENSIVE" in action:
                return ['background-color: #e8f0fe; color: #1967d2; font-weight: bold;'] * len(row)
            elif "ACTIVATE" in action:
                return ['background-color: #fef7e0; color: #b06000; font-weight: bold;'] * len(row)
            return [''] * len(row)

        c_exp, _ = st.columns([2.5, 7.5])
        with c_exp:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                b_df.to_excel(writer, index=False, sheet_name='ActionPlan')
            st.download_button(
                "📥 Export Action Plan (.xlsx)",
                data=buf.getvalue(),
                file_name=f"bidding_plan_{target_kw}_{target_pin}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                **WIDTH_KWARG
            )

        st.dataframe(b_df.style.apply(style_bidding, axis=1), height=280, **WIDTH_KWARG)
    else:
        st.info("No Anand Sweets / Chak Now SKUs require bidding adjustments in this scan.")

    st.divider()

    # Shelf share chart
    st.subheader("📊 Shelf Share (Target Brand vs. Competitors)")
    counts = df["Brand"].value_counts().reset_index()
    counts.columns = ["Brand", "Count"]
    counts["Ownership"] = counts["Brand"].apply(lambda b: "My Brand (Anand / Chak Now)" if is_my_brand(b) else "Competitor")

    chart = alt.Chart(counts).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X('Brand:N', sort='-y', title="Brand"),
        y=alt.Y('Count:Q', title="SKUs on Shelf"),
        color=alt.Color('Ownership:N', scale=alt.Scale(domain=['My Brand (Anand / Chak Now)', 'Competitor'], range=['#28a745', '#4a5568'])),
        tooltip=['Brand', 'Count', 'Ownership']
    ).properties(height=300)

    st.altair_chart(chart, **WIDTH_KWARG)

    st.divider()

    # Master table
    st.subheader("📋 Master Storefront Inventory")

    def style_master(row):
        is_mine = is_my_brand(row.get("Brand", ""))
        is_ad = row.get("Type", "") == "Sponsored Ad"
        if is_mine and is_ad:
            return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row)
        elif is_mine:
            return ['background-color: #dcfce7; color: #166534; font-weight: bold;'] * len(row)
        elif is_ad:
            return ['background-color: #fef08a; color: #854d0e; font-weight: bold;'] * len(row)
        return [''] * len(row)

    cols = ["Product Name", "Brand", "Overall Shelf Pos", "Placement Rank", "Type", "Price", "Platform", "Search Term", "Pincode", "Rank Shift"]
    avail_cols = [c for c in cols if c in df.columns]

    st.dataframe(df[avail_cols].style.apply(style_master, axis=1), height=450, **WIDTH_KWARG)
else:
    st.info("Enter a product search term and 6-digit pincode above, then click **'🚀 Fetch Live Shelf Now'** to retrieve real-time data.")
