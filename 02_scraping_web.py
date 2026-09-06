# Nombres y Apellidos: <COMPLETAR>
# Codigo de matricula: <COMPLETAR>
# Tema y numero del temario: <COMPLETAR - Tema N.o __>
# Fecha de extraccion: 2026-09-05

"""
02_scraping_web.py

Descarga programatica (scraping) de la serie mensual PN06822NM del BCRP
("Obligaciones sujetas a encaje - TOSE I - Interbank", miles de S/),
publicada como tabla HTML en el portal BCRPData:
https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/resultados/PN06822NM/html

Este script NO usa la API JSON del BCRP (eso corresponde a
01_extraccion_api.py). Aqui se rastrea directamente la pagina HTML de
resultados, tal como la sirve el portal, respetando:
  - pausa minima de 1 segundo entre solicitudes,
  - User-Agent identificable,
  - parametros de consulta congelados (FECHA_INICIO / FECHA_CORTE),
  - guardado del archivo crudo intacto, sin edicion manual.
"""

import os
import re
import time
import logging
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

# ------------------------------------------------------------------
# Parametros congelados de la consulta (NO usar fechas dinamicas "hoy")
# ------------------------------------------------------------------
CODIGO_SERIE = "PN06822NM"
FECHA_INICIO = "2010-12"        # aaaa-mm : primer periodo requerido
FECHA_CORTE = "2026-08"         # aaaa-mm : ultimo periodo requerido
CODIGO_MATRICULA = "COMPLETAR"  # codigo de matricula del estudiante

BASE_URL = (
    f"https://estadisticas.bcrp.gob.pe/estadisticas/series/mensuales/"
    f"resultados/{CODIGO_SERIE}/html"
)

HEADERS = {
    "User-Agent": (
        "FinanzasI-UNCP-EstudianteBot/1.0 "
        "(+uso academico; contacto: <correo_institucional>@uncp.edu.pe)"
    )
}

PAUSA_SEGUNDOS = 1.5  # pausa minima entre solicitudes exigida por la consigna

RUTA_CRUDOS = os.path.join("datos_crudos", f"datos_crudos_{CODIGO_MATRICULA}.csv")
RUTA_LOG = "log_ejecucion.txt"

logging.basicConfig(
    filename=RUTA_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def construir_url(fecha_inicio: str, fecha_corte: str) -> str:
    """
    Construye la URL de la tabla de resultados del BCRP para el rango
    congelado FECHA_INICIO / FECHA_CORTE, en el formato que acepta el
    portal: .../html/<anio-mes_inicio>/<anio-mes_fin>.
    Si el rango no se puede interpretar, cae de vuelta a la tabla completa.
    """
    try:
        ini = datetime.strptime(fecha_inicio, "%Y-%m")
        fin = datetime.strptime(fecha_corte, "%Y-%m")
        return f"{BASE_URL}/{ini.year}-{ini.month}/{fin.year}-{fin.month}"
    except ValueError:
        logging.warning("Rango de fechas invalido; se usa la tabla completa.")
        return BASE_URL


def descargar_html(url: str) -> str:
    respuesta = requests.get(url, headers=HEADERS, timeout=30)
    logging.info("GET %s -> HTTP %s", url, respuesta.status_code)
    respuesta.raise_for_status()
    time.sleep(PAUSA_SEGUNDOS)
    return respuesta.text


PATRON_PERIODO = re.compile(
    r"^(Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)\d{2}$"
)


def _extraer_por_clases_css(soup: BeautifulSoup) -> Optional[pd.DataFrame]:
    """
    Vía principal: el portal BCRPData marca la tabla de resultados con
    class="series" y cada fila con <td class="periodo"><b>Dic10</b></td>
    y <td class="dato">6141575</td>. Se apunta directamente a esas clases,
    que es mas confiable que adivinar por posicion.
    """
    tabla = soup.find("table", class_="series")
    if tabla is None:
        return None

    filas = tabla.find_all("tr")
    if not filas:
        return None

    encabezado = [c.get_text(strip=True) for c in filas[0].find_all(["th", "td"])]
    if len(encabezado) != 2:
        encabezado = ["Fecha", "Valor"]

    registros = []
    for fila in filas:
        celda_periodo = fila.find("td", class_="periodo")
        celda_dato = fila.find("td", class_="dato")
        if celda_periodo is not None and celda_dato is not None:
            registros.append([
                celda_periodo.get_text(strip=True),
                celda_dato.get_text(strip=True),
            ])

    if not registros:
        return None

    return pd.DataFrame(registros, columns=encabezado)


def _extraer_por_heuristica(soup: BeautifulSoup) -> pd.DataFrame:
    """
    Vía de respaldo (por si el portal cambia el marcado y ya no usa
    class="series"/"periodo"/"dato"): recorre todas las <table> y elige
    la que tiene 2 columnas y cuyas filas calzan con el patron de periodo
    mensual (ej. 'Dic10', 'Ene26'), descartando asi tablas decorativas
    como el selector "Desde/Hasta".
    """
    tablas = soup.find_all("table")
    if not tablas:
        raise ValueError("No se encontro ninguna tabla en el HTML.")

    formas_encontradas = []
    for tabla in tablas:
        filas = tabla.find_all("tr")
        if len(filas) < 2:
            continue

        encabezado = [c.get_text(strip=True) for c in filas[0].find_all(["th", "td"])]
        registros = []
        coincidencias = 0
        for fila in filas[1:]:
            celdas = [c.get_text(strip=True) for c in fila.find_all(["td", "th"])]
            if len(celdas) == len(encabezado) == 2 and celdas[0]:
                registros.append(celdas)
                if PATRON_PERIODO.match(celdas[0]):
                    coincidencias += 1

        formas_encontradas.append((len(filas), len(encabezado)))

        if registros and coincidencias >= max(1, len(registros) // 2):
            return pd.DataFrame(registros, columns=encabezado)

    raise ValueError(
        "No se encontro la tabla de resultados Fecha/Valor esperada. "
        f"Tablas revisadas: {formas_encontradas}"
    )


def parsear_tabla(html: str) -> pd.DataFrame:
    """Extrae la tabla de resultados (Fecha | Valor) del HTML del portal."""
    soup = BeautifulSoup(html, "html.parser")

    df = _extraer_por_clases_css(soup)
    if df is None:
        logging.warning(
            "No se encontro table.series; se usa la heuristica de respaldo."
        )
        df = _extraer_por_heuristica(soup)

    logging.info(
        "Tabla de resultados identificada: %d filas, columnas %s",
        len(df), list(df.columns),
    )
    return df


def main():
    os.makedirs("datos_crudos", exist_ok=True)
    url = construir_url(FECHA_INICIO, FECHA_CORTE)

    try:
        html = descargar_html(url)
    except requests.exceptions.RequestException as exc:
        logging.error("Fallo la solicitud a %s: %s", url, exc)
        html = descargar_html(BASE_URL)  # respaldo: tabla completa sin rango

    df_crudo = parsear_tabla(html)

    # Se guarda EXACTAMENTE como sale de la fuente, sin editar ni limpiar
    df_crudo.to_csv(RUTA_CRUDOS, index=False, encoding="utf-8-sig")
    logging.info("Archivo crudo guardado en %s con %d filas.", RUTA_CRUDOS, len(df_crudo))
    print(f"Extraccion completada: {len(df_crudo)} filas guardadas en {RUTA_CRUDOS}")


if __name__ == "__main__":
    main()