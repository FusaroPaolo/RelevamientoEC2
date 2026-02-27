#!/usr/bin/env python3
"""
aws_ec2_cost_data_downloader_v2.py

Descarga costos de EC2 desde AWS Cost Explorer y genera 2 archivos JSON:
- ec2_cost_data_daily_total.json
- ec2_cost_data_per_instance_type.json

Mejoras:
- CLI: --days, --start, --end (end inclusivo), --granularity, --out-dir
- Cost Explorer client en us-east-1 (más compatible)

Permisos IAM: ce:GetCostAndUsage
"""

import argparse
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError


def parse_date(s: str) -> str:
    datetime.strptime(s, "%Y-%m-%d")
    return s


def date_range_from_days(days: int) -> (str, str):
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    end_exclusive = end + timedelta(days=1)
    return start.strftime("%Y-%m-%d"), end_exclusive.strftime("%Y-%m-%d")


def ce_client():
    return boto3.client("ce", region_name="us-east-1")


def get_cost_total(start: str, end: str, granularity: str) -> List[Dict[str, Any]]:
    ce = ce_client()
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity=granularity,
        Metrics=["UnblendedCost"],
        Filter={"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Elastic Compute Cloud - Compute"]}},
    )
    return resp.get("ResultsByTime", [])


def get_cost_by_instance_type(start: str, end: str, granularity: str) -> List[Dict[str, Any]]:
    ce = ce_client()
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity=granularity,
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "INSTANCE_TYPE"}],
        Filter={"Dimensions": {"Key": "SERVICE", "Values": ["Amazon Elastic Compute Cloud - Compute"]}},
    )
    return resp.get("ResultsByTime", [])


def main():
    ap = argparse.ArgumentParser(description="Descarga costos EC2 desde Cost Explorer (total + por tipo).")
    ap.add_argument("--days", type=int, default=30, help="Días hacia atrás (default 30).")
    ap.add_argument("--start", type=parse_date, default="", help="Inicio YYYY-MM-DD.")
    ap.add_argument("--end", type=parse_date, default="", help="Fin INCLUSIVO YYYY-MM-DD.")
    ap.add_argument("--granularity", default="DAILY", choices=["DAILY", "MONTHLY"])
    ap.add_argument("--out-dir", default=".", help="Directorio de salida.")
    args = ap.parse_args()

    if args.start and args.end:
        end_excl = (datetime.strptime(args.end, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
        start, end = args.start, end_excl
    else:
        start, end = date_range_from_days(args.days)

    os.makedirs(args.out_dir, exist_ok=True)

    try:
        total = get_cost_total(start, end, args.granularity)
        by_type = get_cost_by_instance_type(start, end, args.granularity)
    except ClientError as e:
        raise SystemExit(f"ERROR Cost Explorer: {e}")

    total_path = os.path.join(args.out_dir, "ec2_cost_data_daily_total.json")
    type_path = os.path.join(args.out_dir, "ec2_cost_data_per_instance_type.json")

    with open(total_path, "w", encoding="utf-8") as f:
        json.dump(total, f, ensure_ascii=False, indent=2)
    with open(type_path, "w", encoding="utf-8") as f:
        json.dump(by_type, f, ensure_ascii=False, indent=2)

    print(f"OK. Rango: {start} -> {end} (End exclusivo)")
    print(f"Generado: {total_path}")
    print(f"Generado: {type_path}")


if __name__ == "__main__":
    main()
