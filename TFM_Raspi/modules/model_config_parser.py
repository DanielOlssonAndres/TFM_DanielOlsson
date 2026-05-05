import os
from dataclasses import dataclass

# Usamos dataclass para crear una estructura de datos que contendrá la información extraída de los ficheros .txt
@dataclass
class ModelConfig:
    name: str
    required_devices: list
    classes: list

class ModelConfigParser:

    def __init__(self, models_dir, configs_dir):
        self.models_dir = models_dir
        self.configs_dir = configs_dir

    def get_available_models(self):
        # Devuelve una lista con los nombres de los modelos disponibles (.json)
        try:
            # Escanea el directorio y limpia la extensión .json para mostrar al usuario
            return [f.replace('.json', '') for f in os.listdir(self.models_dir) if f.endswith('.json')]
        except FileNotFoundError:
            return []

    def load_config(self, model_name):
        config_path = os.path.join(self.configs_dir, f"{model_name}.txt")
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Falta el fichero de configuración: {config_path}")

        req_devs, clases_finales = [], []
        
        # Lectura del archivo plano
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEVICES:"):
                    # Extrae la lista de dispositivos separada por comas
                    req_devs = [d.strip() for d in line.split("DEVICES:")[1].split(",")]
                elif line.startswith("CLASSES:"):
                    # Extrae la lista de clases a predecir separada por comas
                    clases_finales = [c.strip() for c in line.split("CLASSES:")[1].split(",")]

        # Validación de integridad de los datos parseados
        if not req_devs or not clases_finales:
            raise ValueError(f"El fichero '{model_name}.txt' está mal formateado o incompleto.")

        # Devuelve el objeto estructurado
        return ModelConfig(name=model_name, required_devices=req_devs, classes=clases_finales)