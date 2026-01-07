import streamlit as st
import pandas as pd
import plotly.express as px
import os
import io

# ================= 1. 基础配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")
DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# 清理旧文件
def clear_old_files():
    import glob
    for f in glob.glob(os.path.join(DATA_DIR, "*")):
        try: os.remove(f)
        except: pass

# ================= 2. 外科手术式读取函数 (核心修复) =================
def surgical_read(file_path, file_desc):
    """
    针对 "Ragged CSV" (列数不齐) 的终极修复：
    先作为纯文本读取 -> 找到真正的表头行 -> 截取有效内容 -> 生成 DataFrame
    """
    try:
        # 1. 如果是 Excel (.xlsx)，直接用标准读取
        if file_path.endswith('.xlsx'):
            return pd.read_excel(file_path, header=0) # 默认读第1行，如果失败后面会有逻辑修正

        # 2. 如果是 CSV，进行外科手术处理
        content = None
        used_encoding = 'utf-8'
        
        # 尝试解码 (包含中文的 CSV 通常是 GBK 或 UTF-8-SIG)
        for enc in ['utf-8-sig', 'gb18030', 'gbk', 'utf-8']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.readlines()
                used_encoding = enc
                break
            except:
                continue
        
        if content is None:
            st.error(f"❌ {file_desc} 编码识别失败，无法读取。")
            return None

        # 3. 寻找“真表头”所在的行数
        # 您的文件中，真正有用的那一行包含 "门店名称", "排名", "质检总分" 等关键词
        # 第一行那些 ",,,,,流程规范" 是干扰项
        
        keywords = ['门店名称', '顾问', '管家', '线索', '排名']
        start_row = -1
        
        for i, line in enumerate(content[:20]): # 只扫前20行
            if any(k in line for k in keywords):
                start_row = i
                break
        
        if start_row == -1:
            # 如果没找到关键词，尝试直接暴力读取
            st.warning(f"⚠️ {file_desc} 未找到明显表头，尝试强行读取...")
            return pd.read_csv(file_path, encoding=used_encoding)

        # 4. 截取有效部分并生成 DataFrame
        # 将 list of strings 重新组合成单个 string IO 对象
        clean_content = "".join(content[start_row:])
        df = pd.read_csv(io.StringIO(clean_content))
        
        # 清理列名中的回车换行
        df.columns = df.columns.astype(str).str.strip().str.replace('\n', '')
        
        return df

    except Exception as e:
        st.error(f"❌ 读取 {file_desc} 发生错误: {e}")
        return None

# ================= 3. 数据处理 =================
def process_data_logic():
    # 扫描目录下文件
    files = [f for f in os.listdir(DATA_DIR) if not f.startswith('.')]
    
    data_map = {"funnel": None, "dcc": None, "ams": None, "rank": None}
    
    for f in files:
        full_path = os.path.join(DATA_DIR, f)
        
        # 无论后缀是什么，先读进来看看列名
        df = surgical_read(full_path, f)
        
        if df is not None:
            cols = list(df.columns)
            # 智能分类
            if '到店量' in cols or '有效线索' in cols:
                data_map['funnel'] = df
            elif '排名' in cols and '门店名称' in cols:
                data_map['rank'] = df
            elif ('60秒通话' in cols or 'S_60s' in cols) and '质检总分' in cols:
                data_map['dcc'] = df
            elif '外呼线索数' in cols or '接通线索数' in cols:
                data_map['ams'] = df
    
    return data_map

# ================= 4. 界面渲染 =================
st.sidebar.header("🛠️ 数据上传")

with st.sidebar.form("upload_panel"):
    st.write("请直接上传所有文件 (原始格式即可)：")
    uploaded_files = st.file_uploader("", accept_multiple_files=True)
    if st.form_submit_button("开始分析"):
        if uploaded_files:
            clear_old_files()
            for f in uploaded_files:
                save_path = os.path.join(DATA_DIR, f.name)
                with open(save_path, "wb") as buffer:
                    buffer.write(f.getbuffer())
            st.success(f"已上传 {len(uploaded_files)} 个文件！")
            st.rerun()

# 核心逻辑
data_map = process_data_logic()
missing_files = [k for k, v in data_map.items() if v is None]

if not missing_files:
    try:
        # === 数据准备 ===
        df_f = data_map['funnel']
        df_d = data_map['dcc']
        df_a = data_map['ams']
        df_s = data_map['rank']

        # 1. 统一列名映射
        def standardize_cols(df):
            new_cols = {}
            for c in df.columns:
                if '门店' in c: new_cols[c] = '门店名称'
                elif '顾问' in c or '管家' in c: new_cols[c] = '邀约专员/管家'
                elif '有效线索' in c or '线索量' in c: new_cols[c] = '线索量'
                elif '到店' in c and '率' not in c: new_cols[c] = '到店量'
                elif '接通' in c and '线索' in c: new_cols[c] = 'conn_num'
                elif '外呼' in c and '线索' in c: new_cols[c] = 'conn_denom'
            df.rename(columns=new_cols, inplace=True)
            return df

        df_f = standardize_cols(df_f)
        df_d = standardize_cols(df_d)
        df_a = standardize_cols(df_a)
        df_s = standardize_cols(df_s)

        # 2. 数值转换工具
        def to_num(series):
            return pd.to_numeric(series, errors='coerce').fillna(0)

        # 3. 处理漏斗表
        df_f['线索量'] = to_num(df_f['线索量'])
        df_f['到店量'] = to_num(df_f['到店量'])
        
        # 拆分
        if '邀约专员/管家' in df_f.columns:
            mask_sub = df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)
            df_store_base = df_f[mask_sub].copy()
            df_advisor_base = df_f[~mask_sub].copy()
        else:
            df_store_base = df_f.copy()
            df_advisor_base = pd.DataFrame()

        # 4. 合并顾问数据
        full_advisors = df_advisor_base
        if not full_advisors.empty:
            full_advisors = pd.merge(full_advisors, df_d, on='邀约专员/管家', how='left')
            if 'conn_num' in df_a.columns:
                full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
                full_advisors['conn_num'] = to_num(full_advisors['conn_num'])
                full_advisors['conn_denom'] = to_num(full_advisors['conn_denom'])

        # 5. 合并门店数据 (漏斗 + 排名表)
        # 排名表里应该已经有 '质检总分', '60秒通话' 等
        full_stores = pd.merge(df_store_base, df_s, on='门店名称', how='left')
        
        # 清洗最终数据
        full_stores['质检总分'] = to_num(full_stores.get('质检总分', 0))
        
        # 尝试找 60秒通话 列 (可能叫 60秒通话 或 S_60s)
        s_60_col = next((c for c in full_stores.columns if '60' in str(c)), None)
        if s_60_col: full_stores['S_60s'] = to_num(full_stores[s_60_col])
        else: full_stores['S_60s'] = 0

        # === 页面展示 ===
        st.title("📊 Audi DCC 效能看板")
        
        tab1, tab2 = st.tabs(["🏆 全区概览", "👤 顾问详情"])
        
        with tab1:
            k1, k2, k3 = st.columns(3)
            k1.metric("全区总线索", int(full_stores['线索量'].sum()))
            k2.metric("全区总到店", int(full_stores['到店量'].sum()))
            
            avg_score = full_stores[full_stores['质检总分']>0]['质检总分'].mean()
            k3.metric("门店平均质检分", f"{avg_score:.1f}")
            
            st.markdown("### 门店排名榜")
            
            # 展示列
            cols = ['门店名称', '线索量', '到店量', '质检总分', 'S_60s']
            cols = [c for c in cols if c in full_stores.columns]
            
            # 增加到店率
            full_stores['线索到店率'] = (full_stores['到店量'] / full_stores['线索量'].replace(0, 1)).apply(lambda x: f"{x:.1%}")
            cols.insert(3, '线索到店率')
            
            st.dataframe(
                full_stores[cols].sort_values('质检总分', ascending=False),
                use_container_width=True,
                height=500
            )

        with tab2:
            if not full_advisors.empty:
                st.markdown("### 顾问明细数据")
                stores = ["全部"] + list(full_advisors['门店名称'].unique())
                sel = st.selectbox("筛选门店", stores)
                
                view_df = full_advisors if sel == "全部" else full_advisors[full_advisors['门店名称']==sel]
                
                # 计算展示字段
                view_df['线索到店率'] = (view_df['到店量'] / view_df['线索量'].replace(0, 1)).apply(lambda x: f"{x:.1%}")
                
                # 尝试找接通率
                if 'conn_num' in view_df.columns:
                    view_df['接通率'] = (view_df['conn_num'] / view_df['conn_denom'].replace(0, 1))
                    
                    # 气泡图
                    # 找 60秒 列
                    adv_60_col = next((c for c in view_df.columns if '60' in str(c)), None)
                    if adv_60_col:
                        view_df[adv_60_col] = to_num(view_df[adv_60_col])
                        view_df['质检总分'] = to_num(view_df.get('质检总分', 0))
                        
                        fig = px.scatter(
                            view_df, x='接通率', y=adv_60_col, 
                            size='线索量', color='质检总分', 
                            hover_name='邀约专员/管家',
                            title="话术执行(Y) vs 接通效率(X)"
                        )
                        fig.update_layout(xaxis_tickformat=".0%")
                        st.plotly_chart(fig, use_container_width=True)
                
                st.dataframe(view_df, use_container_width=True)
            else:
                st.info("暂无顾问层级数据")

    except Exception as e:
        st.error(f"数据处理时发生错误: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    st.info("👋 请在左侧上传数据文件")
    st.write("文件识别状态：")
    cols = st.columns(4)
    labels = ["漏斗表", "顾问质检", "AMS表", "门店排名"]
    keys = ["funnel", "dcc", "ams", "rank"]
    
    for i in range(4):
        status = "✅" if data_map[keys[i]] is not None else "❌"
        cols[i].metric(labels[i], status)
