"""
지정학 리스크 모니터링 (core_func_2 로직)
키워드 감지 → 리스크 유형 분류 → 경보 카드 데이터 생성
"""
import pandas as pd
import re
from collections import defaultdict
from datetime import datetime

CHAR_MAP = {"美中": "미중", "中美": "미중", "美": "미국", "中": "중국", "日": "일본"}

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

RISK_TYPE_MAP = {
    "중국 수출규제": "중국발 수출 제한",
    "중국 화학공장": "중국 화학공장 가동 차질",
    "중국 전력난":   "중국 화학공장 가동 차질",
    "중국 나프타":   "중국 화학공장 가동 차질",
    "중국 물류":     "물류 차질",
    "미중 관세":     "미중 무역분쟁·수출규제",
    "미중 무역분쟁": "미중 무역분쟁·수출규제",
    "대만해협":      "정정불안(중국-대만 긴장)",
    "미국 에탄":     "에너지 공급 차질(미국)",
    "미국 텍사스":   "에너지 공급 차질(미국)",
    "사우디 감산":   "에너지 가격 급등",
    "러시아":        "전쟁·분쟁",
    "우크라이나":    "전쟁·분쟁",
    "이란":          "전쟁·분쟁",
}

ROUTE_RISK_MAP = {
    "홍해":    "물류 차질(홍해·수에즈)",
    "수에즈":  "물류 차질(홍해·수에즈)",
    "호르무즈": "호르무즈 해협 분쟁",
}

RISK_IMPACT_PATH: dict[str, str] = {
    "중국발 수출 제한":          "공급 가용성 감소 — 중국산 원재료 대체 조달 필요",
    "중국 화학공장 가동 차질":   "원재료 생산 차질 → 공급량 감소",
    "물류 차질":                 "납기 지연 · 운임 상승",
    "미중 무역분쟁·수출규제":    "관세 비용 상승 · 수입 루트 불안",
    "정정불안(중국-대만 긴장)":  "중국·대만 연관 원재료 공급 불안",
    "호르무즈 해협 분쟁":        "나프타·에너지 원가 상승",
    "물류 차질(홍해·수에즈)":    "납기 지연 · 해상 운임 상승",
    "에너지 공급 차질(미국)":    "에탄 공급 감소 → PE 원가 상승",
    "에너지 가격 급등":          "전 원재료 에너지 원가 상승",
    "전쟁·분쟁":                 "공급망 불안 · 물류 차질",
}

ROUTE_EXPLANATION: dict[str, str] = {
    "호르무즈 해협 분쟁":     "호르무즈 해협은 중동 원유·LNG 수송 루트로, 원재료인 나프타 원가 상승과 에너지 비용을 높이는 영향을 미칩니다.",
    "물류 차질(홍해·수에즈)": "홍해·수에즈는 컨테이너 해운 루트로, 납기 지연과 운임 상승에 영향을 미칩니다.",
}


def _normalize(t: str) -> str:
    for a, b in CHAR_MAP.items():
        t = t.replace(a, b)
    return t

def _detect_common(title: str) -> list:
    n = _normalize(title)
    return [(kw, m["weight"], m["countries"]) for kw, m in COMMON_KEYWORDS.items() if kw in n]

def _detect_route(title: str) -> list:
    return [kw for kw in ROUTE_KEYWORDS if kw in title]


def classify_events(df_rss: pd.DataFrame, df_notice: pd.DataFrame) -> dict:
    """
    RSS + 외교부 공지 → 리스크 유형별 집계
    반환: {risk_type: {rss_count, notice_count, route_kws, sample_titles}}
    """
    agg = defaultdict(lambda: {
        "rss_count": 0, "notice_count": 0,
        "route_kws": set(), "sample_titles": [],
    })
    seen = set()

    for df, key in [(df_rss, "rss_count"), (df_notice, "notice_count")]:
        if df.empty:
            continue
        for _, row in df.iterrows():
            uid = row.get("id", "")
            if uid and uid in seen:
                continue
            if uid:
                seen.add(uid)
            title = row.get("제목", "")
            for kw, _, _ in _detect_common(title):
                rt = RISK_TYPE_MAP.get(kw)
                if rt:
                    agg[rt][key] += 1
                    if len(agg[rt]["sample_titles"]) < 2:
                        agg[rt]["sample_titles"].append(title[:45] + "...")
            for rkw in _detect_route(title):
                rt = ROUTE_RISK_MAP.get(rkw)
                if rt:
                    agg[rt][key] += 1
                    agg[rt]["route_kws"].add(rkw)

    return dict(agg)


def event_severity(total_count: int) -> tuple[str, str]:
    if total_count >= 15: return "심각", "🔴"
    if total_count >= 8:  return "경계", "🟠"
    if total_count >= 3:  return "주의", "🟡"
    return "모니터링", "🟢"


# ── 완화 요인 감지 설정 ────────────────────────────────────

# 제목만으로 충분히 구체적인 키워드 (단일 str 또는 AND 튜플)
MITIGATION_SPECIFIC: dict = {
    # 정부 지원
    "나프타 지원":           {"type": "정부 원가 지원"},
    "기초유분 지원":         {"type": "정부 원가 지원"},
    "원재료 지원":           {"type": "정부 원가 지원"},
    "석유화학 지원":         {"type": "정부 원가 지원"},
    "원가 지원":             {"type": "정부 원가 지원"},
    ("원가", "지원"):        {"type": "정부 원가 지원"},   # "원가 인상분 정부 지원" 등 비인접 표현
    ("정부", "원재료"):      {"type": "정부 원가 지원"},   # "정부, 원재료 수급 지원"
    # 원재료명이 제목에 이미 있는 가격 변동
    ("석유화학", "인하"):    {"type": "구매 여건 개선"},
    ("석유화학", "하락"):    {"type": "구매 여건 개선"},
    ("폴리에틸렌", "인하"):  {"type": "구매 여건 개선"},
    ("폴리프로필렌", "인하"): {"type": "구매 여건 개선"},
    ("나프타", "하락"):      {"type": "원료비 하락"},
    ("나프타", "인하"):      {"type": "원료비 하락"},
    ("에틸렌", "하락"):      {"type": "원료비 하락"},
    ("에틸렌", "인하"):      {"type": "원료비 하락"},
    # 물류·공급 정상화
    "항로 재개":             {"type": "물류 정상화"},
    "물류 정상화":           {"type": "물류 정상화"},
    "공급 정상화":           {"type": "공급망 안정"},
    "홍해 정상화":           {"type": "물류 정상화"},
    # 무역 완화
    "관세 인하":             {"type": "무역 여건 개선"},
    "관세 유예":             {"type": "무역 여건 개선"},
    "수출 규제 해제":        {"type": "무역 여건 개선"},
}

# 가격 신호: 제목에 아래 두 조건 모두 필요
_PRICE_MUST   = ["가격", "단가", "납품가"]   # 이 중 하나
_PRICE_SIGNAL = ["인하", "하락"]              # 이 중 하나

# 원재료 맥락: 제목 또는 요약에 하나라도 있으면 히트
_MATERIAL_CONTEXT = [
    "석유화학", "나프타", "기초유분", "원자재",
    "폴리에틸렌", "폴리프로필렌", "폴리염화비닐",
    "에틸렌", "프로필렌",
    "PE", "PP", "PVC", "PET",
]


def _detect_mitigation(title: str, summary: str = "") -> list:
    """완화 요인 감지. 반환: [(matched_label, mitigation_type), ...]

    1) 제목 기반 특정 키워드 (MITIGATION_SPECIFIC)
    2) 가격 신호(제목) + 원재료 맥락(제목 or 요약) → '구매 여건 개선'
    """
    results = []

    # 1. 특정 키워드 (제목만)
    for kw, v in MITIGATION_SPECIFIC.items():
        if isinstance(kw, tuple):
            if all(k in title for k in kw):
                results.append((" & ".join(kw), v["type"]))
        else:
            if kw in title:
                results.append((kw, v["type"]))

    # 2. 가격 신호 + 원재료 맥락
    has_price = any(p in title for p in _PRICE_MUST) and any(s in title for s in _PRICE_SIGNAL)
    if has_price:
        context = title + " " + summary
        mat = next((m for m in _MATERIAL_CONTEXT if m in context), None)
        if mat:
            signal = next(s for s in _PRICE_SIGNAL if s in title)
            results.append((f"가격 {signal} ({mat})", "구매 여건 개선"))

    # 3. "정부 지원" + 원재료 맥락 (제목 or 요약)
    if ("정부" in title) and ("지원" in title):
        context = title + " " + summary
        mat = next((m for m in _MATERIAL_CONTEXT if m in context), None)
        if mat:
            results.append((f"정부 지원 ({mat})", "정부 원가 지원"))

    return results


def build_mitigation_cards(df_rss: pd.DataFrame, df_notice: pd.DataFrame,
                           df_extra: pd.DataFrame = None) -> list[dict]:
    """연합뉴스 RSS + 외교부 공지 + 보완 소스에서 완화 요인 카드 생성.
    df_rss / df_notice 에 '완화_키워드' 컬럼을 in-place로 추가한다.
    df_extra: 구글뉴스 등 보완 소스 (완화_키워드 in-place 추가 없이 스캔만)
    """
    agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "keywords": set(), "sample_titles": []})
    seen: set = set()  # 기사 제목 기준 중복 제거

    sources = [df_rss, df_notice]
    if df_extra is not None and not df_extra.empty:
        sources.append(df_extra)

    for df in sources:
        if df.empty:
            continue
        # 완화_키워드 컬럼 생성 (title + summary 기반)
        if "요약" in df.columns:
            df["완화_키워드"] = [
                _detect_mitigation(str(t), str(s))
                for t, s in zip(df["제목"], df["요약"])
            ]
        else:
            df["완화_키워드"] = [_detect_mitigation(str(t)) for t in df["제목"]]

        for _, row in df.iterrows():
            title = row.get("제목", "")
            if not title or title in seen:
                continue
            seen.add(title)
            summary = row.get("요약", "")
            detections = _detect_mitigation(title, summary)
            if detections:
                agg["구매 여건 개선"]["count"] += 1
                for _, mit_type in detections:
                    agg["구매 여건 개선"]["keywords"].add(mit_type)  # 세부 유형을 근거로
                if len(agg["구매 여건 개선"]["sample_titles"]) < 2:
                    agg["구매 여건 개선"]["sample_titles"].append(title[:45] + "...")

    cards = []
    for mit_type, data in sorted(agg.items(), key=lambda x: -x[1]["count"]):
        cards.append({
            "type": mit_type,
            "count": data["count"],
            "keywords": sorted(data["keywords"]),
            "sample_title": data["sample_titles"][0] if data["sample_titles"] else "",
        })
    return cards


def build_alert_cards(event_agg: dict, brent_5d_ret: float) -> list[dict]:
    """경보 카드 리스트 (Streamlit 렌더링용)"""
    cards = []
    for rt, data in sorted(event_agg.items(),
                            key=lambda x: -(x[1]["rss_count"] + x[1]["notice_count"])):
        total = data["rss_count"] + data["notice_count"]
        severity, icon = event_severity(total)
        evidence = []
        if data["rss_count"] > 0:
            evidence.append(f"연합뉴스 {data['rss_count']}건")
        if data["notice_count"] > 0:
            evidence.append(f"외교부 공지 {data['notice_count']}건")
        if abs(brent_5d_ret) >= 1.5:
            direction = "상승" if brent_5d_ret > 0 else "하락"
            evidence.append(f"유가 5일 {brent_5d_ret:+.1f}% {direction}")
        cards.append({
            "icon": icon,
            "severity": severity,
            "risk_type": rt,
            "impact_path": RISK_IMPACT_PATH.get(rt, "공급망 리스크"),
            "explanation": ROUTE_EXPLANATION.get(rt, ""),
            "evidence": ", ".join(evidence) if evidence else "없음",
            "sample_title": data["sample_titles"][0] if data["sample_titles"] else "",
            "total_count": total,
        })
    return cards
