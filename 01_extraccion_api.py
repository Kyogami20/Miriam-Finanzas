# Nombres y Apellidos completos: [COMPLETAR: Ej. Ana Torres Quispe]
# Codigo de matricula: [COMPLETAR: Ej. 2021123456]
# Tema y numero del temario: [COMPLETAR: Ej. Tema 12 - Tipo de cambio e inversion]
# Fecha de extraccion: [COMPLETAR: Ej. 2026-09-05]

"""
01_extraccion_api.py
---------------------
Extrae series estadisticas desde la API publica de BCRPData (Banco Central
de Reserva del Peru) y guarda el resultado TAL COMO SALE de la fuente en
/datos_crudos, en formato CSV, sin editar.

Documentacion oficial de la API:
https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/api

Estructura del endpoint (metodo GET):
https://estadisticas.bcrp.gob.pe/estadisticas/series/api/[codigos_series]/[formato]/[fecha_inicio]/[fecha_fin]/[idioma]

- [codigos_series]: 1 a 10 codigos de series de la MISMA frecuencia, separados por guion.
- [formato]: json, xml, csv, html, entre otros. Aqui se pide "csv" directamente
  al servidor, para guardar la respuesta tal como la entrega la fuente
  (evidencia primaria) y no tener que convertirla despues.
- [fecha_inicio] / [fecha_fin]: formato depende de la frecuencia (ej. "2015-1" para
  mensual, "2015" para anual). Si se omiten, trae el periodo mas reciente.
- [idioma]: "esp" o "ing".

IMPORTANTE (numeral 2.4.5 de la rubrica): el periodo de consulta se declara
como CONSTANTE (FECHA_INICIO / FECHA_CORTE), nunca como fecha dinamica tipo
"hoy", para que la extraccion sea reproducible y verificable por el docente.
"""

import os
import time
import logging
from datetime import datetime

import requests
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# 1. CONFIGURACION Y PARAMETROS CONGELADOS (declarar aqui, no calcular en runtime)
# --------------------------------------------------------------------------

load_dotenv()  # carga variables desde .env (si la fuente lo requiere; BCRPData es de acceso libre y NO requiere clave)

# Ejemplo: codigos de series del BCRP. Cambiar por el/los indicador(es) de TU
# tema del temario. Puedes buscar el codigo exacto de tu serie en:
# https://estadisticas.bcrp.gob.pe/estadisticas/series/
SERIES_CODES = [
    "PN06822NM",  # Obligaciones sujetas a encaje - TOSE I - Interbank (miles S/)
]

FORMATO = "csv"
FECHA_INICIO = "2010-12"  # <-- CONSTANTE: primer periodo disponible de la serie (Dic-2010)
FECHA_CORTE = "2026-8"    # <-- CONSTANTE: ultimo periodo disponible de la serie (Ago-2026)
IDIOMA = "esp"

CODIGO_MATRICULA = os.getenv("CODIGO_MATRICULA", "00000000")  # se puede fijar tambien como constante directa

BASE_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"

RUTA_CRUDOS = os.path.join(os.path.dirname(__file__), "datos_crudos")
os.makedirs(RUTA_CRUDOS, exist_ok=True)

# --------------------------------------------------------------------------
# 2. LOGGING (queda registrado en log_ejecucion.txt, en la raiz del proyecto)
# --------------------------------------------------------------------------

RUTA_LOG = os.path.join(os.path.dirname(__file__), "log_ejecucion.txt")
logging.basicConfig(
    filename=RUTA_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("extraccion_api_bcrp")


def construir_url(series_codes, formato, fecha_inicio, fecha_fin, idioma):
    """Arma la URL de consulta segun la estructura oficial de BCRPData."""
    codigos = "-".join(series_codes)
    return f"{BASE_URL}/{codigos}/{formato}/{fecha_inicio}/{fecha_fin}/{idioma}"


def extraer_serie_bcrp_csv(series_codes, fecha_inicio, fecha_fin, idioma="esp",
                            max_reintentos=3, espera_seg=2):
    
    url = construir_url(series_codes, "csv", fecha_inicio, fecha_fin, idioma)
    logger.info(f"Solicitando: {url}")

    intento = 0
    while intento < max_reintentos:
        intento += 1
        try:
            respuesta = requests.get(url, timeout=30)
            logger.info(f"Intento {intento} | Codigo HTTP: {respuesta.status_code}")

            if respuesta.status_code == 200:
                return respuesta.content  # bytes crudos, sin decodificar
            else:
                logger.warning(
                    f"Respuesta no exitosa (HTTP {respuesta.status_code}). "
                    f"Reintentando en {espera_seg}s..."
                )
                time.sleep(espera_seg)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error de conexion en intento {intento}: {e}")
            time.sleep(espera_seg)

    logger.error("Se agotaron los reintentos. No se pudo extraer la serie.")
    raise ConnectionError(
        "No fue posible conectarse a la API del BCRP tras varios intentos. "
        "Si el problema persiste, documentar en incidencias_fuente.md."
    )


def guardar_csv_crudo(bytes_csv, codigo_matricula):
    nombre_archivo = f"datos_crudos_{codigo_matricula}.csv"
    ruta = os.path.join(RUTA_CRUDOS, nombre_archivo)
    with open(ruta, "wb") as f:
        f.write(bytes_csv)
    logger.info(f"Archivo crudo guardado en: {ruta}")
    return ruta


def contar_filas(bytes_csv):
    return bytes_csv.count(b"<br>")  # cada "<br>" separa una fila de datos de la siguiente


if __name__ == "__main__":
    logger.info("=== INICIO extraccion API BCRP ===")
    csv_crudo = extraer_serie_bcrp_csv(SERIES_CODES, FECHA_INICIO, FECHA_CORTE, IDIOMA)

    n_filas = contar_filas(csv_crudo)
    logger.info(f"Filas/periodos descargados (aprox.): {n_filas}")

    ruta_guardada = guardar_csv_crudo(csv_crudo, CODIGO_MATRICULA)

    print(f"Extraccion completada. ~{n_filas} filas guardadas en: {ruta_guardada}")
    logger.info("=== FIN extraccion API BCRP ===")