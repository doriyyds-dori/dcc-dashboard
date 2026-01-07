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
    div[data-testid="stFormSubmitButton"] button:hover {
        background-color: #990000;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# ================= 2. 基础配置 =================
ADMIN_PASSWORD = "AudiSARR3" 
DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# 内部文件代号映射 (不需要用户关心文件名，代码自动处理后缀)
FILE_KEYS = {
    "funnel": "1. 漏斗表 (包含: 线索量/到店量)",
    "dcc": "2. 顾问质检表 (包含: 顾问得分/管家排名)",
    "ams": "3. AMS表 (包含: 接通率/跟进数据)",
    "store_rank": "4. 门店排名表 (包含: 门店得分/排名)" 
}

def get_existing_file_path(base_name):
    """根据基础名查找实际存在的文件路径 (自动判断是csv还是xlsx)"""
    for ext in ['.xlsx', '.csv']:
        path = os.path.join(DATA_DIR, f"{base_name}{ext}")
        if os.path.exists(path):
            return path
    return None

def save_uploaded_file(uploaded_file, base_name):
    """保存文件，自动保留原始后缀，并删除旧的同名不同后缀文件"""
    try:
        # 获取用户上传文件的后缀 (.csv 或 .xlsx)
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        if file_ext not in ['.csv', '.xlsx']:
            file_ext = '.csv' # 默认回退
            
        save_path = os.path.join(DATA_DIR, f"{base_name}{file_ext}")
        
        # 为了防止混淆，先删除该基础名下的所有旧文件
        for ext in ['.xlsx', '.csv']:
            old_path = os.path.join(DATA_DIR, f"{base_name}{ext}")
            if os.path.exists(old_path):
                os.remove(old_path)
                
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return True
    except Exception as e:
        st.error(f"文件保存失败: {e}")
        return False

# ================= 3. 侧边栏 =================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/9/92/Audi-Logo_2016.svg/1200px-Audi-Logo_2016.svg.png", width=150)
    st.header("⚙️ 管理面板")
    
    # 检查文件是否齐全
    missing_files = []
    for key in FILE_KEYS.keys():
        if not get_existing_file_path(key):
            missing_files.append(key)
    
    has_data = len(missing_files) == 0
    
    if has_data:
        st.success("✅ 数据状态：已就绪")
    else:
        st.warning(f"⚠️ 缺数据，请上传")
    st.markdown("---")
    
    with st.expander("🔐 更新数据 (仅限管理员)", expanded=True):
        pwd = st.text_input("输入管理员密码", type="password")
        
        if pwd == ADMIN_PASSWORD:
            st.info("🔓 身份验证通过")
            with st.form("data_update_form", clear_on_submit=False):
                st.markdown("##### 请对应上传 4 个文件：")
                
                # 动态生成上传组件
                up_f = st.file_uploader(FILE_KEYS['funnel'], type=["xlsx", "csv"])
                up_d = st.file_uploader(FILE_KEYS['dcc'], type=["xlsx", "csv"])
                up_a = st.file_uploader(FILE_KEYS['ams'], type=["xlsx", "csv"])
                up_s = st.file_uploader(FILE_KEYS['store_rank'], type=["xlsx", "csv"])
                
                if st.form_submit_button("🚀 确认并更新数据"):
                    if up_f and up_d and up_a and up_s:
                        with st.spinner("正在保存并处理..."):
                            # 使用内部代号保存，自动识别后缀
                            s1 = save_uploaded_file(up_f, "funnel")
                            s2 = save_uploaded_file(up_d, "dcc")
                            s3 = save_uploaded_file(up_a, "ams")
                            s4 = save_uploaded_file(up_s, "store_rank")
                            
                            if s1 and s2 and s3 and s4:
                                st.success("✅ 更新成功！正在刷新页面...")
                                st.rerun()
                    else:
                        st.error("❌ 请一次性上传所有 4 个文件，以确保数据一致性。")
        elif pwd:
            st.error("密码错误")

# ================= 4. 数据处理 =================
def smart_read(file_path):
    """
    增强版文件读取：支持 xlsx 和 csv (utf-8/gbk)
    """
    try:
        if not file_path or not os.path.exists(file_path):
            return None
            
        df = None
        # 1. Excel 处理
        if file_path.endswith('.xlsx'):
            try:
                df = pd.read_excel(file_path, header=None)
            except Exception as e:
                st.error(f"Excel读取错误 {os.path.basename(file_path)}: {e}")
                return None
        else:
            # 2. CSV 多编码尝试
            encodings = ['utf-8-sig', 'gb18030', 'utf-16']
            for enc in encodings:
                try:
                    df = pd.read_csv(file_path, header=None, encoding=enc, engine='python', on_bad_lines='skip')
                    break
                except: continue
            
            if df is None:
                st.error(f"❌ 无法识别文件编码: {os.path.basename(file_path)}")
                return None

        # 3. 智能寻找表头
        header_row = 0
        keywords = ['门店', '顾问', '管家', '排名', '代理商', '序号', '线索']
        
        if len(df) > 0:
            for i in range(min(10, len(df))):
                row_values = df.iloc[i].astype(str).str.cat(sep=',')
                if any(k in row_values for k in keywords):
                    header_row = i
                    break
        
        df.columns = df.iloc[header_row]
        df = df[header_row + 1:].reset_index(drop=True)
        
        # 清理列名
        df.columns = df.columns.astype(str).str.strip().str.replace('\n', '').str.replace('\r', '')
        # 删除无名列
        df = df.loc[:, df.columns.notna()]
        
        return df

    except Exception as e:
        st.error(f"读取失败: {os.path.basename(file_path)} - {e}")
        return None

def safe_div(df, num_col, denom_col):
    if num_col not in df.columns or denom_col not in df.columns: return 0
    num = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
    denom = pd.to_numeric(df[denom_col], errors='coerce').fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)

@st.cache_data(ttl=300)
def process_data():
    # 动态获取文件路径
    path_f = get_existing_file_path("funnel")
    path_d = get_existing_file_path("dcc")
    path_a = get_existing_file_path("ams")
    path_s = get_existing_file_path("store_rank")
    
    try:
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        raw_s = smart_read(path_s)
        
        if raw_f is None or raw_d is None or raw_a is None or raw_s is None: 
            return None, None

        # --- A. 漏斗表处理 ---
        f_cols = raw_f.columns
        col_store = next((c for c in f_cols if '门店' in c or '代理' in c), '门店名称')
        col_name = next((c for c in f_cols if '顾问' in c or '管家' in c), '邀约专员/管家')
        col_leads = next((c for c in f_cols if '有效线索' in c or '线索量' in c), '线索量')
        col_visits = next((c for c in f_cols if '到店' in c and '率' not in c), '到店量')
        
        df_f = raw_f.rename(columns={col_store: '门店名称', col_name: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'})
        
        mask_sub = df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)
        df_store_data = df_f[mask_sub].copy()
        df_advisor_data = df_f[~mask_sub].copy()

        for df in [df_store_data, df_advisor_data]:
            df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
            df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
            df['线索到店率_数值'] = safe_div(df, '到店量', '线索量')
            df['线索到店率'] = (df['线索到店率_数值'] * 100).map('{:.1f}%'.format)

        # --- B. 顾问质检表 ---
        d_map = {
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        }
        wechat_raw = next((c for c in raw_d.columns if '微信' in c and '添加' in c), '添加微信')
        df_d = raw_d.rename(columns=d_map)
        df_d['S_Wechat'] = df_d[wechat_raw] if wechat_raw in df_d.columns else 0
        
        num_cols = ['质检总分', 'S_60s', 'S_Time', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat']
        for c in num_cols: 
            if c in df_d.columns: df_d[c] = pd.to_numeric(df_d[c], errors='coerce')
        
        if '邀约专员/管家' not in df_d.columns and '管家' in raw_d.columns:
            df_d.rename(columns={'管家': '邀约专员/管家'}, inplace=True)

        # --- C. 门店排名表 ---
        s_map = {
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        }
        s_wechat_raw = next((c for c in raw_s.columns if '微信' in c and '添加' in c), '添加微信')
        s_store_raw = next((c for c in raw_s.columns if '门店' in c and 'ID' not in c), '门店名称')
        
        df_s = raw_s.rename(columns={**s_map, s_store_raw: '门店名称'})
        df_s['S_Wechat'] = df_s[s_wechat_raw] if s_wechat_raw in df_s.columns else 0
        
        for c in ['质检总分', 'S_60s', 'S_Time']:
            if c in df_s.columns: df_s[c] = pd.to_numeric(df_s[c], errors='coerce')

        # --- D. AMS表 ---
        a_map = {}
        for c in raw_a.columns:
            if '接通' in c and '线索' in c and '率' not in c: a_map[c] = 'conn_num'
            if '外呼' in c and '线索' in c and '需' not in c and '率' not in c: a_map[c] = 'conn_denom'
            if '管家' in c or '顾问' in c: a_map[c] = '邀约专员/管家'
            if '平均通话时长' in c: a_map[c] = '通话时长'
            
        df_a = raw_a.rename(columns=a_map)
        
        for c in ['conn_num', 'conn_denom', '通话时长']:
            if c not in df_a.columns: df_a[c] = 0
            else: df_a[c] = pd.to_numeric(df_a[c], errors='coerce').fillna(0)

        # --- E. 合并 ---
        for df in [df_advisor_data, df_d, df_a, df_store_data, df_s]:
            if '邀约专员/管家' in df.columns:
                df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
            if '门店名称' in df.columns:
                df['门店名称'] = df['门店名称'].astype(str).str.strip()

        # 1. 顾问层合并
        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
        if '邀约专员/管家' in df_a.columns:
            df_a_unique = df_a.groupby('邀约专员/管家').first().reset_index()
            full_advisors = pd.merge(full_advisors, df_a_unique, on='邀约专员/管家', how='left')
        
        # 2. 门店层合并
        if 'conn_num' in full_advisors.columns and '门店名称' in full_advisors.columns:
            ams_grp = full_advisors.groupby('门店名称')[['conn_num', 'conn_denom']].sum().reset_index()
        else:
            ams_grp = pd.DataFrame(columns=['门店名称', 'conn_num', 'conn_denom'])

        full_stores = pd.merge(df_store_data, df_s, on='门店名称', how='left')
        full_stores = pd.merge(full_stores, ams_grp, on='门店名称', how='left')
        
        return full_advisors, full_stores

    except Exception as e:
        import traceback
        st.error(f"数据处理逻辑错误: {e}")
        st.text(traceback.format_exc())
        return None, None

# ================= 5. 界面渲染 =================
if has_data:
    df_advisors, df_stores = process_data()
    
    if df_advisors is not None:
        
        st.sidebar.markdown("---")
        if not df_stores.empty:
            store_options = ["全部"] + sorted(list(df_stores['门店名称'].unique()))
        else:
            store_options = ["全部"]
            
        selected_store = st.sidebar.selectbox("🏭 切换门店视图", store_options)

        if selected_store == "全部":
            current_df = df_stores.copy()
            current_df['Name'] = current_df['门店名称']
            rank_title = "🏆 全区门店排名"
        else:
            current_df = df_advisors[df_advisors['门店名称'] == selected_store].copy()
            current_df['Name'] = current_df['邀约专员/管家']
            rank_title = f"👤 {selected_store} - 顾问排名"

        # KPI
        kpi_leads = current_df['线索量'].sum()
        kpi_visits = current_df['到店量'].sum()
        kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
        kpi_score = current_df['质检总分'].mean() if '质检总分' in current_df.columns else 0

        # 1. 概览
        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")
        
        st.markdown("---")

        # 2. 图表
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通话质量分析")
            if 'S_60s' in current_df.columns and 'conn_num' in current_df.columns:
                current_df['接通率'] = safe_div(current_df, 'conn_num', 'conn_denom')
                plot_df = current_df.fillna(0)
                fig = px.scatter(
                    plot_df, x="接通率", y="S_60s", size="线索量", 
                    color="质检总分" if '质检总分' in plot_df.columns else None,
                    hover_name="Name",
                    labels={'S_60s': '60秒通话占比', '接通率': '外呼接通率'}
                )
                fig.update_layout(xaxis_tickformat=".0%", height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("ℹ️ 数据不足，无法显示通话质量散点图 (需 AMS 和 质检数据)")

        with c2:
            st.subheader(rank_title)
            show_cols = ['Name', '线索到店率', '质检总分', '线索量', '到店量']
            if 'S_60s' in current_df.columns: show_cols.append('S_60s')
            show_cols = [c for c in show_cols if c in current_df.columns]
            
            if not current_df.empty:
                st.dataframe(
                    current_df[show_cols].sort_values('线索量', ascending=False),
                    use_container_width=True, height=400, hide_index=True
                )
            else:
                st.warning("暂无数据")
else:
    st.info("👋 欢迎使用！请在左侧点击“更新数据”并上传文件。")
