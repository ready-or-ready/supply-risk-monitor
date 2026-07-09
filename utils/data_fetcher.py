"""
공통 데이터 수집 모듈
관세청 GW / 한국은행 ECOS / yfinance / 연합뉴스 RSS / 외교부 안전공지
"""
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import yfinance as yf
import re
import warnings
from datetime import datetime, timedelta
from collections import defaultdict
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import streamlit as st

warnings.filterwarnings("ignore")

# ── HS코드 / 리스크국가 상수 ────────────────────────────────
HS_CODES = {
    "PP":  ["390210"],
    "PE":  ["390110", "390120", "390140", "390190"],
    "PVC": ["390410", "390421", "390422"],
    "PET": ["390761", "390769"],
}

RISK_CODES = {"CN", "RU", "IR", "SA"}

COUNTRY_NAME_TO_CODE = {
    "중국": "CN", "미국": "US", "미합중국": "US", "일본": "JP",
    "사우디아라비아": "SA", "아랍에미리트 연합": "AE", "이란": "IR",
    "러시아": "RU", "우크라이나": "UA", "대만": "TW",
    "싱가포르": "SG", "말레이시아": "MY", "인도": "IN",
    "태국": "TH", "인도네시아": "ID", "쿠웨이트": "KW",
    "카타르": "QA", "오만": "OM", "독일": "DE",
    "네덜란드": "NL", "벨기에": "BE",
}

TICKERS = {
    "WTI":    "CL=F",
    "Brent":  "BZ=F",
    "KOSPI":  "^KS11",
    "대한유화": "006650.KS",
    "USDKRW": "USDKRW=X",
}

CUSTOMS_URL = "http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
MOF_URL     = "https://apis.data.go.kr/1262000/CountrySafetyService6/getCountrySafetyList6"

# ── SSL 우회 어댑터 (연합뉴스 RSS) ──────────────────────────
class LegacyTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.options |= 0x4
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

rss_session = requests.Session()
rss_session.mount("https://", LegacyTLSAdapter())

# ── API 키 (st.secrets) ───────────────────────────────────
def _customs_key():
    return st.secrets["CUSTOMS_KEY"]

def _ecos_key():
    return st.secrets["ECOS_KEY"]

def _mof_key():
    return st.secrets["MOF_KEY"]


# ══════════════════════════════════════════════════════════
# 관세청 GW
# ══════════════════════════════════════════════════════════
def _fetch_trade_raw(hs_code: str, strt: str, end: str) -> ET.Element:
    """관세청 GW 단일 HS코드 조회 — 타임아웃 시 최대 3회 재시도"""
    import time as _time
    last_exc = None
    for attempt in range(3):
        try:
            res = requests.get(CUSTOMS_URL, params={
                "serviceKey": _customs_key(),
                "strtYymm": strt,
                "endYymm": end,
                "hsSgn": hs_code,
            }, timeout=20)
            return ET.fromstring(res.text)
        except requests.exceptions.Timeout as e:
            last_exc = e
            if attempt < 2:
                _time.sleep(2)
    raise last_exc

def _parse_monthly(root: ET.Element) -> dict:
    monthly = {}
    for item in root.iter("item"):
        yr = item.findtext("year") or ""
        if yr == "총계" or not yr:
            continue
        ym  = yr.replace(".", "")
        dlr = float(item.findtext("impDlr") or 0)
        wgt = float(item.findtext("impWgt") or 0)
        if ym not in monthly:
            monthly[ym] = {"imp_dlr": 0.0, "imp_wgt_kg": 0.0}
        monthly[ym]["imp_dlr"]    += dlr
        monthly[ym]["imp_wgt_kg"] += wgt
    return monthly

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_monthly_unit_price(material: str, strt: str, end: str) -> pd.DataFrame:
    """관세청 GW: 품목별 월별 수입단가 (USD/kg)"""
    codes = HS_CODES[material]
    combined = {}
    for code in codes:
        for ym, v in _parse_monthly(_fetch_trade_raw(code, strt, end)).items():
            if ym not in combined:
                combined[ym] = {"imp_dlr": 0.0, "imp_wgt_kg": 0.0}
            combined[ym]["imp_dlr"]    += v["imp_dlr"]
            combined[ym]["imp_wgt_kg"] += v["imp_wgt_kg"]
    rows = []
    for ym in sorted(combined):
        d = combined[ym]["imp_dlr"]
        w = combined[ym]["imp_wgt_kg"]
        rows.append({"품목": material, "연월": ym,
                     "수입단가_USD_kg": round(d / w, 4) if w else None})
    return pd.DataFrame(rows)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_country_shares(material: str, strt: str, end: str) -> pd.DataFrame:
    """관세청 GW: 품목별 국가별 수입비중"""
    codes = HS_CODES[material]
    all_rows = []
    for code in codes:
        root = _fetch_trade_raw(code, strt, end)
        for item in root.iter("item"):
            yr = item.findtext("year") or ""
            if yr == "총계" or not yr:
                continue
            cn  = item.findtext("statCdCntnKor1") or ""
            dlr = float(item.findtext("impDlr") or 0)
            wgt = float(item.findtext("impWgt") or 0)
            if dlr > 0 and cn:
                all_rows.append({"국가명": cn, "수입금액_USD": dlr, "수입중량_kg": wgt})
    if not all_rows:
        return pd.DataFrame()
    df    = pd.DataFrame(all_rows).groupby("국가명", as_index=False).sum()
    total = df["수입금액_USD"].sum()
    df["수입비중"]   = (df["수입금액_USD"] / total).round(4)
    df["수입비중_%"] = (df["수입비중"] * 100).round(2)
    df["국가코드"]   = df["국가명"].map(COUNTRY_NAME_TO_CODE).fillna("기타")
    return df.sort_values("수입비중", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════════
# 한국은행 ECOS
# ══════════════════════════════════════════════════════════
def _ecos_get(url: str, **kwargs) -> requests.Response:
    """ECOS API 호출 — 예외 메시지에서 API 키 마스킹"""
    try:
        return requests.get(url, **kwargs)
    except Exception as e:
        key = _ecos_key()
        safe_msg = str(e).replace(key, "***")
        raise type(e)(safe_msg) from None

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_usd_krw_monthly(start_ym: str, end_ym: str) -> dict:
    """ECOS: 월별 USD/KRW 환율 {YYYYMM: float}"""
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{_ecos_key()}"
           f"/json/kr/1/100/731Y004/M/{start_ym}/{end_ym}/0000001")
    rows = _ecos_get(url, timeout=15).json().get("StatisticSearch", {}).get("row", [])
    if not rows:
        raise ValueError("ECOS 월별 환율 데이터 없음")
    return {r["TIME"]: float(r["DATA_VALUE"].replace(",", "")) for r in rows}


# ══════════════════════════════════════════════════════════
# yfinance (시장 데이터)
# ══════════════════════════════════════════════════════════
_yf_session = requests.Session()
_yf_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
})

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_market_data(days: int = 30) -> pd.DataFrame:
    """yfinance: Brent / WTI / USDKRW / 대한유화 / KOSPI 일별 종가"""
    frames = {}
    for label, ticker in TICKERS.items():
        for attempt in range(3):
            try:
                df = yf.download(ticker, period=f"{days}d", interval="1d",
                                 progress=False, auto_adjust=True,
                                 session=_yf_session)
                if not df.empty:
                    close = df["Close"].squeeze()
                    close.index = close.index.strftime("%Y-%m-%d")
                    frames[label] = close
                break
            except Exception:
                if attempt == 2:
                    pass
    result = pd.DataFrame(frames)
    result.index.name = "날짜"
    return result.dropna(how="all")


# ══════════════════════════════════════════════════════════
# 연합뉴스 RSS + 외교부 안전공지
# ══════════════════════════════════════════════════════════
YONHAP_RSS = {
    "경제":  "https://www.yna.co.kr/rss/economy.xml",
    "산업":  "https://www.yna.co.kr/rss/industry.xml",
    "국제":  "https://www.yna.co.kr/rss/international.xml",
    "정치":  "https://www.yna.co.kr/rss/politics.xml",
}

def _parse_rss_date(s: str):
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"]:
        try:
            return datetime.strptime(s.strip(), fmt).replace(tzinfo=None)
        except Exception:
            pass
    return None

def _parse_notice_date(title: str, yr: int = None):
    if yr is None:
        yr = datetime.today().year
    m = re.search(r'\b(\d{2})\.(\d{1,2})\.(\d{1,2})\.?\b', title)
    if m:
        try:
            return datetime(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
    m = re.search(r'\((\d{1,2})\.(\d{1,2})\.?(?:자)?\)', title)
    if m:
        try:
            return datetime(yr, int(m.group(1)), int(m.group(2)))
        except Exception:
            pass
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_news_and_notices(window_days: int = 14) -> tuple[pd.DataFrame, pd.DataFrame]:
    """연합뉴스 RSS + 외교부 안전공지 수집 (TTL 1시간)"""
    cutoff = datetime.today() - timedelta(days=window_days)

    # RSS
    rss_rows = []
    for feed, url in YONHAP_RSS.items():
        try:
            res  = rss_session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            root = ET.fromstring(res.text)
            for item in root.findall(".//item"):
                title = item.findtext("title") or ""
                link  = item.findtext("link")  or ""
                desc  = item.findtext("description") or ""
                dt    = _parse_rss_date(item.findtext("pubDate") or "")
                if dt and dt < cutoff:
                    continue
                rss_rows.append({"소스": f"연합뉴스_{feed}", "제목": title,
                                 "요약": desc[:300], "날짜": dt, "id": link})
        except Exception:
            pass
    df_rss = pd.DataFrame(rss_rows) if rss_rows else pd.DataFrame(columns=["소스","제목","요약","날짜","id"])

    # 외교부
    notice_rows = []
    try:
        res   = requests.get(MOF_URL, params={
            "serviceKey": _mof_key(), "numOfRows": 200, "pageNo": 1, "returnType": "json",
        }, timeout=15)
        items = res.json()["response"]["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        for item in items:
            title  = item.get("title", "")
            dt_str = item.get("wrt_dt", "")
            dt     = None
            if dt_str:
                try:
                    dt = datetime.strptime(dt_str[:10], "%Y-%m-%d")
                except Exception:
                    pass
            if dt is None:
                dt = _parse_notice_date(title)
            if dt and dt < cutoff:
                continue
            notice_rows.append({"소스": "외교부", "제목": title, "날짜": dt,
                                 "id": item.get("sfty_notice_id", "")})
    except Exception:
        pass
    df_notice = pd.DataFrame(notice_rows) if notice_rows else pd.DataFrame(columns=["소스","제목","날짜","id"])

    return df_rss, df_notice


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_google_news(query: str, window_days: int = 30, max_results: int = 10) -> pd.DataFrame:
    """구글 뉴스 RSS 키워드 검색 (TTL 1시간)"""
    import urllib.parse
    cutoff = datetime.today() - timedelta(days=window_days)
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        res.raise_for_status()
        root = ET.fromstring(res.content)
        rows = []
        for item in root.findall(".//item"):
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            if not link:
                guid_el = item.find("guid")
                link = guid_el.text if guid_el is not None else ""
            dt = _parse_rss_date(item.findtext("pubDate") or "")
            if dt and dt < cutoff:
                continue
            source_el = item.find("source")
            source = source_el.text if source_el is not None else "구글뉴스"
            rows.append({"소스": source, "제목": title, "날짜": dt, "id": link})
        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["소스", "제목", "날짜", "id"])
        return df.head(max_results)
    except Exception:
        return pd.DataFrame(columns=["소스", "제목", "날짜", "id"])


import os

# ══════════════════════════════════════════════════════════
# KOTRA 글로벌 공급망 인사이트
# ══════════════════════════════════════════════════════════
_KOTRA_GSI_URL = "https://apis.data.go.kr/B410001/globalSupplyInsights/globalSupplyInsights"

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_kotra_supply_insights(num: int = 3) -> list[dict]:
    """KOTRA 글로벌 공급망 인사이트 최신 N건 반환 (TTL 24시간)"""
    try:
        res = requests.get(
            _KOTRA_GSI_URL,
            params={"serviceKey": _customs_key(), "pageNo": 1, "numOfRows": num, "type": "json"},
            timeout=15,
        )
        items = res.json()["response"]["body"]["itemList"]["item"]
        if isinstance(items, dict):
            items = [items]
        result = []
        for it in items:
            files = it.get("realAtfileInfoList", {}).get("realAtfileInfo", [])
            if isinstance(files, dict):
                files = [files]
            pdf_url = next((f["realAtfileUrl"] for f in files if f.get("realAtfileName", "").endswith(".pdf")), "")
            result.append({
                "제목":   it.get("nttSj", ""),
                "날짜":   it.get("othbcDt", "")[:10],
                "링크":   it.get("kotraNewsUrl", ""),
                "pdf":    pdf_url,
            })
        return result
    except Exception:
        return []


# ══════════════════════════════════════════════════════════
# KOTRA 미국 / 중국 글로벌 이슈 모니터링
# ══════════════════════════════════════════════════════════
_USA_ISSUE_URL   = "https://apis.data.go.kr/B410001/usaGlobalIssueMonitoring/getUsaGlobalIssueMonitoring"
_CHINA_ISSUE_URL = "https://apis.data.go.kr/B410001/chinaGlobalIssueMonitoring/getChinaGlobalIssueMonitoring"

_USA_KEYWORDS   = ["관세", "에너지", "화학", "에탄", "공급망", "수출입", "무역", "제재", "셰일"]
# 중국: 행사 종료 요약 성격의 제목만 제외 (폐막 보고 등)
# ※ 정부업무보고는 경제목표·산업정책 발표라 제외하지 않음
_CHINA_EXCLUDE = ["폐막"]

def _parse_kotra_items(data: dict) -> list[dict]:
    try:
        items = data["response"]["body"]["itemList"]["item"]
        if isinstance(items, dict):
            items = [items]
        result = []
        for it in items:
            result.append({
                "제목":  it.get("nttSj", "").strip(),
                "요약":  it.get("smmarCn", "").replace("&middot;", "·").replace("&nbsp;", " ").strip(),
                "날짜":  (it.get("othbcDt") or it.get("regDt") or "")[:10],
                "pdf":   it.get("fileLink", ""),
                "무역관": it.get("kbc", ""),
            })
        return result
    except Exception:
        return []

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_usa_issues(num_fetch: int = 20, num_show: int = 4) -> list[dict]:
    """미국 글로벌 이슈 모니터링 — 관세·에너지·화학 키워드 필터 후 최신 N건"""
    try:
        res   = requests.get(_USA_ISSUE_URL,
                             params={"serviceKey": _customs_key(), "pageNo": 1,
                                     "numOfRows": num_fetch, "type": "json"}, timeout=15)
        items = _parse_kotra_items(res.json())
        filtered = [it for it in items
                    if any(kw in it["제목"] + it["요약"] for kw in _USA_KEYWORDS)]
        return (filtered or items)[:num_show]
    except Exception:
        return []

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_china_issues(num_show: int = 6) -> list[dict]:
    """중국 글로벌 이슈 모니터링 — 올해 항목 중 정치 이벤트 제외 후 최신 N건"""
    import datetime as _dt
    this_year = str(_dt.date.today().year)
    try:
        res   = requests.get(_CHINA_ISSUE_URL,
                             params={"serviceKey": _customs_key(), "pageNo": 1,
                                     "numOfRows": 83, "type": "json"}, timeout=15)
        items = _parse_kotra_items(res.json())
        # 올해 항목만, 정치 이벤트 제목 제외
        filtered = [
            it for it in items
            if it["날짜"].startswith(this_year)
            and not any(ex in it["제목"] for ex in _CHINA_EXCLUDE)
        ]
        # 올해 항목이 없으면 전체 최신건으로 폴백
        return (filtered if filtered else items)[:num_show]
    except Exception:
        return []


# ══════════════════════════════════════════════════════════
# 산업통상부 CSV (NCC 스프레드)
# ══════════════════════════════════════════════════════════
_CSV_NAME = "산업통상부_석유화학  원자재가격동향_20260331.csv"
_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), _CSV_NAME)

@st.cache_resource(show_spinner=False)
def load_ncc_spread() -> pd.DataFrame:
    """산업통상부 CSV → NCC 스프레드 시계열 (앱 기동 시 1회 로드)"""
    df_raw = pd.read_csv(_CSV_PATH, index_col=0, encoding="utf-8")
    df_raw.index   = df_raw.index.str.strip()
    df_raw.columns = df_raw.columns.str.strip()

    ethylene = df_raw.loc["에틸렌"].astype(float)
    naphtha  = df_raw.loc["나프타"].astype(float)

    def _parse_col(col):
        yr, q_str = str(col).strip().split("_")
        q = int(q_str.replace("분기", ""))
        return pd.Timestamp(f"{yr}-{(q - 1) * 3 + 1:02d}")

    dates = [_parse_col(c) for c in df_raw.columns]
    df = pd.DataFrame({
        "날짜":           dates,
        "에틸렌_USD_ton": ethylene.values,
        "나프타_USD_ton":  naphtha.values,
    }).sort_values("날짜").reset_index(drop=True)
    df["스프레드_USD_ton"] = df["에틸렌_USD_ton"] - df["나프타_USD_ton"]
    return df
