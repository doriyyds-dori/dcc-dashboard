import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
</style>
""", unsafe_allow_html=True)

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.header("📂 数据上传")
    file_f = st.file_uploader("1. 漏斗指标表 (含小计行)", type=["xlsx", "csv"])
    file_d = st.file_uploader("2. 管家排名表 (含质检分)", type=["xlsx", "csv"])
    file_a = st.file_uploader("3. AMS跟进表 (含时长)", type=["xlsx", "csv"])

# ================= 3. 数据处理 =================
def smart_read(file):
    try:
        if file.name.endswith('.csv'): return pd.read_csv(file)
        else: return pd.read_excel(file)
    except: return None

def process_data(f_file, d_file, a_file):
    try:
        raw_f = smart_read(f_file)
        raw_d = smart_read(d_file)
        raw_a = smart_read(a_file)

        if raw_f is None or raw_d is None or raw_a is None: return None, None

        # --- A. 漏斗表处理 ---
        # 1. 找核心列
        # 门店列
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), raw_f.columns[0])
        # 姓名列
        name_col = next((c for c in raw_f.columns if '管家' in str(c) or '顾问' in str(c)), raw_f.columns[1])
        # 线索列
        col_leads = '线上_有效线索数' if '线上_有效线索数' in raw_f.columns else '线索量'
        # 到店列
        col_visits = '线上_到店数' if '线上_到店数' in raw_f.columns else '到店量'
        
        # 【关键】直接锁定 Excel 里的 "线上_有效线索到店率"
        # 优先找完全匹配的，找不到再找带“率”的
        col_excel_rate = '线上_有效线索到店率'
        if col_excel_rate not in raw_f.columns:
             col_excel_rate = next((c for c in raw_f.columns if '率' in str(c) and ('到店' in str(c) or '有效' in str(c))), None)

        # 重命名映射
        rename_dict = {
            store_col: '门店名称', 
            name_col: '邀约专员/管家', 
            col_leads: '线索量', 
            col_visits: '到店量'
        }
        if col_excel_rate: 
            rename_dict[col_excel_rate] = 'Excel_Rate' # 标记它

        df_f = raw_f.rename(columns=rename_dict)
        
        # 2. 分离 门店行(小计) 和 个人行
        # 提取门店数据 (小计行)
        df_store_data = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
        # 提取顾问数据
        df_advisor_data = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()

        # 3. 数值清洗与率的处理
        for df in [df_store_data, df_advisor_data]:
            df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
            df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
            
            # 【核心逻辑】：直接引用 Excel 里的率
            if 'Excel_Rate' in df.columns:
                df['Excel_Rate'] = pd.to_numeric(df['Excel_Rate'], errors='coerce').fillna(0)
                # 判断百分比格式：如果大部分数据>1 (比如 5.2)，说明是 5.2%，需要除以100变成小数用于格式化
                # 如果大部分数据<1 (比如 0.052)，说明已经是小数，不用动
                if df['Excel_Rate'].max() > 1.0:
                    df['线索到店率'] = df['Excel_Rate'] / 100
                else:
                    df['线索到店率'] = df['Excel_Rate']
            else:
                # 只有找不到列时才计算
                df['线索到店率'] = (df['到店量'] / df['线索量']).replace([np.inf, -np.inf], 0).fillna(0)

        # --- B. DCC 表处理 ---
        wechat_col = '添加微信.1' if '添加微信.1' in raw_d.columns else '添加微信'
        df_d = raw_d.rename(columns={
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', 
            '车型信息': 'S_Car', '政策相关': 'S_Policy',
            '明确到店时间': 'S_Time'
        })
        df_d['S_Wechat'] = raw_d[wechat_col]
        df_d = df_d[['邀约专员/管家', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']]

        # --- C. AMS 表处理 ---
        df_a = raw_a.rename(columns={'管家姓名': '邀约专员/管家', 'DCC平均通话时长': '通话时长'})
        df_a = df_a[['邀约专员/管家', '通话时长']]

        # --- D. 去空格 ---
        for df in [df_store_data, df_advisor_data, df_d, df_a]:
            if '邀约专员/管家' in df.columns: df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
            if '门店名称' in df.columns: df['门店名称'] = df['门店名称'].astype(str).str.strip()

        # --- E. 组合数据 ---
        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='inner')
        full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
        full_advisors['通话时长'] = full_advisors['通话时长'].fillna(0)

        store_scores = full_advisors.groupby('门店名称')[['质检总分', 'S_Time']].mean().reset_index()
        full_stores = pd.merge(df_store_data, store_scores, on='门店名称', how='left')
        
        return full_advisors, full_stores

    except Exception as e:
        st.error(f"处理出错: {e}")
        return None, None

# ================= 4. 界面渲染 =================

if file_f and file_d and file_a:
    df_advisors, df_stores = process_data(file_f, file_d, file_a)
    
    if df_advisors is not None:
        
        # --- 顶部布局 ---
        col_header, col_filter = st.columns([3, 1])
        with col_header: st.title("Audi | DCC 效能质检看板")
        with col_filter:
            if not df_stores.empty: all_stores = sorted(list(df_stores['门店名称'].unique()))
            else: all_stores = sorted(list(df_advisors['门店名称'].unique()))
            store_options = ["全部"] + all_stores
            selected_store = st.selectbox("🏭 切换门店视图", store_options)

        # --- 逻辑分支 ---
        if selected_store == "全部":
            # 模式 A: 门店排名
            current_df = df_stores.copy()
            # 为了表格显示统一，把“门店名称”这列复制一份叫“名称”
            current_df['名称'] = current_df['门店名称']
            rank_title = "🏆 全区门店排名"
            scatter_x_label = "门店平均明确到店分"
            
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            if kpi_leads > 0: kpi_rate = kpi_visits / kpi_leads
            else: kpi_rate = 0
            kpi_score = df_advisors['质检总分'].mean()

        else:
            # 模式 B: 个人排名
            current_df = df_advisors[df_advisors['门店名称'] == selected_store].copy()
            # 为了表格显示统一，把“邀约专员/管家”这列复制一份叫“名称”
            current_df['名称'] = current_df['邀约专员/管家']
            rank_title = f"👤 {selected_store} - 顾问排名"
            scatter_x_label = "个人明确到店得分"
            
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            if kpi_leads > 0: kpi_rate = kpi_visits / kpi_leads
            else: kpi_rate = 0
            kpi_score = current_df['质检总分'].mean()

        # --- KPI ---
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")
        
        st.markdown("---")

        # --- 排名 & 散点 ---
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown(f"### {rank_title}")
            
            # 准备表格数据：固定选取 [名称, 线索到店率, 质检总分]
            # 这样无论切门店还是全区，列名都叫“名称”，就不会消失了
            rank_df = current_df[['名称', '线索到店率', '质检总分']].sort_values('线索到店率', ascending=False).head(15)
            
            st.dataframe(
                rank_df,
                hide_index=True,
                use_container_width=True,
                height=400,
                column_config={
                    "名称": st.column_config.TextColumn("名称"),
                    "线索到店率": st.column_config.NumberColumn(
                        "线索到店率",
                        format="%.1f%%", # 强制百分比格式，解决手动格式问题
                    ),
                    "质检总分": st.column_config.NumberColumn(
                        "质检总分", format="%.1f"
                    )
                }
            )

        with c_right:
            st.markdown("### 💡 话术质量 vs 转化结果")
            plot_df = current_df.copy()
            plot_df['转化率%'] = plot_df['线索到店率'] * 100
            
            fig = px.scatter(
                plot_df, 
                x="S_Time", 
                y="转化率%", 
                size="线索量", 
                color="质检总分",
                hover_name="名称",
                labels={"S_Time": scatter_x_label, "转化率%": "线索到店率(%)"},
                color_continuous_scale="Reds",
                height=400
            )
            if not plot_df.empty:
                fig.add_vline(x=plot_df['S_Time'].mean(), line_dash="dash", line_color="gray")
                fig.add_hline(y=kpi_rate * 100, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)

        # --- 诊断 ---
        st.markdown("---")
        with st.container():
            st.markdown("### 🕵️‍♀️ 管家深度诊断")
            
            if selected_store == "全部":
                st.info("💡 请先在右上方选择具体【门店】，查看该门店下的顾问详细诊断。")
            else:
                diag_list = sorted(current_df['邀约专员/管家'].unique())
                if len(diag_list) > 0:
                    selected_person = st.selectbox("🔍 选择/搜索该店顾问：", diag_list)
                    p = df_advisors[df_advisors['邀约专员/管家'] == selected_person].iloc[0]
                    
                    d1, d2, d3 = st.columns([1, 1, 1.2])
                    with d1:
                        st.caption("转化漏斗 (RESULT)")
                        fig_f = go.Figure(go.Funnel(
                            y = ["线索量", "到店量"],
                            x = [p['线索量'], p['到店量']],
                            textinfo = "value+percent initial",
                            marker = {"color": ["#d9d9d9", "#bb0a30"]}
                        ))
                        fig_f.update_layout(showlegend=False, height=180, margin=dict(t=0,b=0,l=0,r=0))
                        st.plotly_chart(fig_f, use_container_width=True)
                        st.metric("线索到店率", f"{p['线索到店率']:.1%}") 
                        st.caption(f"平均通话时长: {p['通话时长']:.1f} 秒")

                    with d2:
                        st.caption("质检得分详情 (QUALITY)")
                        metrics = {
                            "明确到店时间": p['S_Time'], "60秒通话占比": p['S_60s'],
                            "车型信息介绍": p['S_Car'], "政策相关话术": p['S_Policy'], "添加微信": p['S_Wechat']
                        }
                        for k, v in metrics.items():
                            c_a, c_b = st.columns([3, 1])
                            c_a.progress(min(v/100, 1.0))
                            c_b.write(f"{v:.1f}")
                            st.caption(k)

                    with d3:
                        with st.container():
                            st.error("🤖 AI 智能诊断建议")
                            issues = []
                            if p['S_Time'] < 60:
                                st.markdown(f"🔴 **明确到店 (得分{p['S_Time']:.1f})**\n建议使用二选一法锁定时间。")
                                issues.append(1)
                            if p['S_60s'] < 60:
                                st.markdown(f"🟠 **60秒占比 (得分{p['S_60s']:.1f})**\n开场白需抛出利益点。")
                                issues.append(1)
                            if p['S_Wechat'] < 80:
                                st.markdown(f"🟠 **添加微信 (得分{p['S_Wechat']:.1f})**\n建议以发定位为由加微。")
                                issues.append(1)
                            if not issues: st.success("各项指标表现优秀！")
                else:
                    st.warning("该门店下暂无顾问数据。")
else:
    st.info("👈 请在左侧上传三个文件")
