import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    div[data-testid="stFormSubmitButton"] button {
        width: 100%;
        background-color: #bb0a30;
        color: white;
        border: none;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ================= 2. 基础配置 =================
ADMIN_PASSWORD = "AudiSARR3" 
DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")
PATH_S = os.path.join(DATA_DIR, "store_rank.csv")

def save_uploaded_file(uploaded_file, save_path):
    with open(save_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return True

# ================= 3. 侧边栏 =================
with st.sidebar:
    st.header("⚙️ 管理面板")
    has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and os.path.exists(PATH_S)
    
    if has_data: st.success("✅ 数据状态：已就绪")
    else: st.warning("⚠️ 暂无数据")
    st.markdown("---")
    
    with st.expander("🔐 更新数据 (仅限管理员)", expanded=True):
        pwd = st.text_input("输入管理员密码", type="password")
        if pwd == ADMIN_PASSWORD:
            st.info("🔓 身份验证通过")
            with st.form("update_form"):
                st.markdown("##### 请上传所有 4 个文件")
                new_f = st.file_uploader("1. 漏斗表", type=["xlsx", "csv"])
                new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"])
                new_a = st.file_uploader("3. AMS表", type=["xlsx", "csv"])
                new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"])
                
                if st.form_submit_button("🚀 确认更新"):
                    if new_f and new_d and new_a and new_s:
                        save_uploaded_file(new_f, PATH_F)
                        save_uploaded_file(new_d, PATH_D)
                        save_uploaded_file(new_a, PATH_A)
                        save_uploaded_file(new_s, PATH_S)
                        st.success("更新成功！")
                        st.rerun()
                    else:
                        st.error("❌ 必须传齐4个文件")

# ================= 4. 数据处理 (防崩溃版) =================
def smart_read(file_path, is_rank_file=False):
    try:
        if isinstance(file_path, str): is_csv = file_path.endswith('.csv') or file_path.endswith('.txt')
        else: is_csv = file_path.name.endswith('.csv')
        
        if is_csv: df = pd.read_csv(file_path)
        else: df = pd.read_excel(file_path)
        
        # 门店排名表特殊处理：跳过可能的元数据行
        if is_rank_file:
            target_cols = ['门店名称', '质检总分']
            # 如果第一行没找到关键列，尝试读第二行
            if not any(c in df.columns for c in target_cols):
                if is_csv: df = pd.read_csv(file_path, header=1)
                else: df = pd.read_excel(file_path, header=1)
        return df
    except: return None

def safe_div(df, num_col, denom_col):
    if num_col not in df.columns or denom_col not in df.columns: return 0
    num = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
    denom = pd.to_numeric(df[denom_col], errors='coerce').fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)

def process_data(path_f, path_d, path_a, path_s):
    try:
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        raw_s = smart_read(path_s, is_rank_file=True)
        
        if raw_f is None or raw_d is None or raw_a is None or raw_s is None: return None, None

        # --- A. 漏斗处理 ---
        # 自动寻找列名
        col_store = next((c for c in raw_f.columns if '门店' in str(c) or '代理' in str(c)), '门店名称')
        col_name = next((c for c in raw_f.columns if '顾问' in str(c) or '管家' in str(c)), '邀约专员/管家')
        col_leads = next((c for c in raw_f.columns if '有效线索' in str(c) or '线索量' in str(c)), '线索量')
        col_visits = next((c for c in raw_f.columns if '到店' in str(c) and '率' not in str(c)), '到店量')
        
        df_f = raw_f.rename(columns={col_store: '门店名称', col_name: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'})
        
        # 拆分
        df_store_data = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
        df_advisor_data = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()
        
        for df in [df_store_data, df_advisor_data]:
            df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
            df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
            df['线索到店率_数值'] = safe_div(df, '到店量', '线索量')
            df['线索到店率'] = (df['线索到店率_数值']*100).map('{:.1f}%'.format)

        # --- B. 顾问质检 ---
        # 映射列名
        d_map = {
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car',
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        }
        # 查找可能的微信列
        wechat_raw = next((c for c in raw_d.columns if '微信' in str(c) and '添加' in str(c)), '添加微信')
        df_d = raw_d.rename(columns=d_map)
        df_d['S_Wechat'] = raw_d[wechat_raw] if wechat_raw in raw_d.columns else 0
        
        # 仅保留需要的列
        target_score_cols = ['质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']
        cols_to_keep = ['邀约专员/管家'] + [c for c in target_score_cols if c in df_d.columns]
        df_d = df_d[cols_to_keep]
        for c in target_score_cols: 
            if c in df_d.columns: df_d[c] = pd.to_numeric(df_d[c], errors='coerce')

        # --- C. 门店质检 (排名表) ---
        s_map = {
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car',
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        }
        df_s = raw_s.rename(columns=s_map)
        s_wechat_raw = next((c for c in raw_s.columns if '微信' in str(c) and '添加' in str(c)), '添加微信')
        df_s['S_Wechat'] = raw_s[s_wechat_raw] if s_wechat_raw in raw_s.columns else 0
        
        # 确保列是数值
        s_cols_check = ['质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']
        for c in s_cols_check:
            if c in df_s.columns: df_s[c] = pd.to_numeric(df_s[c], errors='coerce')
        
        # --- D. AMS ---
        # 简单重命名逻辑
        a_map = {}
        for c in raw_a.columns:
            cs = str(c).strip()
            if '接通' in cs and '线索' in cs: a_map[c] = 'conn_num'
            elif '外呼' in cs and '线索' in cs and '需' not in cs and '二' not in cs and '三' not in cs: a_map[c] = 'conn_denom'
            elif '及时' in cs: a_map[c] = 'timely_num'
            elif '需外呼' in cs: a_map[c] = 'timely_denom'
            elif '二次' in cs: a_map[c] = 'call2_num'
            elif '需再呼' in cs and '二' not in cs: a_map[c] = 'call2_denom'
            elif '三次' in cs: a_map[c] = 'call3_num'
            elif '需再呼' in cs and '二' in cs: a_map[c] = 'call3_denom'
            elif '通话时长' in cs: a_map[c] = '通话时长'
            elif '管家' in cs or '顾问' in cs: a_map[c] = '邀约专员/管家'

        df_a = raw_a.rename(columns=a_map)
        ams_metrics = ['conn_num', 'conn_denom', 'timely_num', 'timely_denom', 'call2_num', 'call2_denom', 'call3_num', 'call3_denom']
        for c in ams_metrics:
            if c not in df_a.columns: df_a[c] = 0
            else: df_a[c] = pd.to_numeric(df_a[c], errors='coerce').fillna(0)

        # --- E. 合并 ---
        # 统一清理空格
        for df in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
            if '邀约专员/管家' in df.columns: df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
            if '门店名称' in df.columns: df['门店名称'] = df['门店名称'].astype(str).str.strip()

        # 合并顾问
        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
        full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')

        # 合并门店 (AMS聚合 + 质检文件)
        store_ams = full_advisors.groupby('门店名称')[ams_metrics].sum().reset_index()
        full_stores = pd.merge(df_store_data, df_s, on='门店名称', how='left')
        full_stores = pd.merge(full_stores, store_ams, on='门店名称', how='left')

        # 【核心修复】：强制补齐所有可能缺失的列，防止 KeyError
        all_cols_needed = ['质检总分', 'S_60s', 'S_Time', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat']
        for df in [full_advisors, full_stores]:
            for col in all_cols_needed:
                if col not in df.columns:
                    df[col] = np.nan # 补空值，避免报错

        return full_advisors, full_stores

    except Exception as e:
        st.error(f"处理逻辑报错: {str(e)}")
        return None, None

# ================= 5. 渲染 =================
if has_data:
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, PATH_S)
    
    if df_advisors is not None:
        # 侧边栏筛选
        st.sidebar.markdown("---")
        store_list = ["全部"] + sorted(df_stores['门店名称'].unique().tolist())
        selected_store = st.sidebar.selectbox("查看范围", store_list)

        if selected_store == "全部":
            current_df = df_stores.copy()
            current_df['Name'] = current_df['门店名称']
        else:
            current_df = df_advisors[df_advisors['门店名称'] == selected_store].copy()
            current_df['Name'] = current_df['邀约专员/管家']

        # 计算基础 KPI
        kpi_leads = current_df['线索量'].sum()
        kpi_visits = current_df['到店量'].sum()
        kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
        kpi_score = current_df['质检总分'].mean()

        # 显示标题
        st.title(f"📊 Audi DCC 看板 - {selected_store}")
        
        # 第一排：KPI
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("线索量", int(kpi_leads))
        k2.metric("到店量", int(kpi_visits))
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("质检均分", f"{kpi_score:.1f}")
        
        st.markdown("---")

        # 第二排：图表
        c1, c2 = st.columns(2)
        
        # 散点图：接通率 vs 60s
        # 安全计算接通率
        current_df['Connect_Rate'] = safe_div(current_df, 'conn_num', 'conn_denom')
        
        with c1:
            st.subheader("通话质量分析 (接通率 vs 60s占比)")
            if 'S_60s' in current_df.columns:
                fig1 = px.scatter(
                    current_df, x="Connect_Rate", y="S_60s", size="线索量", color="质检总分",
                    hover_name="Name", labels={"Connect_Rate": "接通率", "S_60s": "60秒占比得分"},
                    title="气泡大小=线索量，颜色=质检总分"
                )
                fig1.update_layout(xaxis_tickformat=".0%")
                st.plotly_chart(fig1, use_container_width=True)
            else:
                st.info("暂无 60秒通话 数据")

        # 散点图：明确到店 vs 转化率
        with c2:
            st.subheader("邀约能力分析 (明确时间得分 vs 到店率)")
            if 'S_Time' in current_df.columns:
                fig2 = px.scatter(
                    current_df, x="S_Time", y="线索到店率_数值", size="线索量", color="质检总分",
                    hover_name="Name", labels={"S_Time": "明确到店时间得分", "线索到店率_数值": "到店率"},
                )
                fig2.update_layout(yaxis_tickformat=".0%")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("暂无 明确到店时间 数据")

        # 第三排：诊断 (仅门店视图下显示)
        if selected_store != "全部":
            st.markdown("---")
            st.subheader("🕵️‍♀️ 顾问单人诊断")
            person = st.selectbox("选择顾问", current_df['Name'].unique())
            p_data = current_df[current_df['Name'] == person].iloc[0]
            
            d1, d2 = st.columns(2)
            with d1:
                st.write("**核心指标**")
                st.write(f"- 线索到店率: {p_data['线索到店率']}")
                st.write(f"- 质检总分: {p_data.get('质检总分', 0):.1f}")
            
            with d2:
                st.write("**AI 建议**")
                # 容错获取分数
                s_60s = p_data.get('S_60s', 0)
                s_time = p_data.get('S_Time', 0)
                
                # 简单的规则判断
                suggestions = []
                if pd.isna(s_60s) or s_60s < 60: suggestions.append("⚠️ **60秒占比低**：建议优化开场白，迅速抛出利益点。")
                if pd.isna(s_time) or s_time < 80: suggestions.append("⚠️ **明确到店弱**：建议使用二选一法锁定具体时间。")
                
                if suggestions:
                    for s in suggestions: st.markdown(s)
                else:
                    st.success("🎉 各项表现良好，继续保持！")
