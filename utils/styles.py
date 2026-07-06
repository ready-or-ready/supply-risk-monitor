import streamlit as st

def apply_global_styles():
    st.markdown("""
    <style>
    /* 헤딩 앵커 링크 아이콘 숨김 */
    h1 a, h2 a, h3 a, h4 a { display: none !important; }
    </style>
    """, unsafe_allow_html=True)
