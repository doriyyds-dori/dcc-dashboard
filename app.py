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

# ================= 3. 智能读取与清洗 =================
def smart_read(file):
    try:
        if file.name.endswith('.csv'):
            return pd.read_csv(file)
        else:
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"读取失败: {e}")
        return None

def process_data(f_file, d_file, a_file):
    try:
        # 1. 读取原始文件
        raw_f = smart_read(f_file)
        raw_d = smart_read(d_file)
        raw_a = smart_read(a_file)

        if raw_f is None or raw_d is None or raw_a is None:
            return None, None

        # --- A. 处理漏斗表 (区分 门店小计行 和 个人行) ---
        # 识别列：假设第1列是门店(代理商)，第2列是管家(顾问)
        # 根据您的CSV snippet: 代理商, 管家, 线上_线索数...
        
        # 寻找关键列名
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), raw_f.columns[0])
        name_col = next((c for c in raw_f.columns if '管家' in str(c) or '顾问' in str(c)), raw_f.columns[1])
        
        # 重命名标准列
        df_f = raw_f.rename(columns={
            store_col: '门店名称',
            name_col: '邀约专员/管家',
            '线上_有效线索数': '线索量',
            '线上_到店数': '到店量'
        })
        
        # 容错处理：如果没有直接找到线索列
        if '线索量' not in df_f.columns:
             lead_col = next((c for c in raw_f.columns if '线索' in str(c) and '有效' in str(c)), None)
             if lead_col: df_f = df_f.rename(columns={lead_col: '线索量'})

        # 确保数值转换
        for c in ['线索量', '到店量']:
            if c in df_f.columns:
                df_f[c] = pd.to_numeric(df_f[c], errors='coerce').fillna(0)

        # 拆分数据：
        # 1. 门店级数据 (管家名为 '小计' 的行)
        df_store_level = df_f[df_f['邀约专员/管家'].str.contains('小计', na=False)].copy()
        
        # 2. 顾问级数据 (管家名 不是 '小计' 且 不是 '总计' 的行)
        df_advisor_level = df_f[~df_f['邀约专员/管家'].str.contains('计', na=False)].copy()

        # --- B. 处理 DCC 表 (提取分数) ---
        wechat_col = '添加微信.1' if '添加微信.1' in raw_d.columns else '添加微信'
        df_d = raw_d.rename(columns={
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', 
            '车型信息': 'S_Car', '政策相关': 'S_Policy',
            '明确到店时间': 'S_Time'
        })
        df_d['S_Wechat'] = raw_d[wechat_col]
        # 只保留需要的列
        df_d = df_d[['邀约专员/管家', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']]

        # --- C. 处理 AMS 表 (提取时长) ---
        df_a = raw_a.rename(columns={'管家姓名': '邀约专员/管家', 'DCC平均通话时长': '通话时长'})
        df_a = df_a[['邀约专员/管家', '通话时长']]

        # --- D. 统一去空格 ---
        for df in [df_store_level, df_advisor_level, df_d, df_a]:
            if '邀约专员/管家' in df.columns:
                df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
            if '门店名称' in df.columns:
                df['门店名称'] = df['门店名称'].astype(str).str.strip()

        # --- E. 合并顾问级数据 (用于具体门店视图 & 散点图) ---
        # 顾问级 = 漏斗(个人) + DCC + AMS
        merged_advisor = pd.merge(df_advisor_level, df_d, on='邀约专员/管家', how='inner')
        merged_advisor = pd.merge(merged_advisor, df_a, on='邀约专员/管家', how='inner')
        
        # 计算个人的线索到店率
        merged_advisor['线索到店率'] = (merged_advisor['到店量'] / merged_advisor['线索量']).replace([np.inf, -np.inf], 0).fillna(0)

        # --- F. 合并门店级数据 (用于全部视图) ---
        # 门店级基础数据来自 df_store_level (准确的线索/到店)
        # 门店级质检分需要从 merged_advisor 聚合而来 (因为DCC表通常没有门店行)
        
        # 1. 计算各门店的平均质检分
        store_scores = merged_advisor.groupby('门店名称')[['质检总分', 'S_Time']].mean().reset_index()
        
        # 2. 将平均分合并回门店准确数据表
        merged_store = pd.merge(df_store_level, store_scores, on='门店名称', how='left')
        
        # 计算门店的线索到店率 (直接用表里的数据计算，最准)
        merged_store['线索到店率'] = (merged_store['到店量'] / merged_store['线索量']).replace([np.inf, -np.inf], 0).fillna(0)
        
        return merged_advisor, merged_store
        
    except Exception as e:
        st.error(f"数据处理出错: {e}")
        return None, None

# ================= 4. 界面渲染 =================

if file_f and file_d and file_a:
    # 获取两份数据：advisors(个人), stores(门店)
    df_advisors, df_stores = process_data(file_f, file_d, file_a)
    
    if df_advisors is not None and not df_advisors.empty:
        
        # --- 侧边栏：切片器 (Slicer) ---
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 门店筛选")
        
        # 从门店表中获取列表
        if df_stores is not None and not df_stores.empty:
            all_store_names = sorted(list(df_stores['门店名称'].unique()))
        else:
            # 备用方案：如果没匹配到小计行，就从个人表里取
            all_store_names = sorted(list(df_advisors['门店名称'].unique()))
            
        store_options = ["全部"] + all_store_names
        selected_store = st.sidebar.selectbox("选择门店：", store_options)
        
        # --- 逻辑分支 ---
        if selected_store == "全部":
            # === 模式 A：全区视图 (看门店排名) ===
            current_df = df_stores
            display_name_col = '门店名称'
            rank_title = "🏦 全区门店排名 (基于漏斗表小计数据)"
            
            # KPI 计算 (基于门店汇总表求和，更准)
            total_leads = int(df_stores['线索量'].sum())
            total_visits = int(df_stores['到店量'].sum())
            if total_leads > 0:
                avg_rate = total_visits / total_leads
            else:
                avg_rate = 0.0
            avg_score = df_advisors['质检总分'].mean() # 全区平均分还是得算所有人的平均
            
        else:
            # === 模式 B：单店视图 (看该店人员排名) ===
            # 筛选该门店下的顾问
            current_df = df_advisors[df_advisors['门店名称'] == selected_store]
            display_name_col = '邀约专员/管家'
            rank_title = f"👤 {selected_store} - 顾问排名"
            
            # KPI 计算 (基于该店人员汇总)
            total_leads = int(current_df['线索量'].sum())
            total_visits = int(current_df['到店量'].sum())
            if total_leads > 0:
                avg_rate = total_visits / total_leads
            else:
                avg_rate = 0.0
            avg_score = current_df['质检总分'].mean()

        # --- 顶部 KPI ---
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{total_leads:,}")
        k2.metric("总实际到店", f"{total_visits:,}")
        k3.metric("线索到店率", f"{avg_rate:.1%}")
        k4.metric("平均质检总分", f"{avg_score:.1f}")
        
        st.markdown("---")

        # --- 排名与散点图 ---
        c_left, c_right = st.columns([1, 2])
        
        with c_left:
            st.markdown(f"### {rank_title}")
            
            # 准备排名数据
            rank_show = current_df[[display_name_col, '线索到店率', '质检总分']].sort_values('线索到店率', ascending=False).head(15)
            
            # 展示表格
            st.dataframe(
                rank_show,
                hide_index=True,
                use_container_width=True,
                height=400,
                column_config={
                    display_name_col: st.column_config.TextColumn("名称"),
                    "线索到店率": st.column_config.ProgressColumn(
                        "线索到店率",
                        format="%.1f%%",
                        min_value=0,
                        max_value=0.15, # 调整最大值以适应普遍较低的转化率，让进度条更明显
                    ),
                    "质检总分": st.column_config.NumberColumn(
                        "质检总分",
                        format="%.1f"
                    )
                }
            )

        with c_right:
            st.markdown("### 💡 话术质量 vs 转化结果")
            if selected_store == "全部":
                st.info("👈 左侧显示各门店数据。选择具体门店后，此处将显示该店人员的详细散点分析。")
                # 全部模式下，也可以画一个门店级的散点图
                plot_df = current_df.copy()
                plot_df['转化率_百分比'] = plot_df['线索到店率'] * 100
                fig = px.scatter(
                    plot_df, x="S_Time", y="转化率_百分比", # S_Time 是门店平均分
                    size="线索量", color="质检总分",
                    hover_name=display_name_col,
                    text=display_name_col, # 显示门店名
                    labels={"S_Time": "门店明确到店平均分", "转化率_百分比": "门店线索到店率(%)"},
                    color_continuous_scale="Reds",
                    height=400
                )
            else:
                # 单店模式：画人员散点图
                plot_df = current_df.copy()
                plot_df['转化率_百分比'] = plot_df['线索到店率'] * 100
                fig = px.scatter(
                    plot_df, x="S_Time", y="转化率_百分比",
                    size="线索量", color="质检总分",
                    hover_name=display_name_col,
                    labels={"S_Time": "个人明确到店得分", "转化率_百分比": "个人转化率(%)"},
                    color_continuous_scale="Reds",
                    height=400
                )
            
            # 添加辅助线
            if not plot_df.empty:
                fig.add_vline(x=plot_df['S_Time'].mean(), line_dash="dash", line_color="gray")
                fig.add_hline(y=avg_rate * 100, line_dash="dash", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)

        # --- 底部诊断 (级联筛选核心) ---
        st.markdown("---")
        with st.container():
            st.markdown("### 🕵️‍♀️ 管家深度诊断")
            
            # 逻辑升级：
            # 1. 这里的名单必须是 df_advisors (因为诊断是针对人的，不是针对门店的)
            # 2. 如果选了“全部”，是否显示所有人？建议显示，或者提示先选门店。
            # 3. 如果选了“某门店”，只显示该门店的人。
            
            if selected_store == "全部":
                diag_advisors = sorted(df_advisors['邀约专员/管家'].unique())
                st.info("当前为全区视图。您可以在下方搜索全区任何一位顾问，或在左侧筛选具体门店以缩小范围。")
            else:
                # 只筛选当前门店的人
                diag_advisors = sorted(current_df['邀约专员/管家'].unique())
            
            if len(diag_advisors) > 0:
                selected_advisor_name = st.selectbox("🔍 选择/搜索顾问姓名：", diag_advisors)
                
                # 锁定该顾问的数据行
                p = df_advisors[df_advisors['邀约专员/管家'] == selected_advisor_name].iloc[0]
                
                # 开始渲染三栏
                d1, d2, d3 = st.columns([1, 1, 1.2])
                
                with d1:
                    st.caption(f"所属门店：{p['门店名称']}")
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
                st.warning("该范围内暂无顾问数据。")

    else:
        st.warning("数据解析失败，请检查文件格式。")
else:
    st.info("👈 请在左侧上传三个文件")
