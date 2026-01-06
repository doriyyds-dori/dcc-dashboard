import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ================= 1. 页面基础设置 =================
st.set_page_config(page_title="Audi DCC 质检六维看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .metric-container {background-color: #f0f2f6; padding: 10px; border-radius: 5px; border-left: 5px solid #bb0a30;}
    .big-font {font-size: 20px !important; font-weight: bold;}
    h3 {border-bottom: 2px solid #e6e6e6; padding-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

st.title("🏎️ Audi DCC | 质检六维效能看板")

# ================= 2. 侧边栏：三表上传 =================
with st.sidebar:
    st.header("📂 数据源配置")
    file_funnel = st.file_uploader("1. 漏斗指标表 (含线索/到店)", type=["xlsx", "csv"])
    file_dcc = st.file_uploader("2. 管家排名表 (含6大质检得分)", type=["xlsx", "csv"])
    file_ams = st.file_uploader("3. AMS跟进表 (含通话时长)", type=["xlsx", "csv"])

def find_col(df, keywords):
    for col in df.columns:
        for k in keywords:
            if k in col: return col
    return df.columns[0]

# ================= 3. 主程序逻辑 =================
if file_funnel and file_dcc and file_ams:
    try:
        # 读取数据
        df_f = pd.read_csv(file_funnel) if file_funnel.name.endswith('csv') else pd.read_excel(file_funnel)
        df_d = pd.read_csv(file_dcc) if file_dcc.name.endswith('csv') else pd.read_excel(file_dcc)
        df_a = pd.read_csv(file_ams) if file_ams.name.endswith('csv') else pd.read_excel(file_ams)

        # --- ⚙️ 关键列名映射 (核心升级) ---
        with st.expander("🔧 点击展开：配置 6 大关键得分列名", expanded=True):
            st.info("请确保下方选中的列名与您 Excel 中的表头一一对应")
            c1, c2, c3 = st.columns(3)
            
            with c1:
                st.markdown("**1. 基础信息**")
                col_name_d = st.selectbox("顾问姓名列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['顾问','姓名'])))
                col_score_total = st.selectbox("质检总分列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['质检','总分'])))
                
            with c2:
                st.markdown("**2. 流程与基石指标**")
                # 60秒 / 用车需求
                col_60s = st.selectbox("【60秒通话占比】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['60秒','时长占比'])))
                col_needs = st.selectbox("【用车需求】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['需求','用车'])))
                col_wechat = st.selectbox("【添加微信】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['微信','加微'])))

            with c3:
                st.markdown("**3. 专业与结果指标**")
                # 车型 / 政策 / 明确到店
                col_car = st.selectbox("【车型信息】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['车型','信息'])))
                col_policy = st.selectbox("【政策相关】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['政策','话术'])))
                col_time = st.selectbox("【明确到店时间】列", df_d.columns, index=df_d.columns.get_loc(find_col(df_d, ['明确','时间'])))

            # 隐式配置其他两表的关键列 (简化显示)
            col_name_f = find_col(df_f, ['顾问','姓名'])
            col_leads = find_col(df_f, ['线索','总数'])
            col_visit = find_col(df_f, ['到店','进店'])
            col_name_a = find_col(df_a, ['顾问','姓名'])
            col_duration = find_col(df_a, ['时长','通话'])

        # --- 数据融合 ---
        df_f = df_f.rename(columns={col_name_f: 'Name'})
        df_d = df_d.rename(columns={col_name_d: 'Name'})
        df_a = df_a.rename(columns={col_name_a: 'Name'})
        
        merged = pd.merge(df_f, df_d, on='Name', how='inner')
        merged = pd.merge(merged, df_a, on='Name', how='inner')
        merged['转化率'] = (merged[col_visit] / merged[col_leads] * 100).fillna(0).round(2)
        
        # ================= 4. 看板展示 =================

        # A. 顶部 KPI
        st.markdown("### 1️⃣ 全区效能概览")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总线索量", int(merged[col_leads].sum()))
        k2.metric("平均转化率", f"{merged['转化率'].mean():.2f}%")
        k3.metric("平均质检总分", f"{merged[col_score_total].mean():.1f}")
        # 算出60秒达标率 (假设 > 0 算有)
        pass_60s = (merged[col_60s] >= 60).sum() / len(merged) * 100
        k4.metric("60秒通话达标率", f"{pass_60s:.1f}%")

        st.markdown("---")

        # B. 顾问深度诊断 (核心升级：六维雷达图)
        st.markdown("### 🕵️‍♀️ 顾问六维能力诊断")
        
        col_list, col_radar = st.columns([1, 2])
        
        with col_list:
            st.subheader("顾问列表")
            selected_advisor = st.radio("点击选择顾问查看详情:", merged['Name'].unique())
            
        with col_radar:
            p = merged[merged['Name'] == selected_advisor].iloc[0]
            
            # 准备雷达图数据
            categories = ['60秒占比', '用车需求', '车型信息', '政策相关', '添加微信', '明确到店']
            values = [p[col_60s], p[col_needs], p[col_car], p[col_policy], p[col_wechat], p[col_time]]
            
            # 绘制雷达图
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
                title=f"{selected_advisor} 的质检能力模型"
            )
            st.plotly_chart(fig, use_container_width=True)

        # C. 详细得分与 AI 建议
        st.markdown("---")
        st.subheader(f"📝 {selected_advisor} 的智能改进方案")
        
        c_score, c_advice = st.columns([1, 1])
        
        with c_score:
            st.caption("各项指标具体得分")
            col_metrics = {
                '60秒通话占比 (基石)': p[col_60s],
                '用车需求 (挖掘)': p[col_needs],
                '车型信息 (专业)': p[col_car],
                '政策相关 (专业)': p[col_policy],
                '添加微信 (留存)': p[col_wechat],
                '明确到店 (结果)': p[col_time]
            }
            
            for k, v in col_metrics.items():
                col_a, col_b = st.columns([3, 1])
                col_a.progress(v/100)
                col_b.write(f"{v} 分")
                st.caption(k)

        with c_advice:
            st.caption("AI 诊断建议")
            
            # 针对 6 个维度的规则引擎
            issues = []
            
            if p[col_time] < 60:
                st.error(f"🔴 **【致命短板】明确到店 (得分{p[col_time]})**：未有效锁定到店时间，流失风险极大。建议使用“二选一”法提问。")
                issues.append(1)
            
            if p[col_60s] < 60:
                st.warning(f"🟠 **【基石不稳】60秒占比 (得分{p[col_60s]})**：客户挂断过快，需优化开场白，增加吸引力。")
                issues.append(1)
                
            if p[col_wechat] < 60:
                st.warning(f"🟠 **【私域缺失】添加微信 (得分{p[col_wechat]})**：未尝试加微，后续跟进困难。建议以“发定位/配置表”为由加微。")
                issues.append(1)
            
            if p[col_needs] < 60:
                st.info(f"🔵 **用车需求 (得分{p[col_needs]})**：需求挖掘不深，建议多用开放式提问（如：您主要在哪里用车？）。")
                issues.append(1)
                
            if not issues:
                st.success("✅ 该顾问六维能力均衡，表现优秀！")

    except Exception as e:
        st.error(f"发生错误，请检查列名是否配置正确。错误信息: {e}")

else:
    st.info("👈 请在左侧上传全部 3 个文件以生成看板")
