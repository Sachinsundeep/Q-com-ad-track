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
import urllib.request

st.set_page_config(
    page_title="Quick Commerce Shelf Monitor & Bidding Desk",
    page_icon="⚡",
    layout="wide"
)

def df_width():
    try:
        ver = tuple(map(int, st.__version__.split(".")[:2]))
        if ver >= (1, 40): return {"width": "stretch"}
    except Exception: pass
    return {"use_container_width": True}

WIDTH_KWARG = df_width()
GITHUB_RAW_URL = "https://raw.githubusercontent.com/Sachinsundeep/Q-com-ad-track/main/shelf_history.json"
LOCAL_HISTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shelf_history.json")

LOCATION_LOOKUP = {
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
    "560068": {"name": "Electronic City", "lat": "12.899446", "lon": "77.625475"},
    "bommanahalli": {"name": "Bommanahalli", "lat": "12.902900", "lon": "77.624200"},
    "560066": {"name": "Whitefield", "lat": "12.969819", "lon": "77.749972"},
    "whitefield": {"name": "Whitefield", "lat": "12.969819", "lon": "77.749972"},
    "560004": {"name": "Basavanagudi", "lat": "12.943187", "lon": "77.573787"},
    "basavanagudi": {"name": "Basavanagudi", "lat": "12.943187", "lon": "77.573787"},
    "560040": {"name": "Vijayanagar", "lat": "12.971900", "lon": "77.530500"},
    "vijayanagar": {"name": "Vijayanagar", "lat": "12.971900", "lon": "77.530500"},
    "560056": {"name": "Ullal / Bangalore West", "lat": "12.955600", "lon": "77.498000"},
    "ullal": {"name": "Ullal / Bangalore West", "lat": "12.955600", "lon": "77.498000"},
    "560091": {"name": "Viswaneedam", "lat": "12.990000", "lon": "77.510000"}
}

def resolve_location(user_input: str):
    clean = str(user_input).strip().lower()
    if clean in LOCATION_LOOKUP:
        loc = LOCATION_LOOKUP[clean]
        return loc["lat"], loc["lon"], f"{loc['name']} ({clean})"
    if re.match(r"^\d{6}$", clean):
        return "13.0470976", "77.5476596", f"Pincode {clean}"
    return "12.971598", "77.594563", f"{user_input.title()}"

EXCLUDED_BRANDS = ["anandhaas", "shree anandhaas", "anandhas", "ananda dairy", "ananda"]

def is_my_brand(brand_name: str) -> bool:
    b = str(brand_name).strip().lower()
    for exc in EXCLUDED_BRANDS:
        if exc in b: return False
    return bool("anand" in b or "chak" in b)

@st.cache_data(ttl=10)
def load_history_live():
    # Attempt to load directly from GitHub raw API
    try:
        req = urllib.request.Request(
            f"{GITHUB_RAW_URL}?t={int(time.time())}",
            headers={"User-Agent": "Qcom-Monitor"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        pass

    # Local fallback
    if os.path.exists(LOCAL_HISTORY):
        try:
            with open(LOCAL_HISTORY, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def export_history_to_excel():
    history = load_history_live()
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
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df_all.to_excel(writer, index=False, sheet_name='Historical Scans')
        df_targets = df_all[df_all["Target Brand Flag"] == "YES"] if not df_all.empty else df_all
        df_targets.to_excel(writer, index=False, sheet_name='Target Brands Shift Log')
    return buf.getvalue()

# Initialize dynamic options
raw_hist = load_history_live()
hist_kws = sorted(list({k.split("_")[1] for k in raw_hist.keys() if len(k.split("_")) > 1}))
hist_locs = sorted(list({k.split("_")[2] for k in raw_hist.keys() if len(k.split("_")) > 2}))

if not hist_kws: hist_kws = ["besan laddu", "mysore pak", "kaju katli"]
if not hist_locs: hist_locs = ["560021", "560091", "560103", "560034"]

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
    alert_scope = st.radio("Evaluate rank shifts for:", ["My Brands Only", "Top-5 Competitor Ads Only", "Both (Full Visibility)"], index=0)

    st.divider()
    st.header("💡 Bidding Engine Filter")
    suggest_blinkit = st.checkbox("Blinkit (Brands Central)", value=True)
    suggest_zepto = st.checkbox("Zepto Brand Engine", value=True)
    suggest_instamart = st.checkbox("Swiggy Ads", value=True)
    suggest_platforms = []
    if suggest_blinkit: suggest_platforms.append("Blinkit")
    if suggest_zepto: suggest_platforms.append("Zepto")
    if suggest_instamart: suggest_platforms.append("Instamart")

st.title("Quick Commerce Shelf Monitor & Bidding Desk")
st.caption("Live storefront shelf monitoring & algorithmic bidding engine for Anand Sweets & Chak Now.")

st_autorefresh(interval=15 * 1000, key="cloud_refresher")

st.subheader("🎯 Monitoring Scope: Target Keywords & Locations")
c_sel1, c_sel2 = st.columns(2)

with c_sel1:
    selected_keywords = st.multiselect("Active Search Keywords:", options=hist_kws, default=[hist_kws[0]])

with c_sel2:
    selected_locations = st.multiselect("Active Locations / Pincodes:", options=hist_locs, default=[hist_locs[0]])

c_scope, c_store, c_fetch = st.columns([3, 3, 2])
with c_scope:
    store_scope = st.selectbox("Storefront Scope", ["All Enabled Storefronts", "Selected Storefront Only"])
with c_store:
    chosen_store = st.selectbox("Active Store", ["Blinkit", "Zepto", "Instamart"])
with c_fetch:
    st.write("")
    st.write("")
    fetch_btn = st.button("🚀 Refresh Live Shelf", type="primary", **WIDTH_KWARG)

if fetch_btn:
    st.cache_data.clear()
    st.rerun()

# Build Active Display Dataset
history = load_history_live()
active_items = []
target_stores = [chosen_store.capitalize()] if store_scope == "Selected Storefront Only" else (active_platforms if active_platforms else ["Blinkit", "Zepto", "Instamart"])

for kw in selected_keywords:
    for loc in selected_locations:
        c_kw = str(kw).lower().strip()
        c_loc = str(loc).lower().strip()
        for st_name in target_stores:
            ckey = f"{st_name.lower()}_{c_kw}_{c_loc}"
            if ckey in history:
                _, _, loc_label = resolve_location(c_loc)
                for item in history[ckey].get("items", []):
                    ci = dict(item)
                    ci["Platform"] = st_name.capitalize()
                    ci["Search Term"] = c_kw
                    ci["Location"] = loc
                    ci["Location Name"] = loc_label
                    ci["Rank Shift"] = "-"
                    active_items.append(ci)

if active_items:
    df = pd.DataFrame(active_items)
    kw_str = ", ".join([k.title() for k in selected_keywords])
    loc_str = ", ".join([l.title() for l in selected_locations])
    st.success(f"Displaying {len(df)} live listings for **{kw_str}** at **{loc_str}**.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tracked Listings", len(df))
    ad_count = len(df[df["Type"] == "Sponsored Ad"])
    m2.metric("Ad Load (SOV)", f"{(ad_count / len(df) * 100):.1f}%" if len(df) > 0 else "0%")
    m3.metric("Target Brands (Anand / Chak Now)", len(df[df["Brand"].apply(is_my_brand)]))
    m4.metric("Storefronts In View", ", ".join(df["Platform"].unique()))

    st.divider()

    # Strategic Bidding Desk
    st.subheader("💡 Strategic Bidding Desk")
    def compute_bidding_matrix(items, enabled_plats):
        matrix = []
        raw = pd.DataFrame(items)
        grouped = raw.groupby(["Platform", "Search Term", "Location"])
        norm_enabled = [p.capitalize() for p in enabled_plats] if enabled_plats else ["Blinkit", "Zepto", "Instamart"]

        for (plat, kw, loc), group in grouped:
            if str(plat).capitalize() not in norm_enabled: continue
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

                action_badge = "⚪ MAINTAIN BID"
                priority = "LOW"
                target_placement = "Sustain Placement"
                cpc_shift = "Hold (0%)"
                budget_advice = "Normal Daily Cap"
                rationale = "Listing maintains acceptable positioning without auction threat."

                if is_ad and top_org_pos <= 3:
                    action_badge = "🛑 PAUSE / REDUCE CPC"
                    priority = "CRITICAL"
                    target_placement = f"Organic Locked (Pos #{top_org_pos})"
                    cpc_shift = "-30% to -40% CPC"
                    budget_advice = "Reallocate 50% Budget to Deficit Dark Stores"
                    rationale = f"Organic SKU '{top_org_item['Product Name']}' is secured at Pos #{top_org_pos}. Paid ad cannibalizes free organic conversions."

                elif is_ad and pos > 4:
                    action_badge = "🚀 BOOST BID (SURGE TO ROW 1)"
                    priority = "CRITICAL"
                    target_placement = "Top-of-Fold Row 1 (Pos 1–4)"
                    cpc_shift = "+20% to +30% Bid Surge"
                    budget_advice = "Increase Daily Budget (+20%)"
                    rationale = f"Ad cleared at Pos #{pos} (Row 2+). Click-through rate decays significantly below Row 1. Surge bid to win Slot 1–4."

                elif comp_slot1 is not None and (pos > int(comp_slot1["Overall Shelf Pos"])):
                    action_badge = "🛡️ DEFENSIVE COUNTER-BID"
                    priority = "HIGH"
                    target_placement = "Capture Ad Slot #1 (Pos 1–2)"
                    cpc_shift = "+15% to +20% Surge"
                    budget_advice = "Increase Daily Budget (+15%)"
                    rationale = f"Competitor '{comp_slot1['Brand']}' took Ad Slot #{comp_slot1['Overall Shelf Pos']}. Outbid to protect purchase intent."

                elif not is_ad and pos >= 4:
                    action_badge = "📢 ACTIVATE SPONSORED BID"
                    priority = "HIGH"
                    target_placement = "Sponsored Slot #1 or #2"
                    cpc_shift = "Set Category Benchmark CPC"
                    budget_advice = "Open Dedicated Campaign Line"
                    rationale = f"Organic rank at Pos #{pos} is drifting. Activating a targeted ad will push this SKU back to row 1."

                elif is_ad and pos <= 3:
                    action_badge = "🟢 LOCK TOP POSITION"
                    priority = "MEDIUM"
                    target_placement = f"Hold Slot #{pos}"
                    cpc_shift = "Test -5% Decrement"
                    budget_advice = "Sustain Current Cap"
                    rationale = "Holding premium ad placement. Incrementally shave CPC by 5% to discover minimum winning clearing price."

                matrix.append({
                    "Urgency": priority,
                    "Platform": plat,
                    "Keyword": kw,
                    "Location": loc,
                    "Target SKU": title,
                    "Current Position": f"Pos #{pos} ({row.get('Placement Rank', '')})",
                    "Recommended Action": action_badge,
                    "Target Placement": target_placement,
                    "Suggested CPC Shift": cpc_shift,
                    "Budget Sizing": budget_advice,
                    "Commercial Rationale": rationale
                })
        return matrix

    b_mat = compute_bidding_matrix(active_items, suggest_platforms)
    if b_mat:
        b_df = pd.DataFrame(b_mat)
        def style_bidding(row):
            action = row["Recommended Action"]
            if "PAUSE" in action or row["Urgency"] == "CRITICAL":
                return ['background-color: #fce8e6; color: #a51d24; font-weight: bold;'] * len(row)
            elif "BOOST" in action or "DEFENSIVE" in action:
                return ['background-color: #e8f0fe; color: #1967d2; font-weight: bold;'] * len(row)
            elif "ACTIVATE" in action:
                return ['background-color: #fef7e0; color: #b06000; font-weight: bold;'] * len(row)
            return [''] * len(row)

        c_exp, _ = st.columns([2.8, 7.2])
        with c_exp:
            b_buf = io.BytesIO()
            with pd.ExcelWriter(b_buf, engine='openpyxl') as writer:
                b_df.to_excel(writer, index=False, sheet_name='ActionableBiddingPlan')
            st.download_button("📥 Export Bidding Action Sheet (.xlsx)", data=b_buf.getvalue(), file_name="qcom_bidding_action_plan.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", **WIDTH_KWARG)
        st.dataframe(b_df.style.apply(style_bidding, axis=1), height=300, **WIDTH_KWARG)

    st.divider()

    # Top-of-Fold & Sponsored
    c_ad, c_top = st.columns([3, 2])
    with c_ad:
        st.markdown("**Identified Sponsored Placements**")
        s_df = df[df["Type"] == "Sponsored Ad"]
        if not s_df.empty:
            def style_ad(row):
                return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row) if is_my_brand(row["Brand"]) else [''] * len(row)
            st.dataframe(s_df[["Platform", "Location", "Overall Shelf Pos", "Placement Rank", "Brand", "Product Name", "Price"]].style.apply(style_ad, axis=1), height=230, **WIDTH_KWARG)
        else:
            st.info("No sponsored ads present.")

    with c_top:
        st.markdown("**Top-of-Fold (Slots 1 to 4)**")
        top4 = df.groupby(["Platform", "Search Term", "Location"]).head(4)[["Platform", "Overall Shelf Pos", "Type", "Brand", "Product Name"]]
        def style_top4(row):
            is_mine = is_my_brand(row["Brand"])
            is_ad = row["Type"] == "Sponsored Ad"
            if is_mine and is_ad: return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row)
            elif is_mine: return ['background-color: #dcfce7; color: #166534; font-weight: bold;'] * len(row)
            elif is_ad: return ['background-color: #fef08a; color: #854d0e; font-weight: bold;'] * len(row)
            return [''] * len(row)
        st.dataframe(top4.style.apply(style_top4, axis=1), height=230, **WIDTH_KWARG)

    st.divider()

    # Brand Share Chart
    st.subheader("📊 Brand Shelf Share (Target vs. Competitors)")
    b_counts = df["Brand"].value_counts().reset_index()
    b_counts.columns = ["Brand", "Count"]
    b_counts["Classification"] = b_counts["Brand"].apply(lambda b: "My Brand (Anand / Chak Now)" if is_my_brand(b) else "Competitor")
    chart = alt.Chart(b_counts).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X('Brand:N', sort='-y', title="Brand"),
        y=alt.Y('Count:Q', title="SKUs on Shelf"),
        color=alt.Color('Classification:N', scale=alt.Scale(domain=['My Brand (Anand / Chak Now)', 'Competitor'], range=['#28a745', '#4a5568'])),
        tooltip=['Brand', 'Count', 'Classification']
    ).properties(height=320)
    st.altair_chart(chart, **WIDTH_KWARG)

    st.divider()

    # Master Table & Exports
    st.subheader("📋 Complete Master Shelf Inventory")
    c_d1, c_d2, _ = st.columns([1.5, 1.5, 7])
    with c_d1:
        st.download_button("📥 Export Current Shelf (.csv)", data=df.to_csv(index=False).encode('utf-8'), file_name="current_shelf.csv", mime="text/csv")
    with c_d2:
        m_buf = io.BytesIO()
        with pd.ExcelWriter(m_buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='CurrentShelf')
        st.download_button("📊 Export Current Shelf (.xlsx)", data=m_buf.getvalue(), file_name="current_shelf.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def style_full_table(row):
        is_mine = is_my_brand(row.get("Brand", ""))
        is_ad = row.get("Type", "") == "Sponsored Ad"
        if is_mine and is_ad: return ['background-color: #bbf7d0; color: #14532d; font-weight: bold; border-left: 5px solid #16a34a;'] * len(row)
        elif is_mine: return ['background-color: #dcfce7; color: #166534; font-weight: bold;'] * len(row)
        elif is_ad: return ['background-color: #fef08a; color: #854d0e; font-weight: bold;'] * len(row)
        return [''] * len(row)

    cols_order = ["Product Name", "Brand", "Overall Shelf Pos", "Type", "Price", "Platform", "Search Term", "Location", "Location Name", "Rank Shift"]
    st.dataframe(df[[c for c in cols_order if c in df.columns]].style.apply(style_full_table, axis=1), height=550, **WIDTH_KWARG)

else:
    st.warning("No shelf records found for the selected scope. Please run a scan from a local machine or select an existing record.")
