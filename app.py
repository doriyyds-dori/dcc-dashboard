import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ================= 1. 页面基础设置 =================
st.set_page_config(page_title="Audi DCC 质检六维看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .metric-container {background-color: #f0f2f6; padding: 10px; border-radius: 5px; border-left: 5px solid #bb0a30;}
    .big-font {font-size: 20px !important; font-weight: bold;}
    h3 {border-bottom: 2px solid #e6e6e6; padding-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

st.title("🏎️ Audi DCC | 质检六维效能看板")

# ================= 2. 侧边栏：三表上传 =================
with st.sidebar:
    st.header("📂 数据源配置")
    file_funnel = st.file_uploader("1. 漏斗指标表 (含线索/到店)", type=["xlsx", "csv"])
    file_dcc = st.file_uploader("2. 管家排名表 (含6大质检得分)", type=["xlsx", "csv"])
    file_ams = st.file_uploader("3. AMS跟进表 (含通话时长)", type=["xlsx", "csv"])

def find_col(df, keywords):
    for col in df.columns:
        for k in keywords:
            if k in col: return col
    return df.columns[0]

# ================= 3. 主程序逻辑 =================
if file_funnel and file_dcc and file_ams:
    try:
        # 读取数据
        df_f = pd.read_csv(file_funnel) if file_funnel.name.endswith('csv') else pd.read_excel(file_funnel)
        df_d = pd.read_csv(file_dcc) if file_dcc.name.endswith('csv') else pd.read_excel(file_dcc)
        df_a = pd.read_csv(file_ams) if file_ams.name.endswith('csv') else pd.read_excel(file_ams)

        # --- ⚙️ 关键列名映射 (核心升级) ---
        with st.expander("🔧 点击展开：配置 6 大关键得分列名", expanded=True):
            st.info("请确保下方选中的列名与您 Excel 中的表头一一对应")
            c1, c2, c3 = st.columns(3)
            
            with c1:
                st.markdown("**1. 基础信息**")
                col_name_f = st.selectbox("【漏斗表】姓名列", df_f.columns, index=df_f.columns.get_loc(find_col(df_f, ['顾问','姓名'])), key='nf')
                col_name_d = st.selectbox("【管家表】姓名列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['顾问','姓名'])), key='nd')
                col_name_a = st.selectbox("【AMS表】姓名列", df_a.columns, index=df_a.columns.get_loc(find_col(df_a, ['顾问','姓名'])), key='na')
                col_score_total = st.selectbox("质检总分列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['质检','总分'])))
                
            with c2:
                st.markdown("**2. 流程与基石指标**")
                # 60秒 / 用车需求
                col_60s = st.selectbox("【60秒通话占比】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['60秒','时长占比'])))
                col_needs = st.selectbox("【用车需求】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['需求','用车'])))
                col_wechat = st.selectbox("【添加微信】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['微信','加微'])))

            with c3:
                st.markdown("**3. 专业与结果指标**")
                # 车型 / 政策 / 明确到店
                col_car = st.selectbox("【车型信息】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['车型','信息'])))
                col_policy = st.selectbox("【政策相关】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['政策','话术'])))
                col_time = st.selectbox("【明确到店时间】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['明确','时间'])))

            # 隐式配置其他两表的关键列 (简化显示)
            col_leads = find_col(df_f, ['线索','总数'])
            col_visit = find_col(df_f, ['到店','进店'])
            col_duration = find_col(df_a, ['时长','通话'])

        # --- 数据清洗与融合 (修复 Bug 的核心) ---
        
        # 1. 统一列名为 Name
        df_f = df_f.rename(columns={col_name_f: 'Name'})
        df_d = df_d.rename(columns={col_name_d: 'Name'})
        df_a = df_a.rename(columns={col_name_a: 'Name'})
        
        # 2. 强制转为字符串并去除前后空格 (解决匹配不到的问题)
        df_f['Name'] = df_f['Name'].astype(str).str.strip()
        df_d['Name'] = df_d['Name'].astype(str).str.strip()
        df_a['Name'] = df_a['Name'].astype(str).str.strip()
        
        # 3. 合并
        merged = pd.merge(df_f, df_d, on='Name', how='inner')
        merged = pd.merge(merged, df_a, on='Name', how='inner')
        
        # 4. 安全检查：如果合并后没数据，停止运行并提示
        if len(merged) == 0:
            st.error("⚠️ **数据合并结果为空！**")
            st.markdown("""
            **可能原因：**
            1. 三个表格里的 **顾问姓名** 写法不一致（例如：“王小明” vs “王 小明”）。
            2. 您在上方配置栏
