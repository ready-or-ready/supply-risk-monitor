"""
홈 페이지 — 서비스 소개
"""
import streamlit as st
from utils.styles import apply_global_styles
from utils.risk_engine import THRESHOLDS

st.set_page_config(
    page_title="공급망 리스크 모니터링",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_global_styles()
st.title("⚠️ 플라스틱 원재료 공급망 마비 대응 솔루션")
st.caption("PP / PE / PVC / PET 원재료 공급망 다중 리스크 모니터링 대시보드")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🎯 서비스 목적")
    st.markdown("""
    석유화학 원재료(PP/PE/PET/PVC)를 쓰는 **국내 제조 중소기업**이
    세 가지 리스크를 통합 모니터링하여 선제적 대응 전략을 수립할 수 있도록 지원합니다.

    - **에너지·원가 리스크**: 국제유가(Brent/WTI) + 환율 + 월별 수입단가 변동
    - **공급 집중 리스크**: PP·PVC·PET 대중국 수입의존(70~85%) + 수입집중도(HHI)
    - **지정학·물류 리스크**: 홍해·호르무즈 항로 봉쇄, 미중 무역분쟁·수출규제
    """)

with col2:
    st.subheader("📌 주요 기능")
    st.markdown("""
    | 메뉴 | 내용 |
    |---|---|
    | 📊 대시보드 | 품목별 위험지수 카드·차트, 수입 의존도, 나프타 시장 시나리오 |
    | 🌏 지정학 리스크 | 키워드 감지 경보 카드, 항로 위험 신호 |
    | 📄 리포트 생성 | 재고·원가 입력 → 맞춤 협상 방향 신호카드, AI 리포트 생성 |
    """)

st.markdown("---")

st.info("""
**📖 서비스 이용 안내**
- 왼쪽 사이드바에서 메뉴를 선택해 각 기능을 이용하세요.
- 데이터는 관세청/산업통상부/한국은행/뉴스 RSS/외교부 기반으로 자동 수집됩니다.
- 위험지수는 5개 공공 지표 룰 기반 가중합산으로 산출되며, **미래 가격 예측이 아닌 현재 리스크 수준 진단** 도구입니다.
""")

with st.expander("위험지수 산식 보기"):
    st.code("""
위험지수 = 국제유가압력점수 (×0.25)   ← yfinance [Brent 10영업일 변동률 + 변동성]
         + 환율압력점수     (×0.15)   ← ECOS [USD/KRW 20영업일 변동률 + 변동성]
         + 수입가격압력점수 (×0.20)   ← 관세청 GW [원화기준 수입단가 전월비 ln변동률]
         + 수입구조취약성점수(×0.20)  ← 관세청 GW [리스크국가의존도 + HHI + Top1의존도]
         + 지정학이벤트노출점수(×0.20) ← 연합뉴스 RSS + 외교부 [14일 키워드 가중합 + 항로가산점]
    """, language="text")

    st.markdown("**품목별 등급 기준** (2020–2024년 과거 분포 기반, P60/P85/P97 분위수)")
    _rows = ""
    for mat, (t1, t2, t3) in THRESHOLDS.items():
        _rows += (
            f"<tr>"
            f"<td style='padding:6px 12px;font-weight:bold'>{mat}</td>"
            f"<td style='padding:6px 12px;background:#e8f5e9'>≤ {t1}</td>"
            f"<td style='padding:6px 12px;background:#fffde7'>{t1+1} ~ {t2}</td>"
            f"<td style='padding:6px 12px;background:#fff3e0'>{t2+1} ~ {t3}</td>"
            f"<td style='padding:6px 12px;background:#ffebee'>> {t3}</td>"
            f"</tr>"
        )
    st.markdown(
        f"<table style='border-collapse:collapse;font-size:13px'>"
        f"<thead><tr style='background:#f5f5f5'>"
        f"<th style='padding:6px 12px'>품목</th>"
        f"<th style='padding:6px 12px'>🟢 낮음</th>"
        f"<th style='padding:6px 12px'>🟡 주의</th>"
        f"<th style='padding:6px 12px'>🟠 경계</th>"
        f"<th style='padding:6px 12px'>🔴 심각</th>"
        f"</tr></thead><tbody>{_rows}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption("PET는 중국 의존도(84%)로 인한 구조적 취약성 때문에 다른 품목보다 임계값이 높게 설정됩니다.")
