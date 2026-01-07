import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os

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

# ================= 3. 侧边栏 (无邮件功能) =================
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
            with st.form("data_update_form"):
                st.markdown("##### 请上传所有 4 个文件：")
                new_f = st.file_uploader("1. 漏斗表", type=["xlsx", "csv"])
                new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"])
                new_a = st.file_uploader("3. AMS表", type=["xlsx", "csv"])
                new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"]) 
                
                if st.form_submit_button("🚀 确认并更新数据"):
                    if new_f and new_d and new_a and new_s:
                        save_uploaded_file(new_f, PATH_F)
                        save_uploaded_file(new_d, PATH_D)
                        save_uploaded_file(new_a, PATH_A)
                        save_uploaded_file(new_s, PATH_S)
                        st.success("更新成功！正在刷新...")
                        st.rerun()
                    else:
                        st.error("❌ 请传齐 4 个文件")

# ================= 4. 数据处理 (修复了读取报错) =================
def smart_read(file_path):
    """
    智能读取：
    1. 自动判断 Excel/CSV
    2. CSV 自动尝试 GBK/UTF-8 编码 (解决乱码报错)
    3. 自动寻找表头 (解决第一行是空行的问题)
    """
    try:
        # 1. 读取内容
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path, header=None)
        else:
            # 尝试不同编码，解决 'gbk codec can't decode' 错误
            try:
                df = pd.read_csv(file_path, header=None, encoding='utf-8')
            except:
                try:
                    df = pd.read_csv(file_path, header=None, encoding='gbk')
                except:
                    df = pd.read_csv(file_path, header=None, encoding='gb18030')

        # 2. 寻找真正的表头行
        # 很多文件第一行是空的或者分类标题，我们要找包含 "门店名称" 或 "顾问" 的那一行
        header_row = 0
        for i in range(min(5, len(df))): # 只找前5行
            row_values = df.iloc[i].astype(str).values
            if any("门店" in v for v in row_values) or any("顾问" in v for v in row_values):
                header_row = i
                break
        
        # 3. 重设表头
        df.columns = df.iloc[header_row]
        df = df[header_row + 1:].reset_index(drop=True)
        
        # 清理列名（去空格、去换行）
        df.columns = df.columns.astype(str).str.strip().str.replace('\n', '')
        return df

    except Exception as e:
        st.error(f"读取文件失败: {os.path.basename(file_path)} - {e}")
        return None

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
        raw_s = smart_read(path_s)
        
        if raw_f is None or raw_d is None or raw_a is None or raw_s is None: 
            return None, None

        # --- A. 漏斗表 ---
        # 模糊匹配列名
        f_cols = raw_f.columns
        col_store = next((c for c in f_cols if '门店' in c or '代理' in c), '门店名称')
        col_name = next((c for c in f_cols if '顾问' in c or '管家' in c), '邀约专员/管家')
        col_leads = next((c for c in f_cols if '有效线索' in c or '线索量' in c), '线索量')
        col_visits = next((c for c in f_cols if '到店' in c and '率' not in c), '到店量')
        
        df_f = raw_f.rename(columns={col_store: '门店名称', col_name: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'})
        
        # 拆分
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
        
        for c in ['质检总分', 'S_60s', 'S_Time']: 
            if c in df_d.columns: df_d[c] = pd.to_numeric(df_d[c], errors='coerce')
        
        # --- C. 门店排名表 (直接读取) ---
        s_map = {
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        }
        s_wechat_raw = next((c for c in raw_s.columns if '微信' in c and '添加' in c), '添加微信')
        # 确保有门店名称
        s_store_raw = next((c for c in raw_s.columns if '门店' in c), '门店名称')
        
        df_s = raw_s.rename(columns={**s_map, s_store_raw: '门店名称'})
        df_s['S_Wechat'] = df_s[s_wechat_raw] if s_wechat_raw in df_s.columns else 0
        
        for c in ['质检总分', 'S_60s', 'S_Time']:
            if c in df_s.columns: df_s[c] = pd.to_numeric(df_s[c], errors='coerce')

        # --- D. AMS表 ---
        a_map = {}
        for c in raw_a.columns:
            if '接通' in c and '线索' in c: a_map[c] = 'conn_num'
            if '外呼' in c and '线索' in c and '需' not in c: a_map[c] = 'conn_denom'
            if '管家' in c or '顾问' in c: a_map[c] = '邀约专员/管家'
        df_a = raw_a.rename(columns=a_map)
        
        for c in ['conn_num', 'conn_denom']:
            if c not in df_a.columns: df_a[c] = 0
            else: df_a[c] = pd.to_numeric(df_a[c], errors='coerce').fillna(0)

        # --- E. 合并 ---
        # 1. 顾问层
        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
        full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
        
        # 2. 门店层 (AMS聚合 + 门店排名文件)
        # AMS聚合
        if 'conn_num' in full_advisors.columns:
            ams_grp = full_advisors.groupby('门店名称')[['conn_num', 'conn_denom']].sum().reset_index()
        else:
            ams_grp = pd.DataFrame(columns=['门店名称', 'conn_num', 'conn_denom'])

        full_stores = pd.merge(df_store_data, df_s, on='门店名称', how='left')
        full_stores = pd.merge(full_stores, ams_grp, on='门店名称', how='left')
        
        # 补全
        for df in [full_advisors, full_stores]:
            for col in ['质检总分', 'S_60s', 'S_Time']:
                if col not in df.columns: df[col] = np.nan

        return full_advisors, full_stores

    except Exception as e:
        st.error(f"处理错误: {e}")
        return None, None

# ================= 5. 界面渲染 =================
if has_data:
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, PATH_S)
    
    if df_advisors is not None:
        
        # 侧边栏选择
        st.sidebar.markdown("---")
        store_options = ["全部"] + sorted(list(df_stores['门店名称'].unique()))
        selected_store = st.sidebar.selectbox("🏭 切换门店视图", store_options)

        if selected_store == "全部":
            current_df = df_stores.copy()
            current_df['Name'] = current_df['门店名称']
            rank_title = "🏆 全区门店排名"
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df['质检总分'].mean() 
        else:
            current_df = df_advisors[df_advisors['门店名称'] == selected_store].copy()
            current_df['Name'] = current_df['邀约专员/管家']
            rank_title = f"👤 {selected_store} - 顾问排名"
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df['质检总分'].mean()

        # 1. 顶部KPI
        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")
        
        st.markdown("---")

        # 2. 图表区
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通话质量分析")
            if 'S_60s' in current_df.columns and 'conn_num' in current_df.columns:
                current_df['接通率'] = safe_div(current_df, 'conn_num', 'conn_denom')
                # 填充0以显示
                plot_df = current_df.fillna(0)
                fig = px.scatter(plot_df, x="接通率", y="S_60s", size="线索量", color="质检总分", hover_name="Name")
                fig.update_layout(xaxis_tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("数据不足，无法显示散点图")

        with c2:
            st.subheader(rank_title)
            # 准备排行数据
            show_cols = ['Name', '线索到店率', '质检总分']
            # 动态添加列
            if 'S_60s' in current_df.columns: show_cols.append('S_60s')
            
            show_cols = [c for c in show_cols if c in current_df.columns]
            
            st.dataframe(
                current_df[show_cols].sort_values('质检总分', ascending=False),
                use_container_width=True,
                height=400
            )
else:
    st.info("👋 欢迎使用！请在左侧上传数据。")
