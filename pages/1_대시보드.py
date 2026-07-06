"""
페이지 1: 원재료별 조기경보 대시보드 (기능1 + 기능3)
위험지수 카드 / 가격 추세 차트 / 수입 의존도 / NCC 시나리오 / 리스크 매핑 테이블
"""
import streamlit as st
from utils.styles import apply_global_styles
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

from utils.data_fetcher import (
    fetch_monthly_unit_price, fetch_country_shares,
    fetch_usd_krw_monthly, fetch_market_data, load_ncc_spread,
    fetch_news_and_notices, fetch_google_news,
    fetch_usa_issues, fetch_china_issues,
    HS_CODES, RISK_CODES,
)
from utils.risk_engine import (
    calc_oil_score, calc_fx_score, calc_imp_scores,
    calc_vuln_scores, calc_geo_scores, calc_risk_results,
    top_contributors, risk_grade, grade_icon,
)
from utils.report_builder import ncc_spread_summary, classify_scenario, get_buyer_insight, SCENARIO_DETAIL

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide")
apply_global_styles()
st.title("📊 원재료별 조기경보 대시보드")
st.caption(f"기준일: {datetime.today().strftime('%Y-%m-%d')}  |  데이터: 관세청 GW · yfinance · ECOS · 연합뉴스 RSS · 구글뉴스 · 외교부")

# ── 기간 설정 ─────────────────────────────────────────────
today     = datetime.today()
SCORE_END = today.strftime("%Y%m")
SCORE_STRT= (today - timedelta(days=180)).strftime("%Y%m")
VULN_STRT = (today - timedelta(days=210)).strftime("%Y%m")
VULN_END  = SCORE_END

# ── 데이터 로딩 ──────────────────────────────────────────
try:
    with st.spinner("데이터 수집 중... (관세청 API 응답에 30초 내외 소요될 수 있습니다)"):
        df_market     = fetch_market_data(days=35)
        krw_monthly   = fetch_usd_krw_monthly(SCORE_STRT, SCORE_END)
        df_ncc        = load_ncc_spread()
        df_rss, df_notice = fetch_news_and_notices()
        monthly_data   = {mat: fetch_monthly_unit_price(mat, SCORE_STRT, SCORE_END) for mat in HS_CODES}
        import_shares  = {mat: fetch_country_shares(mat, VULN_STRT, VULN_END) for mat in HS_CODES}
except Exception as _e:
    st.error(
        f"데이터 수집 중 오류가 발생했습니다. 잠시 후 사이드바 **🔄 데이터 새로고침** 버튼을 눌러주세요.\n\n"
        f"_(오류: {type(_e).__name__})_"
    )
    st.stop()

# ── 위험지수 계산 ─────────────────────────────────────────
oil_scores   = calc_oil_score(df_market)
fx_score     = calc_fx_score(df_market)
imp_scores   = calc_imp_scores(monthly_data, krw_monthly)
vuln_scores  = calc_vuln_scores(import_shares)
geo_scores, country_scores, route_count = calc_geo_scores(df_rss, df_notice, import_shares)
risk_results = calc_risk_results(oil_scores, fx_score, imp_scores, vuln_scores, geo_scores)

# ── 데이터 새로고침 버튼 ──────────────────────────────────
if st.sidebar.button("🔄 데이터 새로고침"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption("뉴스·외교부: 1시간 캐시\n관세청·유가·환율: 24시간 캐시")

# ══════════════════════════════════════════════════════════
# S1. 위험지수 요약 카드 (4개)
# ══════════════════════════════════════════════════════════
st.subheader("📌 원재료별 위험지수")
st.caption(
    "국제유가·환율·수입가격·수입구조취약성·지정학 5개 요인의 현재 상태를 0–100점으로 종합한 모니터링 지수입니다. "
    "등급 기준은 2020–2024년(60개월) 실데이터 분포를 기준으로 산정합니다."
)
with st.expander("📖 위험지수 등급 기준 및 활용 안내"):
    st.markdown("""
**등급 기준** (품목별 상이, 과거 5년 분포 기준)

| 등급 | 과거 분포 기준 | 의미 |
|------|-------------|------|
| 🟢 낮음 | 하위 60% 이하 | 평온한 시장 상태 — 정기 모니터링 |
| 🟡 주의 | 60–85% 구간 | 리스크 요인 활성화 — 동향 모니터링 강화 권고 |
| 🟠 경계 | 85–97% 구간 | 복수 요인 동시 상승 — 담당자 검토 및 대응 준비 |
| 🔴 심각 | 상위 3% 이내 | 극단적 시장 상황 — 즉각 대응 검토 |

**활용 시 유의사항**
- 이 지수는 **가격 예측 지수가 아닙니다.** 현재 리스크 요인의 압력 수준을 과거 대비 상대적으로 보여주는 참고 지표입니다.
- 카드의 **세부 점수 보기**를 눌러 5개 요인 중 어느 것이 높은지 확인하고, 아래 **가격 추세·수입 의존도·나프타 시나리오** 섹션에서 해당 요인의 배경 데이터를 확인하세요.
- 조달 의사결정은 이 지수를 포함한 복수의 정보를 종합적으로 판단하여 이루어져야 합니다.
""")
cols = st.columns(4)
for i, mat in enumerate(["PP", "PE", "PVC", "PET"]):
    r     = risk_results[mat]
    grade = r["등급"]
    icon  = grade_icon(grade)
    top3  = top_contributors(r)

    color_map = {"낮음": "#e8f5e9", "주의": "#fffde7", "경계": "#fff3e0", "심각": "#ffebee"}
    with cols[i]:
        st.markdown(
            f"""
            <div style="background:{color_map[grade]};border-radius:10px;padding:16px;text-align:center">
                <div style="font-size:28px">{icon}</div>
                <div style="font-size:22px;font-weight:bold">{mat}</div>
                <div style="font-size:32px;font-weight:bold">{r['위험지수']:.1f}</div>
                <div style="font-size:14px;color:#555">{grade}</div>
                <div style="font-size:11px;color:#888;margin-top:6px">{' / '.join(top3[:2])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── 세부 점수 테이블 ───────────────────────────────────────
with st.expander("세부 점수 보기"):
    rows = []
    for mat in ["PP", "PE", "PVC", "PET"]:
        r = risk_results[mat]
        rows.append({
            "품목": mat,
            "국제유가(25%)": r["유가"],
            "환율(15%)": r["환율"],
            "수입가격(20%)": r["수입가격"],
            "수입구조(20%)": r["수입구조"],
            "지정학(20%)": r["지정학"],
            "위험지수": r["위험지수"],
            "등급": f"{grade_icon(r['등급'])} {r['등급']}",
        })
    st.dataframe(
        pd.DataFrame(rows).set_index("품목"),
        use_container_width=True,
        column_config={
            "국제유가(25%)": st.column_config.NumberColumn(
                help="0.70 × 유가상승률점수(Brent/WTI 10영업일 변동률) + 0.30 × 변동성점수(Brent 20일 표준편차)"
            ),
            "환율(15%)": st.column_config.NumberColumn(
                help="0.70 × 환율상승률점수(USD/KRW 20영업일 변동률) + 0.30 × 변동성점수(USD/KRW 20일 표준편차)"
            ),
            "수입가격(20%)": st.column_config.NumberColumn(
                help="ln(원화기준 수입단가 당월 ÷ 전월) → 구간 점수 | 소스: 관세청 수입단가 × USD/KRW 월평균"
            ),
            "수입구조(20%)": st.column_config.NumberColumn(
                help="0.40 × 리스크국가의존도 + 0.35 × HHI + 0.25 × Top1 국가의존도 | 소스: 관세청 국가별 수입액 6개월 이동평균"
            ),
            "지정학(20%)": st.column_config.NumberColumn(
                help="Σ(수입비중 × 국가별 뉴스 심각도점수) + 항로 가산점 | 소스: 연합뉴스 RSS + 외교부 안전공지 14일"
            ),
            "위험지수": st.column_config.NumberColumn(
                help="유가(×0.25) + 환율(×0.15) + 수입가격(×0.20) + 수입구조(×0.20) + 지정학(×0.20) 가중합"
            ),
        },
    )

_c1, _c2, _c3 = st.columns([4, 2, 4])
with _c2:
    if st.button("📄 리포트 생성하기", use_container_width=True, type="primary"):
        st.switch_page("pages/3_리포트_생성.py")

st.markdown("---")

# ══════════════════════════════════════════════════════════
# S2. 가격 추세 차트
# ══════════════════════════════════════════════════════════
st.subheader("📈 가격 추세")
tab_price, tab_customs = st.tabs(["유가 · 환율", "월별 수입단가"])

with tab_price:
    brent_s  = df_market["Brent"].dropna()
    wti_s    = df_market["WTI"].dropna()
    usdkrw_s = df_market["USDKRW"].dropna()
    krw_mean = usdkrw_s.mean()

    # 호버용 한글 날짜
    def kr_hover(d: str) -> str:
        return f"{int(d[5:7])}월 {int(d[8:10])}일"

    brent_hover  = [kr_hover(d) for d in brent_s.index]
    wti_hover    = [kr_hover(d) for d in wti_s.index]
    krw_hover    = [kr_hover(d) for d in usdkrw_s.index]

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=("유가 추세 (최근 30일, USD/barrel)",
                                        "USD/KRW 환율 (최근 30일)"))

    # 유가 차트
    fig.add_trace(go.Scatter(x=brent_s.index, y=brent_s.values,
                             customdata=brent_hover,
                             name="Brent (PP/PVC/PET 기준)",
                             line=dict(color="#d62728", width=2),
                             hovertemplate="%{customdata}<br>Brent: %{y:.2f} USD/bbl<extra></extra>"),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=wti_s.index, y=wti_s.values,
                             customdata=wti_hover,
                             name="WTI (PE 보조)",
                             line=dict(color="#1f77b4", width=1.5, dash="dash"),
                             hovertemplate="%{customdata}<br>WTI: %{y:.2f} USD/bbl<extra></extra>"),
                  row=1, col=1)

    # 환율 차트
    fig.add_trace(go.Scatter(x=usdkrw_s.index, y=[krw_mean] * len(usdkrw_s),
                             showlegend=False, line=dict(color="rgba(0,0,0,0)")),
                  row=1, col=2)
    fig.add_trace(go.Scatter(x=usdkrw_s.index, y=usdkrw_s.values,
                             customdata=krw_hover,
                             name="USD/KRW",
                             line=dict(color="#2ca02c", width=2),
                             fill="tonexty", fillcolor="rgba(44,160,44,0.12)",
                             hovertemplate="%{customdata}<br>%{y:,.0f} KRW<extra></extra>"),
                  row=1, col=2)
    fig.add_hline(y=krw_mean, line_dash="dot", line_color="#2ca02c",
                  opacity=0.5, row=1, col=2,
                  annotation_text=f"평균 {krw_mean:,.0f}", annotation_position="right")

    fig.update_yaxes(title_text="USD/barrel", row=1, col=1)
    fig.update_yaxes(title_text="KRW", row=1, col=2)
    fig.update_layout(
        height=380, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.18, x=0),
        margin=dict(t=90, b=50),
    )
    st.plotly_chart(fig, use_container_width=True)

with tab_customs:
    colors = {"PP": "#d62728", "PE": "#1f77b4", "PVC": "#2ca02c", "PET": "#ff7f0e"}
    fig2 = go.Figure()
    latest_month = ""
    for mat in HS_CODES:
        df_m = monthly_data[mat].copy()
        df_m["환율_KRW"]        = df_m["연월"].map(krw_monthly)
        df_m["수입단가_KRW_kg"] = df_m["수입단가_USD_kg"] * df_m["환율_KRW"]
        df_m = df_m.dropna(subset=["수입단가_KRW_kg"])
        if df_m.empty: continue
        df_m["연월_표시"] = df_m["연월"].apply(lambda v: f"{v[:4]}년 {int(v[4:])}월")
        fig2.add_trace(go.Scatter(
            x=df_m["연월_표시"], y=df_m["수입단가_KRW_kg"],
            name=mat, mode="lines+markers",
            line=dict(color=colors[mat], width=2),
            marker=dict(size=5),
            hovertemplate=f"<b>{mat}</b><br>%{{x}}<br>%{{y:,.0f}} KRW/kg<extra></extra>",
        ))
        latest_month = df_m["연월"].iloc[-1]

    fig2.update_layout(
        title=dict(text=f"월별 수입단가 — 원화기준, 관세청 GW (최신 확정월: {latest_month})", font=dict(size=13)),
        yaxis_title="KRW/kg", height=380, hovermode="x unified",
        annotations=[dict(x=0, y=-0.25, xref="paper", yref="paper", showarrow=False,
                          text="※ 관세청 후행 특성상 1~2개월 전 실거래 데이터",
                          font=dict(size=10, color="gray"))],
    )
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════
# S3. NCC 나프타 시장 시나리오
# ══════════════════════════════════════════════════════════
st.subheader("⚗️ 나프타 시장 시나리오")
st.caption(
    "대한유화 5일 KOSPI 대비 상대수익률을 NCC 마진 방향의 간접 지표로 활용하여 시나리오를 제공합니다. "
    "2022~2026년 1,057 거래일 실데이터를 분석, Brent 방향과 조합한 6가지 패턴과 상관성을 보이는 "
    "실제 석유화학 경기 상황을 고려하였습니다. "
    "인과관계는 검증되지 않았으며, 방향성 참고 신호로 제공합니다."
)
ncc_sum  = ncc_spread_summary(df_ncc)
scenario = classify_scenario(df_market)

# 국제유가압력점수: PP 기준 (Brent 단독 연동, PP/PVC/PET 동일)
oil_score_pp = oil_scores.get("PP", 0)

col_a, col_b = st.columns(2)
with col_a:
    st.caption("📅 이번 주 방향성 신호 — Brent·NCC 5일 기준")
    b_ret = scenario.get("brent_5d_ret_%")
    n_rel = scenario.get("ncc_relative_%")
    b_str = f"{b_ret:+.2f}%" if b_ret is not None else "N/A"
    n_str = f"{n_rel:+.2f}%" if n_rel is not None else "N/A"
    st.metric("국제유가압력점수 (Brent 기준, 0~100)", f"{oil_score_pp:.1f}점",
              help="위험지수의 첫 번째 축 — Brent 10영업일 변동률(70%) + 20일 변동성(30%). 시나리오의 Brent 방향성 전제가 되는 점수.")
    st.metric("Brent 5일 변동률", b_str,
              help="시나리오 분류에 쓰이는 단기 방향 신호. 국제유가압력점수와 같은 Brent 데이터 공유.")
    st.metric("NCC 상대수익률 (대한유화 vs KOSPI)", n_str)
    _detail = SCENARIO_DETAIL.get(
        (scenario.get("brent_dir", "중립"), scenario.get("ncc_dir", "중립")), ""
    )
    st.info(
        f"**{scenario['scenario_name']}**\n\n"
        f"{scenario['scenario_desc']}"
        + (f"\n\n{_detail}" if _detail else "")
    )
    if _detail:
        st.caption("※ 시나리오 해석은 NCC 마진 구조·수요-공급 관계 등 일반적인 석유화학 시장 원리를 기반으로 작성되었으며, 전문가 검증을 거치지 않았습니다.")

with col_b:
    st.caption("📊 역사적 절대 수준 — 에틸렌 스프레드 (2019년~현재 분기별)")
    st.metric("에틸렌 스프레드 현재값", f"{ncc_sum['스프레드']} USD/ton",
              delta=f"전분기비 {ncc_sum['전분기비_%']:+.1f}%" if ncc_sum.get('전분기비_%') else None,
              help="에틸렌 − 나프타 (USD/ton). 2019Q1~현재 분기별 실데이터 기반 백분위 구간 판정.")
    st.caption(f"기준: {ncc_sum['기준분기']}  |  역사 분포: Q25={ncc_sum['q25']}  Q50={ncc_sum['q50']}  Q75={ncc_sum['q75']}")
    _NCC_BEP = 300
    _spread_val = ncc_sum["스프레드"]
    _zone_text = ncc_sum["구간_텍스트"]
    if _spread_val < _NCC_BEP:
        _gap = round(_NCC_BEP - _spread_val, 1)
        _zone_text += f"\n\n\\* 업계 손익분기점(BEP) 추정: 250~300 USD/ton — 현재 {_spread_val} USD/ton는 BEP 상단 기준 {_gap}달러 하회 (적자 구간 가능성)"
    st.warning(_zone_text)

# 구매 관점 해석 — 전체 폭 (두 컬럼 아래)
insight = get_buyer_insight(scenario, oil_score_pp)
if insight is None:
    b_str2 = f"{b_ret:+.2f}%" if b_ret is not None else "N/A"
    n_str2 = f"{n_rel:+.2f}%" if n_rel is not None else "N/A"
    st.caption(f"유가 방향성 없음 — Brent 5일 {b_str2}, 대한유화 KOSPI 대비 {n_str2}")
elif insight.get("outlier"):
    st.caption("⚠️ 대한유화 단기 이상 변동 감지 (NCC 상대수익률 ±15% 초과) — 신호 보류")
else:
    with st.container(border=True):
        st.markdown("**📌 구매 관점 해석**")
        st.markdown(
            f"- **유가압력점수** {insight['pressure_label']} → {insight['pressure_meaning']}"
        )
        st.markdown(f"- **NCC 방향** {insight['ncc_meaning']}")
        st.markdown(f"- **실무 시사점** {insight['action']}")
        if insight.get("mismatch_text"):
            st.caption(f"※ {insight['mismatch_text']}")

# 나프타·석유화학 관련 뉴스 (구글 뉴스 RSS, 최근 30일)
_GOOGLE_QUERY = "나프타 OR 에틸렌 OR 석유화학 OR NCC OR 유가 OR OPEC"
_naphtha_news = fetch_google_news(query=_GOOGLE_QUERY, window_days=30, max_results=5)

st.markdown("**📰 나프타·유가 관련 뉴스 (최근 30일)**")
if _naphtha_news.empty:
    st.caption("관련 뉴스 없음")
else:
    for _, row in _naphtha_news.iterrows():
        날짜str = row["날짜"].strftime("%m/%d") if pd.notna(row["날짜"]) else ""
        소스 = row["소스"] if pd.notna(row.get("소스")) else ""
        st.markdown(f"- [{row['제목']}]({row['id']}) <span style='color:gray;font-size:0.85em'>{날짜str} · {소스}</span>",
                    unsafe_allow_html=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════
# S4. 수입 의존도 차트
# ══════════════════════════════════════════════════════════
st.subheader("🌍 품목별 수입 의존도")

mats = ["PP", "PE", "PVC", "PET"]
risk_deps = {mat: import_shares[mat].head(7)[
    import_shares[mat].head(7)["국가코드"].isin(RISK_CODES)]["수입비중_%"].sum()
    for mat in mats}

fig3 = make_subplots(
    rows=2, cols=2,
    subplot_titles=[f"{m}  |  리스크국가 의존도 {risk_deps[m]:.1f}%" for m in mats],
    horizontal_spacing=0.12, vertical_spacing=0.30,
)

positions = [(1,1),(1,2),(2,1),(2,2)]
for i, mat in enumerate(mats):
    df_c = import_shares[mat].head(7).copy()
    clrs = ["#d62728" if c in RISK_CODES else "#4472C4" for c in df_c["국가코드"]]
    row, col = positions[i]
    fig3.add_trace(
        go.Bar(
            x=df_c["수입비중_%"][::-1],
            y=df_c["국가명"][::-1],
            orientation="h",
            marker_color=clrs[::-1],
            text=[f"{v:.1f}%" for v in df_c["수입비중_%"][::-1]],
            textposition="outside",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
            showlegend=False,
        ),
        row=row, col=col,
    )

# 범례용 더미 트레이스
fig3.add_trace(go.Bar(x=[None], y=[None], orientation="h",
                      marker_color="#d62728", name="리스크 국가 (CN/RU/IR/SA)"))
fig3.add_trace(go.Bar(x=[None], y=[None], orientation="h",
                      marker_color="#4472C4", name="일반 국가"))

fig3.update_layout(
    title=dict(text=f"품목별 수입 의존도 (상위 7개국, {VULN_STRT}~{VULN_END})", font=dict(size=13)),
    height=580,
    legend=dict(orientation="h", yanchor="top", y=-0.04, xanchor="center", x=0.5),
    barmode="overlay",
)
fig3.update_xaxes(title_text="수입비중 (%)")
st.plotly_chart(fig3, use_container_width=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════
# S4-1. 주요국 글로벌 이슈 동향 (수입의존도 차트 아래)
# ══════════════════════════════════════════════════════════
st.subheader("🌐 주요 공급국 정책·통상 리포트")
st.caption("수입 의존도 상위국의 경제·산업·무역 정책 동향 분석 (KOTRA 경제통상 리포트, 24시간 캐시) — 실시간 뉴스 경보는 '지정학 리스크' 탭 참고")

tab_cn, tab_us = st.tabs(["🇨🇳 중국 (PP·PVC·PET 주공급국)", "🇺🇸 미국 (PE 주공급국, 에탄 크래킹)"])

with tab_cn:
    china_items = fetch_china_issues(num_show=6)
    if china_items:
        for item in china_items:
            with st.expander(f"📄 {item['제목']}  |  {item['날짜']}"):
                if item["요약"]:
                    st.markdown(item["요약"])
                col_l, col_r = st.columns([3, 1])
                col_l.caption(f"출처: {item['무역관']}")
                if item["pdf"]:
                    col_r.markdown(f"[PDF 보기]({item['pdf']})")
    else:
        st.info("중국 이슈 데이터를 불러오는 중입니다.")

with tab_us:
    st.caption("PE 수입 중 미국산 31% (에탄 크래킹 기반) — 미국 에너지·관세·산업 정책이 PE 조달 비용에 직접 영향")
    usa_items = fetch_usa_issues(num_fetch=30, num_show=6)
    if usa_items:
        for item in usa_items:
            with st.expander(f"📄 {item['제목']}  |  {item['날짜']}"):
                if item["요약"]:
                    st.markdown(item["요약"])
                col_l, col_r = st.columns([3, 1])
                col_l.caption(f"출처: {item['무역관']}")
                if item["pdf"]:
                    col_r.markdown(f"[PDF 보기]({item['pdf']})")
    else:
        st.info("미국 이슈 데이터를 불러오는 중입니다.")

st.markdown("---")

# ══════════════════════════════════════════════════════════
# S5. 리스크 매핑 테이블
# ══════════════════════════════════════════════════════════
st.subheader("📋 리스크 매핑 테이블")
rows = []
for mat in ["PP", "PE", "PVC", "PET"]:
    df_c     = import_shares[mat]
    top1     = df_c.iloc[0]
    risk_dep = df_c[df_c["국가코드"].isin(RISK_CODES)]["수입비중_%"].sum()
    hhi      = round((df_c["수입비중"] ** 2).sum() * 100, 1)
    r        = risk_results[mat]
    rows.append({
        "원재료":          mat,
        "최대 수입국":     top1["국가명"],
        "최대 수입국 비중(%)": top1["수입비중_%"],
        "리스크국가 의존도(%)": round(risk_dep, 1),
        "HHI": hhi,
        "취약성 점수": vuln_scores.get(mat, 0),
        "위험지수": r["위험지수"],
        "등급": f"{grade_icon(r['등급'])} {r['등급']}",
    })
st.dataframe(pd.DataFrame(rows).set_index("원재료"), width='stretch')
st.caption("리스크국가: CN(중국) · RU(러시아) · IR(이란) · SA(사우디아라비아)  |  HHI: 수입 집중도 지수")
