import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import os

# ================= 1. 页面配置 =================
st.set_page_config(page_title="Audi DCC 效能看板", layout="wide", page_icon="🏎️")

st.markdown(
    """
<style>
    .metric-card {background-color: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);}
    div[data-testid="stSelectbox"] {min-width: 200px;}
    div[data-testid="stFormSubmitButton"] button {
        width: 100%;
        background-color: #bb0a30;
        color: white;
        border: none;
        font-weight: bold;
    }
    div[data-testid="stFormSubmitButton"] button:hover {
        background-color: #990000;
        color: white;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ================= 2. 基础配置 =================
ADMIN_PASSWORD = "AudiSARR3"
DATA_DIR = "data_store"
os.makedirs(DATA_DIR, exist_ok=True)

# ✅ 固定 store_rank 以 xlsx 为主；兼容误传 csv
PATH_F = os.path.join(DATA_DIR, "funnel.xlsx")
PATH_D = os.path.join(DATA_DIR, "dcc.xlsx")
PATH_A = os.path.join(DATA_DIR, "ams.xlsx")
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


# ================= 3. 侧边栏 =================
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/9/92/Audi-Logo_2016.svg/1200px-Audi-Logo_2016.svg.png",
        width=150,
    )
    st.header("⚙️ 管理面板")

    store_rank_path = get_store_rank_path()
    has_data = (
        os.path.exists(PATH_F)
        and os.path.exists(PATH_D)
        and os.path.exists(PATH_A)
        and (store_rank_path is not None)
    )

    if has_data:
        st.success("✅ 数据状态：已就绪")
    else:
        st.warning("⚠️ 暂无数据")
    st.markdown("---")

    with st.expander("🔐 更新数据 (仅限管理员)", expanded=True):
        pwd = st.text_input("输入管理员密码", type="password")

        if pwd == ADMIN_PASSWORD:
            st.info("🔓 身份验证通过")
            with st.form("data_update_form", clear_on_submit=False):
                st.markdown("##### 请上传所有 4 个文件：")
                new_f = st.file_uploader("1. 漏斗表 (funnel)", type=["xlsx", "csv"])
                new_d = st.file_uploader("2. 顾问质检表 (dcc)", type=["xlsx", "csv"])
                new_a = st.file_uploader("3. AMS表 (ams)", type=["xlsx", "csv"])
                new_s = st.file_uploader("4. 门店排名表 (store_rank)", type=["xlsx", "csv"])

                if st.form_submit_button("🚀 确认并更新数据"):
                    if new_f and new_d and new_a and new_s:
                        with st.spinner("正在保存并处理..."):
                            s1 = save_uploaded_file(new_f, PATH_F)
                            s2 = save_uploaded_file(new_d, PATH_D)
                            s3 = save_uploaded_file(new_a, PATH_A)

                            # ✅ store_rank 根据上传真实后缀保存
                            if new_s.name.lower().endswith(".xlsx"):
                                if os.path.exists(PATH_S_CSV):
                                    try:
                                        os.remove(PATH_S_CSV)
                                    except Exception:
                                        pass
                                s4 = save_uploaded_file(new_s, PATH_S_XLSX)
                            else:
                                if os.path.exists(PATH_S_XLSX):
                                    try:
                                        os.remove(PATH_S_XLSX)
                                    except Exception:
                                        pass
                                s4 = save_uploaded_file(new_s, PATH_S_CSV)

                            if s1 and s2 and s3 and s4:
                                st.success("✅ 更新成功！正在刷新页面...")
                                st.rerun()
                    else:
                        st.error("❌ 请确保 4 个文件全部上传完毕。")
        elif pwd:
            st.error("密码错误")


# ================= 4. 数据读取与处理 =================
def dedupe_columns(columns):
    """把重复列名变成: 列名, 列名__1, 列名__2 ..."""
    seen = {}
    new_cols = []
    for c in list(columns):
        c = str(c)
        if c not in seen:
            seen[c] = 0
            new_cols.append(c)
        else:
            seen[c] += 1
            new_cols.append(f"{c}__{seen[c]}")
    return new_cols


def smart_read(file_path: str):
    """增强版读取：
    - xlsx: read_excel(header=None)
    - csv: 多编码尝试
    - 兜底：若文件签名是 PK..（其实是xlsx），即便后缀是csv也按xlsx读
    - 关键：列名去重，避免 df['添加微信'] 取出多列
    """
    try:
        if not file_path or not os.path.exists(file_path):
            return None

        df = None

        # 兜底：签名判断（xlsx/docx/pptx 都是 zip: PK..）
        try:
            with open(file_path, "rb") as f:
                sig = f.read(4)
            if sig == b"PK\x03\x04":
                df = pd.read_excel(file_path, header=None)
        except Exception:
            pass

        if df is None:
            if file_path.lower().endswith(".xlsx"):
                df = pd.read_excel(file_path, header=None)
            else:
                encodings = ["utf-8-sig", "gb18030", "utf-16"]
                for enc in encodings:
                    try:
                        df = pd.read_csv(
                            file_path,
                            header=None,
                            encoding=enc,
                            engine="python",
                            on_bad_lines="skip",
                        )
                        break
                    except (UnicodeDecodeError, pd.errors.ParserError):
                        continue
                    except Exception:
                        continue

        if df is None:
            st.error(f"❌ 无法读取文件: {os.path.basename(file_path)}")
            return None

        # 智能找表头
        header_row = 0
        keywords = ["门店", "顾问", "管家", "排名", "代理商", "序号", "线索", "质检"]
        for i in range(min(8, len(df))):
            row_values = df.iloc[i].astype(str).str.cat(sep=",")
            if any(k in row_values for k in keywords):
                header_row = i
                break

        df.columns = df.iloc[header_row]
        df = df[header_row + 1 :].reset_index(drop=True)

        # 清理列名
        df.columns = (
            df.columns.astype(str)
            .str.strip()
            .str.replace("\n", "", regex=False)
            .str.replace("\r", "", regex=False)
        )

        # ✅ 去重列名
        df.columns = dedupe_columns(df.columns)

        # 删除空列
        df = df.loc[:, df.columns.notna()]
        df = df.loc[:, df.columns != "nan"]

        return df

    except Exception as e:
        st.error(f"读取文件系统级失败: {os.path.basename(file_path)} - {e}")
        return None


def safe_div(df, num_col, denom_col):
    if num_col not in df.columns or denom_col not in df.columns:
        return 0
    num = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
    denom = pd.to_numeric(df[denom_col], errors="coerce").fillna(0)
    return (num / denom).replace([np.inf, -np.inf], 0).fillna(0)


@st.cache_data(ttl=300)
def process_data(path_f, path_d, path_a, store_rank_path):
    try:
        raw_f = smart_read(path_f)
        raw_d = smart_read(path_d)
        raw_a = smart_read(path_a)
        raw_s = smart_read(store_rank_path)

        if raw_f is None or raw_d is None or raw_a is None or raw_s is None:
            return None, None

        # --- A. 漏斗表 ---
        f_cols = raw_f.columns
        col_store = next((c for c in f_cols if "门店" in str(c) or "代理" in str(c)), "门店名称")
        col_name = next((c for c in f_cols if "顾问" in str(c) or "管家" in str(c)), "邀约专员/管家")
        col_leads = next((c for c in f_cols if "有效线索" in str(c) or "线索量" in str(c)), "线索量")
        col_visits = next((c for c in f_cols if "到店" in str(c) and "率" not in str(c)), "到店量")

        df_f = raw_f.rename(
            columns={
                col_store: "门店名称",
                col_name: "邀约专员/管家",
                col_leads: "线索量",
                col_visits: "到店量",
            }
        )

        mask_sub = df_f["邀约专员/管家"].astype(str).str.contains("小计", na=False)
        df_store_data = df_f[mask_sub].copy()
        df_advisor_data = df_f[~mask_sub].copy()

        for df in [df_store_data, df_advisor_data]:
            df["线索量"] = pd.to_numeric(df["线索量"], errors="coerce").fillna(0)
            df["到店量"] = pd.to_numeric(df["到店量"], errors="coerce").fillna(0)
            df["线索到店率_数值"] = safe_div(df, "到店量", "线索量")
            df["线索到店率"] = (df["线索到店率_数值"] * 100).map("{:.1f}%".format)

        # --- B. 顾问质检表 ---
        d_map = {
            "顾问名称": "邀约专员/管家",
            "质检总分": "质检总分",
            "60秒通话": "S_60s",
            "用车需求": "S_Needs",
            "车型信息": "S_Car",
            "政策相关": "S_Policy",
            "明确到店时间": "S_Time",
        }
        df_d = raw_d.rename(columns=d_map)

        # ✅ 多列安全：匹配所有“添加微信”相关列，取第一列
        wechat_cols = [c for c in df_d.columns if ("微信" in str(c) and "添加" in str(c))]
        if wechat_cols:
            df_d["S_Wechat"] = pd.to_numeric(df_d[wechat_cols].iloc[:, 0], errors="coerce").fillna(0)
        else:
            df_d["S_Wechat"] = 0

        # 兜底：若顾问列名不同
        if "邀约专员/管家" not in df_d.columns:
            if "管家" in df_d.columns:
                df_d.rename(columns={"管家": "邀约专员/管家"}, inplace=True)
            elif "顾问" in df_d.columns:
                df_d.rename(columns={"顾问": "邀约专员/管家"}, inplace=True)

        num_cols = ["质检总分", "S_60s", "S_Time", "S_Needs", "S_Car", "S_Policy", "S_Wechat"]
        for c in num_cols:
            if c in df_d.columns:
                df_d[c] = pd.to_numeric(df_d[c], errors="coerce")

        # --- C. 门店排名表 ---
        s_map = {
            "60秒通话": "S_60s",
            "用车需求": "S_Needs",
            "车型信息": "S_Car",
            "政策相关": "S_Policy",
            "明确到店时间": "S_Time",
        }
        s_store_raw = next((c for c in raw_s.columns if "门店" in str(c) and "ID" not in str(c)), "门店名称")
        df_s = raw_s.rename(columns={**s_map, s_store_raw: "门店名称"})

        # ✅ 多列安全：门店排名表的“添加微信”列
        s_wechat_cols = [c for c in df_s.columns if ("微信" in str(c) and "添加" in str(c))]
        if s_wechat_cols:
            df_s["S_Wechat"] = pd.to_numeric(df_s[s_wechat_cols].iloc[:, 0], errors="coerce").fillna(0)
        else:
            df_s["S_Wechat"] = 0

        for c in ["质检总分", "S_60s", "S_Time", "S_Needs", "S_Car", "S_Policy", "S_Wechat"]:
            if c in df_s.columns:
                df_s[c] = pd.to_numeric(df_s[c], errors="coerce")

        # --- D. AMS表 ---
        a_map = {}
        for c in raw_a.columns:
            sc = str(c)
            if "接通" in sc and "线索" in sc and "率" not in sc:
                a_map[c] = "conn_num"
            if "外呼" in sc and "线索" in sc and "需" not in sc and "率" not in sc:
                a_map[c] = "conn_denom"
            if "管家" in sc or "顾问" in sc:
                a_map[c] = "邀约专员/管家"
            if "平均通话时长" in sc:
                a_map[c] = "通话时长"

        df_a = raw_a.rename(columns=a_map)
        for c in ["conn_num", "conn_denom", "通话时长"]:
            if c not in df_a.columns:
                df_a[c] = 0
            else:
                df_a[c] = pd.to_numeric(df_a[c], errors="coerce").fillna(0)

        # --- E. 合并 ---
        for df in [df_advisor_data, df_d, df_a, df_store_data, df_s]:
            if "邀约专员/管家" in df.columns:
                df["邀约专员/管家"] = df["邀约专员/管家"].astype(str).str.strip()
            if "门店名称" in df.columns:
                df["门店名称"] = df["门店名称"].astype(str).str.strip()

        full_advisors = pd.merge(df_advisor_data, df_d, on="邀约专员/管家", how="left")

        if "邀约专员/管家" in df_a.columns:
            df_a_unique = df_a.groupby("邀约专员/管家").first().reset_index()
            full_advisors = pd.merge(full_advisors, df_a_unique, on="邀约专员/管家", how="left")

        if "conn_num" in full_advisors.columns and "门店名称" in full_advisors.columns:
            ams_grp = full_advisors.groupby("门店名称")[["conn_num", "conn_denom"]].sum().reset_index()
        else:
            ams_grp = pd.DataFrame(columns=["门店名称", "conn_num", "conn_denom"])

        full_stores = pd.merge(df_store_data, df_s, on="门店名称", how="left")
        full_stores = pd.merge(full_stores, ams_grp, on="门店名称", how="left")

        return full_advisors, full_stores

    except Exception as e:
        import traceback

        st.error(f"数据处理逻辑错误: {e}")
        st.text(traceback.format_exc())
        return None, None


# ================= 5. 界面渲染 =================
store_rank_path = get_store_rank_path()
has_data = (
    os.path.exists(PATH_F)
    and os.path.exists(PATH_D)
    and os.path.exists(PATH_A)
    and (store_rank_path is not None)
)

if has_data:
    df_advisors, df_stores = process_data(PATH_F, PATH_D, PATH_A, store_rank_path)

    if df_advisors is not None:
        st.sidebar.markdown("---")
        if df_stores is not None and not df_stores.empty and "门店名称" in df_stores.columns:
            store_options = ["全部"] + sorted(list(df_stores["门店名称"].unique()))
        else:
            store_options = ["全部"]

        selected_store = st.sidebar.selectbox("🏭 切换门店视图", store_options)

        if selected_store == "全部":
            current_df = df_stores.copy() if df_stores is not None else pd.DataFrame()
            current_df["Name"] = current_df.get("门店名称", "")
            rank_title = "🏆 全区门店排名"
        else:
            current_df = df_advisors[df_advisors.get("门店名称", "") == selected_store].copy()
            current_df["Name"] = current_df.get("邀约专员/管家", "")
            rank_title = f"👤 {selected_store} - 顾问排名"

        kpi_leads = current_df["线索量"].sum() if "线索量" in current_df.columns else 0
        kpi_visits = current_df["到店量"].sum() if "到店量" in current_df.columns else 0
        kpi_rate = (kpi_visits / kpi_leads) if kpi_leads > 0 else 0
        kpi_score = current_df["质检总分"].mean() if "质检总分" in current_df.columns else 0

        st.subheader("1️⃣ 结果概览 (Result)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("总有效线索", f"{int(kpi_leads):,}")
        k2.metric("总实际到店", f"{int(kpi_visits):,}")
        k3.metric("线索到店率", f"{kpi_rate:.1%}")
        k4.metric("平均质检总分", f"{kpi_score:.1f}")

        st.markdown("---")

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("通话质量分析")
            if "S_60s" in current_df.columns and "conn_num" in current_df.columns:
                current_df["接通率"] = safe_div(current_df, "conn_num", "conn_denom")
                plot_df = current_df.fillna(0)
                fig = px.scatter(
                    plot_df,
                    x="接通率",
                    y="S_60s",
                    size="线索量" if "线索量" in plot_df.columns else None,
                    color="质检总分" if "质检总分" in plot_df.columns else None,
                    hover_name="Name",
                    labels={"S_60s": "60秒通话占比", "接通率": "外呼接通率"},
                )
                fig.update_layout(xaxis_tickformat=".0%", height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("ℹ️ 数据不足，无法显示通话质量散点图 (需 AMS 和 质检数据)")

        with c2:
            st.subheader(rank_title)
            show_cols = ["Name", "线索到店率", "质检总分", "线索量", "到店量"]
            if "S_60s" in current_df.columns:
                show_cols.append("S_60s")

            show_cols = [c for c in show_cols if c in current_df.columns]

            if not current_df.empty and show_cols:
                if "线索量" in current_df.columns:
                    view_df = current_df[show_cols].sort_values("线索量", ascending=False)
                else:
                    view_df = current_df[show_cols]
                st.dataframe(view_df, use_container_width=True, height=400, hide_index=True)
            else:
                st.warning("暂无数据")
else:
    st.info("👋 欢迎使用！请在左侧点击“更新数据”并上传文件。")
