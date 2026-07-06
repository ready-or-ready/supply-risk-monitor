"""
공급망 마비 대응 정밀 솔루션 — 네비게이션 진입점
"""
import streamlit as st

pg = st.navigation([
    st.Page("홈.py",                      title="홈",          icon="🏠"),
    st.Page("pages/1_대시보드.py",         title="대시보드",    icon="📊"),
    st.Page("pages/2_지정학_리스크.py",    title="지정학 리스크", icon="🌏"),
    st.Page("pages/3_리포트_생성.py",      title="리포트 생성", icon="📄"),
])
pg.run()
