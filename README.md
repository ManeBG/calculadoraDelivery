# Calculadora de Deliveries — Miscelánea García
# ================================================
# App Flask privada para verificar y auditar pedidos de delivery

## Instalación y arranque

```bash
# 1. Crea y activa un entorno virtual
python3 -m venv venv
source venv/bin/activate       # Linux / macOS
# venv\Scripts\activate        # Windows

# 2. Instala dependencias
pip install -r requirements.txt

# 3. Ejecuta la app
python app.py
```

La app estará disponible en: **http://127.0.0.1:5000**

## Estructura del proyecto

```
calculadoraDelivey/
├── app.py                    ← Entry point Flask
├── requirements.txt
├── README.md
├── data/
│   └── products.json         ← Catálogo Miscelánea García
├── services/
│   ├── __init__.py
│   ├── catalog.py            ← Adaptador del JSON
│   ├── calculator.py         ← Motor de cálculo
│   ├── history.py            ← SQLite historial
│   └── parser.py             ← Parser del formulario
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── verificador.html
│   ├── resultado.html
│   ├── historial.html
│   ├── resumen.html
│   └── error.html
├── static/
│   ├── css/styles.css
│   └── js/
│       ├── app.js
│       └── verificador.js
└── database/
    └── historial.db          ← Se crea automáticamente al iniciar
```

## Rutas disponibles

| Ruta            | Descripción                             |
|-----------------|-----------------------------------------|
| `/`             | Dashboard con resumen del día           |
| `/verificar`    | Formulario de verificación de pedidos   |
| `/resultado`    | Resultado del último cálculo            |
| `/historial`    | Tabla de verificaciones guardadas       |
| `/ver/<id>`     | Detalle de una verificación específica  |
| `/resumen`      | Resumen acumulado del día               |

## Base de datos

La app crea `database/historial.db` automáticamente.
Para reiniciar/borrar el historial, simplemente elimina ese archivo.

## Reglas de negocio

- `precio_web`    → lo que paga el cliente (precio delivery)
- `precio_tienda` → precio real de costo para la tienda
- **Ganancia plataforma** = subtotal_web − subtotal_tienda
- **Pago repartidor** = costo de envío configurado en JSON
- **Estado**: OK (diff ≤ $0.01) / Revisar (diff ≤ $5) / Manipulado (diff > $5)
# calculadoraDelivery
