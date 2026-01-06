import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np # 引入numpy处理数学计算

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能质检看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    .red-border {border-left: 5px solid #bb0a30 !important;}
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

# ================= 3. 数据清洗 (修复无穷大Bug) =================
def process_data(f_file, d_file, a_file):
    try:
        raw_f = pd.read_csv(f_file) if f_file.name.endswith('csv') else pd.read_excel(f_file)
        raw_d = pd.read_csv(d_file) if d_file.name.endswith('csv') else pd.read_excel(d_file)
        raw_a = pd.read_csv(a_file) if a_file.name.endswith('csv') else pd.read_excel(a_file)

        # 清洗列名
        df_f = raw_f.rename(columns={'管家': 'Name', '线上_有效线索数': 'Leads', '线上_到店数': 'Visits'})
        df_d = raw_d.rename(columns={
            '顾问名称': 'Name', '质检总分': 'Score',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', 
            '车型信息': 'S_Car', '政策相关': 'S_Policy',
            '添加微信': 'S_Wechat', '明确到店时间': 'S_Time'
        })
        df_a = raw_a.rename(columns={'管家姓名': 'Name', 'DCC平均通话时长': 'Duration'})

        # 统一去空格
        for df in [df_f, df_d, df_a]:
            if 'Name' in df.columns:
                df['Name'] = df['Name'].astype(str).str.strip()

        # 合并
        merged = pd.merge(df_d, df_f[['Name', 'Leads', 'Visits']], on='Name', how='inner')
        merged = pd.merge(merged, df_a[['Name', 'Duration']], on='Name', how='inner')
        
        # 转换数值
        cols = ['Leads', 'Visits', 'Score', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time', 'Duration']
        for c in cols:
            merged[c] = pd.to_numeric(merged[c], errors='coerce').fillna(0)
            
        # --- 核心修复：计算转化率 ---
        # 1. 正常计算
        merged['Rate'] = (merged['Visits'] / merged['Leads'] * 100)
        # 2. 将无穷大 (inf) 替换为 0，将空值 (nan) 替换为 0
        merged['Rate'] = merged['Rate'].replace([np.inf, -np.inf], 0).fillna(0).round(2)
        
        return merged
        
    except Exception as e:
        st.error(f"数据处理出错: {e}")
        return None

# ================= 4. 界面渲染 =================

if file_f and file_d and file_a:
    df = process_data(file_f, file_d, file_a)
    
    if df is not None and not df.empty:
        
        # --- 顶部 KPI ---
        k1, k2, k3, k4 = st.columns(4)
        
        total_leads = int(df['Leads'].sum())
        total_visits = int(df['Visits'].sum())
        
        # 修复：使用加权平均计算总转化率 (总到店/总线索)，避免无穷大
        if total_leads > 0:
            avg_rate_global = (total_visits / total_leads) * 100
        else:
            avg_rate_global = 0.0
            
        k1.metric("全区有效线索", total_leads)
        k2.metric("实际到店人数", total_visits)
        k3.metric("平均到店率", f"{avg_rate_global:.2f}%") # 使用新的加权平均
        k4.metric("平均质检分", f"{df['Score'].mean():.1f}")
        
        st.markdown("---")

        # --- 排名与散点图 ---
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown("### 🏦 门店到店率排名")
            rank_df = df[['Name', 'Rate', 'Score']].sort_values('Rate', ascending=False).head(8)
            # 使用高亮显示
            st.dataframe(
                rank_df.style.background_gradient(subset=['Rate'], cmap="Reds"),
                hide_index=True,
                use_container_width=True,
                height=300
            )

        with c_right:
            st.markdown("### 💡 明确到店时间 vs 最终结果")
            fig = px.scatter(
                df, x="S_Time", y="Rate",
                size="Leads", color="Score",
                hover_name="Name",
                labels={"S_Time": "明确到店话术得分", "Rate": "到店转化率(%)"},
                color_continuous_scale="Reds",
                height=350
            )
            fig.add_vline(x=df['S_Time'].mean(), line_dash="dash", line_color="gray")
            # 这里的平均线也用加权平均值
            fig.add_hline(y=avg_rate_global, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)

        # --- 底部诊断 ---
        st.markdown("---")
        with st.container():
            st.markdown("### 🕵️‍♀️ 管家深度诊断")
            
            advisors = df['Name'].unique()
            selected_advisor = st.selectbox("请选择顾问:", advisors)
            
            p = df[df['Name'] == selected_advisor].iloc[0]
            
            d1, d2, d3 = st.columns([1, 1, 1.2])
            
            with d1:
                st.caption("转化漏斗 (RESULT)")
                fig_funnel = go.Figure(go.Funnel(
                    y = ["线索量", "到店量"],
                    x = [p['Leads'], p['Visits']],
                    textinfo = "value+percent initial",
                    marker = {"color": ["#d9d9d9", "#bb0a30"]}
                ))
                fig_funnel.update_layout(showlegend=False, height=200, margin=dict(t=0,b=0,l=0,r=0))
                st.plotly_chart(fig_funnel, use_container_width=True)
                st.metric("最终转化率", f"{p['Rate']}%")
                st.caption(f"平均通话时长: {p['Duration']} 秒")

            with d2:
                st.caption("质检得分详情 (QUALITY)")
                metrics = {
                    "明确到店时间 (核心)": p['S_Time'],
                    "60秒通话占比 (基石)": p['S_60s'],
                    "车型信息介绍": p['S_Car'],
                    "政策相关话术": p['S_Policy'],
                    "添加微信": p['S_Wechat']
                }
                for label, score in metrics.items():
                    st.text(f"{label}")
                    st.progress(min(score/100, 1.0)) # 修复：防止超过100分报错
                    st.caption(f"得分: {score}")

            with d3:
                with st.container():
                    st.error("🤖 AI 智能诊断建议")
                    issues = []
                    
                    if p['S_Time'] < 60:
                        st.markdown(f"🔴 **致命短板：明确到店时间 (得分{p['S_Time']})**")
                        st.markdown("原因：未引导客户确认具体到店时间。建议使用二选一法。")
                        issues.append(1)
                    
                    if p['S_60s'] < 60:
                        st.markdown(f"🟠 **基石不稳：60秒占比 (得分{p['S_60s']})**")
                        st.markdown("原因：客户挂断过快。建议优化开场白利益点。")
                        issues.append(1)
                        
                    if p['S_Wechat'] < 80:
                        st.markdown(f"🟠 **私域缺失：添加微信 (得分{p['S_Wechat']})**")
                        st.markdown("建议：发送定位或配置表为由加微。")
                        issues.append(1)
                        
                    if not issues:
                        st.success("该顾问表现优秀，核心指标健康。")
    else:
        st.warning("数据为空，请检查上传表格的列名是否正确。")
else:
    st.info("👈 请在左侧上传三个文件")
