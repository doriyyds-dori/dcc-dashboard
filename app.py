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
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    .big-font {font-size: 18px !important; font-weight: bold;}
    /* 优化提交按钮样式 */
    div[data-testid="stFormSubmitButton"] button {
        width: 100%;
        background-color: #bb0a30;
        color: white;
        border: none;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ================= 2. 安全锁与文件存储 =================
ADMIN_PASSWORD = "AudiSARR3" 

DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")      # 1. 漏斗
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")         # 2. 顾问质检
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")         # 3. AMS
PATH_S = os.path.join(DATA_DIR, "store_rank.csv")   # 4. 门店排名

def save_uploaded_file(uploaded_file, save_path):
    # 强制覆盖保存
    with open(save_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return True

# ================= 3. 侧边栏逻辑 (使用 Form 解决点击无反应问题) =================
with st.sidebar:
    st.header("⚙️ 管理面板")
    has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and os.path.exists(PATH_S)
    
    if has_data: st.success("✅ 数据状态：已就绪")
    else: st.warning("⚠️ 暂无数据")
    st.markdown("---")
    
    with st.expander("🔐 更新数据 (仅限管理员)", expanded=True):
        pwd = st.text_input("输入管理员密码", type="password")
        
        if pwd == ADMIN_PASSWORD:
            st.info("🔓 身份验证通过，请上传数据：")
            
            # --- 使用 st.form 确保提交稳定 ---
            with st.form("data_update_form", clear_on_submit=False):
                st.markdown("##### 必须上传所有 4 个文件：")
                new_f = st.file_uploader("1. 漏斗指标表", type=["xlsx", "csv"])
                new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"])
                new_a = st.file_uploader("3. AMS跟进表", type=["xlsx", "csv"])
                new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"]) 
                
                # 提交按钮
                submitted = st.form_submit_button("🚀 确认并更新数据")
                
                if submitted:
                    if new_f and new_d and new_a and new_s:
                        with st.spinner("正在保存文件并处理..."):
                            save_uploaded_file(new_f, PATH_F)
                            save_uploaded_file(new_d, PATH_D)
                            save_uploaded_file(new_a, PATH_A)
                            save_uploaded_file(new_s, PATH_S)
                        
                        st.success("✅ 数据更新成功！页面即将刷新...")
                        st.rerun()
                    else:
                        st.error("❌ 更新失败：请确保 4 个文件全部都已上传。")
        elif pwd:
            st.error("密码错误")

# ================= 4. 数据处理逻辑 (增强容错) =================
def smart_read(file_path, is_rank_file=False):
    """智能读取，支持csv/xlsx，针对排名表支持跳过首行"""
    try:
        if isinstance(file_path, str):
            is_csv = file_path.endswith('.csv') or file_path.endswith('.txt')
        else:
            is_csv = file_path.name.endswith('.csv') or file_path.name.endswith('.txt')
            
        if is_csv:
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
            
        # 针对门店排名表的特殊处理 (检测是否包含 metadata 头)
        if is_rank_file:
            # 定义我们在找的关键列
            target_cols = ['门店名称', '质检总分', '排名']
            # 如果第一行表头里没找到这些列，尝试读第二行作为表头
            if not any(col in df.columns for col in target_cols):
                if is_csv: df = pd.read_csv(file_path, header=1)
                else: df = pd.read_excel(file_path, header=1)
        return df
    except Exception as e:
        print(f"读取文件失败: {file_path}, 错误: {e}")
        return None

def clean_percent_col(df, col_name):
    if col_name not in df.columns: return
    series = df[col_name].astype(str).str.strip().str.replace('%', '', regex=False)
    numeric_series = pd.to_numeric(series, errors='coerce').fillna(0)
    if numeric_series.max() > 1.0:
        df[col_name] = numeric_series / 100
    else:
        df[col_name] = numeric_series

def safe_div(df, num_col, denom_col):
    num = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
    denom = pd.to_numeric(df[denom_col], errors='coerce').fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)

def process_data(path_f, path_d, path_a, path_s):
    try:
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        raw_s = smart_read(path_s, is_rank_file=True)
        
        # 只要有一个文件没读出来，就返回 None
        if raw_f is None or raw_d is None or raw_a is None or raw_s is None: 
            return None, None

        # ================= A. Funnel (漏斗) =================
        # 模糊匹配列名，增加鲁棒性
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), raw_f.columns[0])
        name_col = next((c for c in raw_f.columns if '管家' in str(c) or '顾问' in str(c)), raw_f.columns[1])
        col_leads = '线上_有效线索数' if '线上_有效线索数' in raw_f.columns else '线索量'
        col_visits = '线上_到店数' if '线上_到店数' in raw_f.columns else '到店量'
        col_excel_rate = next((c for c in raw_f.columns if '率' in str(c) and ('到店' in str(c) or '有效' in str(c))), None)

        rename_dict = {store_col: '门店名称', name_col: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'}
        if col_excel_rate: rename_dict[col_excel_rate] = 'Excel_Rate'
        
        df_f = raw_f.rename(columns=rename_dict)
        # 区分门店行和顾问行
        df_store_data = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
        df_advisor_data = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()

        for df in [df_store_data, df_advisor_data]:
            df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
            df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
            if 'Excel_Rate' in df.columns:
                clean_percent_col(df, 'Excel_Rate')
                df['线索到店率_数值'] = df['Excel_Rate']
            else:
                df['线索到店率_数值'] = safe_div(df, '到店量', '线索量')
            df['线索到店率'] = (df['线索到店率_数值'] * 100).map('{:.1f}%'.format)

        # ================= B. DCC (顾问质检) =================
        wechat_col = '添加微信.1' if '添加微信.1' in raw_d.columns else '添加微信'
        df_d = raw_d.rename(columns={
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        })
        # 兼容处理
        if wechat_col in raw_d.columns:
            df_d['S_Wechat'] = raw_d[wechat_col]
        else:
            df_d['S_Wechat'] = 0
        
        score_cols = ['质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']
        for c in score_cols:
            if c in df_d.columns:
                df_d[c] = pd.to_numeric(df_d[c], errors='coerce') 
        
        # 只取存在的列
        existing_cols = [c for c in (['邀约专员/管家'] + score_cols) if c in df_d.columns]
        df_d = df_d[existing_cols]

        # ================= C. Store Scores (门店质检 - 直接读取文件4) =================
        df_s = raw_s.rename(columns={
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        })
        s_wechat_col = '添加微信.1' if '添加微信.1' in raw_s.columns else '添加微信'
        if s_wechat_col in raw_s.columns:
            df_s['S_Wechat'] = raw_s[s_wechat_col]
        else:
            df_s['S_Wechat'] = 0
        
        store_score_cols = ['门店名称', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']
        available_store_cols = [c for c in store_score_cols if c in df_s.columns]
        df_s = df_s[available_store_cols]
        for c in available_store_cols:
            if c != '门店名称':
                df_s[c] = pd.to_numeric(df_s[c], errors='coerce')

        # ================= D. AMS (跟进数据) =================
        # 模糊匹配 AMS 列名
        cols_config = [
            ({'管家姓名'}, '邀约专员/管家'),
            ({'DCC平均通话时长'}, '通话时长'),
            ({'DCC接通线索数'}, 'conn_num'), ({'DCC外呼线索数'}, 'conn_denom'),
            ({'DCC及时处理线索'}, 'timely_num'), ({'需外呼线索数'}, 'timely_denom'),
            ({'二次外呼线索数'}, 'call2_num'), ({'需再呼线索数'}, 'call2_denom'),
            ({'DCC三次外呼的线索数', '三次外呼线索数'}, 'call3_num'), 
            ({'DCC二呼状态为需再呼的线索数', '二呼状态为需再呼'}, 'call3_denom')
        ]
        found_rename_map = {}
        for keywords, target_name in cols_config:
            found_col = None
            for col in raw_a.columns:
                for k in keywords:
                    if k in str(col).strip(): found_col = col; break
                if found_col: break
            if found_col: found_rename_map[found_col] = target_name
        
        df_a = raw_a.rename(columns=found_rename_map)
        
        all_ams_calc_cols = ['conn_num', 'conn_denom', 'timely_num', 'timely_denom', 
                             'call2_num', 'call2_denom', 'call3_num', 'call3_denom']
        for c in all_ams_calc_cols:
            if c not in df_a.columns: df_a[c] = 0
            else: df_a[c] = pd.to_numeric(df_a[c], errors='coerce').fillna(0)

        df_a['外呼接通率'] = safe_div(df_a, 'conn_num', 'conn_denom')
        df_a['DCC及时处理率'] = safe_div(df_a, 'timely_num', 'timely_denom')
        df_a['DCC二次外呼率'] = safe_div(df_a, 'call2_num', 'call2_denom')
        df_a['DCC三次外呼率'] = safe_div(df_a, 'call3_num', 'call3_denom')

        final_ams_cols = ['邀约专员/管家', '通话时长', '外呼接通率', 'DCC及时处理率', 'DCC二次外呼率', 'DCC三次外呼率'] + all_ams_calc_cols
        # 仅保留存在的列
        final_ams_cols = [c for c in final_ams_cols if c in df_a.columns]
        df_a = df_a[final_ams_cols]

        # ================= E. Merge =================
        # 清理空格
        for df in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
            if '邀约专员/管家' in df.columns: df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
            if '门店名称' in df.columns: df['门店名称'] = df['门店名称'].astype(str).str.strip()

        # 1. 顾问全量表
        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
        full_advisors = pd.merge(full_
