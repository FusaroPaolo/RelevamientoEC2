# AWS Inventory & Reporting Toolkit

Repositorio de scripts en Python para **relevamiento** (inventario) y **reporting** sobre una cuenta AWS.
El foco principal es generar archivos fáciles de consumir (CSV/XLSX/JSON/HTML) para auditorías internas, operación y seguimiento.

---

## Scripts incluidos

### 1) Inventario EC2 (CSV + XLSX)
**Script:** `ec2_inventory.py`  
**Salida:**
- `reporte_instancias.csv`
- `reporte_instancias.xlsx`

Incluye por instancia:
- Nombre (Tag `Name`)
- Estado
- IP privada / pública
- VPC ID y **VPC Name**
- Región
- Fecha/hora de consulta (UTC)

> Este es el script “base” usado manualmente desde Cloud9.

### 2) Reporte de red “full” (JSON)
**Script:** `aws_network_report_full_v2.py`  
**Salida:** `aws_network_report_full.json`  
Contenido (por región):
- VPCs + Subnets + IGWs + NAT Gateways
- Security Groups (reglas inbound/outbound)
- EC2 Instances (IPs, SGs, tags, estado)
- RDS Instances
- Lambda Functions  
Además (global):
- S3 Buckets (region + tags cuando sea posible)

### 3) Inventario amplio de recursos (JSON)
**Script:** `aws_resources_report_v2.py`  
**Salida:** `aws_resources_report.json`  
Contenido (por región):
- VPCs, EC2 Instances, Availability Zones
- RDS Instances
- Lambda Functions (+ tags)
- CloudFormation Stacks  
Además (global):
- S3 buckets

Incluye IAM **solo si se solicita**:
- `--include-iam` (usuarios/roles/policies). **Advertencia:** datos sensibles y permisos extra.

### 4) Descarga de costos EC2 (Cost Explorer) (JSON)
**Script:** `aws_ec2_cost_data_downloader_v2.py`  
**Salidas:**
- `ec2_cost_data_daily_total.json` (costo diario total EC2)
- `ec2_cost_data_per_instance_type.json` (costo diario por tipo de instancia)

### 5) Reporte de análisis de costos EC2 (HTML + imágenes)
**Script:** `ec2_cost_analysis_v2.py`  
**Salida:**
- `<out-dir>/ec2_cost_report.html`
- `<out-dir>/images/*.png`

---

## Requisitos

### Base (inventario EC2 CSV/XLSX)
- Python 3.x
- Paquetes:
  - `boto3`
  - `openpyxl`

```bash
pip install boto3 openpyxl
```

### Costos (análisis HTML)
- Paquetes adicionales:
  - `pandas`
  - `matplotlib`

```bash
pip install pandas matplotlib
```

---

## Permisos IAM (por script)

> Recomendación: usar **IAM Role asociado a la instancia Cloud9/EC2** (Instance Profile). Evitar claves estáticas.

### Inventario EC2 (CSV/XLSX)
- `ec2:DescribeRegions`
- `ec2:DescribeInstances`
- `ec2:DescribeVpcs`

### Reporte de red (aws_network_report_full_v2.py)
- EC2:
  - `ec2:DescribeRegions`, `ec2:DescribeVpcs`, `ec2:DescribeSubnets`,
    `ec2:DescribeInternetGateways`, `ec2:DescribeNatGateways`,
    `ec2:DescribeSecurityGroups`, `ec2:DescribeInstances`
- S3 (global):
  - `s3:ListAllMyBuckets`, `s3:GetBucketLocation`
  - `s3:GetBucketTagging` (opcional; si falta, el script registra un error por bucket)
- RDS:
  - `rds:DescribeDBInstances`
- Lambda:
  - `lambda:ListFunctions`

### Inventario amplio (aws_resources_report_v2.py) sin IAM
- EC2:
  - `ec2:DescribeRegions`, `ec2:DescribeVpcs`, `ec2:DescribeInstances`, `ec2:DescribeAvailabilityZones`
- S3:
  - `s3:ListAllMyBuckets`, `s3:GetBucketLocation`, `s3:GetBucketTagging` (opcional)
- RDS:
  - `rds:DescribeDBInstances`
- Lambda:
  - `lambda:ListFunctions`, `lambda:ListTags`
- CloudFormation:
  - `cloudformation:DescribeStacks`

### Inventario amplio con IAM (`--include-iam`)
Además de lo anterior:
- `iam:ListUsers`, `iam:ListRoles`
- `iam:ListAttachedUserPolicies`, `iam:ListUserPolicies`
- `iam:ListAttachedRolePolicies`, `iam:ListRolePolicies`

### Cost Explorer (aws_ec2_cost_data_downloader_v2.py)
- `ce:GetCostAndUsage`

---

## Ejecución manual (Cloud9 / EC2) — flujo actual

### Verificación rápida
```bash
aws sts get-caller-identity
```

### Ejemplo: Inventario EC2
```bash
cd /home/ec2-user/environment/<TU_REPO>
python ec2_inventory.py
ls -lh reporte_instancias.*
```

### Ejemplo: Reporte de red (JSON)
```bash
python aws_network_report_full_v2.py --out-dir output --pretty
ls -lh output/aws_network_report_full.json
```

### Ejemplo: Inventario amplio (JSON)
```bash
python aws_resources_report_v2.py --out-dir output --pretty
# si necesitás IAM (sensible):
python aws_resources_report_v2.py --out-dir output --pretty --include-iam
```

### Ejemplo: Costos EC2 (descarga + análisis)
```bash
python aws_ec2_cost_data_downloader_v2.py --out-dir cost_data --days 30
python ec2_cost_analysis_v2.py --in-dir cost_data --out-dir cost_report
# abrir cost_report/ec2_cost_report.html
```

---

## Automatización mensual con cron (misma instancia Cloud9)

**No cambia el script**, solo cambia cómo se ejecuta.
Condición clave: la instancia Cloud9/EC2 debe estar **encendida** en el horario programado.

### Wrapper recomendado: `run_inventory.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/ec2-user/environment/<TU_REPO>"
OUT_DIR="/home/ec2-user/inventory_reports"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$OUT_DIR"
cd "$REPO_DIR"

/usr/bin/python3 ec2_inventory.py

cp -f reporte_instancias.csv  "${OUT_DIR}/reporte_instancias_${TS}.csv"
cp -f reporte_instancias.xlsx "${OUT_DIR}/reporte_instancias_${TS}.xlsx"
```

Permisos:
```bash
chmod +x /home/ec2-user/environment/<TU_REPO>/run_inventory.sh
```

### Crontab (1er día del mes 08:00)
```bash
crontab -e
```

```cron
0 8 1 * * /home/ec2-user/environment/<TU_REPO>/run_inventory.sh >> /home/ec2-user/inventory_cron.log 2>&1
```

Logs:
```bash
tail -n 200 /home/ec2-user/inventory_cron.log
```

---

## Alternativa a futuro: Lambda + EventBridge (resumen)

Para no depender de una EC2 encendida:
- EventBridge dispara mensual.
- Lambda ejecuta.
- Reportes suelen persistirse en S3 y luego enviarse por email (SES) o link presignado.

Se deja como alternativa futura (requiere empaquetado de dependencias y persistencia en S3).

---

## Seguridad
- No almacenar credenciales AWS en el repo.
- Usar IAM Role de instancia (Instance Profile).
- Mantener permisos mínimos (principio de menor privilegio).
- Tratar con cuidado salidas que incluyan IAM (`--include-iam`) o tags sensibles.
