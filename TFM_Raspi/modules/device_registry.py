import json
import os

# Ruta donde se guarda la base de datos de dispositivos
REGISTRY_PATH = os.path.join("data", "devices.json")

class DeviceRegistry:
    def __init__(self):
        self.devices = []
        self._load_registry()

    # Funcion que carga el registro de dispositivos desde el archivo JSON
    def _load_registry(self):
        if os.path.exists(REGISTRY_PATH):
            try:
                with open(REGISTRY_PATH, "r") as f:
                    data = json.load(f)
                    self.devices = data.get("devices", [])
            except Exception as e:
                print(f"Error cargando archivo: {e}")
                self.devices = []
        else:
            # Si no existe carpeta data, la creamos
            os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)

    # Funcion que guarda un dispositivo en el archivo JSON
    def save_device(self, address, name, alias):
        # Evitar duplicados
        if self.is_registered(address):
            print(f"El dispositivo {address} ya existe.")
            return

        new_device = {
            "mac": address,
            "name": name,
            "alias": alias
        }
        self.devices.append(new_device)
        self._save_to_disk()
        print(f"Dispositivo guardado: {alias} ({address})")

    # Funcion que elimina un dispositivo del registro
    def remove_device(self, address):
        self.devices = [d for d in self.devices if d["mac"] != address]
        self._save_to_disk()
        print(f"Dispositivo eliminado: {address}")

    # Funcion interna para guardar el registro en disco
    def _save_to_disk(self):
        with open(REGISTRY_PATH, "w") as f:
            json.dump({"devices": self.devices}, f, indent=4)

    # Funcion para verificar si un dispositivo ya está registrado
    def is_registered(self, address):
        for d in self.devices:
            if d["mac"] == address:
                return True
        return False

    # Funcion para obtener la lista completa de dispositivos
    def get_all_devices(self):
        return self.devices