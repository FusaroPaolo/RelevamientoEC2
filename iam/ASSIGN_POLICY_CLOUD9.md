# Asignar políticas IAM a una instancia Cloud9 (EC2) — `Instancia_Relevameintos`

Esta guía explica cómo asignar un **IAM Role (Instance Profile)** a la instancia EC2 que usa Cloud9 para poder ejecutar los scripts de relevamiento y generar reportes localmente (CSV/XLSX/JSON).

> Objetivo: que la instancia **Instancia_Relevameintos** pueda ejecutar los scripts (inventario/red/recursos/costos) usando credenciales temporales del rol, sin claves estáticas.

---

## Archivos incluidos

- `iam/relevamientos_iam_policies.json`
  - `trust_policy_ec2_assume_role`
  - `policy_relevamientos_base_readonly`
  - `policy_relevamientos_cost_explorer_readonly` (opcional)
  - `policy_relevamientos_iam_readonly_optional` (opcional y sensible)

---

## 1) Elegir qué políticas necesitás

### A. Base (inventario/red/recursos **sin** IAM)
Adjuntar: `policy_relevamientos_base_readonly`

Cubre:
- EC2 (regions, instances, vpcs, subnets, igw, nat, sgs, tags, AZs)
- S3 (list buckets, location, bucket tags)
- RDS (describe instances)
- Lambda (list functions + tags)
- CloudFormation (describe stacks)

### B. Costos (Cost Explorer)
Solo si vas a ejecutar el script de descarga de costos:
Adjuntar: `policy_relevamientos_cost_explorer_readonly`

### C. IAM (opcional, sensible)
Solo si vas a ejecutar el reporte de recursos con `--include-iam`:
Adjuntar: `policy_relevamientos_iam_readonly_optional`

> Recomendación: mantener IAM como opt-in. El inventario IAM puede ser considerado información sensible.

---

## 2) Crear el Role para EC2 (Trust Policy)

El rol debe permitir que EC2 lo asuma. Usar el bloque:
`trust_policy_ec2_assume_role` dentro de `relevamientos_iam_policies.json`.

Nombre sugerido: `Role_Instancia_Relevamientos`

---

## 3) Asignar el rol a la instancia `Instancia_Relevameintos` (Consola)

1. Ir a **EC2 → Instances**
2. Buscar la instancia por **Name**: `Instancia_Relevameintos`
3. Seleccionar la instancia
4. Menú: **Actions → Security → Modify IAM role**
5. Seleccionar el rol (por ejemplo `Role_Instancia_Relevamientos`)
6. Guardar

---

## 4) Verificación en Cloud9

En la terminal del entorno Cloud9:

### 4.1 Ver identidad (debe responder sin error)
```bash
aws sts get-caller-identity
```

### 4.2 Ver regiones (prueba de permisos base EC2)
```bash
aws ec2 describe-regions --query "Regions[].RegionName" --output text
```

### 4.3 Probar consulta de VPCs en una región (ejemplo)
```bash
aws ec2 describe-vpcs --region us-east-1 --max-items 5
```

### 4.4 Probar Cost Explorer (solo si agregaste policy de costos)
> Este comando es ilustrativo; requiere parámetros completos.
```bash
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '7 days ago' +%F),End=$(date -u +%F) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=INSTANCE_TYPE \
  --filter '{
    "Dimensions": {
      "Key": "SERVICE",
      "Values": ["Amazon Elastic Compute Cloud - Compute"]
    }
  }'
```

---

## 5) Importante: Cloud9 “AWS managed temporary credentials”

En algunos entornos Cloud9 existe una opción de credenciales administradas por Cloud9.
Si querés que el rol de instancia sea la única fuente de credenciales, revisá:

- **Cloud9 → Preferences → AWS Settings**
  - Desactivar “AWS managed temporary credentials” (si está habilitado)

> Si no existe esa opción en tu cuenta, ignorar esta sección.

---

## 6) Automatización mensual (resumen)

Si el flujo actual es manual, lo recomendado es mantenerlo así y dejar automatización como “siguiente etapa”.

- **Cron** en la misma EC2: funciona si la instancia está encendida el día/hora programado.
- **Lambda + EventBridge**: alternativa a futuro para no depender de EC2 encendida (implica S3/Layers).

---

## Checklist rápido

- [ ] Rol creado con trust policy EC2
- [ ] Policy base adjunta al rol
- [ ] (Opcional) Policy de Cost Explorer adjunta
- [ ] (Opcional) Policy IAM adjunta solo si se usa `--include-iam`
- [ ] Rol asignado a la instancia `Instancia_Relevameintos`
- [ ] `aws sts get-caller-identity` funciona desde Cloud9
