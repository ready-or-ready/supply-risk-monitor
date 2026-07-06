"""
위험지수 계산 엔진 (core_func_3 로직)
5개 세부점수 → 가중 합산 → 0~100, 4등급
"""
import numpy as np
import pandas as pd
from collections import defaultdict

# ── 가중치 ───────────────────────────────────────────────
W_OIL, W_FX, W_IMP, W_VULN, W_GEO = 0.25, 0.15, 0.20, 0.20, 0.20
W_RISK, W_HHI, W_TOP1              = 0.40, 0.35, 0.25

# 품목별 등급 임계값
# 산출 근거: 2020-2024년 89개월 월별 점수 분위수 (P60/P85/P97)
# PET는 중국 의존도 84%로 구조적 취약성이 높아 다른 품목보다 임계값이 높음
THRESHOLDS: dict[str, tuple[int, int, int]] = {
    "PP":  (24, 32, 44),   # 낮음≤24 / 주의≤32 / 경계≤44 / 심각>44
    "PE":  (21, 27, 37),   # 낮음≤21 / 주의≤27 / 경계≤37 / 심각>37
    "PVC": (23, 33, 43),   # 낮음≤23 / 주의≤33 / 경계≤43 / 심각>43
    "PET": (33, 39, 49),   # 낮음≤33 / 주의≤39 / 경계≤49 / 심각>49
}

RISK_CODES = {"CN", "RU", "IR", "SA"}

COMMON_KEYWORDS = {
    "중국 수출규제": {"weight": 30, "countries": ["CN"]},
    "중국 화학공장": {"weight": 30, "countries": ["CN"]},
    "중국 전력난":   {"weight": 30, "countries": ["CN"]},
    "중국 나프타":   {"weight": 30, "countries": ["CN"]},
    "중국 물류":     {"weight": 15, "countries": ["CN"]},
    "미중 관세":     {"weight": 20, "countries": ["CN", "US"]},
    "미중 무역분쟁": {"weight": 20, "countries": ["CN", "US"]},
    "대만해협":      {"weight": 20, "countries": ["TW", "CN"]},
    "미국 에탄":     {"weight": 15, "countries": ["US"]},
    "미국 텍사스":   {"weight": 10, "countries": ["US"]},
    "사우디 감산":   {"weight": 15, "countries": ["SA"]},
    "러시아":        {"weight": 10, "countries": ["RU"]},
    "우크라이나":    {"weight": 10, "countries": ["UA"]},
    "이란":          {"weight": 10, "countries": ["IR"]},
}
ROUTE_KEYWORDS = ["홍해", "수에즈", "호르무즈"]
CHAR_MAP = {"美中": "미중", "中美": "미중", "美": "미국", "中": "중국", "日": "일본"}


# ── 점수 변환 함수 ────────────────────────────────────────
def _brent_ret_score(p):  return 0  if p < 2  else 40 if p < 5  else 75 if p < 10 else 100
def _oil_vol_score(s):    return 0  if s < 1  else 30 if s < 2  else 70 if s < 3  else 100
def _krw_ret_score(p):    return 0  if p <= 1 else 33 if p <= 2 else 67 if p <= 3 else 100
def _krw_vol_score(s):    return 0  if s < 0.3 else 30 if s < 0.6 else 70 if s < 1.0 else 100
def _ln_score(r):         return 0  if pd.isna(r) or r <= 0.02 else 30 if r <= 0.05 else 60 if r <= 0.10 else 100

def risk_grade(score: float, material: str = "PP") -> str:
    t1, t2, t3 = THRESHOLDS.get(material, (24, 33, 44))
    if score <= t1: return "낮음"
    if score <= t2: return "주의"
    if score <= t3: return "경계"
    return "심각"

def grade_icon(grade: str) -> str:
    return {"낮음": "🟢", "주의": "🟡", "경계": "🟠", "심각": "🔴"}.get(grade, "⚪")


def _normalize(t: str) -> str:
    for a, b in CHAR_MAP.items():
        t = t.replace(a, b)
    return t

def _detect_common(title: str) -> list:
    n = _normalize(title)
    return [(kw, m["weight"], m["countries"]) for kw, m in COMMON_KEYWORDS.items() if kw in n]

def _detect_route(title: str) -> list:
    return [kw for kw in ROUTE_KEYWORDS if kw in title]

def _route_score(count: int) -> int:
    return 0 if count == 0 else 5 if count <= 2 else 10 if count <= 5 else 20


# ── S1: 국제유가압력점수 ─────────────────────────────────
def calc_oil_score(df_market: pd.DataFrame) -> dict:
    """Brent 10영업일 변동률 + 20일 변동성 → 품목별 유가압력점수"""
    brent = df_market["Brent"].dropna() if "Brent" in df_market.columns else pd.Series(dtype=float)
    wti   = df_market["WTI"].dropna()   if "WTI"   in df_market.columns else pd.Series(dtype=float)

    brent_10 = (brent.iloc[-1] / brent.iloc[-11] - 1) * 100 if len(brent) >= 11 else 0.0
    wti_10   = (wti.iloc[-1]   / wti.iloc[-11]   - 1) * 100 if len(wti)   >= 11 else 0.0
    brent_std = brent.pct_change(fill_method=None).tail(20).std() * 100

    oil_vol = _oil_vol_score(brent_std)
    # PE만 Brent+WTI 50/50 평균
    oil_rise = {
        "PP":  _brent_ret_score(brent_10),
        "PE":  round((_brent_ret_score(brent_10) + _brent_ret_score(wti_10)) / 2),
        "PVC": _brent_ret_score(brent_10),
        "PET": _brent_ret_score(brent_10),
    }
    return {
        mat: round(0.70 * oil_rise[mat] + 0.30 * oil_vol, 2)
        for mat in ["PP", "PE", "PVC", "PET"]
    }


# ── S2: 환율압력점수 ─────────────────────────────────────
def calc_fx_score(df_market: pd.DataFrame) -> float:
    usdkrw = df_market["USDKRW"].dropna() if "USDKRW" in df_market.columns else pd.Series(dtype=float)
    krw_20  = (usdkrw.iloc[-1] / usdkrw.iloc[-21] - 1) * 100 if len(usdkrw) >= 21 else 0.0
    krw_std = usdkrw.pct_change(fill_method=None).tail(20).std() * 100
    return round(0.7 * _krw_ret_score(krw_20) + 0.3 * _krw_vol_score(krw_std), 2)


# ── S3: 수입가격압력점수 ─────────────────────────────────
def calc_imp_scores(monthly_data: dict, krw_monthly: dict) -> dict:
    """monthly_data: {material: DataFrame(연월, 수입단가_USD_kg)}"""
    imp_scores = {}
    for mat, df_m in monthly_data.items():
        df_m = df_m.copy()
        df_m["환율_KRW"]        = df_m["연월"].map(krw_monthly)
        df_m["수입단가_KRW_kg"] = df_m["수입단가_USD_kg"] * df_m["환율_KRW"]
        df_m["ln"]              = np.log(df_m["수입단가_KRW_kg"]).diff()
        valid = df_m[df_m["ln"].notna()]
        imp_scores[mat] = _ln_score(valid.iloc[-1]["ln"]) if not valid.empty else 0
    return imp_scores


# ── S4: 수입구조취약성점수 ──────────────────────────────
def calc_vuln_scores(import_shares: dict) -> dict:
    scores = {}
    for mat, df_c in import_shares.items():
        if df_c.empty:
            scores[mat] = 0.0
            continue
        risk_dep = df_c[df_c["국가코드"].isin(RISK_CODES)]["수입비중_%"].sum()
        hhi      = (df_c["수입비중"] ** 2).sum() * 100
        top1     = df_c["수입비중_%"].max()
        scores[mat] = round(W_RISK * risk_dep + W_HHI * hhi + W_TOP1 * top1, 2)
    return scores


# ── S5: 지정학이벤트노출점수 ────────────────────────────
def calc_geo_scores(df_rss: pd.DataFrame, df_notice: pd.DataFrame,
                    import_shares: dict) -> tuple[dict, dict, int]:
    """(geo_scores, country_scores, route_count) 반환"""
    country_scores = defaultdict(float)
    route_count    = 0
    seen           = set()

    for df in [df_rss, df_notice]:
        if df.empty:
            continue
        for _, row in df.iterrows():
            uid = row.get("id", "")
            if uid and uid in seen:
                continue
            if uid:
                seen.add(uid)
            title = row.get("제목", "")
            for _, w, countries in _detect_common(title):
                for c in countries:
                    country_scores[c] += w
            if _detect_route(title):
                route_count += 1

    country_scores = {c: min(s, 100) for c, s in country_scores.items()}
    rt = _route_score(route_count)

    geo_scores = {}
    for mat, df_c in import_shares.items():
        if df_c.empty:
            geo_scores[mat] = 0.0
            continue
        ws = sum(r["수입비중"] * country_scores.get(r["국가코드"], 0)
                 for _, r in df_c.iterrows())
        geo_scores[mat] = round(min(ws + rt, 100), 2)

    return geo_scores, dict(country_scores), route_count


# ── S6: 종합 위험지수 ─────────────────────────────────────
def calc_risk_results(oil_scores: dict, fx_score: float, imp_scores: dict,
                      vuln_scores: dict, geo_scores: dict) -> dict:
    results = {}
    for mat in ["PP", "PE", "PVC", "PET"]:
        oil  = oil_scores.get(mat, 0)
        imp  = imp_scores.get(mat, 0)
        vuln = vuln_scores.get(mat, 0)
        geo  = geo_scores.get(mat, 0)
        total = round(W_OIL*oil + W_FX*fx_score + W_IMP*imp + W_VULN*vuln + W_GEO*geo, 2)
        results[mat] = {
            "위험지수": total,
            "등급":    risk_grade(total, mat),
            "유가":    oil,
            "환율":    fx_score,
            "수입가격": imp,
            "수입구조": vuln,
            "지정학":  geo,
        }
    return results


def top_contributors(r: dict, n: int = 3) -> list[str]:
    W = {"유가": W_OIL, "환율": W_FX, "수입가격": W_IMP, "수입구조": W_VULN, "지정학": W_GEO}
    LABEL = {
        "유가": "국제유가 상승", "환율": "환율 상승",
        "수입가격": "수입단가 급등", "수입구조": "수입집중 리스크", "지정학": "지정학 리스크",
    }
    c = {LABEL[k]: r.get(k, 0) * W[k] for k in W if r.get(k, 0) > 0}
    return [k for k, _ in sorted(c.items(), key=lambda x: -x[1])][:n]
