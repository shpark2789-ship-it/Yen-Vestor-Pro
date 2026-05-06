import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime
import json

# [필수] Streamlit 페이지 설정은 반드시 최상단에 위치해야 합니다.
st.set_page_config(page_title="엔화 투자 마스터", page_icon="💴", layout="wide")

# yfinance 및 GCP 임포트 (만약 설치 안 되어 있어도 앱이 뻗지 않도록 처리)
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    HAS_GCP = True
except ImportError:
    HAS_GCP = False

# --- CSS로 디자인 다듬기 ---
st.markdown("""
    <style>
    .metric-card {
        background-color: #1e293b;
        border-radius: 10px;
        padding: 20px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .metric-title { color: #94a3b8; font-size: 14px; font-weight: bold; margin-bottom: 5px; }
    .metric-value { color: white; font-size: 28px; font-weight: 900; margin-bottom: 5px; }
    .metric-status { font-size: 13px; font-weight: bold; }
    
    /* 라디오 버튼 스타일 다듬기 */
    div.row-widget.stRadio > div {
        flex-direction: row;
        justify-content: center;
        background-color: #1e293b;
        padding: 10px;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- ☁️ GCP Firestore 데이터베이스 연동 엔진 ---
@st.cache_resource
def get_db():
    if HAS_GCP and "GCP_JSON" in st.secrets:
        try:
            key_dict = json.loads(st.secrets["GCP_JSON"])
            creds = service_account.Credentials.from_service_account_info(key_dict)
            db = firestore.Client(credentials=creds, project=key_dict["project_id"])
            return db
        except Exception as e:
            st.sidebar.error(f"GCP 인증 에러: {e}")
    return None

def load_portfolio():
    db = get_db()
    if db is not None:
        try:
            trades = []
            docs = db.collection('yen_portfolio').stream()
            for doc in docs:
                trades.append(doc.to_dict())
            if trades:
                return sorted(trades, key=lambda x: x['id'])
            return []
        except Exception as e:
            st.sidebar.error(f"클라우드 로딩 에러: {e}")
    return [{'id': 1, 'date': '2025-10-15', 'type': 'buy', 'amount_jpy': 500000, 'rate': 905.20}]

def add_trade_to_db(trade):
    db = get_db()
    if db is not None:
        try:
            db.collection('yen_portfolio').document(str(trade['id'])).set(trade)
        except Exception as e:
            st.sidebar.error(f"클라우드 저장 에러: {e}")

def delete_trade_from_db(trade_id):
    db = get_db()
    if db is not None:
        try:
            db.collection('yen_portfolio').document(str(trade_id)).delete()
        except Exception as e:
            st.sidebar.error(f"클라우드 삭제 에러: {e}")

# --- 지표별 의미 해석기 ---
def get_krw_status(val):
    if val <= 880: return "🟢 강력 매수 (매우 쌈)", "#10b981"
    elif val <= 910: return "🔵 분할 매수 (저평가)", "#3b82f6"
    elif val >= 950: return "🔴 매도 권장 (고평가)", "#ef4444"
    else: return "⚪ 박스권 (관망)", "#94a3b8"

def get_usd_status(val):
    if val >= 150: return "🟢 BOJ 개입 임박 (매수)", "#10b981"
    elif val <= 140: return "🔴 엔화 이미 강세", "#ef4444"
    else: return "⚪ 일반적인 흐름", "#94a3b8"

def get_yield_status(val):
    if val >= 4.5: return "🔴 달러 강세 (엔약세)", "#ef4444"
    elif val <= 4.0: return "🟢 금리 인하 (엔강세)", "#10b981"
    else: return "⚪ 방향성 탐색중", "#94a3b8"

def get_vix_status(val):
    if val >= 25: return "🔴 패닉장 (단기 폭등)", "#ef4444"
    elif val >= 20: return "🟡 경계장 (수요 쏠림)", "#f59e0b"
    else: return "🟢 평온장 (매집 시기)", "#10b981"

# --- 🕯️ AI 캔들 및 패턴 분석 엔진 ---
def analyze_candles(df):
    if len(df) < 3: return ["데이터가 부족하여 캔들 패턴을 분석할 수 없습니다."]
    last = df.iloc[-1]
    prev = df.iloc[-2]
    body_size = abs(last['Close'] - last['Open'])
    total_size = last['High'] - last['Low']
    upper_shadow = last['High'] - max(last['Open'], last['Close'])
    lower_shadow = min(last['Open'], last['Close']) - last['Low']
    trend = "상승" if df['MA20'].iloc[-1] > df['MA20'].iloc[-2] else "하락"
    patterns = []
    if total_size > 0 and body_size <= total_size * 0.1:
        patterns.append("🔹 **도지형(Doji) 출현**: 매수세와 매도세가 팽팽하게 맞서고 있습니다. 곧 추세가 크게 반전될 가능성이 있습니다.")
    if prev['Close'] < prev['Open'] and last['Close'] > last['Open'] and last['Open'] <= prev['Close'] and last['Close'] >= prev['Open']:
        patterns.append("🚀 **상승 장악형(Bullish Engulfing)**: 강력한 매수세가 들어왔습니다. **상승 반전 가능성**이 높습니다.")
    if prev['Close'] > prev['Open'] and last['Close'] < last['Open'] and last['Open'] >= prev['Close'] and last['Close'] <= prev['Open']:
        patterns.append("⚠️ **하락 장악형(Bearish Engulfing)**: 강력한 매도세가 출현했습니다. **하락에 주의**하세요.")
    if total_size > 0 and lower_shadow > body_size * 2 and upper_shadow < total_size * 0.1:
        if trend == "하락": patterns.append("🔨 **망치형(Hammer)**: 하락 중 강한 매수세 유입. **단기 바닥**일 확률이 높습니다.")
        else: patterns.append("➰ **교수형(Hanging Man)**: 고점에서 나타난 긴 아래꼬리. 단기 고점 징후일 수 있습니다.")
    if not patterns:
        patterns.append(f"현재 뚜렷한 반전 패턴은 보이지 않으며, 기존의 **{trend} 추세**를 이어가고 있습니다.")
    return patterns

# --- 🛡️ 방탄 데이터 로더 ---
@st.cache_data(ttl=60, show_spinner=False) 
def fetch_global_data(period="1y", interval="1d"):
    if not HAS_YFINANCE: return _generate_fallback_data()
    try:
        macro_us_yield = yf.Ticker("^TNX").history(period="5d", interval="1d")['Close']
        macro_vix = yf.Ticker("^VIX").history(period="5d", interval="1d")['Close']
        macro_usd_jpy = yf.Ticker("JPY=X").history(period="5d", interval="1d")['Close']
        krw_history = yf.Ticker("KRW=X").history(period=period, interval=interval)
        jpy_history = yf.Ticker("JPY=X").history(period=period, interval=interval)
        if krw_history.empty or jpy_history.empty or macro_us_yield.empty: return _generate_fallback_data()
        df_krw, df_jpy = krw_history.align(jpy_history, join='inner')
        df = pd.DataFrame(index=df_krw.index)
        df['Open'] = (df_krw['Open'] / df_jpy['Open']) * 100
        df['High'] = (df_krw['High'] / df_jpy['Low']) * 100 
        df['Low'] = (df_krw['Low'] / df_jpy['High']) * 100 
        df['Close'] = (df_krw['Close'] / df_jpy['Close']) * 100
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['STD20'] = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
        df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean(); avg_loss = loss.rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (avg_gain / avg_loss)))
        df.dropna(inplace=True)
        latest = {
            'krw_jpy': df['Close'].iloc[-1], 'usd_jpy': macro_usd_jpy.iloc[-1],
            'us_yield': macro_us_yield.iloc[-1], 'vix': macro_vix.iloc[-1],
            'rsi': df['RSI'].iloc[-1], 'bb_lower': df['BB_Lower'].iloc[-1],
            'bb_upper': df['BB_Upper'].iloc[-1], 'ma20': df['MA20'].iloc[-1]
        }
        return df, latest, True 
    except: return _generate_fallback_data()

def _generate_fallback_data():
    dates = pd.date_range(end=datetime.now(), periods=100)
    np.random.seed(42); walk = np.random.normal(0, 1.5, 100).cumsum()
    df = pd.DataFrame({'Close': 880 + walk}, index=dates)
    df['Open'] = df['Close'] - 2; df['High'] = df['Close'] + 2; df['Low'] = df['Open'] - 2
    df['MA20'] = df['Close'].rolling(20).mean(); df['BB_Upper'] = df['MA20'] + 10; df['BB_Lower'] = df['MA20'] - 10
    df['RSI'] = 50; df.dropna(inplace=True)
    latest = { 'krw_jpy': 885.0, 'usd_jpy': 150.0, 'us_yield': 4.3, 'vix': 15.0, 'rsi': 50, 'bb_lower': 870, 'bb_upper': 900, 'ma20': 885 }
    return df, latest, False

# --- 메인 화면 시작 ---
with st.sidebar:
    if get_db() is not None: st.success("☁️ GCP 클라우드 DB 연동 완료")
    else: st.warning("⚠️ 임시 메모리 모드 (GCP 연동 필요)")

st.title("💴 Yen-Vestor Pro (실시간 웹 대시보드)")
st.markdown("전 세계 금융 API와 연동된 **가장 완벽한 엔화 투자 AI 시뮬레이터**입니다.")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()

timeframe_map = {
    "30분": {"period": "1mo", "interval": "30m"}, "1시간": {"period": "3mo", "interval": "1h"},
    "일봉": {"period": "1y", "interval": "1d"}, "주봉": {"period": "3y", "interval": "1wk"},
    "월봉": {"period": "10y", "interval": "1mo"}, "분기봉": {"period": "20y", "interval": "3mo"}
}

with st.spinner("금융 데이터를 동기화 중입니다..."):
    df, latest, is_live = fetch_global_data()

tab1, tab2, tab3 = st.tabs(["📊 AI 대시보드", "💼 내 자산 관리", "📖 투자 전략"])

# ==========================================
# 탭 1: AI 대시보드
# ==========================================
with tab1:
    st.write("⏱️ **차트 시간 간격 설정**")
    selected_tf = st.radio("tf", options=list(timeframe_map.keys()), index=2, horizontal=True, label_visibility="collapsed")
    df_chart, latest_chart, _ = fetch_global_data(period=timeframe_map[selected_tf]["period"], interval=timeframe_map[selected_tf]["interval"])

    col1, col2, col3, col4 = st.columns(4)
    def r_card(col, title, value, unit, status_fn):
        txt, color = status_fn(value)
        col.markdown(f'<div class="metric-card"><div class="metric-title">{title}</div><div class="metric-value">{value:.2f}{unit}</div><div class="metric-status" style="color: {color};">{txt}</div></div>', unsafe_allow_html=True)
    r_card(col1, "💰 현재 환율(원/100엔)", latest_chart['krw_jpy'], "원", get_krw_status)
    r_card(col2, "💵 달러/엔 환율", latest_chart['usd_jpy'], "엔", get_usd_status)
    r_card(col3, "🇺🇸 미 국채 10년물", latest_chart['us_yield'], "%", get_yield_status)
    r_card(col4, "📉 VIX 공포지수", latest_chart['vix'], "", get_vix_status)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['BB_Upper'], line=dict(color='rgba(148, 163, 184, 0.5)', dash='dash'), name='볼린저 상단'))
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['BB_Lower'], line=dict(color='rgba(16, 185, 129, 0.5)', dash='dash'), fill='tonexty', fillcolor='rgba(203, 213, 225, 0.1)', name='볼린저 하단'))
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA20'], line=dict(color='#f59e0b', width=2), name='20선'))
    fig.add_trace(go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], increasing_line_color='#ef4444', increasing_fillcolor='#ef4444', decreasing_line_color='#3b82f6', decreasing_fillcolor='#3b82f6', name='캔들'))
    fig.add_hline(y=950, line_dash="dot", line_color="red", annotation_text="고평가 (매도)")
    fig.add_hline(y=900, line_dash="dot", line_color="green", annotation_text="저평가 (매수)")
    fig.update_layout(height=500, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='#f8fafc', paper_bgcolor='#f8fafc', xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 🕯️ AI 캔들 분석")
    for p in analyze_candles(df_chart): st.info(p)

# ==========================================
# 탭 2: 내 자산 관리 (성과 분석 및 수정 완료)
# ==========================================
with tab2:
    st.subheader("📊 투자 성과 및 수익률 분석")
    
    current_jpy = 0; current_principal = 0; realized_profit = 0; total_injected_krw = 0
    portfolio_records = []; performance_by_date = []
    
    sorted_trades = sorted(st.session_state.portfolio, key=lambda x: x['id'])
    for t in sorted_trades:
        amt = t['amount_jpy']; r = t['rate'] / 100; krw_val = amt * r; t_date = t['date']
        if t.get('type', 'buy') == 'buy':
            current_jpy += amt; current_principal += krw_val; total_injected_krw += krw_val
            portfolio_records.append({'ID': t['id'], '날짜': t_date, '구분': '🔴 매수', '엔화': f"¥ {amt:,.0f}", '환율': f"{t['rate']:.2f}", '한화': f"₩ {krw_val:,.0f}"})
        else:
            avg_cost = current_principal / current_jpy if current_jpy > 0 else 0
            trade_profit = krw_val - (amt * avg_cost); realized_profit += trade_profit
            current_jpy -= amt; current_principal -= (amt * avg_cost)
            portfolio_records.append({'ID': t['id'], '날짜': t_date, '구분': '🔵 매도', '엔화': f"¥ {amt:,.0f}", '환율': f"{t['rate']:.2f}", '한화': f"₩ {krw_val:,.0f}"})
        
        temp_unrealized = (current_jpy * (latest['krw_jpy'] / 100)) - current_principal
        performance_by_date.append({'date': t_date, 'cumulative_profit': realized_profit + temp_unrealized})

    cur_val_krw = current_jpy * (latest['krw_jpy'] / 100)
    unrealized = cur_val_krw - current_principal; total_p = realized_profit + unrealized
    total_roi = (total_p / total_injected_krw * 100) if total_injected_krw > 0 else 0
    avg_rate = (current_principal / current_jpy * 100) if current_jpy > 0 else 0

    st.markdown(f"""
    <div style="background-color: #0f172a; border: 2px solid {'#10b981' if total_p >= 0 else '#ef4444'}; border-radius: 12px; padding: 25px; text-align: center; margin-bottom: 25px;">
        <p style="color: #94a3b8; font-size: 16px; font-weight: bold;">🏆 기간 누적 최종 투자 성과</p>
        <h2 style="color: {'#10b981' if total_p >= 0 else '#ef4444'}; font-size: 42px; font-weight: 900;">
            {'+' if total_p > 0 else ''}{total_p:,.0f} 원 ({'+' if total_roi > 0 else ''}{total_roi:.2f}%)
        </h2>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("보유 잔고", f"¥ {current_jpy:,.0f}"); c2.metric("매수평단", f"{avg_rate:.2f}원")
    c3.metric("평가 손익", f"₩ {unrealized:,.0f}"); c4.metric("실현 수익", f"₩ {realized_profit:,.0f}")

    st.markdown("---")
    st.subheader("📅 월별 누적 성과 요약")
    if portfolio_records:
        df_temp = pd.DataFrame(sorted_trades)
        df_temp['date'] = pd.to_datetime(df_temp['date'])
        df_temp['Month'] = df_temp['date'].dt.strftime('%Y-%m')
        monthly_summary = []
        months = sorted(df_temp['Month'].unique())
        last_cum = 0
        for m in months:
            m_trades = df_temp[df_temp['Month'] == m]
            last_id = m_trades['id'].max()
            idx = [i for i, x in enumerate(sorted_trades) if x['id'] == last_id][0]
            current_m_profit = performance_by_date[idx]['cumulative_profit']
            monthly_summary.append({'기간': m, '누적 수익금': f"₩ {current_m_profit:,.0f}", '상태': "📈" if current_m_profit >= last_cum else "📉"})
            last_cum = current_m_profit
        st.table(pd.DataFrame(monthly_summary))

    st.markdown("---")
    st.subheader("📝 거래 내역 기록")
    with st.form("add_v2", clear_on_submit=True):
        f1, f2, f3, f4 = st.columns([1.5, 2, 2, 1.5])
        t_in = f1.radio("q", ["🔴 매수", "🔵 매도"], label_visibility="collapsed")
        amt_in = f2.number_input("수량(JPY)", min_value=0, step=10000)
        rate_in = f3.number_input("환율(원/100엔)", min_value=0.0, format="%.2f")
        if f4.form_submit_button("➕ 추가") and amt_in > 0:
            is_buy = "매수" in t_in
            if not is_buy and amt_in > current_jpy: st.error("잔고 부족!")
            else:
                new_t = {'id': int(time.time()*1000), 'date': datetime.now().strftime("%Y-%m-%d"), 'type': 'buy' if is_buy else 'sell', 'amount_jpy': amt_in, 'rate': rate_in}
                st.session_state.portfolio.append(new_t); add_trade_to_db(new_t); st.rerun()

    if portfolio_records:
        st.dataframe(pd.DataFrame(portfolio_records), use_container_width=True, hide_index=True)
        d1, d2, d3 = st.columns([2, 1, 1])
        del_id = d1.number_input("ID", min_value=0, step=1, label_visibility="collapsed")
        if d2.button("삭제", use_container_width=True):
            st.session_state.portfolio = [t for t in st.session_state.portfolio if t['id'] != del_id]
            delete_trade_from_db(del_id); st.rerun()
        csv = pd.DataFrame(portfolio_records).to_csv(index=False).encode('utf-8-sig')
        d3.download_button("💾 백업", data=csv, file_name="yen.csv", use_container_width=True)

# ==========================================
# 탭 3: 투자 전략 백과
# ==========================================
with tab3:
    st.header("성공하는 투자자들의 엔화 기법")
    with st.expander("1. 환율 밴드 기반 그리드 트레이딩", expanded=True):
        st.write("- 역사적 저점과 고점을 밴드로 설정하고 기계적으로 분할 매매하는 기법입니다.")
    with st.expander("2. 미·일 금리차 역추적"):
        st.write("- 미국 금리가 하락 반전할 때가 최고의 엔화 매수 타이밍입니다.")
    with st.expander("📈 기술적 지표 활용법"):
        st.write("- 볼린저 밴드 하단 터치 시 매수, 상단 터치 시 매도 확률이 높습니다.")
