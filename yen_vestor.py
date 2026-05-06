import tkinter as tk
from tkinter import ttk, messagebox
import time
import datetime
import threading
import re
import sys
import os  # 완전 종료를 위한 os 모듈 추가

# 안정적인 금융 API 라이브러리 사용
try:
    import yfinance as yf
    import pandas as pd
    import numpy as np

    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib import rc
    import platform

    # OS별 한글 폰트 깨짐 방지 설정
    if platform.system() == 'Windows':
        rc('font', family='Malgun Gothic')
    elif platform.system() == 'Darwin':  # Mac
        rc('font', family='AppleGothic')
    else:
        rc('font', family='NanumGothic')
    plt.rcParams['axes.unicode_minus'] = False
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

ANALYSIS_STEPS = [
    "거시 경제 지표 로드 중...",
    "원/엔(KRW/JPY) 역사적 밴드 하단 이탈 여부 확인...",
    "이동평균선(MA20) 추세 방향성 연산 중...",
    "볼린저 밴드(Bollinger Bands) 하단 지지선 테스트...",
    "RSI(상대강도지수) 기반 과매수/과매도 심리 분석...",
    "미일 금리차(US-JP Yield Gap) 축소 가능성 계산...",
    "글로벌 리스크 오프(Safe Haven) 자금 이동 추적...",
    "과거 1년 차트 패턴 딥러닝 매칭 중...",
    "기술적 + 거시경제(Macro) 데이터 통합 가중치 부여...",
    "최종 매수/매도 확률(Conviction Score) 산출 완료!"
]


# --- 💡 지표별 의미 해석기 ---
def get_krw_status(val):
    if val <= 880:
        return "🟢 강력 매수 (매우 쌈)", "#10b981"
    elif val <= 910:
        return "🔵 분할 매수 (저평가)", "#3b82f6"
    elif val >= 950:
        return "🔴 매도 권장 (고평가)", "#ef4444"
    else:
        return "⚪ 박스권 (관망)", "#94a3b8"


def get_usd_status(val):
    if val >= 150:
        return "🟢 BOJ 개입 임박 (엔화 매수)", "#10b981"
    elif val <= 140:
        return "🔴 엔화 이미 강세 (추격 금지)", "#ef4444"
    else:
        return "⚪ 일반적인 흐름", "#94a3b8"


def get_yield_status(val):
    if val >= 4.5:
        return "🔴 달러 강세 (엔화 약세장)", "#ef4444"
    elif val <= 4.0:
        return "🟢 금리 인하 (엔화 강세 전환점)", "#10b981"
    else:
        return "⚪ 중립 (방향성 탐색중)", "#94a3b8"


def get_vix_status(val):
    if val >= 25:
        return "🔴 패닉장 (엔화 단기 폭등/차익실현)", "#ef4444"
    elif val >= 20:
        return "🟡 경계장 (안전자산 수요 쏠림)", "#f59e0b"
    else:
        return "🟢 평온장 (엔화 조용히 매집할 때)", "#10b981"


class YenVestorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("엔화 투자 마스터 (Yen-Vestor Pro) - 기술적 분석 통합 버젼")
        self.root.geometry("1100x950")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 전역 상태 데이터 (기술적 지표 추가)
        self.indicators = {
            'krw_jpy': 885.50,
            'usd_jpy': 155.20,
            'us_yield': 4.45,
            'vix': 14.5,
            'rsi': 50.0,
            'bb_lower': 850.0,
            'ma20': 880.0
        }

        self.portfolio = [
            {'id': 1, 'date': '2025-10-15', 'amount_jpy': 500000, 'rate': 905.20}
        ]

        style = ttk.Style()
        style.theme_use('clam')

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=10)

        self.tab_dashboard = ttk.Frame(self.notebook)
        self.tab_portfolio = ttk.Frame(self.notebook)
        self.tab_strategy = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_dashboard, text=' AI 대시보드 (차트 분석) ')
        self.notebook.add(self.tab_portfolio, text=' 내 자산 관리 ')
        self.notebook.add(self.tab_strategy, text=' 투자 전략 백과 ')

        self.build_dashboard_tab()
        self.build_portfolio_tab()
        self.build_strategy_tab()

    # --- 1. AI 대시보드 탭 ---
    def build_dashboard_tab(self):
        # 1. 상단 매크로 지표 프레임
        self.ind_frame = tk.Frame(self.tab_dashboard, bg="#0f172a", pady=15)
        self.ind_frame.pack(fill='x')

        # 이모지 대신 텍스트로 대체하여 Matplotlib 폰트 깨짐 방지
        self.btn_refresh = tk.Button(self.ind_frame, text="[새로고침] 실시간 데이터 및 차트 분석", bg="#3b82f6", fg="white",
                                     font=("Arial", 11, "bold"), relief="flat", command=self.refresh_realtime_data,
                                     padx=10, pady=5)
        self.btn_refresh.pack(side="right", padx=20)

        def create_indicator(parent, title, info_cmd=None):
            frame = tk.Frame(parent, bg="#0f172a")
            frame.pack(side="left", expand=True)

            top_frame = tk.Frame(frame, bg="#0f172a")
            top_frame.pack()

            lbl_title = tk.Label(top_frame, text=title, bg="#0f172a", fg="#94a3b8", font=("Arial", 11))
            lbl_title.pack(side="left")

            if info_cmd:
                btn_info = tk.Button(top_frame, text="?", bg="#334155", fg="white", font=("Arial", 8, "bold"),
                                     relief="flat", command=info_cmd, padx=4, cursor="hand2")
                btn_info.pack(side="left", padx=5)

            lbl_val = tk.Label(frame, text="대기중", font=("Arial", 18, "bold"), bg="#0f172a", fg="white")
            lbl_val.pack(pady=(5, 0))

            lbl_status = tk.Label(frame, text="-", font=("Arial", 10, "bold"), bg="#0f172a", fg="#94a3b8")
            lbl_status.pack(pady=(0, 5))

            return lbl_val, lbl_status

        self.lbl_krw, self.stat_krw = create_indicator(self.ind_frame, "💰 현재 환율(원/100엔)")
        self.lbl_usd, self.stat_usd = create_indicator(self.ind_frame, "달러/엔", self.info_usd_jpy)
        self.lbl_yield, self.stat_yield = create_indicator(self.ind_frame, "미 국채 10년물", self.info_us_yield)
        self.lbl_vix, self.stat_vix = create_indicator(self.ind_frame, "VIX 공포지수", self.info_vix)

        self.lbl_krw.config(fg="#fbbf24", font=("Arial", 22, "bold"))
        self.update_indicator_labels()

        # 2. 중단 기술적 분석 차트 프레임 (듀얼 차트)
        chart_container = tk.Frame(self.tab_dashboard)
        chart_container.pack(fill='both', expand=True, padx=10, pady=5)

        chart_header = tk.Frame(chart_container)
        chart_header.pack(fill='x', pady=(5, 0))

        tk.Label(chart_header, text="📈 원/엔 환율 종합 기술적 분석 (Price, 이동평균, 볼린저밴드, RSI)", font=("Arial", 12, "bold"),
                 fg="#1e293b").pack(side="left")
        tk.Button(chart_header, text="[?] 기술적 지표란?", bg="#10b981", fg="white", font=("Arial", 9, "bold"), relief="flat",
                  command=self.info_technical, padx=8).pack(side="right")

        if HAS_MATPLOTLIB:
            self.fig = plt.figure(figsize=(10, 5.5), dpi=100)
            self.fig.patch.set_facecolor('#f8fafc')

            # 초기 안내 화면용 임시 축
            self.ax = self.fig.add_subplot(111)
            self.ax.set_facecolor('#f8fafc')
            self.ax.text(0.5, 0.5, "우측 상단의 '[새로고침] 실시간 데이터 및 차트 분석' 버튼을 눌러주세요.",
                         horizontalalignment='center', verticalalignment='center', color='#64748b', fontsize=12,
                         fontweight='bold')
            self.ax.set_xticks([])
            self.ax.set_yticks([])

            self.canvas = FigureCanvasTkAgg(self.fig, master=chart_container)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill='both', expand=True, pady=5)
        else:
            tk.Label(chart_container, text="\n차트를 보려면 터미널에서 'pip install matplotlib pandas' 를 설치해주세요.\n",
                     fg="red").pack()

        # 3. 하단 AI 분석 프레임
        analysis_frame = ttk.LabelFrame(self.tab_dashboard, text="Deep Analysis (매크로 + 기술적 지표 융합 엔진)")
        analysis_frame.pack(fill='x', padx=10, pady=5)

        top_ctrl = tk.Frame(analysis_frame)
        top_ctrl.pack(fill='x', pady=5)

        self.btn_analyze = tk.Button(top_ctrl, text="▶ 현재 데이터 기반 AI 알고리즘 가동", font=("Arial", 11, "bold"), bg="#2563eb",
                                     fg="white", command=self.start_analysis, relief="flat", padx=20, pady=5)
        self.btn_analyze.pack()

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(analysis_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill='x', padx=50, pady=2)

        self.lbl_analysis_step = ttk.Label(analysis_frame, text="대기 중...", font=("Arial", 10, "italic"),
                                           foreground="#64748b")
        self.lbl_analysis_step.pack()

        self.txt_result = tk.Text(analysis_frame, height=6, state='disabled', bg='#f1f5f9', font=("Arial", 11),
                                  relief="flat")
        self.txt_result.pack(fill='both', expand=True, padx=20, pady=5)

    # --- 꿀팁(도움말) 팝업 기능 ---
    def info_usd_jpy(self):
        msg = "💡 [ 달러/엔 환율 (USD/JPY) ]\n\n150엔 돌파 시 (엔화 매수 적기):\n달러/엔이 150엔 근처로 가면 일본은행(BOJ)의 시장 개입(금리 인상 등) 확률이 높아져 엔화가 강세(원/엔 상승)로 전환될 가능성이 큽니다."
        messagebox.showinfo("지표 가이드 - 달러/엔", msg)

    def info_us_yield(self):
        msg = "💡 [ 미국 10년물 국채 금리 ]\n\n금리 4.0% 이하 하락 시 (엔화 매수 적기):\n미국 금리가 꺾이면 글로벌 자금이 일본으로 돌아가며 엔화가 급격히 강세를 띕니다. 금리 하락 반전이 최고의 매수 타이밍입니다."
        messagebox.showinfo("지표 가이드 - 미 국채", msg)

    def info_vix(self):
        msg = "💡 [ VIX 공포지수 ]\n\n패닉장 (25~30 이상 돌파 시 - 엔화 매도 적기):\n위기가 터지면 안전자산인 엔화로 돈이 몰려 환율이 폭등합니다. 이때가 쥐고 있던 엔화를 비싸게 팔(차익 실현) 최고의 기회입니다."
        messagebox.showinfo("지표 가이드 - VIX", msg)

    def info_technical(self):
        msg = (
            "📈 [ 차트 기술적 지표 가이드 ]\n\n"
            "주식처럼 환율도 차트 분석이 핵심입니다. 이 프로그램은 프로 트레이더들의 3대 지표를 자동 계산합니다.\n\n"
            "1. 🟡 이동평균선 (20일선 MA):\n"
            " - 환율의 '단기 추세'를 보여줍니다. 주가가 이 선 위에 있으면 상승세, 아래에 있으면 하락세입니다.\n\n"
            "2. ☁️ 볼린저 밴드 (회색 점선 밴드):\n"
            " - 환율이 움직일 '정상적인 고속도로'입니다.\n"
            " - 하단 밴드 이탈: 비정상적으로 너무 많이 떨어짐. 튕겨 올라갈 확률 높음 (매수 찬스!)\n"
            " - 상단 밴드 터치: 너무 급하게 오름. 다시 떨어질 확률 높음 (매도 찬스!)\n\n"
            "3. 🟣 RSI (상대강도지수, 하단 차트):\n"
            " - 시장의 '투자 심리(열기)'를 0~100으로 나타냅니다.\n"
            " - 30 이하 (초록색): 다들 던져서 헐값이 된 상태. (과매도 = 매수 줍줍 찬스)\n"
            " - 70 이상 (빨간색): 다들 흥분해서 너무 비싸진 상태. (과매수 = 매도 도망 찬스)"
        )
        messagebox.showinfo("차트 기술적 지표 완벽 가이드", msg)

    def update_indicator_labels(self):
        krw = self.indicators['krw_jpy']
        usd = self.indicators['usd_jpy']
        yld = self.indicators['us_yield']
        vix = self.indicators['vix']

        self.lbl_krw.config(text=f"{krw:.2f}")
        self.lbl_usd.config(text=f"{usd:.2f}")
        self.lbl_yield.config(text=f"{yld:.2f}%")
        self.lbl_vix.config(text=f"{vix:.1f}")

        k_txt, k_col = get_krw_status(krw)
        u_txt, u_col = get_usd_status(usd)
        y_txt, y_col = get_yield_status(yld)
        v_txt, v_col = get_vix_status(vix)

        self.stat_krw.config(text=k_txt, fg=k_col)
        self.stat_usd.config(text=u_txt, fg=u_col)
        self.stat_yield.config(text=y_txt, fg=y_col)
        self.stat_vix.config(text=v_txt, fg=v_col)

    def refresh_realtime_data(self):
        if not HAS_YFINANCE:
            messagebox.showerror("라이브러리 필요", "터미널에서 'pip install yfinance pandas numpy'를 설치해주세요.")
            return

        self.btn_refresh.config(text="[대기중] 글로벌 API 및 차트 딥러닝 중...", state="disabled", bg="#64748b")
        threading.Thread(target=self._fetch_data_thread, daemon=True).start()

    def _fetch_data_thread(self):
        try:
            # 1년 치 과거 데이터를 불러옵니다.
            krw_data = yf.Ticker("KRW=X").history(period="1y")['Close']
            jpy_data = yf.Ticker("JPY=X").history(period="1y")['Close']

            us_yield_data = yf.Ticker("^TNX").history(period="5d")['Close']
            vix_data = yf.Ticker("^VIX").history(period="5d")['Close']

            if krw_data.empty or jpy_data.empty:
                raise ValueError("환율 API 응답이 비어있습니다.")

            # 최신가 계산
            usd_krw_latest = float(krw_data.iloc[-1])
            usd_jpy_latest = float(jpy_data.iloc[-1])
            krw_jpy_latest = (usd_krw_latest / usd_jpy_latest) * 100
            us_yield_latest = float(us_yield_data.iloc[-1])
            vix_latest = float(vix_data.iloc[-1])

            # --- 🛠️ 퀀트(Quant) 기술적 지표 계산 로직 ---
            df = pd.concat([krw_data, jpy_data], axis=1).dropna()
            df.columns = ['KRW', 'JPY']
            df['KRW_JPY'] = (df['KRW'] / df['JPY']) * 100

            # 1. 이동평균선 (20일 MA)
            df['MA20'] = df['KRW_JPY'].rolling(window=20).mean()

            # 2. 볼린저 밴드 (표준편차 * 2)
            df['STD20'] = df['KRW_JPY'].rolling(window=20).std()
            df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
            df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)

            # 3. RSI (14일 상대강도지수)
            delta = df['KRW_JPY'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss
            df['RSI'] = 100 - (100 / (1 + rs))

            # NaN 값(초기 20일 데이터) 제거하여 차트 깨짐 방지
            df.dropna(inplace=True)

            self.root.after(0, self._apply_fetched_data, krw_jpy_latest, usd_jpy_latest, us_yield_latest, vix_latest,
                            df)

        except Exception as e:
            self.root.after(0, self._handle_fetch_error, str(e))

    def _apply_fetched_data(self, krw_jpy, usd_jpy, us_yield, vix, df):
        # 1. 지표 데이터 및 기술적 지표 상태 갱신
        self.indicators['krw_jpy'] = round(krw_jpy, 2)
        self.indicators['usd_jpy'] = round(usd_jpy, 2)
        self.indicators['us_yield'] = round(us_yield, 2)
        self.indicators['vix'] = round(vix, 2)

        # AI가 읽어들일 수 있도록 최신 기술적 지표 저장
        self.indicators['rsi'] = round(df['RSI'].iloc[-1], 2)
        self.indicators['bb_lower'] = round(df['BB_Lower'].iloc[-1], 2)
        self.indicators['bb_upper'] = round(df['BB_Upper'].iloc[-1], 2)
        self.indicators['ma20'] = round(df['MA20'].iloc[-1], 2)

        self.update_indicator_labels()
        self.update_portfolio_ui()

        # 2. 듀얼 서브플롯(Subplots) 차트 그리기
        if HAS_MATPLOTLIB and hasattr(self, 'fig'):
            self.fig.clf()  # 캔버스 초기화

            # 레이아웃 분할 (위 70%: 가격+볼린저, 아래 30%: RSI)
            ax1 = self.fig.add_subplot(3, 1, (1, 2))
            ax2 = self.fig.add_subplot(3, 1, 3, sharex=ax1)  # x축 공유

            hist_dates = [d.strftime("%y.%m.%d") for d in df.index]
            x_vals = np.arange(len(hist_dates))

            # --- [ 상단 차트: 가격 + 이동평균선 + 볼린저 밴드 ] ---
            ax1.set_facecolor('#f8fafc')

            # 가격선 및 영역
            ax1.fill_between(x_vals, df['KRW_JPY'], min(df['BB_Lower']) - 5, color='#3b82f6', alpha=0.1)
            ax1.plot(x_vals, df['KRW_JPY'], color='#3b82f6', linewidth=2, label="KRW/JPY 현재가")

            # 이동평균선
            ax1.plot(x_vals, df['MA20'], color='#f59e0b', linewidth=1.5, label="20일 이동평균 (추세)")

            # 볼린저 밴드
            ax1.plot(x_vals, df['BB_Upper'], color='#94a3b8', linewidth=1, linestyle='--', label="볼린저 상단 (저항)")
            ax1.plot(x_vals, df['BB_Lower'], color='#10b981', linewidth=1, linestyle='--', label="볼린저 하단 (지지)")
            ax1.fill_between(x_vals, df['BB_Upper'], df['BB_Lower'], color='#cbd5e1', alpha=0.15)

            # 현재가 말풍선 표시
            current_rate = df['KRW_JPY'].iloc[-1]
            ax1.plot(x_vals[-1], current_rate, marker='o', color='#ef4444', markersize=6)
            ax1.annotate(f"{current_rate:.2f}", xy=(x_vals[-1], current_rate), xytext=(-30, 15),
                         textcoords='offset points', fontweight='bold', color='white',
                         bbox=dict(boxstyle="round,pad=0.3", fc="#ef4444", ec="none"))

            ax1.grid(True, linestyle=':', alpha=0.5)
            ax1.legend(loc="upper left", fontsize=8)
            ax1.set_ylabel("KRW / 100 JPY")

            # --- [ 하단 차트: RSI (투자 심리) ] ---
            ax2.set_facecolor('#f8fafc')
            ax2.plot(x_vals, df['RSI'], color='#8b5cf6', linewidth=1.5, label="RSI (14일)")

            # 과매수(70) / 과매도(30) 기준선
            ax2.axhline(y=70, color='#ef4444', linestyle='--', alpha=0.5)
            ax2.axhline(y=30, color='#10b981', linestyle='--', alpha=0.5)

            # 70 이상 빨간색 칠하기, 30 이하 초록색 칠하기
            ax2.fill_between(x_vals, df['RSI'], 70, where=(df['RSI'] >= 70), color='#ef4444', alpha=0.3)
            ax2.fill_between(x_vals, df['RSI'], 30, where=(df['RSI'] <= 30), color='#10b981', alpha=0.3)

            ax2.set_ylim(10, 90)
            ax2.grid(True, linestyle=':', alpha=0.5)
            ax2.legend(loc="upper left", fontsize=8)
            ax2.set_ylabel("RSI (심리)")

            # X축 세팅 (겹치지 않게 조절)
            n_ticks = 6
            tick_idx = np.linspace(0, len(hist_dates) - 1, n_ticks, dtype=int)
            ax2.set_xticks(tick_idx)
            ax2.set_xticklabels([hist_dates[i] for i in tick_idx])

            self.fig.tight_layout()  # 차트 간격 자동 맞춤
            self.canvas.draw()

        self.btn_refresh.config(text="[새로고침] 실시간 데이터 및 차트 분석", state="normal", bg="#3b82f6")

    def _handle_fetch_error(self, err_msg):
        self.btn_refresh.config(text="[새로고침] 실시간 데이터 및 차트 분석", state="normal", bg="#3b82f6")
        messagebox.showerror("데이터 갱신 실패", f"글로벌 API 통신 중 오류가 발생했습니다.\n인터넷 연결을 확인해주세요.\n\n상세내용: {err_msg}")

    def start_analysis(self):
        self.btn_analyze.config(state='disabled')
        self.txt_result.config(state='normal')
        self.txt_result.delete(1.0, tk.END)
        self.txt_result.config(state='disabled')
        self.progress_var.set(0)
        self.run_simulation_step(1)

    def run_simulation_step(self, step):
        self.progress_var.set(step)
        if step % 10 == 0:
            step_idx = int(step / 10) - 1
            if step_idx < len(ANALYSIS_STEPS):
                self.lbl_analysis_step.config(text=f"[{step}%] {ANALYSIS_STEPS[step_idx]}")

        if step < 100:
            self.root.after(30, self.run_simulation_step, step + 1)
        else:
            self.lbl_analysis_step.config(text="분석 완료!")
            self.show_analysis_result()
            self.btn_analyze.config(state='normal')

    # --- 🧠 AI 엔진: 매크로 지표 + [새로운 차트 기술적 지표] 통합 스코어링 ---
    def show_analysis_result(self):
        score = 50
        reasons = []

        cur_price = self.indicators['krw_jpy']

        # [1] 기술적 지표 분석 (신규 추가)
        if self.indicators['rsi'] <= 30:
            score += 20;
            reasons.append(f"🟣 RSI {self.indicators['rsi']}% (과매도): 시장의 투매가 멈추고 기술적 반등이 강하게 임박했습니다.")
        elif self.indicators['rsi'] >= 70:
            score -= 20;
            reasons.append(f"🟣 RSI {self.indicators['rsi']}% (과매수): 단기 과열 상태입니다. 곧 조정이 예상됩니다.")

        if cur_price <= self.indicators['bb_lower'] * 1.01:  # 밴드 하단 근접
            score += 15;
            reasons.append(f"☁️ 볼린저 밴드 하단 터치: 통계적으로 가격이 위로 튕겨오를 확률이 95% 이상인 저점입니다.")
        elif cur_price >= self.indicators['bb_upper'] * 0.99:
            score -= 15;
            reasons.append(f"☁️ 볼린저 밴드 상단 터치: 저항선에 부딪혀 곧 가격이 하락할 가능성이 큽니다.")

        if cur_price > self.indicators['ma20']:
            score += 5;
            reasons.append(f"🟡 이동평균선 상회: 20일선 위에 있어 단기 추세가 우상향(상승세)을 타고 있습니다.")
        else:
            score -= 5;
            reasons.append(f"🟡 이동평균선 하회: 20일선 아래에 있어 단기 추세가 다소 꺾인 상태입니다.")

        # [2] 매크로(거시 경제) 지표 분석
        if self.indicators['usd_jpy'] > 150:
            score += 10;
            reasons.append("🌎 달러/엔 150엔 돌파: BOJ의 환율 방어 개입 및 금리 인상 압박으로 엔화 가치 상승 기대.")

        if self.indicators['us_yield'] > 4.5:
            score -= 10;
            reasons.append("🌎 미 국채 10년물 강세: 미국 금리가 높아 일본을 이탈하는 자금이 많아 엔화 약세 유지.")
        elif self.indicators['us_yield'] < 4.0:
            score += 15;
            reasons.append("🌎 미 국채 금리 하락: 미-일 금리차 축소로, 글로벌 자금이 다시 엔화로 몰려들 좋은 환경입니다.")

        if self.indicators['vix'] > 25:
            score += 15;
            reasons.append("🚨 VIX 공포지수 급등: 글로벌 위기로 인해 안전자산(엔화)의 급격한 수요가 몰리고 있습니다.")

        # 제한 처리
        score = max(0, min(100, int(score)))

        action = 'HOLD (관망)'
        if score >= 80:
            action = 'STRONG BUY (영혼까지 끌어모아 강력 매수)'
        elif score >= 60:
            action = 'BUY (분할 매수 권장)'
        elif score <= 20:
            action = 'STRONG SELL (뒤도 보지 말고 전량 매도)'
        elif score <= 40:
            action = 'SELL (수익 실현 / 분할 매도)'

        result_text = f" ■ AI 통합 최종 판단: {action}\n"
        result_text += f" ■ 매수 확신도 (Score): {score} / 100\n\n"
        result_text += " [차트 + 매크로 종합 분석 요약]\n"
        for i, r in enumerate(reasons, 1):
            result_text += f"  {i}. {r}\n"

        self.txt_result.config(state='normal')
        self.txt_result.insert(tk.END, result_text)
        self.txt_result.config(state='disabled')

    # --- 2. 포트폴리오 관리 탭 ---
    def build_portfolio_tab(self):
        self.summary_frame = ttk.LabelFrame(self.tab_portfolio, text="자산 요약")
        self.summary_frame.pack(fill='x', padx=10, pady=10)

        self.lbl_total_jpy = ttk.Label(self.summary_frame, font=("Arial", 14, "bold"))
        self.lbl_total_jpy.grid(row=0, column=0, padx=20, pady=15)

        self.lbl_avg_rate = ttk.Label(self.summary_frame, font=("Arial", 14, "bold"))
        self.lbl_avg_rate.grid(row=0, column=1, padx=20, pady=15)

        self.lbl_profit = ttk.Label(self.summary_frame, font=("Arial", 14, "bold"))
        self.lbl_profit.grid(row=0, column=2, padx=20, pady=15)

        columns = ("id", "date", "jpy", "rate", "krw")
        self.tree = ttk.Treeview(self.tab_portfolio, columns=columns, show="headings", height=8)
        self.tree.heading("id", text="ID")
        self.tree.heading("date", text="거래 일자")
        self.tree.heading("jpy", text="매수 엔화 (¥)")
        self.tree.heading("rate", text="적용 환율")
        self.tree.heading("krw", text="투자 원금 (₩)")

        self.tree.column("id", width=40, anchor='center')
        self.tree.column("date", width=100, anchor='center')
        self.tree.column("jpy", width=120, anchor='e')
        self.tree.column("rate", width=100, anchor='e')
        self.tree.column("krw", width=120, anchor='e')
        self.tree.pack(fill='both', expand=True, padx=10, pady=5)

        ctrl_frame = ttk.Frame(self.tab_portfolio)
        ctrl_frame.pack(fill='x', padx=10, pady=10)

        ttk.Label(ctrl_frame, text="매수 엔화(JPY):").grid(row=0, column=0, padx=5)
        self.ent_jpy = ttk.Entry(ctrl_frame, width=15)
        self.ent_jpy.grid(row=0, column=1, padx=5)

        ttk.Label(ctrl_frame, text="환율(원/100엔):").grid(row=0, column=2, padx=5)
        self.ent_rate = ttk.Entry(ctrl_frame, width=10)
        self.ent_rate.grid(row=0, column=3, padx=5)

        ttk.Button(ctrl_frame, text="추가", command=self.add_trade).grid(row=0, column=4, padx=10)
        ttk.Button(ctrl_frame, text="선택 삭제", command=self.delete_trade).grid(row=0, column=5, padx=10)

        self.update_portfolio_ui()

    def update_portfolio_ui(self):
        total_jpy = sum(t['amount_jpy'] for t in self.portfolio)
        total_krw_invested = sum(t['amount_jpy'] * (t['rate'] / 100) for t in self.portfolio)
        avg_rate = (total_krw_invested / total_jpy * 100) if total_jpy > 0 else 0
        current_value_krw = total_jpy * (self.indicators['krw_jpy'] / 100)
        profit_krw = current_value_krw - total_krw_invested
        profit_percent = (profit_krw / total_krw_invested * 100) if total_krw_invested > 0 else 0

        self.lbl_total_jpy.config(text=f"총 보유 엔화\n¥ {total_jpy:,.0f}")
        self.lbl_avg_rate.config(text=f"내 평균 단가\n{avg_rate:.2f} 원")

        sign = "+" if profit_krw > 0 else ""
        if profit_krw > 0:
            profit_color = "#ef4444"
        elif profit_krw < 0:
            profit_color = "#3b82f6"
        else:
            profit_color = "black"

        self.lbl_profit.config(text=f"평가 손익\n{sign}{profit_krw:,.0f} 원 ({sign}{profit_percent:.2f}%)",
                               foreground=profit_color)

        for item in self.tree.get_children():
            self.tree.delete(item)

        for t in self.portfolio:
            invested = int(t['amount_jpy'] * (t['rate'] / 100))
            self.tree.insert("", "end", values=(
                t['id'], t['date'], f"¥ {t['amount_jpy']:,.0f}", f"{t['rate']:.2f}", f"₩ {invested:,.0f}"
            ))

    def add_trade(self):
        try:
            amt = float(self.ent_jpy.get())
            rate = float(self.ent_rate.get())
            new_id = max([t['id'] for t in self.portfolio] + [0]) + 1

            self.portfolio.append({
                'id': new_id,
                'date': datetime.datetime.now().strftime("%Y-%m-%d"),
                'amount_jpy': amt,
                'rate': rate
            })

            self.ent_jpy.delete(0, tk.END)
            self.ent_rate.delete(0, tk.END)
            self.update_portfolio_ui()
            messagebox.showinfo("성공", "거래 내역이 추가되었습니다.")
        except ValueError:
            messagebox.showerror("입력 오류", "금액과 환율에는 숫자만 입력해주세요.")

    def delete_trade(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("선택 오류", "삭제할 거래 내역을 선택해주세요.")
            return

        item_values = self.tree.item(selected_item[0], "values")
        del_id = int(item_values[0])

        self.portfolio = [t for t in self.portfolio if t['id'] != del_id]
        self.update_portfolio_ui()

    # --- 3. 투자 전략 탭 ---
    def build_strategy_tab(self):
        txt_strategy = tk.Text(self.tab_strategy, wrap='word', font=("Arial", 11), bg='#f8f9fa')
        txt_strategy.pack(expand=True, fill='both', padx=20, pady=20)

        content = """[ 투자 백과: 성공하는 투자자들의 엔화 기법 ]\n\n"""
        content += "1. 환율 밴드 기반 그리드(Grid) 트레이딩\n"
        content += " - 가장 많은 투자자들이 사용하는 방법입니다. 역사적 저점과 고점을 밴드로 설정하고,\n"
        content += "   정해진 간격(예: 5원 단위)으로 분할 매수 및 분할 매도를 기계적으로 반복합니다.\n"
        content += " - Tip: 절대 한 번에 몰빵하지 마세요.\n\n"

        content += "2. 미·일 금리차 역추적 (Macro Following)\n"
        content += " - 엔화 약세의 핵심 원인인 '미국-일본 간 금리차'를 추적합니다.\n"
        content += " - 미국 10년물 금리가 하락 반전하거나, 일본은행이 금리를 인상할 때 매수합니다.\n"
        content += " - Tip: 대시보드의 '미국 10년물 금리' 하락이 최고의 매수 타이밍입니다.\n\n"

        content += "3. 안전 자산 선호 (Safe-Haven) 피크 아웃\n"
        content += " - 전쟁이나 경제 위기 시 VIX(공포지수)가 폭등하며 안전자산인 엔화로 자금이 몰려 환율이 급등합니다.\n"
        content += " - 평소에 모아둔 엔화를 이때 차익 실현합니다.\n"
        content += " - Tip: VIX 지수가 25~30을 넘어가는 시장 패닉이 최고의 매도 찬스입니다.\n"

        txt_strategy.insert(tk.END, content)
        txt_strategy.config(state='disabled')

    def on_closing(self):
        try:
            self.root.destroy()
        except:
            pass
        os._exit(0)  # 완벽하고 깔끔한 백그라운드 프로세스 강제 종료


if __name__ == "__main__":
    root = tk.Tk()
    app = YenVestorApp(root)
    root.mainloop()
