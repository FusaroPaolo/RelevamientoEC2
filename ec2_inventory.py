import boto3
from datetime import datetime
import csv
import openpyxl

def obtener_info_instancias():
    """
    Retorna una lista de diccionarios con información de
    las instancias EC2:
        - Nombre (tag 'Name')
        - Estado (State)
        - IP privada
        - IP pública
        - VPC (VpcId)
        - Nombre de la VPC (tag 'Name' de la VPC)
        - Región
        - Fecha y hora de consulta (UTC)
    """
    fecha_consulta = datetime.utcnow().isoformat()  # Timestamp de la consulta (UTC)

    ec2_client = boto3.client('ec2')
    regiones = [reg['RegionName'] for reg in ec2_client.describe_regions()['Regions']]
    
    info_instancias = []
    
    # Recorremos cada región
    for region in regiones:
        ec2_regional = boto3.client('ec2', region_name=region)
        
        # 1. Obtenemos el "mapa" VPC -> NombreVPC para esta región
        vpc_name_map = obtener_nombres_vpc(ec2_regional)
        
        # 2. Obtenemos información de todas las instancias de la región
        response = ec2_regional.describe_instances()
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                # Nombre de la instancia (tag Name)
                nombre_instancia = None
                if 'Tags' in instance:
                    for tag in instance['Tags']:
                        if tag['Key'] == 'Name':
                            nombre_instancia = tag['Value']
                            break
                
                # Estado de la instancia (ej. 'running', 'stopped', etc.)
                estado = instance.get('State', {}).get('Name', 'Desconocido')
                
                # IPs y VPC
                ip_privada = instance.get('PrivateIpAddress', 'No tiene')
                ip_publica = instance.get('PublicIpAddress', 'No tiene')
                vpc_id = instance.get('VpcId', 'Desconocido')
                
                # Nombre de la VPC (si existe)
                vpc_nombre = vpc_name_map.get(vpc_id, "Sin Nombre")
                
                # Agregamos la información a la lista
                info_instancias.append({
                    'Nombre': nombre_instancia if nombre_instancia else 'Sin Tag Name',
                    'Estado': estado,
                    'IP Privada': ip_privada,
                    'IP Pública': ip_publica,
                    'VPC ID': vpc_id,
                    'VPC Nombre': vpc_nombre,
                    'Región': region,
                    'Fecha y hora consulta (UTC)': fecha_consulta
                })
    
    return info_instancias

def obtener_nombres_vpc(ec2_regional):
    """
    Retorna un diccionario con las VPCs de la región
    mapeadas a su nombre (tag Name).
    Ejemplo: { 'vpc-0123456789abcdef0': 'VPC-Produccion', ... }
    """
    vpc_name_map = {}
    respuesta_vpc = ec2_regional.describe_vpcs()
    
    for vpc in respuesta_vpc.get('Vpcs', []):
        vpc_id = vpc['VpcId']
        vpc_name = None
        # Buscar tag Name en la VPC
        if 'Tags' in vpc:
            for tag in vpc['Tags']:
                if tag['Key'] == 'Name':
                    vpc_name = tag['Value']
                    break
        vpc_name_map[vpc_id] = vpc_name if vpc_name else 'Sin Nombre'
    
    return vpc_name_map

def exportar_a_csv(instancias, nombre_archivo='reporte_instancias.csv'):
    """
    Crea un archivo CSV con los datos de las instancias.
    """
    # Definimos las columnas y el orden deseado
    columnas = [
        'Nombre',
        'Estado',
        'IP Privada',
        'IP Pública',
        'VPC ID',
        'VPC Nombre',
        'Región',
        'Fecha y hora consulta (UTC)'
    ]
    
    with open(nombre_archivo, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columnas)
        writer.writeheader()
        for inst in instancias:
            writer.writerow(inst)
    
    print(f"Archivo CSV generado: {nombre_archivo}")

def exportar_a_excel(instancias, nombre_archivo='reporte_instancias.xlsx'):
    """
    Crea un archivo Excel (.xlsx) con los datos de las instancias.
    """
    # Creamos un libro y seleccionamos la hoja activa
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Instancias EC2"
    
    # Definimos las columnas (mismo orden que en CSV)
    columnas = [
        'Nombre',
        'Estado',
        'IP Privada',
        'IP Pública',
        'VPC ID',
        'VPC Nombre',
        'Región',
        'Fecha y hora consulta (UTC)'
    ]
    
    # Escribimos la fila de encabezados
    ws.append(columnas)
    
    # Escribimos una fila por cada instancia
    for inst in instancias:
        row = [inst[col] for col in columnas]
        ws.append(row)
    
    # Guardamos el archivo
    wb.save(nombre_archivo)
    print(f"Archivo Excel generado: {nombre_archivo}")

def main():
    instancias = obtener_info_instancias()
    
    # Mostrar la información en consola (opcional)
    for idx, inst in enumerate(instancias, start=1):
        print(f"\nInstancia {idx}:")
        print(f"  Nombre: {inst['Nombre']}")
        print(f"  Estado: {inst['Estado']}")
        print(f"  IP Privada: {inst['IP Privada']}")
        print(f"  IP Pública: {inst['IP Pública']}")
        print(f"  VPC ID: {inst['VPC ID']}")
        print(f"  VPC Nombre: {inst['VPC Nombre']}")
        print(f"  Región: {inst['Región']}")
        print(f"  Fecha y hora consulta: {inst['Fecha y hora consulta (UTC)']}")
    
    # Exportar a CSV
    exportar_a_csv(instancias, nombre_archivo='reporte_instancias.csv')
    
    # Exportar a Excel
    exportar_a_excel(instancias, nombre_archivo='reporte_instancias.xlsx')

if __name__ == '__main__':
    main()ec2_inventory.py
