import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ================= 1. 页面基础设置 =================
st.set_page_config(page_title="Audi DCC 质检实战看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .metric-card {background-color: #f9f9f9; border-left: 5px solid #bb0a30; padding: 15px; border-radius: 5px;}
    .stProgress > div > div > div > div { background-color: #bb0a30; }
    div[data-testid="stFileUploader"] {margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

st.title("🏎️ Audi DCC | 效能质检实战看板")
st.caption("请在左侧上传您的三个原始报表文件（支持 Excel/CSV）")

# ================= 2. 数据读取与清洗函数 =================

def load_file(uploaded_file):
    """智能读取 Excel 或 CSV"""
    try:
        if uploaded_file.name.lower().endswith('.csv'):
            return pd.read_csv(uploaded_file)
        else:
            return pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"文件 {uploaded_file.name} 读取失败: {e}")
        return None

def clean_data(df_funnel, df_dcc, df_ams):
    """
    针对您的三个特定文件进行自动清洗和合并
    """
    # 1. 规范化列名 (基于您提供的文件结构)
    # 漏斗表: '管家' -> Name, '线上_有效线索数' -> Leads, '线上_到店数' -> Visits
    df_funnel = df_funnel.rename(columns={
        '管家': 'Name', 
        '线上_有效线索数': 'Leads', 
        '线上_到店数': 'Visits'
    })
    
    # DCC表: '顾问名称' -> Name, 以及6大得分
    df_dcc = df_dcc.rename(columns={
        '顾问名称': 'Name',
        '质检总分': 'Score',
        '60秒通话': 'S_60s',
        '用车需求': 'S_Needs',
        '车型信息': 'S_Car',
        '政策相关': 'S_Policy',
        '添加微信': 'S_Wechat',
        '明确到店时间': 'S_Time'
    })
    
    # AMS表: '管家姓名' -> Name, 'DCC平均通话时长' -> Duration
    df_ams = df_ams.rename(columns={
        '管家姓名': 'Name',
        'DCC平均通话时长': 'Duration'
    })

    # 2. 清理姓名列 (去空格，防止匹配不上)
    for df in [df_funnel, df_dcc, df_ams]:
        if 'Name' in df.columns:
            df['Name'] = df['Name'].astype(str).str.strip()
        else:
            st.error("无法在表中找到‘顾问姓名’列，请检查表头是否包含 '管家' 或 '顾问名称'")
            return None

    # 3. 合并数据 (Inner Join，只保留三张表都有的人)
    merged = pd.merge(df_dcc, df_funnel[['Name', 'Leads', 'Visits']], on='Name', how='inner')
    merged = pd.merge(merged, df_ams[['Name', 'Duration']], on='Name', how='inner')

    # 4. 数值类型转换 (防止Excel里有非数字字符)
    cols = ['Score', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time', 'Leads', 'Visits', 'Duration']
    for c in cols:
        merged[c] = pd.to_numeric(merged[c], errors='coerce').fillna(0)

    # 5. 计算转化率
    merged['转化率'] = (merged['Visits'] / merged['Leads'] * 100).fillna(0).round(2)
    
    return merged

# ================= 3. 侧边栏：上传入口 =================
with st.sidebar:
    st.header("📂 数据上传区")
    
    file_f = st.file_uploader("1. 上传【漏斗指标表】(Funnel)", type=["xlsx", "csv"])
    file_d = st.file_uploader("2. 上传【管家排名表】(DCC)", type=["xlsx", "csv"])
    file_a = st.file_uploader("3. 上传【AMS跟进表】(AMS)", type=["xlsx", "csv"])
    
    st.markdown("---")
    st.info("💡 提示：上传顺序不限，只要三个文件齐了就会自动分析。")

# ================= 4. 主逻辑 =================

if file_f and file_d and file_a:
    # 1. 读取
    raw_f = load_file(file_f)
    raw_d = load_file(file_d)
    raw_a = load_file(file_a)

    if raw_f is not None and raw_d is not None and raw_a is not None:
        # 2. 清洗与合并
        df = clean_data(raw_f, raw_d, raw_a)
        
        if df is not None and not df.empty:
            st.success(f"✅ 数据融合成功！共分析 {len(df)} 位顾问。")
            
            # --- A. 全局 KPI ---
            st.markdown("### 1️⃣ 全区效能概览")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("总线索量", int(df['Leads'].sum()))
            k2.metric("平均转化率", f"{df['转化率'].mean():.2f}%")
            k3.metric("平均质检分", f"{df['Score'].mean():.1f}")
            # 计算60秒达标率 (>0分即视为有动作，或者您可以定>=60)
            pass_rate = (df['S_60s'] >= 60).mean() * 100
            k4.metric("60秒通话达标率 (≥60分)", f"{pass_rate:.1f}%")

            st.markdown("---")

            # --- B. 顾问六维诊断 (雷达图) ---
            st.markdown("### 🕵️‍♀️ 顾问深度诊断")
            
            c_selector, c_radar = st.columns([1, 2])
            
            with c_selector:
                st.subheader("👥 顾问名单")
                # 按质检分排序显示
                sorted_names = df.sort_values('Score', ascending=False)['Name'].unique()
                selected_advisor = st.radio("请选择顾问:", sorted_names)
            
            with c_radar:
                # 获取该顾问数据
                p = df[df['Name'] == selected_advisor].iloc[0]
                
                st.subheader(f"📊 {selected_advisor} 的六维能力模型")
                
                # 雷达图
                categories = ['60秒占比', '用车需求', '车型信息', '政策相关', '添加微信', '明确到店']
                values = [p['S_60s'], p['S_Needs'], p['S_Car'], p['S_Policy'], p['S_Wechat'], p['S_Time']]
                
                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(
                    r=values,
                    theta=categories,
                    fill='toself',
                    name=selected_advisor,
                    line_color='#bb0a30'
                ))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=False,
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)

            # --- C. 详细数据与 AI 建议 ---
            st.markdown("---")
            st.subheader(f"📝 {selected_advisor} 的改进方案")
            
            d1, d2 = st.columns(2)
            
            with d1:
                st.info("📋 **执行与结果数据**")
                st.write(f"⏱️ **DCC平均通话时长**: {p['Duration']} 秒")
                st.write(f"📉 **线索转化率**: {p['转化率']}% (线索 {int(p['Leads'])} -> 到店 {int(p['Visits'])})")
                
                st.markdown("#### 六维得分详情")
                metrics = {
                    '60秒通话占比': p['S_60s'],
                    '用车需求': p['S_Needs'],
                    '车型信息': p['S_Car'],
                    '政策相关': p['S_Policy'],
                    '添加微信': p['S_Wechat'],
                    '明确到店': p['S_Time']
                }
                for k, v in metrics.items():
                    col_x, col_y = st.columns([3, 1])
                    col_x.progress(min(v/100, 1.0))
                    col_y.write(f"{v} 分")
                    st.caption(k)

            with d2:
                st.error("🤖 **AI 智能诊断 (基于业务规则)**")
                issues = []
                
                # 规则 1: 明确到店时间 (核心)
                if p['S_Time'] < 60:
                    st.markdown(f"🔴 **【致命短板】明确到店 (得分 {p['S_Time']})**")
                    st.markdown("> **问题**：未有效引导客户确认到店时间。")
                    st.markdown("> **话术**：采用二选一法则：“您是周六上午方便，还是下午方便？”")
                    issues.append(1)

                # 规则 2: 60秒通话 (基石)
                if p['S_60s'] < 60:
                    st.markdown(f"🟠 **【基石不稳】60秒占比 (得分 {p['S_60s']})**")
                    st.markdown("> **问题**：客户挂断过快，开场白缺乏吸引力。")
                    st.markdown("> **话术**：前3句需抛出利益点（如现车资源、限时活动）。")
                    issues.append(1)

                # 规则 3: 添加微信
                if p['S_Wechat'] < 80:
                    st.markdown(f"🟠 **【私域缺失】添加微信 (得分 {p['S_Wechat']})**")
                    st.markdown("> **问题**：未尝试留存私域流量。")
                    st.markdown("> **话术**：以“发具体配置表”或“发定位”为由尝试加微。")
                    issues.append(1)
                
                # 规则 4: 通话时长
                if p['Duration'] < 40:
                    st.markdown(f"🔵 **【沟通过浅】通话时长 ({p['Duration']}秒)**")
                    st.markdown("> **建议**：增加开放式提问，深入挖掘客户用车场景。")
                    issues.append(1)

                if not issues:
                    st.success("✅ 该顾问表现优秀，各项核心指标均无明显短板！")

        else:
            st.warning("数据合并后为空。请检查您的三个表格中【顾问姓名】列是否一致（是否有空格或错别字）。")
else:
    # 初始空状态
    st.info("👈 请在左侧侧边栏上传您的 3 个 Excel/CSV 文件。")
    st.markdown("""
    ### 👋 欢迎使用
    上传文件后，系统将自动关联分析以下数据：
    1. **结果数据**（线索、到店、转化率）
    2. **过程数据**（通话时长）
    3. **质检得分**（60秒占比、用车需求、添加微信、明确到店等）
    """)
