import asyncio

class ConsoleUI:  
    @staticmethod
    def show_main_menu(connected_devices, mode="RECONOCIMIENTO"):
        print("\n" + "="*40)
        print(f"[{mode}] Dispositivos Enlazados: {len(connected_devices)}")
        if not connected_devices:
            print(" (Ningún dispositivo enlazado)")
        else:
            for mac, info in connected_devices.items():
                print(f" * {info['alias']} [{mac}]")
        print("="*40)
        print("1. Registrar un nuevo dispositivo")
        
        if mode == "RECONOCIMIENTO":
            print("2. Comenzar la recepción y predicción de datos")
        else:
            print("2. Empezar el grabado de datos")
            
        print("3. Desconectar dispositivo")
        print("4. Consultar niveles de batería")
        print("5. Finalizar programa")

    @staticmethod
    async def get_input(prompt):
        # Mueve la llamada bloqueante a un hilo separado
        return await asyncio.to_thread(input, prompt)

    @staticmethod
    async def get_position_alias():
        opciones_validas = {
            "1": "Mano_Izquierda", "2": "Mano_Derecha",
            "3": "Tobillo_Izquierdo", "4": "Tobillo_Derecho",
            "5": "Cadera_Izquierda", "6": "Cadera_Derecha",
            "7": "Personalizado"
        }

        while True:
            print("\n--- Seleccione posición del dispositivo ---")
            for k, v in opciones_validas.items():
                print(f"{k}. {v.replace('_', ' ')}")
            
            eleccion = (await ConsoleUI.get_input("\nElija una opción: ")).strip()

            if eleccion in opciones_validas:
                if eleccion == "7":
                    alias = await ConsoleUI.get_input("Introduzca el alias personalizado: ")
                    return alias.strip().replace(" ", "_")
                return opciones_validas[eleccion]
            
            print("ERROR: Opción no válida.")


    @staticmethod
    async def select_candidate_device(candidates):
        if not candidates:
            ConsoleUI.show_info("No se encontraron dispositivos válidos cercanos.")
            return None

        print("\n--- Dispositivos Disponibles ---")
        for i, d in enumerate(candidates):
            print(f"[{i}] {d.name} ({d.address})")
        
        sel = await ConsoleUI.get_input(">> Nº dispositivo: ")
        
        try:
            idx = int(sel)
            if 0 <= idx < len(candidates):
                return candidates[idx]
        except ValueError:
            pass 
            
        ConsoleUI.show_error("Entrada inválida.")
        return None

    @staticmethod
    async def select_device_to_disconnect(connected_devices):
        if not connected_devices:
            ConsoleUI.show_info("No hay dispositivos conectados para eliminar.")
            return None

        print("\n--- Seleccione dispositivo a desconectar ---")
        mac_list = list(connected_devices.keys())
        
        for i, mac in enumerate(mac_list):
            alias = connected_devices[mac]['alias']
            name = connected_devices[mac]['name']
            print(f"[{i}] {name} -> {alias} ({mac})")
        
        sel = await ConsoleUI.get_input(">> Nº dispositivo: ")
        
        try:
            idx = int(sel)
            if 0 <= idx < len(mac_list):
                return mac_list[idx]
        except ValueError:
            pass
            
        ConsoleUI.show_error("Entrada inválida.")
        return None

    @staticmethod
    async def select_model_from_list(model_names):
        if not model_names:
            ConsoleUI.show_error("No hay modelos disponibles en el directorio.")
            return None

        print("\n--- Modelos Disponibles ---")
        for i, mod in enumerate(model_names):
            print(f"[{i}] {mod}")
            
        sel = await ConsoleUI.get_input(">> Seleccione modelo: ")
        
        try:
            return model_names[int(sel)]
        except (ValueError, IndexError):
            ConsoleUI.show_error("Selección inválida.")
            return None

    @staticmethod
    def show_battery_levels(battery_data):
        print("\n--- Nivel de Batería ---")
        for name, alias, mac, nivel in battery_data:
            estado = f"{nivel}%" if nivel is not None else "ERROR DE LECTURA"
            print(f" * {name} -> {alias} ({mac}): {estado}")

    @staticmethod
    def show_error(msg):
        print(f">> [ERROR] {msg}")

    @staticmethod
    def show_info(msg):
        print(f">> {msg}")