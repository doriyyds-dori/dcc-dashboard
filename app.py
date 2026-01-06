import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能质检看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    .stProgress > div > div > div > div { background-color: #bb0a30; }
</style>
""", unsafe_allow_html=True)

st.title("Audi | DCC 效能质检看板")

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.header("📂 数据源")
    file_f = st.file_uploader("1. 漏斗指标表 (Funnel)", type=["xlsx", "csv"])
    file_d = st.file_uploader("2. 管家排名表 (DCC)", type=["xlsx", "csv"])
    file_a = st.file_uploader("3. AMS跟进表 (AMS)", type=["xlsx", "csv"])

# ================= 3. 智能数据读取函数 (防报错核心) =================
def smart_read(file, key_col_snippets):
    """
    尝试读取文件，如果第一行找不到关键列，就往下找，直到找到为止。
    key_col_snippets: 用来识别表头的关键词列表，如 ['管家', '顾问']
    """
    try:
        # 1. 先按默认读取
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # 2. 检查表头是否在第一行
        # 将所有列名转为字符串并拼接，检查是否包含关键词
        header_found = False
        for i in range(5): # 最多往后找5行
            cols_str = " ".join([str(c) for c in df.columns])
            if any(k in cols_str for k in key_col_snippets):
                header_found = True
                break
            # 如果没找到，就把第一行作为列名，重新解析
            new_header = df.iloc[0]
            df = df[1:]
            df.columns = new_header
            df = df.reset_index(drop=True)
            
        if not header_found:
            st.warning(f"⚠️ 在文件 {file.name} 中未找到关键列 {key_col_snippets}，请检查表头。")
            return None
            
        return df
    except Exception as e:
        st.error(f"读取 {file.name} 失败: {e}")
        return None

# ================= 4. 数据处理逻辑 =================
def process_data(f_file, d_file, a_file):
    try:
        # 1. 智能读取
        raw_f = smart_read(f_file, ['管家', '线索'])
        raw_d = smart_read(d_file, ['顾问', '质检'])
        raw_a = smart_read(a_file, ['管家', '通话'])

        if raw_f is None or raw_d is None or raw_a is None:
            return None

        # 2. 漏斗表 (Funnel) 处理
        # 自动找‘门店’列 (可能是‘代理商’或‘门店名称’)
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), '门店名称')
        
        df_f = raw_f.rename(columns={'管家': '邀约专员/管家', '线上_有效线索数': '线索量', '线上_到店数': '到店量', store_col: '门店名称'})
        # 容错：如果找不到对应列，尝试模糊匹配
        if '线索量' not in df_f.columns:
             # 尝试找包含'线索'的数字列
             lead_col = next((c for c in raw_f.columns if '线索' in str(c) and '有效' in str(c)), None)
             if lead_col: df_f = df_f.rename(columns={lead_col: '线索量'})

        df_f = df_f[['邀约专员/管家', '线索量', '到店量', '门店名称']]

        # 3. 管家表 (DCC) 处理
        # 处理重复列名问题 (比如有两个'添加微信')
        # 方案：如果有 '添加微信.1'，优先用它；否则用 '添加微信'
        wechat_col = '添加微信'
        if '添加微信.1' in raw_d.columns:
            wechat_col = '添加微信.1'
        
        df_d = raw_d.rename(columns={
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', 
            '车型信息': 'S_Car', '政策相关': 'S_Policy',
            '明确到店时间': 'S_Time'
        })
        # 单独处理微信列映射
        df_d['S_Wechat'] = raw_d[wechat_col]
        
        # 4. AMS表 处理
        df_a = raw_a.rename(columns={'管家姓名': '邀约专员/管家', 'DCC平均通话时长': '通话时长'})

        # 5. 统一去空格
        for df in [df_f, df_d, df_a]:
            if '邀约专员/管家' in df.columns:
                df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()

        # 6. 合并
        merged = pd.merge(df_d, df_f, on='邀约专员/管家', how='inner')
        merged = pd.merge(merged, df_a[['邀约专员/管家', '通话时长']], on='邀约专员/管家', how='inner')
        
        # 7. 数值安全转换
        cols = ['线索量', '到店量', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time', '通话时长']
        for c in cols:
            if c in merged.columns:
                merged[c] = pd.to_numeric(merged[c], errors='coerce').fillna(0)
            else:
                merged[c] = 0 # 缺列补0
            
        # 计算线索到店率
        merged['线索到店率'] = (merged['到店量'] / merged['线索量']).replace([np.inf, -np.inf], 0).fillna(0)
        
        return merged
        
    except Exception as e:
        st.error(f"数据清洗阶段出错: {e}")
        return None

# ================= 5. 界面渲染 =================

if file_f and file_d and file_a:
    df = process_data(file_f, file_d, file_a)
    
    if df is not None and not df.empty:
        
        # --- 门店筛选 ---
        all_stores = list(df['门店名称'].unique())
        store_options = ["全部"] + all_stores
        selected_store = st.sidebar.selectbox("选择门店查看：", store_options)
        
        if selected_store == "全部":
            df_display = df
        else:
            df_display = df[df['门店名称'] == selected_store]
            
        # --- KPI ---
        k1, k2, k3, k4 = st.columns(4)
        total_leads = int(df_display['线索量'].sum())
        total_visits = int(df_display['到店量'].sum())
        
        if total_leads > 0:
            avg_rate_global = total_visits / total_leads
        else:
            avg_rate_global = 0.0
            
        k1.metric("全区有效线索", f"{total_leads:,}")
        k2.metric("实际到店人数", f"{total_visits:,}")
        k3.metric("平均线索到店率", f"{avg_rate_global:.1%}") 
        k4.metric("平均质检总分", f"{df_display['质检总分'].mean():.1f}") 
        
        st.markdown("---")

        # --- 排名与散点 ---
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            if selected_store == "全部":
                st.markdown("### 🏦 门店排名")
                rank_data = df.groupby('门店名称').agg({'线索量': 'sum', '到店量': 'sum', '质检总分': 'mean'}).reset_index()
                rank_data['线索到店率'] = (rank_data['到店量'] / rank_data['线索量']).fillna(0)
                # 选择列并重命名以符合 column_config
                rank_df = rank_data[['门店名称', '线索到店率', '质检总分']].sort_values('线索到店率', ascending=False).head(10)
            else:
                st.markdown(f"### 👤 {selected_store} 管家排名")
                rank_df = df_display[['邀约专员/管家', '线索到店率', '质检总分']].sort_values('线索到店率', ascending=False).head(10)

            # 使用 Streamlit 原生 Column Config (替代 matplotlib)
            st.dataframe(
                rank_df,
                hide_index=True,
                use_container_width=True,
                height=350,
                column_config={
                    "线索到店率": st.column_config.ProgressColumn(
                        "线索到店率",
                        format="%.1f%%", # 百分比格式
                        min_value=0,
                        max_value=0.2, # 进度条最大值设为20%，让差异更明显
                    ),
                    "质检总分": st.column_config.NumberColumn(
                        "质检总分",
