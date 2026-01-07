import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
import traceback # 用于显示详细错误

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板(诊断版)", layout="wide", page_icon="🔧")

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
    st.header("🔧 诊断模式")
    has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and os.path.exists(PATH_S)
    
    if has_data: 
        st.success("✅ 4个文件都在")
        st.info("如果右侧空白，说明文件内容读取失败，请看右侧报错。")
    else: 
        st.warning("⚠️ 文件缺失")
    
    st.markdown("---")
    with st.expander("重传文件"):
        pwd = st.text_input("管理员密码", type="password")
        if pwd == ADMIN_PASSWORD:
            with st.form("update_form"):
                st.write("请重新上传所有文件：")
                new_f = st.file_uploader("1. 漏斗表", type=["xlsx", "csv"])
                new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"])
                new_a = st.file_uploader("3. AMS表", type=["xlsx", "csv"])
                new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"])
                if st.form_submit_button("确认更新"):
                    if new_f and new_d and new_a and new_s:
                        save_uploaded_file(new_f, PATH_F)
                        save_uploaded_file(new_d, PATH_D)
                        save_uploaded_file(new_a, PATH_A)
                        save_uploaded_file(new_s, PATH_S)
                        st.success("上传成功！")
                        st.rerun()

# ================= 4. 数据处理 (显式报错版) =================
def smart_read(file_path, file_desc):
    """读取文件并打印列名，方便调试"""
    try:
        if isinstance(file_path, str): is_csv = file_path.endswith('.csv')
        else: is_csv = file_path.name.endswith('.csv')
        
        if is_csv: df = pd.read_csv(file_path)
        else: df = pd.read_excel(file_path)
        
        # 门店排名表特殊逻辑：如果没找到“门店名称”，尝试跳过一行读取
        if '门店' in file_desc and '门店名称' not in df.columns:
            st.warning(f"⚠️ {file_desc}：首行未找到【门店名称】，尝试读取第2行作为表头...")
            if is_csv: df = pd.read_csv(file_path, header=1)
            else: df = pd.read_excel(file_path, header=1)

        # 打印读取到的列名（调试用）
        # st.write(f"📄 **{file_desc}** 列名: {list(df.columns)}")
        return df
    except Exception as e:
        st.error(f"❌ 读取 {file_desc} 失败！错误信息：{e}")
        return None

def safe_div(df, num_col, denom_col):
    if num_col not in df.columns or denom_col not in df.columns: return 0
    num = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
    denom = pd.to_numeric(df[denom_col], errors='coerce').fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)

def process_data_debug(path_f, path_d, path_a, path_s):
    # 这里去掉了 try...except，让错误直接爆出来
    raw_f = smart_read(path_f, "漏斗表")
    raw_d = smart_read(path_d, "顾问质检表")
    raw_a = smart_read(path_a, "AMS表")
    raw_s = smart_read(path_s, "门店排名表")
    
    if raw_f is None or raw_d is None or raw_a is None or raw_s is None:
        st.error("⛔ 因文件读取失败，中止处理。")
        return None, None

    # --- A. 漏斗处理 ---
    # 模糊匹配
    col_store = next((c for c in raw_f.columns if '门店' in str(c) or '代理' in str(c)), None)
    col_name = next((c for c in raw_f.columns if '顾问' in str(c) or '管家' in str(c)), None)
    
    if not col_store or not col_name:
        st.error(f"❌ 漏斗表列名识别失败！\n当前列名：{list(raw_f.columns)}")
        return None, None

    col_leads = next((c for c in raw_f.columns if '有效线索' in str(c) or '线索量' in str(c)), '线索量')
    col_visits = next((c for c in raw_f.columns if '到店' in str(c) and '率' not in str(c)), '到店量')
    
    df_f = raw_f.rename(columns={col_store: '门店名称', col_name: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'})
    
    df_store_data = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
    df_advisor_data = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()
    
    for df in [df_store_data, df_advisor_data]:
        df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
        df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
        df['线索到店率_数值'] = safe_div(df, '到店量', '线索量')
        df['线索到店率'] = (df['线索到店率_数值']*100).map('{:.1f}%'.format)

    # --- B. 顾问质检 ---
    # 强制重命名，如果找不到列，就报错提示
    d_map = {
        '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
        '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car',
        '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
    }
    # 检查原始列名是否包含这些
    # 这里做一个简单的映射，防止列名不完全匹配
    df_d = raw_d.copy()
    
    # 尝试找到微信列
    wechat_raw = next((c for c in raw_d.columns if '微信' in str(c) and '添加' in str(c)), '添加微信')
    df_d.rename(columns=d_map, inplace=True)
    df_d.rename(columns={wechat_raw: 'S_Wechat'}, inplace=True)
    
    # 补全缺失列（防崩溃）
    for col in ['S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat', '质检总分']:
        if col not in df_d.columns:
            df_d[col] = 0 # 缺列补0
            
    df_d = df_d[['邀约专员/管家', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat']]
    for c in df_d.columns:
        if c != '邀约专员/管家': df_d[c] = pd.to_numeric(df_d[c], errors='coerce')

    # --- C. 门店排名表 (重点检查) ---
    s_map = {
        '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car',
        '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
    }
    df_s = raw_s.copy()
    s_wechat_raw = next((c for c in raw_s.columns if '微信' in str(c) and '添加' in str(c)), '添加微信')
    df_s.rename(columns=s_map, inplace=True)
    df_s.rename(columns={s_wechat_raw: 'S_Wechat'}, inplace=True)

    # 确保有门店名称列
    if '门店名称' not in df_s.columns:
        st.error(f"❌ 门店排名表中找不到【门店名称】列！当前列名：{list(raw_s.columns)}")
        st.info("提示：请检查 CSV 文件是否有多余的表头行。")
        return None, None

    # 补全缺失列
    for col in ['S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat', '质检总分']:
        if col not in df_s.columns:
            df_s[col] = 0

    target_s_cols = ['门店名称', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Time', 'S_Wechat']
    # 只取存在的
    cols_exist = [c for c in target_s_cols if c in df_s.columns]
    df_s = df_s[cols_exist]
    for c in cols_exist:
        if c != '门店名称': df_s[c] = pd.to_numeric(df_s[c], errors='coerce')

    # --- D. AMS ---
    # 极简映射
    df_a = raw_a.copy()
    a_renames = {}
    for c in df_a.columns:
        if '接通' in str(c) and '线索' in str(c): a_renames[c] = 'conn_num'
        if '外呼' in str(c) and '线索' in str(c) and '需' not in str(c): a_renames[c] = 'conn_denom'
        if '及时' in str(c): a_renames[c] = 'timely_num'
        if '需外呼' in str(c): a_renames[c] = 'timely_denom'
        if '管家' in str(c) or '顾问' in str(c): a_renames[c] = '邀约专员/管家'
    
    df_a.rename(columns=a_renames, inplace=True)
    
    # --- E. 合并 ---
    # 清理空格
    for df in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
        if '邀约专员/管家' in df.columns: df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
        if '门店名称' in df.columns: df['门店名称'] = df['门店名称'].astype(str).str.strip()

    full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
    full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')

    # 简单的门店合并
    # 只要 漏斗 + 门店得分
    full_stores = pd.merge(df_store_data, df_s, on='门店名称', how='left')
    
    # 计算AMS指标 (如果没有就算了，防止崩溃)
    if 'conn_num' in full_advisors.columns:
        ams_grp = full_advisors.groupby('门店名称')[['conn_num', 'conn_denom']].sum().reset_index()
        full_stores = pd.merge(full_stores, ams_grp, on='门店名称', how='left')

    return full_advisors, full_stores

# ================= 5. 渲染 =================
if has_data:
    try:
        with st.spinner("🔍 正在诊断数据..."):
            df_advisors, df_stores = process_data_debug(PATH_F, PATH_D, PATH_A, PATH_S)
        
        if df_advisors is not None:
            # --- 成功显示 ---
            st.sidebar.markdown("---")
            store_list = ["全部"] + sorted(df_stores['门店名称'].unique().tolist())
            selected_store = st.sidebar.selectbox("查看范围", store_list)

            if selected_store == "全部":
                current_df = df_stores.copy()
                current_df['Name'] = current_df['门店名称']
            else:
                current_df = df_advisors[df_advisors['门店名称'] == selected_store].copy()
                current_df['Name'] = current_df['邀约专员/管家']

            # 安全计算 KPI
            if '线索量' in current_df.columns:
                kpi_leads = current_df['线索量'].sum()
                kpi_visits = current_df['到店量'].sum()
                kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            else:
                kpi_leads, kpi_visits, kpi_rate = 0, 0, 0
            
            kpi_score = current_df['质检总分'].mean() if '质检总分' in current_df.columns else 0

            # 标题
            st.title(f"📊 Audi DCC 看板 (Running) - {selected_store}")
            
            # KPI
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("线索量", int(kpi_leads))
            k2.metric("到店量", int(kpi_visits))
            k3.metric("到店率", f"{kpi_rate:.1%}")
            k4.metric("质检分", f"{kpi_score:.1f}")
            
            st.markdown("---")
            
            # 图表区
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("通话质量")
                if 'S_60s' in current_df.columns:
                    # 补全 NaN 为 0 方便画图
                    current_df['S_60s'] = current_df['S_60s'].fillna(0)
                    current_df['质检总分'] = current_df['质检总分'].fillna(0)
                    
                    fig = px.scatter(current_df, x="线索到店率_数值", y="S_60s", size="线索量", color="质检总分", hover_name="Name")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("缺少 [60秒通话] 数据")

            with c2:
                st.subheader("排行榜")
                if not current_df.empty:
                    st.dataframe(current_df[['Name', '线索到店率', '质检总分']].sort_values('质检总分', ascending=False), use_container_width=True)

        else:
            # 如果 process_data_debug 返回 None，上面的 st.error 已经显示了错误原因
            st.warning("请根据上方的红色报错信息调整您的文件。")

    except Exception as e:
        st.error("💥 程序崩溃！详细报错信息如下（请截图发给我）：")
        st.code(traceback.format_exc())
