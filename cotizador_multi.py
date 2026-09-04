"""
COTIZADOR MULTI-ASEGURADORA — Mateo Herrera Seguros
=====================================================
Automatiza el ingreso de datos de un cliente en los portales de agentes
de aseguradoras que NO ofrecen conexión Web Service (API) y consolida
las cotizaciones resultantes (con PDF) en un solo archivo Excel.

ASEGURADORAS CUBIERTAS AQUÍ (solo portal manual, vía RPA):
    Sura, Seguros del Estado, Equidad Seguros, AXA Colpatria, Solidaria

Las que SÍ tienen Web Service oficial (Bolívar, SBS, Allianz, HDI, Mapfre,
Seguros Mundial, Quality, Previsora) se conectan aparte, vía API, una vez
llegue la aprobación de cada aseguradora — no requieren este RPA.

REQUISITOS PREVIOS:
    pip install playwright pandas openpyxl python-dotenv --break-system-packages
    playwright install chromium

IMPORTANTE — LEE ESTO:
    - Las funciones de abajo son PLANTILLAS. Reemplaza los selectores
      (page.fill, page.click) con los reales de cada portal — se obtienen
      con clic derecho > Inspeccionar, o mejor: `playwright codegen <url>`.
    - Credenciales SIEMPRE en el archivo .env, nunca en este script.
    - Si un portal usa 2FA, usa sesión persistente (storage_state) en vez
      de loguear con usuario/clave en cada corrida.
    - Revisa Términos de Uso de cada portal antes de automatizar el login.
    - Cuando la aseguradora cambie su portal, el selector correspondiente
      se rompe y hay que actualizarlo — mantenimiento recurrente.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

CARPETA_PDFS = Path("pdfs_cotizaciones")
CARPETA_PDFS.mkdir(exist_ok=True)

# Límite de navegadores Playwright corriendo AL MISMO TIEMPO.
# En el plan gratuito de Render (512MB RAM) 2 es un valor seguro.
# Si despliegas en un servidor con más RAM, puedes subir este número
# (ej: 6, para cotizar las 6 aseguradoras en paralelo real) vía variable
# de entorno MAX_COTIZACIONES_PARALELAS en el .env.
MAX_PARALELO = int(os.getenv("MAX_COTIZACIONES_PARALELAS", "2"))
_SEMAFORO = asyncio.Semaphore(MAX_PARALELO)


# ----------------------------------------------------------------------
# 1. DATOS DEL CLIENTE
# ----------------------------------------------------------------------
@dataclass
class DatosCliente:
    nombre_completo: str
    tipo_documento: str
    numero_documento: str
    fecha_nacimiento: str    # DD/MM/AAAA
    genero: str              # "M" o "F"
    ciudad: str
    telefono: str
    correo: str
    tipo_seguro: str         # "vida", "auto", "hogar", "salud"
    valor_asegurado: float | None = None  # opcional — si no se da, la aseguradora lo pide en su propio flujo
    placa_vehiculo: str = "" # si aplica (seguro de auto) — la aseguradora
                             # resuelve marca/modelo/año internamente vía RUNT,
                             # no hace falta pedírselo al cliente ni consultarlo tú mismo

    def edad(self) -> int:
        dia, mes, anio = map(int, self.fecha_nacimiento.split("/"))
        hoy = datetime.now()
        return hoy.year - anio - ((hoy.month, hoy.day) < (mes, dia))


# ----------------------------------------------------------------------
# 2. CATÁLOGO DE PLANES POR ASEGURADORA (ajustar con planes/reglas reales)
# ----------------------------------------------------------------------
PLANES_SURA = [
    {"nombre": "Plan Vida Mujer", "selector_valor": "vida_mujer",
     "elegible": lambda c: c.genero == "F" and c.tipo_seguro == "vida"},
    {"nombre": "Plan Vida Clásico", "selector_valor": "vida_clasico",
     "elegible": lambda c: c.tipo_seguro == "vida"},
    {"nombre": "Plan Auto Full", "selector_valor": "auto_full",
     "elegible": lambda c: c.tipo_seguro == "auto"},
]

PLANES_SEGUROS_DEL_ESTADO = [
    {"nombre": "Plan Vida Estatal", "selector_valor": "vida_estado",
     "elegible": lambda c: c.tipo_seguro == "vida"},
]

PLANES_EQUIDAD = [
    {"nombre": "Plan Vida Equidad", "selector_valor": "vida_equidad",
     "elegible": lambda c: c.tipo_seguro == "vida"},
    {"nombre": "Plan Auto Equidad", "selector_valor": "auto_equidad",
     "elegible": lambda c: c.tipo_seguro == "auto"},
]

PLANES_AXA_COLPATRIA = [
    {"nombre": "Plan Vida AXA", "selector_valor": "vida_axa",
     "elegible": lambda c: c.tipo_seguro == "vida"},
    {"nombre": "Plan Vida Mujer AXA", "selector_valor": "vida_mujer_axa",
     "elegible": lambda c: c.genero == "F" and c.tipo_seguro == "vida"},
]

PLANES_SOLIDARIA = [
    {"nombre": "Plan Vida Solidaria", "selector_valor": "vida_solidaria",
     "elegible": lambda c: c.tipo_seguro == "vida"},
]


def planes_elegibles(catalogo: list[dict], cliente: DatosCliente) -> list[dict]:
    return [plan for plan in catalogo if plan["elegible"](cliente)]


# ----------------------------------------------------------------------
# 3. FUNCIÓN GENÉRICA DE COTIZACIÓN (reutilizable por aseguradora)
# ----------------------------------------------------------------------
async def _cotizar_generico(nombre_aseguradora: str, url_login: str,
                             user_field: str, pass_field: str,
                             env_user: str, env_pass: str,
                             catalogo: list[dict], cliente: DatosCliente,
                             headless: bool = True) -> list[dict]:
    """
    Motor genérico: loguea una vez y cotiza cada plan elegible.
    PLANTILLA — los selectores de navegación/formulario/descarga dentro
    del bucle deben ajustarse por aseguradora (cada portal es distinto).
    """
    planes_a_cotizar = planes_elegibles(catalogo, cliente)
    if not planes_a_cotizar:
        return [{"aseguradora": nombre_aseguradora, "plan": "—", "estado": "sin_planes_elegibles",
                  "prima": None, "pdf_path": None, "detalle": f"Ningún plan de {nombre_aseguradora} aplica"}]

    resultados = []
    async with _SEMAFORO:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()
            try:
                await page.goto(url_login)
                await page.fill(user_field, os.getenv(env_user, ""))
                await page.fill(pass_field, os.getenv(env_pass, ""))
                await page.click('button[type="submit"]')
                await page.wait_for_load_state("networkidle")

                for plan in planes_a_cotizar:
                    resultado = {"aseguradora": nombre_aseguradora, "plan": plan["nombre"],
                                 "estado": "pendiente_configurar_selectores", "prima": None,
                                 "pdf_path": None, "detalle": ""}
                    # --- AJUSTAR POR PORTAL: navegar, seleccionar plan['selector_valor'],
                    #     llenar formulario con datos del cliente, calcular, descargar PDF ---
                    #     Nota: cliente.valor_asegurado puede ser None (campo opcional).
                    #     Si el portal lo exige y viene vacío, deja que el portal lo pida
                    #     con su propio default, o omite ese page.fill() cuando sea None:
                    #     if cliente.valor_asegurado is not None:
                    #         await page.fill('input[name="valor_asegurado"]', str(cliente.valor_asegurado))
                    resultados.append(resultado)

            except Exception as e:
                resultados = [{"aseguradora": nombre_aseguradora, "plan": p["nombre"], "estado": "error",
                               "prima": None, "pdf_path": None, "detalle": f"Fallo de login: {e}"}
                              for p in planes_a_cotizar]
            finally:
                await browser.close()
    return resultados


async def cotizar_sura(cliente, headless=True):
    return await _cotizar_generico("Sura", "https://portal-agentes.sura.com/login",
                                    'input[name="usuario"]', 'input[name="clave"]',
                                    "SURA_USER", "SURA_PASS", PLANES_SURA, cliente, headless)


async def cotizar_seguros_del_estado(cliente, headless=True):
    return await _cotizar_generico("Seguros del Estado", "https://portalagentes.segurosdelestado.com/login",
                                    'input[name="usuario"]', 'input[name="clave"]',
                                    "ESTADO_USER", "ESTADO_PASS", PLANES_SEGUROS_DEL_ESTADO, cliente, headless)


async def cotizar_equidad(cliente, headless=True):
    return await _cotizar_generico("Equidad Seguros", "https://polizae.laequidadseguros.coop",
                                    'input[name="usuario"]', 'input[name="clave"]',
                                    "EQUIDAD_USER", "EQUIDAD_PASS", PLANES_EQUIDAD, cliente, headless)


async def cotizar_axa_colpatria(cliente, headless=True):
    # Nota: el login de AXA Colpatria corre sobre Auth0 (axa-colpatria.us.auth0.com),
    # un proveedor de identidad externo. Los formularios de Auth0 casi siempre usan
    # name="username" y name="password" (no "usuario"/"clave") — verifícalo con
    # playwright codegen antes de correr en producción.
    return await _cotizar_generico("AXA Colpatria", "https://axa-colpatria.us.auth0.com",
                                    'input[name="username"]', 'input[name="password"]',
                                    "AXA_USER", "AXA_PASS", PLANES_AXA_COLPATRIA, cliente, headless)


async def cotizar_solidaria(cliente, headless=True):
    return await _cotizar_generico("Solidaria", "https://portal.solidaria.com.co/login",
                                    'input[name="usuario"]', 'input[name="clave"]',
                                    "SOLIDARIA_USER", "SOLIDARIA_PASS", PLANES_SOLIDARIA, cliente, headless)


# ----------------------------------------------------------------------
# 4. ORQUESTADOR — corre las 6 aseguradoras EN PARALELO
# ----------------------------------------------------------------------
async def cotizar_todas(cliente: DatosCliente, headless: bool = True) -> list[dict]:
    tareas = [
        cotizar_sura(cliente, headless),
        cotizar_seguros_del_estado(cliente, headless),
        cotizar_equidad(cliente, headless),
        cotizar_axa_colpatria(cliente, headless),
        cotizar_solidaria(cliente, headless),
        # Las 8 de Web Service (Bolívar, SBS, Allianz, HDI, Mapfre, Seguros
        # Mundial, Quality, Previsora) se agregan aquí como llamadas a API
        # normales (requests/httpx) en cuanto llegue la aprobación.
    ]
    resultados_por_aseguradora = await asyncio.gather(*tareas)
    return [fila for lista in resultados_por_aseguradora for fila in lista]


def guardar_resultado_excel(resultados: list[dict], cliente: DatosCliente):
    df = pd.DataFrame(resultados)
    nombre_archivo = f"cotizaciones_{cliente.numero_documento}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    df.to_excel(nombre_archivo, index=False)
    print(f"\n✅ Resultado guardado en: {nombre_archivo}\n")
    print(df.to_string(index=False))
    return nombre_archivo


if __name__ == "__main__":
    cliente_ejemplo = DatosCliente(
        nombre_completo="María Pérez", tipo_documento="CC", numero_documento="123456789",
        fecha_nacimiento="15/03/1990", genero="F", ciudad="Ibagué", telefono="3001234567",
        correo="maria.perez@email.com", tipo_seguro="vida", valor_asegurado=50000000,
    )
    resultados = asyncio.run(cotizar_todas(cliente_ejemplo, headless=True))
    guardar_resultado_excel(resultados, cliente_ejemplo)
