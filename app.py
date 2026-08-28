"""
APP WEB — Cotizador Multi-Aseguradora
=======================================
Interfaz simple para que un asesor de Mateo Herrera Seguros ingrese los
datos del cliente UNA VEZ y obtenga las cotizaciones (con PDF) de todas
las aseguradoras conectadas, en una sola pantalla.

INSTALAR:
    pip install flask playwright pandas openpyxl python-dotenv --break-system-packages
    playwright install chromium

CORRER:
    python app.py
    Abrir en el navegador: http://localhost:5000
"""

import asyncio
import os
from pathlib import Path

from flask import Flask, render_template, request, send_from_directory

from cotizador_multi import DatosCliente, cotizar_todas, CARPETA_PDFS

app = Flask(__name__)

# Guarda el último set de resultados en memoria para la página de resultados.
# Para producción real (varios asesores usando la app a la vez) esto debería
# guardarse en una base de datos con un ID de sesión/cotización, no en memoria.
ULTIMO_RESULTADO = {"cliente": None, "resultados": []}


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/cotizar", methods=["POST"])
def cotizar():
    form = request.form

    cliente = DatosCliente(
        nombre_completo=form["nombre_completo"],
        tipo_documento=form["tipo_documento"],
        numero_documento=form["numero_documento"],
        fecha_nacimiento=form["fecha_nacimiento"],
        genero=form["genero"],
        ciudad=form["ciudad"],
        telefono=form["telefono"],
        correo=form["correo"],
        tipo_seguro=form["tipo_seguro"],
        valor_asegurado=float(form["valor_asegurado"]) if form.get("valor_asegurado") else None,
        placa_vehiculo=form.get("placa_vehiculo", ""),
    )

    # Ejecuta las cotizaciones en paralelo (headless=True para no abrir ventanas)
    resultados = asyncio.run(cotizar_todas(cliente, headless=True))

    ULTIMO_RESULTADO["cliente"] = cliente
    ULTIMO_RESULTADO["resultados"] = resultados

    return render_template("resultados.html", cliente=cliente, resultados=resultados)


@app.route("/pdf/<nombre_archivo>")
def descargar_pdf(nombre_archivo):
    return send_from_directory(CARPETA_PDFS, nombre_archivo, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
