# 📂 Estructura del Proyecto Raspberry Pi (TFM)

Este documento detalla la organización de archivos y carpetas del sistema central (Raspberry Pi). El diseño sigue una **arquitectura modular** para facilitar la expansión (añadir más pulseras o nuevas IAs) sin romper el código base.

## 🌳 Árbol de Directorios

```text
TFM_Raspi/
│
├── .venv/                 # Entorno Virtual de Python (Librerías aisladas)
├── .gitignore             # Archivos que Git debe ignorar (CSVs grandes, claves, basura)
├── main.py                # PUNTO DE ENTRADA. Orquesta todo el sistema.
│
├── ⚙️ config/             # Configuraciones globales
│   ├── __init__.py
│   └── settings.py        # Constantes (UUIDs, Nombres de dispositivos, rutas...)
│
├── 🧠 modules/            # Lógica del negocio (Backend)
│   ├── __init__.py
│   ├── ble_manager.py     # Gestión de Bluetooth (Escaneo, Conexión, Suscripción)
│   ├── data_handler.py    # Procesamiento de datos (Raw -> CSV estructurado)
│   └── security.py        # Gestión de emparejamiento y claves seguras
│
├── 🖥️ gui/                # Interfaz de Usuario (Frontend)
│   ├── __init__.py
│   └── app.py             # Código de la aplicación visual (Dashboard/Consola)
│
└── 💾 data/               # Almacenamiento de datos (Ignorado por Git)
    ├── raw/               # Archivos CSV crudos generados por las sesiones
    └── models/            # Modelos de IA entrenados (.tflite, .onnx)