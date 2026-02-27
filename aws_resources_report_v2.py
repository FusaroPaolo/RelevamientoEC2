#!/usr/bin/env python3
"""
aws_resources_report_v2.py

Inventario amplio de recursos AWS (JSON) con soporte multi-región.

Incluye (por región):
- VPCs
- EC2 Instances
- Availability Zones
- RDS Instances
- Lambda Functions (+ tags)
- CloudFormation Stacks

Incluye (global):
- S3 buckets (location + tags cuando sea posible)
- IAM (opcional con --include-iam)  **SENSIBLE**

Mejoras vs versión original:
- Multi-región (describe_regions)
- Paginators (evita truncamiento)
- CLI: --out-dir, --regions, --include-iam, --pretty

Permisos IAM (mínimos sin IAM):
- ec2:DescribeRegions, ec2:DescribeVpcs, ec2:DescribeInstances, ec2:DescribeAvailabilityZones
- rds:DescribeDBInstances
- lambda:ListFunctions, lambda:ListTags
- cloudformation:DescribeStacks
- s3:ListAllMyBuckets, s3:GetBucketLocation (+ s3:GetBucketTagging opcional)

Permisos extra si --include-iam:
- iam:ListUsers, iam:ListRoles
- iam:ListAttachedUserPolicies, iam:ListUserPolicies
- iam:ListAttachedRolePolicies, iam:ListRolePolicies
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


# -------- Regional
def get_vpcs(ec2) -> List[Dict[str, Any]]:
    out = []
    for page in paginate(ec2, "describe_vpcs"):
        for vpc in page.get("Vpcs", []):
            out.append(
                {
                    "VpcId": vpc.get("VpcId"),
                    "Name": tag_value(vpc.get("Tags"), "Name") or "Sin Nombre",
                    "CidrBlock": vpc.get("CidrBlock"),
                    "IsDefault": vpc.get("IsDefault"),
                    "State": vpc.get("State"),
                    "Tags": vpc.get("Tags", []),
                }
            )
    return out


def get_instances(ec2) -> List[Dict[str, Any]]:
    out = []
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
                        "Tags": inst.get("Tags", []),
                        "LaunchTime": inst.get("LaunchTime").isoformat() if inst.get("LaunchTime") else None,
                    }
                )
    return out


def get_azs(ec2) -> List[Dict[str, Any]]:
    out = []
    for page in paginate(ec2, "describe_availability_zones", AllAvailabilityZones=False):
        for az in page.get("AvailabilityZones", []):
            out.append(
                {
                    "ZoneName": az.get("ZoneName"),
                    "ZoneId": az.get("ZoneId"),
                    "State": az.get("State"),
                    "OptInStatus": az.get("OptInStatus"),
                }
            )
    return out


def get_rds(rds) -> List[Dict[str, Any]]:
    out = []
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
    out = []
    for page in paginate(lam, "list_functions"):
        for fn in page.get("Functions", []):
            arn = fn.get("FunctionArn")
            tags: Any = {}
            try:
                if arn:
                    tags = (lam.list_tags(Resource=arn) or {}).get("Tags", {})
            except ClientError as e:
                tags = {"error": e.response.get("Error", {}).get("Code", "Unknown")}

            out.append(
                {
                    "FunctionName": fn.get("FunctionName"),
                    "FunctionArn": arn,
                    "Runtime": fn.get("Runtime"),
                    "Handler": fn.get("Handler"),
                    "LastModified": fn.get("LastModified"),
                    "Role": fn.get("Role"),
                    "Timeout": fn.get("Timeout"),
                    "MemorySize": fn.get("MemorySize"),
                    "Tags": tags,
                }
            )
    return out


def get_cfn_stacks(cf) -> List[Dict[str, Any]]:
    out = []
    for page in paginate(cf, "describe_stacks"):
        for st in page.get("Stacks", []):
            out.append(
                {
                    "StackName": st.get("StackName"),
                    "StackStatus": st.get("StackStatus"),
                    "CreationTime": st.get("CreationTime").isoformat() if st.get("CreationTime") else None,
                    "LastUpdatedTime": st.get("LastUpdatedTime").isoformat() if st.get("LastUpdatedTime") else None,
                    "Description": st.get("Description"),
                    "Tags": st.get("Tags", []),
                }
            )
    return out


# -------- Global
def get_s3_buckets(s3) -> List[Dict[str, Any]]:
    out = []
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


def get_iam_inventory(iam) -> Dict[str, Any]:
    out: Dict[str, Any] = {"users": [], "roles": []}

    for page in paginate(iam, "list_users"):
        for u in page.get("Users", []):
            uname = u.get("UserName")
            user_obj = {
                "UserName": uname,
                "UserId": u.get("UserId"),
                "Arn": u.get("Arn"),
                "CreateDate": u.get("CreateDate").isoformat() if u.get("CreateDate") else None,
                "AttachedPolicies": [],
                "InlinePolicies": [],
            }
            for ap in paginate(iam, "list_attached_user_policies", UserName=uname):
                user_obj["AttachedPolicies"].extend(ap.get("AttachedPolicies", []))
            for ip in paginate(iam, "list_user_policies", UserName=uname):
                user_obj["InlinePolicies"].extend(ip.get("PolicyNames", []))

            out["users"].append(user_obj)

    for page in paginate(iam, "list_roles"):
        for r in page.get("Roles", []):
            rname = r.get("RoleName")
            role_obj = {
                "RoleName": rname,
                "RoleId": r.get("RoleId"),
                "Arn": r.get("Arn"),
                "CreateDate": r.get("CreateDate").isoformat() if r.get("CreateDate") else None,
                "AttachedPolicies": [],
                "InlinePolicies": [],
            }
            for ap in paginate(iam, "list_attached_role_policies", RoleName=rname):
                role_obj["AttachedPolicies"].extend(ap.get("AttachedPolicies", []))
            for ip in paginate(iam, "list_role_policies", RoleName=rname):
                role_obj["InlinePolicies"].extend(ip.get("PolicyNames", []))

            out["roles"].append(role_obj)

    return out


def build_report(regions: List[str], include_iam: bool) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "generated_at_utc": utc_now_iso(),
        "account_id": get_account_id(),
        "s3_buckets": [],
        "regions": {},
    }

    report["s3_buckets"] = get_s3_buckets(boto3.client("s3"))

    if include_iam:
        try:
            report["iam"] = get_iam_inventory(boto3.client("iam"))
        except ClientError as e:
            report["iam_error"] = str(e)

    for region in regions:
        ec2 = boto3.client("ec2", region_name=region)
        rds = boto3.client("rds", region_name=region)
        lam = boto3.client("lambda", region_name=region)
        cf = boto3.client("cloudformation", region_name=region)

        block: Dict[str, Any] = {}
        try:
            block["vpcs"] = get_vpcs(ec2)
        except ClientError as e:
            block["vpcs_error"] = str(e)
        try:
            block["ec2_instances"] = get_instances(ec2)
        except ClientError as e:
            block["ec2_instances_error"] = str(e)
        try:
            block["availability_zones"] = get_azs(ec2)
        except ClientError as e:
            block["availability_zones_error"] = str(e)
        try:
            block["rds_instances"] = get_rds(rds)
        except ClientError as e:
            block["rds_instances_error"] = str(e)
        try:
            block["lambda_functions"] = get_lambdas(lam)
        except ClientError as e:
            block["lambda_functions_error"] = str(e)
        try:
            block["cloudformation_stacks"] = get_cfn_stacks(cf)
        except ClientError as e:
            block["cloudformation_stacks_error"] = str(e)

        report["regions"][region] = block

    return report


def main():
    ap = argparse.ArgumentParser(description="Inventario amplio AWS (JSON) multi-región.")
    ap.add_argument("--out-dir", default=".", help="Directorio de salida.")
    ap.add_argument("--regions", default="", help="Regiones separadas por coma (opcional).")
    ap.add_argument("--include-iam", action="store_true", help="Incluye inventario IAM (sensible).")
    ap.add_argument("--pretty", action="store_true", help="JSON indentado.")
    args = ap.parse_args()

    regions = [r.strip() for r in args.regions.split(",") if r.strip()] if args.regions else list_regions()
    report = build_report(regions, include_iam=args.include_iam)

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "aws_resources_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2 if args.pretty else None, ensure_ascii=False)

    print(f"Reporte generado: {out_path}")
    print(f"Regiones: {', '.join(regions)}")
    if args.include_iam:
        print("Incluye IAM: SI (tratar como sensible).")


if __name__ == "__main__":
    main()
