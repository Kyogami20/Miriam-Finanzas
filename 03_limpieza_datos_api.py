# Nombres y Apellidos completos: [COMPLETAR]
# Codigo de matricula: [COMPLETAR]
# Tema y numero del temario: [COMPLETAR]
# Fecha de extraccion: [COMPLETAR]

"""
03_limpieza_datos_api.py
--------------------------
Version EXCLUSIVA para cuando la base de datos se construye solo con la via
API del BCRP (valido para Unidad I, donde la segunda via es opcional). No
incluye logica de fusion con una fuente de scraping.

Toma el archivo crudo generado por 01_extraccion_api.py (bytes, guardados
tal cual llegan del servidor, con "<br>" como separador de filas), lo
corrige de formato, lo tipifica, reconstruye el calendario completo (para
que los "n.d." de la fuente queden explicitos) y trata outliers, generando
datos_procesados_<codigo>.csv en /datos_procesados.

IMPORTANTE: si tu unidad exige tambien la via de scraping (obligatoria en
Unidad II), usa en su lugar 03_limpieza_datos.py, que si fusiona ambas
fuentes por una llave comun.
"""

import os
import html
import logging
from io import StringIO

import pandas as pd
import numpy as np

CODIGO_MATRICULA = "00000000"  # reemplazar por el codigo real

# Debe coincidir EXACTAMENTE con SERIES_CODES de 01_extraccion_api.py, en el
# mismo orden, para poder renombrar las columnas del CSV correctamente.
SERIES_CODES = [
    "PN06822NM",
]

RUTA_BASE = os.path.dirname(__file__)
# Misma ruta que usa 01_extraccion_api.py: "datos_crudos" queda DENTRO de
# /codigo. (Para cumplir al pie de la letra la estructura de la rubrica,
# numeral 2.5, lo ideal es que sea hermana de /codigo; ajustar aqui y en el
# extractor si se corrige mas adelante.)
RUTA_CRUDOS = os.path.join(RUTA_BASE, "datos_crudos")
RUTA_PROCESADOS = os.path.join(RUTA_BASE, "datos_procesados")
os.makedirs(RUTA_PROCESADOS, exist_ok=True)

RUTA_LOG = os.path.join(RUTA_BASE, "log_ejecucion.txt")
logging.basicConfig(
    filename=RUTA_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("limpieza_datos_api")


def corregir_formato_texto_bcrp(bytes_crudos):
    """
    El archivo crudo de BCRPData (guardado tal cual por 01_extraccion_api.py,
    en BYTES, sin decodificar: respuesta.content) trae peculiaridades de
    FORMATO que hay que corregir aqui, sin alterar los valores de los datos:

    1. Usa literalmente "<br>" como separador de filas, en vez de saltos de
       linea reales.
    2. Codifica algunos caracteres especiales como entidades HTML,
       ej. "&ntilde;" en vez de 'ñ' directamente.
    3. Posible doble codificacion ("mojibake": "Ã³" en vez de "ó"), por si el
       servidor respondiera con una codificacion distinta a UTF-8. Se
       revierte re-codificando como Latin-1 (para recuperar los bytes
       originales) y decodificando de nuevo como UTF-8. Si no hace falta,
       el intento simplemente no tiene efecto.

    Devuelve el texto ya normalizado, listo para pd.read_csv.
    """
    texto = bytes_crudos.decode("utf-8", errors="replace")
    texto = texto.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

    # IMPORTANTE: primero se intenta revertir el mojibake y RECIEN DESPUES
    # se desescapan las entidades HTML. Si se hiciera al reves, una 'ñ' ya
    # convertida (fuera del rango de bytes UTF-8 validos por si sola) rompe
    # la conversion latin-1 -> utf-8 para el resto del texto.
    try:
        texto = texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass  # el texto ya estaba bien codificado; no se toca

    texto = html.unescape(texto)  # convierte &ntilde; -> ñ, &oacute; -> ó, etc.
    return texto.strip() + "\n"


def cargar_csv_bcrp(ruta_csv, series_codes):
    """
    Carga el CSV crudo de BCRPData TAL COMO LO GUARDO 01_extraccion_api.py
    (bytes, con "<br>" sin corregir) y aplica aqui la correccion de formato
    antes de parsearlo con pandas.

    Formato real observado: separador COMA, con los valores entre comillas.
    La primera columna trae el periodo (ej. "Dic.2010") bajo el encabezado
    "Mes/Año"; las demas columnas traen como encabezado la DESCRIPCION
    COMPLETA de cada serie (no el codigo), por ejemplo:
    "Encaje, depositos overnight... - TOSE I - Interbank (miles S/)".

    Se renombra la primera columna a 'periodo' y las siguientes al codigo
    de serie correspondiente (en el mismo orden en que se pidieron en
    SERIES_CODES), para que el resto del pipeline trabaje con nombres
    cortos y estables. La descripcion completa se documenta aparte en
    diccionario_variables.md.
    """
    with open(ruta_csv, "rb") as f:
        bytes_crudos = f.read()

    texto_corregido = corregir_formato_texto_bcrp(bytes_crudos)
    df = pd.read_csv(StringIO(texto_corregido), sep=",")

    nuevas_columnas = ["periodo"] + list(series_codes[: len(df.columns) - 1])
    if len(nuevas_columnas) != len(df.columns):
        raise ValueError(
            f"El CSV tiene {len(df.columns)} columnas pero se declararon "
            f"{len(series_codes)} codigos de serie. Revisa SERIES_CODES."
        )
    df.columns = nuevas_columnas
    return df


def normalizar_periodo_mensual(texto_periodo):
    """
    Convierte periodos tipo 'Ene.2020' (formato tipico de BCRP en espanol)
    a un Timestamp de pandas.
    AJUSTAR si tu serie es trimestral, anual o diaria.
    """
    meses = {
        "Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Ago": "08",
        "Set": "09", "Sep": "09", "Oct": "10", "Nov": "11", "Dic": "12",
    }
    try:
        mes_abrev, anio = texto_periodo.split(".")
        return pd.Timestamp(year=int(anio), month=int(meses[mes_abrev]), day=1)
    except Exception:
        return pd.NaT


def reindexar_calendario_completo(df, columna_fecha, frecuencia="MS"):
    """
    Reconstruye el calendario completo (mes a mes, por defecto) entre la
    primera y la ultima fecha del DataFrame. Los periodos que el BCRP omitio
    por ser "n.d." en la fuente original quedan aqui como filas con NaN,
    en vez de simplemente desaparecer del archivo.

    frecuencia: 'MS' = inicio de mes (para series mensuales). Cambiar a 'QS'
    (trimestral), 'AS' (anual) o 'D' (diaria) segun la frecuencia real de tu serie.
    """
    rango_completo = pd.date_range(
        start=df[columna_fecha].min(), end=df[columna_fecha].max(), freq=frecuencia
    )
    df_completo = (
        df.set_index(columna_fecha)
        .reindex(rango_completo)
        .rename_axis(columna_fecha)
        .reset_index()
    )
    n_faltantes = df_completo.drop(columns=[columna_fecha]).isna().any(axis=1).sum()
    logger.info(
        f"Calendario reconstruido: {len(rango_completo)} periodos esperados, "
        f"{n_faltantes} periodos con al menos un valor faltante (n.d. en la fuente)."
    )
    return df_completo


def limpiar_api(df_api):
    """
    Tipifica valores numericos, trata 'n.d.' como faltante, normaliza el
    periodo y reconstruye el calendario completo (los meses 'n.d.' que el
    BCRP omite del CSV se recuperan explicitamente como filas con NaN).
    """
    df = df_api.copy()
    df["fecha"] = df["periodo"].apply(normalizar_periodo_mensual)

    columnas_valor = [c for c in df.columns if c not in ("periodo", "fecha")]
    for col in columnas_valor:
        df[col] = pd.to_numeric(
            df[col].replace({"n.d.": np.nan, "": np.nan}), errors="coerce"
        )

    df = df.drop(columns=["periodo"]).dropna(subset=["fecha"])
    df = reindexar_calendario_completo(df, "fecha", frecuencia="MS")

    # Marca explicita de que fila era "n.d." en la fuente original (antes de
    # cualquier imputacion). Sirve para reportarlo en el articulo y para que
    # el docente distinga "faltante real de la fuente" de "error de extraccion".
    for col in columnas_valor:
        df[f"{col}_faltante"] = df[col].isna()

    return df


def tratar_outliers_iqr(df, columnas):
    """Marca (no elimina) outliers por rango intercuartilico, para revision manual."""
    df = df.copy()
    for col in columnas:
        q1, q3 = df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        limite_inf, limite_sup = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        df[f"{col}_outlier"] = ~df[col].between(limite_inf, limite_sup)
    return df


if __name__ == "__main__":
    logger.info("=== INICIO limpieza de datos (solo API) ===")

    ruta_csv_api = os.path.join(RUTA_CRUDOS, f"datos_crudos_{CODIGO_MATRICULA}.csv")

    df_api_crudo = cargar_csv_bcrp(ruta_csv_api, SERIES_CODES)
    df_final = limpiar_api(df_api_crudo)
    logger.info(f"Datos API limpios: {df_final.shape[0]} filas, {df_final.shape[1]} columnas")

    columnas_numericas = [c for c in df_final.select_dtypes(include=[np.number]).columns
                          if not c.endswith("_faltante")]
    df_final = tratar_outliers_iqr(df_final, columnas_numericas)

    ruta_salida = os.path.join(RUTA_PROCESADOS, f"datos_procesados_{CODIGO_MATRICULA}.csv")
    df_final.to_csv(ruta_salida, index=False, encoding="utf-8")

    logger.info(f"Datos procesados guardados en: {ruta_salida} ({df_final.shape[0]} filas, {df_final.shape[1]} columnas)")
    print(f"Limpieza completada: {df_final.shape[0]} filas, {df_final.shape[1]} columnas -> {ruta_salida}")
    logger.info("=== FIN limpieza de datos (solo API) ===")