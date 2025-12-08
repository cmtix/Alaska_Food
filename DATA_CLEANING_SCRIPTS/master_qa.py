#!/usr/bin/env python3
"""
Lightweight QA module for ISER Food Pricing master build.

This replaces a corrupted previous version but keeps the same public API:

    run_master_qa(builds_root, central_log_path, build_tag, manifest_path)

and the same manifest fields written by master_assembly.py:

    build_tag, build_dir, qa_dir, qa_site_dir, panel_csv

Outputs (all CSVs go into qa_dir):

    QA_missing_by_column_{tag}.csv
    QA_missing_by_row_count_distribution_{tag}.csv
    QA_missing_overall_summary_{tag}.csv
    QA_missing_by_source_file_{tag}.csv      (if SOURCE_FILE column exists)
    QA_missing_by_month_{tag}.csv           (HOME_STORE_NAME x MONTH_LABEL)

    QA_counts_overall_{tag}.csv
    QA_counts_by_home_store_{tag}.csv
    QA_counts_by_year_{tag}.csv             (if YEAR exists)
    QA_counts_by_month_{tag}.csv            (if YEAR/MONTH exist)
    QA_counts_by_month_home_store_{tag}.csv (if HOME_STORE_NAME & dates exist)
    QA_counts_by_month_primary_store_key_{tag}.csv
                                           (if PRIMARY_STORE_KEY & dates exist)

It also writes a static PNG barplot of missingness by column and
a simple HTML "QA site" page linking to all outputs.
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# -------------------------------------------------------------------
# Logging helpers
# -------------------------------------------------------------------
def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_line(central_log_path: Optional[Path], msg: str) -> None:
    """
    Write a log line to stdout and to central_log_path (if provided).
    """
    line = f"{_timestamp()} {msg}"
    print(line)
    if central_log_path is not None:
        try:
            central_log_path.parent.mkdir(parents = True, exist_ok = True)
            with central_log_path.open("a", encoding = "utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            # Logging failure should never break the pipeline
            pass


# -------------------------------------------------------------------
# Manifest / data loading
# -------------------------------------------------------------------
def _load_manifest(builds_root: Path, build_tag: Optional[str]) -> Path:
    """
    Fallback manifest lookup if run_master_qa is called from CLI
    without manifest_path. It picks the manifest for build_tag,
    or the latest manifest if build_tag is None.
    """
    builds_root = Path(builds_root)
    if build_tag:
        cand = list(builds_root.glob(f"{build_tag}/MASTER_manifest_{build_tag}.json"))
        if cand:
            return cand[0]

    # Fall back to latest manifest by mtime
    manifests: List[Path] = list(builds_root.glob("*/MASTER_manifest_*.json"))
    if not manifests:
        raise FileNotFoundError(f"No manifest JSON files found under {builds_root}")
    manifests.sort(key = lambda p: p.stat().st_mtime, reverse = True)
    return manifests[0]


def _read_df(panel_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(panel_csv)
    return df


# -------------------------------------------------------------------
# Date helpers
# -------------------------------------------------------------------
def _derive_panel_date(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure PANEL_DATE, YEAR, and MONTH exist when possible.
    """
    out = df.copy()

    # Prefer an existing PANEL_DATE
    d = None
    if "PANEL_DATE" in out.columns:
        d = pd.to_datetime(out["PANEL_DATE"], errors = "coerce")
    else:
        for c in ["PULL_DATE", "Pull_Date", "DATE", "Date"]:
            if c in out.columns:
                d = pd.to_datetime(out[c], errors = "coerce")
                break

    if d is None or (isinstance(d, pd.Series) and d.isna().all()):
        # Try to build from YEAR / MONTH if available
        if "YEAR" in out.columns and "MONTH" in out.columns:
            y = pd.to_numeric(out["YEAR"], errors = "coerce")
            m = pd.to_numeric(out["MONTH"], errors = "coerce")
            d = pd.to_datetime(
                dict(year = y, month = m, day = 1),
                errors = "coerce",
            )
        elif "MONTH" in out.columns:
            # Best-effort month-only dates (no real year information)
            m = pd.to_numeric(out["MONTH"], errors = "coerce")
            d = pd.to_datetime(
                {"year": 2000, "month": m, "day": 1},
                errors = "coerce",
            )

    if not isinstance(d, pd.Series):
        d = pd.Series([pd.NaT] * len(out), index = out.index)

    out["PANEL_DATE"] = d

    if "YEAR" not in out.columns:
        out["YEAR"] = out["PANEL_DATE"].dt.year

    if "MONTH" not in out.columns:
        out["MONTH"] = out["PANEL_DATE"].dt.month

    return out


def _safe_month_label(year_series: pd.Series, month_series: pd.Series) -> pd.Series:
    """
    Build a YYYY-MM label safely, without failing on NaNs.

    Any row with missing YEAR or MONTH gets MONTH_LABEL = 'UNKNOWN'.
    """
    if year_series is None or month_series is None:
        return pd.Series(["UNKNOWN"] * len(year_series), index = year_series.index)

    y = pd.to_numeric(year_series, errors = "coerce")
    m = pd.to_numeric(month_series, errors = "coerce")

    labels = pd.Series(["UNKNOWN"] * len(y), index = y.index)
    mask = y.notna() & m.notna()
    if mask.any():
        labels.loc[mask] = (
            y.loc[mask].astype(int).astype(str)
            + "-"
            + m.loc[mask].astype(int).astype(str).str.zfill(2)
        )
    return labels


# -------------------------------------------------------------------
# Core QA calculations
# -------------------------------------------------------------------
def _write_qa_csvs(master_long: pd.DataFrame, qa_dir: Path, tag: str) -> Dict[str, Any]:
    qa_dir.mkdir(parents = True, exist_ok = True)

    # --- Paths ---
    missing_by_col_path = qa_dir / f"QA_missing_by_column_{tag}.csv"
    missing_by_row_dist_path = qa_dir / f"QA_missing_by_row_count_distribution_{tag}.csv"
    overall_summary_path = qa_dir / f"QA_missing_overall_summary_{tag}.csv"
    missing_by_source_file_path = qa_dir / f"QA_missing_by_source_file_{tag}.csv"
    missing_by_month_path = qa_dir / f"QA_missing_by_month_{tag}.csv"

    counts_overall_path = qa_dir / f"QA_counts_overall_{tag}.csv"
    counts_by_home_store_path = qa_dir / f"QA_counts_by_home_store_{tag}.csv"
    counts_by_year_path = qa_dir / f"QA_counts_by_year_{tag}.csv"
    counts_by_month_path = qa_dir / f"QA_counts_by_month_{tag}.csv"
    counts_by_month_store_path = qa_dir / f"QA_counts_by_month_home_store_{tag}.csv"
    counts_by_month_storekey_path = qa_dir / f"QA_counts_by_month_primary_store_key_{tag}.csv"

    # --- Basic missingness ---
    total_rows, total_columns = master_long.shape
    total_cells = int(total_rows * total_columns)
    total_missing = int(master_long.isna().sum().sum())

    col_miss = master_long.isna().sum().rename("missing_cells").reset_index()
    col_miss = col_miss.rename(columns = {"index": "column"})
    col_miss["total_rows"] = total_rows
    col_miss["pct_missing_cells"] = (
        col_miss["missing_cells"] / col_miss["total_rows"] if total_rows > 0 else np.nan
    )
    col_miss = col_miss.sort_values("pct_missing_cells", ascending = False)
    col_miss.to_csv(missing_by_col_path, index = False)

    row_missing_counts = master_long.isna().sum(axis = 1)
    row_dist = (
        row_missing_counts.value_counts()
        .rename_axis("n_missing_cells")
        .reset_index(name = "n_rows")
        .sort_values("n_missing_cells")
    )
    row_dist.to_csv(missing_by_row_dist_path, index = False)

    overall = pd.DataFrame(
        [
            {
                "total_rows": total_rows,
                "total_columns": total_columns,
                "total_cells": total_cells,
                "total_missing_cells": total_missing,
                "pct_missing_cells": (
                    total_missing / total_cells if total_cells > 0 else np.nan
                ),
            }
        ]
    )
    overall.to_csv(overall_summary_path, index = False)

    # --- Missingness by source file (if column exists) ---
    if "SOURCE_FILE" in master_long.columns:
        tmp = master_long.copy()
        tmp["row_missing"] = row_missing_counts
        miss_by_source = tmp.groupby("SOURCE_FILE", as_index = False).agg(
            n_rows = ("row_missing", "size"),
            missing_cells = ("row_missing", "sum"),
        )
        miss_by_source["pct_missing_cells"] = (
            miss_by_source["missing_cells"]
            / (miss_by_source["n_rows"] * total_columns)
            if total_columns > 0
            else np.nan
        )
        miss_by_source = miss_by_source.sort_values(
            "pct_missing_cells", ascending = False
        )
        miss_by_source.to_csv(missing_by_source_file_path, index = False)
    else:
        miss_by_source = pd.DataFrame(
            columns = ["SOURCE_FILE", "n_rows", "missing_cells", "pct_missing_cells"]
        )
        miss_by_source.to_csv(missing_by_source_file_path, index = False)

    # --- Date and month labels for coverage tables ---
    tmp_dates = _derive_panel_date(master_long)
    tmp_dates["MONTH_LABEL"] = _safe_month_label(
        tmp_dates.get("YEAR"), tmp_dates.get("MONTH")
    )

    # --- Counts overall ---
    counts_overall = overall.copy()
    counts_overall.to_csv(counts_overall_path, index = False)

    # --- Counts by home store ---
    if "HOME_STORE_NAME" in tmp_dates.columns:
        counts_by_store = (
            tmp_dates.groupby("HOME_STORE_NAME", as_index = False)
            .agg(n_records = ("HOME_STORE_NAME", "size"))
            .sort_values("HOME_STORE_NAME")
        )
        counts_by_store.to_csv(counts_by_home_store_path, index = False)
    else:
        counts_by_store = pd.DataFrame(columns = ["HOME_STORE_NAME", "n_records"])
        counts_by_store.to_csv(counts_by_home_store_path, index = False)

    # --- Counts by YEAR ---
    if "YEAR" in tmp_dates.columns:
        counts_by_year = (
            tmp_dates.groupby("YEAR", as_index = False)
            .agg(n_records = ("YEAR", "size"))
            .sort_values("YEAR")
        )
        counts_by_year.to_csv(counts_by_year_path, index = False)
    else:
        counts_by_year = pd.DataFrame(columns = ["YEAR", "n_records"])
        counts_by_year.to_csv(counts_by_year_path, index = False)

    # --- Counts by MONTH_LABEL ---
    if "MONTH_LABEL" in tmp_dates.columns:
        counts_by_month = (
            tmp_dates.groupby("MONTH_LABEL", as_index = False)
            .agg(n_records = ("MONTH_LABEL", "size"))
            .sort_values("MONTH_LABEL")
        )
        counts_by_month.to_csv(counts_by_month_path, index = False)
    else:
        counts_by_month = pd.DataFrame(columns = ["MONTH_LABEL", "n_records"])
        counts_by_month.to_csv(counts_by_month_path, index = False)

    # --- Counts by MONTH_LABEL & HOME_STORE_NAME ---
    if "HOME_STORE_NAME" in tmp_dates.columns and "MONTH_LABEL" in tmp_dates.columns:
        counts_by_month_store = (
            tmp_dates.groupby(["HOME_STORE_NAME", "MONTH_LABEL"], as_index = False)
            .agg(n_records = ("HOME_STORE_NAME", "size"))
            .sort_values(["HOME_STORE_NAME", "MONTH_LABEL"])
        )
        # Add STATUS column like before
        counts_by_month_store["STATUS"] = np.where(
            counts_by_month_store["n_records"] > 0, "OK", "MISSING"
        )
        counts_by_month_store.to_csv(counts_by_month_store_path, index = False)

        # For the "missing_by_month" QA table, we use the same content
        miss_by_month = counts_by_month_store.copy()
        miss_by_month.to_csv(missing_by_month_path, index = False)
    else:
        counts_by_month_store = pd.DataFrame(
            columns = ["HOME_STORE_NAME", "MONTH_LABEL", "n_records", "STATUS"]
        )
        counts_by_month_store.to_csv(counts_by_month_store_path, index = False)
        counts_by_month_store.to_csv(missing_by_month_path, index = False)

    # --- Counts by MONTH_LABEL & PRIMARY_STORE_KEY ---
    if "PRIMARY_STORE_KEY" in tmp_dates.columns and "MONTH_LABEL" in tmp_dates.columns:
        counts_by_month_storekey = (
            tmp_dates.groupby(["PRIMARY_STORE_KEY", "MONTH_LABEL"], as_index = False)
            .agg(n_records = ("PRIMARY_STORE_KEY", "size"))
            .sort_values(["PRIMARY_STORE_KEY", "MONTH_LABEL"])
        )
        counts_by_month_storekey.to_csv(counts_by_month_storekey_path, index = False)
    else:
        counts_by_month_storekey = pd.DataFrame(
            columns = ["PRIMARY_STORE_KEY", "MONTH_LABEL", "n_records"]
        )
        counts_by_month_storekey.to_csv(counts_by_month_storekey_path, index = False)

    return {
        "col_miss_df": col_miss,
        "row_missing_counts": row_missing_counts,
        "overall_summary": overall,
        "miss_by_source": miss_by_source,
        "counts_overall": counts_overall,
        "counts_by_store": counts_by_store,
        "counts_by_year": counts_by_year,
        "counts_by_month": counts_by_month,
        "counts_by_month_store": counts_by_month_store,
        "counts_by_month_storekey": counts_by_month_storekey,
    }


# -------------------------------------------------------------------
# Static plot and HTML QA site
# -------------------------------------------------------------------
def _write_static_plot(col_miss_df: pd.DataFrame, qa_dir: Path, tag: str) -> Path:
    qa_dir.mkdir(parents = True, exist_ok = True)
    plot_path = qa_dir / f"QA_missing_by_column_{tag}.png"

    if col_miss_df.empty:
        # Create an empty placeholder plot
        plt.figure(figsize = (6, 4))
        plt.text(0.5, 0.5, "No data", ha = "center", va = "center")
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(plot_path, dpi = 120)
        plt.close()
        return plot_path

    df = col_miss_df.sort_values("pct_missing_cells", ascending = False)
    plt.figure(figsize = (max(6, len(df) * 0.3), 4))
    plt.bar(df["column"], df["pct_missing_cells"])
    plt.xticks(rotation = 90)
    plt.ylabel("Pct missing cells")
    plt.tight_layout()
    plt.savefig(plot_path, dpi = 120)
    plt.close()
    return plot_path


def _write_html_site(qa_dir: Path, qa_site_dir: Path, tag: str, plot_path: Path) -> Path:
    qa_site_dir.mkdir(parents = True, exist_ok = True)
    html_path = qa_site_dir / f"MASTER_QA_site_{tag}.html"

    # Relative path from site dir to QA PNG
    rel_plot = Path("..") / qa_dir.name / plot_path.name

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ISER Food Pricing — QA Site {tag}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
</head>
<body class="bg-light">
<div class="container my-4">
  <h1 class="mb-3">ISER Food Pricing — QA Site {tag}</h1>
  <p class="text-muted">Quick overview of missingness and record counts for master build <code>{tag}</code>.</p>

  <h2 class="h4 mt-4">Missing by Column</h2>
  <p><a href="../{qa_dir.name}/QA_missing_by_column_{tag}.csv">Download CSV</a></p>
  <img src="{rel_plot.as_posix()}" alt="Missing by column" class="img-fluid border rounded">

  <h2 class="h4 mt-4">Missingness Summary</h2>
  <ul>
    <li><a href="../{qa_dir.name}/QA_missing_overall_summary_{tag}.csv">Overall summary</a></li>
    <li><a href="../{qa_dir.name}/QA_missing_by_row_count_distribution_{tag}.csv">Row missing-count distribution</a></li>
    <li><a href="../{qa_dir.name}/QA_missing_by_source_file_{tag}.csv">Missing by source file</a></li>
    <li><a href="../{qa_dir.name}/QA_missing_by_month_{tag}.csv">Missing / counts by month &amp; store</a></li>
  </ul>

  <h2 class="h4 mt-4">Record Counts</h2>
  <ul>
    <li><a href="../{qa_dir.name}/QA_counts_overall_{tag}.csv">Counts overall</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_home_store_{tag}.csv">Counts by home store</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_year_{tag}.csv">Counts by year</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_month_{tag}.csv">Counts by month</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_month_home_store_{tag}.csv">Counts by month &amp; home store</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_month_primary_store_key_{tag}.csv">Counts by month &amp; primary store key</a></li>
  </ul>
</div>
</body>
</html>
"""
    html_path.write_text(html, encoding = "utf-8")
    return html_path


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def run_master_qa(
    builds_root: Path,
    central_log_path: Optional[Path],
    build_tag: Optional[str],
    manifest_path: Optional[Path],
) -> None:
    start = datetime.now()
    try:
        if manifest_path is None:
            manifest_path = _load_manifest(builds_root, build_tag)

        manifest = json.loads(Path(manifest_path).read_text(encoding = "utf-8"))
        tag = manifest["build_tag"]
        build_dir = Path(manifest["build_dir"])
        qa_dir = Path(manifest["qa_dir"])
        qa_site_dir = Path(manifest["qa_site_dir"])
        panel_csv = Path(manifest["panel_csv"])

        log_line(central_log_path, f"[MASTER_QA] START tag={tag}")

        df = _read_df(panel_csv)
        df = _derive_panel_date(df)

        qa = _write_qa_csvs(df, qa_dir, tag)
        plot_path = _write_static_plot(qa["col_miss_df"], qa_dir, tag)
        html_path = _write_html_site(qa_dir, qa_site_dir, tag, plot_path)

        elapsed = datetime.now() - start
        log_line(
            central_log_path,
            f"[MASTER_QA] SUCCESS tag={tag} elapsed={str(elapsed).split('.')[0]} HTML={html_path}",
        )
    except Exception as e:
        elapsed = datetime.now() - start
        log_line(
            central_log_path,
            f"[MASTER_QA] FAIL elapsed={str(elapsed).split('.')[0]} error={e}",
        )
        raise


# -------------------------------------------------------------------
# CLI entry point (optional)
# -------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--clean-root", type = str, required = True)
    p.add_argument("--central-log", type = str, default = "")
    p.add_argument("--build-tag", type = str, default = "")
    p.add_argument("--manifest", type = str, default = "")
    args = p.parse_args()

    builds_root = Path(args.clean_root) / "MASTER_builds"
    central_log_path = Path(args.central_log) if args.central_log else None
    build_tag = args.build_tag if args.build_tag else None
    manifest_path = Path(args.manifest) if args.manifest else None

    run_master_qa(builds_root, central_log_path, build_tag, manifest_path)


if __name__ == "__main__":
    main()
