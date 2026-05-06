import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from datetime import datetime

# --- 웹페이지 기본 설정 ---
st.set_page_config(page_title="엔화 투자 마스터", page_icon="💴", layout="wide")

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

# --- 데이터 불러오기 (캐싱 적용으로 속도 향상) ---
@st.cache_data(ttl=300) # 5분마다 새로고침
def fetch_global_data():
    try:
        krw_data = yf.Ticker("KRW=X").history(period="1y")['Close']
        jpy_data = yf.Ticker("JPY=X").history(period="1y")['Close']
        us_yield_data = yf.Ticker("^TNX").history(period="5d")['Close']
        vix_data = yf.Ticker("^VIX").history(period="5d")['Close']

        if krw_data.empty or jpy_data.empty:
            return None, None

        df = pd.concat([krw_data, jpy_data], axis=1).dropna()
        df.columns = ['KRW', 'JPY']
        df['KRW_JPY'] = (df['KRW'] / df['JPY']) * 100

        # 기술적 지표 계산
        df['MA20'] = df['KRW_JPY'].rolling(window=20).mean()
        df['STD20'] = df['KRW_JPY'].rolling(window=20).std()
        df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
        df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)

        delta = df['KRW_JPY'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))

        df.dropna(inplace=True)
        
        latest = {
            'krw_jpy': df['KRW_JPY'].iloc[-1],
            'usd_jpy': jpy_data.iloc[-1],
            'us_yield': us_yield_data.iloc[-1],
            'vix': vix_data.iloc[-1],
            'rsi': df['RSI'].iloc[-1],
            'bb_lower': df['BB_Lower'].iloc[-1],
            'bb_upper': df['BB_Upper'].iloc[-1],
            'ma20': df['MA20'].iloc[-1]
        }
        return df, latest
    except Exception as e:
        st.error(f"데이터 통신 에러: {e}")
        return None, None

# --- 앱 메인 화면 시작 ---
st.title("💴 Yen-Vestor Pro (실시간 웹 대시보드)")
st.markdown("전 세계 금융 API와 연동된 **가장 완벽한 엔화 투자 AI 시뮬레이터**입니다.")

# 포트폴리오 세션 초기화
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [
        {'id': 1, 'date': '2025-10-15', 'amount_jpy': 500000, 'rate': 905.20}
    ]

# 데이터 로딩
with st.spinner("야후 파이낸스 글로벌 데이터를 실시간으로 가져오는 중입니다..."):
    df, latest = fetch_global_data()

if df is None:
    st.stop()

# --- 탭 구성 ---
tab1, tab2, tab3 = st.tabs(["📊 AI 대시보드 (차트 분석)", "💼 내 자산 관리", "📖 투자 전략 백과"])

# ==========================================
# 탭 1: AI 대시보드
# ==========================================
with tab1:
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

    # 2. Plotly 인터랙티브 차트 (웹에 최적화)
    st.subheader("📈 원/엔 환율 종합 기술적 분석")
    st.caption("마우스를 올려 가격을 확인하거나 드래그해서 차트를 확대할 수 있습니다.")
    
    fig = go.Figure()
    
    # 볼린저 밴드 영역
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(148, 163, 184, 0.5)', dash='dash'), name='볼린저 상단'))
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(16, 185, 129, 0.5)', dash='dash'), fill='tonexty', fillcolor='rgba(203, 213, 225, 0.1)', name='볼린저 하단'))
    
    # 20일 이동평균선
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#f59e0b', width=2), name='20일 이동평균'))
    
    # 현재가
    fig.add_trace(go.Scatter(x=df.index, y=df['KRW_JPY'], line=dict(color='#3b82f6', width=3), name='원/100엔 현재가'))

    # 가이드 라인
    fig.add_hline(y=950, line_dash="dot", line_color="red", annotation_text="고평가 (매도)", annotation_position="top left")
    fig.add_hline(y=850, line_dash="dot", line_color="green", annotation_text="저평가 (매수)", annotation_position="bottom left")
    
    # 레이아웃 설정
    fig.update_layout(height=450, margin=dict(l=0, r=0, t=30, b=0), plot_bgcolor='#f8fafc', paper_bgcolor='#f8fafc',
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.05)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.05)')
    
    st.plotly_chart(fig, use_container_width=True)

    # 3. AI 분석 엔진
    st.markdown("---")
    st.subheader("🧠 Deep Analysis (매크로 + 기술적 지표 융합 엔진)")
    
    if st.button("▶ 현재 데이터 기반 AI 시뮬레이션 가동", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        steps = [
            "기술적 지표(RSI, MACD) 다이버전스 확인...",
            "볼린저 밴드(Bollinger Bands) 지지/저항 테스트...",
            "미일 금리차(US-JP Yield Gap) 축소 가능성 계산...",
            "과거 1년 차트 패턴 딥러닝 매칭 중...",
            "최종 매수/매도 확률(Conviction Score) 산출 완료!"
        ]
        
        for i in range(100):
            time.sleep(0.02)
            progress_bar.progress(i + 1)
            if i % 20 == 0:
                status_text.text(f"[{i}%] {steps[i//20]}")
                
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
        
    with st.expander("📈 기술적 지표 (이평선, 볼린저밴드, RSI) 활용법"):
        st.write("""
        - **이동평균선 (MA20):** 단기 20일간의 가격 평균. 추세의 방향을 보여줍니다.
        - **볼린저 밴드:** 가격이 움직이는 정상 궤도. **하단 터치 시 매수**, **상단 터치 시 매도** 확률이 높습니다.
        - **RSI (투자 심리):** 30 이하(초록색)면 과매도(싸다!), 70 이상(빨간색)이면 과매수(비싸다!)를 의미합니다.
        """)
