import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")
DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# 清理旧文件
def clear_old_files():
    files = glob.glob(os.path.join(DATA_DIR, "*"))
    for f in files:
        try: os.remove(f)
        except: pass

# ================= 2. 核心读取函数 (针对您的报错修复) =================
def robust_read(file_path):
    """
    针对 'gbk codec error' 的修复版读取逻辑
    """
    try:
        df = None
        # 1. 如果是 CSV，轮询编码
        if file_path.lower().endswith('.csv'):
            # 【关键修改】优先尝试 utf-8-sig (解决Excel导出的BOM头问题) 和 utf-8
            encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb18030']
            for enc in encodings:
                try:
                    # 使用 python 引擎，容错率更高
                    df = pd.read_csv(file_path, header=None, encoding=enc, engine='python')
                    break 
                except:
                    continue
        else:
            # Excel
            df = pd.read_excel(file_path, header=None)

        if df is None:
            return None, "无法识别的文件编码"

        # 2. 暴力搜寻表头 (定位“门店名称”或“排名”所在的行)
        target_keywords = ['门店名称', '顾问', '管家', '线索', '排名', '接通']
        header_idx = -1
        
        # 扫描前 10 行
        for i in range(min(10, len(df))):
            # 把这一行转成字符串来搜关键词
            row_str = df.iloc[i].astype(str).str.cat(sep=',')
            if any(k in row_str for k in target_keywords):
                header_idx = i
                break
        
        if header_idx == -1:
            return None, "未找到有效表头（需包含'门店名称'等列）"

        # 3. 重建 DataFrame
        df_final = df.iloc[header_idx+1:].copy()
        df_final.columns = df.iloc[header_idx].astype(str).str.strip().str.replace('\n', '')
        df_final.reset_index(drop=True, inplace=True)
        
        return df_final, "Success"

    except Exception as e:
        return None, str(e)

# ================= 3. 数据处理 =================
def process_data():
    all_files = os.listdir(DATA_DIR)
    file_map = {"funnel": None, "dcc": None, "ams": None, "rank": None}
    
    for f in all_files:
        path = os.path.join(DATA_DIR, f)
        if f.startswith("."): continue
        
        df, msg = robust_read(path)
        if df is None: continue
        
        cols = list(df.columns)
        # 智能分类
        if '到店量' in cols or '有效线索' in cols: file_map["funnel"] = df
        elif '排名' in cols and '门店名称' in cols: file_map["rank"] = df
        elif '60秒通话' in cols and '质检总分' in cols: file_map["dcc"] = df
        elif '外呼线索数' in cols or '接通线索数' in cols: file_map["ams"] = df
            
    return file_map

# ================= 4. 界面渲染 =================
st.sidebar.header("🛠️ 数据上传")

with st.sidebar.form("upload_form"):
    st.write("请一次性上传 4 个文件 (无需重命名)：")
    files = st.file_uploader("", accept_multiple_files=True)
    if st.form_submit_button("🚀 开始分析"):
        if files:
            clear_old_files()
            for f in files:
                # 保留原始文件名
                with open(os.path.join(DATA_DIR, f.name), "wb") as buffer:
                    buffer.write(f.getbuffer())
            st.success(f"上传 {len(files)} 个文件成功！")
            st.rerun()

# 加载数据
data_map = process_data()
missing = [k for k,v in data_map.items() if v is None]

if not missing:
    try:
        # 取数
        df_f = data_map['funnel']
        df_d = data_map['dcc']
        df_a = data_map['ams']
        df_s = data_map['rank'] # 门店排名表

        # --- 1. 列名标准化 ---
        def rename_cols(df, mapping):
            # 模糊匹配：只要列名里包含关键字，就重命名
            new_cols = {}
            for col in df.columns:
                for key, target in mapping.items():
                    if key in col: new_cols[col] = target
            df.rename(columns=new_cols, inplace=True)
            return df

        # 定义映射规则
        map_f = {'门店': '门店名称', '顾问': '管家', '管家': '管家', '有效线索': '线索量', '线索量': '线索量', '到店': '到店量'}
        map_d = {'顾问': '管家'} # 质检表
        map_s = {'门店': '门店名称'} # 排名表
        map_a = {'管家': '管家', '接通': 'conn_num', '外呼': 'conn_denom'} # AMS

        df_f = rename_cols(df_f, map_f)
        df_d = rename_cols(df_d, map_d)
        df_s = rename_cols(df_s, map_s)
        df_a = rename_cols(df_a, map_a)

        # 统一 '管家' 列名为 '邀约专员/管家'
        for df in [df_f, df_d, df_a]:
            if '管家' in df.columns: df.rename(columns={'管家': '邀约专员/管家'}, inplace=True)

        # --- 2. 数值清洗 ---
        def clean_num(s): return pd.to_numeric(s, errors='coerce').fillna(0)
        
        df_f['线索量'] = clean_num(df_f['线索量'])
        df_f['到店量'] = clean_num(df_f['到店量'])
        
        # 拆分 门店行 vs 顾问行 (漏斗表)
        if '邀约专员/管家' in df_f.columns:
            mask_sub = df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)
            df_store_base = df_f[mask_sub].copy()
            df_advisor_base = df_f[~mask_sub].copy()
        else:
            df_store_base = df_f.copy() # 只有门店数据
            df_advisor_base = pd.DataFrame()

        # --- 3. 合并逻辑 ---
        # 顾问层
        full_advisors = df_advisor_base
        if not full_advisors.empty:
            full_advisors = pd.merge(full_advisors, df_d, on='邀约专员/管家', how='left')
            if 'conn_num' in df_a.columns:
                full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
                full_advisors['conn_num'] = clean_num(full_advisors['conn_num'])
                full_advisors['conn_denom'] = clean_num(full_advisors['conn_denom'])

        # 门店层 (漏斗 + 排名表)
        full_stores = pd.merge(df_store_base, df_s, on='门店名称', how='left')
        
        # 补全关键指标
        for c in ['质检总分', 'S_60s', '60秒通话']:
            if c not in full_stores.columns: full_stores[c] = 0
        
        # 兼容列名 (有的表叫 60秒通话，有的叫 S_60s)
        if '60秒通话' in full_stores.columns: full_stores['S_60s'] = full_stores['60秒通话']
        full_stores['质检总分'] = clean_num(full_stores['质检总分'])

        # --- 4. 看板展示 ---
        st.title("📊 Audi DCC 效能看板")
        
        tab1, tab2 = st.tabs(["🏆 门店排名", "👤 顾问明细"])
        
        with tab1:
            k1, k2, k3 = st.columns(3)
            k1.metric("总线索", int(full_stores['线索量'].sum()))
            k2.metric("总到店", int(full_stores['到店量'].sum()))
            avg_s = full_stores[full_stores['质检总分']>0]['质检总分'].mean()
            k3.metric("平均质检分", f"{avg_s:.1f}")
            
            # 显示门店排名表
            cols_show = ['门店名称', '线索量', '到店量', '质检总分']
            if 'S_60s' in full_stores.columns: cols_show.append('S_60s')
            
            # 过滤存在的列
            cols_show = [c for c in cols_show if c in full_stores.columns]
            
            st.dataframe(
                full_stores[cols_show].sort_values('质检总分', ascending=False)
                .style.format({'质检总分': '{:.2f}', 'S_60s': '{:.1f}'}), 
                use_container_width=True
            )

        with tab2:
            if not full_advisors.empty:
                stores = ["全部"] + list(full_advisors['门店名称'].unique())
                sel = st.selectbox("选择门店：", stores)
                
                if sel == "全部": sub = full_advisors
                else: sub = full_advisors[full_advisors['门店名称'] == sel]
                
                # 计算率
                sub['线索到店率'] = (sub['到店量']/sub['线索量'].replace(0,1)).apply(lambda x: f"{x:.1%}")
                
                # 散点图
                if 'conn_num' in sub.columns and 'S_60s' in sub.columns:
                    sub['接通率'] = sub['conn_num'] / sub['conn_denom'].replace(0, 1)
                    fig = px.scatter(sub, x='接通率', y='S_60s', size='线索量', color='质检总分', hover_name='邀约专员/管家', title="接通率 vs 60秒话术")
                    st.plotly_chart(fig, use_container_width=True)
                
                st.dataframe(sub, use_container_width=True)
            else:
                st.info("暂无顾问数据")

    except Exception as e:
        st.error(f"处理数据时出错: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    st.info("👋 请上传数据文件。")
    st.write("目前识别状态：")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("漏斗表", "✅" if data_map['funnel'] is not None else "❌")
    col2.metric("顾问质检", "✅" if data_map['dcc'] is not None else "❌")
    col3.metric("AMS表", "✅" if data_map['ams'] is not None else "❌")
    col4.metric("门店排名", "✅" if data_map['rank'] is not None else "❌")
