# AWS EC2 Inventory Reporter (CSV + XLSX)

Herramienta en Python (boto3) para realizar un relevamiento de instancias EC2 en todas las regiones habilitadas de la cuenta AWS.

Genera:
- Un archivo **CSV** (`reporte_instancias.csv`)
- Un archivo **Excel** (`reporte_instancias.xlsx`)

Incluye por instancia:
- Nombre (Tag `Name`)
- Estado (`running`, `stopped`, `terminated`, etc.)
- IP privada / IP pública
- VPC ID y **VPC Name** (Tag `Name` de la VPC)
- Región
- Fecha/hora de consulta (UTC)

---

## Requisitos

- Python 3.x
- Paquetes:
  - `boto3`
  - `openpyxl`

Instalación:

```bash
pip install boto3 openpyxl
```

---

## Permisos IAM (obligatorio)

La instancia (Cloud9/EC2) que ejecuta el script debe tener un **IAM Role (instance profile)** con permisos de solo lectura para describir recursos EC2.

### Policy mínima (JSON)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DescribeEC2Inventory",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeRegions",
        "ec2:DescribeInstances",
        "ec2:DescribeVpcs"
      ],
      "Resource": "*"
    }
  ]
}
```

> Recomendación: usar credenciales por rol de instancia (Instance Profile) y evitar claves estáticas en el entorno.

### Verificación rápida de credenciales/rol

Antes de ejecutar, validar identidad y acceso:

```bash
aws sts get-caller-identity
aws ec2 describe-regions --query "Regions[].RegionName" --output text
```

---

## Ejecución manual (Cloud9 / EC2) — flujo actual

### Qué pasa cuando lo ejecutás

1. Tu sesión Cloud9 corre sobre una **instancia EC2** (la “instancia de Cloud9”).
2. El script usa **boto3** y toma credenciales automáticamente del **IAM Role asociado a esa instancia** (Instance Profile).
3. El script:
   - Consulta todas las regiones (`DescribeRegions`)
   - En cada región:
     - Trae VPCs (`DescribeVpcs`) y arma un mapa `VpcId -> VPC Name`
     - Trae instancias (`DescribeInstances`) y construye el inventario
   - Escribe los archivos en el filesystem local de la instancia, en el directorio donde lo ejecutaste.

### Dónde quedan los archivos

Por defecto, quedan en el directorio actual:

- `reporte_instancias.csv`
- `reporte_instancias.xlsx`

Ejemplo típico:

```bash
cd /home/ec2-user/environment/<TU_REPO>
python ec2_inventory.py
ls -lh reporte_instancias.*
```

### Requisitos en la instancia Cloud9

- Python 3
- Paquetes:
  ```bash
  pip install --user boto3 openpyxl
  ```
- IAM Role adjunto a la EC2 con:
  - `ec2:DescribeRegions`
  - `ec2:DescribeInstances`
  - `ec2:DescribeVpcs`

### Comportamiento esperado si hay errores

- **AccessDenied / UnauthorizedOperation**: faltan permisos en el rol.
- **NoRegionError**: si boto3 no detecta región; se puede resolver exportando `AWS_DEFAULT_REGION` o seteando región en el cliente inicial.
- **Excel no se genera**: falta `openpyxl`.

---

## Cómo funciona (resumen)

1. Obtiene todas las regiones disponibles con `DescribeRegions`.
2. Para cada región:
   - Consulta VPCs con `DescribeVpcs` y arma un mapa `VpcId -> VPC Name`.
   - Lista instancias con `DescribeInstances`.
   - En cada instancia:
     - Lee `VpcId`, IPs, estado y el Tag `Name`.
     - Resuelve `VPC Name` desde el mapa.
3. Exporta el resultado a CSV y XLSX.

---

## Ejecución programada con cron (misma instancia Cloud9)

Este enfoque **no cambia el script**: solo cambia **cómo se ejecuta**. En vez de correrlo manualmente, lo ejecuta el sistema automáticamente.

### Condición clave

La instancia EC2 donde está Cloud9 **tiene que estar encendida** en el momento programado.  
Si Cloud9 se apaga, cron no corre.

### Flujo del proceso con cron

1. Cron ejecuta el script el día/hora indicada.
2. El script genera CSV/XLSX en la misma instancia.
3. Los archivos quedan guardados localmente (igual que en ejecución manual).
4. (Opcional futuro) otro paso podría enviar email / subir a S3.

### Pasos recomendados

#### 1) Asegurar ruta y entorno

Ubicación típica del repo en Cloud9:  
`/home/ec2-user/environment/<TU_REPO>`

Probar ejecución manual desde ahí:

```bash
cd /home/ec2-user/environment/<TU_REPO>
python ec2_inventory.py
```

#### 2) Crear wrapper `run_inventory.sh`

Esto evita problemas comunes de cron (directorio de trabajo, PATH, python).

`run_inventory.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/ec2-user/environment/<TU_REPO>"
cd "$REPO_DIR"

/usr/bin/python3 ec2_inventory.py
```

Dar permisos:

```bash
chmod +x /home/ec2-user/environment/<TU_REPO>/run_inventory.sh
```

#### 3) Crear carpeta de salida (recomendado)

Para ordenar históricos:

```bash
mkdir -p /home/ec2-user/inventory_reports
```

Si querés que se guarden con fecha sin modificar Python, podés copiar desde el wrapper:

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/home/ec2-user/environment/<TU_REPO>"
OUT_DIR="/home/ec2-user/inventory_reports"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

cd "$REPO_DIR"
/usr/bin/python3 ec2_inventory.py

cp -f reporte_instancias.csv  "${OUT_DIR}/reporte_instancias_${TS}.csv"
cp -f reporte_instancias.xlsx "${OUT_DIR}/reporte_instancias_${TS}.xlsx"
```

#### 4) Configurar cron

Editar crontab:

```bash
crontab -e
```

Ejemplo: **primer día de cada mes a las 08:00**:

```cron
0 8 1 * * /home/ec2-user/environment/<TU_REPO>/run_inventory.sh >> /home/ec2-user/inventory_cron.log 2>&1
```

#### 5) Ver logs

```bash
tail -n 200 /home/ec2-user/inventory_cron.log
```

#### 6) Probar “en el momento” sin esperar al 1 del mes

```bash
/home/ec2-user/environment/<TU_REPO>/run_inventory.sh
```

---

## Alternativa a futuro: Lambda + EventBridge

Para independizarte de una EC2 encendida contantemente:

- **EventBridge** dispara una ejecución mensual (ej. `cron(0 8 1 * ? *)`).
- **Lambda** ejecuta el relevamiento.
- Los archivos suelen guardarse en **S3** (por persistencia) y luego:
  - se envía un email con link (SES) o
  - se comparte un link presignado.

Se deja como alternativa futura porque típicamente requiere:
- empaquetar dependencias (como `openpyxl`) o usar Lambda Layers
- definir persistencia (S3) porque Lambda no tiene disco permanente

---

## Seguridad

- No almacenar credenciales AWS en el repo.
- Usar IAM Role de instancia (Instance Profile).
- Mantener permisos mínimos (principio de menor privilegio).
