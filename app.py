import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
import traceback
from datetime import datetime

# --- Page Config ---
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

# --- CSS Styling ---
# 调整 selectbox 样式，使其在并排时更美观
st.markdown(
    """
    <style>
        .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
        .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
        /* 调整下拉框样式，防止过宽或过窄 */
        div[data-testid="stSelectbox"] {width: 100%;} 
        .big-font {font-size: 18px !important; font-weight: bold;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Constants & Config ---
ADMIN_PASSWORD = "AudiSARR3"
DATA_DIR = "data_store"
os.makedirs(DATA_DIR, exist_ok=True)

# Fixed filenames (Operational Data)
PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")
PATH_S_XLSX = os.path.join(DATA_DIR, "store_rank.xlsx")
PATH_S_CSV = os.path.join(DATA_DIR, "store_rank.csv")

# Fixed filenames (Master Data)
PATH_M = os.path.join(DATA_DIR, "store_mapping.xlsx")  # 代理商归属表

LAST_UPDATE_FILE = os.path.join(DATA_DIR, "_last_upload_time.txt")


# --- Helper Functions ---

def save_uploaded_file(uploaded_file, save_path: str) -> bool:
    try:
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return True
    except Exception as e:
        st.error(f"文件保存失败: {e}")
        return False


def get_store_rank_path():
    if os.path.exists(PATH_S_XLSX):
        return PATH_S_XLSX
    if os.path.exists(PATH_S_CSV):
        return PATH_S_CSV
    return None


def get_data_update_time(store_rank_path: str | None):
    """返回最新一次上传数据报的时间"""
    if os.path.exists(LAST_UPDATE_FILE):
        try:
            with open(LAST_UPDATE_FILE, "r", encoding="utf-8") as f:
                txt = f.read().strip()
            if txt:
                return datetime.fromisoformat(txt)
        except Exception:
            pass

    paths = [PATH_F, PATH_D, PATH_A]
    if store_rank_path:
        paths.append(store_rank_path)

    mtimes = []
    for p in paths:
        if p and os.path.exists(p):
            try:
                mtimes.append(os.path.getmtime(p))
            except Exception:
                pass

    if not mtimes:
        return None

    ts = max(mtimes)
    return datetime.fromtimestamp(ts)


def dedupe_columns(columns):
    """把重复列名变成: 列名, 列名__1, 列名__2"""
    seen = {}
    out = []
    for c in list(columns):
        c = str(c)
        if c not in seen:
            seen[c] = 0
            out.append(c)
        else:
            seen[c] += 1
            out.append(f"{c}__{seen[c]}")
    return out


def smart_read(file_path: str, is_rank_file: bool = False):
    """鲁棒读取（xlsx/csv/误后缀 xlsx）+ 自动找表头 + 列名去重"""
    if not file_path or not os.path.exists(file_path):
        return None

    df = None

    # 尝试直接读取 Excel
    try:
        with open(file_path, "rb") as f:
            sig = f.read(4)
        if sig == b"PK\x03\x04" or sig.startswith(b"PK"): # Excel signature check
            df = pd.read_excel(file_path, header=None)
    except Exception:
        pass

    if df is None:
        is_csv = str(file_path).lower().endswith((".csv", ".txt"))
        encodings = ["utf-8-sig", "gb18030", "utf-16", "gbk"]
        for enc in encodings:
            try:
                df = pd.read_csv(file_path, header=None, encoding=enc, engine="python", on_bad_lines="skip")
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
            except Exception:
                continue

    if df is None or df.empty:
        return None

    # 这里的 keywords 增加归属表相关的列名，防止找错表头
    keywords = ["门店", "顾问", "管家", "排名", "代理商", "序号", "线索", "质检", "添加微信", "区域经理", "省份", "城市"]
    header_row = 0

    search_rows = 20 if is_rank_file else 15
    for i in range(min(search_rows, len(df))):
        row_values = df.iloc[i].astype(str).str.cat(sep=",")
        if any(k in row_values for k in keywords):
            header_row = i
            break

    df.columns = df.iloc[header_row]
    df = df[header_row + 1:].reset_index(drop=True)

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\n", "", regex=False)
        .str.replace("\r", "", regex=False)
    )

    df.columns = dedupe_columns(df.columns)

    df = df.loc[:, df.columns.notna()]
    df = df.loc[:, df.columns != "nan"]

    return df


def clean_percent_col(df: pd.DataFrame, col_name: str):
    if col_name not in df.columns:
        return
    series = df[col_name].astype(str).str.strip().str.replace("%", "", regex=False)
    numeric_series = pd.to_numeric(series, errors="coerce").fillna(0)
    if numeric_series.max() > 1.0:
        df[col_name] = numeric_series / 100
    else:
        df[col_name] = numeric_series


def safe_div(df: pd.DataFrame, num_col: str, denom_col: str):
    if num_col not in df.columns or denom_col not in df.columns:
        return pd.Series([0] * len(df))
    num = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
    denom = pd.to_numeric(df[denom_col], errors="coerce").fillna(0)
    result = (num / denom).replace([np.inf, -np.inf], 0).fillna(0)
    return result


def _to_1d_numeric(x):
    """把 Series 或DataFrame 压成 1 列数值 Series"""
    if isinstance(x, pd.DataFrame):
        tmp = x.apply(pd.to_numeric, errors="coerce")
        return tmp.bfill(axis=1).iloc[:, 0].fillna(0)
    return pd.to_numeric(x, errors="coerce").fillna(0)


def _pick_col_exact(df: pd.DataFrame, exact_name: str):
    """精确查找列名"""
    for c in df.columns:
        if str(c).strip() == exact_name:
            return c
    return None

def _pick_any_col(df: pd.DataFrame, any_keywords, exclude_keywords=None):
    """模糊查找列名"""
    exclude_keywords = exclude_keywords or []
    for c in df.columns:
        s = str(c)
        if any(k in s for k in any_keywords) and not any(x in s for x in exclude_keywords):
            return c
    return None

# --- Data Processing ---

@st.cache_data(ttl=300)
def process_data(path_f, path_d, path_a, path_s, path_m):
    try:
        # 读取业务数据
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        raw_s = smart_read(path_s, is_rank_file=True)
        
        # 读取归属关系数据 (Master Data)
        raw_m = smart_read(path_m)

        if raw_f is None or raw_d is None or raw_a is None or raw_s is None:
            return None, None

        # ==========================================
        # 0. 准备归属映射表 (Store Mapping)
        # ==========================================
        df_mapping = None
        def strict_clean_str(series):
            return series.astype(str).str.strip().str.replace(r'\s+', '', regex=True).str.lower().replace('nan', '')

        if raw_m is not None:
            # 标准化列名，防止Excel里的列名有空格
            raw_m = raw_m.rename(columns=lambda x: str(x).strip())
            
            # 识别关键列
            col_mgr = _pick_any_col(raw_m, ["区域经理", "大区经理"])
            col_prov = _pick_any_col(raw_m, ["省份", "省"])
            col_city = _pick_any_col(raw_m, ["城市", "市"])
            col_store = _pick_any_col(raw_m, ["门店名称", "代理商", "经销商"])

            if col_mgr and col_store:
                df_mapping = raw_m[[col_store]].copy()
                df_mapping.rename(columns={col_store: "门店名称"}, inplace=True)
                
                df_mapping["区域经理"] = raw_m[col_mgr] if col_mgr else "未知"
                df_mapping["省份"] = raw_m[col_prov] if col_prov else "未知"
                df_mapping["城市"] = raw_m[col_city] if col_city else "未知"
                
                # 清洗门店名作为 Key
                df_mapping["Join_Key"] = strict_clean_str(df_mapping["门店名称"])
                # 去重，防止一对多
                df_mapping = df_mapping.drop_duplicates(subset=["Join_Key"])

        # ==========================================
        # 1. 处理漏斗数据 (Funnel)
        # ==========================================
        store_col_f = _pick_col_exact(raw_f, "代理商") or _pick_any_col(raw_f, ["门店", "经销商"]) or raw_f.columns[0]
        name_col_f = _pick_any_col(raw_f, ["管家", "顾问", "邀约"]) or raw_f.columns[1]

        col_leads = "线上_有效线索数" if "线上_有效线索数" in raw_f.columns else ("线索量" if "线索量" in raw_f.columns else _pick_any_col(raw_f, ["有效线索", "线索数"]))
        col_visits = "线上_到店数" if "线上_到店数" in raw_f.columns else ("到店量" if "到店量" in raw_f.columns else _pick_any_col(raw_f, ["到店数", "到店量"]))
        col_excel_rate = _pick_any_col(raw_f, ["率"], exclude_keywords=["试驾", "成交"])

        rename_dict_f = {store_col_f: "门店名称", name_col_f: "邀约专员/管家"}
        if col_leads: rename_dict_f[col_leads] = "线索量"
        if col_visits: rename_dict_f[col_visits] = "到店量"
        if col_excel_rate: rename_dict_f[col_excel_rate] = "Excel_Rate"

        df_f = raw_f.rename(columns=rename_dict_f)
        df_f.columns = dedupe_columns(df_f.columns)

        if "门店名称" in df_f.columns:
            df_f["门店名称"] = df_f["门店名称"].replace([r'^\s*$', 'nan', 'None'], np.nan, regex=True).ffill()

        mask_sub = df_f["邀约专员/管家"].astype(str).str.contains("小计|合计|总计", na=False)
        df_store_data = df_f[mask_sub].copy()

        mask_bad = df_f["邀约专员/管家"].astype(str).str.strip().isin(["", "-", "—", "nan", "None"])
        df_advisor_data = df_f[~mask_sub & ~mask_bad].copy()

        for df in [df_store_data, df_advisor_data]:
            if "线索量" in df.columns: df["线索量"] = pd.to_numeric(df["线索量"], errors="coerce").fillna(0)
            else: df["线索量"] = 0.0

            if "到店量" in df.columns: df["到店量"] = pd.to_numeric(df["到店量"], errors="coerce").fillna(0)
            else: df["到店量"] = 0.0

            if "Excel_Rate" in df.columns:
                clean_percent_col(df, "Excel_Rate")
                df["线索到店率_数值"] = df["Excel_Rate"]
            else:
                num = pd.to_numeric(df["到店量"], errors="coerce").fillna(0)
                denom = pd.to_numeric(df["线索量"], errors="coerce").fillna(0)
                df["线索到店率_数值"] = (num / denom).replace([np.inf, -np.inf], 0).fillna(0)

            df["线索到店率"] = (df["线索到店率_数值"] * 100).map("{:.1f}%".format)

        store_qc_cols = ["质检总分", "S_60s", "S_Needs", "S_Car", "S_Policy", "S_Wechat", "S_Time"]
        df_store_data.drop(columns=[c for c in store_qc_cols if c in df_store_data.columns], inplace=True, errors="ignore")

        # ==========================================
        # 2. 处理 DCC 顾问质检数据
        # ==========================================
        df_d = raw_d.rename(columns={
            "顾问名称": "邀约专员/管家", "管家": "邀约专员/管家", "质检总分": "质检总分",
            "60秒通话": "S_60s", "用车需求": "S_Needs", "车型信息": "S_Car",
            "政策相关": "S_Policy", "明确到店时间": "S_Time"
        })
        store_col_d = _pick_col_exact(raw_d, "门店名称") or _pick_any_col(raw_d, ["门店", "代理商"])
        if store_col_d and store_col_d in df_d.columns:
             df_d = df_d.rename(columns={store_col_d: "门店名称"})
        
        df_d.columns = dedupe_columns(df_d.columns)
        
        wechat_cols = [c for c in df_d.columns if ("微信" in str(c) and "添加" in str(c)) or ("添加微信" in str(c))]
        df_d["S_Wechat"] = _to_1d_numeric(df_d[wechat_cols]) if wechat_cols else 0

        score_cols = ["质检总分", "S_60s", "S_Needs", "S_Car", "S_Policy", "S_Wechat", "S_Time"]
        for c in score_cols:
            if c in df_d.columns: df_d[c] = pd.to_numeric(df_d[c], errors="coerce")
        
        if "邀约专员/管家" not in df_d.columns: df_d["邀约专员/管家"] = ""
        cols_to_keep_d = ["邀约专员/管家"] + [c for c in score_cols if c in df_d.columns]
        if "门店名称" in df_d.columns: cols_to_keep_d.append("门店名称")
        df_d = df_d[cols_to_keep_d]

        # ==========================================
        # 3. 处理 门店排名/质检数据
        # ==========================================
        store_name_candidates = [c for c in raw_s.columns if ("门店" in str(c)) and ("ID" not in str(c))]
        store_name_exact = _pick_col_exact(raw_s, "门店名称")
        
        if store_name_exact: store_name = raw_s[store_name_exact].astype(str)
        elif store_name_candidates:
            tmp = raw_s[store_name_candidates]
            store_name = tmp.astype(str) if isinstance(tmp, pd.Series) else tmp.bfill(axis=1).iloc[:, 0].astype(str)
        else: store_name = pd.Series(["" for _ in range(len(raw_s))])
            
        store_name = store_name.str.strip()
        df_s = pd.DataFrame({"门店名称": store_name})

        # Mapping config
        col_map = {
            "SR_质检总分": _pick_any_col(raw_s, ["质检总分", "总分"], exclude_keywords=["显示"]),
            "SR_S_60s": _pick_any_col(raw_s, ["60秒", "60 秒"]),
            "SR_S_Needs": _pick_any_col(raw_s, ["用车需求"]),
            "SR_S_Car": _pick_any_col(raw_s, ["车型信息"]),
            "SR_S_Policy": _pick_any_col(raw_s, ["政策"]),
            "SR_S_Time": _pick_any_col(raw_s, ["明确到店", "到店时间"]),
            "SR_S_Wechat": _pick_any_col(raw_s, ["添加微信", "加微信"])
        }

        for new_col, raw_col in col_map.items():
            if raw_col and raw_col in raw_s.columns:
                df_s[new_col] = _to_1d_numeric(raw_s[raw_col])
            else:
                df_s[new_col] = np.nan

        df_s["门店名称"] = df_s["门店名称"].astype(str).str.strip()
        df_s = df_s[df_s["门店名称"].ne("")].copy()
        df_s = df_s.drop_duplicates(subset=["门店名称"], keep="first")

        # ==========================================
        # 4. 处理 AMS 数据
        # ==========================================
        df_a = raw_a.copy()
        store_col_a = _pick_col_exact(raw_a, "代理商") or _pick_any_col(raw_a, ["门店", "经销商"])
        if store_col_a: df_a = df_a.rename(columns={store_col_a: "门店名称"})

        rename_map_ams = {
            "管家姓名": "邀约专员/管家", "DCC平均通话时长": "通话时长", "DCC接通线索数": "conn_num",
            "DCC外呼线索数": "conn_denom", "DCC及时处理线索": "timely_num", "需外呼线索数": "timely_denom",
            "二次外呼线索数": "call2_num", "需再呼线索数": "call2_denom", "DCC三次外呼的线索数": "call3_num",
            "DCC二呼状态为需再呼的线索数": "call3_denom"
        }
        for src, tgt in rename_map_ams.items():
            if src in df_a.columns: df_a = df_a.rename(columns={src: tgt})

        if "邀约专员/管家" not in df_a.columns: df_a["邀约专员/管家"] = ""
        
        all_ams_calc_cols = ["conn_num", "conn_denom", "timely_num", "timely_denom",
                             "call2_num", "call2_denom", "call3_num", "call3_denom"]
        for c in all_ams_calc_cols + ["通话时长"]:
            if c not in df_a.columns: df_a[c] = 0
            df_a[c] = _to_1d_numeric(df_a[c])

        # ==========================================
        # 5. 清洗与合并
        # ==========================================
        for df_x in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
            if "门店名称" in df_x.columns: df_x["门店名称"] = strict_clean_str(df_x["门店名称"])
            if "邀约专员/管家" in df_x.columns: df_x["邀约专员/管家"] = strict_clean_str(df_x["邀约专员/管家"])

        # 合并 1: 漏斗(Advisor) + DCC(Advisor)
        full_advisors = df_advisor_data.copy()
        if "邀约专员/管家" in df_d.columns:
            cols_use_d = list(df_d.columns)
            if "门店名称" in cols_use_d: df_d = df_d.rename(columns={"门店名称": "门店名称_dcc"})
            full_advisors = pd.merge(full_advisors, df_d, on="邀约专员/管家", how="left", suffixes=("", "_dcc"))

        # 合并 2: 合并 AMS (个人)
        cols_ams_needed = [c for c in all_ams_calc_cols if c in df_a.columns] + ["通话时长"]
        join_on = ["门店名称", "邀约专员/管家"] if ("门店名称" in df_a.columns and "门店名称" in full_advisors.columns) else ["邀约专员/管家"]
        cols_for_merge = list(set(join_on + cols_ams_needed))
        full_advisors = pd.merge(full_advisors, df_a[cols_for_merge], on=join_on, how="left", suffixes=("", "_ams"))

        # 填充0
        for c in ["线索量", "到店量", "通话时长"] + all_ams_calc_cols:
            if c in full_advisors.columns: full_advisors[c] = pd.to_numeric(full_advisors[c], errors="coerce").fillna(0)

        # 个人率
        full_advisors["外呼接通率"] = safe_div(full_advisors, "conn_num", "conn_denom")
        full_advisors["DCC及时处理率"] = safe_div(full_advisors, "timely_num", "timely_denom")
        full_advisors["DCC二次外呼率"] = safe_div(full_advisors, "call2_num", "call2_denom")
        full_advisors["DCC三次外呼率"] = safe_div(full_advisors, "call3_num", "call3_denom")

        # 合并 3: 生成 门店级 宽表
        if "门店名称" in df_a.columns and len(all_ams_calc_cols) > 0:
             ams_store_agg = df_a.groupby("门店名称").agg({c:"sum" for c in all_ams_calc_cols}).reset_index()
             ams_store_agg["外呼接通率"] = safe_div(ams_store_agg, "conn_num", "conn_denom")
             ams_store_agg["DCC及时处理率"] = safe_div(ams_store_agg, "timely_num", "timely_denom")
             ams_store_agg["DCC二次外呼率"] = safe_div(ams_store_agg, "call2_num", "call2_denom")
             ams_store_agg["DCC三次外呼率"] = safe_div(ams_store_agg, "call3_num", "call3_denom")
             
             full_stores = pd.merge(df_store_data, df_s, on="门店名称", how="left")
             full_stores = pd.merge(full_stores, ams_store_agg, on="门店名称", how="left")
        else:
             full_stores = pd.merge(df_store_data, df_s, on="门店名称", how="left")

        # 恢复SR_列名
        for col in full_stores.columns:
            if str(col).startswith("SR_"):
                real_col = str(col).replace("SR_", "")
                full_stores[real_col] = full_stores[col]
        full_stores.drop(columns=[c for c in full_stores.columns if str(c).startswith("SR_")], inplace=True, errors="ignore")
        full_stores.columns = dedupe_columns(full_stores.columns)

        # ==========================================
        # 6. 注入归属信息 (Manager/Province/City)
        # ==========================================
        if df_mapping is not None and not df_mapping.empty:
            # 关联门店表
            full_stores["Join_Key"] = strict_clean_str(full_stores["门店名称"])
            full_stores = pd.merge(full_stores, df_mapping, on="Join_Key", how="left", suffixes=("", "_map"))
            # 修正关联后的列名
            for c in ["区域经理", "省份", "城市"]:
                if f"{c}_map" in full_stores.columns:
                    full_stores[c] = full_stores[f"{c}_map"].fillna("未知")
                elif c in full_stores.columns:
                     # 关键修复：如果原表有列但没匹配上，也要填未知，防止出现 NaN
                     full_stores[c] = full_stores[c].fillna("未知")
                else:
                    full_stores[c] = "未知"
            
            full_stores.drop(columns=["Join_Key"] + [c for c in full_stores.columns if c.endswith("_map")], inplace=True)
            
            # 关联顾问表
            full_advisors["Join_Key"] = strict_clean_str(full_advisors["门店名称"])
            full_advisors = pd.merge(full_advisors, df_mapping, on="Join_Key", how="left", suffixes=("", "_map"))
            for c in ["区域经理", "省份", "城市"]:
                if f"{c}_map" in full_advisors.columns:
                    full_advisors[c] = full_advisors[f"{c}_map"].fillna("未知")
                elif c in full_advisors.columns:
                    full_advisors[c] = full_advisors[c].fillna("未知")
                else:
                    full_advisors[c] = "未知"
            
            full_advisors.drop(columns=["Join_Key"] + [c for c in full_advisors.columns if c.endswith("_map")], inplace=True)
        else:
            # 如果没有 Mapping 文件，给默认值防止报错
            for df in [full_stores, full_advisors]:
                df["区域经理"] = "未知"
                df["省份"] = "未知"
                df["城市"] = "未知"

        return full_advisors, full_stores

    except Exception as e:
        st.error(f"处理出错: {e}")
        st.text(traceback.format_exc())
        return None, None


# --- UI Layout ---

with st.sidebar:
    st.header("⚙️ 管理面板")

    store_rank_path = get_store_rank_path()
    # 检查 Operational Data 是否齐全
    op_data_ready = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and (store_rank_path is not None)
    
    if op_data_ready:
        st.success("✅ 业务数据：已就绪")
    else:
        st.warning("⚠️ 业务数据：缺失")
        
    if os.path.exists(PATH_M):
        st.success("✅ 归属数据：已就绪")
    else:
        st.warning("⚠️ 归属数据：暂无 (请上传)")
        
    st.markdown("---")

    with st.expander("🔐 更新数据 (仅限管理员)"):
        pwd = st.text_input("输入管理员密码", type="password")
        if pwd == ADMIN_PASSWORD:
            tab1, tab2 = st.tabs(["📊 更新业务数据", "🗺️ 更新归属关系"])
            
            with tab1:
                st.info("请上传本次考评周期的 4 个业务报表：")
                new_f = st.file_uploader("1. 漏斗指标表", type=["xlsx", "csv"], key="up_f")
                new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"], key="up_d")
                new_a = st.file_uploader("3. AMS跟进表", type=["xlsx", "csv"], key="up_a")
                new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"], key="up_s")

                if st.button("🚀 提交业务数据"):
                    if new_f and new_d and new_a and new_s:
                        with st.spinner("正在保存业务数据..."):
                            save_uploaded_file(new_f, PATH_F)
                            save_uploaded_file(new_d, PATH_D)
                            save_uploaded_file(new_a, PATH_A)
                            
                            # 门店排名特殊处理
                            if str(new_s.name).lower().endswith(".xlsx"):
                                if os.path.exists(PATH_S_CSV): os.remove(PATH_S_CSV)
                                save_uploaded_file(new_s, PATH_S_XLSX)
                            else:
                                if os.path.exists(PATH_S_XLSX): os.remove(PATH_S_XLSX)
                                save_uploaded_file(new_s, PATH_S_CSV)

                            try:
                                with open(LAST_UPDATE_FILE, "w", encoding="utf-8") as f:
                                    f.write(datetime.now().isoformat(timespec="seconds"))
                            except Exception: pass
                        
                        # 清除缓存，确保下次读取新数据
                        process_data.clear()
                        st.success("更新完成，正在刷新...")
                        st.rerun()
                    else:
                        st.error("请传齐 4 个业务文件")
            
            with tab2:
                st.info("此处上传【代理商名称归属表】。仅需上传一次，除非归属关系发生变更。")
                new_m = st.file_uploader("5. 代理商归属表 (含区域/省份/城市)", type=["xlsx", "csv"], key="up_m")
                
                if st.button("💾 保存归属关系"):
                    if new_m:
                        with st.spinner("正在保存归属表..."):
                            save_uploaded_file(new_m, PATH_M)
                        # 清除缓存，确保下次读取新归属关系
                        process_data.clear()
                        st.success("归属关系已更新！")
                        st.rerun()
                    else:
                        st.error("请选择文件")


store_rank_path = get_store_rank_path()
op_data_ready = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and (store_rank_path is not None)

if op_data_ready:
    # 无论有无 Mapping 文件，都尝试读取 (process_data 内部处理了 None 的情况)
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, store_rank_path, PATH_M)

    if df_advisors is not None:
        col_header, col_update = st.columns([3, 1])
        with col_header:
            st.title("Audi | DCC 效能看板")
        with col_update:
            upd = get_data_update_time(store_rank_path)
            upd_text = upd.strftime("%Y-%m-%d %H:%M") if upd else "暂无"
            st.markdown(f"<div style='text-align:right;color:gray;font-size:12px;padding-top:20px;'>🕒 数据更新: {upd_text}</div>", unsafe_allow_html=True)

        # =========================================================
        # 四级联动筛选器 (Cascading Filters)
        # =========================================================
        st.markdown("### 🧬 多维视图切换")
        
        # 使用 4 列布局，使筛选框等宽、整齐
        f_c1, f_c2, f_c3, f_c4 = st.columns(4)
        
        # 1. 区域经理
        # 强制转换为字符串再提取 unique，防止 TypeError (NaN vs String)
        if "区域经理" in df_stores.columns:
            mgr_list = sorted(df_stores["区域经理"].dropna().astype(str).unique().tolist())
        else:
            mgr_list = []
        all_managers = ["全部"] + mgr_list

        with f_c1:
            sel_mgr = st.selectbox("1️⃣ 区域经理", all_managers, key="filter_mgr")
        
        # 2. 省份 (基于经理联动)
        df_l2 = df_stores if sel_mgr == "全部" else df_stores[df_stores["区域经理"] == sel_mgr]
        if "省份" in df_l2.columns:
            prov_list = sorted(df_l2["省份"].dropna().astype(str).unique().tolist())
        else:
            prov_list = []
        all_provs = ["全部"] + prov_list
        
        with f_c2:
            sel_prov = st.selectbox("2️⃣ 省份", all_provs, key="filter_prov")
        
        # 3. 城市 (基于省份联动)
        df_l3 = df_l2 if sel_prov == "全部" else df_l2[df_l2["省份"] == sel_prov]
        if "城市" in df_l3.columns:
            city_list = sorted(df_l3["城市"].dropna().astype(str).unique().tolist())
        else:
            city_list = []
        all_cities = ["全部"] + city_list
        
        with f_c3:
            sel_city = st.selectbox("3️⃣ 城市", all_cities, key="filter_city")
        
        # 4. 门店 (基于城市联动)
        df_l4 = df_l3 if sel_city == "全部" else df_l3[df_l3["城市"] == sel_city]
        if "门店名称" in df_l4.columns:
            store_list = sorted(df_l4["门店名称"].dropna().astype(str).unique().tolist())
        else:
            store_list = []
        all_stores = ["全部"] + store_list

        with f_c4:
            sel_store = st.selectbox("4️⃣ 门店", all_stores, key="filter_store")

        # =========================================================
        # 数据过滤逻辑
        # =========================================================
        
        filtered_stores = df_l4.copy() # 当前筛选漏斗剩下的所有门店
        
        if sel_store == "全部":
            # 聚合模式：计算 filtered_stores 的总和/平均
            current_df = filtered_stores.copy()
            
            # 显示标题
            if sel_city != "全部": rank_title = f"🏆 {sel_city} - 门店排名"
            elif sel_prov != "全部": rank_title = f"🏆 {sel_prov} - 门店排名"
            elif sel_mgr != "全部": rank_title = f"🏆 {sel_mgr}区域 - 门店排名"
            else: rank_title = "🏆 全区门店排名"
            
            # 用于 KPI 计算的聚合
            kpi_leads = current_df["线索量"].sum()
            kpi_visits = current_df["到店量"].sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df["质检总分"].mean() # 平均分
            
            # 用于绘图的 DF 就是 current_df (包含该层级下所有门店)
            current_df["名称"] = current_df["门店名称"]
            
        else:
            # 单店模式
            current_df = df_advisors[df_advisors["门店名称"] == sel_store].copy()
            current_df["名称"] = current_df["邀约专员/管家"]
            rank_title = f"👤 {sel_store} - 顾问排名"
            
            kpi_leads = current_df["线索量"].sum()
            kpi_visits = current_df["到店量"].sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df["质检总分"].mean()

        # =========================================================
        # 仪表盘展示
        # =========================================================
        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")

        st.markdown("---")
        st.subheader("2️⃣ DCC 外呼过程监控 (Process)")

        def calc_kpi_rate(df, num, denom):
            if num not in df.columns or denom not in df.columns: return 0
            total_num = df[num].sum()
            total_denom = df[denom].sum()
            return total_num / total_denom if total_denom > 0 else 0

        p1, p2, p3, p4 = st.columns(4)
        avg_conn = calc_kpi_rate(current_df, "conn_num", "conn_denom")
        avg_timely = calc_kpi_rate(current_df, "timely_num", "timely_denom")
        avg_call2 = calc_kpi_rate(current_df, "call2_num", "call2_denom")
        avg_call3 = calc_kpi_rate(current_df, "call3_num", "call3_denom")

        p1.metric("📞 外呼接通率", f"{avg_conn:.1%}")
        p2.metric("⚡ DCC及时处理率", f"{avg_timely:.1%}")
        p3.metric("🔄 二次外呼率", f"{avg_call2:.1%}")
        p4.metric("🔁 三次外呼率", f"{avg_call3:.1%}")
        
        # 绘图数据准备
        plot_df_vis = current_df.copy()
        plot_df_vis["质检总分_显示"] = plot_df_vis.get("质检总分", pd.Series([0]*len(plot_df_vis))).fillna(0)

        # 散点图 1
        c_proc_1, c_proc_2 = st.columns(2)
        with c_proc_1:
            st.markdown("#### 🕵️ 异常侦测：外呼接通率 vs 60秒通话占比")
            if "S_60s" in plot_df_vis.columns and "外呼接通率" in plot_df_vis.columns:
                fig_p1 = px.scatter(
                    plot_df_vis, x="外呼接通率", y="S_60s",
                    size="线索量", color="质检总分_显示", hover_name="名称",
                    color_continuous_scale="RdYlGn", height=350,
                )
                fig_p1.add_vline(x=avg_conn, line_dash="dash", line_color="gray")
                fig_p1.update_layout(xaxis=dict(tickformat=".0%"))
                st.plotly_chart(fig_p1, use_container_width=True)
            else: st.warning("数据不足")

        with c_proc_2:
            st.markdown("#### 🔗 归因分析：过程指标 vs 线索首邀到店率")
            x_axis_choice = st.radio("选择横轴指标：", ["DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"], horizontal=True)
            
            plot_df_vis["线索到店率_显示"] = pd.to_numeric(plot_df_vis.get("线索到店率_数值", 0)).fillna(0).clip(0, 1)
            
            if x_axis_choice in plot_df_vis.columns:
                fig_p2 = px.scatter(
                    plot_df_vis, x=x_axis_choice, y="线索到店率_显示",
                    size="线索量", color="质检总分_显示", hover_name="名称",
                    color_continuous_scale="Blues", height=300
                )
                fig_p2.update_layout(xaxis=dict(tickformat=".0%"), yaxis=dict(tickformat=".1%"))
                st.plotly_chart(fig_p2, use_container_width=True)
            else: st.warning("数据不足")

        st.markdown("---")

        c_left, c_right = st.columns([1, 2])
        with c_left:
            st.markdown(f"### {rank_title}")
            if "线索到店率_数值" in current_df.columns:
                rank_df = current_df[["名称", "线索到店率", "线索到店率_数值", "质检总分"]].copy()
                rank_df["Sort_Score"] = rank_df["线索到店率_数值"].fillna(-1)
                rank_df = rank_df.sort_values("Sort_Score", ascending=False).head(15)
                st.dataframe(
                    rank_df[["名称", "线索到店率", "质检总分"]],
                    hide_index=True, use_container_width=True, height=400,
                    column_config={"质检总分": st.column_config.NumberColumn(format="%.1f")}
                )
            else: st.warning("无排行数据")

        with c_right:
            st.markdown("### 💡 话术质量 vs 转化结果")
            if "S_Time" in plot_df_vis.columns:
                fig = px.scatter(
                    plot_df_vis, x="S_Time", y="线索到店率_显示",
                    size="线索量", color="质检总分_显示", hover_name="名称",
                    color_continuous_scale="Reds", height=400,
                    labels={"S_Time": "明确到店时间得分", "线索到店率_显示": "线索到店率"}
                )
                fig.update_layout(yaxis=dict(tickformat=".1%"))
                st.plotly_chart(fig, use_container_width=True)
            else: st.warning("数据不足")

        # 诊断部分保持不变，仅当选了具体门店时才显示顾问列表
        st.markdown("---")
        if sel_store != "全部":
            st.markdown("### 🕵️‍♀️ 顾问深度诊断")
            # ... (这部分逻辑复用之前的，无需变动，因为current_df已经是顾问级数据)
            diag_list = sorted(current_df["邀约专员/管家"].dropna().astype(str).unique())
            if diag_list:
                sel_p = st.selectbox("🔍 选择顾问：", diag_list)
                p_row = current_df[current_df["邀约专员/管家"] == sel_p]
                if not p_row.empty:
                    p = p_row.iloc[0]
                    # 简单绘制一下漏斗
                    c1, c2 = st.columns(2)
                    with c1:
                        fig_f = go.Figure(go.Funnel(y=["线索", "到店"], x=[p.get("线索量",0), p.get("到店量",0)]))
                        fig_f.update_layout(height=200, showlegend=False)
                        st.plotly_chart(fig_f, use_container_width=True)
                    with c2:
                        st.metric("线索到店率", p.get("线索到店率", "0%"))
                        st.metric("质检总分", f"{p.get('质检总分', 0):.1f}")
        else:
            st.info("💡 选择具体【门店】后，可查看该店顾问的详细诊断报告。")

else:
    st.info("👋 欢迎使用 Audi 效能看板！")
    st.warning("👉 请在左侧侧边栏上传数据。")
