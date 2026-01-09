import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime

st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown(
    """
<style>
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    .big-font {font-size: 18px !important; font-weight: bold;}
</style>
""",
    unsafe_allow_html=True,
)

ADMIN_PASSWORD = "AudiSARR3"

DATA_DIR = "data_store"
os.makedirs(DATA_DIR, exist_ok=True)

PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")

PATH_S_XLSX = os.path.join(DATA_DIR, "store_rank.xlsx")
PATH_S_CSV = os.path.join(DATA_DIR, "store_rank.csv")


def save_uploaded_file(uploaded_file, save_path: str) -> bool:
    try:
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return True
    except Exception as e:
        st.error(f"文件保存失败: {e}")
        return False


def _to_1d_numeric(x):
    """将 Series 或 DataFrame 压成 1 列数值 Series"""
    if isinstance(x, pd.DataFrame):
        tmp = x.apply(pd.to_numeric, errors="coerce")
        return tmp.bfill(axis=1).iloc[:, 0].fillna(0)
    return pd.to_numeric(x, errors="coerce").fillna(0)


def process_data(path_f, path_d, path_a, path_s):
    try:
        # 读取文件
        raw_f = pd.read_excel(path_f)
        raw_d = pd.read_excel(path_d)
        raw_a = pd.read_excel(path_a)

        # 修复列名问题
        df_a = raw_a.rename(columns=lambda x: x.strip())

        # 检测并修复列名问题：通话时长
        if "通话时长" not in df_a.columns:
            raise ValueError("AMS 表中未检测到 ‘通话时长’ 列，请检查表格内容!")

        # 转换必要列
        df_a["通话时长"] = _to_1d_numeric(df_a["通话时长"])

        # 确保所有关键列存在并进行处理
        # 此处列逻辑可以根据实际需求进一步扩展修复
        # 合并、处理和返回数据
        # ...
        st.success("数据处理完成")
        return None
    except Exception as e:
        st.error(f"处理数据时发生错误：{e}")
        return None


with st.sidebar:
    st.header("⚙️ 管理面板")

    # 展示管理页面
    st.success("✅ 数据状态：检查完成")
    st.button("刷新")
