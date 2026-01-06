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

# ================= 3. 智能数据读取函数 =================
def smart_read(file, key_col_snippets):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # 自动寻找表头
        header_found = False
        for i in range(5): 
            cols_str = " ".join([str(c) for c in df.columns])
            if any(k in cols_str for k in key_col_snippets):
                header_found = True
                break
            # 如果这行不是，尝试下一行
            new_header = df.iloc[0]
            df = df[1:]
            df.columns = new_header
            df = df.reset_index(drop=True)
            
        if not header_found:
            st.warning(f"⚠️ 在文件 {file.name} 中未找到关键列 {key_col_snippets}。")
            return None
        return df
    except Exception as e:
        st.error(f"读取 {file.name} 失败: {e}")
        return None

# ================= 4. 数据处理逻辑 (核心修复) =================
def process_data(f_file, d_file, a_file):
    try:
        # 1. 读取
        raw_f = smart_read(f_file, ['管家', '线索'])
        raw_d = smart_read(d_file, ['顾问', '质检'])
        raw_a = smart_read(a_file, ['管家', '通话'])

        if raw_f is None or raw_d is None or raw_a is None:
            return None

        # 2. 漏斗表 (Funnel) -> 提供：管家、线索、到店、门店名称
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), '门店名称')
        
        df_f = raw_f.rename(columns={'管家': '邀约专员/管家', '线上_有效线索数': '线索量', '线上_到店数': '到店量', store_col: '门店名称'})
        
        # 容错：找线索列
        if '线索量' not in df_f.columns:
             lead_col = next((c for c in raw_f.columns if '线索' in str(c) and '有效' in str(c)), None)
             if lead_col: df_f = df_f.rename(columns={lead_col: '线索量'})
        
        # 这里的 df_f 保留了 '门店名称'
        df_f = df_f[['邀约专员/管家', '线索量', '到店量', '门店名称']]

        # 3. DCC表 -> 提供：得分 (只取这些列，防止和 df_f 的门店名称冲突)
        wechat_col = '添加微信'
        if '添加微信.1' in raw_d.columns:
            wechat_col = '添加微信.1'
        
        df_d = raw_d.rename(columns={
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', 
            '车型信息': 'S_Car', '政策相关': 'S_Policy',
            '明确到店时间': 'S_Time'
        })
        df_d['S_Wechat'] = raw_d[wechat_col]
        
        # 修复关键点：显式筛选需要的列，扔掉 DCC 表里的“门店名称”，避免冲突
        df_d = df_d[['邀约专员/管家', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']]

        # 4. AMS表 -> 提供：通话时长
        df_a = raw_a.rename(columns={'管家姓名': '邀约专员/管家', 'DCC平均通话时长': '通话时长'})
        df_a = df_a[['邀约专员/管家', '通话时长']]

        # 5. 去空格
        for df in [df_f, df_d, df_a]:
            df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()

        # 6. 合并
        merged = pd.merge(df_d, df_f, on='邀约专员/管家', how='inner')
        merged = pd.merge(merged, df_a, on='邀约专员/管家', how='inner')
        
        # 7. 数值转换
        cols = ['线索量', '到店量', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time', '通话时长']
        for c in cols:
            merged[c] = pd.to_numeric(merged[c], errors='coerce').fillna(0)
            
        merged['线索到店率'] = (merged['到店量'] / merged['线索量']).replace([np.inf, -np.inf], 0).fillna(0)
        return merged
        
    except Exception as e:
        st.error(f"数据处理出错，请检查文件格式: {e}")
        return None

# ================= 5. 界面渲染 =================

if file_f and file_d and file_a:
    df = process_data(file_f, file_d, file_a)
    
    if df is not None and not df.empty:
        
        # --- 门店筛选 ---
        if '门店名称' not in df.columns:
            st.error("无法找到‘门店名称’列，请检查漏斗指标表中是否包含‘代理商’或‘门店’列。")
        else:
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
                    rank_df = rank_data[['门店名称', '线索到店率', '质检总分']].sort_values('线索到店率', ascending=False).head(10)
                else:
                    st.markdown(f"### 👤 {selected_store} 管家排名")
                    rank_df = df_display[['邀约专员/管家', '线索到店率', '质检总分']].sort_values('线索到店率', ascending=False).head(10)

                st.dataframe(
                    rank_df,
                    hide_index=True,
                    use_container_width=True,
                    height=350,
                    column_config={
                        "线索到店率": st.column_config.ProgressColumn(
                            "线索到店率",
                            format="%.1f%%",
                            min_value=0,
                            max_value=0.2
                        ),
                        "质检总分": st.column_config.NumberColumn(
                            "质检总分",
                            format="%.1f"
                        )
                    }
                )

            with c_right:
                st.markdown("### 💡 明确到店时间 vs 最终结果")
                df_display['转化率_百分比'] = df_display['线索到店率'] * 100
                fig = px.scatter(
                    df_display, x="S_Time", y="转化率_百分比",
                    size="线索量", color="质检总分",
                    hover_name="邀约专员/管家",
                    labels={"S_Time": "明确到店话术得分", "转化率_百分比": "线索到店率(%)"},
                    color_continuous_scale="Reds",
                    height=350
                )
                fig.add_vline(x=df_display['S_Time'].mean(), line_dash="dash", line_color="gray")
                fig.add_hline(y=avg_rate_global * 100, line_dash="dash", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)

            # --- 底部诊断 ---
            st.markdown("---")
            with st.container():
                st.markdown("### 🕵️‍♀️ 管家深度诊断")
                
                advisors = df_display['邀约专员/管家'].unique()
                if len(advisors) > 0:
                    selected_advisor = st.selectbox("请选择要诊断的顾问:", advisors)
                    
                    p = df_display[df_display['邀约专员/管家'] == selected_advisor].iloc[0]
                    
                    d1, d2, d3 = st.columns([1, 1, 1.2])
                    
                    with d1:
                        st.caption("转化漏斗 (RESULT)")
                        fig_funnel = go.Figure(go.Funnel(
                            y = ["线索量", "到店量"],
                            x = [p['线索量'], p['到店量']],
                            textinfo = "value+percent initial",
                            marker = {"color": ["#d9d9d9", "#bb0a30"]}
                        ))
                        fig_funnel.update_layout(showlegend=False, height=200, margin=dict(t=0,b=0,l=0,r=0))
                        st.plotly_chart(fig_funnel, use_container_width=True)
                        st.metric("线索到店率", f"{p['线索到店率']:.1%}")
                        st.caption(f"平均通话时长: {p['通话时长']:.1f} 秒")

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
                            st.progress(min(score/100, 1.0))
                            st.caption(f"得分: {score:.1f}")

                    with d3:
                        with st.container():
                            st.error("🤖 AI 智能诊断建议")
                            issues = []
                            if p['S_Time'] < 60:
                                st.markdown(f"🔴 **致命短板：明确到店时间 (得分{p['S_Time']:.1f})**")
                                st.markdown("未引导客户确认具体到店时间。建议使用二选一法。")
                                issues.append(1)
                            if p['S_60s'] < 60:
                                st.markdown(f"🟠 **基石不稳：60秒占比 (得分{p['S_60s']:.1f})**")
                                st.markdown("客户挂断过快。建议优化开场白利益点。")
                                issues.append(1)
                            if p['S_Wechat'] < 80:
                                st.markdown(f"🟠 **私域缺失：添加微信 (得分{p['S_Wechat']:.1f})**")
                                st.markdown("建议发送定位或配置表为由加微。")
                                issues.append(1)
                            if not issues:
                                st.success("该顾问表现优秀，核心指标健康。")
                else:
                    st.info("该门店下暂无顾问数据。")
    else:
        st.warning("数据清洗后为空，请检查三张表中的姓名列是否一致。")
else:
    st.info("👈 请在左侧上传三个文件")
