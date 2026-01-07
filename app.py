import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="数据体检模式", layout="wide", page_icon="🩺")

# 基础配置
DATA_DIR = "data_store"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)
PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")
PATH_S = os.path.join(DATA_DIR, "store_rank.csv")

st.title("🩺 数据文件深度体检")
st.info("此模式用于检查文件是否被正确读取，以及列名是否正确。")

def check_file(path, name):
    st.markdown(f"### 📂 检查文件：{name}")
    
    if not os.path.exists(path):
        st.error(f"❌ 文件缺失：{path}")
        return
    
    try:
        # 尝试读取，兼容 Excel 和 CSV
        if path.endswith(".csv"):
            # 尝试多种编码
            try:
                df = pd.read_csv(path, encoding='utf-8')
            except:
                df = pd.read_csv(path, encoding='gbk')
        else:
            df = pd.read_excel(path)
            
        st.success(f"✅ 读取成功！包含 {len(df)} 行数据")
        
        # 展示前3行
        st.dataframe(df.head(3), use_container_width=True)
        
        # 打印列名
        columns = list(df.columns)
        st.write("📋 **识别到的列名列表：**")
        st.code(columns)
        
        # 智能诊断
        check_columns(name, columns)
        
    except Exception as e:
        st.error(f"❌ 读取报错：{e}")

def check_columns(name, cols):
    # 转换为字符串并去空格，防止肉眼看不见的空格
    cols = [str(c).strip() for c in cols]
    
    missing = []
    if name == "1. 漏斗表":
        required = ['门店名称', '邀约专员/管家', '线索量', '到店量']
        # 模糊匹配检查
        if not any('门店' in c or '代理' in c for c in cols): missing.append("门店名称")
        if not any('顾问' in c or '管家' in c for c in cols): missing.append("邀约专员/管家")
        
    elif name == "2. 顾问质检表":
        required = ['质检总分']
        if not any('质检总分' in c for c in cols): missing.append("质检总分")
        
    elif name == "4. 门店排名表":
        if '门店名称' not in cols: 
            # 检查是不是在第二行
            st.warning("⚠️ 警告：未找到【门店名称】列。这可能是因为表头在第2行。")
            st.markdown("**建议：** 请查看上方表格预览，如果第一行是空的或乱码，说明表头确实需要跳过。")
            return

    if missing:
        st.error(f"❌ 关键列缺失警告：我们没找到 {missing} 这些列。")
    else:
        st.caption("✔️ 关键列检测通过")

# --- 主界面 ---

st.sidebar.header("文件状态")
files = {
    "1. 漏斗表": PATH_F,
    "2. 顾问质检表": PATH_D,
    "3. AMS表": PATH_A,
    "4. 门店排名表": PATH_S
}

all_exist = True
for name, path in files.items():
    if os.path.exists(path):
        st.sidebar.success(f"{name}: 已上传")
    else:
        st.sidebar.error(f"{name}: 未找到")
        all_exist = False

if not all_exist:
    st.sidebar.warning("请先上传缺失的文件！")

# 渲染检查区域
col1, col2 = st.columns(2)
with col1:
    check_file(PATH_F, "1. 漏斗表")
    check_file(PATH_D, "2. 顾问质检表")
with col2:
    check_file(PATH_A, "3. AMS表")
    check_file(PATH_S, "4. 门店排名表")

# 上传区
with st.sidebar.expander("⬆️ 重新上传文件", expanded=True):
    with st.form("upload_form"):
        f1 = st.file_uploader("漏斗表", type=['xlsx', 'csv'])
        f2 = st.file_uploader("顾问质检表", type=['xlsx', 'csv'])
        f3 = st.file_uploader("AMS表", type=['xlsx', 'csv'])
        f4 = st.file_uploader("门店排名表", type=['xlsx', 'csv'])
        if st.form_submit_button("确认更新"):
            if f1: 
                with open(PATH_F, "wb") as f: f.write(f1.getbuffer())
            if f2: 
                with open(PATH_D, "wb") as f: f.write(f2.getbuffer())
            if f3: 
                with open(PATH_A, "wb") as f: f.write(f3.getbuffer())
            if f4: 
                with open(PATH_S, "wb") as f: f.write(f4.getbuffer())
            st.success("上传完成，页面即将刷新...")
            st.rerun()
