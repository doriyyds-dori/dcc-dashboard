import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ================= 1. 页面配置 (还原奥迪风格) =================
st.set_page_config(page_title="Audi DCC 效能质检看板", layout="wide", page_icon="🏎️")

# 注入 CSS：还原截图里的卡片阴影、红色边框和字体风格
st.markdown("""
<style>
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    .red-border {border-left: 5px solid #bb0a30 !important;}
    .big-num {font-size: 24px; font-weight: bold; color: #333;}
    .sub-text {font-size: 14px; color: #666;}
    h3 {font-size: 18px !important; font-weight: 600; margin-top: 20px;}
    .stSelectbox > div > div {background-color: #fff;}
    /* 进度条颜色 */
    .stProgress > div > div > div > div { background-color: #bb0a30; }
</style>
""", unsafe_allow_html=True)

st.title("Audi | DCC 效能质检看板")

# ================= 2. 侧边栏：上传三个固定格式文件 =================
with st.sidebar:
    st.header("📂 数据源")
    st.caption("请上传您的三个原始报表：")
    file_f = st.file_uploader("1. 漏斗指标表 (Funnel)", type=["xlsx", "csv"])
    file_d = st.file_uploader("2. 管家排名表 (DCC)", type=["xlsx", "csv"])
    file_a = st.file_uploader("3. AMS跟进表 (AMS)", type=["xlsx", "csv"])

# ================= 3. 数据清洗 (针对您的文件写死规则) =================
def process_data(f_file, d_file, a_file):
    try:
        # 读取
        raw_f = pd.read_csv(f_file) if f_file.name.endswith('csv') else pd.read_excel(f_file)
        raw_d = pd.read_csv(d_file) if d_file.name.endswith('csv') else pd.read_excel(d_file)
        raw_a = pd.read_csv(a_file) if a_file.name.endswith('csv') else pd.read_excel(a_file)

        # 1. 清洗漏斗表 (Funnel)
        df_f = raw_f.rename(columns={'管家': 'Name', '线上_有效线索数': 'Leads', '线上_到店数': 'Visits'})
        df_f = df_f[['Name', 'Leads', 'Visits']]

        # 2. 清洗管家表 (DCC)
        # 您的表头：顾问名称, 质检总分, 60秒通话, 用车需求, 车型信息, 政策相关, 添加微信, 明确到店时间
        df_d = raw_d.rename(columns={
            '顾问名称': 'Name', '质检总分': 'Score',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', 
            '车型信息': 'S_Car', '政策相关': 'S_Policy',
            '添加微信': 'S_Wechat', '明确到店时间': 'S_Time'
        })
        # 确保只要这些列，防止报错
        df_d = df_d[['Name', 'Score', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']]

        # 3. 清洗AMS表
        df_a = raw_a.rename(columns={'管家姓名': 'Name', 'DCC平均通话时长': 'Duration'})
        df_a = df_a[['Name', 'Duration']]

        # 4. 统一去空格
        for df in [df_f, df_d, df_a]:
            df['Name'] = df['Name'].astype(str).str.strip()

        # 5. 合并 (Inner Join)
        merged = pd.merge(df_d, df_f, on='Name', how='inner')
        merged = pd.merge(merged, df_a, on='Name', how='inner')
        
        # 6. 计算转化率和数值化
        cols = ['Leads', 'Visits', 'Score', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time', 'Duration']
        for c in cols:
            merged[c] = pd.to_numeric(merged[c], errors='coerce').fillna(0)
            
        merged['Rate'] = (merged['Visits'] / merged['Leads'] * 100).fillna(0).round(2)
        return merged
        
    except Exception as e:
        st.error(f"数据处理出错: {e}")
        return None

# ================= 4. 界面渲染 (严格还原截图布局) =================

if file_f and file_d and file_a:
    df = process_data(file_f, file_d, file_a)
    
    if df is not None and not df.empty:
        
        # --- 第一部分：顶部 KPI (KPI Cards) ---
        # 布局：4个指标横排
        k1, k2, k3, k4 = st.columns(4)
        
        k1.metric("全区有效线索", int(df['Leads'].sum()))
        k2.metric("实际到店人数", int(df['Visits'].sum()))
        avg_rate = df['Rate'].mean()
        k3.metric("平均到店率", f"{avg_rate:.2f}%")
        k4.metric("平均质检分", f"{df['Score'].mean():.1f}")
        
        st.markdown("---")

        # --- 第二部分：排名与散点图 (Ranking & Scatter) ---
        # 布局：左窄(排名)，右宽(散点)
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown("### 🏦 门店到店率排名")
            # 简化展示：姓名 | 到店率 | 质检分
            rank_df = df[['Name', 'Rate', 'Score']].sort_values('Rate', ascending=False).head(8)
            # 使用简单的 dataframe 展示，高亮到店率
            st.dataframe(
                rank_df.style.background_gradient(subset=['Rate'], cmap="Reds"),
                hide_index=True,
                use_container_width=True,
                height=300
            )

        with c_right:
            st.markdown("### 💡 明确到店时间 vs 最终结果")
            # 还原截图的散点图逻辑：X轴=话术得分，Y轴=转化率
            fig = px.scatter(
                df, x="S_Time", y="Rate",
                size="Leads", color="Score",
                hover_name="Name",
                labels={"S_Time": "明确到店话术得分", "Rate": "到店转化率(%)"},
                color_continuous_scale="Reds",
                height=350
            )
            # 加平均线
            fig.add_vline(x=df['S_Time'].mean(), line_dash="dash", line_color="gray")
            fig.add_hline(y=df['Rate'].mean(), line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)

        # --- 第三部分：管家深度诊断 (Deep Diagnosis) ---
        # 这是一个独立的卡片区域，还原截图底部的样子
        st.markdown("---")
        with st.container():
            st.markdown("### 🕵️‍♀️ 管家深度诊断")
            
            # 1. 筛选器
            advisor_list = df['Name'].unique()
            selected_advisor = st.selectbox("请选择顾问:", advisor_list)
            
            # 获取该人数据
            p = df[df['Name'] == selected_advisor].iloc[0]
            
            # 2. 三栏布局：漏斗 | 质检得分条 | AI建议
            d1, d2, d3 = st.columns([1, 1, 1.2])
            
            # -> 左侧：转化漏斗
            with d1:
                st.caption("转化漏斗 (RESULT)")
                fig_funnel = go.Figure(go.Funnel(
                    y = ["线索量", "到店量"],
                    x = [p['Leads'], p['Visits']],
                    textinfo = "value+percent initial",
                    marker = {"color": ["#d9d9d9", "#bb0a30"]} # 灰+红
                ))
                fig_funnel.update_layout(showlegend=False, height=200, margin=dict(t=0,b=0,l=0,r=0))
                st.plotly_chart(fig_funnel, use_container_width=True)
                st.metric("最终转化率", f"{p['Rate']}%")
                # 额外展示通话时长 (来自AMS)
                st.caption(f"平均通话时长: {p['Duration']} 秒")

            # -> 中间：质检得分详情 (条形图样式)
            with d2:
                st.caption("质检得分详情 (QUALITY)")
                
                # 按照截图样式，列出关键项
                metrics = {
                    "明确到店时间 (核心)": p['S_Time'],
                    "60秒通话占比 (基石)": p['S_60s'],
                    "车型信息介绍": p['S_Car'],
                    "政策相关话术": p['S_Policy'],
                    "添加微信": p['S_Wechat']
                }
                
                for label, score in metrics.items():
                    # 进度条
                    st.text(f"{label}")
                    st.progress(score/100)
                    st.caption(f"得分: {score}")

            # -> 右侧：AI 智能诊断建议 (带红框)
            with d3:
                # 模拟那个红色的边框效果
                with st.container():
                    st.error("🤖 AI 智能诊断建议") # 使用Error样式作为红框容器
                    
                    issues = []
                    
                    # 规则 1: 明确到店
                    if p['S_Time'] < 60:
                        st.markdown(f"🔴 **致命短板：明确到店时间 (得分{p['S_Time']})**")
                        st.markdown("这是导致客户流失的核心原因。请检查是否不敢提出具体邀约时间，建议使用二选一法。")
                        issues.append(1)
                    
                    # 规则 2: 60秒通话
                    if p['S_60s'] < 60:
                        st.markdown(f"🟠 **基石不稳：60秒占比 (得分{p['S_60s']})**")
                        st.markdown("客户挂断过快，开场白缺乏吸引力。")
                        issues.append(1)
                        
                    # 规则 3: 私域
                    if p['S_Wechat'] < 80:
                        st.markdown(f"🟠 **私域缺失：添加微信 (得分{p['S_Wechat']})**")
                        st.markdown("未尝试留存私域流量，建议发送定位加微。")
                        issues.append(1)
                        
                    if not issues:
                        st.success("该顾问表现优秀，核心指标健康。")

    else:
        st.warning("数据合并为空，请检查Excel中的姓名列是否一致。")
else:
    st.info("👈 请在左侧上传您的三个文件 (AMS, DCC, 漏斗) 以生成看板。")
