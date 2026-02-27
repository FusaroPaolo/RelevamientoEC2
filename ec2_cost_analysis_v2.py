#!/usr/bin/env python3
"""
ec2_cost_analysis_v2.py

Genera un reporte HTML de costos EC2 y gráficos a partir de:
- ec2_cost_data_daily_total.json (recomendado)
- ec2_cost_data_per_instance_type.json (requerido)

Si el total diario no existe, lo deriva sumando los costos por tipo.

Requisitos:
- pandas
- matplotlib
"""

import argparse
import json
import os
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import matplotlib.pyplot as plt


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def df_daily_total(results: List[Dict[str, Any]]) -> pd.DataFrame:
    rec = []
    for e in results:
        rec.append(
            {
                "Date": e["TimePeriod"]["Start"],
                "Cost": float(e["Total"]["UnblendedCost"]["Amount"]),
            }
        )
    df = pd.DataFrame(rec)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date")


def df_by_type(results: List[Dict[str, Any]]) -> pd.DataFrame:
    rec = []
    for e in results:
        date = e["TimePeriod"]["Start"]
        for g in e.get("Groups", []):
            itype = g["Keys"][0] if g.get("Keys") else "UNKNOWN"
            cost = float(g["Metrics"]["UnblendedCost"]["Amount"])
            rec.append({"Date": date, "InstanceType": itype, "Cost": cost})
    df = pd.DataFrame(rec)
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date")


def derive_daily_from_type(df_type: pd.DataFrame) -> pd.DataFrame:
    df = df_type.groupby("Date", as_index=False)["Cost"].sum()
    df = df.rename(columns={"Cost": "Cost"})
    return df.sort_values("Date")


def analyze(df_daily: pd.DataFrame) -> Dict[str, Any]:
    if df_daily.empty:
        return {
            "total_cost": 0.0,
            "average_cost": 0.0,
            "max_cost": 0.0,
            "max_cost_date": None,
            "min_cost": 0.0,
            "min_cost_date": None,
        }
    total = float(df_daily["Cost"].sum())
    avg = float(df_daily["Cost"].mean())
    mx = float(df_daily["Cost"].max())
    mn = float(df_daily["Cost"].min())
    mx_date = df_daily.loc[df_daily["Cost"].idxmax(), "Date"].strftime("%Y-%m-%d")
    mn_date = df_daily.loc[df_daily["Cost"].idxmin(), "Date"].strftime("%Y-%m-%d")
    return {
        "total_cost": total,
        "average_cost": avg,
        "max_cost": mx,
        "max_cost_date": mx_date,
        "min_cost": mn,
        "min_cost_date": mn_date,
    }


def plot_daily(df_daily: pd.DataFrame, images_dir: str) -> str:
    out = os.path.join(images_dir, "cost_over_time.png")
    plt.figure(figsize=(10, 6))
    plt.plot(df_daily["Date"], df_daily["Cost"], marker="o")
    plt.title("Costo Diario de Instancias EC2")
    plt.xlabel("Fecha")
    plt.ylabel("Costo (USD)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(out)
    plt.close()
    return out


def plot_by_type(df_type: pd.DataFrame, images_dir: str) -> str:
    out = os.path.join(images_dir, "cost_per_instance_type.png")
    totals = df_type.groupby("InstanceType", as_index=False)["Cost"].sum().sort_values("Cost", ascending=False)
    plt.figure(figsize=(12, 6))
    plt.bar(totals["InstanceType"], totals["Cost"])
    plt.title("Costo por Tipo de Instancia EC2 (Total del Período)")
    plt.xlabel("Tipo de Instancia")
    plt.ylabel("Costo (USD)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out)
    plt.close()
    return out


def write_html(analysis: Dict[str, Any], line_plot: str, bar_plot: str, report_path: str):
    line_rel = os.path.relpath(line_plot, os.path.dirname(report_path))
    bar_rel = os.path.relpath(bar_plot, os.path.dirname(report_path))

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Informe de Costos EC2</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 40px; }}
    table {{ border-collapse: collapse; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background: #f2f2f2; }}
    img {{ max-width: 100%; height: auto; }}
  </style>
</head>
<body>
  <h1>Informe de Análisis de Costos de Instancias EC2</h1>

  <h2>Resumen</h2>
  <table>
    <tr><th>Costo Total (USD)</th><td>{analysis["total_cost"]:.4f}</td></tr>
    <tr><th>Costo Promedio Diario (USD)</th><td>{analysis["average_cost"]:.4f}</td></tr>
    <tr><th>Día con Mayor Costo</th><td>{analysis["max_cost_date"]} ({analysis["max_cost"]:.4f} USD)</td></tr>
    <tr><th>Día con Menor Costo</th><td>{analysis["min_cost_date"]} ({analysis["min_cost"]:.4f} USD)</td></tr>
  </table>

  <h2>Gráfico: Costo Diario</h2>
  <img src="{line_rel}" alt="Costo diario"/>

  <h2>Gráfico: Costo por Tipo de Instancia</h2>
  <img src="{bar_rel}" alt="Costo por tipo de instancia"/>

  <p>Generado el {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC</p>
</body>
</html>
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser(description="Genera reporte HTML de costos EC2.")
    ap.add_argument("--in-dir", default=".", help="Directorio donde están los JSONs.")
    ap.add_argument("--out-dir", default="output", help="Directorio de salida del reporte.")
    args = ap.parse_args()

    in_dir = args.in_dir
    out_dir = args.out_dir
    images_dir = os.path.join(out_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    type_path = os.path.join(in_dir, "ec2_cost_data_per_instance_type.json")
    daily_path = os.path.join(in_dir, "ec2_cost_data_daily_total.json")

    if not os.path.exists(type_path):
        raise SystemExit(f"Falta archivo requerido: {type_path}")

    df_type = df_by_type(load_json(type_path))

    if os.path.exists(daily_path):
        df_daily = df_daily_total(load_json(daily_path))
    else:
        df_daily = derive_daily_from_type(df_type)

    analysis = analyze(df_daily)
    line_plot = plot_daily(df_daily, images_dir)
    bar_plot = plot_by_type(df_type, images_dir)

    report_path = os.path.join(out_dir, "ec2_cost_report.html")
    write_html(analysis, line_plot, bar_plot, report_path)

    print(f"OK. Reporte generado: {report_path}")


if __name__ == "__main__":
    main()
