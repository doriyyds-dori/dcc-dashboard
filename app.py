import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
from datetime import datetime

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown(
    """
<style>
    .top-container {display: flex; align-items: center; justify-content: space-between; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;}
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    .big-font {font-size: 18px !important; font-weight: bold;}
</style>
""",
    unsafe_allow_html=True,
)

# ================= 2. 安全锁、文件存储与邮件配置 =================
ADMIN_PASSWORD = "AudiSARR3"

DATA_DIR = "data_store"
os.makedirs(DATA_DIR, exist_ok=True)

# 1) 漏斗 / 2) 顾问质检 / 3) AMS
PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")

# ✅ 4) 门店排名：真实后缀保存，读取时自动选存在的那个
PATH_S_XLSX = os.path.join(DATA_DIR, "store_rank.xlsx")
PATH_S_CSV = os.path.join(DATA_DIR, "store_rank.csv")


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


# ================= 3. 工具函数（读取/清洗/计算） =================
def dedupe_columns(columns):
    """把重复列名变成: 列名, 列名__1, 列名__2 ..."""
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
    """鲁棒读取（xlsx/csv/误后缀 xlsx）+ 自动找表头 + 列名去重。

    - 误把 xlsx 存成 csv 后缀：通过文件签名 PK.. 识别并按 xlsx 读
    - csv：多编码尝试
    - 自动在前 12 行找表头（适配门店排名表第一行是标题）
    """
    if not file_path or not os.path.exists(file_path):
        return None

    df = None

    # 兜底：签名判断（xlsx 是 zip：PK..）
    try:
        with open(file_path, "rb") as f:
            sig = f.read(4)
        if sig == b"PK":
            df = pd.read_excel(file_path, header=None)
    except Exception:
        pass

    if df is None:
        is_csv = str(file_path).lower().endswith((".csv", ".txt"))
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

    # 智能找表头
    keywords = ["门店", "顾问", "管家", "排名", "代理商", "序号", "线索", "质检", "添加微信"]
    header_row = 0

    search_rows = 15 if is_rank_file else 12
    for i in range(min(search_rows, len(df))):
        row_values = df.iloc[i].astype(str).str.cat(sep=",")
        if any(k in row_values for k in keywords):
            header_row = i
            break

    df.columns = df.iloc[header_row]
    df = df[header_row + 1 :].reset_index(drop=True)

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\n", "", regex=False)
        .str.replace("\r", "", regex=False)
    )

    df.columns = dedupe_columns(df.columns)

    # 删掉全空列
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
        return 0
    num = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
    denom = pd.to_numeric(df[denom_col], errors="coerce").fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)


def _to_1d_numeric(x):
    """把 Series 或（同名列导致的）DataFrame 压成 1 列数值 Series。"""
    if isinstance(x, pd.DataFrame):
        tmp = x.apply(pd.to_numeric, errors="coerce")
        return tmp.bfill(axis=1).iloc[:, 0].fillna(0)
    return pd.to_numeric(x, errors="coerce").fillna(0)


def _pick_first_col(df: pd.DataFrame, include_keywords, exclude_keywords=None):
    exclude_keywords = exclude_keywords or []
    for c in df.columns:
        s = str(c)
        if all(k in s for k in include_keywords) and not any(x in s for x in exclude_keywords):
            return c
    return None


def _pick_any_col(df: pd.DataFrame, any_keywords, exclude_keywords=None):
    exclude_keywords = exclude_keywords or []
    for c in df.columns:
        s = str(c)
        if any(k in s for k in any_keywords) and not any(x in s for x in exclude_keywords):
            return c
    return None


def _col_as_series(df: pd.DataFrame, col_name: str):
    """df[col] 可能因为重复列名返回 DataFrame；这里统一压成 1D Series。"""
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

        # ================= A. Funnel (漏斗) =================
        store_col = _pick_any_col(raw_f, ["代理商", "门店"]) or raw_f.columns[0]
        name_col = _pick_any_col(raw_f, ["管家", "顾问", "邀约"]) or raw_f.columns[1]

        col_leads = "线上_有效线索数" if "线上_有效线索数" in raw_f.columns else ("线索量" if "线索量" in raw_f.columns else _pick_any_col(raw_f, ["有效线索", "线索数"]))
        col_visits = "线上_到店数" if "线上_到店数" in raw_f.columns else ("到店量" if "到店量" in raw_f.columns else _pick_any_col(raw_f, ["到店数", "到店量"]))

        col_excel_rate = _pick_any_col(raw_f, ["率"], exclude_keywords=["试驾", "成交"])  # 尽量拿到“到店率”那列

        rename_dict = {store_col: "门店名称", name_col: "邀约专员/管家"}
        if col_leads:
            rename_dict[col_leads] = "线索量"
        if col_visits:
            rename_dict[col_visits] = "到店量"
        if col_excel_rate:
            rename_dict[col_excel_rate] = "Excel_Rate"

        df_f = raw_f.rename(columns=rename_dict)
        # 防止 rename 后出现重复列名（会导致 df['门店名称'] 变成 DataFrame）
        df_f.columns = dedupe_columns(df_f.columns)

        # 小计/合计行
        mask_sub = df_f["邀约专员/管家"].astype(str).str.contains("小计|合计|总计", na=False)
        df_store_data = df_f[mask_sub].copy()

        # 顾问明细：排除小计/空/分隔符
        mask_bad = df_f["邀约专员/管家"].astype(str).str.strip().isin(["", "-", "—", "nan"])
        df_advisor_data = df_f[~mask_sub & ~mask_bad].copy()

        for df in [df_store_data, df_advisor_data]:
            df["线索量"] = pd.to_numeric(df.get("线索量", 0), errors="coerce").fillna(0)
            df["到店量"] = pd.to_numeric(df.get("到店量", 0), errors="coerce").fillna(0)

            if "Excel_Rate" in df.columns:
                clean_percent_col(df, "Excel_Rate")
                df["线索到店率_数值"] = df["Excel_Rate"]
            else:
                df["线索到店率_数值"] = safe_div(df, "到店量", "线索量")

            df["线索到店率"] = (df["线索到店率_数值"] * 100).map("{:.1f}%".format)

        # ================= B. DCC (顾问质检) =================
        df_d = raw_d.rename(

            columns={
                "顾问名称": "邀约专员/管家",
                "管家": "邀约专员/管家",
                "质检总分": "质检总分",
                "60秒通话": "S_60s",
                "用车需求": "S_Needs",
                "车型信息": "S_Car",
                "政策相关": "S_Policy",
                "明确到店时间": "S_Time",
            }
        )

        # 防止 rename 后出现重复列名（避免 df['邀约专员/管家'] / df['门店名称'] 变成 DataFrame）
        df_d.columns = dedupe_columns(df_d.columns)

        # 添加微信：可能重复列名，取第一列
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

        # ================= C. Store Scores (门店质检) =================
        df_s = raw_s.rename(
            columns={
                "60秒通话": "S_60s",
                "用车需求": "S_Needs",
                "车型信息": "S_Car",
                "政策相关": "S_Policy",
                "明确到店时间": "S_Time",
            }
        )

        # 门店名称：可能同时存在“门店名称 / 门店名称__1 / 门店”等多列，先合并成唯一的“门店名称”
        store_name_cols = [c for c in df_s.columns if ("门店" in str(c)) and ("ID" not in str(c))]
        if not store_name_cols:
            df_s["门店名称"] = ""
        else:
            tmp = df_s[store_name_cols]
            if isinstance(tmp, pd.Series):
                df_s["门店名称"] = tmp.astype(str).str.strip()
            else:
                df_s["门店名称"] = tmp.bfill(axis=1).iloc[:, 0].astype(str).str.strip()
            # 删除多余门店列（保留门店名称）
            drop_cols = [c for c in store_name_cols if c != "门店名称"]
            df_s.drop(columns=drop_cols, inplace=True, errors="ignore")

        # 再次确保列名唯一（避免 merge 报 The column label '门店名称' is not unique）
        df_s.columns = dedupe_columns(df_s.columns)

        s_wechat_cols = [c for c in df_s.columns if ("微信" in str(c) and "添加" in str(c)) or ("添加微信" in str(c))]
        if s_wechat_cols:
            df_s["S_Wechat"] = _to_1d_numeric(df_s[s_wechat_cols])
        else:
            df_s["S_Wechat"] = 0

        store_score_cols = ["门店名称", "质检总分", "S_60s", "S_Needs", "S_Car", "S_Policy", "S_Wechat", "S_Time"]
        available_store_cols = [c for c in store_score_cols if c in df_s.columns]
        df_s = df_s[available_store_cols]
        for c in available_store_cols:
            if c != "门店名称":
                df_s[c] = pd.to_numeric(df_s[c], errors="coerce")

        # ================= D. AMS (跟进数据) =================
        # 你原来的 cols_config 思路保留，但修复“未接通误命中/重复列导致 DataFrame”
        cols_config = [
            (["管家姓名", "顾问姓名", "顾问名称", "管家"], "邀约专员/管家", []),
            (["DCC平均通话时长", "平均通话时长"], "通话时长", []),
            (["DCC接通线索数", "接通线索数"], "conn_num", ["未接通"]),
            (["DCC外呼线索数", "外呼线索数"], "conn_denom", []),
            (["DCC及时处理线索", "及时处理线索"], "timely_num", []),
            (["需外呼线索数", "需外呼"], "timely_denom", []),
            (["二次外呼线索数", "二次外呼"], "call2_num", []),
            (["需再呼线索数", "需再呼"], "call2_denom", []),
            (["DCC三次外呼的线索数", "三次外呼线索数", "三次外呼"], "call3_num", []),
            (["DCC二呼状态为需再呼的线索数", "二呼状态为需再呼", "三次外呼分母"], "call3_denom", []),
        ]

        # 目标名 -> 源列（只取一个，避免重复）
        target_to_src = {}
        for any_kw, target_name, exclude_kw in cols_config:
            if target_name in target_to_src:
                continue
            found = None
            for col in raw_a.columns:
                s = str(col).strip()
                if any(k in s for k in any_kw) and not any(ex in s for ex in exclude_kw):
                    found = col
                    break
            if found is not None:
                target_to_src[target_name] = found

        rename_map = {src: tgt for tgt, src in target_to_src.items()}
        df_a = raw_a.rename(columns=rename_map)

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

        if "邀约专员/管家" not in df_a.columns:
            df_a["邀约专员/管家"] = ""

        for c in all_ams_calc_cols:
            if c not in df_a.columns:
                df_a[c] = 0
            df_a[c] = _to_1d_numeric(df_a[c])

        if "通话时长" not in df_a.columns:
            df_a["通话时长"] = 0
        df_a["通话时长"] = _to_1d_numeric(df_a["通话时长"])

        # 个人层面的率计算
        df_a["外呼接通率"] = safe_div(df_a, "conn_num", "conn_denom")
        df_a["DCC及时处理率"] = safe_div(df_a, "timely_num", "timely_denom")
        df_a["DCC二次外呼率"] = safe_div(df_a, "call2_num", "call2_denom")
        df_a["DCC三次外呼率"] = safe_div(df_a, "call3_num", "call3_denom")

        final_ams_cols = (
            ["邀约专员/管家", "通话时长", "外呼接通率", "DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"]
            + all_ams_calc_cols
        )
        final_ams_cols = [c for c in final_ams_cols if c in df_a.columns]
        df_a = df_a[final_ams_cols]

        # ================= E. Merge (合并数据) =================
        for df in [df_store_data, df_advisor_data, df_d, df_a, df_s]:
            if "邀约专员/管家" in df.columns:
                s = _col_as_series(df, "邀约专员/管家")
                if s is not None:
                    df["邀约专员/管家"] = s.astype(str).str.strip()
            if "门店名称" in df.columns:
                s2 = _col_as_series(df, "门店名称")
                if s2 is not None:
                    df["门店名称"] = s2.astype(str).str.strip()

        # 1) 顾问全量表
        full_advisors = pd.merge(df_advisor_data, df_d, on="邀约专员/管家", how="left")
        full_advisors = pd.merge(full_advisors, df_a, on="邀约专员/管家", how="left")

        cols_to_fill_zero = ["线索量", "到店量", "通话时长"] + all_ams_calc_cols
        for c in cols_to_fill_zero:
            if c in full_advisors.columns:
                full_advisors[c] = pd.to_numeric(full_advisors[c], errors="coerce").fillna(0)

        # 2) 门店全量表：从顾问加总 AMS
        ams_agg_dict = {c: "sum" for c in all_ams_calc_cols}
        if "门店名称" in full_advisors.columns and all(c in full_advisors.columns for c in all_ams_calc_cols):
            store_ams = full_advisors.groupby("门店名称").agg(ams_agg_dict).reset_index()
        else:
            store_ams = pd.DataFrame(columns=["门店名称"] + all_ams_calc_cols)

        # 门店级率
        if not store_ams.empty:
            store_ams["外呼接通率"] = safe_div(store_ams, "conn_num", "conn_denom")
            store_ams["DCC及时处理率"] = safe_div(store_ams, "timely_num", "timely_denom")
            store_ams["DCC二次外呼率"] = safe_div(store_ams, "call2_num", "call2_denom")
            store_ams["DCC三次外呼率"] = safe_div(store_ams, "call3_num", "call3_denom")

        full_stores = pd.merge(df_store_data, df_s, on="门店名称", how="left")
        full_stores = pd.merge(full_stores, store_ams, on="门店名称", how="left")

        return full_advisors, full_stores

    except Exception as e:
        st.error(f"处理出错: {e}")
        import traceback

        st.text(traceback.format_exc())
        return None, None


# ================= 4. 侧边栏逻辑（放到函数后，避免 NameError） =================
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
            st.info("🔓 请上传新文件：")
            new_f = st.file_uploader("1. 漏斗指标表", type=["xlsx", "csv"], key="up_f")
            new_d = st.file_uploader("2. 顾问质检表", type=["xlsx", "csv"], key="up_d")
            new_a = st.file_uploader("3. AMS跟进表", type=["xlsx", "csv"], key="up_a")
            new_s = st.file_uploader("4. 门店排名表", type=["xlsx", "csv"], key="up_s")

            # ✅ 已取消：异常邮件功能（避免环境/账号配置导致更新失败）

            if st.button("🚀 确认更新数据"):
                if new_f and new_d and new_a and new_s:
                    with st.spinner("正在保存数据..."):
                        save_uploaded_file(new_f, PATH_F)
                        save_uploaded_file(new_d, PATH_D)
                        save_uploaded_file(new_a, PATH_A)

                        # 门店排名：按真实后缀保存，避免 xlsx 被误存为 csv 造成乱码
                        if str(new_s.name).lower().endswith(".xlsx"):
                            # 删除旧 csv（如果存在）
                            if os.path.exists(PATH_S_CSV):
                                try:
                                    os.remove(PATH_S_CSV)
                                except Exception:
                                    pass
                            save_uploaded_file(new_s, PATH_S_XLSX)
                        else:
                            # 删除旧 xlsx（如果存在）
                            if os.path.exists(PATH_S_XLSX):
                                try:
                                    os.remove(PATH_S_XLSX)
                                except Exception:
                                    pass
                            save_uploaded_file(new_s, PATH_S_CSV)

                    st.success("更新完成，正在刷新...")
                    st.rerun()
                else:
                    st.error("请传齐 4 个文件")


# ================= 5. 界面渲染 =================
store_rank_path = get_store_rank_path()
has_data = os.path.exists(PATH_F) and os.path.exists(PATH_D) and os.path.exists(PATH_A) and (store_rank_path is not None)

if has_data:
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, store_rank_path)

    if df_advisors is not None:
        col_header, col_filter = st.columns([3, 1])
        with col_header:
            st.title("Audi | DCC 效能看板")
        with col_filter:
            if df_stores is not None and not df_stores.empty and "门店名称" in df_stores.columns:
                all_stores = sorted(list(df_stores["门店名称"].dropna().unique()))
            else:
                all_stores = sorted(list(df_advisors.get("门店名称", pd.Series(dtype=str)).dropna().unique()))
            store_options = ["全部"] + all_stores
            selected_store = st.selectbox("🏭 切换门店视图", store_options)

        if selected_store == "全部":
            current_df = df_stores.copy() if df_stores is not None else pd.DataFrame()
            current_df["名称"] = current_df.get("门店名称", "")
            rank_title = "🏆 全区门店排名"
            kpi_leads = current_df.get("线索量", pd.Series(dtype=float)).sum()
            kpi_visits = current_df.get("到店量", pd.Series(dtype=float)).sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df.get("质检总分", pd.Series(dtype=float)).mean() if "质检总分" in current_df.columns else 0
        else:
            current_df = df_advisors[df_advisors.get("门店名称", "") == selected_store].copy()
            current_df["名称"] = current_df.get("邀约专员/管家", "")
            rank_title = f"👤 {selected_store} - 顾问排名"
            kpi_leads = current_df.get("线索量", pd.Series(dtype=float)).sum()
            kpi_visits = current_df.get("到店量", pd.Series(dtype=float)).sum()
            kpi_rate = kpi_visits / kpi_leads if kpi_leads > 0 else 0
            kpi_score = current_df.get("质检总分", pd.Series(dtype=float)).mean() if "质检总分" in current_df.columns else 0

        # 1. Result
        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")

        # 2. Process
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
        p2.metric("⚡ DCC及时处理率", f"{avg_timely:.1%}")
        p3.metric("🔄 二次外呼率", f"{avg_call2:.1%}")
        p4.metric("🔁 三次外呼率", f"{avg_call3:.1%}")
        st.caption("注：以上为加权平均值（sum/sum）")

        # 绘图数据准备
        plot_df_vis = current_df.copy()
        if "质检总分" in plot_df_vis.columns:
            plot_df_vis["质检总分_显示"] = plot_df_vis["质检总分"].fillna(0)
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
                fig_p1.update_layout(xaxis=dict(tickformat=".0%"))
                st.plotly_chart(fig_p1, use_container_width=True)
            else:
                st.warning("缺少外呼接通率或60秒通话数据，无法绘图")

        with c_proc_2:
            st.markdown("#### 🔗 归因分析：过程指标 vs 线索首邀到店率")
            st.info("💡 观察外呼及时性与邀约到店率相关性。")

            x_axis_choice = st.radio("选择横轴指标：", ["DCC及时处理率", "DCC二次外呼率", "DCC三次外呼率"], horizontal=True)
            plot_df_corr = plot_df_vis.copy()

            # Y：线索到店率（小数），用于按百分比格式展示（保留1位小数）
            plot_df_corr["线索到店率_显示"] = pd.to_numeric(plot_df_corr.get("线索到店率_数值", 0), errors="coerce").fillna(0).clip(0, 1)

            # X：过程指标（小数），强制限制在 0%~100%
            if x_axis_choice in plot_df_corr.columns:
                plot_df_corr[x_axis_choice] = pd.to_numeric(plot_df_corr[x_axis_choice], errors="coerce").fillna(0).clip(0, 1)

                fig_p2 = px.scatter(
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

                # 坐标轴：X 最大不超过 100%，Y 按百分比显示 1 位小数
                fig_p2.update_xaxes(range=[0, 1], tickformat=".0%")
                fig_p2.update_yaxes(tickformat=".1%")

                # 右侧留白：不改 X 最大值（仍是100%），但允许气泡超出坐标轴不被裁切
                fig_p2.update_traces(cliponaxis=False)
                fig_p2.update_layout(margin=dict(r=70))

                # Hover：把到店率按百分比 1 位小数展示
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
                            "线索量: %{customdata[0]:,.0f}<br>"
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

        # 3. Rank & Diagnosis
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
                display_df = rank_df[["名称", "线索到店率", "质检总分"]]

                st.dataframe(
                    display_df,
                    hide_index=True,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "名称": st.column_config.TextColumn("名称"),
                        "线索到店率": st.column_config.TextColumn("线索到店率"),
                        "质检总分": st.column_config.NumberColumn("质检总分", format="%.1f"),
                    },
                )
            else:
                st.warning("当前视图缺少排行必需列")

        with c_right:
            st.markdown("### 💡 话术质量 vs 转化结果")
            if "S_Time" in plot_df_vis.columns:
                plot_df = plot_df_vis.copy()
                plot_df["转化率%"] = pd.to_numeric(plot_df.get("线索到店率_数值", 0), errors="coerce").fillna(0) * 100
                fig = px.scatter(
                    plot_df,
                    x="S_Time",
                    y="转化率%",
                    size="线索量" if "线索量" in plot_df.columns else None,
                    color="质检总分_显示",
                    hover_name="名称",
                    labels={"S_Time": "明确到店时间得分", "转化率%": "线索到店率(%)"},
                    color_continuous_scale="Reds",
                    height=400,
                )
                if not plot_df.empty:
                    fig.add_vline(x=pd.to_numeric(plot_df["S_Time"], errors="coerce").fillna(0).mean(), line_dash="dash", line_color="gray")
                    fig.add_hline(y=kpi_rate * 100, line_dash="dash", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("缺少“明确到店时间”数据，无法绘图")

        st.markdown("---")

        # 4. 深度诊断
        with st.container():
            st.markdown("### 🕵️‍♀️ 邀约专员/管家深度诊断")
            if selected_store == "全部":
                st.info("💡 请先选择具体【门店】，查看该门店下的顾问详细诊断。")
            else:
                diag_df = current_df.copy()
                if "线索量" in diag_df.columns:
                    diag_df = diag_df[pd.to_numeric(diag_df["线索量"], errors="coerce").fillna(0) > 0].copy()

                if "邀约专员/管家" in diag_df.columns:
                    diag_list = sorted(diag_df["邀约专员/管家"].dropna().astype(str).unique())
                else:
                    diag_list = []

                if diag_list:
                    selected_person = st.selectbox("🔍 选择该店邀约专员/管家：", diag_list)
                    p_row = df_advisors[df_advisors["邀约专员/管家"] == selected_person]
                    if p_row.empty:
                        st.warning("找不到该人员明细")
                    else:
                        p = p_row.iloc[0]

                        d1, d2, d3 = st.columns([1, 1, 1.2])
                        with d1:
                            st.caption("转化漏斗 (RESULT)")
                            leads = float(pd.to_numeric(p.get("线索量", 0), errors="coerce") or 0)
                            visits = float(pd.to_numeric(p.get("到店量", 0), errors="coerce") or 0)

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

                            st.metric("线索到店率", p.get("线索到店率", "0.0%"))
                            st.caption(f"平均通话时长: {float(pd.to_numeric(p.get('通话时长', 0), errors='coerce') or 0):.1f} 秒")

                        has_score = ("质检总分" in p.index) and (not pd.isna(p.get("质检总分")))

                        with d2:
                            st.caption("质检得分详情 (QUALITY)")
                            if has_score:
                                metrics = {
                                    "明确到店时间": p.get("S_Time", np.nan),
                                    "60秒通话占比": p.get("S_60s", np.nan),
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
                                    "明确到店": (p.get("S_Time", np.nan), "建议使用二选一法锁定时间。"),
                                    "添加微信": (p.get("S_Wechat", np.nan), "建议以发定位/资料为由加微。"),
                                    "用车需求": (p.get("S_Needs", np.nan), "需加强需求挖掘，至少问清场景/预算/家庭结构。"),
                                    "车型信息": (p.get("S_Car", np.nan), "需提升产品讲解链路，先讲1-2个强卖点。"),
                                    "政策相关": (p.get("S_Policy", np.nan), "需准确传达政策，并用截止时间推动决策。"),
                                }

                                issues_list = []
                                is_failing = False

                                if val_60s < 60:
                                    issues_list.append(f"🟠 **60秒占比 (得分{val_60s:.1f})**\n开场先抛利益点 + 明确下一步动作。")
                                    is_failing = True

                                cleaned_others = {}
                                for k, (v, advice) in other_kpis.items():
                                    score = 0 if pd.isna(v) else float(v)
                                    cleaned_others[k] = (score, advice)
                                    if score < 80:
                                        issues_list.append(f"🔴 **{k} (得分{score:.1f})**\n{advice}")
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
    st.warning("👉 目前暂无数据。请在左侧侧边栏展开【更新数据】，输入管理员密码并上传所有 **4** 个数据文件。")
