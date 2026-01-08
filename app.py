import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime

st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown(
    """
<style>
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border:  1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    .big-font {font-size: 18px !   important; font-weight: bold;}
</style>
""",
    unsafe_allow_html=True,
)

ADMIN_PASSWORD = "AudiSARR3"

DATA_DIR = "data_store"
os.makedirs(DATA_DIR, exist_ok=True)

PATH_F = os.path.join(DATA_DIR, "funnel. xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.  xlsx")
PATH_A = os.path.join(DATA_DIR, "ams. xlsx")

PATH_S_XLSX = os.path.join(DATA_DIR, "store_rank.xlsx")
PATH_S_CSV = os.path.join(DATA_DIR, "store_rank.csv")


def save_uploaded_file(uploaded_file, save_path:   str) -> bool:
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


LAST_UPDATE_FILE = os.path.join(DATA_DIR, "_last_upload_time.txt")


def get_data_update_time(store_rank_path:  str | None):
    """返回最新一次上传数据报的时间"""
    if os.path.exists(LAST_UPDATE_FILE):
        try:
            txt = open(LAST_UPDATE_FILE, "r", encoding="utf-8").read().strip()
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
    """把重复列名变成:   列名, 列名__1, 列名__2"""
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


def smart_read(file_path:   str, is_rank_file: bool = False):
    """鲁棒读取（xlsx/csv/误后缀 xlsx）+ 自动找表头 + 列名去重"""
    if not file_path or not os.path.exists(file_path):
        return None

    df = None

    try:
        with open(file_path, "rb") as f:
            sig = f.read(4)
        if sig == b"PK":
            df = pd.  read_excel(file_path, header=None)
    except Exception:  
        pass

    if df is None: 
        is_csv = str(file_path).lower().endswith((". csv", ".txt"))
        if is_csv:
            encodings = ["utf-8-sig", "gb18030", "utf-16"]
            for enc in encodings:  
                try:
                    df = pd.read_csv(file_path, header=None, encoding=enc, engine="python", on_bad_lines="skip")
                    break
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
                except Exception:
                    continue
        else:
            try:  
                df = pd.read_excel(file_path, header=None)
            except Exception: 
                return None

    if df is None or df.empty:
        return None

    keywords = ["门店", "顾问", "管家", "排名", "代理商", "序号", "线索", "质检", "添加微信"]
    header_row = 0

    search_rows = 15 if is_rank_file else 12
    for i in range(min(search_rows, len(df))):
        row_values = df.iloc[i].astype(str).str.cat(sep=",")
        if any(k in row_values for k in keywords):
            header_row = i
            break

    df.  columns = df.iloc[header_row]
    df = df[header_row + 1:].reset_index(drop=True)

    df.  columns = (
        df.columns.astype(str)
        .str. strip()
        .str.replace("\n", "", regex=False)
        .str.replace("\r", "", regex=False)
    )

    df. columns = dedupe_columns(df.columns)

    df = df.loc[:  , df.columns.notna()]
    df = df.loc[:, df.columns != "nan"]

    return df


def clean_percent_col(df:   pd.DataFrame, col_name: str):
    if col_name not in df.columns:
        return
    series = df[col_name].  astype(str).str.strip().str.replace("%", "", regex=False)
    numeric_series = pd.to_numeric(series, errors="coerce").fillna(0)
    if numeric_series.max() > 1. 0:
        df[col_name] = numeric_series / 100
    else:  
        df[col_name] = numeric_series


def safe_div(df:   pd.DataFrame, num_col: str, denom_col: str):
    if num_col not in df.columns or denom_col not in df.columns:
        return pd.Series([0] * len(df))
    num = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
    denom = pd.to_numeric(df[denom_col], errors="coerce").fillna(0)
    result = (num / denom).replace([np.inf, -np. inf], 0).fillna(0)
    return result


def _to_1d_numeric(x):
    """把 Series 或DataFrame 压成 1 列数值 Series"""
    if isinstance(x, pd.DataFrame):
        tmp = x.apply(pd.to_numeric, errors="coerce")
        return tmp.bfill(axis=1).iloc[:, 0].  fillna(0)
    return pd.to_numeric(x, errors="coerce").fillna(0)


def _pick_any_col(df: pd.DataFrame, any_keywords, exclude_keywords=None):
    exclude_keywords = exclude_keywords or []
    for c in df.columns:
        s = str(c)
        if any(k in s for k in any_keywords) and not any(x in s for x in exclude_keywords):
            return c
    return None


def _col_as_series(df: pd.DataFrame, col_name: str):
    """df[col] 可能因为重复列名返回 DataFrame；这里统一压成 1D Series"""
    if col_name not in df.columns:
        return None
    x = df[col_name]
    if isinstance(x, pd.DataFrame):
        x = x.iloc[:, 0]
    return x


@st.cache_data(ttl=300)
def process_data(path_f, path_d, path_a, path_s):
    try:
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        raw_s = smart_read(path_s, is_rank_file=True)

        if raw_f is None or raw_d is None or raw_a is None or raw_s is None:
            return None, None

        store_col = _pick_any_col(raw_f, ["代理商", "门店"]) or raw_f.columns[0]
        name_col = _pick_any_col(raw_f, ["管家", "顾问", "邀约"]) or raw_f.columns[1]

        col_leads = "线上_有效线索数" if "线上_有效线索数" in raw_f.columns else ("线索量" if "线索量" in raw_f.columns else _pick_any_col(raw_f, ["有效线索", "线索数"]))
        col_visits = "线上_到店数" if "线上_到店数" in raw_f.columns else ("到店量" if "到店量" in raw_f.columns else _pick_any_col(raw_f, ["到店数", "到店量"]))

        col_excel_rate = _pick_any_col(raw_f, ["率"], exclude_keywords=["试驾", "成交"])

        rename_dict = {store_col: "门店名称", name_col: "邀约专员/管家"}
        if col_leads:  
            rename_dict[col_leads] = "线索量"
        if col_visits:  
            rename_dict[col_visits] = "到店量"
        if col_excel_rate: 
            rename_dict[col_excel_rate] = "Excel_Rate"

        df_f = raw_f.rename(columns=rename_dict)
        df_f.  columns = dedupe_columns(df_f.  columns)

        mask_sub = df_f["邀约专员/管家"]. astype(str).str.contains("小计|合计|总计", na=False)
        df_store_data = df_f[mask_sub].  copy()

        mask_bad = df_f["邀约专员/管家"]. astype(str).str.strip().isin(["", "-", "—", "nan"])
        df_advisor_data = df_f[~mask_sub & ~mask_bad]. copy()

        for df in [df_store_data, df_advisor_data]: 
            if "线索量" in df.columns:
                df["线索量"] = pd.to_numeric(df["线索量"], errors="coerce").fillna(0)
            else:
                df["线索量"] = 0.0

            if "到店量" in df.columns:
                df["到店量"] = pd.to_numeric(df["到店量"], errors="coerce").fillna(0)
            else:
                df["到店量"] = 0.0

            if "Excel_Rate" in df.columns:
                clean_percent_col(df, "Excel_Rate")
                df["线索到店率_数值"] = df["Excel_Rate"]
            else:
                num = pd.to_numeric(df["到店量"], errors="coerce").fillna(0)
                denom = pd.to_numeric(df["线索量"], errors="coerce").fillna(0)
                df["线索到店率_数值"] = (num / denom).replace([np.inf, -np. inf], 0).fillna(0)

            df["线索到店率"] = (df["线索到店率_数值"] * 100).map("{:.1f}%".format)

        store_qc_cols = ["质检总分", "S_60s", "S_Needs", "S_Car", "S_Policy", "S_Wechat", "S_Time"]
        df_store_data.  drop(columns=[c for c in store_qc_cols if c in df_store_data.columns], inplace=True, errors="ignore")

        df_d = raw_d.rename(
            columns={
                "顾问名称": "邀约专员/管家",
                "管家":   "邀约专员/管家",
                "质检总分": "质检总分",
                "60秒通话": "S_60s",
                "用车需求": "S_Needs",
                "车型信息": "S_Car",
                "政策相关": "S_Policy",
                "明确到店时间": "S_Time",
            }
        )

        df_d. columns = dedupe_columns(df_d.  columns)

        wechat_cols = [c for c in df_d.columns if ("微信" in str(c) and "添加" in str(c)) or ("添加微信" in str(c))]
        if wechat_cols:
            df_d["S_Wechat"] = _to_1d_numeric(df_d[wechat_cols])
        else:
            df_d["S_Wechat"] = 0

        score_cols = ["质检总分", "S_60s", "S_Needs", "S_Car", "S_Policy", "S_Wechat", "S_Time"]
        for c in score_cols:
            if c in df_d.columns:
                df_d[c] = pd.to_numeric(df_d[c], errors="coerce")
        if "邀约专员/管家" not in df_d.columns:
            df_d["邀约专员/管家"] = ""
        df_d = df_d[["邀约专员/管家"] + [c for c in score_cols if c in df_d.columns]]

        def pick_col_by_keywords(df:   pd.DataFrame, must_have_any, must_have_all=None, exclude=None):
            must_have_all = must_have_all or []
            exclude = exclude or []
            for c in df.columns:
                s = str(c)
                if any(k in s for k in must_have_any) and all(k in s for k in must_have_all) and not any(x in s for x in exclude):
                    return c
            return None

        store_name_candidates = [c for c in raw_s.columns if ("门店" in str(c)) and ("ID" not in str(c)) and ("编号" not in str(c))]
        if store_name_candidates:
            tmp = raw_s[store_name_candidates]
            if isinstance(tmp, pd.Series):
                store_name = tmp.astype(str)
            else:
                store_name = tmp.bfill(axis=1).iloc[:, 0]. astype(str)
            store_name = store_name.str.strip()
        else:
            store_name = pd.Series(["" for _ in range(len(raw_s))])

        col_total = pick_col_by_keywords(raw_s, ["质检总分", "总分"], exclude=["显示"])
        col_60s = pick_col_by_keywords(raw_s, ["60秒", "60 秒"], exclude=[])
        col_needs = pick_col_by_keywords(raw_s, ["用车需求"], exclude=[])
        col_car = pick_col_by_keywords(raw_s, ["车型信息"], exclude=[])
        col_policy = pick_col_by_keywords(raw_s, ["政策"], exclude=[])
        col_time = pick_col_by_keywords(raw_s, ["明确到店", "到店时间"], exclude=[])
        col_wechat = pick_col_by_keywords(raw_s, ["添加微信", "加微信", "加微"], exclude=[])

        df_s = pd.DataFrame({"门店名称": store_name})

        if col_total and col_total in raw_s.columns:
            df_s["SR_质检总分"] = _to_1d_numeric(raw_s[col_total])
        else:
            df_s["SR_质检总分"] = np.nan

        if col_60s and col_60s in raw_s.columns:
            df_s["SR_S_60s"] = _to_1d_numeric(raw_s[col_60s])
        else:
            df_s["SR_S_60s"] = np.nan

        if col_needs and col_needs in raw_s.columns:
            df_s["SR_S_Needs"] = _to_1d_numeric(raw_s[col_needs])
        else:
            df_s["SR_S_Needs"] = np.nan

        if col_car and col_car in raw_s.columns:
            df_s["SR_S_Car"] = _to_1d_numeric(raw_s[col_car])
        else:
            df_s["SR_S_Car"] = np.  nan

        if col_policy and col_policy in raw_s.  columns:
            df_s["SR_S_Policy"] = _to_1d_numeric(raw_s[col_policy])
        else:
            df_s["SR_S_Policy"] = np.nan

        if col_wechat and col_wechat in raw_s.columns:
            df_s["SR_S_Wechat"] = _to_1d_numeric(raw_s[col_wechat])
        else:
            df_s["SR_S_Wechat"] = np.nan

        if col_time and col_time in raw_s.columns:
            df_s["SR_S_Time"] = _to_1d_numeric(raw_s[col_time])
        else:
            df_s["SR_S_Time"] = np.nan

        df_s["门店名称"] = df_s["门店名称"].astype(str).str.strip()
        df_s = df_s[df_s["门店名称"]. ne("")].  copy()
        df_s = df_s.drop_duplicates(subset=["门店名称"], keep="first")

        rename_map_ams = {
            "管家姓名": "邀约专员/管家",
            "DCC平均通话时长": "通话时长",
            "DCC接通线索数": "conn_num",
            "DCC外呼线索数": "conn_denom",
            "DCC及时处理线索": "timely_num",
            "需外呼线索数": "timely_denom",
            "二次外呼线索数": "call2_num",
            "需再呼线索数": "call2_denom",
            "DCC三次外呼的线索数": "call3_num",
            "DCC二呼状态为需再呼的线索数": "call3_denom",
        }

        rate_cols_to_keep = ["外呼接通率", "DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"]

        df_a = raw_a.copy()

        for src, tgt in rename_map_ams.items():
            if src in df_a.columns:
                df_a = df_a.rename(columns={src: tgt})

        for col in rate_cols_to_keep:  
            if col in df_a.  columns:
                df_a[col] = pd.to_numeric(df_a[col].  astype(str).str.replace('%', ''), errors="coerce").fillna(0)
                mask = df_a[col] > 1
                if mask.any():
                    df_a.  loc[mask, col] = df_a. loc[mask, col] / 100

        if "邀约专员/管家" not in df_a.  columns:
            df_a["邀约专员/管家"] = ""
        df_a["邀约专员/管家"] = df_a["邀约专员/管家"].astype(str).str.strip()

        all_ams_calc_cols = [
            "conn_num",
            "conn_denom",
            "timely_num",
            "timely_denom",
            "call2_num",
            "call2_denom",
            "call3_num",
            "call3_denom",
        ]

        for c in all_ams_calc_cols:
            if c not in df_a.columns:
                df_a[c] = 0
            df_a[c] = _to_1d_numeric(df_a[c])

        if "通话时长" not in df_a.columns:
            df_a["通话时长"] = 0
        df_a["通话时长"] = _to_1d_numeric(df_a["通话时��"])

        if "外呼接通率" not in df_a.columns:
            df_a["外呼接通率"] = safe_div(df_a, "conn_num", "conn_denom")
        if "DCC及时处理率" not in df_a.columns:
            df_a["DCC及时处理率"] = safe_div(df_a, "timely_num", "timely_denom")
        if "DCC二次外呼率" not in df_a.  columns:
            df_a["DCC二次外呼率"] = safe_div(df_a, "call2_num", "call2_denom")
        if "DCC三次外呼率" not in df_a. columns:
            df_a["DCC三次外呼率"] = safe_div(df_a, "call3_num", "call3_denom")

        for rate_col in ["外呼接通率", "DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"]:
            if rate_col in df_a. columns:
                df_a[rate_col] = pd.to_numeric(df_a[rate_col], errors="coerce").fillna(0)
                mask = df_a[rate_col] > 1
                if mask.any():
                    df_a.loc[mask, rate_col] = df_a.loc[mask, rate_col] / 100
                df_a[rate_col] = df_a[rate_col].  clip(0, 1)

        # ✅ 标准化所有邀约专员/管家列和门店名列
        for df in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
            if "邀约专员/管家" in df.columns:
                df["邀约专员/管家"] = df["邀约专员/管家"].astype(str).str.strip().str.lower()
            if "门店名称" in df.columns:
                df["门店名称"] = df["门店名称"]. astype(str).str.strip()

        # ✅ 改进的合并逻辑：DCC按顾问合并，AMS按门店汇总
        full_advisors = df_advisor_data. copy()

        # 合并DCC数据（按顾问名）
        if "邀约专员/管家" in df_d.columns:
            full_advisors = pd.merge(full_advisors, df_d, on="邀约专员/管家", how="left", suffixes=("", "_dcc"))

        # 按门店汇总AMS数据（因为AMS表中顾问名和漏斗表不一致）
        if "门店名称" in df_a.columns and len(all_ams_calc_cols) > 0:
            ams_by_store = df_a.groupby("门店名称").agg({
                "conn_num": "sum",
                "conn_denom": "sum",
                "timely_num": "sum",
                "timely_denom": "sum",
                "call2_num":  "sum",
                "call2_denom": "sum",
                "call3_num": "sum",
                "call3_denom": "sum",
                "通话时长": "mean"
            }).reset_index()
            
            # 计算汇总后的比率
            ams_by_store["外呼接通率"] = safe_div(ams_by_store, "conn_num", "conn_denom")
            ams_by_store["DCC及时处理率"] = safe_div(ams_by_store, "timely_num", "timely_denom")
            ams_by_store["DCC二次外呼率"] = safe_div(ams_by_store, "call2_num", "call2_denom")
            ams_by_store["DCC三次外呼率"] = safe_div(ams_by_store, "call3_num", "call3_denom")
            
            # 和顾问数据按门店合并
            full_advisors = pd.merge(full_advisors, ams_by_store, on="门店名称", how="left")
        else:
            # 如果没有门店名，直接按顾问名合并AMS
            full_advisors = pd.merge(full_advisors, df_a[["邀约专员/管家"] + [c for c in df_a.columns if c not in ["邀约专员/管家", "门店名称"]]], 
                                   on="邀约专员/管家", how="left", suffixes=("", "_ams"))

        st.  write(f"顾问明细行数: {len(df_advisor_data)}")
        st.write(f"DCC表行数: {len(df_d)}")
        st.write(f"AMS表行数:   {len(df_a)}")
        st.write(f"合并后行数: {len(full_advisors)}")
        st.write(f"合并后有AMS数据的行:   {full_advisors['conn_num'].notna().sum()}")
        st.write(f"样本顾问名称（漏斗）: {df_advisor_data['邀约专员/管家'].head(3).tolist()}")
        st.write(f"样本顾问名称（AMS）: {df_a['邀约专员/管家'].head(3).tolist()}")

        cols_to_fill_zero = ["线索量", "到店量", "通话时长"] + all_ams_calc_cols
        for c in cols_to_fill_zero:
            if c in full_advisors.columns:
                full_advisors[c] = pd.to_numeric(full_advisors[c], errors="coerce").fillna(0)

        ams_agg_dict = {c: "sum" for c in all_ams_calc_cols}
        if "门店名称" in full_advisors.columns and all(c in full_advisors.  columns for c in all_ams_calc_cols):
            store_ams = full_advisors. groupby("门店名称").agg(ams_agg_dict).reset_index()
        else:
            store_ams = pd.DataFrame(columns=["门店名称"] + all_ams_calc_cols)

        if not store_ams.empty:
            store_ams["外呼接通率"] = safe_div(store_ams, "conn_num", "conn_denom")
            store_ams["DCC及时处理率"] = safe_div(store_ams, "timely_num", "timely_denom")
            store_ams["DCC二次外呼率"] = safe_div(store_ams, "call2_num", "call2_denom")
            store_ams["DCC三次外呼率"] = safe_div(store_ams, "call3_num", "call3_denom")

        full_stores = pd.merge(df_store_data, df_s, on="门店名称", how="left")
        full_stores = pd.merge(full_stores, store_ams, on="门店名称", how="left")

        full_stores["质检总分"] = full_stores.  get("SR_质检总分")
        full_stores["S_60s"] = full_stores. get("SR_S_60s")
        full_stores["S_Needs"] = full_stores. get("SR_S_Needs")
        full_stores["S_Car"] = full_stores. get("SR_S_Car")
        full_stores["S_Policy"] = full_stores.get("SR_S_Policy")
        full_stores["S_Wechat"] = full_stores.get("SR_S_Wechat")
        full_stores["S_Time"] = full_stores.get("SR_S_Time")

        full_stores.  drop(columns=[c for c in full_stores.  columns if str(c).startswith("SR_")], inplace=True, errors="ignore")

        full_stores.  columns = dedupe_columns(full_stores.  columns)

        return full_advisors, full_stores

    except Exception as e:
        st. error(f"处理出错: {e}")
        import traceback
        st.text(traceback.format_exc())
        return None, None


with st.sidebar:
    st.header("⚙️ 管理面板")

    store_rank_path = get_store_rank_path()
    has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and (store_rank_path is not None)

    if has_data:
        st.success("✅ 数据状态：已就绪")
    else:
        st.warning("⚠️ 暂无数据")
    st.markdown("---")

    with st.expander("🔐 更新数据 (仅限管理员)"):
        pwd = st.text_input("输入管理员密码", type="password")
        if pwd == ADMIN_PASSWORD:
            st.  info("🔓 请上传新文件：")
            new_f = st.file_uploader("1. 漏斗指标表", type=["xlsx", "csv"], key="up_f")
            new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"], key="up_d")
            new_a = st.file_uploader("3. AMS跟进表", type=["xlsx", "csv"], key="up_a")
            new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"], key="up_s")

            if st.button("🚀 确认更新数据"):
                if new_f and new_d and new_a and new_s:
                    with st.spinner("正在保存数据..."):
                        save_uploaded_file(new_f, PATH_F)
                        save_uploaded_file(new_d, PATH_D)
                        save_uploaded_file(new_a, PATH_A)

                        if str(new_s. name).lower().endswith(". xlsx"):
                            if os.path.exists(PATH_S_CSV):
                                try:
                                    os.remove(PATH_S_CSV)
                                except Exception:  
                                    pass
                            save_uploaded_file(new_s, PATH_S_XLSX)
                        else:
                            if os.path.exists(PATH_S_XLSX):
                                try: 
                                    os.  remove(PATH_S_XLSX)
                                except Exception:  
                                    pass
                            save_uploaded_file(new_s, PATH_S_CSV)

                        try:
                            with open(LAST_UPDATE_FILE, "w", encoding="utf-8") as f:
                                f.write(datetime.now().isoformat(timespec="seconds"))
                        except Exception: 
                            pass

                    st.success("更新完成，正在刷新...")
                    st.rerun()
                else:
                    st.error("请传齐 4 个文件")


store_rank_path = get_store_rank_path()
has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and (store_rank_path is not None)

if has_data:
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, store_rank_path)

    if df_advisors is not None:  
        col_header, col_update, col_filter = st.columns([2. 4, 1.2, 1])
        with col_header:
            st.title("Audi | DCC 效能看板")

        with col_update:
            upd = get_data_update_time(store_rank_path)
            upd_text = upd.strftime("%Y-%m-%d %H:%M") if upd else "暂无"
            st.markdown(
                f"""
                <div style='text-align: right; padding-top: 12px;'>
                  <span style='display: inline-block; padding: 6px 10px; border-radius: 999px; border: 1px solid rgba(49, 51, 63, 0.18); background:  rgba(49, 51, 63, 0.06); font-size: 12px;'>
                    🕒 数据更新时间：<b>{upd_text}</b>
                  </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_filter:
            if df_stores is not None and not df_stores.empty and "门店名称" in df_stores.columns:
                all_stores = sorted(list(df_stores["门店名称"].dropna().unique()))
            else:
                all_stores = sorted(list(df_advisors.  get("门店名称", pd.Series(dtype=str)).dropna().unique()))
            store_options = ["全部"] + all_stores
            selected_store = st.selectbox("🏭 切换门店视图", store_options)

        if selected_store == "全部":
            current_df = df_stores.  copy() if df_stores is not None else pd.DataFrame()
            current_df["名称"] = current_df.  get("门店名称", "")
            rank_title = "🏆 全区门店排名"
            kpi_leads = current_df. get("线索量", pd.Series(dtype=float)).sum()
            kpi_visits = current_df. get("到店量", pd. Series(dtype=float)).sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df.get("质检总分", pd.Series(dtype=float)).mean() if "质检总分" in current_df.columns else 0
        else:
            current_df = df_advisors[df_advisors.  get("门店名称", "") == selected_store].  copy()
            current_df["名称"] = current_df. get("邀约专员/管家", "")
            rank_title = f"👤 {selected_store} - 顾问排名"
            kpi_leads = current_df.get("线索量", pd.Series(dtype=float)).sum()
            kpi_visits = current_df.  get("到店量", pd.  Series(dtype=float)).sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df.get("质检总分", pd.  Series(dtype=float)).mean() if "质检总分" in current_df.columns else 0

        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")

        st.markdown("---")
        st.subheader("2️⃣ DCC 外呼过程监控 (Process)")

        def calc_kpi_rate(df, num, denom):
            if num not in df.columns or denom not in df.columns:
                return 0
            total_num = pd.to_numeric(df[num], errors="coerce").fillna(0).sum()
            total_denom = pd.to_numeric(df[denom], errors="coerce").fillna(0).sum()
            return total_num / total_denom if total_denom > 0 else 0

        p1, p2, p3, p4 = st.columns(4)
        avg_conn = calc_kpi_rate(current_df, "conn_num", "conn_denom")
        avg_timely = calc_kpi_rate(current_df, "timely_num", "timely_denom")
        avg_call2 = calc_kpi_rate(current_df, "call2_num", "call2_denom")
        avg_call3 = calc_kpi_rate(current_df, "call3_num", "call3_denom")

        p1.metric("📞 外呼接通率", f"{avg_conn:.1%}")
        p2.metric("⚡ DCC及时处理率", f"{avg_timely:. 1%}")
        p3.metric("🔄 二次外呼率", f"{avg_call2:. 1%}")
        p4.metric("🔁 三次外呼率", f"{avg_call3:.1%}")
        st.caption("注：以上为加权平均值（sum/sum）")

        plot_df_vis = current_df.  copy()
        if "质检总分" in plot_df_vis.columns:
            plot_df_vis["质检总分_显示"] = plot_df_vis["质检总分"]. fillna(0)
        else:
            plot_df_vis["质检总分_显示"] = 0

        c_proc_1, c_proc_2 = st.columns(2)
        with c_proc_1:
            st.markdown("#### 🕵️ 异常侦测：外呼接通率 vs 60秒通话占比")
            st.info("💡 右下角（接通率高但60秒占比低）通常代表：可能存在话术弱/人为压时长。")

            if "S_60s" in plot_df_vis.columns and "外呼接通率" in plot_df_vis.columns:
                fig_p1 = px.scatter(
                    plot_df_vis,
                    x="外呼接通率",
                    y="S_60s",
                    size="线索量" if "线索量" in plot_df_vis.columns else None,
                    color="质检总分_显示",
                    hover_name="名称",
                    labels={"外呼接通率": "外呼接通率", "S_60s": "60秒通话占比得分"},
                    color_continuous_scale="RdYlGn",
                    height=350,
                )
                fig_p1.add_vline(x=avg_conn, line_dash="dash", line_color="gray")
                if "S_60s" in plot_df_vis.columns:
                    fig_p1.add_hline(y=pd.to_numeric(plot_df_vis["S_60s"], errors="coerce").fillna(0).mean(), line_dash="dash", line_color="gray")
                fig_p1.update_layout(xaxis=dict(tickformat=". 0%"))
                st.plotly_chart(fig_p1, use_container_width=True)
            else:
                st.warning("缺少外呼接通率或60秒通话数据，无法绘图")

        with c_proc_2:
            st.markdown("#### 🔗 归因分析：过程指标 vs 线索首邀到店率")
            st.info("💡 观察外呼及时性与邀约到店率相关性。")

            x_axis_choice = st.radio("选择横轴指标：", ["DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"], horizontal=True)
            plot_df_corr = plot_df_vis. copy()

            plot_df_corr["线索到店率_显示"] = pd.to_numeric(plot_df_corr.  get("线索到店率_数值", 0), errors="coerce").fillna(0).clip(0, 1)

            if x_axis_choice in plot_df_corr.columns:
                plot_df_corr[x_axis_choice] = pd.to_numeric(plot_df_corr[x_axis_choice], errors="coerce").fillna(0).clip(0, 1)

                fig_p2 = px.  scatter(
                    plot_df_corr,
                    x=x_axis_choice,
                    y="线索到店率_显示",
                    size="线索量" if "线索量" in plot_df_corr.columns else None,
                    color="质检总分_显示",
                    hover_name="名称",
                    labels={x_axis_choice: x_axis_choice, "线索到店率_显示": "线索到店率"},
                    color_continuous_scale="Blues",
                    height=300,
                )

                fig_p2.update_xaxes(range=[0, 1.02], tickformat=".0%", tick0=0, dtick=0.2)
                fig_p2.update_yaxes(tickformat=".1%")

                fig_p2.update_traces(cliponaxis=False)
                fig_p2.update_layout(margin=dict(r=70))

                if "线索量" in plot_df_corr.columns:
                    fig_p2.update_traces(
                        customdata=np.stack(
                            (
                                pd.to_numeric(plot_df_corr["线索量"], errors="coerce").fillna(0),
                                plot_df_corr[x_axis_choice],
                                plot_df_corr["线索到店率_显示"],
                                pd.to_numeric(plot_df_corr["质检总分_显示"], errors="coerce").fillna(0),
                            ),
                            axis=-1,
                        ),
                        cliponaxis=False,
                        hovertemplate=(
                            "<b>%{hovertext}</b><br><br>"
                            "线索量:   %{customdata[0]: ,.  0f}<br>"
                            + f"{x_axis_choice}: %{{customdata[1]:.1%}}<br>"
                            "线索到店率: %{customdata[2]:.1%}<br>"
                            "质检总分: %{customdata[3]:.1f}<br>"
                            "<extra></extra>"
                        ),
                    )
                else:
                    fig_p2.update_traces(
                        customdata=np.stack(
                            (
                                plot_df_corr[x_axis_choice],
                                plot_df_corr["线索到店率_显示"],
                                pd.to_numeric(plot_df_corr["质检总分_显示"], errors="coerce").fillna(0),
                            ),
                            axis=-1,
                        ),
                        hovertemplate=(
                            "<b>%{hovertext}</b><br><br>"
                            + f"{x_axis_choice}: %{{customdata[0]:.1%}}<br>"
                            "线索到店率: %{customdata[1]:.1%}<br>"
                            "质检总分: %{customdata[2]:.1f}<br>"
                            "<extra></extra>"
                        ),
                    )

                st.plotly_chart(fig_p2, use_container_width=True)
            else:
                st.warning("当前视图缺少所选过程指标列，无法绘图")

        st.markdown("---")

        c_left, c_right = st.columns([1, 2])
        with c_left:
            st.markdown(f"### 🏆 {rank_title}")
            if all(c in current_df.columns for c in ["名称", "线索到店率", "线索到店率_数值"]):
                rank_df = current_df[["名称", "线索到店率", "线索到店率_数值"]].copy()
                if "质检总分" in current_df.columns:
                    rank_df["质检总分"] = current_df["质检总分"]
                else:
                    rank_df["质检总分"] = 0

                rank_df["Sort_Score"] = pd.to_numeric(rank_df["线索到店率_数值"], errors="coerce").fillna(-1)
                rank_df = rank_df.sort_values("Sort_Score", ascending=False).head(15)
                display_df = rank_df[["名称", "线索到店率", "质检总���"]]

                st.dataframe(
                    display_df,
                    hide_index=True,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "名称": st.column_config.  TextColumn("名称"),
                        "线索到店率": st.column_config.  TextColumn("线索到店率"),
                        "质检总分": st.column_config. NumberColumn("质检总分", format="%.1f"),
                    },
                )
            else:
                st.warning("当前视图缺少排行必需列")

        with c_right:  
            st.markdown("### 💡 话术质量 vs 转化结果")
            if "S_Time" in plot_df_vis.columns:
                plot_df = plot_df_vis.copy()
                plot_df["转化率%"] = pd.to_numeric(plot_df.  get("线索到店率_数值", 0), errors="coerce").fillna(0) * 100
                fig = px.scatter(
                    plot_df,
                    x="S_Time",
                    y="转化率%",
                    size="线索量" if "线索量" in plot_df.columns else None,
                    color="质检总分_显示",
                    hover_name="名称",
                    labels={"S_Time": "明确到店时间得分", "转化率%":   "线索到店率(%)"},
                    color_continuous_scale="Reds",
                    height=400,
                )

                s60 = pd.to_numeric(plot_df.  get("S_60s", 0), errors="coerce").fillna(0)
                total = pd.to_numeric(plot_df.  get("质检总分", 0), errors="coerce").fillna(0)
                leads = pd.to_numeric(plot_df. get("线索量", 0), errors="coerce").fillna(0)
                fig.update_traces(
                    customdata=np.stack((leads, s60, total), axis=-1),
                    hovertemplate=(
                        "<b>%{hovertext}</b><br><br>"
                        "明确到店时间得分: %{x: .  1f}<br>"
                        "线索到店率: %{y:.1f}%<br>"
                        "线索量: %{customdata[0]:,. 0f}<br>"
                        "60秒通话占比得分: %{customdata[1]:.1f}<br>"
                        "质检总分: %{customdata[2]:.1f}<br>"
                        "<extra></extra>"
                    ),
                )

                if not plot_df.  empty:
                    fig.add_vline(x=pd.to_numeric(plot_df["S_Time"], errors="coerce").fillna(0).mean(), line_dash="dash", line_color="gray")
                    fig.add_hline(y=kpi_rate * 100, line_dash="dash", line_color="gray")

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("缺少明确到店时间数据无法绘图")

        st.markdown("---")

        with st.container():
            st.markdown("### 🕵️‍♀️ 邀约专员/管家深度诊断")
            if selected_store == "全部":  
                st.info("💡 请先选择具体门店查看该门店下的顾问详细诊断。")
            else:
                diag_df = current_df. copy()
                if "线索量" in diag_df.columns:
                    diag_df = diag_df[pd.to_numeric(diag_df["线索量"], errors="coerce").fillna(0) > 0].  copy()

                if "邀约专员/管家" in diag_df.columns:
                    diag_list = sorted(diag_df["邀约专员/管家"].dropna().astype(str).unique())
                else:
                    diag_list = []

                if diag_list:
                    selected_person = st.selectbox("🔍 选择该店邀约专员/管家：", diag_list)
                    p_row = df_advisors[df_advisors["邀约专员/管家"] == selected_person.  lower()]
                    if p_row.empty:
                        st.warning("找不到该人员明细")
                    else:
                        p = p_row.iloc[0]

                        d1, d2, d3 = st.columns([1, 1, 1.2])
                        with d1:
                            st.caption("转化漏斗 (RESULT)")
                            leads = float(pd.to_numeric(p.  get("线索量", 0), errors="coerce") or 0)
                            visits = float(pd.to_numeric(p. get("到店量", 0), errors="coerce") or 0)

                            fig_f = go.Figure(
                                go.Funnel(
                                    y=["线索量", "到店量"],
                                    x=[leads, visits],
                                    textinfo="value+percent initial",
                                    marker={"color": ["#d9d9d9", "#bb0a30"]},
                                )
                            )
                            fig_f.update_layout(showlegend=False, height=180, margin=dict(t=0, b=0, l=0, r=0))
                            st.plotly_chart(fig_f, use_container_width=True)

                            st.metric("线索到店率", p.  get("线索到店率", "0.0%"))
                            avg_call_dur = float(pd.to_numeric(p.get("通话时长", 0), errors="coerce") or 0)
                            st.caption(f"平均通话时长: {avg_call_dur:.1f} 秒")

                        has_score = ("质检总分" in p.  index) and (not pd.isna(p.get("质检总分")))

                        with d2:
                            st.  caption("质检得分详情 (QUALITY)")
                            if has_score:
                                metrics = {
                                    "明确到店时间":   p.get("S_Time", np.nan),
                                    "60秒通话占比":  p.get("S_60s", np.nan),
                                    "用车需求": p.get("S_Needs", np.nan),
                                    "车型信息介绍": p.get("S_Car", np.nan),
                                    "政策相关话术": p.get("S_Policy", np.nan),
                                    "添加微信": p.get("S_Wechat", np.nan),
                                }
                                for k, v in metrics.items():
                                    val = 0 if pd.isna(v) else float(v)
                                    c_a, c_b = st.columns([3, 1])
                                    c_a.progress(min(val / 100, 1.0))
                                    c_b.write(f"{val:.1f}")
                                    st.caption(k)
                            else:
                                st.warning("暂无质检数据")

                        with d3:
                            if has_score:
                                st.error("🤖 AI 智能诊断建议")
                                val_60s = 0 if pd.isna(p.get("S_60s", np.nan)) else float(p.get("S_60s"))

                                other_kpis = {
                                    "明确到店":   (p.get("S_Time", np.nan), "建议使用二选一法锁定时间。"),
                                    "添加微信": (p.get("S_Wechat", np.nan), "建议以发定位/资料为由加微。"),
                                    "用车需求": (p.get("S_Needs", np.nan), "需加强需求挖掘，至少问清场景/预算/家庭结构。"),
                                    "车型信息":   (p.get("S_Car", np.nan), "需提升产品讲解链路，先讲1-2个强卖点。"),
                                    "政策相关":  (p.get("S_Policy", np.nan), "需准确传达政策，并用截止时间推动决策。"),
                                }

                                issues_list = []
                                is_failing = False

                                if val_60s < 60:
                                    msg = "开场先抛利益点 + 明确下一步动作。"
                                    issues_list.append(f"🟠 **60秒占比 (得分{val_60s:.1f})** {msg}")
                                    is_failing = True

                                cleaned_others = {}
                                for k, (v, advice) in other_kpis.items():
                                    score = 0 if pd.isna(v) else float(v)
                                    cleaned_others[k] = (score, advice)
                                    if score < 80:
                                        issues_list.append(f"🔴 **{k} (得分{score:.1f})** {advice}")
                                        is_failing = True

                                if is_failing: 
                                    for item in issues_list:
                                        st.markdown(item)
                                    st.warning("⚠️ 存在明显短板，请重点辅导。")
                                else:
                                    all_above_85 = all(score >= 85 for score, _ in cleaned_others.values())
                                    if all_above_85:
                                        st.success("🌟 各项指标表现优秀！")
                                    else:  
                                        st.info("✅ 各项指标合格，但仍有提升空间。")
                            else:
                                st.info("暂无数据，无法生成诊断建议。")
                else:
                    st.warning("该门店下暂无数据。")
else:
    st.info("👋 欢迎使用 Audi 效能看板！")
    st.warning("👉 目前暂无数据。请在左侧侧边栏展开【更新数据】，输入管理员密码并上传所有 4 个数据文件。")
