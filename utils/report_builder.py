"""
룰 기반 템플릿 리포트 생성 (core_func_4 로직)
NCC 스프레드 분석 + 나프타 시나리오 + 리포트 텍스트 조합
"""
import pandas as pd
from datetime import datetime

GRADE_ADVICE = {
    "낮음": "공급망 안정 수준 유지 중. 정기 모니터링 권고.",
    "주의": "원자재 조달 비용 증가 가능성 — 단기 재고 수준 점검 권고.",
    "경계": "공급망 교란 징후 다수 — 대체 공급선 및 재고 확충 검토 권고.",
    "심각": "즉각적인 리스크 대응 필요. 긴급 수급 대책 수립 요망.",
}

SCENARIO_RULE = {
    ("↑", "↑"):       ("마진 전가 중",          "원료비 상승 + NCC 선방 — 비용 전가 진행 중, 단가 인상 예고 대비 권고"),
    ("↑", "↓"):       ("스프레드 압박",         "원료비 상승 + NCC 약세 — 시장이 전가 실패로 판단, 공급사 인상 요청 거부 근거 있음"),
    ("↓", "↑"):       ("스프레드 개선",         "원료비 하락 + NCC 선방 — 단기 마진 방향 개선, 현 발주 주기 유지 권고"),
    ("↓", "↓"):       ("수요 약세",             "원료비 하락에도 NCC 약세 — 수요 위축 신호, 최소 재고·저점 대기 권고"),
    ("중립", "↑"):    ("유가 중립/NCC 선방",    "유가 방향성 없음, NCC 상대적 강세 — 추이 관찰"),
    ("중립", "↓"):    ("유가 중립/NCC 약세",    "유가 방향성 없음, NCC 상대적 약세 — 추이 관찰"),
    ("중립", "중립"): ("방향성 부재",            "Brent·NCC 모두 뚜렷한 방향성 없음 — 현황 유지 및 추이 관찰"),
    ("↑", "중립"):    ("유가 상승/NCC 중립",    "원료비 상승 부담, NCC 뚜렷한 반응 없음 — 전가 여부 주시"),
    ("↓", "중립"):    ("유가 하락/NCC 중립",    "원료비 하락, NCC 뚜렷한 반응 없음 — 수요 신호 대기"),
}

SCENARIO_DETAIL = {
    ("↑", "↑"):       "NCC가 원료 상승분을 제품가에 전가 중. 공급사 마진 방어 성공 → 추가 단가 인상 요청 명분 있음. 재고 선확보 기회를 놓치면 더 비싼 가격에 매입 가능성.",
    ("↑", "↓"):       "원료비 오르는데 NCC 제품가 하락 → 업계 스프레드 압박. 공급사 수익성 악화. 단기 인상 요청 거부 가능하나 적자 지속 시 감산·공급 축소 리스크 잠재.",
    ("↓", "↑"):       "원료비 하락 + NCC 선방 → 마진 개선 국면. 공급 안정, 수요 신호 양호. 급선매입 불필요. 가격 인하 협상 여지 탐색.",
    ("↓", "↓"):       "원료비 하락에도 NCC 제품가도 동반 하락 → 수요 위축 신호. 추가 하락 가능. 최소 재고 유지, 저점 매수 대기. 덤핑 오퍼 주시.",
    ("중립", "↑"):    "유가 횡보 속 NCC 상대강세. 수요 개선 또는 공급 타이트 가능성. 방향성 확인 후 행동.",
    ("중립", "↓"):    "유가 횡보 속 NCC 약세. 수요 부진 신호 가능. 발주 보수적 접근.",
    ("중립", "중립"): "Brent·NCC 모두 뚜렷한 방향성 없음. 현황 유지, 주 1회 이상 시나리오 재확인.",
    ("↑", "중립"):    "원료비 상승 부담 있으나 NCC 뚜렷한 반응 없음. 전가 여부 불확실 — 공급사 움직임 주시.",
    ("↓", "중립"):    "원료비 하락 중 NCC 뚜렷한 반응 없음. 수요 신호 대기. 단가 인하 협상 기회 탐색.",
}

NCC_SPREAD_TEXTS = {
    "q0_q25":  "하위 25% — 에틸렌·나프타 스프레드(가공 마진) 역사적 최하위 구간. 생산 감축 시 공급 부족으로 이어질 수 있음",
    "q25_q50": "25~50% — 에틸렌·나프타 스프레드 평균 이하. 공급 타이트 가능성, 수급 동향 주시",
    "q50_q75": "50~75% — 에틸렌·나프타 스프레드 평균 이상. 공급 안정 구간",
    "q75_":    "상위 25% — 에틸렌·나프타 스프레드 여유 구간. 공급사 단가 인상 압력이 높은 시점",
}

SECTION5_RULE = [
    (7.0,  "단가 조정 근거자료 준비 권고",
     "중소 제조업 평균 영업이익률 5~8%(한국은행 기업경영분석) 감안 시 실질 잠식 구간"),
    (3.0,  "납품단가 협의 검토",
     "하도급법 제16조·상생협력법 제22조의2 기반 실무 협의 신청 구간"),
    (0.0,  "모니터링 유지",
     "하도급법 제16조 협의 신청 기준 미달"),
]


# ── NCC 스프레드 요약 ────────────────────────────────────
def ncc_spread_summary(df_ncc: pd.DataFrame) -> dict:
    latest = df_ncc.iloc[-1]
    prev   = df_ncc.iloc[-2] if len(df_ncc) >= 2 else None
    spread = df_ncc["스프레드_USD_ton"]
    q25, q50, q75 = spread.quantile([0.25, 0.50, 0.75])
    val = latest["스프레드_USD_ton"]
    chg = ((val - prev["스프레드_USD_ton"]) / prev["스프레드_USD_ton"] * 100
           if prev is not None else None)

    if val <= q25:   zone_key = "q0_q25"
    elif val <= q50: zone_key = "q25_q50"
    elif val <= q75: zone_key = "q50_q75"
    else:            zone_key = "q75_"

    return {
        "기준분기":        latest["날짜"].strftime("%Y-Q") + str((latest["날짜"].month - 1) // 3 + 1),
        "에틸렌":          round(latest["에틸렌_USD_ton"], 1),
        "나프타":          round(latest["나프타_USD_ton"], 1),
        "스프레드":        round(val, 1),
        "전분기비_%":      round(chg, 1) if chg is not None else None,
        "방향":            "확대" if (prev is not None and val > prev["스프레드_USD_ton"]) else "축소",
        "구간_키":         zone_key,
        "구간_텍스트":     NCC_SPREAD_TEXTS[zone_key],
        "q25": round(q25, 1), "q50": round(q50, 1), "q75": round(q75, 1),
    }


NCC_OUTLIER_THRESHOLD = 15.0  # %, 이상치 감지 기준

_BUYER_INSIGHT = {
    ("↑", "↑"): {
        "ncc": "NCC 강세 → 원가 상승분이 제품가에 전가되고 있음",
        "action": "재고 선확보 검토. 현 가격에 협의 가능한 마지막 시점일 수 있음.",
    },
    ("↑", "↓"): {
        "ncc": "NCC 약세 → 원가 올라도 시장이 전가 안 된다고 판단. 공급사 인상 명분 약함",
        "action": "공급사가 단가 인상 요청해도 거부 근거 있음. 단, 적자 지속 시 감산·공급 차질로 이어질 수 있어 수급 동향 병행 모니터링.",
    },
    ("↓", "↑"): {
        "ncc": "NCC 강세 → 원가 하락 수혜, 마진 개선. 공급 안정 국면",
        "action": "급선매입 불필요. 현 발주 주기 유지. 공급사 가격 인하 협상 여지 검토.",
    },
    ("↓", "↓"): {
        "ncc": "NCC 약세 → 원가 빠져도 제품가 더 빠짐. 수요 위축으로 추가 하락 가능",
        "action": "최소 재고 유지. 가격 저점 대기. 덤핑 오퍼 주시.",
    },
}


# ── 나프타 시나리오 분류 ─────────────────────────────────
def classify_scenario(df_market: pd.DataFrame,
                      brent_window: int = 5,
                      ncc_window: int = 5,
                      brent_threshold: float = 2.0) -> dict:
    result = {}
    brent  = df_market["Brent"].dropna()   if "Brent"   in df_market.columns else pd.Series(dtype=float)
    daehan = df_market["대한유화"].dropna() if "대한유화" in df_market.columns else pd.Series(dtype=float)
    kospi  = df_market["KOSPI"].dropna()   if "KOSPI"   in df_market.columns else pd.Series(dtype=float)

    # Brent 5일 방향
    if len(brent) >= brent_window + 1:
        b_ret = (brent.iloc[-1] / brent.iloc[-(brent_window + 1)] - 1) * 100
        result["brent_5d_ret_%"] = round(b_ret, 2)
        if b_ret > brent_threshold:    brent_dir = "↑"
        elif b_ret < -brent_threshold: brent_dir = "↓"
        else:                          brent_dir = "중립"
    else:
        b_ret, brent_dir = 0.0, "중립"
        result["brent_5d_ret_%"] = None
    result["brent_dir"] = brent_dir

    # Brent 10일 방향 (압력점수 수식어용)
    if len(brent) >= 11:
        b10_ret = (brent.iloc[-1] / brent.iloc[-11] - 1) * 100
        result["brent_10d_ret_%"] = round(b10_ret, 2)
        if b10_ret > brent_threshold:    b10d_dir = "↑"
        elif b10_ret < -brent_threshold: b10d_dir = "↓"
        else:                            b10d_dir = "중립"
    else:
        result["brent_10d_ret_%"] = None
        b10d_dir = "중립"
    result["brent_10d_dir"] = b10d_dir

    # NCC 상대수익률 + 이상치 감지
    if len(daehan) >= ncc_window + 1 and len(kospi) >= ncc_window + 1:
        d_ret = (daehan.iloc[-1] / daehan.iloc[-(ncc_window + 1)] - 1) * 100
        k_ret = (kospi.iloc[-1]  / kospi.iloc[-(ncc_window + 1)]  - 1) * 100
        rel   = d_ret - k_ret
        result["ncc_relative_%"]  = round(rel, 2)
        result["daehan_5d_ret_%"] = round(d_ret, 2)
        result["kospi_5d_ret_%"]  = round(k_ret, 2)
        result["ncc_outlier"]     = abs(rel) > NCC_OUTLIER_THRESHOLD
        ncc_dir = "↑" if rel > 0 else "↓"
    else:
        ncc_dir = "중립"
        result["ncc_relative_%"]  = None
        result["daehan_5d_ret_%"] = None
        result["kospi_5d_ret_%"]  = None
        result["ncc_outlier"]     = False
    result["ncc_dir"] = ncc_dir

    scenario_key = (brent_dir, ncc_dir)
    scenario_name, scenario_desc = SCENARIO_RULE.get(scenario_key, ("분류 불가", "데이터 부족"))
    result["scenario_name"] = scenario_name
    result["scenario_desc"] = scenario_desc
    return result


def get_buyer_insight(scenario: dict, oil_score: float) -> dict | None:
    """구매 관점 해석 블록 데이터.
    중립·이상치 케이스는 None 반환 → 호출부에서 수치만 표시.
    """
    brent_dir = scenario.get("brent_dir", "중립")
    ncc_dir   = scenario.get("ncc_dir",   "중립")

    if brent_dir == "중립":
        return None
    if scenario.get("ncc_outlier"):
        return {"outlier": True}

    detail = _BUYER_INSIGHT.get((brent_dir, ncc_dir))
    if not detail:
        return None

    # 유가압력점수 레벨
    if oil_score <= 30:
        p_label, p_meaning = f"{oil_score:.0f}점 (낮음)", "공급사 단가 인상 명분 약한 시점"
    elif oil_score <= 60:
        p_label, p_meaning = f"{oil_score:.0f}점 (보통)", "공급사 원가 부담 누적 중"
    elif oil_score <= 80:
        p_label, p_meaning = f"{oil_score:.0f}점 (높음)", "공급사 단가 인상 명분 강한 시점"
    else:
        p_label, p_meaning = f"{oil_score:.0f}점 (매우 높음)", "공급사 즉각 단가 인상 압력 구간"

    # 5일/10일 방향 불일치 수식어
    b10d_dir = scenario.get("brent_10d_dir", "중립")
    b10d_ret = scenario.get("brent_10d_ret_%")
    mismatch_text = None
    if b10d_dir not in ("중립", brent_dir) and b10d_ret is not None:
        if brent_dir == "↑":
            mismatch_text = f"단기 반등 가능성 — Brent 10일 기준 {b10d_ret:+.1f}% (하락 추세)"
        else:
            mismatch_text = f"단기 조정 가능성 — Brent 10일 기준 {b10d_ret:+.1f}% (상승 추세)"

    return {
        "outlier":          False,
        "pressure_label":   p_label,
        "pressure_meaning": p_meaning,
        "ncc_meaning":      detail["ncc"],
        "action":           detail["action"],
        "mismatch_text":    mismatch_text,
    }


# ── Section 3~5: 사용자 입력 기반 계산 ──────────────────
def calc_inventory_days(stock: float, monthly_usage: float) -> float | None:
    """재고 소진 예상일 = 현재 재고량 ÷ (월 사용량 ÷ 30)"""
    if monthly_usage and monthly_usage > 0:
        return round(stock / (monthly_usage / 30), 1)
    return None

def inventory_urgency(days: float | None) -> tuple[str, str]:
    if days is None: return "입력 필요", "⚪"
    if days < 7:     return "즉시 발주 검토", "🔴"
    if days < 15:    return "발주 일정 확인", "🟠"   # 8~14일 (14.x일 포함)
    if days <= 30:   return "모니터링",       "🟡"   # 15~30일 (30일 포함)
    return "여유",   "🟢"

def calc_cost_impact(imp_change_pct: float | None, cost_ratio_pct: float | None) -> float | None:
    """원가 영향% = 수입단가 변동률 × 원재료별 원가 비중"""
    if imp_change_pct is not None and cost_ratio_pct is not None:
        return round(imp_change_pct * cost_ratio_pct / 100, 2)
    return None

def delivery_price_advice(cost_impact_pct: float | None) -> tuple[str, str]:
    """Section 5 권고문구 (Section 5 룰 그대로 재사용)"""
    if cost_impact_pct is None:
        return "원가 비중 미입력 — 정량 추정 불가", ""
    for threshold, advice, reason in SECTION5_RULE:
        if cost_impact_pct >= threshold:
            return advice, reason
    return "모니터링 유지", ""


# ── 리포트 텍스트 생성 ───────────────────────────────────
def build_report_text(material: str, risk_result: dict, ncc_summary: dict,
                      scenario: dict, user_inputs: dict | None = None) -> str:
    today = datetime.today().strftime("%Y-%m-%d")
    grade = risk_result["등급"]
    score = risk_result["위험지수"]

    W = {"유가": 0.25, "환율": 0.15, "수입가격": 0.20, "수입구조": 0.20, "지정학": 0.20}
    LABEL = {"유가": "국제유가 상승", "환율": "환율 상승",
              "수입가격": "수입단가 급등", "수입구조": "수입집중 리스크", "지정학": "지정학 리스크"}
    top3 = " / ".join(
        [k for k, _ in sorted(
            {LABEL[k]: risk_result.get(k, 0) * W[k] for k in W}.items(),
            key=lambda x: -x[1]
        ) if _ > 0][:3]  # 리스트 3개 추린 후 join
    ) or "—"

    b_ret = scenario.get("brent_5d_ret_%")
    ncc_r = scenario.get("ncc_relative_%")
    b_str = f"{b_ret:+.2f}%" if b_ret is not None else "N/A"
    n_str = f"{ncc_r:+.2f}%" if ncc_r is not None else "N/A"

    chg_str = f"{ncc_summary['전분기비_%']:+.1f}%" if ncc_summary.get("전분기비_%") is not None else "—"

    lines = [
        f"{'='*60}",
        f"[{material}] 원자재 리스크 모니터링 리포트  ({today})",
        f"{'='*60}",
        "",
        f"■ 위험지수: {score:.1f}점  [{grade}]",
        f"  주요 원인: {top3}",
        f"  {GRADE_ADVICE[grade]}",
        "",
        "■ 세부 지표",
        f"  국제유가 압력:   {risk_result.get('유가', 0):.1f}점  (가중치 25%)",
        f"  환율 압력:       {risk_result.get('환율', 0):.1f}점  (가중치 15%)",
        f"  수입가격 압력:   {risk_result.get('수입가격', 0):.1f}점  (가중치 20%)",
        f"  수입구조 취약성: {risk_result.get('수입구조', 0):.1f}점  (가중치 20%)",
        f"  지정학 노출:     {risk_result.get('지정학', 0):.1f}점  (가중치 20%)",
        "",
        "■ 나프타 시장 시나리오",
        f"  Brent 5일 변동률: {b_str} ({scenario.get('brent_dir', '—')})"
        f"  |  NCC 상대수익률: {n_str} ({scenario.get('ncc_dir', '—')})",
        f"  → {scenario.get('scenario_name', '—')}: {scenario.get('scenario_desc', '—')}",
        "",
        "■ NCC 스프레드 현황",
        f"  {ncc_summary['스프레드']:.1f} USD/ton (전분기비 {chg_str}, {ncc_summary['방향']})"
        f"  | {ncc_summary['기준분기']}",
        f"  {ncc_summary['구간_텍스트']}",
        "",
    ]

    if user_inputs:
        lines += ["■ 우리 회사 영향 예상 (입력값 기반)"]
        days = user_inputs.get("재고_소진_예상일")
        urgency, u_icon = inventory_urgency(days)
        if days is not None:
            lines.append(f"  재고 소진 예상일: {days:.0f}일  {u_icon} {urgency}")

        cost_impact = user_inputs.get("원가_영향_%")
        if cost_impact is not None:
            advice, reason = delivery_price_advice(cost_impact)
            lines.append(f"  원가 영향:        약 {cost_impact:.1f}%")
            lines.append(f"  납품단가 권고:    {advice}")
            if reason:
                lines.append(f"    ({reason})")
        lines.append("")

    lines += [
        "■ KOTRA 시장 동향",
        "  https://dream.kotra.or.kr (글로벌공급망인사이트 > 석유화학)",
        "",
        "─" * 60,
        "※ 본 리포트는 공공데이터 기반 룰엔진이 자동 생성한 정보입니다.",
        "   투자·구매 결정의 최종 책임은 이용자에게 있습니다.",
    ]
    return "\n".join(lines)
