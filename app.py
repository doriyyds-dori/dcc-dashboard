import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    .big-font {font-size: 18px !important; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# ================= 2. 安全锁与文件存储 =================
ADMIN_PASSWORD = "AudiSARR3" 

DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")

def save_uploaded_file(uploaded_file, save_path):
    with open(save_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return True

# ================= 3. 侧边栏逻辑 =================
with st.sidebar:
    st.header("⚙️ 管理面板")
    has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A)
    if has_data: st.success("✅ 数据状态：已就绪")
    else: st.warning("⚠️ 暂无数据")
    st.markdown("---")
    
    with st.expander("🔐 更新数据 (仅限管理员)"):
        pwd = st.text_input("输入管理员密码", type="password")
        if pwd == ADMIN_PASSWORD:
            st.info("🔓 请上传新文件：")
            new_f = st.file_uploader("1. 漏斗指标表", type=["xlsx", "csv"])
            new_d = st.file_uploader("2. 管家排名表", type=["xlsx", "csv"])
            new_a = st.file_uploader("3. AMS跟进表", type=["xlsx", "csv"])
            if st.button("🚀 确认更新数据"):
                if new_f and new_d and new_a:
                    save_uploaded_file(new_f, PATH_F)
                    save_uploaded_file(new_d, PATH_D)
                    save_uploaded_file(new_a, PATH_A)
                    st.success("更新成功！正在刷新...")
                    st.rerun()
                else: st.error("请传齐 3 个文件")

# ================= 4. 数据处理 =================
def smart_read(file_path):
    try:
        if isinstance(file_path, str):
            if file_path.endswith('.csv'): return pd.read_csv(file_path)
            else: return pd.read_excel(file_path)
        else:
            if file_path.name.endswith('.csv'): return pd.read_csv(file_path)
            else: return pd.read_excel(file_path)
    except: return None

def clean_percent_col(df, col_name):
    if col_name not in df.columns: return
    series = df[col_name].astype(str).str.strip().str.replace('%', '', regex=False)
    numeric_series = pd.to_numeric(series, errors='coerce').fillna(0)
    if numeric_series.max() > 1.0:
        df[col_name] = numeric_series / 100
    else:
        df[col_name] = numeric_series

def safe_div(df, num_col, denom_col):
    num = pd.to_numeric(df[num_col], errors='coerce').fillna(0)
    denom = pd.to_numeric(df[denom_col], errors='coerce').fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)

def process_data(path_f, path_d, path_a):
    try:
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        if raw_f is None or raw_d is None or raw_a is None: return None, None

        # --- A. 漏斗表 ---
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), raw_f.columns[0])
        name_col = next((c for c in raw_f.columns if '管家' in str(c) or '顾问' in str(c)), raw_f.columns[1])
        col_leads = '线上_有效线索数' if '线上_有效线索数' in raw_f.columns else '线索量'
        col_visits = '线上_到店数' if '线上_到店数' in raw_f.columns else '到店量'
        col_excel_rate = next((c for c in raw_f.columns if '率' in str(c) and ('到店' in str(c) or '有效' in str(c))), None)

        rename_dict = {store_col: '门店名称', name_col: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'}
        if col_excel_rate: rename_dict[col_excel_rate] = 'Excel_Rate'
        
        df_f = raw_f.rename(columns=rename_dict)
        df_store_data = df_f[df_f['邀约专员/管家'].astype(str).str.contains('小计', na=False)].copy()
        df_advisor_data = df_f[~df_f['邀约专员/管家'].astype(str).str.contains('计|-', na=False)].copy()

        for df in [df_store_data, df_advisor_data]:
            df['线索量'] = pd.to_numeric(df['线索量'], errors='coerce').fillna(0)
            df['到店量'] = pd.to_numeric(df['到店量'], errors='coerce').fillna(0)
            if 'Excel_Rate' in df.columns:
                clean_percent_col(df, 'Excel_Rate')
                df['线索到店率_数值'] = df['Excel_Rate']
            else:
                df['线索到店率_数值'] = safe_div(df, '到店量', '线索量')
            df['线索到店率'] = (df['线索到店率_数值'] * 100).map('{:.1f}%'.format)

        # --- B. DCC (质检分) ---
        wechat_col = '添加微信.1' if '添加微信.1' in raw_d.columns else '添加微信'
        df_d = raw_d.rename(columns={
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        })
        df_d['S_Wechat'] = raw_d[wechat_col]
        
        # 确保分数为数字，但不要 fillna(0)，保留 NaN
        score_cols = ['质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']
        for c in score_cols:
            df_d[c] = pd.to_numeric(df_d[c], errors='coerce') # 转换失败或空值都会变成 NaN

        df_d = df_d[['邀约专员/管家'] + score_cols]

        # --- C. AMS ---
        cols_config = [
            ({'管家姓名'}, '邀约专员/管家'),
            ({'DCC平均通话时长'}, '通话时长'),
            ({'DCC接通线索数'}, 'conn_num'), ({'DCC外呼线索数'}, 'conn_denom'),
            ({'DCC及时处理线索'}, 'timely_num'), ({'需外呼线索数'}, 'timely_denom'),
            ({'二次外呼线索数'}, 'call2_num'), ({'需再呼线索数'}, 'call2_denom'),
            ({'DCC三次外呼的线索数', '三次外呼线索数'}, 'call3_num'), 
            ({'DCC二呼状态为需再呼的线索数', '二呼状态为需再呼'}, 'call3_denom')
        ]
        found_rename_map = {}
        for keywords, target_name in cols_config:
            found_col = None
            for col in raw_a.columns:
                for k in keywords:
                    if k in str(col).strip(): found_col = col; break
                if found_col: break
            if found_col: found_rename_map[found_col] = target_name
        
        df_a = raw_a.rename(columns=found_rename_map)
        
        all_ams_calc_cols = ['conn_num', 'conn_denom', 'timely_num', 'timely_denom', 
                             'call2_num', 'call2_denom', 'call3_num', 'call3_denom']
        for c in all_ams_calc_cols:
            if c not in df_a.columns: df_a[c] = 0
            else: df_a[c] = pd.to_numeric(df_a[c], errors='coerce').fillna(0)

        df_a['外呼接通率'] = safe_div(df_a, 'conn_num', 'conn_denom')
        df_a['DCC及时处理率'] = safe_div(df_a, 'timely_num', 'timely_denom')
        df_a['DCC二次外呼率'] = safe_div(df_a, 'call2_num', 'call2_denom')
        df_a['DCC三次外呼率'] = safe_div(df_a, 'call3_num', 'call3_denom')

        final_ams_cols = ['邀约专员/管家', '通话时长', '外呼接通率', 'DCC及时处理率', 'DCC二次外呼率', 'DCC三次外呼率'] + all_ams_calc_cols
        df_a = df_a[final_ams_cols]

        # --- D. Merge ---
        for df in [df_store_data, df_advisor_data, df_d, df_a]:
            if '邀约专员/管家' in df.columns: df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
            if '门店名称' in df.columns: df['门店名称'] = df['门店名称'].astype(str).str.strip()

        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
        full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
        
        # 【核心修正】：只填充"数量"列为0，绝对不要动"分数"列的 NaN
        cols_to_fill_zero = ['线索量', '到店量', '通话时长'] + all_ams_calc_cols
        full_advisors[cols_to_fill_zero] = full_advisors[cols_to_fill_zero].fillna(0)
        # 注意：这里没有执行 full_advisors.fillna(0)，所以质检分里的 NaN 依然是 NaN

        agg_dict = {
            '质检总分': 'mean', 'S_Time': 'mean', 'S_60s': 'mean', # mean 会自动忽略 NaN，得出正确平均分
            'conn_num': 'sum', 'conn_denom': 'sum',
            'timely_num': 'sum', 'timely_denom': 'sum',
            'call2_num': 'sum', 'call2_denom': 'sum',
            'call3_num': 'sum', 'call3_denom': 'sum'
        }
        store_scores = full_advisors.groupby('门店名称').agg(agg_dict).reset_index()
        
        # 聚合后重新计算率
        store_scores['外呼接通率'] = safe_div(store_scores, 'conn_num', 'conn_denom')
        store_scores['DCC及时处理率'] = safe_div(store_scores, 'timely_num', 'timely_denom')
        store_scores['DCC二次外呼率'] = safe_div(store_scores, 'call2_num', 'call2_denom')
        store_scores['DCC三次外呼率'] = safe_div(store_scores, 'call3_num', 'call3_denom')

        full_stores = pd.merge(df_store_data, store_scores, on='门店名称', how='left')
        
        return full_advisors, full_stores

    except Exception as e:
        st.error(f"处理出错: {e}")
        return None, None

# ================= 5. 界面渲染 =================
if has_data:
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A)
    
    if df_advisors is not None:
        
        col_header, col_filter = st.columns([3, 1])
        with col_header: st.title("Audi | DCC 效能看板")
        with col_filter:
            if not df_stores.empty: all_stores = sorted(list(df_stores['门店名称'].unique()))
            else: all_stores = sorted(list(df_advisors['门店名称'].unique()))
            store_options = ["全部"] + all_stores
            selected_store = st.selectbox("🏭 切换门店视图", store_options)

        if selected_store == "全部":
            current_df = df_stores.copy()
            current_df['名称'] = current_df['门店名称']
            rank_title = "🏆 全区门店排名"
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            if kpi_leads > 0: kpi_rate = kpi_visits / kpi_leads
            else: kpi_rate = 0
            kpi_score = df_advisors['质检总分'].mean() # 这里会自动忽略 NaN
        else:
            current_df = df_advisors[df_advisors['门店名称'] == selected_store].copy()
            current_df['名称'] = current_df['邀约专员/管家']
            rank_title = f"👤 {selected_store} - 顾问排名"
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            if kpi_leads > 0: kpi_rate = kpi_visits / kpi_leads
            else: kpi_rate = 0
            kpi_score = current_df['质检总分'].mean()

        # ------------------- 1. 结果 (Result) -------------------
        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")
        
        # ------------------- 2. 过程 (Process) -------------------
        st.markdown("---")
        st.subheader("2️⃣ DCC 外呼过程监控 (Process)")
        
        # 2.1 过程指标 KPI (加权计算)
        p1, p2, p3, p4 = st.columns(4)
        
        def calc_kpi_rate(df, num, denom):
            total_num = df[num].sum()
            total_denom = df[denom].sum()
            return total_num / total_denom if total_denom > 0 else 0

        avg_conn = calc_kpi_rate(current_df, 'conn_num', 'conn_denom')
        avg_timely = calc_kpi_rate(current_df, 'timely_num', 'timely_denom')
        avg_call2 = calc_kpi_rate(current_df, 'call2_num', 'call2_denom')
        avg_call3 = calc_kpi_rate(current_df, 'call3_num', 'call3_denom')
        
        p1.metric("📞 外呼接通率", f"{avg_conn:.1%}")
        p2.metric("⚡ DCC及时处理率", f"{avg_timely:.1%}")
        p3.metric("🔄 二次外呼率", f"{avg_call2:.1%}")
        p4.metric("🔁 三次外呼率", f"{avg_call3:.1%}")
        
        st.caption("注：以上为加权平均值 (总分子 / 总分母)")

        # 2.2 关联图表 (为展示美观，画图时将 NaN 质检分暂填为 0，但提示用户)
        c_proc_1, c_proc_2 = st.columns(2)
        
        # 绘图数据准备 (仅用于绘图，不影响 KPI 计算)
        plot_df_vis = current_df.copy()
        # 将分数 NaN 填为 0 以免散点图报错，或者过滤掉
        # 策略：为了能看到所有人（即使没质检分），我们将质检分填为 0，但在 hover 里显示 '无'
        plot_df_vis['质检总分_显示'] = plot_df_vis['质检总分'].fillna(0)
        
        with c_proc_1:
            st.markdown("#### 🕵️ 异常侦测：DCC外呼接通率 vs 60秒通话占比")
            st.info("💡 **分析逻辑：** 右下角（接通率高但60秒占比低）代表可能存在“人为压低时长/话术差”问题。")
            
            fig_p1 = px.scatter(
                plot_df_vis, 
                x="外呼接通率", 
                y="S_60s", 
                size="线索量",
                color="质检总分_显示",
                hover_name="名称",
                labels={"外呼接通率": "外呼接通率", "S_60s": "60秒通话占比得分"},
                color_continuous_scale="RdYlGn", 
                height=350
            )
            fig_p1.add_vline(x=avg_conn, line_dash="dash", line_color="gray")
            # 注意：这里的 S_60s 平均值计算也要忽略 NaN
            fig_p1.add_hline(y=plot_df_vis['S_60s'].mean(), line_dash="dash", line_color="gray")
            fig_p1.update_layout(xaxis=dict(tickformat=".0%"))

            fig_p1.update_traces(
                customdata=np.stack((
                    plot_df_vis['线索量'], 
                    plot_df_vis['外呼接通率'], 
                    plot_df_vis['S_60s'].fillna(0), 
                    plot_df_vis['质检总分'].fillna(0)
                ), axis=-1),
                hovertemplate=(
                    "<b>%{hovertext}</b><br><br>" +
                    "线索量: %{customdata[0]:,}<br>" +
                    "外呼接通率: %{customdata[1]:.1%}<br>" +
                    "60秒通话占比得分: %{customdata[2]:.0f}<br>" + 
                    "质检总分: %{customdata[3]:.1f}<br>" +
                    "<extra></extra>"
                )
            )
            st.plotly_chart(fig_p1, use_container_width=True)

        with c_proc_2:
            st.markdown("#### 🔗 归因分析：过程指标 vs 线索首邀到店率")
            st.info("💡 **分析逻辑：** 监控外呼及时性与邀约到店率相关性。")
            
            x_axis_choice = st.radio("选择横轴指标：", ["DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"], horizontal=True)
            
            plot_df_corr = plot_df_vis.copy()
            plot_df_corr['转化率%'] = plot_df_corr['线索到店率_数值'] * 100
            
            fig_p2 = px.scatter(
                plot_df_corr,
                x=x_axis_choice,
                y="转化率%",
                size="线索量",
                color="质检总分_显示",
                hover_name="名称",
                labels={x_axis_choice: x_axis_choice, "转化率%": "线索到店率(%)"},
                color_continuous_scale="Blues",
                height=300
            )
            fig_p2.update_layout(xaxis=dict(tickformat=".0%"))

            fig_p2.update_traces(
                customdata=np.stack((
                    plot_df_corr['线索量'], 
                    plot_df_corr['DCC及时处理率'], 
                    plot_df_corr['DCC二次外呼率'], 
                    plot_df_corr['DCC三次外呼率'],
                    plot_df_corr['线索到店率_数值'],
                    plot_df_corr['质检总分'].fillna(0)
                ), axis=-1),
                hovertemplate=(
                    "<b>%{hovertext}</b><br><br>" +
                    "线索量: %{customdata[0]:,}<br>" +
                    "DCC及时处理率: %{customdata[1]:.1%}<br>" +
                    "DCC二次外呼率: %{customdata[2]:.1%}<br>" +
                    "DCC三次外呼率: %{customdata[3]:.1%}<br>" +
                    "线索到店率: %{customdata[4]:.1%}<br>" +
                    "质检总分: %{customdata[5]:.1f}<br>" +
                    "<extra></extra>"
                )
            )

            st.plotly_chart(fig_p2, use_container_width=True)

        st.markdown("---")

        # ------------------- 3. 详细排名 & 诊断 -------------------
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown(f"### 🏆 {rank_title}")
            # 排序时把 NaN 视为 0 放在最后
            rank_df = current_df[['名称', '线索到店率', '线索到店率_数值', '质检总分']].copy()
            rank_df['Sort_Score'] = rank_df['线索到店率_数值'].fillna(-1)
            rank_df = rank_df.sort_values('Sort_Score', ascending=False).head(15)
            display_df = rank_df[['名称', '线索到店率', '质检总分']]
            
            st.dataframe(
                display_df,
                hide_index=True,
                use_container_width=True,
                height=400,
                column_config={
                    "名称": st.column_config.TextColumn("名称"),
                    "线索到店率": st.column_config.TextColumn("线索到店率"),
                    "质检总分": st.column_config.NumberColumn("质检总分", format="%.1f")
                }
            )

        with c_right:
            st.markdown("### 💡 话术质量 vs 转化结果")
            plot_df = plot_df_vis.copy() # 使用处理过可视化的数据
            plot_df['转化率%'] = plot_df['线索到店率_数值'] * 100
            
            fig = px.scatter(
                plot_df, 
                x="S_Time", 
                y="转化率%", 
                size="线索量", 
                color="质检总分_显示",
                hover_name="名称",
                labels={"S_Time": "明确到店时间得分", "转化率%": "线索到店率(%)"},
                color_continuous_scale="Reds", 
                height=400
            )

            fig.update_traces(
                customdata=np.stack((
                    plot_df['线索量'], 
                    plot_df['线索到店率_数值'], 
                    plot_df['质检总分'].fillna(0), 
                    plot_df['S_Time'].fillna(0)
                ), axis=-1),
                
                hovertemplate=(
                    "<b>%{hovertext}</b><br><br>" +
                    "线索量: %{customdata[0]:,}<br>" +
                    "线索到店率: %{customdata[1]:.1%}<br>" +
                    "质检总分: %{customdata[2]:.1f}<br>" +
                    "明确到店时间得分: %{customdata[3]:.1f}" +
                    "<extra></extra>"
                )
            )

            if not plot_df.empty:
                # 均值线也要忽略 NaN
                fig.add_vline(x=plot_df['S_Time'].mean(), line_dash="dash", line_color="gray")
                fig.add_hline(y=kpi_rate * 100, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        with st.container():
            st.markdown("### 🕵️‍♀️ 邀约专员/管家深度诊断")
            if selected_store == "全部":
                st.info("💡 请先在右上方选择具体【门店】，查看该门店下的顾问详细诊断。")
            else:
                diag_list = sorted(current_df['邀约专员/管家'].unique())
                if len(diag_list) > 0:
                    selected_person = st.selectbox("🔍 选择该店邀约专员/管家：", diag_list)
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
                        st.metric("线索到店率", p['线索到店率']) 
                        st.caption(f"平均通话时长: {p['通话时长']:.1f} 秒")

                    with d2:
                        st.caption("质检得分详情 (QUALITY)")
                        # 处理 NaN，防止报错
                        def get_score(val):
                            return 0 if pd.isna(val) else val

                        metrics = {
                            "明确到店时间": get_score(p['S_Time']), 
                            "60秒通话占比": get_score(p['S_60s']),
                            "用车需求": get_score(p['S_Needs']), 
                            "车型信息介绍": get_score(p['S_Car']), 
                            "政策相关话术": get_score(p['S_Policy']), 
                            "添加微信": get_score(p['S_Wechat'])
                        }
                        for k, v in metrics.items():
                            c_a, c_b = st.columns([3, 1])
                            c_a.progress(min(v/100, 1.0))
                            c_b.write(f"{v:.1f}")
                            st.caption(k)

                    with d3:
                        with st.container():
                            st.error("🤖 诊断建议")
                            issues = []
                            # 只有当质检分不是 NaN 时才诊断，否则可能是未考核
                            if not pd.isna(p['S_Time']) and p['S_Time'] < 60:
                                st.markdown(f"🔴 **明确到店 (得分{p['S_Time']:.1f})**\n建议使用二选一法锁定时间。")
                                issues.append(1)
                            if not pd.isna(p['S_60s']) and p['S_60s'] < 60:
                                st.markdown(f"🟠 **60秒占比 (得分{p['S_60s']:.1f})**\n开场白需抛出利益点。")
                                issues.append(1)
                            if not pd.isna(p['S_Wechat']) and p['S_Wechat'] < 80:
                                st.markdown(f"🟠 **添加微信 (得分{p['S_Wechat']:.1f})**\n建议以发定位为由加微。")
                                issues.append(1)
                            if not issues: st.success("各项指标表现优秀！")
                else:
                    st.warning("该门店下暂无数据。")
else:
    st.info("👋 欢迎使用 Audi 效能看板！")
    st.warning("👉 目前暂无数据。请在左侧侧边栏展开【更新数据】，输入管理员密码并上传文件。")
