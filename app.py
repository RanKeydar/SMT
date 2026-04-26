import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="תנועות בניירות ערך", page_icon="📈", layout="wide")

SHEET_NAME = "הכל"
REQUIRED_HEADERS = ['סוג נייר','ענף','מספר נייר ערך','נייר ערך','סוג לקוח','תת סוג לקוח']
COLUMN_DEFS = [
    ('פנסיה/גמל/ביטוח', ['קרן פנסיה/קופת גמל/חברת ביטוח']),
    ('מנהל תיקים', ['מנהל תיקים/לקוח מנוהל על ידי מנהל תיקים']),
    ('קרן סל', ['קרן סל/עושה שוק בקרן סל']),
    ('ישראלי - יחיד', ['ישראלי - יחיד']),
    ('ישראלי - תאגיד', ['ישראלי - תאגיד']),
    ('ישראלי - מאוחד', ['ישראלי - יחיד', 'ישראלי - תאגיד', 'ישראלי - אחר']),
    ('קרן נאמנות', ['משקיע מוסדי מסוג קרן נאמנות']),
    ('נוסטרו', ['נוסטרו']),
    ('תושב חוץ', ['משקיע חוץ'])
]

st.markdown("""
<style>
html, body, [class*="css"] { direction: rtl; }
body, p, div, label, span, h1, h2, h3 { text-align: right !important; }
.block-container { padding-top: 1.25rem; padding-bottom: 2rem; }
h1, h2, h3 { direction: rtl; unicode-bidi: plaintext; }
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div { text-align: right; direction: rtl; border-radius: 12px; }
div[data-testid="stFileUploader"] section { border-radius: 16px; }
.summary-head, .summary-values { display:grid; grid-template-columns: repeat(9, minmax(110px,1fr)); gap:14px; }
.summary-head { margin-top:10px; margin-bottom:10px; }
.header-cell button { width:100%; border:1px solid #cbd5e1; border-radius:10px; background:#fff; color:#0f172a; font-weight:700; min-height:44px; }
.header-cell button:hover { border-color:#94a3b8; color:#0f4c81; }
.value-box { padding:14px 10px; border:1px solid #cbd5e1; text-align:center !important; font-weight:700; }
.pos { background:#d9f2d9; color:#116329; }
.neg { background:#f7d6d9; color:#a61b29; }
.zero { background:#f8fafc; color:#334155; }
.result-title { font-size:1.45rem; font-weight:800; margin:1rem 0 0.25rem; }
.period-text { font-size:0.95rem; color:#475569; margin-bottom:0.75rem; }
.detail-title { margin-top:24px; margin-bottom:10px; }
.detail-html table { width:100%; border-collapse:collapse; direction:rtl; table-layout:auto; }
.detail-html th { background:#eef2f7; color:#111827; border:1px solid #d1d5db; padding:10px; text-align:right !important; white-space:nowrap; }
.detail-html td { border:1px solid #d1d5db; padding:10px; text-align:right !important; white-space:nowrap; }
.detail-html .num { text-align:right !important; direction:ltr; font-variant-numeric: tabular-nums; }
.detail-html .num.pos { background:#d9f2d9; color:#116329; }
.detail-html .num.neg { background:#f7d6d9; color:#a61b29; }
.detail-html .num.zero { background:#f8fafc; color:#334155; }
@media (max-width: 1200px) {
  .summary-head, .summary-values { grid-template-columns: repeat(3, minmax(110px,1fr)); }
}
</style>
""", unsafe_allow_html=True)


def find_header_row(raw, required_headers, scan_rows=12):
    limit = min(scan_rows, len(raw))
    best_idx, best_score = None, -1
    for i in range(limit):
        row_vals = set(raw.iloc[i].fillna('').astype(str).str.strip().tolist())
        score = sum(1 for h in required_headers if h in row_vals)
        if score > best_score:
            best_idx, best_score = i, score
    return best_idx, best_score


@st.cache_data
def load_excel(file_bytes):
    bio = BytesIO(file_bytes)
    raw = pd.read_excel(bio, sheet_name=SHEET_NAME, header=None)
    title_text = str(raw.iloc[0,0]).strip() if len(raw) > 0 else ''
    header_row, score = find_header_row(raw, REQUIRED_HEADERS)
    if header_row is None or score < 4:
        raise ValueError('לא הצלחתי לזהות אוטומטית את שורת הכותרות בלשונית "הכל"')

    headers = raw.iloc[header_row].fillna('').astype(str).str.strip().tolist()
    df = raw.iloc[header_row + 1:].copy()
    df.columns = headers
    df = df.loc[:, [c for c in df.columns if str(c).strip() and not str(c).startswith('Unnamed:')]]
    df = df.rename(columns={
        'נייר ערך': 'security_name',
        'מספר נייר ערך': 'security_id',
        'סוג נייר': 'security_type',
        'ענף': 'sector',
        'סוג לקוח': 'client_type',
        'תת סוג לקוח': 'client_subtype',
        'מחזור כספי - קונה': 'buy',
        'מחזור כספי - מוכר': 'sell',
        'מחזור כספי - נטו': 'net',
        'מחזור כספי - כולל': 'total'
    })

    needed = ['security_name','security_id','security_type','sector','client_type','client_subtype','buy','sell','net','total']
    for c in needed:
        if c not in df.columns:
            df[c] = None

    for c in ['buy','sell','net','total']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    for c in ['security_name','security_id','security_type','sector','client_type','client_subtype']:
        df[c] = df[c].astype(str).str.strip()

    df = df[df['security_name'].notna() & (df['security_name'] != '') & (df['security_name'] != 'nan')]
    df = df[df['security_id'].notna() & (df['security_id'] != '') & (df['security_id'] != 'nan')]

    def normalize_group(row):
        ct = row['client_type']
        sub = row['client_subtype']
        if ct == 'משקיע ישראלי':
            if 'יחיד' in sub:
                return 'ישראלי - יחיד'
            if 'תאגיד' in sub:
                return 'ישראלי - תאגיד'
            return 'ישראלי - אחר'
        if ct == 'תושב חוץ':
            return 'משקיע חוץ'
        return ct

    df['display_group'] = df.apply(normalize_group, axis=1)
    return df, title_text


def format_num(x):
    return f"{x:,.0f}"


def class_for_value(v):
    return 'pos' if v > 0 else 'neg' if v < 0 else 'zero'


def build_summary_values(selected):
    sums = selected.groupby('display_group', as_index=False)['net'].sum()
    mapping = dict(zip(sums['display_group'], sums['net']))
    row = []
    for label, keys in COLUMN_DEFS:
        val = sum(mapping.get(k, 0) for k in keys)
        row.append((label, keys, val))
    return row


def aggregate_view(work, group_label):
    sums = work.groupby('display_group', as_index=False)['net'].sum()
    mapping = dict(zip(sums['display_group'], sums['net']))
    return group_label, [(label, keys, sum(mapping.get(k, 0) for k in keys)) for label, keys in COLUMN_DEFS]


def detail_table(selected, groups):
    rows = selected[selected['display_group'].isin(groups)].copy()
    if rows.empty:
        return None
    out = rows.groupby(['client_type','client_subtype'], as_index=False)[['buy','sell','net','total']].sum()
    out = out.rename(columns={
        'client_type':'סוג לקוח',
        'client_subtype':'תת סוג לקוח',
        'buy':'קונה',
        'sell':'מוכר',
        'net':'נטו',
        'total':'כולל'
    })
    return out


def render_detail_html(df):
    cols = ['סוג לקוח','תת סוג לקוח','קונה','מוכר','נטו','כולל']
    html = '<div class="detail-html"><table><thead><tr>'
    for c in cols:
        html += f'<th>{c}</th>'
    html += '</tr></thead><tbody>'
    for _, r in df.iterrows():
        html += '<tr>'
        html += f'<td>{r["סוג לקוח"]}</td>'
        html += f'<td>{r["תת סוג לקוח"]}</td>'
        html += f'<td class="num {class_for_value(r["קונה"])}">{format_num(r["קונה"])}</td>'
        html += f'<td class="num {class_for_value(r["מוכר"])}">{format_num(r["מוכר"])}</td>'
        html += f'<td class="num {class_for_value(r["נטו"])}">{format_num(r["נטו"])}</td>'
        html += f'<td class="num {class_for_value(r["כולל"])}">{format_num(r["כולל"])}</td>'
        html += '</tr>'
    html += '</tbody></table></div>'
    return html


st.title('תנועות בניירות ערך')
st.caption('חיפוש פשוט לפי נייר ערך והצגת חלוקה לפי חיתוכי משקיעים')

if 'detail_groups' not in st.session_state:
    st.session_state.detail_groups = None

with st.sidebar:
    st.header('טעינת נתונים')
    uploaded = st.file_uploader('העלה קובץ XLSX', type=['xlsx'])

if not uploaded:
    st.info('העלה קובץ XLSX כדי להתחיל לעבוד')
    st.stop()

try:
    df, title_text = load_excel(uploaded.getvalue())
except Exception as e:
    st.error(str(e))
    st.stop()

c1, c2, c3 = st.columns([2,1,1])
with c1:
    query = st.text_input('חיפוש לפי שם נייר או מספר נייר', value='')
view_mode = st.radio('אופן תצוגה', ['לפי נייר ערך', 'לפי ענף', 'לפי סוג נייר'], horizontal=True)
with c2:
    sector_filter = st.selectbox('ענף', ['הכל'] + sorted([x for x in df['sector'].dropna().unique().tolist() if x and x != 'nan']))
with c3:
    sec_type_filter = st.selectbox('סוג נייר', ['הכל'] + sorted([x for x in df['security_type'].dropna().unique().tolist() if x and x != 'nan']))

work = df.copy()
if sector_filter != 'הכל':
    work = work[work['sector'] == sector_filter]
if sec_type_filter != 'הכל':
    work = work[work['security_type'] == sec_type_filter]

selected = None
summary = None
security_label = ''

if view_mode == 'לפי נייר ערך':
    if not query.strip():
        st.session_state.detail_groups = None
        st.info('הקלד שם נייר או מספר נייר כדי להציג נתונים')
        st.stop()
    q = query.strip()
    exact_id = work[work['security_id'] == q]
    exact_name = work[work['security_name'] == q]
    if not exact_id.empty:
        matched = exact_id
    elif not exact_name.empty:
        matched = exact_name
    else:
        matched = work[
            work['security_name'].str.contains(q, case=False, na=False) |
            work['security_id'].str.contains(q, case=False, na=False)
        ]
    if matched.empty:
        st.session_state.detail_groups = None
        st.warning('לא נמצאו תוצאות לפי הסינון הנוכחי')
        st.stop()
    matches = matched[['security_name','security_id']].drop_duplicates().sort_values(['security_name','security_id'])
    if len(matches) > 1:
        st.session_state.detail_groups = None
        st.warning('נמצאו כמה תוצאות. דייק את החיפוש:')
        for _, row in matches.head(20).iterrows():
            st.write(f"- {row['security_name']} | {row['security_id']}")
        st.stop()
    security_id = matches.iloc[0]['security_id']
    selected = matched[matched['security_id'] == security_id].copy()
    security_label = selected.iloc[0]['security_name']
    summary = build_summary_values(selected)
elif view_mode == 'לפי ענף':
    if sector_filter == 'הכל':
        st.session_state.detail_groups = None
        st.info('בחר ענף כדי להציג פלט לפי ענף')
        st.stop()
    selected = work.copy()
    security_label = f'ענף: {sector_filter}'
    summary = build_summary_values(selected)
else:
    if sec_type_filter == 'הכל':
        st.session_state.detail_groups = None
        st.info('בחר סוג נייר כדי להציג פלט לפי סוג נייר')
        st.stop()
    selected = work.copy()
    security_label = f'סוג נייר: {sec_type_filter}'
    summary = build_summary_values(selected)

st.markdown(f'<div class="result-title">{security_label}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="period-text">תקופת הנתונים: {title_text}</div>', unsafe_allow_html=True)

head_cols = st.columns(len(summary))
for i, (label, groups, val) in enumerate(summary):
    with head_cols[i]:
        if st.button(label, key=f'btn_{i}', use_container_width=True):
            st.session_state.detail_groups = groups

value_cols = st.columns(len(summary))
for i, (_, groups, val) in enumerate(summary):
    with value_cols[i]:
        st.markdown(f'<div class="value-box {class_for_value(val)}">{format_num(val)}</div>', unsafe_allow_html=True)

if st.session_state.detail_groups:
    details = detail_table(selected, st.session_state.detail_groups)
    if details is not None:
        st.markdown('<div class="detail-title"><h3>תנועות לחיתוך שנבחר</h3></div>', unsafe_allow_html=True)
        st.markdown(render_detail_html(details), unsafe_allow_html=True)
