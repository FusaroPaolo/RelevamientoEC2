#!/usr/bin/env python3
"""
aws_network_report_full_v2.py

Reporte multi-región de red + recursos básicos (JSON).
Genera: aws_network_report_full.json (por defecto en --out-dir).

Incluye:
- VPCs (con subnets, IGWs, NAT Gateways)
- Security Groups (reglas inbound/outbound)
- EC2 instances (estado, IPs, SGs, tags)
- RDS instances
- Lambda functions
- S3 buckets (global; region + tags cuando sea posible)

Mejoras vs versión original:
- Multi-región (describe_regions)
- Paginators en todas las APIs relevantes (evita truncamiento)
- CLI: --out-dir, --regions, --pretty

Permisos IAM (mínimos):
EC2: DescribeRegions/Vpcs/Subnets/InternetGateways/NatGateways/SecurityGroups/Instances
RDS: DescribeDBInstances
Lambda: ListFunctions
S3: ListAllMyBuckets + GetBucketLocation (+ GetBucketTagging opcional)
"""

import argparse
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def get_account_id() -> Optional[str]:
    try:
        return boto3.client("sts").get_caller_identity().get("Account")
    except Exception:
        return None


def list_regions(explicit: Optional[List[str]] = None) -> List[str]:
    if explicit:
        return explicit
    ec2 = boto3.client("ec2")
    resp = ec2.describe_regions(AllRegions=False)
    return sorted([r["RegionName"] for r in resp.get("Regions", [])])


def paginate(client, op: str, **kwargs):
    for page in client.get_paginator(op).paginate(**kwargs):
        yield page


def tag_value(tags: Optional[List[Dict[str, Any]]], key: str) -> Optional[str]:
    if not tags:
        return None
    for t in tags:
        if t.get("Key") == key:
            return t.get("Value")
    return None


def get_vpcs(ec2) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for page in paginate(ec2, "describe_vpcs"):
        for vpc in page.get("Vpcs", []):
            vpc_id = vpc.get("VpcId")
            vpc_obj: Dict[str, Any] = {
                "VpcId": vpc_id,
                "Name": tag_value(vpc.get("Tags"), "Name") or "Sin Nombre",
                "CidrBlock": vpc.get("CidrBlock"),
                "IsDefault": vpc.get("IsDefault"),
                "State": vpc.get("State"),
                "Tags": vpc.get("Tags", []),
                "Subnets": [],
                "InternetGateways": [],
                "NatGateways": [],
            }

            for s_page in paginate(ec2, "describe_subnets", Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]):
                for s in s_page.get("Subnets", []):
                    vpc_obj["Subnets"].append(
                        {
                            "SubnetId": s.get("SubnetId"),
                            "Name": tag_value(s.get("Tags"), "Name") or "Sin Nombre",
                            "CidrBlock": s.get("CidrBlock"),
                            "AvailabilityZone": s.get("AvailabilityZone"),
                            "MapPublicIpOnLaunch": s.get("MapPublicIpOnLaunch"),
                            "State": s.get("State"),
                            "Tags": s.get("Tags", []),
                        }
                    )

            for igw_page in paginate(
                ec2, "describe_internet_gateways", Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
            ):
                for igw in igw_page.get("InternetGateways", []):
                    vpc_obj["InternetGateways"].append(
                        {
                            "InternetGatewayId": igw.get("InternetGatewayId"),
                            "Name": tag_value(igw.get("Tags"), "Name") or "Sin Nombre",
                            "Tags": igw.get("Tags", []),
                            "Attachments": igw.get("Attachments", []),
                        }
                    )

            # NAT Gateways usa "Filter" (singular) en boto3
            for nat_page in paginate(ec2, "describe_nat_gateways", Filter=[{"Name": "vpc-id", "Values": [vpc_id]}]):
                for nat in nat_page.get("NatGateways", []):
                    vpc_obj["NatGateways"].append(
                        {
                            "NatGatewayId": nat.get("NatGatewayId"),
                            "State": nat.get("State"),
                            "SubnetId": nat.get("SubnetId"),
                            "ConnectivityType": nat.get("ConnectivityType"),
                            "NatGatewayAddresses": nat.get("NatGatewayAddresses", []),
                            "CreateTime": nat.get("CreateTime").isoformat() if nat.get("CreateTime") else None,
                            "Name": tag_value(nat.get("Tags"), "Name") or "Sin Nombre",
                            "Tags": nat.get("Tags", []),
                        }
                    )

            out.append(vpc_obj)
    return out


def get_security_groups(ec2) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for page in paginate(ec2, "describe_security_groups"):
        for sg in page.get("SecurityGroups", []):
            out.append(
                {
                    "GroupId": sg.get("GroupId"),
                    "GroupName": sg.get("GroupName"),
                    "Description": sg.get("Description"),
                    "VpcId": sg.get("VpcId"),
                    "IpPermissions": sg.get("IpPermissions", []),
                    "IpPermissionsEgress": sg.get("IpPermissionsEgress", []),
                    "Tags": sg.get("Tags", []),
                }
            )
    return out


def get_instances(ec2) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for page in paginate(ec2, "describe_instances"):
        for res in page.get("Reservations", []):
            for inst in res.get("Instances", []):
                out.append(
                    {
                        "InstanceId": inst.get("InstanceId"),
                        "Name": tag_value(inst.get("Tags"), "Name") or "Sin Tag Name",
                        "State": (inst.get("State") or {}).get("Name"),
                        "InstanceType": inst.get("InstanceType"),
                        "PrivateIpAddress": inst.get("PrivateIpAddress"),
                        "PublicIpAddress": inst.get("PublicIpAddress"),
                        "VpcId": inst.get("VpcId"),
                        "SubnetId": inst.get("SubnetId"),
                        "SecurityGroups": inst.get("SecurityGroups", []),
                        "Tags": inst.get("Tags", []),
                        "LaunchTime": inst.get("LaunchTime").isoformat() if inst.get("LaunchTime") else None,
                    }
                )
    return out


def get_rds(rds) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for page in paginate(rds, "describe_db_instances"):
        for db in page.get("DBInstances", []):
            out.append(
                {
                    "DBInstanceIdentifier": db.get("DBInstanceIdentifier"),
                    "DBInstanceClass": db.get("DBInstanceClass"),
                    "Engine": db.get("Engine"),
                    "EngineVersion": db.get("EngineVersion"),
                    "DBInstanceStatus": db.get("DBInstanceStatus"),
                    "MultiAZ": db.get("MultiAZ"),
                    "PubliclyAccessible": db.get("PubliclyAccessible"),
                    "VpcId": (db.get("DBSubnetGroup") or {}).get("VpcId"),
                }
            )
    return out


def get_lambdas(lam) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for page in paginate(lam, "list_functions"):
        for fn in page.get("Functions", []):
            out.append(
                {
                    "FunctionName": fn.get("FunctionName"),
                    "Runtime": fn.get("Runtime"),
                    "Handler": fn.get("Handler"),
                    "LastModified": fn.get("LastModified"),
                    "Role": fn.get("Role"),
                    "Timeout": fn.get("Timeout"),
                    "MemorySize": fn.get("MemorySize"),
                }
            )
    return out


def get_s3_buckets(s3) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        resp = s3.list_buckets()
    except ClientError as e:
        return [{"error": f"list_buckets failed: {str(e)}"}]

    for b in resp.get("Buckets", []):
        name = b.get("Name")
        created = b.get("CreationDate")
        region = "us-east-1"
        try:
            loc = s3.get_bucket_location(Bucket=name).get("LocationConstraint")
            region = loc or "us-east-1"
        except ClientError:
            region = "Desconocida"

        tags = []
        try:
            tags = (s3.get_bucket_tagging(Bucket=name) or {}).get("TagSet", [])
        except ClientError as e:
            tags = [{"error": e.response.get("Error", {}).get("Code", "Unknown")}]

        out.append(
            {
                "Name": name,
                "CreationDate": created.isoformat() if created else None,
                "Region": region,
                "Tags": tags,
            }
        )
    return out


def build_report(regions: List[str]) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "generated_at_utc": utc_now_iso(),
        "account_id": get_account_id(),
        "s3_buckets": [],
        "regions": {},
    }

    # S3 global
    report["s3_buckets"] = get_s3_buckets(boto3.client("s3"))

    for region in regions:
        ec2 = boto3.client("ec2", region_name=region)
        rds = boto3.client("rds", region_name=region)
        lam = boto3.client("lambda", region_name=region)

        block: Dict[str, Any] = {}
        try:
            block["vpcs"] = get_vpcs(ec2)
        except ClientError as e:
            block["vpcs_error"] = str(e)

        try:
            block["security_groups"] = get_security_groups(ec2)
        except ClientError as e:
            block["security_groups_error"] = str(e)

        try:
            block["ec2_instances"] = get_instances(ec2)
        except ClientError as e:
            block["ec2_instances_error"] = str(e)

        try:
            block["rds_instances"] = get_rds(rds)
        except ClientError as e:
            block["rds_instances_error"] = str(e)

        try:
            block["lambda_functions"] = get_lambdas(lam)
        except ClientError as e:
            block["lambda_functions_error"] = str(e)

        report["regions"][region] = block

    return report


def main():
    ap = argparse.ArgumentParser(description="Reporte multi-región de red/recursos (JSON).")
    ap.add_argument("--out-dir", default=".", help="Directorio de salida.")
    ap.add_argument("--regions", default="", help="Regiones separadas por coma (opcional).")
    ap.add_argument("--pretty", action="store_true", help="JSON indentado (más legible).")
    args = ap.parse_args()

    regions = [r.strip() for r in args.regions.split(",") if r.strip()] if args.regions else list_regions()

    report = build_report(regions)
    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "aws_network_report_full.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2 if args.pretty else None, ensure_ascii=False)

    print(f"Reporte generado: {out_path}")
    print(f"Regiones: {', '.join(regions)}")


if __name__ == "__main__":
    main()
