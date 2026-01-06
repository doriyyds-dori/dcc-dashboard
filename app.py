import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown("""
<style>
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    .big-font {font-size: 18px !important; font-weight: bold;}
    /* 优化提交按钮样式 */
    div[data-testid="stFormSubmitButton"] button {
        width: 100%;
        background-color: #bb0a30;
        color: white;
        border: none;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ================= 2. 安全锁与文件存储 =================
ADMIN_PASSWORD = "AudiSARR3" 

DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")      # 1. 漏斗
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")         # 2. 顾问质检
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")         # 3. AMS
PATH_S = os.path.join(DATA_DIR, "store_rank.csv")   # 4. 门店排名

def save_uploaded_file(uploaded_file, save_path):
    # 强制覆盖保存
    with open(save_path, "wb") as f: f.write(uploaded_file.getbuffer())
    return True

# ================= 3. 侧边栏逻辑 (使用 Form 解决点击无反应问题) =================
with st.sidebar:
    st.header("⚙️ 管理面板")
    has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and os.path.exists(PATH_S)
    
    if has_data: st.success("✅ 数据状态：已就绪")
    else: st.warning("⚠️ 暂无数据")
    st.markdown("---")
    
    with st.expander("🔐 更新数据 (仅限管理员)", expanded=True):
        pwd = st.text_input("输入管理员密码", type="password")
        
        if pwd == ADMIN_PASSWORD:
            st.info("🔓 身份验证通过，请上传数据：")
            
            # --- 使用 st.form 确保提交稳定 ---
            with st.form("data_update_form", clear_on_submit=False):
                st.markdown("##### 必须上传所有 4 个文件：")
                new_f = st.file_uploader("1. 漏斗指标表", type=["xlsx", "csv"])
                new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"])
                new_a = st.file_uploader("3. AMS跟进表", type=["xlsx", "csv"])
                new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"]) 
                
                # 提交按钮
                submitted = st.form_submit_button("🚀 确认并更新数据")
                
                if submitted:
                    if new_f and new_d and new_a and new_s:
                        with st.spinner("正在保存文件并处理..."):
                            save_uploaded_file(new_f, PATH_F)
                            save_uploaded_file(new_d, PATH_D)
                            save_uploaded_file(new_a, PATH_A)
                            save_uploaded_file(new_s, PATH_S)
                        
                        st.success("✅ 数据更新成功！页面即将刷新...")
                        st.rerun()
                    else:
                        st.error("❌ 更新失败：请确保 4 个文件全部都已上传。")
        elif pwd:
            st.error("密码错误")

# ================= 4. 数据处理逻辑 (增强容错) =================
def smart_read(file_path, is_rank_file=False):
    """智能读取，支持csv/xlsx，针对排名表支持跳过首行"""
    try:
        if isinstance(file_path, str):
            is_csv = file_path.endswith('.csv') or file_path.endswith('.txt')
        else:
            is_csv = file_path.name.endswith('.csv') or file_path.name.endswith('.txt')
            
        if is_csv:
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
            
        # 针对门店排名表的特殊处理 (检测是否包含 metadata 头)
        if is_rank_file:
            # 定义我们在找的关键列
            target_cols = ['门店名称', '质检总分', '排名']
            # 如果第一行表头里没找到这些列，尝试读第二行作为表头
            if not any(col in df.columns for col in target_cols):
                if is_csv: df = pd.read_csv(file_path, header=1)
                else: df = pd.read_excel(file_path, header=1)
        return df
    except Exception as e:
        print(f"读取文件失败: {file_path}, 错误: {e}")
        return None

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

def process_data(path_f, path_d, path_a, path_s):
    try:
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        raw_s = smart_read(path_s, is_rank_file=True)
        
        # 只要有一个文件没读出来，就返回 None
        if raw_f is None or raw_d is None or raw_a is None or raw_s is None: 
            return None, None

        # ================= A. Funnel (漏斗) =================
        # 模糊匹配列名，增加鲁棒性
        store_col = next((c for c in raw_f.columns if '代理商' in str(c) or '门店' in str(c)), raw_f.columns[0])
        name_col = next((c for c in raw_f.columns if '管家' in str(c) or '顾问' in str(c)), raw_f.columns[1])
        col_leads = '线上_有效线索数' if '线上_有效线索数' in raw_f.columns else '线索量'
        col_visits = '线上_到店数' if '线上_到店数' in raw_f.columns else '到店量'
        col_excel_rate = next((c for c in raw_f.columns if '率' in str(c) and ('到店' in str(c) or '有效' in str(c))), None)

        rename_dict = {store_col: '门店名称', name_col: '邀约专员/管家', col_leads: '线索量', col_visits: '到店量'}
        if col_excel_rate: rename_dict[col_excel_rate] = 'Excel_Rate'
        
        df_f = raw_f.rename(columns=rename_dict)
        # 区分门店行和顾问行
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

        # ================= B. DCC (顾问质检) =================
        wechat_col = '添加微信.1' if '添加微信.1' in raw_d.columns else '添加微信'
        df_d = raw_d.rename(columns={
            '顾问名称': '邀约专员/管家', '质检总分': '质检总分',
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        })
        # 兼容处理
        if wechat_col in raw_d.columns:
            df_d['S_Wechat'] = raw_d[wechat_col]
        else:
            df_d['S_Wechat'] = 0
        
        score_cols = ['质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']
        for c in score_cols:
            if c in df_d.columns:
                df_d[c] = pd.to_numeric(df_d[c], errors='coerce') 
        
        # 只取存在的列
        existing_cols = [c for c in (['邀约专员/管家'] + score_cols) if c in df_d.columns]
        df_d = df_d[existing_cols]

        # ================= C. Store Scores (门店质检 - 直接读取文件4) =================
        df_s = raw_s.rename(columns={
            '60秒通话': 'S_60s', '用车需求': 'S_Needs', '车型信息': 'S_Car', 
            '政策相关': 'S_Policy', '明确到店时间': 'S_Time'
        })
        s_wechat_col = '添加微信.1' if '添加微信.1' in raw_s.columns else '添加微信'
        if s_wechat_col in raw_s.columns:
            df_s['S_Wechat'] = raw_s[s_wechat_col]
        else:
            df_s['S_Wechat'] = 0
        
        store_score_cols = ['门店名称', '质检总分', 'S_60s', 'S_Needs', 'S_Car', 'S_Policy', 'S_Wechat', 'S_Time']
        available_store_cols = [c for c in store_score_cols if c in df_s.columns]
        df_s = df_s[available_store_cols]
        for c in available_store_cols:
            if c != '门店名称':
                df_s[c] = pd.to_numeric(df_s[c], errors='coerce')

        # ================= D. AMS (跟进数据) =================
        # 模糊匹配 AMS 列名
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
        # 仅保留存在的列
        final_ams_cols = [c for c in final_ams_cols if c in df_a.columns]
        df_a = df_a[final_ams_cols]

        # ================= E. Merge =================
        # 清理空格
        for df in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
            if '邀约专员/管家' in df.columns: df['邀约专员/管家'] = df['邀约专员/管家'].astype(str).str.strip()
            if '门店名称' in df.columns: df['门店名称'] = df['门店名称'].astype(str).str.strip()

        # 1. 顾问全量表
        full_advisors = pd.merge(df_advisor_data, df_d, on='邀约专员/管家', how='left')
        full_advisors = pd.merge(full_advisors, df_a, on='邀约专员/管家', how='left')
        
        cols_to_fill_zero = ['线索量', '到店量', '通话时长'] + all_ams_calc_cols
        # 只填充存在的列
        cols_to_fill_zero = [c for c in cols_to_fill_zero if c in full_advisors.columns]
        full_advisors[cols_to_fill_zero] = full_advisors[cols_to_fill_zero].fillna(0)

        # 2. 门店全量表 (AMS 聚合 + 质检表读取)
        ams_agg_dict = {
            'conn_num': 'sum', 'conn_denom': 'sum',
            'timely_num': 'sum', 'timely_denom': 'sum',
            'call2_num': 'sum', 'call2_denom': 'sum',
            'call3_num': 'sum', 'call3_denom': 'sum'
        }
        # 确保聚合列存在
        valid_agg = {k:v for k,v in ams_agg_dict.items() if k in full_advisors.columns}
        
        store_ams = full_advisors.groupby('门店名称').agg(valid_agg).reset_index()
        
        store_ams['外呼接通率'] = safe_div(store_ams, 'conn_num', 'conn_denom')
        store_ams['DCC及时处理率'] = safe_div(store_ams, 'timely_num', 'timely_denom')
        store_ams['DCC二次外呼率'] = safe_div(store_ams, 'call2_num', 'call2_denom')
        store_ams['DCC三次外呼率'] = safe_div(store_ams, 'call3_num', 'call3_denom')

        full_stores = pd.merge(df_store_data, df_s, on='门店名称', how='left')
        full_stores = pd.merge(full_stores, store_ams, on='门店名称', how='left')
        
        return full_advisors, full_stores

    except Exception as e:
        # 这个 error 会在下面界面中被捕获并打印
        print(f"Process Error: {e}")
        return None, None

# ================= 5. 界面渲染 (带调试诊断) =================
if has_data:
    # 增加 loading 提示
    with st.spinner("正在读取并处理数据..."):
        df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, PATH_S)
    
    # --- 失败诊断块 ---
    if df_advisors is None:
        st.error("❌ 数据处理失败！请检查下方诊断信息：")
        st.markdown("### 🔍 原始文件诊断报告")
        
        st.write("---")
        st.write("📂 **1. 门店排名表 (Raw Data Preview)**")
        try:
            raw_s = smart_read(PATH_S, is_rank_file=True)
            if raw_s is not None:
                st.dataframe(raw_s.head(3))
                st.write("**检测到的列名:**", list(raw_s.columns))
                if '门店名称' not in raw_s.columns:
                    st.error("⚠️ 错误：在排名表中找不到【门店名称】列。请检查表头是否正确。")
            else:
                st.error("无法读取排名表文件。")
        except Exception as e:
            st.error(f"读取异常: {e}")

        st.write("---")
        st.write("📂 **2. 漏斗表 (Raw Data Preview)**")
        try:
            raw_f = smart_read(PATH_F)
            if raw_f is not None:
                st.dataframe(raw_f.head(3))
            else: st.error("无法读取漏斗表。")
        except: pass
        
        st.warning("请根据上述表头信息，调整您的Excel文件列名，或者重新上传。")

    else:
        # --- 数据正常，渲染看板 ---
        
        col_header, col_filter = st.columns([3, 1])
        with col_header: st.title("Audi | DCC 效能看板")
        with col_filter:
            if not df_stores.empty: all_stores = sorted(list(df_stores['门店名称'].unique()))
            else: all_stores = sorted(list(df_advisors['门店名称'].unique()))
            store_options = ["全部"] + all_stores
            selected_store = st.selectbox("🏭 切换门店视图", store_options)

        # 准备当前视图数据
        if selected_store == "全部":
            current_df = df_stores.copy()
            current_df['名称'] = current_df['门店名称']
            rank_title = "🏆 全区门店排名"
            # KPI 计算
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            # 门店总分直接求平均
            kpi_score = current_df['质检总分'].mean() 
        else:
            current_df = df_advisors[df_advisors['门店名称'] == selected_store].copy()
            current_df['名称'] = current_df['邀约专员/管家']
            rank_title = f"👤 {selected_store} - 顾问排名"
            kpi_leads = current_df['线索量'].sum()
            kpi_visits = current_df['到店量'].sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df['质检总分'].mean()

        # 1. KPI Cards
        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")
        
        # 2. Process
        st.markdown("---")
        st.subheader("2️⃣ DCC 外呼过程监控 (Process)")
        
        p1, p2, p3, p4 = st.columns(4)
        def calc_kpi_rate(df, num, denom):
            if num not in df.columns or denom not in df.columns: return 0
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
        st.caption("注：以上为加权平均值")

        # 绘图数据准备
        plot_df_vis = current_df.copy()
        plot_df_vis['质检总分_显示'] = plot_df_vis['质检总分'].fillna(0) 

        c_proc_1, c_proc_2 = st.columns(2)
        with c_proc_1:
            st.markdown("#### 🕵️ 异常侦测：DCC外呼接通率 vs 60秒通话占比")
            st.info("💡 **分析逻辑：** 右下角（接通率高但60秒占比低）代表可能存在“人为压低时长/话术差”问题。")
            
            # 只有当列存在时才绘图
            if 'S_60s' in plot_df_vis.columns and '外呼接通率' in plot_df_vis.columns:
                fig_p1 = px.scatter(
                    plot_df_vis, x="外呼接通率", y="S_60s", size="线索量", color="质检总分_显示",
                    hover_name="名称", labels={"外呼接通率": "外呼接通率", "S_60s": "60秒通话占比得分"},
                    color_continuous_scale="RdYlGn", height=350
                )
                fig_p1.add_vline(x=avg_conn, line_dash="dash", line_color="gray")
                fig_p1.add_hline(y=plot_df_vis['S_60s'].mean(), line_dash="dash", line_color="gray")
                fig_p1.update_layout(xaxis=dict(tickformat=".0%"))
                st.plotly_chart(fig_p1, use_container_width=True)
            else:
                st.warning("⚠️ 缺少必要数据（60秒通话或接通率），无法绘制散点图。")

        with c_proc_2:
            st.markdown("#### 🔗 归因分析：过程指标 vs 线索首邀到店率")
            st.info("💡 **分析逻辑：** 监控外呼及时性与邀约到店率相关性。")
            x_axis_choice = st.radio("选择横轴指标：", ["DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"], horizontal=True)
            
            if x_axis_choice in plot_df_vis.columns:
                plot_df_corr = plot_df_vis.copy()
                plot_df_corr['转化率%'] = plot_df_corr['线索到店率_数值'] * 100
                fig_p2 = px.scatter(
                    plot_df_corr, x=x_axis_choice, y="转化率%", size="线索量", color="质检总分_显示",
                    hover_name="名称", labels={x_axis_choice: x_axis_choice, "转化率%": "线索到店率(%)"},
                    color_continuous_scale="Blues", height=300
                )
                fig_p2.update_layout(xaxis=dict(tickformat=".0%"))
                st.plotly_chart(fig_p2, use_container_width=True)
            else:
                st.warning(f"⚠️ 缺少 {x_axis_choice} 数据，无法绘图。")

        st.markdown("---")

        # 3. Rank Table
        c_left, c_right = st.columns([1, 2])
        with c_left:
            st.markdown(f"### 🏆 {rank_title}")
            rank_df = current_df[['名称', '线索到店率', '线索到店率_数值', '质检总分']].copy()
            rank_df['Sort_Score'] = rank_df['线索到店率_数值'].fillna(-1)
            rank_df = rank_df.sort_values('Sort_Score', ascending=False).head(15)
            display_df = rank_df[['名称', '线索到店率', '质检总分']]
            st.dataframe(
                display_df, hide_index=True, use_container_width=True, height=400,
                column_config={"名称": st.column_config.TextColumn("名称"), "线索到店率": st.column_config.TextColumn("线索到店率"), "质检总分": st.column_config.NumberColumn("质检总分", format="%.1f")}
            )

        with c_right:
            st.markdown("### 💡 话术质量 vs 转化结果")
            if 'S_Time' in plot_df_vis.columns:
                plot_df = plot_df_vis.copy()
                plot_df['转化率%'] = plot_df['线索到店率_数值'] * 100
                fig = px.scatter(
                    plot_df, x="S_Time", y="转化率%", size="线索量", color="质检总分_显示", hover_name="名称",
                    labels={"S_Time": "明确到店时间得分", "转化率%": "线索到店率(%)"}, color_continuous_scale="Reds", height=400
                )
                if not plot_df.empty:
                    fig.add_vline(x=plot_df['S_Time'].mean(), line_dash="dash", line_color="gray")
                    fig.add_hline(y=kpi_rate * 100, line_dash="dash", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("⚠️ 缺少“明确到店时间”数据，无法绘图")

        st.markdown("---")
        
        # 4. Diagnosis
        with st.container():
            st.markdown("### 🕵️‍♀️ 邀约专员/管家深度诊断")
            if selected_store == "全部":
                st.info("💡 请先在右上方选择具体【门店】，查看该门店下的顾问详细诊断。")
            else:
                diag_df = current_df[current_df['线索量'] > 0].copy()
                diag_list = sorted(diag_df['邀约专员/管家'].unique())
                
                if len(diag_list) > 0:
                    selected_person = st.selectbox("🔍 选择该店邀约专员/管家：", diag_list)
                    p = df_advisors[df_advisors['邀约专员/管家'] == selected_person].iloc[0]
                    
                    d1, d2, d3 = st.columns([1, 1, 1.2])
                    with d1:
                        st.caption("转化漏斗 (RESULT)")
                        fig_f = go.Figure(go.Funnel(
                            y = ["线索量", "到店量"], x = [p['线索量'], p['到店量']],
                            textinfo = "value+percent initial", marker = {"color": ["#d9d9d9", "#bb0a30"]}
                        ))
                        fig_f.update_layout(showlegend=False, height=180, margin=dict(t=0,b=0,l=0,r=0))
                        st.plotly_chart(fig_f, use_container_width=True)
                        st.metric("线索到店率", p['线索到店率']) 
                        st.caption(f"平均通话时长: {p['通话时长']:.1f} 秒")

                    has_score = not pd.isna(p['质检总分']) and 'S_Time' in p

                    with d2:
                        st.caption("质检得分详情 (QUALITY)")
                        if has_score:
                            metrics = {"明确到店时间": p.get('S_Time'), "60秒通话占比": p.get('S_60s'), "用车需求": p.get('S_Needs'), "车型信息介绍": p.get('S_Car'), "政策相关话术": p.get('S_Policy'), "添加微信": p.get('S_Wechat')}
                            for k, v in metrics.items():
                                c_a, c_b = st.columns([3, 1])
                                val = 0 if pd.isna(v) else v
                                c_a.progress(min(val/100, 1.0))
                                c_b.write(f"{val:.1f}")
                                st.caption(k)
                        else: st.warning("暂无质检数据")

                    with d3:
                        with st.container():
                            if has_score:
                                st.error("🤖 AI 智能诊断建议")
                                val_60s = 0 if pd.isna(p.get('S_60s')) else p.get('S_60s')
                                other_kpis = {
                                    "明确到店": (p.get('S_Time'), "建议使用二选一法锁定时间。"),
                                    "添加微信": (p.get('S_Wechat'), "建议以发定位为由加微。"),
                                    "用车需求": (p.get('S_Needs'), "需加强需求挖掘能力。"),
                                    "车型信息": (p.get('S_Car'), "需提升产品DCC话术熟练度。"),
                                    "政策相关": (p.get('S_Policy'), "需准确传达促销政策利益点。")
                                }
                                cleaned_others = {}
                                for k, (v, advice) in other_kpis.items():
                                    cleaned_others[k] = (0 if pd.isna(v) else v, advice)

                                issues_list = []
                                is_failing = False
                                
                                if val_60s < 60:
                                    issues_list.append(f"🟠 **60秒占比 (得分{val_60s:.1f})**\n开场白需抛出利益点。")
                                    is_failing = True
                                    
                                for k, (score, advice) in cleaned_others.items():
                                    if score < 80:
                                        issues_list.append(f"🔴 **{k} (得分{score:.1f})**\n{advice}")
                                        is_failing = True
                                        
                                if is_failing:
                                    for item in issues_list: st.markdown(item)
                                    st.warning("⚠️ 存在明显短板，请重点辅导。")
                                else:
                                    all_above_85 = all(score >= 85 for score, _ in cleaned_others.values())
                                    if all_above_85: st.success("🌟 **各项指标表现优秀！**")
                                    else: st.info("✅ **各项指标合格**\n目前表现稳定，但部分指标未达到85分卓越标准，仍有提升空间。")
                            else: st.info("暂无数据，无法生成诊断建议。")
                else: st.warning("该门店下暂无数据。")
else:
    st.info("👋 欢迎使用 Audi 效能看板！")
    st.warning("👉 目前暂无数据。请在左侧侧边栏展开【更新数据】，输入管理员密码并上传所有 **4** 个数据文件。")
