import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Audi DCC 效能看板 (最终修复版)", layout="wide", page_icon="🛠️")
DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# 清理旧文件（防止干扰）
def clear_old_files():
    files = glob.glob(os.path.join(DATA_DIR, "*"))
    for f in files:
        try: os.remove(f)
        except: pass

# ================= 2. 智能读取核心函数 =================
def find_header_and_read(file_path):
    """
    不管表头在哪里，暴力找到它。
    """
    try:
        # 1. 尝试读取（自动识别格式）
        if file_path.endswith('.csv'):
            try:
                # 优先尝试 GBK (中文常见)，失败则 UTF-8
                df_raw = pd.read_csv(file_path, header=None, encoding='gb18030')
            except:
                df_raw = pd.read_csv(file_path, header=None, encoding='utf-8')
        else:
            df_raw = pd.read_excel(file_path, header=None)
        
        # 2. 暴力搜寻表头行
        # 我们要找的关键词
        target_keywords = ['门店名称', '顾问', '管家', '线索', '排名', '接通', '质检总分']
        
        header_row_index = -1
        
        # 扫描前 10 行
        for i in range(min(10, len(df_raw))):
            row_str = df_raw.iloc[i].astype(str).str.cat(sep=' ')
            # 如果这一行包含任意一个关键词
            if any(k in row_str for k in target_keywords):
                header_row_index = i
                break
        
        if header_row_index == -1:
            return None, "未找到有效的表头（包含'门店'、'顾问'等字样）"

        # 3. 重塑 Dataframe
        df = df_raw.iloc[header_row_index+1:].copy()
        df.columns = df_raw.iloc[header_row_index].astype(str).str.strip().str.replace('\n', '')
        df.reset_index(drop=True, inplace=True)
        
        return df, "Success"

    except Exception as e:
        return None, str(e)

# ================= 3. 数据处理 =================
def process_all_files():
    # 获取目录下所有文件
    all_files = os.listdir(DATA_DIR)
    
    # 自动归类文件
    file_map = {"funnel": None, "dcc": None, "ams": None, "rank": None}
    
    for f in all_files:
        full_path = os.path.join(DATA_DIR, f)
        if f.startswith("."): continue # 跳过隐藏文件
        
        # 读取内容判断类型
        df, msg = find_header_and_read(full_path)
        if df is None: continue
        
        cols = list(df.columns)
        # 根据列名特征判断是哪个表
        if '到店量' in cols or '有效线索' in cols:
            file_map["funnel"] = df
        elif '60秒通话' in cols and '质检总分' in cols and '门店名称' in cols:
            # 门店排名表通常也有质检分，且必须有门店名称
            file_map["rank"] = df
        elif '60秒通话' in cols and '质检总分' in cols:
            # 顾问表通常也有这些，但没有“排名”列
            file_map["dcc"] = df
        elif '外呼线索数' in cols or '接通线索数' in cols:
            file_map["ams"] = df
    
    return file_map

# ================= 4. 界面逻辑 =================
st.sidebar.header("🛠️ 数据上传")

# 上传区
with st.sidebar.form("upload_form"):
    st.write("请直接上传原始文件（无需重命名）：")
    files = st.file_uploader("请一次性上传所有 4 个文件", accept_multiple_files=True)
    if st.form_submit_button("开始分析"):
        if files:
            clear_old_files()
            saved_count = 0
            for f in files:
                # 保留原始文件名保存！这是关键！
                save_path = os.path.join(DATA_DIR, f.name)
                with open(save_path, "wb") as buffer:
                    buffer.write(f.getbuffer())
                saved_count += 1
            st.success(f"成功上传 {saved_count} 个文件，正在读取...")
            st.rerun()

# 主逻辑
data_map = process_all_files()

# 检查是否缺文件
missing = [k for k, v in data_map.items() if v is None]

if not missing:
    # === 所有数据就绪，开始处理 ===
    try:
        df_f = data_map['funnel']
        df_d = data_map['dcc']
        df_a = data_map['ams']
        df_s = data_map['rank']

        # 1. 统一列名
        # 漏斗
        f_rename = {c: '门店名称' for c in df_f.columns if '门店' in c}
        f_rename.update({c: '邀约专员/管家' for c in df_f.columns if '顾问' in c or '管家' in c})
        f_rename.update({c: '线索量' for c in df_f.columns if '线索' in c and '量' in c})
        f_rename.update({c: '到店量' for c in df_f.columns if '到店' in c and '量' in c})
        df_f.rename(columns=f_rename, inplace=True)

        # 质检
        d_rename = {c: '邀约专员/管家' for c in df_d.columns if '顾问' in c}
        df_d.rename(columns=d_rename, inplace=True)

        # 排名
        s_rename = {c: '门店名称' for c in df_s.columns if '门店' in c}
        df_s.rename(columns=s_rename, inplace=True)

        # AMS
        a_rename = {c: '邀约专员/管家' for c in df_a.columns if '管家' in c or '顾问' in c}
        a_rename.update({c: 'conn_num' for c in df_a.columns if '接通' in c})
        a_rename.update({c: 'conn_denom' for c in df_a.columns if '外呼' in c and '需' not in c})
        df_a.rename(columns=a_rename, inplace=True)

        # 2. 数值转换
        def to_num(s): return pd.to_numeric(s, errors='coerce').fillna(0)
        
        df_f['线索量'] = to_num(df_f['线索量'])
        df_f['到店量'] = to_num(df_f['到店量'])
        
        # 拆分
        df_stores = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
        df_advisors = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()

        # 3. 合并
        # 顾问层
        full_advisors = pd.merge(df_advisors, df_d, on='邀约专员/管家', how='left')
        if 'conn_num' in df_a.columns:
            full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
            full_advisors['conn_num'] = to_num(full_advisors['conn_num'])
            full_advisors['conn_denom'] = to_num(full_advisors['conn_denom'])

        # 门店层
        full_stores = pd.merge(df_stores, df_s, on='门店名称', how='left')
        
        # 4. 渲染看板
        st.title("📊 Audi DCC 效能看板")
        
        mode = st.radio("查看维度", ["门店排名", "顾问明细"], horizontal=True)
        
        if mode == "门店排名":
            st.subheader("🏆 全区门店总览")
            
            # 补全可能缺失的列
            for c in ['质检总分', 'S_60s']:
                if c not in full_stores.columns: full_stores[c] = 0
            else:
                full_stores['质检总分'] = to_num(full_stores['质检总分'])

            # 核心KPI
            k1, k2, k3 = st.columns(3)
            k1.metric("总线索", int(full_stores['线索量'].sum()))
            k2.metric("总到店", int(full_stores['到店量'].sum()))
            avg_score = full_stores[full_stores['质检总分']>0]['质检总分'].mean()
            k3.metric("平均质检分", f"{avg_score:.1f}")

            # 表格
            disp_cols = ['门店名称', '线索量', '到店量', '质检总分']
            # 动态加入存在的列
            if '60秒通话' in full_stores.columns: disp_cols.append('60秒通话')
            
            st.dataframe(
                full_stores[[c for c in disp_cols if c in full_stores.columns]]
                .sort_values('质检总分', ascending=False)
                .style.background_gradient(subset=['质检总分'], cmap='RdYlGn'),
                use_container_width=True
            )

        else:
            st.subheader("👤 顾问明细")
            sel_store = st.selectbox("选择门店", full_stores['门店名称'].unique())
            subset = full_advisors[full_advisors['门店名称'] == sel_store].copy()
            
            # 计算到店率
            subset['线索到店率'] = (subset['到店量'] / subset['线索量'].replace(0, 1)).apply(lambda x: f"{x:.1%}")
            
            st.dataframe(subset[['邀约专员/管家', '线索量', '到店量', '线索到店率', '质检总分']], use_container_width=True)
            
            if 'S_60s' in subset.columns and 'conn_num' in subset.columns:
                subset['接通率'] = subset['conn_num'] / subset['conn_denom'].replace(0, 1)
                fig = px.scatter(subset, x='接通率', y='S_60s', size='线索量', color='质检总分', hover_name='邀约专员/管家', title='接通率 vs 60秒话术')
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"处理过程中发生错误: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    st.info("👋 欢迎使用！目前数据为空。")
    st.warning(f"请在左侧上传文件。目前识别到的文件类型：")
    
    cols = st.columns(4)
    names = {"funnel": "漏斗表", "dcc": "顾问质检", "ams": "AMS表", "rank": "门店排名"}
    for i, (key, df) in enumerate(data_map.items()):
        status = "✅ 已识别" if df is not None else "❌ 未找到"
        cols[i].metric(names[key], status)
    
    if data_map['rank'] is None and os.path.exists(PATH_S):
        st.error("提示：门店排名表虽然上传了，但没找到'门店名称'列，请检查文件内容。")
