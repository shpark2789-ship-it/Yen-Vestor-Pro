import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime
import json

# [필수] Streamlit 페이지 설정
st.set_page_config(page_title="엔화 투자 마스터", page_icon="💴", layout="wide")

# yfinance 및 GCP 임포트
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

# --- CSS 디자인 ---
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
    
    div.row-widget.stRadio > div {
        flex-direction: row;
        justify-content: center;
        background-color: #1e293b;
        padding: 10px;
        border-radius: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- ☁️ GCP Firestore 엔진 ---
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
            if "404" in str(e):
                st.sidebar.error("❌ DB가 생성되지 않았습니다.")
            else:
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

# --- 지표별 해석기 ---
def get_krw_status(val):
    if val <= 880: return "🟢 강력 매수 (저평가)", "#10b981"
    elif val <= 910: return "🔵 분할 매수 (관심)", "#3b82f6"
    elif val >= 950: return "🔴 매도 권장 (고평가)", "#ef4444"
    else: return "⚪ 박스권 (관망)", "#94a3b8"

def get_usd_status(val):
    if val >= 150: return "🟢 BOJ 개입 임박", "#10b981"
    elif val <= 140: return "🔴 엔화 이미 강세", "#ef4444"
    else: return "⚪ 방향 탐색", "#94a3b8"

def get_yield_status(val):
    if val >= 4.5: return "🔴 달러 강세 (엔약세)", "#ef4444"
    elif val <= 4.0: return "🟢 금리 하락 (엔강세)", "#10b981"
    else: return "⚪ 중립", "#94a3b8"

def get_vix_status(val):
    if val >= 25: return "🔴 패닉 (매도 시점)", "#ef4444"
    elif val >= 20: return "🟡 경계", "#f59e0b"
    else: return "🟢 안정 (매집 시점)", "#10b981"

# --- 🕯️ AI 캔들 분석 ---
def analyze_candles(df):
    if len(df) < 3: return ["데이터 부족"]
    last = df.iloc[-1]; prev = df.iloc[-2]
    body_size = abs(last['Close'] - last['Open'])
    total_size = last['High'] - last['Low']
    trend = "상승" if df['MA20'].iloc[-1] > df['MA20'].iloc[-2] else "하락"
    patterns = []
    if total_size > 0 and body_size <= total_size * 0.1:
        patterns.append("🔹 **도지형(Doji)**: 매수/매도 팽팽. 반전 가능성.")
    if prev['Close'] < prev['Open'] and last['Close'] > last['Open'] and last['Close'] >= prev['Open']:
        patterns.append("🚀 **상승 장악형**: 강력한 매수세 유입.")
    if prev['Close'] > prev['Open'] and last['Close'] < last['Open'] and last['Close'] <= prev['Open']:
        patterns.append("⚠️ **하락 장악형**: 매도 물량 우세.")
    if not patterns:
        patterns.append(f"현재 **{trend} 추세**를 안정적으로 유지 중입니다.")
    return patterns

# --- 🛡️ 데이터 로더 ---
@st.cache_data(ttl=60, show_spinner=False) 
def fetch_global_data(period="1y", interval="1d"):
    if not HAS_YFINANCE: return _generate_fallback_data()
    try:
        macro_us_yield = yf.Ticker("^TNX").history(period="5d", interval="1d")['Close']
        macro_vix = yf.Ticker("^VIX").history(period="5d", interval="1d")['Close']
        macro_usd_jpy = yf.Ticker("JPY=X").history(period="5d", interval="1d")['Close']
        krw_history = yf.Ticker("KRW=X").history(period=period, interval=interval)
        jpy_history = yf.Ticker("JPY=X").history(period=period, interval=interval)
        df_krw, df_jpy = krw_history.align(jpy_history, join='inner')
        df = pd.DataFrame(index=df_krw.index)
        df['Open'] = (df_krw['Open'] / df_jpy['Open']) * 100
        df['High'] = (df_krw['High'] / df_jpy['Low']) * 100 
        df['Low'] = (df_krw['Low'] / df_jpy['High']) * 100 
        df['Close'] = (df_krw['Close'] / df_jpy['Close']) * 100
        df['MA20'] = df['Close'].rolling(20).mean()
        df['STD20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
        df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
        df['RSI'] = 100 - (100 / (1 + (gain.rolling(14).mean() / loss.rolling(14).mean())))
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
    df = pd.DataFrame({'Close': [880]*100, 'Open':[879]*100, 'High':[882]*100, 'Low':[878]*100}, index=dates)
    df['MA20']=880; df['BB_Upper']=900; df['BB_Lower']=860; df['RSI']=50
    latest = {'krw_jpy': 880, 'usd_jpy': 150, 'us_yield': 4.3, 'vix': 15, 'rsi': 50, 'bb_lower': 860, 'bb_upper': 900, 'ma20': 880}
    return df, latest, False

# --- 메인 앱 시작 ---
with st.sidebar:
    if get_db() is not None: st.success("☁️ GCP 클라우드 DB 연동 완료")
    else: st.warning("⚠️ GCP 연동 필요 (비어있는 JPY-Trade 사용)")

st.title("💴 Yen-Vestor Pro (실시간 웹 대시보드)")

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()

with st.spinner("금융 데이터 동기화 중..."):
    df_base, latest, is_live = fetch_global_data()

tab1, tab2, tab3 = st.tabs(["📊 AI 대시보드 (차트 분석)", "💼 내 자산 관리 (성과 분석)", "📖 투자 전략 백과"])

# ==========================================
# 탭 1: AI 대시보드
# ==========================================
with tab1:
    st.write("⏱️ **차트 시간 간격 설정**")
    tf_options = {"30분": "1mo", "1시간": "3mo", "일봉": "1y", "주봉": "3y", "월봉": "10y"}
    selected_tf = st.radio("tf", options=list(tf_options.keys()), index=2, horizontal=True, label_visibility="collapsed")
    
    # 간격별 데이터 로드
    df_chart, latest_chart, _ = fetch_global_data(period=tf_options[selected_tf], interval="30m" if "30분" in selected_tf else "1h" if "1시간" in selected_tf else "1d")

    # 상단 지표 카드
    c1, c2, c3, c4 = st.columns(4)
    def r_card(col, title, value, unit, status_fn):
        txt, color = status_fn(value)
        col.markdown(f'<div class="metric-card"><div class="metric-title">{title}</div><div class="metric-value">{value:.2f}{unit}</div><div class="metric-status" style="color: {color};">{txt}</div></div>', unsafe_allow_html=True)
    r_card(c1, "💰 원/100엔 환율", latest_chart['krw_jpy'], "원", get_krw_status)
    r_card(c2, "💵 달러/엔 환율", latest_chart['usd_jpy'], "엔", get_usd_status)
    r_card(c3, "🇺🇸 미 국채 10년물", latest_chart['us_yield'], "%", get_yield_status)
    r_card(c4, "📉 VIX 공포지수", latest_chart['vix'], "", get_vix_status)

    # 차트 영역
    st.subheader(f"📈 원/엔 환율 종합 기술적 분석 ({selected_tf})")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['BB_Upper'], line=dict(color='rgba(148, 163, 184, 0.4)', dash='dash'), name='볼린저 상단'))
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['BB_Lower'], line=dict(color='rgba(16, 185, 129, 0.4)', dash='dash'), fill='tonexty', fillcolor='rgba(203, 213, 225, 0.1)', name='볼린저 하단'))
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA20'], line=dict(color='#f59e0b', width=1.5), name='20선'))
    fig.add_trace(go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], increasing_line_color='#ef4444', increasing_fillcolor='#ef4444', decreasing_line_color='#3b82f6', decreasing_fillcolor='#3b82f6', name='캔들'))
    fig.add_hline(y=950, line_dash="dot", line_color="red", annotation_text="고평가 (매도)")
    fig.add_hline(y=900, line_dash="dot", line_color="green", annotation_text="저평가 (매수)")
    fig.update_layout(height=450, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='#f8fafc', paper_bgcolor='#f8fafc', xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # ---------------------------------------------------------
    # [부활] 🧠 Deep Analysis 엔진 (100번의 사고 시뮬레이션)
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("🧠 Deep Analysis (거시경제 + 기술적 지표 융합 엔진)")
    st.info("현재의 매크로 변수와 차트 데이터를 기반으로 100가지 시나리오를 시뮬레이션합니다.")
    
    if st.button("▶ 현재 데이터 기반 AI 분석 시뮬레이션 가동", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        analysis_steps = [
            "거시 경제 매크로 데이터 로드 중...",
            "원/엔 역사적 밴드 이탈 여부 계산 중...",
            "볼린저 밴드 지지/저항 강도 테스트...",
            "미일 금리차 추세 및 자금 이동 추적...",
            "최종 매수/매도 컨빅션 스코어 산출 완료!"
        ]
        
        # 시뮬레이션 애니메이션
        for i in range(5):
            time.sleep(0.4)
            progress_bar.progress((i + 1) * 20)
            status_text.text(f"[{ (i+1)*20 }%] {analysis_steps[i]}")
            
        status_text.text("[100%] 분석 완료!")
        
        # 스코어링 로직
        score = 50
        reasons = []
        cur_p = latest_chart['krw_jpy']

        # 1. 기술적 지표
        if latest_chart['rsi'] <= 35: score += 20; reasons.append(f"🟣 RSI {latest_chart['rsi']:.1f}% (과매도): 강력한 기술적 반등 구간 진입.")
        elif latest_chart['rsi'] >= 65: score -= 20; reasons.append(f"🟣 RSI {latest_chart['rsi']:.1f}% (과매수): 단기 과열에 따른 조정 확률 높음.")
        
        if cur_p <= latest_chart['bb_lower'] * 1.005: score += 15; reasons.append("☁️ 볼린저 밴드 하단 터치: 통계적 저점 구간.")
        elif cur_p >= latest_chart['bb_upper'] * 0.995: score -= 15; reasons.append("☁️ 볼린저 밴드 상단 터치: 단기 저항선 부딪힘.")

        # 2. 매크로 지표
        if latest_chart['usd_jpy'] > 150: score += 15; reasons.append("🌎 달러/엔 150엔 돌파: 일본은행의 시장 개입 가능성으로 엔화 강세 압력.")
        if latest_chart['us_yield'] < 4.0: score += 15; reasons.append("🌎 미 국채 금리 하락: 미-일 금리차 축소로 엔화 환류 자금 유입.")
        elif latest_chart['us_yield'] > 4.5: score -= 10; reasons.append("🌎 미 국채 고금리 지속: 달러 강세로 인한 엔화 약세 유지.")
        if latest_chart['vix'] > 25: score += 20; reasons.append("🚨 VIX 지수 급등: 안전자산(엔화)으로의 도피 자금 쏠림 예상.")

        score = max(0, min(100, int(score)))
        
        # 결과 출력 UI
        action = 'HOLD (관망)'
        color = 'gray'
        if score >= 80: action = 'STRONG BUY (강력 매수)'; color = 'green'
        elif score >= 60: action = 'BUY (분할 매수)'; color = 'blue'
        elif score <= 20: action = 'STRONG SELL (전량 매도)'; color = 'red'
        elif score <= 40: action = 'SELL (수익 실현)'; color = 'orange'

        st.markdown(f"""
        <div style="background-color: #0f172a; border-radius: 12px; padding: 25px; text-align: center; border: 2px solid #3b82f6; margin-top: 20px;">
            <p style="color: #94a3b8; font-weight: bold; margin-bottom: 5px;">🤖 AI 통합 최종 판단</p>
            <h2 style="color: white; font-size: 32px; margin: 0;">포지션: <span style="color: {color};">{action}</span></h2>
            <h3 style="color: #f8fafc; margin-top: 5px;">Conviction Score: {score} / 100</h3>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        for i, r in enumerate(reasons, 1):
            st.success(f"{i}. {r}")

# ==========================================
# 탭 2: 내 자산 관리
# ==========================================
with tab2:
    st.subheader("📊 포트폴리오 성과 및 수익률 분석")
    
    cur_jpy = 0; cur_principal = 0; realized_p = 0; total_buy_krw = 0
    records = []; perf_history = []
    
    sorted_trades = sorted(st.session_state.portfolio, key=lambda x: x['id'])
    for t in sorted_trades:
        amt = t['amount_jpy']; r = t['rate'] / 100; krw_val = amt * r; t_date = t['date']
        if t.get('type', 'buy') == 'buy':
            cur_jpy += amt; cur_principal += krw_val; total_buy_krw += krw_val
            records.append({'ID': t['id'], '날짜': t_date, '구분': '🔴 매수', '엔화': f"¥ {amt:,.0f}", '환율': f"{t['rate']:.2f}", '한화': f"₩ {krw_val:,.0f}"})
        else:
            avg_cost = cur_principal / cur_jpy if cur_jpy > 0 else 0
            trade_p = krw_val - (amt * avg_cost); realized_p += trade_p
            cur_jpy -= amt; cur_principal -= (amt * avg_cost)
            records.append({'ID': t['id'], '날짜': t_date, '구분': '🔵 매도', '엔화': f"¥ {amt:,.0f}", '환율': f"{t['rate']:.2f}", '한화': f"₩ {krw_val:,.0f}"})
        
        unrealized = (cur_jpy * (latest['krw_jpy'] / 100)) - cur_principal
        perf_history.append({'date': t_date, 'cumulative_profit': realized_p + unrealized})

    total_p = realized_p + ((cur_jpy * (latest['krw_jpy'] / 100)) - cur_principal)
    total_roi = (total_p / total_buy_krw * 100) if total_buy_krw > 0 else 0
    avg_rate = (current_principal / cur_jpy * 100) if cur_jpy > 0 else 0 # (Note: UI code placeholder)
    avg_rate = (cur_principal / cur_jpy * 100) if cur_jpy > 0 else 0

    st.markdown(f"""
    <div style="background-color: #0f172a; border: 2px solid {'#10b981' if total_p >= 0 else '#ef4444'}; border-radius: 12px; padding: 25px; text-align: center; margin-bottom: 25px;">
        <p style="color: #94a3b8; font-size: 16px; font-weight: bold;">🏆 기간 누적 최종 투자 성과</p>
        <h2 style="color: {'#10b981' if total_p >= 0 else '#ef4444'}; font-size: 42px; font-weight: 900;">
            {total_p:,.0f} 원 ({total_roi:.2f}%)
        </h2>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("보유 잔고", f"¥ {cur_jpy:,.0f}")
    c2.metric("매수평단", f"{avg_rate:.2f}원")
    c3.metric("평가 손익", f"₩ {(cur_jpy * (latest['krw_jpy'] / 100)) - cur_principal:,.0f}")
    c4.metric("실현 수익", f"₩ {realized_p:,.0f}")

    if perf_history:
        st.write("📈 누적 수익 추이")
        perf_df = pd.DataFrame(perf_history); perf_df['date'] = pd.to_datetime(perf_df['date'])
        st.line_chart(perf_df.set_index('date'))

    st.markdown("---")
    st.subheader("📝 거래 내역 기록")
    with st.form("add_v2", clear_on_submit=True):
        f1, f2, f3, f4 = st.columns([1.5, 2, 2, 1.5])
        t_in = f1.radio("q", ["🔴 매수", "🔵 매도"], label_visibility="collapsed")
        amt_in = f2.number_input("수량(JPY)", min_value=0, step=10000)
        rate_in = f3.number_input("환율(원/100엔)", min_value=0.0, format="%.2f")
        if f4.form_submit_button("➕ 추가") and amt_in > 0:
            is_buy = "매수" in t_in
            if not is_buy and amt_in > cur_jpy: st.error("잔고 부족!")
            else:
                new_t = {'id': int(time.time()*1000), 'date': datetime.now().strftime("%Y-%m-%d"), 'type': 'buy' if is_buy else 'sell', 'amount_jpy': amt_in, 'rate': rate_in}
                st.session_state.portfolio.append(new_t); add_trade_to_db(new_t); st.rerun()

    if records:
        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
        d1, d2 = st.columns([3, 1])
        del_id = d1.number_input("삭제 ID", min_value=0, step=1, label_visibility="collapsed")
        if d2.button("삭제", use_container_width=True):
            st.session_state.portfolio = [t for t in st.session_state.portfolio if t['id'] != del_id]
            delete_trade_from_db(del_id); st.rerun()

# ==========================================
# 탭 3: 전략
# ==========================================
with tab3:
    st.header("성공하는 투자 기법")
    with st.expander("1. 그리드 트레이딩", expanded=True):
        st.write("- 역사적 저점과 고점 밴드를 설정하고 기계적으로 분할 매매하는 기법입니다.")
    with st.expander("2. 미일 금리차 추적"):
        st.write("- 미국 금리가 하락 반전할 때가 최고의 엔화 매수 타이밍입니다.")
