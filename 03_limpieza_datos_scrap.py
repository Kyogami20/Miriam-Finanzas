# Nombres y Apellidos: <COMPLETAR>
# Codigo de matricula: <COMPLETAR>
# Tema y numero del temario: <COMPLETAR - Tema N.o __>
# Fecha de extraccion: 2026-09-05

"""
03_limpieza_datos.py

Depura y tipifica UNICAMENTE los datos generados por 02_scraping_web.py
(serie PN06822NM del BCRP, obtenida por scraping de la tabla HTML del
portal BCRPData). No integra otras fuentes: genera
datos_procesados_<codigo>.csv a partir de la unica fuente de scraping.

Pasos: tipificacion de fecha y valor, tratamiento de "n.d." como faltante,
eliminacion de duplicados, orden cronologico y calculo del hash SHA-256
del archivo final (para el README).
"""

import os
import hashlib
import pandas as pd

CODIGO_MATRICULA = "COMPLETAR"

RUTA_CRUDOS = os.path.join("datos_crudos", f"datos_crudos_{CODIGO_MATRICULA}.csv")
RUTA_PROCESADOS = os.path.join("datos_procesados", f"datos_procesados_{CODIGO_MATRICULA}.csv")

MESES = {
    "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12,
}


def parsear_periodo(etiqueta: str) -> pd.Timestamp:
    """Convierte etiquetas tipo 'Dic10' o 'Ene26' en fecha de fin de mes."""
    mes_txt, anio_txt = etiqueta[:3], etiqueta[3:]
    mes = MESES[mes_txt]
    anio_int = int(anio_txt)
    anio = 2000 + anio_int if anio_int < 70 else 1900 + anio_int
    return pd.Timestamp(year=anio, month=mes, day=1) + pd.offsets.MonthEnd(0)


def limpiar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = ["periodo_raw", "valor_raw"]

    df["fecha"] = df["periodo_raw"].apply(parsear_periodo)

    # Se quitan las comas de miles; cualquier marcador no numerico
    # ("n.d.", "N.D.", vacio, etc.) queda como NaN gracias a errors="coerce",
    # sin necesidad de mapearlo antes uno por uno.
    valor_sin_comas = df["valor_raw"].astype(str).str.replace(",", "", regex=False)
    df["valor_tose_i_interbank_miles_sn"] = pd.to_numeric(valor_sin_comas, errors="coerce")
    df["dato_faltante"] = df["valor_tose_i_interbank_miles_sn"].isna()

    faltantes = int(df["dato_faltante"].sum())

    df["codigo_serie"] = "PN06822NM"
    df["fuente"] = "BCRP - BCRPData (scraping HTML)"
    df["codigo_matricula"] = CODIGO_MATRICULA

    df = df.drop_duplicates(subset="fecha").sort_values("fecha").reset_index(drop=True)

    columnas_finales = [
        "codigo_matricula", "fecha", "periodo_raw", "codigo_serie",
        "valor_tose_i_interbank_miles_sn", "dato_faltante", "fuente",
    ]
    df = df[columnas_finales]

    print(f"Valores faltantes ('n.d.') detectados y marcados: {faltantes}")
    return df


def calcular_hash(ruta_archivo: str) -> str:
    hasher = hashlib.sha256()
    with open(ruta_archivo, "rb") as f:
        hasher.update(f.read())
    return hasher.hexdigest()


def main():
    os.makedirs("datos_procesados", exist_ok=True)
    df_crudo = pd.read_csv(RUTA_CRUDOS, dtype=str, encoding="utf-8-sig")
    df_limpio = limpiar(df_crudo)
    df_limpio.to_csv(RUTA_PROCESADOS, index=False, encoding="utf-8-sig")

    hash_sha256 = calcular_hash(RUTA_PROCESADOS)
    print(f"Archivo procesado guardado en {RUTA_PROCESADOS}")
    print(f"Filas finales: {len(df_limpio)}")
    print(f"SHA-256: {hash_sha256}")
    print("Copie este hash en README.md, seccion de verificacion de integridad.")


if __name__ == "__main__":
    main()