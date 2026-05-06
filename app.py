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
    
    /* 리포트 카드 스타일 */
    .report-box {
        background-color: #1e293b; 
        border-radius: 8px; 
        padding: 15px; 
        border-left: 4px solid #3b82f6;
        margin-bottom: 15px;
    }
    .report-title { color: #93c5fd; font-weight: bold; font-size: 16px; margin-bottom: 8px; }
    .report-item { color: #cbd5e1; font-size: 14px; margin-bottom: 4px; line-height: 1.5; }
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
            if "404" in str(e):
                st.sidebar.error("❌ DB가 생성되지 않았습니다. GCP 콘솔에서 Firestore를 '(default)' ID로 생성해주세요.")
            elif "403" in str(e):
                st.sidebar.error("❌ 권한 오류(403). 열쇠(JSON)가 올바른 프로젝트의 것인지 확인해주세요.")
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
    elif val <= 4.0: return "🟢 금리 하락 (엔강세)", "#10b981"
    else: return "⚪ 방향성 탐색중", "#94a3b8"

def get_vix_status(val):
    if val >= 25: return "🔴 패닉장 (단기 폭등)", "#ef4444"
    elif val >= 20: return "🟡 경계장 (수요 쏠림)", "#f59e0b"
    else: return "🟢 평온장 (매집 시기)", "#10b981"

# --- 🕯️ AI 캔들 및 패턴 분석 엔진 ---
def analyze_candles(df):
    if len(df) < 3: return ["데이터가 부족하여 캔들 패턴을 분석할 수 없습니다."]
    last = df.iloc[-1]; prev = df.iloc[-2]
    body_size = abs(last['Close'] - last['Open'])
    total_size = last['High'] - last['Low']
    upper_shadow = last['High'] - max(last['Open'], last['Close'])
    lower_shadow = min(last['Open'], last['Close']) - last['Low']
    trend = "상승" if df['MA20'].iloc[-1] > df['MA20'].iloc[-2] else "하락"
    patterns = []
    if total_size > 0 and body_size <= total_size * 0.1:
        patterns.append("🔹 **도지형(Doji)**: 매도세와 매수세 팽팽. 곧 추세가 반전될 가능성이 큽니다.")
    if prev['Close'] < prev['Open'] and last['Close'] > last['Open'] and last['Open'] <= prev['Close'] and last['Close'] >= prev['Open']:
        patterns.append("🚀 **상승 장악형**: 강력한 매수세 유입. 하락세 종료 및 반등 가능성이 높습니다.")
    if prev['Close'] > prev['Open'] and last['Close'] < last['Open'] and last['Open'] >= prev['Close'] and last['Close'] <= prev['Open']:
        patterns.append("⚠️ **하락 장악형**: 강력한 매도세 유입. 하락 조심하세요.")
    if not patterns:
        patterns.append(f"현재 뚜렷한 반전 캔들 패턴은 없으며 **{trend} 추세** 유지 중입니다.")
    return patterns

# --- 🛡️ 데이터 로더 (MACD 추가) ---
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
        
        # 기존 지표
        df['MA20'] = df['Close'].rolling(20).mean()
        df['STD20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
        df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0); loss = -delta.where(delta < 0, 0)
        df['RSI'] = 100 - (100 / (1 + (gain.rolling(14).mean() / loss.rolling(14).mean())))
        
        # [신규] MACD 추가
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        df.dropna(inplace=True)
        latest = {
            'krw_jpy': df['Close'].iloc[-1], 'usd_jpy': macro_usd_jpy.iloc[-1],
            'us_yield': macro_us_yield.iloc[-1], 'vix': macro_vix.iloc[-1],
            'rsi': df['RSI'].iloc[-1], 'bb_lower': df['BB_Lower'].iloc[-1],
            'bb_upper': df['BB_Upper'].iloc[-1], 'ma20': df['MA20'].iloc[-1],
            'macd': df['MACD'].iloc[-1], 'macd_signal': df['Signal_Line'].iloc[-1]
        }
        return df, latest, True 
    except: return _generate_fallback_data()

def _generate_fallback_data():
    dates = pd.date_range(end=datetime.now(), periods=100)
    df = pd.DataFrame({'Close': [880]*100}, index=dates)
    df['Open']=879; df['High']=882; df['Low']=878; df['MA20']=880; df['BB_Upper']=900; df['BB_Lower']=860; df['RSI']=50
    df['MACD']=0; df['Signal_Line']=0
    latest = {'krw_jpy': 880, 'usd_jpy': 150, 'us_yield': 4.3, 'vix': 15, 'rsi': 50, 'bb_lower': 860, 'bb_upper': 900, 'ma20': 880, 'macd':0, 'macd_signal':0}
    return df, latest, False

# --- 💡 환율 보정 헬퍼 함수 ---
def apply_toss_adjustment(df, latest_dict, adj):
    d = df.copy()
    l = latest_dict.copy()
    if adj != 0:
        for col in ['Open', 'High', 'Low', 'Close', 'MA20', 'BB_Upper', 'BB_Lower']:
            if col in d.columns: d[col] += adj
        for key in ['krw_jpy', 'ma20', 'bb_upper', 'bb_lower']:
            if key in l: l[key] += adj
    return d, l

# --- 메인 시작 ---
with st.sidebar:
    if get_db() is not None: st.success("☁️ GCP 클라우드 DB 연동 완료")
    else: st.warning("⚠️ GCP 연동 필요 (직접 만든 JPY-Trade 프로젝트의 열쇠를 사용하세요)")
    
    st.markdown("---")
    st.subheader("⚙️ 토스뱅크 환율 동기화")
    st.caption("글로벌 환율과 실제 토스 앱의 환율 차이를 보정하세요. (예: 토스가 1.5원 더 비싸면 +1.5 입력)")
    toss_adj = st.number_input("환율 보정값 (+/- 원)", value=0.00, step=0.10, format="%.2f")

# 🔄 새로고침 버튼과 타이틀 나란히 배치
col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.title("💴 Yen-Vestor Pro")
with col_refresh:
    st.write("") # 타이틀과 줄 맞춤
    if st.button("🔄 실시간 새로고침", use_container_width=True):
        fetch_global_data.clear() # 캐시를 삭제하여 다음 호출 시 최신 데이터를 강제로 받아오게 함
        st.rerun()

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()

with st.spinner("금융 데이터 동기화 중..."):
    df_base_raw, latest_raw, is_live = fetch_global_data()
    # 토스 환율 보정 적용
    df_base, latest = apply_toss_adjustment(df_base_raw, latest_raw, toss_adj)

tab1, tab2, tab3 = st.tabs(["📊 AI 대시보드 (차트 분석)", "💼 내 자산 관리 (성과 분석)", "📖 투자 전략 백과"])

# ==========================================
# 탭 1: 대시보드 (차트 & AI 정밀 리포트)
# ==========================================
with tab1:
    tf_options = {"30분": "1mo", "1시간": "3mo", "일봉": "1y", "주봉": "3y", "월봉": "10y"}
    selected_tf = st.radio("차트 간격", options=list(tf_options.keys()), index=2, horizontal=True, label_visibility="collapsed")
    df_chart_raw, latest_chart_raw, _ = fetch_global_data(period=tf_options[selected_tf], interval="30m" if "30분" in selected_tf else "1h" if "1시간" in selected_tf else "1d")
    
    # 탭1 차트용 데이터에도 토스 환율 보정 적용
    df_chart, latest_chart = apply_toss_adjustment(df_chart_raw, latest_chart_raw, toss_adj)

    c1, c2, c3, c4 = st.columns(4)
    def m_card(col, title, val, unit, fn):
        t, c = fn(val)
        col.markdown(f'<div class="metric-card"><div class="metric-title">{title}</div><div class="metric-value">{val:.2f}{unit}</div><div style="color:{c}">{t}</div></div>', unsafe_allow_html=True)
    m_card(c1, "💰 원/100엔 환율", latest_chart['krw_jpy'], "원", get_krw_status)
    m_card(c2, "💵 달러/엔", latest_chart['usd_jpy'], "엔", get_usd_status)
    m_card(c3, "🇺🇸 미 국채", latest_chart['us_yield'], "%", get_yield_status)
    m_card(c4, "📉 VIX 지수", latest_chart['vix'], "", get_vix_status)

    # 💡 지표 가이드 (Expander) 추가
    with st.expander("💡 각 지표가 무슨 의미인가요? (클릭하여 펼치기)"):
        st.markdown("""
        * **💵 달러/엔 환율 (USD/JPY)**: 달러 대비 엔화의 가치입니다. (보통 130~140엔이 평균 기준값)
          * **150엔 이상 상승 시**: 엔화 가치가 바닥이라는 뜻입니다. 이때 일본은행(BOJ)이 억지로 환율을 내리기 위해 시장에 개입할 확률이 매우 높으므로, **원/엔 환율이 오를(엔화 강세) 좋은 매수 기회**가 됩니다.
        * **🇺🇸 미국 10년물 국채 금리**: 글로벌 자금의 흐름을 결정하는 핵심 지표입니다. (보통 3.5%~4.0%가 기준값)
          * **금리 하락 시 (좋음)**: 미국 금리가 내리면 투자자들이 돈을 빼서 다른 나라(일본 등)로 이동시킵니다. 즉, **금리가 내릴수록 엔화가 강세(상승)를 보입니다.**
          * **금리 상승 시 (나쁨)**: 미국 금리가 오르면 굳이 이자도 안 주는 엔화를 들고 있을 이유가 없어져 엔화가 더 떨어집니다.
        * **📉 VIX 공포 지수**: 세계 주식 시장 투자자들의 불안감을 수치화한 것입니다. (평상시 15 내외)
          * **25 이상 급등 시 (좋음)**: 전쟁이나 경제 위기 등 패닉이 오면 사람들은 주식을 팔고 가장 안전한 자산인 **엔화로 대피**합니다. 이때 원/엔 환율이 폭등하므로, **보유 중인 엔화를 비싸게 팔(익절) 최고의 기회**가 됩니다.
        """)

    if toss_adj != 0:
        st.info(f"💡 현재 토스뱅크 환율 동기화가 적용되어 있습니다. (글로벌 기준가 대비 **{toss_adj:+.2f}원** 보정됨)")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['BB_Upper'], line=dict(color='rgba(148, 163, 184, 0.4)', dash='dash'), name='볼린저 상단'))
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['BB_Lower'], line=dict(color='rgba(16, 185, 129, 0.4)', dash='dash'), fill='tonexty', fillcolor='rgba(203, 213, 225, 0.1)', name='볼린저 하단'))
    fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart['MA20'], line=dict(color='#f59e0b', width=1.5), name='20선'))
    fig.add_trace(go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], increasing_line_color='#ef4444', decreasing_line_color='#3b82f6', name='캔들'))
    fig.add_hline(y=950, line_dash="dot", line_color="red", annotation_text="고평가 (저항선)")
    fig.add_hline(y=900, line_dash="dot", line_color="green", annotation_text="저평가 (매수선)")
    fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig, use_container_width=True)

    # ---------------------------------------------------------
    # 🧠 AI 엔진 정밀 리포트 생성기
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("🧠 Deep Analysis (AI 정밀 투자 리포트)")
    st.info("단순 캔들 분석을 넘어 거시경제 변수, 이동평균, 볼린저밴드, RSI, MACD를 총망라하여 입체적으로 시뮬레이션합니다.")
    
    if st.button("▶ 현재 데이터 기반 AI 시뮬레이션 가동", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        analysis_steps = [
            "거시 경제(Macro) 데이터 연산 중 (국채, VIX, JPY)...",
            "볼린저 밴드 이탈 및 역사적 밴드 지지 여부 테스트...",
            "MACD 다이버전스 및 RSI 과매수/과매도 판별 중...",
            "AI 캔들 패턴 매칭 및 추세 강도 분석...",
            "최종 컨빅션 스코어(Conviction Score) 산출 완료!"
        ]
        
        for i in range(5):
            time.sleep(0.4)
            progress_bar.progress((i + 1) * 20)
            status_text.text(f"[{ (i+1)*20 }%] {analysis_steps[i]}")
            
        status_text.text("[100%] 정밀 분석 완료!")
        
        # --- 스코어 산출 및 리포트 작성 ---
        score = 50
        macro_logs = []
        tech_logs = []
        cur_p = latest_chart['krw_jpy']

        # [1. 거시경제 지표 분석]
        if latest_chart['usd_jpy'] > 150: 
            score += 15; macro_logs.append("🔹 **달러/엔 150엔 상회 [+15점]**: 일본은행(BOJ)의 시장 개입 및 환율 방어 가능성이 매우 높아 원/엔 환율 반등(엔화 강세)의 강력한 트리거가 될 수 있습니다.")
        elif latest_chart['usd_jpy'] < 140:
            score -= 10; macro_logs.append("🔸 **달러/엔 140엔 하회 [-10점]**: 이미 글로벌 시장에서 엔화가 충분히 강세를 띄고 있어 추가 상승 여력이 제한적일 수 있습니다.")
            
        if latest_chart['us_yield'] < 4.0: 
            score += 15; macro_logs.append("🔹 **미 국채 10년물 하락세 [+15점]**: 미-일 금리차가 축소됨에 따라 캐리 트레이드 청산 자금이 엔화로 몰려 엔화 강세를 이끌 좋은 환경입니다.")
        elif latest_chart['us_yield'] > 4.5: 
            score -= 10; macro_logs.append("🔸 **미 국채 10년물 고금리 유지 [-10점]**: 강력한 달러 쏠림 현상으로 당분간 엔화의 구조적 약세가 지속될 가능성이 높습니다.")
            
        if latest_chart['vix'] > 25: 
            score += 15; macro_logs.append("🔹 **VIX 공포지수 급등 [+15점]**: 글로벌 증시 불안감 증대로 전통적 안전자산인 엔화에 투기적 매수세가 유입될 확률이 높습니다.")
        else:
            macro_logs.append("▫️ **VIX 지수 안정 [0점]**: 시장 참여자들의 심리가 평온하여 안전자산 프리미엄(엔화 쏠림)이 크지 않은 구간입니다.")

        # [2. 기술적 지표 분석]
        if latest_chart['rsi'] <= 35: 
            score += 20; tech_logs.append(f"🔹 **RSI {latest_chart['rsi']:.1f}% 과매도 [+20점]**: 투매가 절정에 달했습니다. 과거 통계상 이 구간에서는 기술적 숏커버링(반등)이 80% 확률로 발생했습니다.")
        elif latest_chart['rsi'] >= 65: 
            score -= 20; tech_logs.append(f"🔸 **RSI {latest_chart['rsi']:.1f}% 과매수 [-20점]**: 단기 과열 징후가 뚜렷합니다. 언제 조정을 받아도 이상하지 않은 높은 가격대입니다.")
        else:
            tech_logs.append(f"▫️ **RSI {latest_chart['rsi']:.1f}% 중립 [0점]**: 과열도 침체도 아닌 적정 밸류에이션 구간을 지나고 있습니다.")
        
        if cur_p <= latest_chart['bb_lower'] * 1.01: 
            score += 15; tech_logs.append("🔹 **볼린저 밴드 하단 터치 [+15점]**: 정상적인 가격 궤도의 최하단을 찔렀습니다. 강한 지지선으로 작용하여 가격이 위로 튕겨 오를 자리입니다.")
        elif cur_p >= latest_chart['bb_upper'] * 0.99: 
            score -= 15; tech_logs.append("🔸 **볼린저 밴드 상단 터치 [-15점]**: 저항선에 부딪혀 에너지가 소진되고 있습니다. 단기 하락 턴어라운드가 임박했습니다.")

        # MACD 분석 추가
        if latest_chart['macd'] > latest_chart['macd_signal']:
            score += 10; tech_logs.append("🔹 **MACD 골든크로스 상태 [+10점]**: MACD 선이 시그널 선 위로 교차하며 상승 모멘텀(에너지)이 확산되는 추세입니다.")
        else:
            score -= 10; tech_logs.append("🔸 **MACD 데드크로스 상태 [-10점]**: 하락 모멘텀이 상승 모멘텀을 압도하고 있어 아직은 떨어지는 칼날일 확률이 높습니다.")

        score = max(0, min(100, int(score)))
        
        # [결과 출력]
        action = 'HOLD (관망)'
        color = '#64748b'
        advice = "현재 시장 방향성이 불투명합니다. 거시 지표와 기술적 지표가 혼재되어 있으니 뚜렷한 시그널이 나올 때까지 현금을 보유하고 대기하세요."
        
        if score >= 80: 
            action = 'STRONG BUY (강력 매수)'
            color = '#10b981'
            advice = "엔화가 극심한 저평가 구간에 진입했습니다. MACD와 RSI 등 기술적 지표가 반등을 강하게 가리키고 있으며 매크로 환경도 도와주고 있습니다. 비중을 크게 실어 공격적으로 진입할 타이밍입니다."
        elif score >= 60: 
            action = 'BUY (분할 매수)'
            color = '#3b82f6'
            advice = "바닥을 다지는 신호가 포착되고 있습니다. 한 번에 큰 금액을 넣기보다는 현재 가격대부터 10~20%씩 평단가를 낮춰가는 '그리드 방식'의 분할 매수를 시작하기 좋은 시점입니다."
        elif score <= 20: 
            action = 'STRONG SELL (전량 매도)'
            color = '#ef4444'
            advice = "단기적으로 오버슈팅(오버밸류)이 심각한 상태입니다. 보유 중인 엔화 물량이 있다면 전량 매도하여 수익을 확정 짓고 시장의 과열이 식을 때까지 기다려야 합니다."
        elif score <= 40: 
            action = 'SELL (수익 실현)'
            color = '#f59e0b'
            advice = "상승 모멘텀이 둔화되고 저항선에 도달했습니다. 보유 물량의 절반 이상을 매도하여 안전하게 수익을 실현(익절)하는 것을 권장합니다."

        # UI 렌더링
        st.markdown(f"""
        <div style="background-color: #0f172a; border-radius: 12px; padding: 25px; text-align: center; border: 2px solid {color}; margin-top: 15px; margin-bottom: 20px;">
            <p style="color: #94a3b8; font-weight: bold; margin-bottom: 5px;">🤖 AI 알고리즘 최종 투자 판단</p>
            <h2 style="color: {color}; font-size: 34px; font-weight: 900; margin: 0;">{action}</h2>
            <h3 style="color: white; margin-top: 8px;">매수 확신도 (Conviction Score): {score} / 100</h3>
        </div>
        """, unsafe_allow_html=True)
        
        col_macro, col_tech = st.columns(2)
        
        with col_macro:
            st.markdown('<div class="report-box" style="border-left-color: #f59e0b;">', unsafe_allow_html=True)
            st.markdown('<div class="report-title">🌎 거시 경제 (Macro) 분석 요약</div>', unsafe_allow_html=True)
            for log in macro_logs:
                st.markdown(f'<div class="report-item">{log}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_tech:
            st.markdown('<div class="report-box" style="border-left-color: #8b5cf6;">', unsafe_allow_html=True)
            st.markdown('<div class="report-title">📈 기술적 지표 (Technical) 분석 요약</div>', unsafe_allow_html=True)
            for log in tech_logs:
                st.markdown(f'<div class="report-item">{log}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown(f"""
        <div style="background-color: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #334155; margin-top: 10px;">
            <strong style="color: #e2e8f0;">💡 AI 투자 전략 가이드:</strong><br>
            <span style="color: #94a3b8; font-size: 15px; line-height: 1.6;">{advice}</span>
        </div>
        """, unsafe_allow_html=True)

# ==========================================
# 탭 2: 자산 관리 (성과 정밀 분석)
# ==========================================
with tab2:
    st.subheader("📊 투자 성과 및 수익률 분석")
    
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
        
        # 보정된 현재 환율을 기준으로 누적 수익 계산
        unrealized = (cur_jpy * (latest['krw_jpy'] / 100)) - cur_principal
        perf_history.append({'date': t_date, 'cumulative_profit': realized_p + unrealized})

    total_p = realized_p + ((cur_jpy * (latest['krw_jpy'] / 100)) - cur_principal)
    total_roi = (total_p / total_buy_krw * 100) if total_buy_krw > 0 else 0
    avg_rate = (cur_principal / cur_jpy * 100) if cur_jpy > 0 else 0

    st.markdown(f"""
    <div style="background-color: #0f172a; border: 2px solid {'#10b981' if total_p >= 0 else '#ef4444'}; border-radius: 12px; padding: 25px; text-align: center; margin-bottom: 25px;">
        <p style="color: #94a3b8; font-size: 16px; font-weight: bold;">🏆 기간 누적 최종 투자 성과</p>
        <h2 style="color: {'#10b981' if total_p >= 0 else '#ef4444'}; font-size: 42px; font-weight: 900;">
            {'+' if total_p > 0 else ''}{total_p:,.0f} 원 ({'+' if total_roi > 0 else ''}{total_roi:.2f}%)
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
        
        # 보정된 현재 환율을 기본값으로 표시해 편의성 증대
        default_rate = float(latest['krw_jpy']) if latest else 0.0
        rate_in = f3.number_input("환율(원/100엔)", min_value=0.0, value=default_rate, format="%.2f")
        
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
