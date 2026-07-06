"""
페이지 2: 지정학 리스크 모니터링 (기능2)
경보 카드 리스트 / 국가별 심각도 / 최근 감지 기사
"""
import streamlit as st
from utils.styles import apply_global_styles
import pandas as pd
import html as _html
from datetime import datetime

from utils.data_fetcher import fetch_market_data, fetch_news_and_notices, fetch_country_shares, HS_CODES, fetch_google_news
from utils.geo_monitor import (classify_events, build_alert_cards,
                               build_mitigation_cards)

st.set_page_config(page_title="지정학 리스크", page_icon="🌏", layout="wide")
apply_global_styles()
st.title("🌏 지정학 리스크 모니터링")
st.caption(f"기준일: {datetime.today().strftime('%Y-%m-%d')}  |  소스: 연합뉴스 RSS (14일) + 외교부 안전공지 (14일)")

# ── 데이터 로딩 ──────────────────────────────────────────
if st.sidebar.button("🔄 데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("뉴스 데이터: 1시간 캐시")

with st.spinner("뉴스 · 외교부 공지 수집 중..."):
    df_rss, df_notice = fetch_news_and_notices(window_days=14)
    df_market = fetch_market_data(days=10)

# Brent 5일 변동률 (경보 카드 근거용)
brent = df_market["Brent"].dropna() if "Brent" in df_market.columns else None
brent_5d = (brent.iloc[-1] / brent.iloc[-6] - 1) * 100 if brent is not None and len(brent) >= 6 else 0.0

# RSS / 공지에 키워드 감지 적용
from utils.geo_monitor import _detect_common, _detect_route
for df in [df_rss, df_notice]:
    if not df.empty:
        df["공통_키워드"] = df["제목"].apply(_detect_common)
        df["항로_키워드"] = df["제목"].apply(_detect_route)

event_agg        = classify_events(df_rss, df_notice)
alert_cards      = build_alert_cards(event_agg, brent_5d)
# 완화 요인: 연합뉴스 RSS가 최신 N건만 유지하므로 구글뉴스로 보완
df_google_mit = fetch_google_news(
    "나프타 지원 OR 석유화학 지원 OR 원재료 지원 OR 원가 지원 OR 나프타 하락 OR 에틸렌 하락 OR 관세 인하",
    window_days=14, max_results=15,
)
# build_mitigation_cards가 df_rss에 완화_키워드 컬럼도 in-place로 채워줌
mitigation_cards = build_mitigation_cards(df_rss, df_notice, df_extra=df_google_mit)

# ── 수집 현황 요약 ────────────────────────────────────────
col1, col2, col3 = st.columns(3)
col1.metric("연합뉴스 RSS 수집", f"{len(df_rss)}건")
col2.metric("외교부 공지 수집", f"{len(df_notice)}건")
_brent_delta = "⚠ 급변동 (경보 트리거)" if abs(brent_5d) >= 1.5 else "정상 범위 (±1.5% 미만)"
col3.metric("Brent 5일 변동률", f"{brent_5d:+.2f}%",
            delta=_brent_delta,
            delta_color="inverse" if abs(brent_5d) >= 1.5 else "off")

st.markdown("---")

# ══════════════════════════════════════════════════════════
# 경보 카드
# ══════════════════════════════════════════════════════════
st.subheader("🚨 리스크 이벤트 경보 카드")

if not alert_cards:
    st.success("✅ 현재 감지된 리스크 이벤트 없음 (평상시)")
else:
    color_map = {"심각": "#ffebee", "경계": "#fff3e0", "주의": "#fffde7", "모니터링": "#e8f5e9"}
    for card in alert_cards:
        bg = color_map.get(card["severity"], "#f5f5f5")

        with st.container():
            explanation_html = (
                f"<br><span style='font-size:12px;color:#1565c0;font-style:italic'>"
                f"ℹ️ {card['explanation']}</span>"
                if card["explanation"] else ""
            )
            sample_html = f"<br><span style='font-size:11px;color:#777'>대표 기사: {_html.escape(card['sample_title'])}</span>" if card['sample_title'] else ""
            html = (
                f"<div style='background:{bg};border-radius:8px;padding:14px 18px;margin-bottom:10px'>"
                f"<span style='font-size:20px'>{card['icon']}</span>"
                f"<strong style='font-size:16px'> {card['risk_type']}</strong>"
                f"<span style='color:#666;font-size:13px'> — {card['severity']}</span>"
                f"{explanation_html}"
                f"<br><span style='font-size:13px'>🔗 영향 경로: <strong>{card['impact_path']}</strong></span>"
                f"<br><span style='font-size:12px;color:#555'>📰 근거: {card['evidence']}</span>"
                f"{sample_html}"
                f"</div>"
            )
            st.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# 리스크 완화 요인 카드
# ══════════════════════════════════════════════════════════
st.subheader("✅ 리스크 완화 요인")
if not mitigation_cards:
    st.info("현재 감지된 완화 요인 없음 (14일 기준 — 정부 지원·가격 인하·물류 정상화 등 키워드 모니터링 중)")
else:
    for card in mitigation_cards:
        kw_str = " · ".join(card["keywords"])
        sample_html = (f"<br><span style='font-size:11px;color:#555'>대표 기사: {_html.escape(card['sample_title'])}</span>"
                       if card["sample_title"] else "")
        html = (
            f"<div style='background:#e8f5e9;border-left:4px solid #2e7d32;"
            f"border-radius:6px;padding:12px 16px;margin-bottom:8px'>"
            f"<strong style='font-size:15px;color:#1b5e20'>✅ {card['type']}</strong>"
            f"<span style='color:#555;font-size:13px'> — {card['count']}건 감지</span>"
            f"<br><span style='font-size:12px;color:#2e7d32'>🔑 감지 키워드: {kw_str}</span>"
            f"<br><span style='font-size:12px;color:#555'>📰 근거: 뉴스 소스 {card['count']}건</span>"
            f"{sample_html}"
            f"</div>"
        )
        st.markdown(html, unsafe_allow_html=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════
# 최근 감지 기사 목록
# ══════════════════════════════════════════════════════════
st.subheader("📰 최근 감지 기사 · 공지")
tab_rss, tab_notice = st.tabs(["연합뉴스 RSS", "외교부 안전공지"])

with tab_rss:
    if df_rss.empty:
        st.info("수집된 RSS 기사 없음")
    else:
        has_risk = (df_rss["공통_키워드"].apply(len) > 0) if "공통_키워드" in df_rss.columns else pd.Series(False, index=df_rss.index)
        has_mit  = (df_rss["완화_키워드"].apply(len) > 0) if "완화_키워드" in df_rss.columns else pd.Series(False, index=df_rss.index)
        df_show = df_rss[has_risk | has_mit].copy()
        if df_show.empty:
            df_show = df_rss
        df_show = df_show[["소스", "제목", "날짜"]].head(30)
        st.dataframe(df_show, width='stretch', hide_index=True)

with tab_notice:
    if df_notice.empty:
        st.info("수집된 외교부 공지 없음")
    else:
        _dn = df_notice.copy().sort_values("날짜", ascending=False, na_position="last")
        _has_kw = "공통_키워드" in _dn.columns

        _df_kw = _dn[_dn["공통_키워드"].apply(len) > 0] if _has_kw else pd.DataFrame()
        _df_no_kw = (_dn[_dn["공통_키워드"].apply(len) == 0].head(5)
                     if _has_kw else _dn.head(5))

        if not _df_kw.empty:
            st.caption(f"**리스크 키워드 감지된 공지** ({len(_df_kw)}건)")
            st.dataframe(_df_kw[["제목", "날짜"]].reset_index(drop=True),
                         use_container_width=True, hide_index=True)
        else:
            st.caption("리스크 키워드 감지된 공지 없음 (14일 기준)")

        if not _df_no_kw.empty:
            st.caption("**최근 공지 (키워드 미감지, 최신 5건)**")
            st.dataframe(_df_no_kw[["제목", "날짜"]].reset_index(drop=True),
                         use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("""
**리스크 키워드 감지 기준** (연합뉴스 RSS + 외교부 공지 합산): 중국 수출규제·화학공장·전력난·나프타·물류, \
미중 관세·무역분쟁, 대만해협, 미국 에탄·텍사스, 사우디 감산, 러시아, 우크라이나, 이란 \
— 국가별 건당 10~30점, 국가점수 상한 100점

**완화 요인 감지 기준** (연합뉴스 RSS): 나프타 지원·기초유분 지원·원재료 지원·석유화학 지원 / \
판매가 인하·공급가 인하 / 나프타 하락·에틸렌 하락 / 항로 재개·물류 정상화·공급 정상화 / 관세 인하

**항로 가산점**: 홍해·수에즈·호르무즈 — 14일 내 감지 기사·공지 수 기준, 최대 +20점 \
(1\~2건: +5 / 3\~5건: +10 / 6건 이상: +20)

※ 항로 봉쇄 등 중동 이벤트는 '위험지수'에서 지정학이벤트노출점수(뉴스 선포착)와 \
수입구조취약성점수(리스크국가 의존도 상시 반영)로 보완합니다.
""")
