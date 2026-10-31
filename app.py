"""
Auto-Viz & Smart Data Cleaner
==============================
A zero-configuration Streamlit MVP that uploads a CSV/XLSX file,
audits data health, cleans and imputes data, then auto-generates charts.

Code comments and docstrings: English
UI strings: Bahasa Indonesia
"""

import io
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
MAX_FILE_MB: int = 10
MAX_ROWS: int = 50_000
CORRUPT_ROW_RATIO: float = 0.5
EMPTY_COL_RATIO: float = 0.7
SKEW_THRESHOLD: float = 0.5
CAT_MISSING_MODE_LIMIT: float = 0.10
MAX_CATEGORY_CARDINALITY: int = 15
MAX_CHARTS: int = 6
DATE_CONVERSION_MIN_RATIO: float = 0.80
SCATTER_MAX_POINTS: int = 5_000
ID_COL_UNIQUE_THRESHOLD: int = 50  # rows above which 100% unique numeric = ID

TEMPORAL_KEYWORDS: List[str] = ["date", "time", "tahun", "bulan", "tanggal"]


# ---------------------------------------------------------------------------
# PHASE 1 — FILE LOADING
# ---------------------------------------------------------------------------

def _load_csv(file_bytes: bytes) -> pd.DataFrame:
    """Try reading CSV with utf-8, fall back to latin-1."""
    try:
        return pd.read_csv(io.BytesIO(file_bytes), nrows=MAX_ROWS)
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(file_bytes), nrows=MAX_ROWS, encoding="latin-1")


def _load_excel(file_bytes: bytes) -> pd.DataFrame:
    """Read first sheet of an Excel file."""
    return pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=0,
        nrows=MAX_ROWS,
        engine="openpyxl",
    )


def load_file(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> Optional[pd.DataFrame]:
    """
    Validate and load an uploaded file into a DataFrame.

    Returns the DataFrame on success, or None on any error (error already
    surfaced via st.error).
    """
    file_bytes = uploaded_file.read()
    file_size_mb = len(file_bytes) / (1024 * 1024)

    if file_size_mb > MAX_FILE_MB:
        st.error(
            f"❌ Ukuran file melebihi batas maksimal {MAX_FILE_MB} MB "
            f"(file Anda: {file_size_mb:.1f} MB). Harap unggah file yang lebih kecil."
        )
        return None

    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            df = _load_csv(file_bytes)
        elif name.endswith(".xlsx"):
            df = _load_excel(file_bytes)
        else:
            st.error("❌ Format file tidak didukung. Harap unggah file .csv atau .xlsx.")
            return None
    except pd.errors.EmptyDataError:
        st.error("❌ File kosong atau tidak memiliki data. Harap unggah file yang valid.")
        return None
    except pd.errors.ParserError as exc:
        st.error(f"❌ File tidak dapat dibaca (format rusak): {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        st.error(f"❌ Terjadi kesalahan saat membaca file: {exc}")
        return None

    if df.empty or len(df.columns) == 0:
        st.error("❌ File tidak memiliki baris atau kolom data. Harap unggah file yang valid.")
        return None

    # Strip whitespace from column names and deduplicate
    df.columns = [str(c).strip() for c in df.columns]
    # Make column names unique (pandas adds suffixes automatically on read, but just in case)
    seen: Dict[str, int] = {}
    new_cols: List[str] = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    df.columns = new_cols

    total_rows_read = len(df)
    if total_rows_read >= MAX_ROWS:
        st.info(
            f"ℹ️ File memiliki lebih dari {MAX_ROWS:,} baris. "
            f"Sistem hanya memproses {MAX_ROWS:,} baris pertama."
        )

    return df


# ---------------------------------------------------------------------------
# PHASE 2 — DATA HEALTH CHECK
# ---------------------------------------------------------------------------

def compute_health_metrics(df: pd.DataFrame) -> Dict:
    """
    Compute health metrics on the *raw* DataFrame before any modification.

    Returns a dict with keys:
      n_rows, n_cols, n_duplicates, n_corrupted_rows, missing_cols
    """
    total_cols = len(df.columns)
    n_duplicates = int(df.duplicated().sum())
    # Corrupted = rows with > 50% missing values
    min_valid = total_cols * CORRUPT_ROW_RATIO
    n_corrupted = int((df.isnull().sum(axis=1) > (total_cols - min_valid)).sum())
    missing_cols: Dict[str, float] = {}
    for col in df.columns:
        pct = df[col].isnull().mean()
        if pct > 0:
            missing_cols[col] = round(pct * 100, 1)
    return {
        "n_rows": len(df),
        "n_cols": total_cols,
        "n_duplicates": n_duplicates,
        "n_corrupted_rows": n_corrupted,
        "missing_cols": missing_cols,
    }


# ---------------------------------------------------------------------------
# PHASE 2 — CLEANING PIPELINE
# ---------------------------------------------------------------------------

def _fisher_pearson_skewness(series: pd.Series) -> float:
    """
    Compute Fisher-Pearson population skewness.

    S = [Σ(Yi − Ȳ)³ / N] / s³
    Uses population std (ddof=0). Returns 0.0 when std == 0.
    """
    values = series.dropna().values.astype(float)
    n = len(values)
    if n < 3:
        return 0.0
    mean = values.mean()
    deviations = values - mean
    s = values.std(ddof=0)
    if s == 0:
        return 0.0
    skew = (np.sum(deviations ** 3) / n) / (s ** 3)
    return float(skew)


def _try_convert_to_datetime(series: pd.Series) -> Optional[pd.Series]:
    """
    Attempt to convert an object series to datetime64.

    Only converts if >= DATE_CONVERSION_MIN_RATIO of non-null values parse.
    Returns the converted Series, or None if conversion is skipped.
    """
    non_null = series.dropna()
    if len(non_null) == 0:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        converted = pd.to_datetime(non_null, errors="coerce", infer_datetime_format=True)
    success_ratio = converted.notna().sum() / len(non_null)
    if success_ratio >= DATE_CONVERSION_MIN_RATIO:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return pd.to_datetime(series, errors="coerce", infer_datetime_format=True)
    return None


def run_cleaning_pipeline(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """
    Execute the 5-step cleaning pipeline on a copy of the DataFrame.

    Returns (cleaned_df, change_log).
    Pipeline order:
      1. Type standardization (object → datetime where appropriate)
      2. Drop duplicate rows
      3. Drop corrupted rows
      4. Drop empty columns (> 70% missing)
      5. Numeric imputation (mean/median based on skewness)
      6. Categorical imputation (mode / "Unknown")
    """
    df = df.copy()
    log: List[str] = []
    total_cols = len(df.columns)

    # ---- Step 1: Type standardization ----
    for col in df.select_dtypes(include="object").columns:
        converted = _try_convert_to_datetime(df[col])
        if converted is not None:
            df[col] = converted
            log.append(f"Kolom '{col}' dikonversi ke tipe datetime.")

    # ---- Step 2: Drop duplicate rows ----
    n_before = len(df)
    df = df.drop_duplicates()
    n_dropped_dup = n_before - len(df)
    if n_dropped_dup > 0:
        log.append(f"Menghapus {n_dropped_dup} baris duplikat.")

    # ---- Step 3: Drop corrupted rows ----
    n_before = len(df)
    thresh = int(total_cols * CORRUPT_ROW_RATIO)
    df = df.dropna(thresh=thresh)
    n_dropped_corrupt = n_before - len(df)
    if n_dropped_corrupt > 0:
        log.append(f"Menghapus {n_dropped_corrupt} baris rusak (> {int(CORRUPT_ROW_RATIO*100)}% nilai kosong).")

    if df.empty:
        log.append("⚠️ Semua baris telah dihapus setelah pembersihan ekstrem.")
        return df, log

    # ---- Step 4: Drop empty columns ----
    cols_before = set(df.columns)
    empty_col_threshold = EMPTY_COL_RATIO
    missing_pct_per_col = df.isnull().mean()
    cols_to_drop = missing_pct_per_col[missing_pct_per_col > empty_col_threshold].index.tolist()
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
        for c in cols_to_drop:
            log.append(
                f"Menghapus kolom '{c}' karena > {int(empty_col_threshold*100)}% nilai kosong "
                f"({missing_pct_per_col[c]*100:.1f}%)."
            )

    # ---- Step 5: Numeric imputation ----
    for col in df.select_dtypes(include=["int64", "float64"]).columns:
        n_missing = int(df[col].isnull().sum())
        if n_missing == 0:
            continue
        skew = _fisher_pearson_skewness(df[col])
        if abs(skew) <= SKEW_THRESHOLD:
            fill_value = df[col].mean()
            method = "Mean"
        else:
            fill_value = df[col].median()
            method = "Median"
        df[col] = df[col].fillna(fill_value)
        log.append(
            f"Kolom '{col}': Mengisi {n_missing} nilai kosong dengan {method} "
            f"({fill_value:.4g}) karena skew = {skew:.2f}."
        )

    # ---- Step 6: Categorical / text imputation ----
    for col in df.select_dtypes(include=["object", "category"]).columns:
        n_missing = int(df[col].isnull().sum())
        if n_missing == 0:
            continue
        missing_ratio = n_missing / len(df)
        if missing_ratio <= CAT_MISSING_MODE_LIMIT:
            mode_series = df[col].mode()
            if len(mode_series) == 0:
                fill_value = "Unknown"
                method = '"Unknown" (mode kosong)'
            else:
                fill_value = mode_series.iloc[0]
                method = f'Modus ("{fill_value}")'
        else:
            fill_value = "Unknown"
            method = '"Unknown"'
        df[col] = df[col].fillna(fill_value)
        log.append(
            f"Kolom '{col}': Mengisi {n_missing} nilai kosong dengan {method} "
            f"(persentase kosong = {missing_ratio*100:.1f}%)."
        )

    if not log:
        log.append("Tidak ada perubahan yang dilakukan. Data sudah bersih.")

    return df, log


# ---------------------------------------------------------------------------
# PHASE 3 — COLUMN CLASSIFICATION
# ---------------------------------------------------------------------------

ColumnRoles = Dict[str, List[str]]


def classify_columns(df: pd.DataFrame) -> ColumnRoles:
    """
    Classify each column into one of four roles: temporal, categorical,
    numeric, or ignored.

    Evaluation order: Ignored → Temporal → Categorical → Numeric.
    """
    roles: ColumnRoles = {"temporal": [], "categorical": [], "numeric": [], "ignored": []}
    n_rows = len(df)

    for col in df.columns:
        series = df[col]
        n_unique = series.nunique(dropna=True)

        # --- Ignored rules (evaluated first) ---
        if n_unique <= 1:
            # Constant column
            roles["ignored"].append(col)
            continue

        if pd.api.types.is_numeric_dtype(series) and n_rows > ID_COL_UNIQUE_THRESHOLD:
            unique_ratio = n_unique / n_rows
            if unique_ratio == 1.0:
                # 100% unique → treat as ID
                roles["ignored"].append(col)
                continue
            # Check for monotonic integer sequence (sequential ID)
            if pd.api.types.is_integer_dtype(series):
                non_null = series.dropna().reset_index(drop=True)
                if non_null.is_monotonic_increasing and (non_null.diff().dropna() == 1).all():
                    roles["ignored"].append(col)
                    continue

        if pd.api.types.is_object_dtype(series) and n_unique > MAX_CATEGORY_CARDINALITY:
            # Free text / high-cardinality text
            roles["ignored"].append(col)
            continue

        # --- Temporal ---
        if pd.api.types.is_datetime64_any_dtype(series):
            roles["temporal"].append(col)
            continue

        col_lower = col.lower()
        if any(kw in col_lower for kw in TEMPORAL_KEYWORDS):
            # Only treat as temporal if the column is actually datetime-like
            converted = _try_convert_to_datetime(series.astype(str))
            if converted is not None:
                roles["temporal"].append(col)
                continue

        # --- Categorical ---
        if (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_categorical_dtype(series)
            or pd.api.types.is_bool_dtype(series)
        ) and 2 <= n_unique <= MAX_CATEGORY_CARDINALITY:
            roles["categorical"].append(col)
            continue

        # --- Numeric ---
        if pd.api.types.is_numeric_dtype(series) and n_unique > 2:
            roles["numeric"].append(col)
            continue

        # Fallback: ignored
        roles["ignored"].append(col)

    return roles


# ---------------------------------------------------------------------------
# PHASE 3 — CHART BUILDERS
# ---------------------------------------------------------------------------

def build_line_charts(df: pd.DataFrame, roles: ColumnRoles) -> List:
    """Build up to 2 Line Charts (Time Trend)."""
    charts = []
    temporal_cols = roles["temporal"]
    numeric_cols = roles["numeric"]
    if not temporal_cols or not numeric_cols:
        return charts

    for t_col in temporal_cols[: 2]:
        if len(charts) >= 2:
            break
        num_col = numeric_cols[0]
        try:
            temp_df = df[[t_col, num_col]].dropna()
            temp_df = temp_df.copy()
            temp_df[t_col] = pd.to_datetime(temp_df[t_col], errors="coerce")
            temp_df = temp_df.dropna(subset=[t_col])
            temp_df = temp_df.sort_values(t_col)
            agg_df = temp_df.groupby(t_col, as_index=False)[num_col].mean()
            fig = px.line(
                agg_df,
                x=t_col,
                y=num_col,
                title=f"Tren Rata-rata {num_col} berdasarkan {t_col}",
                labels={t_col: t_col, num_col: f"Rata-rata {num_col}"},
            )
            charts.append(fig)
        except Exception:  # noqa: BLE001
            pass

    return charts


def build_bar_charts(df: pd.DataFrame, roles: ColumnRoles) -> List:
    """Build up to 2 Bar Charts (Category Comparison)."""
    charts = []
    cat_cols = roles["categorical"]
    num_cols = roles["numeric"]
    if not cat_cols or not num_cols:
        return charts

    pairs_checked = 0
    for c_col in cat_cols:
        if len(charts) >= 2:
            break
        for n_col in num_cols:
            if len(charts) >= 2:
                break
            pairs_checked += 1
            try:
                agg_df = (
                    df[[c_col, n_col]]
                    .dropna()
                    .groupby(c_col, as_index=False)[n_col]
                    .mean()
                    .sort_values(n_col, ascending=False)
                )
                fig = px.bar(
                    agg_df,
                    x=c_col,
                    y=n_col,
                    title=f"Rata-rata {n_col} per {c_col}",
                    labels={c_col: c_col, n_col: f"Rata-rata {n_col}"},
                )
                charts.append(fig)
                break  # one numeric col per categorical col
            except Exception:  # noqa: BLE001
                pass

    return charts


def build_scatter_chart(df: pd.DataFrame, roles: ColumnRoles) -> Optional[object]:
    """Build 1 Scatter Chart (Correlation) — pair with highest |r| < 1.0."""
    num_cols = roles["numeric"]
    if len(num_cols) < 2:
        return None

    try:
        numeric_df = df[num_cols].dropna()

        if len(num_cols) == 2:
            x_col, y_col = num_cols[0], num_cols[1]
        else:
            # Compute Pearson correlation matrix and find best pair
            corr = numeric_df.corr(method="pearson")
            best_r = -1.0
            x_col, y_col = num_cols[0], num_cols[1]
            for i, col_a in enumerate(num_cols):
                for col_b in num_cols[i + 1 :]:
                    r_val = abs(corr.loc[col_a, col_b])
                    if r_val < 1.0 and r_val > best_r:
                        best_r = r_val
                        x_col, y_col = col_a, col_b

        plot_df = numeric_df[[x_col, y_col]]
        if len(plot_df) > SCATTER_MAX_POINTS:
            plot_df = plot_df.sample(SCATTER_MAX_POINTS, random_state=42)

        fig = px.scatter(
            plot_df,
            x=x_col,
            y=y_col,
            title=f"Korelasi: {x_col} vs {y_col}",
            labels={x_col: x_col, y_col: y_col},
            opacity=0.6,
        )
        return fig
    except Exception:  # noqa: BLE001
        return None


def build_histogram_chart(df: pd.DataFrame, roles: ColumnRoles) -> Optional[object]:
    """
    Build 1 Histogram (Distribution).
    Chooses numeric column with highest coefficient of variation.
    """
    num_cols = roles["numeric"]
    if not num_cols:
        return None

    try:
        # Pick column with highest coefficient of variation (std/mean)
        best_col = num_cols[0]
        best_cv = -1.0
        for col in num_cols:
            col_data = df[col].dropna()
            mean_val = col_data.mean()
            if mean_val == 0 or len(col_data) == 0:
                continue
            cv = col_data.std(ddof=1) / abs(mean_val)
            if cv > best_cv:
                best_cv = cv
                best_col = col

        fig = px.histogram(
            df[[best_col]].dropna(),
            x=best_col,
            title=f"Distribusi {best_col}",
            labels={best_col: best_col},
            nbins=30,
        )
        return fig
    except Exception:  # noqa: BLE001
        return None


def generate_all_charts(df: pd.DataFrame, roles: ColumnRoles) -> List:
    """
    Assemble up to MAX_CHARTS charts in order:
    Line (max 2) → Bar (max 2) → Scatter (max 1) → Histogram (max 1).
    """
    all_charts = []

    line_charts = build_line_charts(df, roles)
    all_charts.extend(line_charts[:2])

    bar_charts = build_bar_charts(df, roles)
    all_charts.extend(bar_charts[:2])

    scatter = build_scatter_chart(df, roles)
    if scatter is not None:
        all_charts.append(scatter)

    histogram = build_histogram_chart(df, roles)
    if histogram is not None:
        all_charts.append(histogram)

    return all_charts[:MAX_CHARTS]


# ---------------------------------------------------------------------------
# PHASE 4 — UI (main)
# ---------------------------------------------------------------------------

def render_health_metrics(metrics: Dict) -> None:
    """Display health metrics in st.metric columns."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📋 Jumlah Baris", f"{metrics['n_rows']:,}")
    col2.metric("📊 Jumlah Kolom", f"{metrics['n_cols']:,}")
    col3.metric("♻️ Baris Duplikat", f"{metrics['n_duplicates']:,}")
    col4.metric("🚨 Baris Rusak", f"{metrics['n_corrupted_rows']:,}")

    if metrics["missing_cols"]:
        with st.expander("📋 Kolom dengan Nilai Kosong", expanded=False):
            rows = [
                {"Nama Kolom": col, "Persentase Kosong (%)": pct}
                for col, pct in metrics["missing_cols"].items()
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)


def render_charts_grid(charts: List) -> None:
    """Render charts in a 2-column grid layout."""
    for i in range(0, len(charts), 2):
        cols = st.columns(2)
        cols[0].plotly_chart(charts[i], use_container_width=True)
        if i + 1 < len(charts):
            cols[1].plotly_chart(charts[i + 1], use_container_width=True)


@st.cache_data(show_spinner=False)
def cached_process(file_bytes: bytes, file_name: str) -> Tuple[
    Optional[pd.DataFrame],
    Optional[pd.DataFrame],
    Dict,
    List[str],
]:
    """
    Cache-key is file_bytes content.
    Returns (raw_df, clean_df, health_metrics, change_log).
    """
    # Re-build a fake UploadedFile-like object is not needed; we work directly.
    # Load
    name = file_name.lower()
    try:
        if name.endswith(".csv"):
            try:
                raw_df = pd.read_csv(io.BytesIO(file_bytes), nrows=MAX_ROWS)
            except UnicodeDecodeError:
                raw_df = pd.read_csv(io.BytesIO(file_bytes), nrows=MAX_ROWS, encoding="latin-1")
        elif name.endswith(".xlsx"):
            raw_df = pd.read_excel(
                io.BytesIO(file_bytes), sheet_name=0, nrows=MAX_ROWS, engine="openpyxl"
            )
        else:
            return None, None, {}, ["Format tidak didukung."]
    except Exception as exc:  # noqa: BLE001
        return None, None, {}, [f"Gagal membaca file: {exc}"]

    raw_df.columns = [str(c).strip() for c in raw_df.columns]
    health = compute_health_metrics(raw_df)
    clean_df, change_log = run_cleaning_pipeline(raw_df)
    return raw_df, clean_df, health, change_log


def main() -> None:
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="Auto-Viz & Smart Data Cleaner",
        page_icon="📊",
        layout="wide",
    )

    # --- Title ---
    st.title("📊 AUTO-VIZ & SMART DATA CLEANER")
    st.caption("Unggah dataset Anda, biarkan sistem membersihkan dan memvisualisasikan.")

    # --- File Uploader ---
    uploaded_file = st.file_uploader(
        "Pilih file CSV atau Excel:",
        type=["csv", "xlsx"],
        help=f"Maks. {MAX_FILE_MB} MB atau {MAX_ROWS:,} baris pertama.",
    )

    if uploaded_file is None:
        st.info("ℹ️ Belum ada file yang diunggah. Silakan unggah file .csv atau .xlsx untuk memulai.")
        return

    # --- File size check (before caching) ---
    file_bytes = uploaded_file.read()
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > MAX_FILE_MB:
        st.error(
            f"❌ Ukuran file melebihi batas maksimal {MAX_FILE_MB} MB "
            f"(file Anda: {file_size_mb:.1f} MB). Harap unggah file yang lebih kecil."
        )
        return

    # --- Process (with caching + spinner) ---
    with st.spinner("⏳ Memindai dan membersihkan data..."):
        try:
            raw_df, clean_df, health, change_log = cached_process(file_bytes, uploaded_file.name)
        except Exception as exc:  # noqa: BLE001
            st.error(f"❌ Terjadi kesalahan tidak terduga: {exc}")
            return

    if raw_df is None:
        st.error("❌ Gagal memproses file. Pastikan format file valid dan tidak rusak.")
        return

    if raw_df.empty or len(raw_df.columns) == 0:
        st.error("❌ File tidak memiliki data yang valid (kosong atau tidak ada kolom).")
        return

    # Info if rows were truncated
    if len(raw_df) >= MAX_ROWS:
        st.info(
            f"ℹ️ File memiliki lebih dari {MAX_ROWS:,} baris. "
            f"Sistem hanya memproses {MAX_ROWS:,} baris pertama."
        )

    # --- Health Alert ---
    st.markdown("---")
    has_issues = (
        health.get("n_duplicates", 0) > 0
        or health.get("n_corrupted_rows", 0) > 0
        or bool(health.get("missing_cols"))
    )
    if has_issues:
        issues_parts = []
        if health["n_duplicates"] > 0:
            issues_parts.append(f"{health['n_duplicates']} baris duplikat")
        if health["n_corrupted_rows"] > 0:
            issues_parts.append(f"{health['n_corrupted_rows']} baris rusak")
        if health["missing_cols"]:
            issues_parts.append(f"{len(health['missing_cols'])} kolom dengan nilai kosong")
        st.warning(
            f"⚠️ **Peringatan Kesehatan Data:** Ditemukan {', '.join(issues_parts)}. "
            f"Sistem telah melakukan pembersihan otomatis."
        )
    else:
        st.success("✅ **Data sudah 100% bersih!** Tidak ditemukan masalah pada dataset.")

    render_health_metrics(health)

    # --- Cleaning Log ---
    with st.expander("🔍 Data Health & Cleaning Log", expanded=has_issues):
        if change_log:
            for entry in change_log:
                st.markdown(f"- {entry}")
        else:
            st.markdown("- Tidak ada perubahan yang dilakukan.")

    # --- Data Preview (Before vs After) ---
    st.markdown("---")
    st.subheader("📋 PRATINJAU DATA")

    if clean_df is None or clean_df.empty:
        st.warning(
            "⚠️ Semua baris telah dihapus setelah proses pembersihan. "
            "Tidak ada data untuk ditampilkan atau divisualisasikan."
        )
        return

    tab_clean, tab_raw = st.tabs(["✅ Data Bersih", "🗂️ Data Asli"])
    with tab_clean:
        st.caption(f"Menampilkan {min(100, len(clean_df))} dari {len(clean_df):,} baris.")
        st.dataframe(clean_df.head(100), use_container_width=True)
    with tab_raw:
        st.caption(f"Menampilkan {min(100, len(raw_df))} dari {len(raw_df):,} baris.")
        st.dataframe(raw_df.head(100), use_container_width=True)

    # --- Download Button ---
    csv_bytes = clean_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Unduh Data Bersih (.csv)",
        data=csv_bytes,
        file_name=f"cleaned_{uploaded_file.name.replace('.xlsx', '.csv')}",
        mime="text/csv",
    )

    # --- Auto-Viz ---
    st.markdown("---")
    st.subheader("📈 VISUALISASI OTOMATIS")

    try:
        roles = classify_columns(clean_df)
        charts = generate_all_charts(clean_df, roles)
    except Exception as exc:  # noqa: BLE001
        st.error(f"❌ Terjadi kesalahan saat menghasilkan visualisasi: {exc}")
        return

    if not charts:
        st.info(
            "ℹ️ Tidak ada grafik yang dapat dibuat dari dataset ini. "
            "Pastikan dataset memiliki setidaknya satu kolom numerik."
        )
        return

    render_charts_grid(charts)


if __name__ == "__main__":
    main()
