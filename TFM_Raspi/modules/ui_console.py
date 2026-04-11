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
    def show_error(msg):
        print(f">> [ERROR] {msg}")

    @staticmethod
    def show_info(msg):
        print(f">> {msg}")