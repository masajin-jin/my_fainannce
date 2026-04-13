import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import sqlite3
import feedparser
import datetime
from pathlib import Path
from urllib.parse import quote

# ══════════════════════════════════════════════
# DB
# ══════════════════════════════════════════════
DB_PATH = Path("stocks.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                name   TEXT NOT NULL UNIQUE,
                ticker TEXT NOT NULL UNIQUE
            )
        """)
        conn.executemany(
            "INSERT OR IGNORE INTO stocks (name, ticker) VALUES (?, ?)",
            [
                ("イオン (8267)",        "8267.T"),
                ("ソニーグループ (6758)", "6758.T"),
            ],
        )

def load_stocks() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT name, ticker FROM stocks ORDER BY name").fetchall()
    return {row["name"]: row["ticker"] for row in rows}

def add_stock(name: str, ticker: str):
    with get_conn() as conn:
        conn.execute("INSERT INTO stocks (name, ticker) VALUES (?, ?)", (name, ticker))

def delete_stock(name: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM stocks WHERE name = ?", (name,))

# ══════════════════════════════════════════════
# ヘルパー
# ══════════════════════════════════════════════
def fmt_large(val):
    if val is None:
        return "—"
    try:
        val = float(val)
    except (TypeError, ValueError):
        return "—"
    if val >= 1_000_000_000_000:
        return f"{val / 1_000_000_000_000:.2f} 兆円"
    if val >= 100_000_000:
        return f"{val / 100_000_000:.0f} 億円"
    return f"{val:,.0f}"

def fmt_pct(val):
    if val is None:
        return "—"
    try:
        return f"{float(val) * 100:.2f} %"
    except (TypeError, ValueError):
        return "—"

def fmt_float(val, decimals=2):
    if val is None:
        return "—"
    try:
        return f"{float(val):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"

def parse_date_jst(entry) -> str:
    if not entry.get("published"):
        return ""
    try:
        dt = datetime.datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %Z")
        return (dt + datetime.timedelta(hours=9)).strftime("%Y/%m/%d %H:%M")
    except ValueError:
        return entry.published[:10]

# ══════════════════════════════════════════════
# ページ設定
# ══════════════════════════════════════════════
st.set_page_config(page_title="マイ株価ダッシュボード", layout="wide")

init_db()

# ══════════════════════════════════════════════
# サイドバー
# ══════════════════════════════════════════════
st.sidebar.header("⚙️ 設定")

dark_mode = st.sidebar.toggle("🌙 ダークモード", value=False)

if dark_mode:
    st.markdown("""
    <style>
        .stApp, [data-testid="stAppViewContainer"] { background-color: #0e1117 !important; }
        html, body, [class*="css"], .stMarkdown, .stMetric, label,
        .stSelectbox, .stTextInput, p, h1, h2, h3, h4, span, div
            { color: #e0e0e0 !important; }
        [data-testid="stSidebar"] { background-color: #161b22 !important; }
        [data-testid="stMetric"] { background-color: #1c2128 !important;
                                   border-radius: 8px; padding: 8px; }
        .stTextInput input, .stSelectbox select
            { background-color: #1c2128 !important; color: #e0e0e0 !important; }
        [data-testid="stDataFrame"] { background-color: #1c2128 !important; }
        .stButton > button { background-color: #238636 !important;
                             color: #fff !important; border: none !important; }
        hr { border-color: #30363d !important; }
    </style>
    """, unsafe_allow_html=True)

stock_dict = load_stocks()

page = st.sidebar.radio(
    "ページ",
    ["📊 サマリー", "🔍 銘柄詳細"],
    label_visibility="collapsed",
)

selected_stock_name = None
period_option = "1y"

if page == "🔍 銘柄詳細":
    if stock_dict:
        selected_stock_name = st.sidebar.selectbox("銘柄を選択", list(stock_dict.keys()))
    else:
        st.sidebar.info("銘柄が登録されていません。以下から追加してください。")
    period_option = st.sidebar.selectbox(
        "期間", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=3
    )

st.sidebar.divider()
st.sidebar.subheader("➕ 銘柄を追加")
new_name   = st.sidebar.text_input("表示名", placeholder="例: トヨタ自動車 (7203)")
new_ticker = st.sidebar.text_input("ティッカー", placeholder="例: 7203.T")

if st.sidebar.button("追加", use_container_width=True):
    if not new_name or not new_ticker:
        st.sidebar.warning("表示名とティッカーを両方入力してください。")
    elif new_name in stock_dict:
        st.sidebar.warning("同じ表示名がすでに登録されています。")
    else:
        try:
            add_stock(new_name.strip(), new_ticker.strip())
            st.sidebar.success(f"「{new_name}」を追加しました。")
            st.rerun()
        except sqlite3.IntegrityError:
            st.sidebar.error("そのティッカーはすでに登録されています。")

if stock_dict:
    st.sidebar.divider()
    st.sidebar.subheader("🗑️ 銘柄を削除")
    del_target = st.sidebar.selectbox("削除する銘柄", list(stock_dict.keys()), key="del_select")
    if st.sidebar.button("削除", use_container_width=True, type="primary"):
        delete_stock(del_target)
        st.sidebar.success(f"「{del_target}」を削除しました。")
        st.rerun()

# ══════════════════════════════════════════════
# ページ：サマリーダッシュボード
# ══════════════════════════════════════════════
if page == "📊 サマリー":
    st.title("📊 サマリーダッシュボード")

    if not stock_dict:
        st.info("銘柄が登録されていません。サイドバーから追加してください。")
        st.stop()

    rows = []
    progress = st.progress(0, text="株価データを取得中...")
    total = len(stock_dict)

    for i, (name, ticker) in enumerate(stock_dict.items()):
        progress.progress((i + 1) / total, text=f"{name} を取得中...")
        try:
            info = yf.Ticker(ticker).info
            current = info.get("currentPrice") or info.get("regularMarketPrice")
            prev    = info.get("previousClose")
            if current and prev:
                diff     = current - prev
                diff_pct = diff / prev * 100
                arrow    = "▲" if diff >= 0 else "▼"
                diff_str = f"{arrow} {abs(diff):,.1f} ({abs(diff_pct):.2f}%)"
            else:
                diff_str = "—"

            rows.append({
                "銘柄":       name,
                "現在値 (円)": f"{current:,.1f}" if current else "—",
                "前日比":      diff_str,
                "時価総額":    fmt_large(info.get("marketCap")),
                "PER":         fmt_float(info.get("trailingPE")),
                "PBR":         fmt_float(info.get("priceToBook")),
                "配当利回り":  fmt_pct(info.get("dividendYield")),
            })
        except Exception:
            rows.append({"銘柄": name, "現在値 (円)": "取得失敗",
                         "前日比": "—", "時価総額": "—",
                         "PER": "—", "PBR": "—", "配当利回り": "—"})

    progress.empty()
    df = pd.DataFrame(rows).set_index("銘柄")

    def color_diff(val):
        if "▲" in str(val):
            return "color: #2ea043"
        if "▼" in str(val):
            return "color: #f85149"
        return ""

    st.dataframe(
        df.style.map(color_diff, subset=["前日比"]),
        use_container_width=True,
        height=min(80 + 40 * len(rows), 600),
    )
    st.caption(f"最終更新: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    st.stop()

# ══════════════════════════════════════════════
# ページ：銘柄詳細
# ══════════════════════════════════════════════
st.title("🔍 銘柄詳細")

if not selected_stock_name:
    st.info("サイドバーから銘柄を追加してください。")
    st.stop()

ticker_symbol = stock_dict[selected_stock_name]
ticker_obj    = yf.Ticker(ticker_symbol)

with st.spinner("データを取得中..."):
    hist = ticker_obj.history(period=period_option)
    info = ticker_obj.info

if hist.empty:
    st.error("データの取得に失敗しました。ティッカーシンボルを確認してください。")
    st.stop()

if isinstance(hist.columns, pd.MultiIndex):
    hist.columns = hist.columns.get_level_values(0)

close_prices = hist["Close"]

col_chart, col_news = st.columns([2, 1])

with col_chart:
    st.subheader(f"{selected_stock_name} 株価推移")

    last_price     = float(close_prices.iloc[-1])
    prev_price     = float(close_prices.iloc[-2])
    price_diff     = last_price - prev_price
    price_diff_pct = price_diff / prev_price * 100

    st.metric(
        label="最新終値",
        value=f"{last_price:,.1f} 円",
        delta=f"{price_diff:,.1f} 円 ({price_diff_pct:.2f}%)",
    )
    st.line_chart(close_prices)

    # ── ファンダメンタル指標 ──
    st.subheader("📋 ファンダメンタル指標")

    earnings_ts = info.get("earningsTimestamp")
    earnings_dt = (
        datetime.datetime.fromtimestamp(earnings_ts).strftime("%Y/%m/%d")
        if earnings_ts else "—"
    )

    fund_data = {
        "時価総額":       fmt_large(info.get("marketCap")),
        "PER (実績)":     fmt_float(info.get("trailingPE")),
        "PER (予想)":     fmt_float(info.get("forwardPE")),
        "PBR":            fmt_float(info.get("priceToBook")),
        "EPS (実績)":     fmt_float(info.get("trailingEps"), 1),
        "ROE":            fmt_pct(info.get("returnOnEquity")),
        "配当利回り":     fmt_pct(info.get("dividendYield")),
        "年間配当額":     (fmt_float(info.get("dividendRate"), 1) + " 円") if info.get("dividendRate") else "—",
        "次回権利確定日": str(info.get("exDividendDate", "—")),
        "次回決算日":     earnings_dt,
        "52週高値":       fmt_float(info.get("fiftyTwoWeekHigh"), 1) + " 円",
        "52週安値":       fmt_float(info.get("fiftyTwoWeekLow"),  1) + " 円",
        "業種":           info.get("industry", "—"),
        "セクター":       info.get("sector", "—"),
    }

    keys   = list(fund_data.keys())
    values = list(fund_data.values())
    mid    = (len(keys) + 1) // 2
    fc1, fc2 = st.columns(2)
    with fc1:
        for k, v in zip(keys[:mid], values[:mid]):
            st.metric(label=k, value=v)
    with fc2:
        for k, v in zip(keys[mid:], values[mid:]):
            st.metric(label=k, value=v)

    # ── 会社HP ──
    st.subheader("🌐 会社HP")
    company_url = info.get("website")
    if company_url:
        st.markdown(f"🔗 [{company_url}]({company_url})")
        components.iframe(company_url, height=450, scrolling=True)
        st.caption("⚠️ サイト側の設定により表示できない場合があります。")
    else:
        st.info("会社HPの情報が取得できませんでした。")

with col_news:
    st.subheader("📰 最新ニュース")

    search_query  = selected_stock_name.replace("(", "").replace(")", "")
    encoded_query = quote(search_query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"

    with st.spinner("ニュースを取得中..."):
        feed = feedparser.parse(rss_url)

    if feed.entries:
        with st.container(height=1100):
            for entry in feed.entries:
                title  = entry.get("title", "タイトルなし")
                link   = entry.get("link", "#")
                source = entry.get("source", {}).get("title", "不明なソース")
                st.markdown(f"**[{title}]({link})**")
                st.caption(f"📅 {parse_date_jst(entry)} | 📢 {source}")
                st.divider()
    else:
        st.write("現在、表示できるニュースはありません。")