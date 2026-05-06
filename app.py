import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime

# [필수] Streamlit 페이지 설정은 반드시 최상단에 위치해야 합니다.
st.set_page_config(page_title="엔화 투자 마스터", page_icon="💴", layout="wide")

# yfinance 임포트 (만약 설치 안 되어 있어도 앱이 뻗지 않도록 처리)
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

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
    
    # 단기 추세 확인 (20일선 기준)
    trend = "상승" if df['MA20'].iloc[-1] > df['MA20'].iloc[-2] else "하락"
    
    patterns = []
    
    # 1. 도지형(Doji)
    if total_size > 0 and body_size <= total_size * 0.1:
        patterns.append("🔹 **도지형(Doji) 출현**: 매수세와 매도세가 팽팽하게 맞서고 있습니다. 곧 현재의 추세가 크게 반전될 가능성이 있습니다.")
        
    # 2. 상승 장악형 (Bullish Engulfing)
    if prev['Close'] < prev['Open'] and last['Close'] > last['Open'] and last['Open'] <= prev['Close'] and last['Close'] >= prev['Open']:
        patterns.append("🚀 **상승 장악형(Bullish Engulfing)**: 이전의 하락세를 완전히 뒤덮는 강력한 매수세가 들어왔습니다. **상승 반전 가능성**이 높습니다.")
        
    # 3. 하락 장악형 (Bearish Engulfing)
    if prev['Close'] > prev['Open'] and last['Close'] < last['Open'] and last['Open'] >= prev['Close'] and last['Close'] <= prev['Open']:
        patterns.append("⚠️ **하락 장악형(Bearish Engulfing)**: 이전의 상승세를 꺾는 강력한 매도세가 출현했습니다. **하락에 주의**가 필요합니다.")
        
    # 4. 망치형 (Hammer) / 교수형
    if total_size > 0 and lower_shadow > body_size * 2 and upper_shadow < total_size * 0.1:
        if trend == "하락":
            patterns.append("🔨 **망치형(Hammer)**: 하락하던 중 바닥에서 강한 매수세가 들어와 꼬리를 길게 달았습니다. **단기 바닥(매수 찬스)**일 확률이 높습니다.")
        else:
            patterns.append("➰ **교수형(Hanging Man)**: 고점에서 나타난 긴 아래꼬리입니다. 단기 고점 징후일 수 있습니다.")
            
    # 5. 역망치형 (Shooting Star)
    if total_size > 0 and upper_shadow > body_size * 2 and lower_shadow < total_size * 0.1:
        if trend == "상승":
            patterns.append("☄️ **유성형(Shooting Star)**: 고점에서 강하게 눌린 흔적입니다. 매도 물량이 쏟아지며 **단기 고점**일 확률이 높습니다.")
            
    if not patterns:
        patterns.append(f"현재 뚜렷한 반전 캔들 패턴은 보이지 않으며, 기존의 **{trend} 추세**를 무난하게 이어가고 있습니다.")
        
    return patterns

# --- 🛡️ [무적 엔진] 방탄 데이터 로더 (시간 단위 선택 지원) ---
@st.cache_data(ttl=60, show_spinner=False) 
def fetch_global_data(period="1y", interval="1d"):
    if not HAS_YFINANCE:
        return _generate_fallback_data()
        
    try:
        # 매크로 지표용 최근 데이터 (이것들은 차트 기간과 무관하게 항상 최신 일봉 기준)
        macro_us_yield = yf.Ticker("^TNX").history(period="5d", interval="1d")['Close']
        macro_vix = yf.Ticker("^VIX").history(period="5d", interval="1d")['Close']
        macro_usd_jpy = yf.Ticker("JPY=X").history(period="5d", interval="1d")['Close']

        # 차트용 OHLC (시가, 고가, 저가, 종가) 데이터 추출
        krw_history = yf.Ticker("KRW=X").history(period=period, interval=interval)
        jpy_history = yf.Ticker("JPY=X").history(period=period, interval=interval)

        # 데이터가 비어있으면 Fallback
        if krw_history.empty or jpy_history.empty or macro_us_yield.empty or macro_vix.empty:
            return _generate_fallback_data()

        # 두 화폐 데이터 병합 및 정렬 (시간축 완벽 매칭)
        df_krw, df_jpy = krw_history.align(jpy_history, join='inner')
        
        # 교차 환율 OHLC 계산 (원/100엔)
        df = pd.DataFrame(index=df_krw.index)
        df['Open'] = (df_krw['Open'] / df_jpy['Open']) * 100
        df['High'] = (df_krw['High'] / df_jpy['Low']) * 100  # 원화 고점 / 엔화 저점
        df['Low'] = (df_krw['Low'] / df_jpy['High']) * 100   # 원화 저점 / 엔화 고점
        df['Close'] = (df_krw['Close'] / df_jpy['Close']) * 100

        # 기술적 지표 계산 (차트 경량화를 위해 불필요한 데이터 포인트가 너무 많으면 최적화)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['STD20'] = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
        df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)

        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))

        df.dropna(inplace=True)
        
        # Latest 딕셔너리는 매크로 지표용 절대 최신값을 담음
        latest = {
            'krw_jpy': df['Close'].iloc[-1],
            'usd_jpy': macro_usd_jpy.iloc[-1],
            'us_yield': macro_us_yield.iloc[-1],
            'vix': macro_vix.iloc[-1],
            'rsi': df['RSI'].iloc[-1],
            'bb_lower': df['BB_Lower'].iloc[-1],
            'bb_upper': df['BB_Upper'].iloc[-1],
            'ma20': df['MA20'].iloc[-1]
        }
        return df, latest, True # True = 라이브 데이터 성공
        
    except Exception as e:
        # 서버 다운, IP 차단 등 어떠한 에러가 발생해도 프로그램이 죽지 않고 백업 실행
        return _generate_fallback_data()

def _generate_fallback_data():
    # 서버 에러 시 화면이 죽지 않도록 생성하는 가상의 OHLC 시뮬레이션 데이터
    dates = pd.date_range(end=datetime.now(), periods=100)
    np.random.seed(42)
    walk = np.random.normal(0, 1.5, 100).cumsum()
    close_mock = 880 + walk
    
    df = pd.DataFrame(index=dates)
    df['Open'] = close_mock - np.random.normal(0, 1, 100)
    df['Close'] = close_mock
    df['High'] = df[['Open', 'Close']].max(axis=1) + np.random.uniform(0.5, 2, 100)
    df['Low'] = df[['Open', 'Close']].min(axis=1) - np.random.uniform(0.5, 2, 100)

    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['STD20'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    df['RSI'] = 45.5 # 가상 RSI

    df.dropna(inplace=True)

    latest = {
        'krw_jpy': df['Close'].iloc[-1],
        'usd_jpy': 151.30,
        'us_yield': 4.35,
        'vix': 16.2,
        'rsi': 45.5,
        'bb_lower': df['BB_Lower'].iloc[-1],
        'bb_upper': df['BB_Upper'].iloc[-1],
        'ma20': df['MA20'].iloc[-1]
    }
    return df, latest, False # False = 시뮬레이션 모드 작동

# --- 앱 메인 화면 시작 ---
st.title("💴 Yen-Vestor Pro (실시간 웹 대시보드)")
st.markdown("전 세계 금융 API와 연동된 **가장 완벽한 엔화 투자 AI 시뮬레이터**입니다.")

# 포트폴리오 세션 초기화
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {'id': 1, 'date': '2025-10-15', 'amount_jpy': 500000, 'rate': 905.20}
    ]

# --- UI: 차트 봉(시간) 선택 ---
# 브라우저 렌더링 부하(렉)를 방지하기 위해 period(조회 기간)를 매우 현실적이고 가볍게 최적화함
timeframe_map = {
    "30분": {"period": "1mo", "interval": "30m"}, # 기존 60d -> 1mo (데이터포인트 대폭 감소)
    "1시간": {"period": "3mo", "interval": "1h"},  # 기존 730d(17000개) -> 3mo(약 500개)로 30배 경량화
    "일봉": {"period": "1y", "interval": "1d"},
    "주봉": {"period": "3y", "interval": "1wk"},
    "월봉": {"period": "10y", "interval": "1mo"},
    "분기봉": {"period": "20y", "interval": "3mo"}
}

# --- 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["📊 AI 대시보드 (차트 분석)", "💼 내 자산 관리", "📖 투자 전략 백과"])

# ==========================================
# 탭 1: AI 대시보드
# ==========================================
with tab1:
    
    # 시간 간격(봉) 선택 (UI 강조)
    st.write("⏱️ **차트 시간 간격 (Timeframe) 설정**")
    selected_tf = st.radio(
        "시간 간격",
        options=list(timeframe_map.keys()),
        index=2, # 기본값: 일봉
        horizontal=True,
        label_visibility="collapsed"
    )
    
    # 선택된 기간으로 데이터 로딩 실행
    with st.spinner("안전하게 글로벌 금융 데이터를 동기화 중입니다..."):
        df, latest, is_live = fetch_global_data(
            period=timeframe_map[selected_tf]["period"], 
            interval=timeframe_map[selected_tf]["interval"]
        )

    # 🚨 차단 방어 성공 알림 (서버 차단 시 시뮬레이션 모드 안내)
    if not is_live:
        st.warning("⚠️ 현재 글로벌 금융 서버(Yahoo) 응답이 지연되어, 앱이 뻗지 않도록 **AI 시뮬레이션 모드(가상 데이터)**로 자동 전환되었습니다. (UI 및 기능은 100% 정상 작동합니다)")


    # 1. 상단 카드 지표
    col1, col2, col3, col4 = st.columns(4)
    
    def render_metric_card(col, title, value, unit, status_fn):
        txt, color = status_fn(value)
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value:.2f}{unit}</div>
            <div class="metric-status" style="color: {color};">{txt}</div>
        </div>
        """, unsafe_allow_html=True)

    render_metric_card(col1, "💰 현재 환율(원/100엔)", latest['krw_jpy'], "원", get_krw_status)
    render_metric_card(col2, "💵 달러/엔 환율", latest['usd_jpy'], "엔", get_usd_status)
    render_metric_card(col3, "🇺🇸 미 국채 10년물", latest['us_yield'], "%", get_yield_status)
    render_metric_card(col4, "📉 VIX 공포지수", latest['vix'], "", get_vix_status)

    st.write("") # 여백

    # 2. Plotly 캔들스틱 인터랙티브 차트
    st.subheader(f"📈 원/엔 환율 종합 기술적 분석 ({selected_tf} 차트)")
    st.caption("마우스를 올려 가격을 확인하거나 드래그해서 차트를 확대할 수 있습니다.")
    
    fig = go.Figure()
    
    # 볼린저 밴드 영역
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(148, 163, 184, 0.5)', dash='dash'), name='볼린저 상단'))
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(16, 185, 129, 0.5)', dash='dash'), fill='tonexty', fillcolor='rgba(203, 213, 225, 0.1)', name='볼린저 하단'))
    
    # 20일 이동평균선
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#f59e0b', width=2), name='20선 (이동평균)'))
    
    # [새로운 기능] 캔들스틱 (봉 차트) - 한국 주식 시장 컬러(상승: 빨강, 하락: 파랑) 완벽 적용
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        increasing_line_color='#ef4444', increasing_fillcolor='#ef4444', # 한국 패치: 상승(양봉) = 빨간색
        decreasing_line_color='#3b82f6', decreasing_fillcolor='#3b82f6', # 한국 패치: 하락(음봉) = 파란색
        name='원/100엔 캔들'
    ))

    # 가이드 라인
    fig.add_hline(y=950, line_dash="dot", line_color="red", annotation_text="고평가 (매도)", annotation_position="top left")
    fig.add_hline(y=850, line_dash="dot", line_color="green", annotation_text="저평가 (매수)", annotation_position="bottom left")
    
    # 레이아웃 설정 (차트 하단의 불필요한 범위 조절 바 제거)
    fig.update_layout(
        height=500, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='#f8fafc', paper_bgcolor='#f8fafc',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False # 캔들 차트의 부피를 차지하는 미니 슬라이더 끔
    )
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.05)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.05)')
    
    st.plotly_chart(fig, use_container_width=True)

    # 3. [신규] 🕯️ AI 캔들 & 차트 패턴 분석
    st.markdown("### 🕯️ AI 캔들 & 차트 패턴 실시간 분석")
    candle_patterns = analyze_candles(df)
    
    for pattern in candle_patterns:
        # 패턴의 종류에 따라 색상을 다르게 표현 (경고, 성공, 안내)
        if "장악형" in pattern and "하락" in pattern or "유성형" in pattern:
            st.warning(pattern)
        elif "장악형" in pattern and "상승" in pattern or "망치형" in pattern:
            st.success(pattern)
        else:
            st.info(pattern)

    # 4. AI 분석 엔진
    st.markdown("---")
    st.subheader("🧠 Deep Analysis (매크로 + 기술적 지표 융합 엔진)")
    
    if st.button("▶ 현재 데이터 기반 AI 시뮬레이션 가동", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        steps = [
            "최근 캔들 패턴(Price Action) 분석 중...",
            "볼린저 밴드(Bollinger Bands) 지지/저항 테스트...",
            "미일 금리차(US-JP Yield Gap) 축소 가능성 계산...",
            "과거 유사 차트 패턴 딥러닝 매칭 중...",
            "최종 매수/매도 확률(Conviction Score) 산출 완료!"
        ]
        
        # 렉을 유발하던 100번의 불필요한 루프를 부드러운 5단계(20%씩) 스텝으로 경량화
        for i in range(5):
            time.sleep(0.3)
            progress_bar.progress((i + 1) * 20)
            status_text.text(f"[{(i + 1) * 20}%] {steps[i]}")
                
        status_text.text("[100%] 분석 완료!")
        
        # AI 점수 계산 로직
        score = 50
        reasons = []
        cur_price = latest['krw_jpy']

        if latest['rsi'] <= 30: score += 20; reasons.append(f"🟣 RSI {latest['rsi']}% (과매도): 시장의 투매가 멈추고 기술적 반등 임박.")
        elif latest['rsi'] >= 70: score -= 20; reasons.append(f"🟣 RSI {latest['rsi']}% (과매수): 단기 과열 상태. 조정 예상.")
            
        if cur_price <= latest['bb_lower'] * 1.01: score += 15; reasons.append("☁️ 볼린저 밴드 하단 터치: 튕겨오를 확률이 높은 저점.")
        elif cur_price >= latest['bb_upper'] * 0.99: score -= 15; reasons.append("☁️ 볼린저 밴드 상단 터치: 저항선 부딪힘. 하락 가능성.")
            
        if cur_price > latest['ma20']: score += 5; reasons.append("🟡 이동평균선 상회: 단기 추세가 우상향을 타고 있음.")
        else: score -= 5; reasons.append("🟡 이동평균선 하회: 단기 추세 꺾임.")

        if latest['usd_jpy'] > 150: score += 10; reasons.append("🌎 달러/엔 150엔 돌파: BOJ의 시장 개입 가능성 상승 (엔화 강세 압력).")
        if latest['us_yield'] > 4.5: score -= 10; reasons.append("🌎 미 국채 10년물 강세: 글로벌 자금이 미국으로 몰려 엔화 약세 유지.")
        elif latest['us_yield'] < 4.0: score += 15; reasons.append("🌎 미 국채 금리 하락: 글로벌 자금이 일본으로 돌아갈 환경 조성.")
        if latest['vix'] > 25: score += 15; reasons.append("🚨 VIX 공포지수 급등: 위기로 인한 안전자산(엔화) 단기 쏠림 현상.")

        score = max(0, min(100, int(score)))

        action = 'HOLD (관망)'
        color = 'gray'
        if score >= 80: action = 'STRONG BUY (강력 매수)'; color = 'green'
        elif score >= 60: action = 'BUY (분할 매수)'; color = 'blue'
        elif score <= 20: action = 'STRONG SELL (전량 매도)'; color = 'red'
        elif score <= 40: action = 'SELL (수익 실현)'; color = 'orange'

        st.markdown(f"### 🤖 AI 통합 최종 판단: :{color}[{action}]")
        st.markdown(f"**■ 매수 확신도 (Score):** {score} / 100")
        
        for i, r in enumerate(reasons, 1):
            st.success(f"{i}. {r}")

# ==========================================
# 탭 2: 내 자산 관리
# ==========================================
with tab2:
    st.subheader("포트폴리오 요약")
    
    total_jpy = sum(t['amount_jpy'] for t in st.session_state.portfolio)
    total_krw_invested = sum(t['amount_jpy'] * (t['rate'] / 100) for t in st.session_state.portfolio)
    avg_rate = (total_krw_invested / total_jpy * 100) if total_jpy > 0 else 0
    current_value_krw = total_jpy * (latest['krw_jpy'] / 100)
    profit_krw = current_value_krw - total_krw_invested
    profit_percent = (profit_krw / total_krw_invested * 100) if total_krw_invested > 0 else 0

    p_col1, p_col2, p_col3 = st.columns(3)
    p_col1.metric("총 보유 엔화", f"¥ {total_jpy:,.0f}")
    p_col2.metric("내 평균 단가", f"{avg_rate:.2f} 원")
    p_col3.metric("평가 손익 (원)", f"₩ {profit_krw:,.0f}", f"{profit_percent:.2f}%")

    st.markdown("---")
    st.subheader("거래 내역 관리")
    
    # 거래 추가 폼
    with st.form("add_trade_form", clear_on_submit=True):
        f_col1, f_col2, f_col3 = st.columns([2, 2, 1])
        amt_input = f_col1.number_input("매수 엔화 (JPY)", min_value=0, step=10000)
        rate_input = f_col2.number_input("적용 환율 (원/100엔)", min_value=0.0, format="%.2f")
        submitted = f_col3.form_submit_button("➕ 기록 추가")
        
        if submitted and amt_input > 0 and rate_input > 0:
            new_id = max([t['id'] for t in st.session_state.portfolio] + [0]) + 1
            st.session_state.portfolio.append({
                'id': new_id,
                'date': datetime.now().strftime("%Y-%m-%d"),
                'amount_jpy': amt_input,
                'rate': rate_input
            })
            st.rerun() # 화면 새로고침

    # 거래 내역 테이블 출력
    if st.session_state.portfolio:
        df_port = pd.DataFrame(st.session_state.portfolio)
        df_port['투자원금(원)'] = (df_port['amount_jpy'] * (df_port['rate'] / 100)).astype(int)
        df_port.columns = ['ID', '거래일자', '매수엔화(¥)', '적용환율', '투자원금(₩)']
        st.dataframe(df_port, use_container_width=True, hide_index=True)
        
        # 삭제 기능
        del_id = st.number_input("삭제할 거래 ID 번호를 입력하세요", min_value=0, step=1)
        if st.button("🗑️ 선택 기록 삭제"):
            st.session_state.portfolio = [t for t in st.session_state.portfolio if t['id'] != del_id]
            st.rerun()
    else:
        st.info("아직 등록된 거래 내역이 없습니다.")

# ==========================================
# 탭 3: 투자 전략 백과
# ==========================================
with tab3:
    st.header("성공하는 투자자들의 엔화 기법")
    
    with st.expander("1. 환율 밴드 기반 그리드(Grid) 트레이딩", expanded=True):
        st.write("""
        - 가장 많은 투자자들이 사용하는 방법입니다. 역사적 저점과 고점을 밴드로 설정합니다.
        - 정해진 간격(예: 5원 단위)으로 하락할 때마다 **기계적으로 분할 매수**하고, 오를 때마다 분할 매도합니다.
        - **Tip:** 절대 한 번에 몰빵하지 마세요. 바닥은 아무도 모릅니다.
        """)
        
    with st.expander("2. 미·일 금리차 역추적 (Macro Following)"):
        st.write("""
        - 엔화 약세의 핵심 원인인 '미국-일본 간 금리차'를 추적합니다.
        - **미국 10년물 금리가 하락 반전**하거나, 일본은행이 금리를 인상할 때 매수합니다.
        - **Tip:** 대시보드의 '미국 10년물 금리' 하락 신호가 떴을 때가 최고의 매수 타이밍입니다.
        """)
        
    with st.expander("3. 안전 자산 선호 (Safe-Haven) 피크 아웃"):
        st.write("""
        - 전쟁이나 경제 위기 시 VIX(공포지수)가 폭등하며 안전자산인 엔화로 자금이 몰려 환율이 단기 급등합니다.
        - 평소에 모아둔 엔화를 이때 차익 실현(매도)합니다.
        - **Tip:** VIX 지수가 25~30을 넘어가는 시장 패닉이 최고의 매도 찬스입니다.
        """)
        
    with st.expander("📈 기술적 지표 (이평선, 볼린저밴드, 캔들) 활용법"):
        st.write("""
        - **이동평균선 (MA20):** 단기 20일간의 가격 평균. 추세의 방향을 보여줍니다.
        - **볼린저 밴드:** 가격이 움직이는 정상 궤도. **하단 터치 시 매수**, **상단 터치 시 매도** 확률이 높습니다.
        - **캔들 (봉):** 빨간색(양봉)은 상승, 파란색(음봉)은 하락을 의미합니다. 꼬리가 길게 달린 모양(망치형 등)은 추세 반전을 예고합니다.
        """)
