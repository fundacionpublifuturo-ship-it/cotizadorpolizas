# Guía de Implementación — Cotizador Multi-Aseguradora

## Estado actual del proyecto (actualizado)

**Aseguradoras activas ahora (RPA — portal manual):**
Sura, Zurich, Seguros del Estado, Equidad Seguros, AXA Colpatria, Solidaria.
Estas ya están en el catálogo del sistema — falta mapear sus selectores reales
(ver Paso 4).

**Aseguradoras pendientes de API (cartas ya enviadas o por enviar):**
Seguros Bolívar, SBS Seguros, Allianz, HDI, Mapfre, Seguros Mundial,
Quality/Quálitas, La Previsora. En cuanto llegue la aprobación y las
credenciales de API de cada una, se agregan a `cotizar_todas()` como
llamadas HTTP normales (no RPA) — mucho más simple y estable.

**Diseño/UX:** el formulario y la página de resultados ya tienen una
identidad visual profesional (header con logo, paleta de marca en
variables CSS, formulario organizado por secciones, resultados en
tarjetas con badges de estado). Los colores actuales (`--color-primario`,
`--color-acento` en el `<style>` de cada HTML) son un placeholder —
en cuanto envíes el logo real de Mateo Herrera Seguros y los colores de
marca (hex), se reemplazan en un solo lugar y todo el sitio se actualiza.


```## Estructura de la app
```
cotizador/
├── app.py                    ← app web (Flask) — formulario + resultados
├── cotizador_multi.py        ← lógica de automatización por aseguradora
├── templates/
│   ├── index.html            ← formulario de datos del cliente
│   └── resultados.html       ← tabla comparativa + links de descarga PDF
└── pdfs_cotizaciones/        ← se crea sola, aquí caen los PDF descargados
```

## Cómo se usa (una vez configurados los selectores reales)
1. `python app.py`
2. Abrir `http://localhost:5000` en el navegador (o publicarlo en un VPS
   para que el equipo de Mateo Herrera Seguros lo use desde cualquier PC).
3. El asesor llena los datos del cliente UNA vez y da clic en "Cotizar en
   todas las aseguradoras".
4. La app abre los navegadores en segundo plano, cotiza en paralelo, y
   muestra una tabla con: aseguradora, prima, estado y botón de descarga
   del PDF de cada cotización.

## Nota sobre "pólizas" vs "cotizaciones"
Esta app entrega PDF de **cotización** (lo que el portal genera al momento
de cotizar). El PDF de **póliza** se emite solo después de que el cliente
acepta y paga — ese paso normalmente lo hace el asesor manualmente dentro
del mismo portal de la aseguradora ya elegida, o se agrega como un paso
adicional de automatización una vez identificado el flujo de emisión de
cada aseguradora (login → cotización aceptada → pago/orden → póliza PDF).
Si quieres que ese paso también se automatice, se agrega como una función
`emitir_poliza_[aseguradora]()` con la misma lógica, una vez tengamos claro
el flujo de emisión de cada portal.


## Paso 1: Preparar el entorno
```bash
pip install playwright pandas openpyxl python-dotenv --break-system-packages
playwright install chromium
```

## Paso 2: Crear archivo `.env` con tus credenciales
En la misma carpeta del script, crea un archivo llamado `.env`:
```
SURA_USER=tu_usuario
SURA_PASS=tu_clave
ALLIANZ_USER=tu_usuario
ALLIANZ_PASS=tu_clave
MAPFRE_USER=tu_usuario
MAPFRE_PASS=tu_clave
```
**Nunca subas este archivo a GitHub ni lo compartas.**

## Paso 3: Configurar el catálogo de planes por aseguradora
Cada aseguradora tiene su propia sección `PLANES_[ASEGURADORA]` en
`cotizador_multi.py`. Ahí defines:
- **Nombre del plan** (como aparece en el portal)
- **selector_valor**: el valor que hay que seleccionar en el portal
  (option, radio button, etc.) — se obtiene inspeccionando el HTML
- **elegible**: una regla en código que decide si el cliente califica

Ejemplo — plan exclusivo para mujeres:
```python
{
    "nombre": "Plan Vida Mujer",
    "selector_valor": "vida_mujer",
    "elegible": lambda c: c.genero == "F" and c.tipo_seguro == "vida",
}
```

Ejemplo — plan solo para mayores de 60:
```python
{
    "nombre": "Plan Vida Senior",
    "selector_valor": "vida_senior",
    "elegible": lambda c: c.tipo_seguro == "vida" and c.edad() >= 60,
}
```

El sistema evalúa automáticamente estas reglas contra los datos del
cliente y **solo cotiza los planes a los que realmente califica** — no
genera cotizaciones inútiles de planes que el cliente no puede tomar.

**Para saber qué planes agregar**: pide a cada aseguradora (o revisa en
el portal) el listado completo de productos que ofrecen para el tipo de
seguro que manejas, y las condiciones de cada uno (género, edad, rango
de valor asegurado, etc.). Eso se traduce directo a este catálogo.

## Paso 4: Mapear los selectores reales de cada portal
Esta es la parte que **no se puede automatizar sin que la hagas una vez por portal**:

1. Abre el portal de la aseguradora en Chrome.
2. Clic derecho sobre el campo (ej: campo "Usuario") → **Inspeccionar**.
3. Busca el atributo `name`, `id`, o `class` del campo en el HTML.
4. Reemplaza en el script:
   ```python
   await page.fill('input[name="usuario"]', ...)
   ```
   por el selector real que encontraste, ej:
   ```python
   await page.fill('#txtUsuario', ...)
   ```
5. Repite para cada campo del formulario de cotización y para el botón de "Calcular"/"Cotizar".

**Tip:** Playwright tiene un modo grabador que hace esto automáticamente:
```bash
playwright codegen https://portal-agentes.sura.com/login
```
Esto abre un navegador — haces el login y llenas el formulario a mano una vez,
y Playwright genera el código Python con los selectores correctos. Copias eso
directo a la función correspondiente.

## Paso 5: Resolver el tema de 2FA (si aplica)
Si un portal pide código por SMS/correo en cada login, dos opciones:
- **Sesión persistente**: loguear manualmente UNA vez y guardar el estado
  de la sesión (`context.storage_state()` en Playwright) para reusarlo
  en corridas futuras sin volver a loguear.
- **Login semi-manual**: correr el script con `headless=False` la primera
  vez del día para que tú ingreses el código, y que se mantenga la sesión
  para las cotizaciones subsecuentes.

## Paso 6: Correr el script
```bash
python cotizador_multi.py
```
Esto abre 3 navegadores en paralelo (uno por aseguradora), cotiza el mismo
cliente en los tres, y genera `cotizaciones_[documento]_[fecha].xlsx` con
la comparación lista para enviar al cliente de Mateo Herrera Seguros.

## Paso 7 (opcional): Automatizar la emisión de pólizas
Una vez los selectores estén ajustados y funcionando, se puede envolver
este script en:
- Un formulario web simple (Flask/FastAPI) donde se ingresan los datos
  del cliente y se dispara la cotización con un clic.
- Un workflow de n8n que llama este script y manda el Excel resultante
  por WhatsApp o correo automáticamente.

## Riesgos a tener en cuenta (negocio, no técnico)
- **Términos de uso**: revisa si el portal de cada aseguradora prohíbe
  el acceso automatizado (algunos lo consideran violación de sus ToS).
- **Mantenimiento**: cuando la aseguradora rediseñe su portal, el
  selector correspondiente se rompe y hay que actualizarlo — no es
  "configúralo una vez y olvídate".
- **Bloqueo por bot**: algunos portales detectan automatización y pueden
  bloquear la cuenta. Mitigación: correr con `headless=False` ocasional,
  no sobrecargar de solicitudes, usar delays entre acciones.
