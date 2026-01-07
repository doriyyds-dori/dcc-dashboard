import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
import traceback

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
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
    
    if has_data: st.success("✅ 数据已就绪")
    else: st.warning("⚠️ 缺文件")
    
    st.markdown("---")
    with st.expander("🔐 更新数据", expanded=not has_data):
        pwd = st.text_input("管理员密码", type="password")
        if pwd == ADMIN_PASSWORD:
            with st.form("update_form"):
                st.write("请上传文件：")
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
                        st.success("上传成功！正在刷新...")
                        st.rerun()
                    else:
                        st.error("❌ 必须传齐 4 个文件")

# ================= 4. 核心逻辑：万能读取函数 =================
def robust_read_csv(file_path, skip_rows=0):
    """尝试多种编码读取CSV"""
    encodings = ['utf-8-sig', 'gb18030', 'gbk', 'utf-8'] # 优先 utf-8-sig (解决Excel导出问题)
    
    for enc in encodings:
        try:
            return pd.read_csv(file_path, encoding=enc, header=skip_rows)
        except:
            continue
    return None

def smart_read_final(file_path, desc):
    try:
        # 1. 扩展名判断
        if isinstance(file_path, str): is_csv = file_path.lower().endswith('.csv')
        else: is_csv = file_path.name.lower().endswith('.csv')

        df = None
        
        # 2. 针对“门店排名表”的特殊处理：您的文件第一行是无关内容，必须跳过
        skip = 0
        if "排名表" in desc:
            skip = 1 # 强制跳过第一行

        # 3. 读取逻辑
        if is_csv:
            df = robust_read_csv(file_path, skip_rows=skip)
            # 如果跳过一行没读到，尝试不跳过
            if df is None and skip == 1:
                df = robust_read_csv(file_path, skip_rows=0)
        else:
            df = pd.read_excel(file_path, header=skip)

        if df is None:
            st.error(f"❌ 无法读取【{desc}】。请确保文件是标准的 Excel 或 CSV 格式。")
            return None

        # 4. 列名清洗 (去除空格、换行)
        df.columns = df.columns.astype(str).str.strip().str.replace('\n', '')
        
        # 5. 排名表二次检查：如果没有找到“门店名称”，可能是因为 skip=1 没生效或生效错了
        if "排名表" in desc and "门店名称" not in df.columns:
            # 最后的尝试：在所有列名里找
            found = False
            for c in df.columns:
                if "门店名称" in str(c):
                    df.rename(columns={c: "门店名称"}, inplace=True)
                    found = True
                    break
            if not found:
                st.warning(f"⚠️ {desc} 读取存疑，未找到【门店名称】列。识别到的列名：{list(df.columns)}")

        return df

    except Exception as e:
        st.error(f"❌ 读取 {desc} 发生系统错误: {e}")
        return None

def safe_div(df, num_col, denom_col):
    if num_col not in df.columns or denom_col not in df.columns: return 0
    num = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
    denom = pd.to_numeric(df[denom_col], errors='coerce').fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)

def process_data(path_f, path_d, path_a, path_s):
    # 读取
    raw_f = smart_read_final(path_f, "漏斗表")
    raw_d = smart_read_final(path_d, "顾问质检表")
    raw_a = smart_read_final(path_a, "AMS表")
    raw_s = smart_read_final(path_s, "门店排名表")

    if raw_f is None or raw_d is None or raw_a is None or raw_s is None:
        return None, None

    try:
        # --- A. 漏斗表 ---
        col_map_f = {}
        for c in raw_f.columns:
            if '门店' in c or '代理' in c: col_map_f[c] = '门店名称'
            elif '顾问' in c or '管家' in c: col_map_f[c] = '邀约专员/管家'
            elif '有效线索' in c or '线索量' in c: col_map_f[c] = '线索量'
            elif '到店' in c and '率' not in c: col_map_f[c] = '到店量'
        
        df_f = raw_f.rename(columns=col_map_f)
        
        # 拆分数据
        if '邀约专员/管家' in df_f.columns:
            df_store_data = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
            df_advisor_data = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()
        else:
            # 容错：如果找不到顾问列，假设全是门店数据
            df_store_data = df_f.copy()
            df_advisor_data = pd.DataFrame()

        for df in [df_store_data, df_advisor_data]:
            if df.empty: continue
            df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
            df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
            df['线索到店率_数值'] = safe_div(df, '到店量', '线索量')
            df['线索到店率'] = (df['线索到店率_数值']*100).map('{:.1f}%'.format)

        # --- B. 顾问质检表 ---
        d_map = {
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car',
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        }
        # 查找微信列
        wechat_c = next((c for c in raw_d.columns if '微信' in c and '添加' in c), '添加微信')
        df_d = raw_d.rename(columns=d_map)
        df_d['S_Wechat'] = raw_d[wechat_c] if wechat_c in raw_d.columns else 0
        
        # 补全列
        for c in ['质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat']:
            if c not in df_d.columns: df_d[c] = 0
            else: df_d[c] = pd.to_numeric(df_d[c], errors='coerce')
        
        cols_d = ['邀约专员/管家', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat']
        cols_d = [c for c in cols_d if c in df_d.columns]
        df_d = df_d[cols_d]

        # --- C. 门店排名表 ---
        s_map = {
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car',
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        }
        df_s = raw_s.rename(columns=s_map)
        s_wechat_c = next((c for c in raw_s.columns if '微信' in c and '添加' in c), '添加微信')
        df_s['S_Wechat'] = raw_s[s_wechat_c] if s_wechat_c in raw_s.columns else 0

        # 补全
        for c in ['质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat']:
            if c not in df_s.columns: df_s[c] = 0
            else: df_s[c] = pd.to_numeric(df_s[c], errors='coerce')

        target_s = ['门店名称', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat']
        target_s = [c for c in target_s if c in df_s.columns]
        df_s = df_s[target_s]

        # --- D. AMS 表 ---
        a_map = {}
        for c in raw_a.columns:
            if '接通' in c and '线索' in c: a_map[c] = 'conn_num'
            if '外呼' in c and '线索' in c and '需' not in c: a_map[c] = 'conn_denom'
            if '及时' in c: a_map[c] = 'timely_num'
            if '需外呼' in c: a_map[c] = 'timely_denom'
            if '管家' in c or '顾问' in c: a_map[c] = '邀约专员/管家'
        
        df_a = raw_a.rename(columns=a_map)
        ams_cols = ['conn_num', 'conn_denom', 'timely_num', 'timely_denom']
        for c in ams_cols:
            if c not in df_a.columns: df_a[c] = 0
            else: df_a[c] = pd.to_numeric(df_a[c], errors='coerce').fillna(0)
        
        # --- E. 合并 ---
        # 统一去空格
        for df in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
            if '门店名称' in df.columns: df['门店名称'] = df['门店名称'].astype(str).str.strip()
            if '邀约专员/管家' in df.columns: df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()

        # 顾问层级合并
        full_advisors = pd.DataFrame()
        if not df_advisor_data.empty:
            full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
            full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')

        # 门店层级合并 (AMS聚合 + 门店排名文件)
        full_stores = df_store_data.copy()
        
        # 1. 拼入门店排名得分 (Inner join 或 Left join)
        if not df_s.empty and '门店名称' in df_s.columns:
            full_stores = pd.merge(full_stores, df_s, on='门店名称', how='left')
        
        # 2. 拼入AMS聚合数据
        if not full_advisors.empty and 'conn_num' in full_advisors.columns:
            ams_grp = full_advisors.groupby('门店名称')[ams_cols].sum().reset_index()
            full_stores = pd.merge(full_stores, ams_grp, on='门店名称', how='left')

        # 补全缺失值 (防止绘图报错)
        for df in [full_advisors, full_stores]:
            for col in ['质检总分', 'S_60s', 'S_Time']:
                if col not in df.columns: df[col] = np.nan

        return full_advisors, full_stores

    except Exception as e:
        st.error(f"处理数据逻辑报错: {e}")
        st.write(traceback.format_exc())
        return None, None

# ================= 5. 渲染看板 =================
if has_data:
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, PATH_S)

    if df_advisors is not None:
        st.sidebar.markdown("---")
        # 门店列表
        if not df_stores.empty and '门店名称' in df_stores.columns:
            stores = ["全部"] + sorted(df_stores['门店名称'].unique().tolist())
        else:
            stores = ["全部"]
        
        selected_store = st.sidebar.selectbox("查看范围", stores)

        # 数据切片
        if selected_store == "全部":
            curr = df_stores.copy()
            curr['Name'] = curr['门店名称']
        else:
            curr = df_advisors[df_advisors['门店名称'] == selected_store].copy()
            curr['Name'] = curr['邀约专员/管家']

        # KPI 计算
        leads = curr['线索量'].sum() if '线索量' in curr else 0
        visits = curr['到店量'].sum() if '到店量' in curr else 0
        rate = visits / leads if leads > 0 else 0
        score = curr['质检总分'].mean() if '质检总分' in curr else 0

        # --- 页面显示 ---
        st.title(f"📊 Audi DCC 效能看板 - {selected_store}")
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("线索量", int(leads))
        k2.metric("到店量", int(visits))
        k3.metric("线索到店率", f"{rate:.1%}")
        k4.metric("质检均分", f"{score:.1f}")
        
        st.markdown("---")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通话质量")
            if 'S_60s' in curr.columns and 'conn_num' in curr.columns:
                curr['接通率'] = safe_div(curr, 'conn_num', 'conn_denom')
                # 填充0值防止图表空
                plot_data = curr.fillna(0)
                fig = px.scatter(plot_data, x="接通率", y="S_60s", size="线索量", color="质检总分", hover_name="Name")
                fig.update_layout(xaxis_tickformat=".0%")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("数据不足，无法绘制气泡图 (缺 60秒通话 或 AMS数据)")

        with c2:
            st.subheader("排行榜")
            if not curr.empty and '线索到店率' in curr.columns:
                show_cols = ['Name', '线索到店率', '质检总分']
                show_cols = [c for c in show_cols if c in curr.columns]
                st.dataframe(curr[show_cols].sort_values('质检总分', ascending=False), use_container_width=True)
