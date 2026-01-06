import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ================= 1. 网站基础设置 =================
st.set_page_config(page_title="Audi DCC 智能诊断看板", layout="wide", page_icon="🚘")

# 注入 CSS 样式 (奥迪红风格)
st.markdown("""
<style>
    .metric-card { background-color: #f9f9f9; border-left: 5px solid #bb0a30; padding: 15px; margin-bottom: 10px; }
    h1, h2, h3 { color: #333; }
    .stAlert { border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

st.title("🚘 Audi DCC | 效能质检智能看板")
st.markdown("---")

# ================= 2. 侧边栏：文件上传 =================
with st.sidebar:
    st.header("📂 第一步：上传数据")
    st.info("请上传对应的三个表格（支持 Excel 或 CSV）")
    
    # 针对您三个具体文件的上传口
    file_funnel = st.file_uploader("1. 上传【漏斗指标】(结果数据)", type=["xlsx", "csv"])
    file_dcc = st.file_uploader("2. 上传【管家排名】(质量数据)", type=["xlsx", "csv"])
    file_ams = st.file_uploader("3. 上传【AMS跟进】(执行数据)", type=["xlsx", "csv"])

# ================= 3. 智能列名辅助函数 =================
def find_column(df, keywords):
    """在dataframe中尝试自动寻找包含关键词的列名"""
    for col in df.columns:
        for key in keywords:
            if key in col:
                return col
    return None

def config_columns(df, label_name, key_prefix):
    """生成下拉菜单让用户确认列名"""
    st.write(f"🔧 **配置 {label_name} 的列名：**")
    cols = df.columns.tolist()
    
    # 自动猜测默认值
    default_name = find_column(df, ['顾问', '姓名', '管家', '销售'])
    default_idx = cols.index(default_name) if default_name in cols else 0
    
    # 让用户选择
    user_choice = st.selectbox(
        f"请选择 {label_name} 中的【姓名/顾问】列:", 
        cols, 
        index=default_idx,
        key=f"{key_prefix}_name"
    )
    return user_choice

# ================= 4. 主程序逻辑 =================

if file_funnel and file_dcc and file_ams:
    try:
        # 读取文件 (兼容 Excel 和 CSV)
        df_f = pd.read_csv(file_funnel) if file_funnel.name.endswith('csv') else pd.read_excel(file_funnel)
        df_d = pd.read_csv(file_dcc) if file_dcc.name.endswith('csv') else pd.read_excel(file_dcc)
        df_a = pd.read_csv(file_ams) if file_ams.name.endswith('csv') else pd.read_excel(file_ams)

        # --- 列名配置区 (折叠) ---
        with st.expander("⚙️ 点击展开：如果数据对不上，请在这里手动调整列名", expanded=True):
            c1, c2, c3 = st.columns(3)
            
            # 1. 配置漏斗表
            with c1:
                col_name_f = config_columns(df_f, "漏斗表", "funnel")
                # 尝试自动找线索和到店
                def_leads = find_column(df_f, ['线索', '总数'])
                def_visit = find_column(df_f, ['到店', '进店'])
                
                col_leads = st.selectbox("【线索量】是哪一列?", df_f.columns, index=df_f.columns.get_loc(def_leads) if def_leads else 0)
                col_visit = st.selectbox("【到店量】是哪一列?", df_f.columns, index=df_f.columns.get_loc(def_visit) if def_visit else 0)

            # 2. 配置管家表
            with c2:
                col_name_d = config_columns(df_d, "管家表", "dcc")
                # 尝试自动找分数
                def_score = find_column(df_d, ['质检', '总分'])
                def_time = find_column(df_d, ['明确到店', '时间'])
                def_wechat = find_column(df_d, ['微信', '加微'])
                
                col_score = st.selectbox("【质检总分】是哪一列?", df_d.columns, index=df_d.columns.get_loc(def_score) if def_score else 0)
                col_time_score = st.selectbox("【明确到店时间得分】?", df_d.columns, index=df_d.columns.get_loc(def_time) if def_time else 0)
                col_wechat_score = st.selectbox("【加微信得分】?", df_d.columns, index=df_d.columns.get_loc(def_wechat) if def_wechat else 0)

            # 3. 配置AMS表
            with c3:
                col_name_a = config_columns(df_a, "AMS表", "ams")
                def_duration = find_column(df_a, ['时长', '通话'])
                col_duration = st.selectbox("【通话时长】是哪一列?", df_a.columns, index=df_a.columns.get_loc(def_duration) if def_duration else 0)

        # --- 数据合并与清洗 ---
        # 统一列名为 'Name'
        df_f = df_f.rename(columns={col_name_f: 'Name'})
        df_d = df_d.rename(columns={col_name_d: 'Name'})
        df_a = df_a.rename(columns={col_name_a: 'Name'})

        # 合并表格 (Inner Join)
        merged = pd.merge(df_f, df_d, on='Name', how='inner')
        merged = pd.merge(merged, df_a, on='Name', how='inner')

        # 计算转化率
        merged['转化率'] = (merged[col_visit] / merged[col_leads] * 100).fillna(0).round(2)

        st.success(f"✅ 数据融合成功！共匹配到 {len(merged)} 位顾问的数据。")
        st.markdown("---")

        # --- 核心交互区 ---
        # 选择顾问
        advisors = merged['Name'].unique().tolist()
        selected_advisor = st.selectbox("🔍 请选择要诊断的顾问：", advisors)
        
        # 获取该顾问数据
        p = merged[merged['Name'] == selected_advisor].iloc[0]

        # 1. 顶部 KPI 卡片
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("线索跟进量", int(p[col_leads]))
        k2.metric("实际到店量", int(p[col_visit]))
        k3.metric("到店转化率", f"{p['转化率']}%")
        k4.metric("质检总分", p[col_score])

        # 2. 图表与诊断
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("📊 转化漏斗")
            # 简单的条形图模拟漏斗
            funnel_data = pd.DataFrame({
                '阶段': ['线索量', '到店量'],
                '数量': [p[col_leads], p[col_visit]]
            })
            fig = px.bar(funnel_data, x='阶段', y='数量', text='数量', color='阶段',
                         color_discrete_sequence=['#bfbfbf', '#bb0a30'])
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.subheader("🤖 AI 智能诊断建议")
            
            # --- 规则引擎 (基于 PDF 逻辑) ---
            
            # 规则 1：明确到店时间 (致命短板)
            val_time = p[col_time_score]
            if val_time < 50:
                st.error(f"🔴 **致命短板：明确到店时间 (得分 {val_time})**")
                st.markdown("> **问题：** 未引导客户确认具体到店时间。\n> **建议：** 采用二选一法则：“您是周六上午方便，还是下午方便？”")
            elif val_time < 80:
                st.warning(f"🟡 **待提升：明确到店时间 (得分 {val_time})**")
            else:
                st.success(f"🟢 **表现优秀：明确到店时间 (得分 {val_time})**")

            # 规则 2：加微信 (重点提升)
            val_wechat = p[col_wechat_score]
            if val_wechat < 60:
                st.warning(f"🟠 **加微信动作缺失 (得分 {val_wechat})**")
                st.markdown("> **建议：** 通话结束前必须尝试添加微信，便于后续发送车型资料和定位。")
            else:
                st.success(f"🟢 **微信添加率达标 (得分 {val_wechat})**")

            # 规则 3：通话时长
            val_dur = p[col_duration]
            if val_dur < 45:
                st.info(f"🔵 **通话时长偏短 ({val_dur}秒)**")
                st.markdown("> **注意：** 需检查开场白是否缺乏吸引力，导致客户过早挂断。")

    except Exception as e:
        st.error(f"❌ 发生错误：{e}")
        st.caption("通常是因为列名选择不正确，请在上方展开配置栏，手动选择正确的列名。")

else:
    st.info("👈 请在左侧侧边栏上传您的三个表格文件")