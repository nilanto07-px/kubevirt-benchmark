#!/usr/bin/env python3
"""
Generate an interactive HTML dashboard for KubeVirt performance test results for the last X days.

Each tab corresponds to one test folder (e.g., 20251014-165952_kubevirt-perf-test_1-50),
displayed as a tab titled:
    2025-10-14 16:59:52 — 50 VMs

Each tab includes:
  - Results Directory
  - Total VMs
  - Creation Summary (table + chart)
  - Boot Storm Summary (table + chart)
  - Creation Results (sortable DataTable)
  - Boot Storm Results (sortable DataTable)

The dashboard automatically opens the **most recent test tab**.

---------------------------------
Usage:
  python3 generate_dashboard.py [--days N] [--base-dir PATH] [--output-html FILE]

Arguments:
  --days N            Include only folders from the last N days (default: 15)
  --base-dir PATH     Path to the base results directory containing test folders (default: ./results)
  --output-html FILE  Path to save the generated dashboard HTML file (default: ./results_dashboard.html)

Examples:
  # Generate a dashboard from the default 'results' folder for the last 15 days
  python3 generate_dashboard.py

  # Include results from the last 30 days
  python3 generate_dashboard.py --days 30

  # Use a custom results directory and save output to a different location
  python3 generate_dashboard.py --base-dir /mnt/kubevirt/tests --output-html /tmp/kubevirt_dashboard.html
---------------------------------
"""


import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta


def load_json(path):
    """Safely load JSON file."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def get_test_folders(base_dir, days=15):
    """Return a list of timestamped test folders under base_dir/ within last X days."""
    cutoff = datetime.now() - timedelta(days=days)
    folders = []
    for p in base_dir.iterdir():
        if not p.is_dir() or "-" not in p.name:
            continue
        try:
            timestamp_str = p.name.split("_")[0]
            folder_time = datetime.strptime(timestamp_str, "%Y%m%d-%H%M%S")
            if folder_time >= cutoff:
                folders.append(p)
        except Exception:
            continue
    return sorted(folders, key=lambda p: p.name)


def rename_metrics(metric_name):
    mapping = {
        "running_time_sec": "Running Time",
        "ping_time_sec": "Ping Time",
        "clone_duration_sec": "Clone Duration"
    }
    return mapping.get(metric_name, metric_name)


def format_folder_name(folder_name):
    """
    Convert folder name like:
    '20251014-165952_kubevirt-perf-test_1-50'
    → '2025-10-14 16:59:52 — 50 VMs'
    """
    try:
        parts = folder_name.split("_")
        timestamp = parts[0]
        vm_range = parts[-1]
        dt = datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
        num_vms = vm_range.split("-")[-1]
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} — {num_vms} VMs"
    except Exception:
        return folder_name


def df_to_html_table(df, table_id):
    if df.empty:
        return f"<p>No data found for {table_id}</p>"
    return df.to_html(classes="display compact nowrap", table_id=table_id, index=False, border=0)


def summary_to_df(summary_json):
    if not summary_json or "metrics" not in summary_json:
        return pd.DataFrame()
    rows = []
    for m in summary_json["metrics"]:
        rows.append({
            "Metric": rename_metrics(m["metric"]),
            "Average (s)": m["avg"],
            "Max (s)": m["max"],
            "Min (s)": m["min"],
            "Count": m["count"],
        })
    df = pd.DataFrame(rows)
    df.loc[len(df)] = {
        "Metric": "Total VMs",
        "Average (s)": summary_json.get("total_vms"),
        "Max (s)": f"Success: {summary_json.get('successful')}",
        "Min (s)": f"Failed: {summary_json.get('failed')}",
        "Count": ""
    }
    return df


def plotly_chart(df, div_id, title):
    if df.empty:
        return f"<p>No summary data for {title}</p>"
    chart_data = df[df["Metric"].isin(["Running Time", "Ping Time", "Clone Duration"])]
    if chart_data.empty:
        return ""
    js_data = chart_data.to_dict(orient="list")
    return f"""
    <div id="{div_id}" style="height:300px;"></div>
    <script>
    Plotly.newPlot('{div_id}', [{{
        x: {js_data['Metric']},
        y: {js_data['Average (s)']},
        type: 'bar',
        marker: {{color: 'rgb(26, 118, 255)'}}
    }}], {{title: '{title}', yaxis: {{title: 'Seconds'}}}});
    </script>
    """


def build_folder_tab(folder: Path):
    creation_summary = load_json(folder / "summary_vm_creation_results.json")
    boot_summary = load_json(folder / "summary_boot_storm_results.json")
    creation_results = load_json(folder / "vm_creation_results.json")
    boot_results = load_json(folder / "boot_storm_results.json")

    creation_df = pd.DataFrame(creation_results or [])
    boot_df = pd.DataFrame(boot_results or [])
    creation_summary_df = summary_to_df(creation_summary)
    boot_summary_df = summary_to_df(boot_summary)

    if not creation_df.empty and "success" in creation_df.columns:
        cols = [c for c in creation_df.columns if c != "success"] + ["success"]
        creation_df = creation_df[cols]

    folder_id = folder.name.replace("-", "_")
    folder_title = format_folder_name(folder.name)

    # Total VMs line
    total_vms = creation_summary.get("total_vms") if creation_summary else "?"
    total_vms_html = f"<h4><strong>Total VMs:</strong> {total_vms}</h4>"

    # Results directory name
    results_dir_html = f"<h4><strong>Results Directory:</strong> {folder.name}</h4>"

    # Convert to HTML tables
    creation_summary_html = df_to_html_table(creation_summary_df, f"table_summary_creation_{folder_id}")
    boot_summary_html = df_to_html_table(boot_summary_df, f"table_summary_boot_{folder_id}")
    creation_html = df_to_html_table(creation_df, f"table_creation_{folder_id}")
    boot_html = df_to_html_table(boot_df, f"table_boot_{folder_id}")

    # Add charts
    creation_chart = plotly_chart(creation_summary_df, f"chart_creation_{folder_id}", "VM Creation Average Times")
    boot_chart = plotly_chart(boot_summary_df, f"chart_boot_{folder_id}", "Boot Storm Average Times")

    tab_html = f"""
    <div class="tab-pane fade" id="tab_{folder_id}" role="tabpanel">
        {results_dir_html}
        {total_vms_html}

        <h3 class="mt-4">Creation Summary</h3>
        {creation_summary_html}
        {creation_chart}

        <h3 class="mt-5">Boot Storm Summary</h3>
        {boot_summary_html}
        {boot_chart}

        <h3 class="mt-5">Creation Results</h3>
        {creation_html}

        <h3 class="mt-5">Boot Storm Results</h3>
        {boot_html}
    </div>
    """

    nav_html = f'<li class="nav-item" role="presentation"><button class="nav-link" id="tab-{folder_id}-tab" data-bs-toggle="tab" data-bs-target="#tab_{folder_id}" type="button" role="tab">{folder_title}</button></li>'

    return tab_html, nav_html


def build_html_page(test_tabs_html, test_tabs_nav):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>KubeVirt Performance Dashboard</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body {{
  margin: 20px;
}}
h3 {{
  margin-top: 30px;
}}
.dataTables_wrapper {{
  width: 100%;
  margin: 0 auto;
}}
table.dataTable {{
  width: 100% !important;
}}
</style>
</head>
<body>
<h1 class="mb-4">KubeVirt Performance Dashboard</h1>
<p><strong>Generated:</strong> {now}</p>

<ul class="nav nav-tabs" id="myTab" role="tablist">
{''.join(test_tabs_nav)}
</ul>

<div class="tab-content" id="myTabContent">
{''.join(test_tabs_html)}
</div>

<script>
$(document).ready(function() {{
    // Initialize DataTables
    $('table.display').DataTable({{
        scrollX: true,
        autoWidth: false,
        pageLength: 25
    }});

    // Adjust DataTables columns when a tab becomes visible
    $('button[data-bs-toggle="tab"]').on('shown.bs.tab', function (e) {{
        $.fn.dataTable.tables({{ visible: true, api: true }}).columns.adjust();
    }});

    // Activate the last (most recent) tab automatically
    const allTabs = document.querySelectorAll('.nav-link');
    if (allTabs.length > 0) {{
        const lastTab = new bootstrap.Tab(allTabs[allTabs.length - 1]);
        lastTab.show();
    }}
}});
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Generate KubeVirt Performance Dashboard")
    parser.add_argument("--days", type=int, default=15, help="Include folders from the last X days (default: 15)")
    parser.add_argument("--base-dir", type=str, default="results", help="Base directory containing test result folders (default: results/)")
    parser.add_argument("--output-html", type=str, default="results_dashboard.html", help="Path to save generated HTML file (default: results_dashboard.html)")
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    output_html = Path(args.output_html)

    test_folders = get_test_folders(base_dir, days=args.days)
    if not test_folders:
        print(f"No test folders found in {base_dir} from the last {args.days} days.")
        return

    tabs_html, tabs_nav = [], []
    for folder in test_folders:
        print(f"Processing folder: {folder.name}")
        tab_html, nav_html = build_folder_tab(folder)
        tabs_html.append(tab_html)
        tabs_nav.append(nav_html)

    html = build_html_page(tabs_html, tabs_nav)
    output_html.write_text(html, encoding="utf-8")
    print(f"\nDashboard generated: {output_html.absolute()}")


if __name__ == "__main__":
    main()
