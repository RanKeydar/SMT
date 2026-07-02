import math
import os
import pathlib
import re
import shutil
from io import BytesIO

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="תנועות בניירות ערך",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_ga_to_streamlit_head():
    ga_id = os.getenv("GA_MEASUREMENT_ID", "").strip()
    if not ga_id:
        return

    ga_tag = f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
    <script id="google_analytics">
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{ga_id}');
    </script>
    """

    index_path = pathlib.Path(st.__file__).parent / "static" / "index.html"
    backup_path = index_path.with_suffix(".bck")

    html = index_path.read_text(encoding="utf-8")

    if 'id="google_analytics"' in html or f"gtag/js?id={ga_id}" in html:
        return

    if not backup_path.exists():
        shutil.copy(index_path, backup_path)

    new_html = html.replace("<head>", "<head>\n" + ga_tag + "\n", 1)
    index_path.write_text(new_html, encoding="utf-8")


inject_ga_to_streamlit_head()

SHEET_NAME = "הכל"

REQUIRED_HEADERS = [
    "סוג נייר",
    "ענף",
    "מספר נייר ערך",
    "נייר ערך",
    "סוג לקוח",
    "תת סוג לקוח",
]

COLUMN_DEFS = [
    ("פנסיה/גמל/ביטוח", ["קרן פנסיה/קופת גמל/חברת ביטוח"]),
    ("מנהל תיקים", ["מנהל תיקים/לקוח מנוהל על ידי מנהל תיקים"]),
    ("קרן סל", ["קרן סל/עושה שוק בקרן סל"]),
    ("ישראלי - יחיד", ["ישראלי - יחיד"]),
    ("ישראלי - תאגיד", ["ישראלי - תאגיד"]),
    ("ישראלי - מאוחד", ["ישראלי - יחיד", "ישראלי - תאגיד", "ישראלי - אחר"]),
    ("קרן נאמנות", ["משקיע מוסדי מסוג קרן נאמנות"]),
    ("נוסטרו", ["נוסטרו"]),
    ("תושב חוץ", ["משקיע חוץ"]),
]

EPSILON = 1e-6
PAGE_SIZE = 20


st.markdown(
    """
    <style>
    html, body, [class*="css"] { direction: rtl; }
    body, p, div, label, span, h1, h2, h3 { text-align: right !important; }
    .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }
    h1, h2, h3 { direction: rtl; unicode-bidi: plaintext; }

    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        text-align: right;
        direction: rtl;
        border-radius: 12px;
    }

    div[data-testid="stFileUploader"] section { border-radius: 16px; }

    .value-box {
        padding: 14px 10px;
        border: 1px solid #cbd5e1;
        text-align: center !important;
        font-weight: 700;
        border-radius: 10px;
    }

    .pos { background: #d9f2d9; color: #116329; }
    .neg { background: #f7d6d9; color: #a61b29; }
    .zero { background: #f8fafc; color: #334155; }

    .result-title {
        font-size: 1.45rem;
        font-weight: 800;
        margin: 1rem 0 0.25rem;
    }

    .period-text {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 0.75rem;
    }

    .detail-title {
        margin-top: 24px;
        margin-bottom: 10px;
    }

    .detail-html {
        overflow-x: auto;
    }

    .detail-html table {
        width: 100%;
        border-collapse: collapse;
        direction: rtl;
        table-layout: auto;
    }

    .detail-html th {
        background: #eef2f7;
        color: #111827;
        border: 1px solid #d1d5db;
        padding: 10px;
        text-align: right !important;
        white-space: nowrap;
    }

    .detail-html td {
        border: 1px solid #d1d5db;
        padding: 10px;
        text-align: right !important;
        white-space: nowrap;
    }

    .detail-html .num {
        text-align: right !important;
        direction: ltr;
        font-variant-numeric: tabular-nums;
    }

    .detail-html .num.pos { background: #d9f2d9; color: #116329; }
    .detail-html .num.neg { background: #f7d6d9; color: #a61b29; }
    .detail-html .num.zero { background: #f8fafc; color: #334155; }
    </style>
    """,
    unsafe_allow_html=True,
)


def find_header_row(raw, required_headers, scan_rows=12):
    limit = min(scan_rows, len(raw))
    best_idx, best_score = None, -1
    for i in range(limit):
        row_vals = set(raw.iloc[i].fillna("").astype(str).str.strip().tolist())
        score = sum(1 for h in required_headers if h in row_vals)
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx, best_score


def extract_period_label(title_text, fallback_name):
    title = str(title_text).strip()
    if not title:
        return fallback_name
    return re.sub(r"\s+", " ", title)


def short_period_label(period_text):
    text = str(period_text)
    dates = re.findall(r"(\d{2})-(\d{2})-(\d{2})", text)
    if dates:
        day, month, year = dates[-1]
        return f"{month}/{year}"
    months_he = {
        "ינואר": "01", "פברואר": "02", "מרץ": "03", "אפריל": "04",
        "מאי": "05", "יוני": "06", "יולי": "07", "אוגוסט": "08",
        "ספטמבר": "09", "אוקטובר": "10", "נובמבר": "11", "דצמבר": "12",
    }
    for name, num in months_he.items():
        if name in text:
            year_match = re.search(r"20(\d{2})", text)
            yy = year_match.group(1) if year_match else ""
            return f"{num}/{yy}" if yy else num
    return text[:18]


def normalize_zero(v):
    try:
        x = float(v)
        if abs(x) < EPSILON:
            return 0.0
        return x
    except Exception:
        return v


def format_num(x):
    try:
        x = normalize_zero(x)
        return f"{float(x):,.0f}"
    except Exception:
        return str(x)


def class_for_value(v):
    try:
        x = normalize_zero(v)
        if x > 0:
            return "pos"
        if x < 0:
            return "neg"
        return "zero"
    except Exception:
        return "zero"


def normalize_group(row):
    ct = row["client_type"]
    sub = row["client_subtype"]

    if ct == "משקיע ישראלי":
        if "יחיד" in sub:
            return "ישראלי - יחיד"
        if "תאגיד" in sub:
            return "ישראלי - תאגיד"
        return "ישראלי - אחר"

    if ct == "תושב חוץ":
        return "משקיע חוץ"

    return ct


def build_summary_values(selected):
    sums = selected.groupby("display_group", as_index=False)["net"].sum()
    mapping = dict(zip(sums["display_group"], sums["net"]))

    row = []
    for label, keys in COLUMN_DEFS:
        val = sum(mapping.get(k, 0) for k in keys)
        val = normalize_zero(val)
        row.append((label, keys, val))

    return row


def detail_table(selected, groups):
    rows = selected[selected["display_group"].isin(groups)].copy()
    if rows.empty:
        return None

    out = rows.groupby(["client_type", "client_subtype"], as_index=False)[
        ["buy", "sell", "net", "total"]
    ].sum()

    for c in ["buy", "sell", "net", "total"]:
        out[c] = out[c].apply(normalize_zero)

    out = out.rename(
        columns={
            "client_type": "סוג לקוח",
            "client_subtype": "תת סוג לקוח",
            "buy": "קונה",
            "sell": "מוכר",
            "net": "נטו",
            "total": "כולל",
        }
    )
    return out


def monthly_detail_table(selected):
    if selected.empty:
        return pd.DataFrame()

    out = (
        selected.groupby("source_period", as_index=False)[["buy", "sell", "net", "total"]]
        .sum()
        .sort_values("source_period")
    )

    for c in ["buy", "sell", "net", "total"]:
        out[c] = out[c].apply(normalize_zero)

    total_row = pd.DataFrame([{
        "source_period": 'סה"כ',
        "buy": normalize_zero(out["buy"].sum()),
        "sell": normalize_zero(out["sell"].sum()),
        "net": normalize_zero(out["net"].sum()),
        "total": normalize_zero(out["total"].sum()),
    }])

    out = pd.concat([out, total_row], ignore_index=True)

    out = out.rename(
        columns={
            "source_period": "תקופה",
            "buy": "קונה",
            "sell": "מוכר",
            "net": "נטו",
            "total": "כולל",
        }
    )
    return out


def period_breakdown_tables(selected):
    if selected.empty:
        return []

    period_tables = []
    for period in sorted(selected["source_period"].dropna().unique().tolist()):
        period_df = selected[selected["source_period"] == period].copy()
        tbl = detail_table(period_df, period_df["display_group"].unique().tolist())
        if tbl is not None and not tbl.empty:
            summary_row = pd.DataFrame([{
                "סוג לקוח": 'סה"כ',
                "תת סוג לקוח": "",
                "קונה": normalize_zero(tbl["קונה"].sum()),
                "מוכר": normalize_zero(tbl["מוכר"].sum()),
                "נטו": normalize_zero(tbl["נטו"].sum()),
                "כולל": normalize_zero(tbl["כולל"].sum()),
            }])
            tbl = pd.concat([tbl, summary_row], ignore_index=True)
            period_tables.append((period, tbl))

    return period_tables


def render_detail_html(df):
    cols = list(df.columns)
    html = '<div class="detail-html"><table><thead><tr>'
    for c in cols:
        html += f"<th>{c}</th>"
    html += "</tr></thead><tbody>"

    numeric_cols = {"קונה", "מוכר", "נטו", "כולל", "טווח שינוי"}

    for _, r in df.iterrows():
        html += "<tr>"
        for c in cols:
            val = r[c]
            if c in numeric_cols and pd.notna(val):
                html += f'<td class="num {class_for_value(val)}">{format_num(val)}</td>'
            else:
                html += f"<td>{val}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def to_excel_bytes(df: pd.DataFrame, sheet_name="export") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output.getvalue()


def prep_download_file(key: str, data: bytes, file_name: str, mime: str):
    st.session_state.downloads[key] = {
        "data": data,
        "file_name": file_name,
        "mime": mime,
        "ready": True,
    }


def load_excel_single(file_obj):
    file_bytes = file_obj.getvalue()
    bio = BytesIO(file_bytes)
    raw = pd.read_excel(bio, sheet_name=SHEET_NAME, header=None)

    title_text = str(raw.iloc[0, 0]).strip() if len(raw) > 0 else ""
    header_row, score = find_header_row(raw, REQUIRED_HEADERS)

    if header_row is None or score < 4:
        raise ValueError(f'לא הצלחתי לזהות אוטומטית את שורת הכותרות בקובץ "{file_obj.name}"')

    headers = raw.iloc[header_row].fillna("").astype(str).str.strip().tolist()
    df = raw.iloc[header_row + 1:].copy()
    df.columns = headers

    df = df.loc[:, [c for c in df.columns if str(c).strip() and not str(c).startswith("Unnamed:")]]

    df = df.rename(
        columns={
            "נייר ערך": "security_name",
            "מספר נייר ערך": "security_id",
            "סוג נייר": "security_type",
            "ענף": "sector",
            "סוג לקוח": "client_type",
            "תת סוג לקוח": "client_subtype",
            "מחזור כספי - קונה": "buy",
            "מחזור כספי - מוכר": "sell",
            "מחזור כספי - נטו": "net",
            "מחזור כספי - כולל": "total",
        }
    )

    needed = [
        "security_name", "security_id", "security_type", "sector",
        "client_type", "client_subtype", "buy", "sell", "net", "total"
    ]

    for c in needed:
        if c not in df.columns:
            df[c] = None

    for c in ["buy", "sell", "net", "total"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).apply(normalize_zero)

    for c in ["security_name", "security_id", "security_type", "sector", "client_type", "client_subtype"]:
        df[c] = df[c].astype(str).str.strip()

    df = df[
        df["security_name"].notna() & (df["security_name"] != "") & (df["security_name"] != "nan")
    ]
    df = df[
        df["security_id"].notna() & (df["security_id"] != "") & (df["security_id"] != "nan")
    ]

    df["display_group"] = df.apply(normalize_group, axis=1)
    df["source_file"] = file_obj.name
    df["source_period"] = extract_period_label(title_text, file_obj.name)

    return df, title_text


@st.cache_data(show_spinner=False)
def load_multiple_excels(file_payloads):
    frames = []
    for item in file_payloads:
        fake_file = item["uploaded_file"]
        df, _ = load_excel_single(fake_file)
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def build_comparison_table(filtered_df, compare_by):
    if filtered_df.empty:
        return pd.DataFrame(), [], {}

    group_cols_map = {
        "לפי נייר ערך": ["security_id", "security_name"],
        "לפי ענף": ["sector"],
        "לפי סוג נייר": ["security_type"],
    }

    index_cols = group_cols_map[compare_by]

    pivot = pd.pivot_table(
        filtered_df,
        values="net",
        index=index_cols,
        columns="source_period",
        aggfunc="sum",
        fill_value=0,
        margins=True,
        margins_name='סה"כ',
    ).reset_index()

    period_cols = [c for c in pivot.columns if c not in index_cols]
    raw_period_cols = [c for c in period_cols if c != 'סה"כ']

    for c in raw_period_cols + ['סה"כ']:
        if c in pivot.columns:
            pivot[c] = pivot[c].apply(normalize_zero)

    if raw_period_cols:
        mask_non_zero = pivot[raw_period_cols].apply(
            lambda row: any(abs(float(v)) >= EPSILON for v in row),
            axis=1
        )
        total_rows = pivot[index_cols].astype(str).eq('סה"כ').any(axis=1) if index_cols else pd.Series([False] * len(pivot))
        pivot = pivot[mask_non_zero | total_rows].copy()

    if len(raw_period_cols) >= 2:
        pivot["טווח שינוי"] = pivot[raw_period_cols].max(axis=1) - pivot[raw_period_cols].min(axis=1)
        pivot["טווח שינוי"] = pivot["טווח שינוי"].apply(normalize_zero)

    rename_map = {col: short_period_label(col) for col in raw_period_cols}
    pivot = pivot.rename(columns=rename_map)

    short_period_cols = [rename_map[c] for c in raw_period_cols]

    return pivot, short_period_cols, rename_map


def paginate_df(df, page_key, page_size=20):
    if df.empty:
        return df, 1, 1, 0

    total_rows = len(df)
    total_pages = max(1, math.ceil(total_rows / page_size))

    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    st.session_state[page_key] = min(max(1, st.session_state[page_key]), total_pages)

    start_idx = (st.session_state[page_key] - 1) * page_size
    end_idx = start_idx + page_size

    return df.iloc[start_idx:end_idx].copy(), st.session_state[page_key], total_pages, total_rows


if "detail_groups" not in st.session_state:
    st.session_state.detail_groups = None

if "downloads" not in st.session_state:
    st.session_state.downloads = {}

if "compare_page" not in st.session_state:
    st.session_state.compare_page = 1


st.title("תנועות בניירות ערך")
st.caption("העלאת כמה קבצים, אגרגציה מאוחדת, פירוט חודשי והשוואה בין תקופות")

with st.sidebar:
    st.header("טעינת נתונים")
    uploaded_files = st.file_uploader(
        "העלה קבצי XLSX",
        type=["xlsx"],
        accept_multiple_files=True,
    )

    st.divider()
    st.subheader("אודות")
    st.caption("האפליקציה תומכת בהעלאת כמה קבצים במקביל, השוואה לפי תקופה ופירוט נפרד לכל תקופה.")


if not uploaded_files:
    st.info("העלה לפחות קובץ XLSX אחד כדי להתחיל לעבוד")
    st.stop()

file_payloads = [{"uploaded_file": f} for f in uploaded_files]

try:
    df = load_multiple_excels(file_payloads)
except Exception as e:
    st.error(str(e))
    st.stop()

if df.empty:
    st.warning("לא נטענו נתונים")
    st.stop()

tab_agg, tab_compare = st.tabs(["אגרגציה מאוחדת", "השוואה בין תקופות"])

with tab_agg:
    c1, c2, c3 = st.columns([2, 1, 1])

    with c1:
        query = st.text_input("חיפוש לפי שם נייר או מספר נייר", value="", key="agg_query")

    view_mode = st.radio(
        "אופן תצוגה",
        ["לפי נייר ערך", "לפי ענף", "לפי סוג נייר"],
        horizontal=True,
        key="agg_view_mode",
    )

    with c2:
        sector_options = ["הכל"] + sorted([x for x in df["sector"].dropna().unique().tolist() if x and x != "nan"])
        sector_filter = st.selectbox("ענף", sector_options, key="agg_sector")

    with c3:
        type_options = ["הכל"] + sorted([x for x in df["security_type"].dropna().unique().tolist() if x and x != "nan"])
        sec_type_filter = st.selectbox("סוג נייר", type_options, key="agg_type")

    period_options = ["הכל"] + sorted(df["source_period"].dropna().unique().tolist())
    selected_period = st.selectbox("תקופה", period_options, key="agg_period")

    work = df.copy()

    if sector_filter != "הכל":
        work = work[work["sector"] == sector_filter]

    if sec_type_filter != "הכל":
        work = work[work["security_type"] == sec_type_filter]

    if selected_period != "הכל":
        work = work[work["source_period"] == selected_period]

    selected = None
    summary = None
    security_label = ""

    if view_mode == "לפי נייר ערך":
        if not query.strip():
            st.session_state.detail_groups = None
            st.info("הקלד שם נייר או מספר נייר כדי להציג נתונים")
            st.stop()

        q = query.strip()
        exact_id = work[work["security_id"] == q]
        exact_name = work[work["security_name"] == q]

        if not exact_id.empty:
            matched = exact_id
        elif not exact_name.empty:
            matched = exact_name
        else:
            matched = work[
                work["security_name"].str.contains(q, case=False, na=False)
                | work["security_id"].str.contains(q, case=False, na=False)
            ]

        if matched.empty:
            st.session_state.detail_groups = None
            st.warning("לא נמצאו תוצאות לפי הסינון הנוכחי")
            st.stop()

        matches = (
            matched[["security_name", "security_id"]]
            .drop_duplicates()
            .sort_values(["security_name", "security_id"])
        )

        if len(matches) > 1:
            st.session_state.detail_groups = None
            st.warning("נמצאו כמה תוצאות. דייק את החיפוש:")
            for _, row in matches.head(20).iterrows():
                st.write(f"- {row['security_name']} | {row['security_id']}")
            st.stop()

        security_id = matches.iloc[0]["security_id"]
        selected = matched[matched["security_id"] == security_id].copy()
        security_label = selected.iloc[0]["security_name"]
        summary = build_summary_values(selected)

    elif view_mode == "לפי ענף":
        if sector_filter == "הכל":
            st.session_state.detail_groups = None
            st.info("בחר ענף כדי להציג פלט לפי ענף")
            st.stop()

        selected = work.copy()
        security_label = f"ענף: {sector_filter}"
        summary = build_summary_values(selected)

    else:
        if sec_type_filter == "הכל":
            st.session_state.detail_groups = None
            st.info("בחר סוג נייר כדי להציג פלט לפי סוג נייר")
            st.stop()

        selected = work.copy()
        security_label = f"סוג נייר: {sec_type_filter}"
        summary = build_summary_values(selected)

    st.markdown(f'<div class="result-title">{security_label}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="period-text">מספר תקופות בטעינה: {selected["source_period"].nunique()}</div>',
        unsafe_allow_html=True,
    )

    head_cols = st.columns(len(summary))
    for i, (label, groups, val) in enumerate(summary):
        with head_cols[i]:
            if st.button(label, key=f"btn_{i}", use_container_width=True):
                st.session_state.detail_groups = groups

    value_cols = st.columns(len(summary))
    for i, (_, groups, val) in enumerate(summary):
        with value_cols[i]:
            st.markdown(
                f"<div class='value-box {class_for_value(val)}'>{format_num(val)}</div>",
                unsafe_allow_html=True,
            )

    monthly_df = monthly_detail_table(selected)
    if not monthly_df.empty:
        st.divider()
        st.subheader("פירוט חודשי מרוכז")
        st.markdown(render_detail_html(monthly_df), unsafe_allow_html=True)

    period_tables = period_breakdown_tables(selected)
    if period_tables:
        st.divider()
        st.subheader("טבלאות נפרדות לפי תקופה")
        for period, tbl in period_tables:
            st.markdown(f"### {period}")
            st.markdown(render_detail_html(tbl), unsafe_allow_html=True)

    st.divider()
    st.subheader("ייצוא תוצאה מאוחדת")

    prep_cols = st.columns(2)
    with prep_cols[0]:
        if st.button("הכן CSV של התוצאה המאוחדת", use_container_width=True):
            prep_download_file(
                key="main_csv",
                data=to_csv_bytes(selected),
                file_name="aggregated_results.csv",
                mime="text/csv",
            )

    with prep_cols[1]:
        if st.button("הכן Excel של התוצאה המאוחדת", use_container_width=True):
            prep_download_file(
                key="main_xlsx",
                data=to_excel_bytes(selected, sheet_name="aggregated_results"),
                file_name="aggregated_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    if st.session_state.downloads.get("main_csv", {}).get("ready") or st.session_state.downloads.get("main_xlsx", {}).get("ready"):
        download_cols = st.columns(2)

        if st.session_state.downloads.get("main_csv", {}).get("ready"):
            with download_cols[0]:
                st.download_button(
                    label="הורד CSV של התוצאה המאוחדת",
                    data=st.session_state.downloads["main_csv"]["data"],
                    file_name=st.session_state.downloads["main_csv"]["file_name"],
                    mime=st.session_state.downloads["main_csv"]["mime"],
                    on_click="ignore",
                    use_container_width=True,
                )

        if st.session_state.downloads.get("main_xlsx", {}).get("ready"):
            with download_cols[1]:
                st.download_button(
                    label="הורד Excel של התוצאה המאוחדת",
                    data=st.session_state.downloads["main_xlsx"]["data"],
                    file_name=st.session_state.downloads["main_xlsx"]["file_name"],
                    mime=st.session_state.downloads["main_xlsx"]["mime"],
                    on_click="ignore",
                    use_container_width=True,
                )

    if st.session_state.detail_groups:
        details = detail_table(selected, st.session_state.detail_groups)
        if details is not None:
            summary_row = pd.DataFrame([{
                "סוג לקוח": 'סה"כ',
                "תת סוג לקוח": "",
                "קונה": normalize_zero(details["קונה"].sum()),
                "מוכר": normalize_zero(details["מוכר"].sum()),
                "נטו": normalize_zero(details["נטו"].sum()),
                "כולל": normalize_zero(details["כולל"].sum()),
            }])
            details = pd.concat([details, summary_row], ignore_index=True)

            st.markdown(
                '<div class="detail-title"><h3>תנועות לחיתוך שנבחר</h3></div>',
                unsafe_allow_html=True,
            )
            st.markdown(render_detail_html(details), unsafe_allow_html=True)


with tab_compare:
    st.subheader("השוואה בין תקופות")

    compare_mode = st.radio(
        "השווה לפי",
        ["לפי נייר ערך", "לפי ענף", "לפי סוג נייר"],
        horizontal=True,
        key="compare_mode",
    )

    compare_col1, compare_col2, compare_col3 = st.columns([2, 1, 1])

    with compare_col1:
        compare_query = st.text_input("חיפוש ממוקד להשוואה", value="", key="compare_query")

    with compare_col2:
        compare_sector = st.selectbox(
            "ענף להשוואה",
            ["הכל"] + sorted([x for x in df["sector"].dropna().unique().tolist() if x and x != "nan"]),
            key="compare_sector",
        )

    with compare_col3:
        compare_type = st.selectbox(
            "סוג נייר להשוואה",
            ["הכל"] + sorted([x for x in df["security_type"].dropna().unique().tolist() if x and x != "nan"]),
            key="compare_type",
        )

    compare_work = df.copy()

    if compare_sector != "הכל":
        compare_work = compare_work[compare_work["sector"] == compare_sector]

    if compare_type != "הכל":
        compare_work = compare_work[compare_work["security_type"] == compare_type]

    if compare_mode == "לפי נייר ערך" and compare_query.strip():
        q = compare_query.strip()
        compare_work = compare_work[
            compare_work["security_name"].str.contains(q, case=False, na=False)
            | compare_work["security_id"].str.contains(q, case=False, na=False)
        ]

    comparison_df, short_period_cols, _ = build_comparison_table(compare_work, compare_mode)

    if comparison_df.empty:
        st.info("אין נתונים להשוואה תחת הסינון הנוכחי")
    else:
        total_row_mask = comparison_df.astype(str).eq("סה\"כ").any(axis=1)
        total_row = comparison_df[total_row_mask].copy()
        base_rows = comparison_df[~total_row_mask].copy()

        paged_df, current_page, total_pages, total_rows = paginate_df(base_rows, "compare_page", PAGE_SIZE)
        display_df = pd.concat([paged_df, total_row], ignore_index=True) if not total_row.empty else paged_df

        st.caption(f"מציג {min(len(paged_df), PAGE_SIZE)} מתוך {len(base_rows)} תוצאות, דף {current_page} מתוך {total_pages}")

        column_config = {}

        if "security_id" in display_df.columns:
            column_config["security_id"] = st.column_config.Column("מס' ני\"ע", width="small")
        if "security_name" in display_df.columns:
            column_config["security_name"] = st.column_config.Column("ני\"ע", width="small")
        if "sector" in display_df.columns:
            column_config["sector"] = st.column_config.Column("ענף", width="small")
        if "security_type" in display_df.columns:
            column_config["security_type"] = st.column_config.Column("סוג נייר", width="small")

        for col in short_period_cols:
            if col in display_df.columns:
                column_config[col] = st.column_config.NumberColumn(col, width="small", format="%d")

        if "סה\"כ" in display_df.columns:
            column_config['סה"כ'] = st.column_config.NumberColumn('סה"כ', width="small", format="%d")

        if "טווח שינוי" in display_df.columns:
            column_config["טווח שינוי"] = st.column_config.NumberColumn("טווח", width="small", format="%d")

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
        )

        nav1, nav2, nav3 = st.columns([1, 2, 1])

        with nav1:
            if st.button("הקודם", disabled=current_page <= 1, use_container_width=True):
                st.session_state.compare_page = max(1, st.session_state.compare_page - 1)
                st.rerun()

        with nav2:
            st.markdown(
                f"<div style='text-align:center;padding-top:8px;'>דף {current_page} / {total_pages}</div>",
                unsafe_allow_html=True,
            )

        with nav3:
            if st.button("הבא", disabled=current_page >= total_pages, use_container_width=True):
                st.session_state.compare_page = min(total_pages, st.session_state.compare_page + 1)
                st.rerun()

        st.divider()
        st.subheader("ייצוא טבלת השוואה")

        cmp_cols = st.columns(2)

        with cmp_cols[0]:
            if st.button("הכן CSV של ההשוואה", use_container_width=True):
                prep_download_file(
                    key="compare_csv",
                    data=to_csv_bytes(comparison_df),
                    file_name="comparison_by_period.csv",
                    mime="text/csv",
                )

        with cmp_cols[1]:
            if st.button("הכן Excel של ההשוואה", use_container_width=True):
                prep_download_file(
                    key="compare_xlsx",
                    data=to_excel_bytes(comparison_df, sheet_name="comparison"),
                    file_name="comparison_by_period.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        if st.session_state.downloads.get("compare_csv", {}).get("ready") or st.session_state.downloads.get("compare_xlsx", {}).get("ready"):
            cmp_download_cols = st.columns(2)

            if st.session_state.downloads.get("compare_csv", {}).get("ready"):
                with cmp_download_cols[0]:
                    st.download_button(
                        label="הורד CSV של ההשוואה",
                        data=st.session_state.downloads["compare_csv"]["data"],
                        file_name=st.session_state.downloads["compare_csv"]["file_name"],
                        mime=st.session_state.downloads["compare_csv"]["mime"],
                        on_click="ignore",
                        use_container_width=True,
                    )

            if st.session_state.downloads.get("compare_xlsx", {}).get("ready"):
                with cmp_download_cols[1]:
                    st.download_button(
                        label="הורד Excel של ההשוואה",
                        data=st.session_state.downloads["compare_xlsx"]["data"],
                        file_name=st.session_state.downloads["compare_xlsx"]["file_name"],
                        mime=st.session_state.downloads["compare_xlsx"]["mime"],
                        on_click="ignore",
                        use_container_width=True,
                    )