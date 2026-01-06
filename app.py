import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能质检看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    .stProgress > div > div > div > div { background-color: #bb0a30; }
    div[data-testid="stSelectbox"] {min-width: 200px;}
</style>
""", unsafe_allow_html=True)

# ================= 2. 侧边栏 =================
with st.sidebar:
    st.header("📂 数据上传")
    file_f = st.file_uploader("1. 漏斗指标表 (含小计行)", type=["xlsx", "csv"])
    file_d = st.file_uploader("2. 管家排名表 (含质检分)", type=["xlsx", "csv"])
    file_a = st.file_uploader("3. AMS跟进表 (含时长)", type=["xlsx", "csv"])

# ================= 3. 数据处理 (核心修正：直接透传原表率) =================
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
        # 1. 找列名
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), raw_f.columns[0])
        name_col = next((c for c in raw_f.columns if '管家' in str(c) or '顾问' in str(c)), raw_f.columns[1])
        col_leads = '线上_有效线索数' if '线上_有效线索数' in raw_f.columns else '线索量'
        col_visits = '线上_到店数' if '线上_到店数' in raw_f.columns else '到店量'
        
        # 【关键修正】直接锁定原始率列 (线上_有效线索到店率)
        col_excel_rate = next((c for c in raw_f.columns if '率' in str(c) and ('到店' in str(c) or '有效' in str(c))), None)

        # 重命名
        rename_dict = {store_col: '门店名称', name_col: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'}
        if col_excel_rate: rename_dict[col_excel_rate] = '原始到店率' # 标记一下
        
        df_f = raw_f.rename(columns=rename_dict)
        
        # 2. 分离数据
        # 提取门店行 (小计)
        df_store_data = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
        
        # 提取顾问行 (非小计、非总计、非-)
        df_advisor_data = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()

        # 3. 数值清洗
        for df in [df_store_data, df_advisor_data]:
            df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
            df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
            
            # 【绝对核心】：直接使用 Excel 里的率
            if '原始到店率' in df.columns:
                # 尝试转数字
                df['原始到店率'] = pd.to_numeric(df['原始到店率'], errors='coerce').fillna(0)
                # 只有当数据明显是小数(如0.05)时，我们在展示时会格式化为百分比
                # 这里不做额外除法，直接信赖 Excel 的值
                df['线索到店率'] = df['原始到店率']
            else:
                # 只有万一没这一列，才自己算
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
        
        # 1. 顾问全量表 (个人维度) -> Merge
        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='inner')
        full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
        full_advisors['通话时长'] = full_advisors['通话时长'].fillna(0)

        # 2. 门店全量表 (门店维度) -> 
        # 关键：基础数据(线索、到店、率) 直接用 df_store_data (即Excel小计行)
        # 只有质检分需要从个人表聚合 (因为小计行通常没质检分)
        store_scores = full_advisors.groupby('门店名称')[['质检总分', 'S_Time']].mean().reset_index()
        
        # 将聚合后的分数，拼接到 Excel 的小计行上
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
            # 门店列表优先从门店表取
            if not df_stores.empty: all_stores = sorted(list(df_stores['门店名称'].unique()))
            else: all_stores = sorted(list(df_advisors['门店名称'].unique()))
            store_options = ["全部"] + all_stores
            selected_store = st.selectbox("🏭 切换门店视图", store_options)

        # --- 核心逻辑分支 ---
        if selected_store == "全部":
            # === 全区模式 (直接展示 df_stores 即小计行) ===
            # 这里的数据就是 Excel 里的行，绝对准确
            current_df = df_stores
            rank_title = "🏆 全区门店排名"
            name_col_show = "门店名称"
            scatter_x_label = "门店平均明确到店分"
            
            # KPI (求和大盘)
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            # 大盘的总转化率还是得算一下，因为Excel没有“总计”行的数据
            if kpi_leads > 0: kpi_rate = kpi_visits / kpi_leads
            else: kpi_rate = 0
            kpi_score = df_advisors['质检总分'].mean()

        else:
            # === 单店模式 (展示个人行) ===
            current_df = df_advisors[df_advisors['门店名称'] == selected_store]
            rank_title = f"👤 {selected_store} - 顾问排名"
            name_col_show = "邀约专员/管家"
            scatter_x_label = "个人明确到店得分"
            
            # KPI
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            # 单店的总转化率，如果有小计行直接取；这里暂用累加求和
            if kpi_leads > 0: kpi_rate = kpi_visits / kpi_leads
            else: kpi_rate = 0
            kpi_score = current_df['质检总分'].mean()

        # --- 1. KPI 卡片 ---
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")
        
        st.markdown("---")

        # --- 2. 排名 & 散点 ---
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown(f"### {rank_title}")
            # 这里的线索到店率直接来自 Excel 列，不做计算
            rank_df = current_df[[name_col_show, '线索到店率', '质检总分']].sort_values('线索到店率', ascending=False).head(15)
            
            st.dataframe(
                rank_df,
                hide_index=True,
                use_container_width=True,
                height=400,
                column_config={
                    name_col_show: st.column_config.TextColumn("名称"),
                    "线索到店率": st.column_config.ProgressColumn(
                        "线索到店率",
                        format="%.1f%%", # 格式化显示百分比
                        min_value=0,
                        max_value=0.2,   # 进度条长度比例
                    ),
                    "质检总分": st.column_config.NumberColumn(
                        "质检总分", format="%.1f"
                    )
                }
            )

        with c_right:
            st.markdown("### 💡 话术质量 vs 转化结果")
            plot_df = current_df.copy()
            # 绘图用百分比值 (0-100)
            plot_df['转化率%'] = plot_df['线索到店率'] * 100
            
            fig = px.scatter(
                plot_df, 
                x="S_Time", 
                y="转化率%", 
                size="线索量", 
                color="质检总分",
                hover_name=name_col_show,
                labels={"S_Time": scatter_x_label, "转化率%": "线索到店率(%)"},
                color_continuous_scale="Reds",
                height=400
            )
            if not plot_df.empty:
                fig.add_vline(x=plot_df['S_Time'].mean(), line_dash="dash", line_color="gray")
                fig.add_hline(y=kpi_rate * 100, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)

        # --- 3. 深度诊断 ---
        st.markdown("---")
        with st.container():
            st.markdown("### 🕵️‍♀️ 管家深度诊断")
            
            # 严格联动：只显示当前范围内的顾问
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
                        st.metric("线索到店率", f"{p['线索到店率']:.1%}") # 这里的率也是直接取自Excel
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
