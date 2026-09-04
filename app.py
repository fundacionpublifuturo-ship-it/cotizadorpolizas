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
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, send_from_directory, Response

from cotizador_multi import DatosCliente, cotizar_todas, CARPETA_PDFS

app = Flask(__name__)

# Guarda el último set de resultados en memoria para la página de resultados.
# Para producción real (varios asesores usando la app a la vez) esto debería
# guardarse en una base de datos con un ID de sesión/cotización, no en memoria.
ULTIMO_RESULTADO = {"cliente": None, "resultados": []}

# ------------------------------------------------------------------
# ACCESO PRIVADO AL COTIZADOR
# ------------------------------------------------------------------
# El cotizador es una herramienta interna (solo para el admin/asesor),
# NO para visitantes del sitio público. Se protege con usuario/clave
# simples (HTTP Basic Auth). Defínelos como variables de entorno:
#   ADMIN_USER=el usuario que quieras
#   ADMIN_PASS=una clave segura
# Si no las defines, usa un valor por defecto SOLO para pruebas locales
# (cámbialo antes de publicar en Render).
ADMIN_USER = os.getenv("ADMIN_USER", "mateo")
ADMIN_PASS = os.getenv("ADMIN_PASS", "cambiar-esta-clave")


def requiere_login(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USER or auth.password != ADMIN_PASS:
            return Response(
                "Acceso restringido — herramienta interna.", 401,
                {"WWW-Authenticate": 'Basic realm="Cotizador Interno"'}
            )
        return vista(*args, **kwargs)
    return envoltura


@app.route("/", methods=["GET"])
def home():
    return render_template("home.html")


@app.route("/cotizar-ahora", methods=["GET"])
@requiere_login
def cotizador_page():
    return render_template("cotizador.html")


@app.route("/cotizar", methods=["POST"])
@requiere_login
def cotizar():
    form = request.form

    try:
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

    except Exception as e:
        # Nunca mostrar el error genérico de Render/Flask: siempre devolver
        # una respuesta clara indicando qué aseguradora o paso falló.
        return render_template(
            "resultados.html",
            cliente=None,
            resultados=[{
                "aseguradora": "Sistema", "plan": "—", "estado": "error",
                "prima": None, "pdf_path": None,
                "detalle": f"No se pudo completar la cotización: {e}",
            }],
        ), 200


@app.route("/pdf/<nombre_archivo>")
@requiere_login
def descargar_pdf(nombre_archivo):
    return send_from_directory(CARPETA_PDFS, nombre_archivo, as_attachment=True)


if __name__ == "__main__":
    # Render (y la mayoría de hostings) inyectan el puerto por variable de entorno.
    puerto = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=puerto)
