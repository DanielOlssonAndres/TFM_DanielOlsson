import asyncio
import os
import sys
import glob
import pwd
import multiprocessing as mp
from modules.ble_manager import BLEManager
from modules.data_recorder import DataRecorder

async def seleccionar_posicion():
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
        
        eleccion = await asyncio.to_thread(input, "\nElija una opción: ")
        eleccion = eleccion.strip()

        if eleccion in opciones_validas:
            if eleccion == "7":
                alias = await asyncio.to_thread(input, "Introduzca el alias personalizado: ")
                # Reemplazamos espacios por barras bajas para mantener consistencia en los nombres
                return alias.strip().replace(" ", "_")
            return opciones_validas[eleccion]
        
        print("ERROR: Opción no válida.")

async def input_async(prompt):
    return await asyncio.to_thread(input, prompt)

def configurar_entorno_grafico():
    # Gestiona el enrutamiento de la interfaz gráfica.
    # Si detecta SSH con X11 Forwarding, envía la GUI al PC.
    # Si no hay X11 Forwarding pero hay HDMI, salta la seguridad local para mostrar la GUI en la Raspi.
    
    display_actual = os.environ.get('DISPLAY')

    # Caso SSH -X o terminal local ya configurada
    if display_actual:
        return True

    # Caso SSH sin -X. Comprobamos si hay HDMI físico
    hdmi_conectado = False
    for port in glob.glob('/sys/class/drm/card*-HDMI-*/status'):
        try:
            with open(port, 'r') as f:
                if 'connected' in f.read():
                    hdmi_conectado = True
                    break
        except Exception:
            pass

    if hdmi_conectado:
        # Inyectar variables de entorno para saltar la protección de la sesión local
        uid = os.getuid()
        user_home = os.path.expanduser('~')
        
        # Parámetros básicos para la pantalla principal
        os.environ['DISPLAY'] = ':0'
        os.environ['WAYLAND_DISPLAY'] = 'wayland-0'
        
        # Parámetro de seguridad para X11
        xauth_path = os.path.join(user_home, '.Xauthority')
        if os.path.exists(xauth_path):
            os.environ['XAUTHORITY'] = xauth_path
            
        # Parámetro de seguridad para Wayland 
        os.environ['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
        
        return True

    return False

async def main():
    # Inicializamos el grabador de datos 
    recorder = DataRecorder()
    ble = BLEManager(data_callback=recorder.process_incoming_data)

    while True:
        devs = ble.connected_devices
        print("\n" + "="*40)
        print(f"   [MODO GRABACIÓN] Dispositivos Enlazados: {len(devs)}")
        if not devs:
            print(" (Ningún dispositivo enlazado)")
        else:
            for mac, info in devs.items():
                print(f" * {info['alias']} [{mac}]")
        print("="*40)
        print("1. Registrar un nuevo dispositivo")
        print("2. Empezar el grabado de datos")
        print("3. Desconectar dispositivo")
        print("4. Finalizar programa")
        
        choice = await input_async("\n>> Seleccione opción: ")
        choice = choice.strip()

        # Opción 1: Registrar un nuevo dispositivo
        if choice == "1":
            print("\nBuscando dispositivos cercanos...")
            candidates = await ble.scan_available()
            
            # Filtramos para mostrar solo dispositivos que sean nuestros ESP32 (D2526) y que no estén ya conectados
            valid_candidates = [d for d in candidates if d.name and d.name.startswith("D2526") and d.address not in ble.connected_devices]

            if not valid_candidates:
                print(">> No se encontraron dispositivos 'D2526' nuevos.")
                continue

            for i, d in enumerate(valid_candidates):
                print(f"[{i}] {d.name} ({d.address})")
            
            sel = await input_async(">> Nº disp. (o 'BACK' para volver): ")
            if sel.strip().upper() == "BACK": continue
            
            try:
                idx = int(sel)
                if 0 <= idx < len(valid_candidates):
                    target = valid_candidates[idx]
                    alias = await seleccionar_posicion()
                    # Conectamos y añadimos el alias al registro interno
                    await ble.connect_and_register(target, alias)
            except ValueError:
                pass

        # Opción 2: Empezar el grabado de datos
        elif choice == "2":
            if not ble.connected_devices:
                print(">> Error: No hay dispositivos registrados.")
                await asyncio.sleep(1)
                continue
            
            await input_async("\n>> Se va a iniciar la grabación con los dispositivos actuales. Pulse ENTER para continuar...")

            try:
                num_gestures = int(await input_async(">> Número de gestos/actividades a grabar: "))
                gestures = []
                for i in range(num_gestures):
                    g = await input_async(f"   Nombre del gesto {i+1} (ej. Correr, Saltar): ")
                    gestures.append(g.strip())
                
                num_frames = int(await input_async(">> Número de frames (ventanas) por actividad: "))
            except ValueError:
                print(">> Error: Entrada inválida. Debe introducir números.")
                continue

            print("\n--- RESUMEN DE LA GRABACIÓN ---")
            print(f"Gestos a grabar: {', '.join(gestures)}")
            print(f"Frames por gesto: {num_frames} (1 frame = 1 ventana solapada)")
            print("-------------------------------")
            
            # Bucle para el submenú de gráficos
            while True:
                print("\n1. Grabar CON visualizador de energía")
                print("2. Grabar SIN visualizador de energía")
                print("3. Volver al menú principal")
                
                modo = await input_async("\n>> Elija una opción (1-3): ")
                modo = modo.strip()
                
                if modo == "1":
                    if not configurar_entorno_grafico():
                        print("\n>> [ERROR] Esta opción no está disponible. No se detecta X11 Forwarding (ssh -X)")
                        print(">> ni un monitor HDMI conectado físicamente a la Raspberry Pi.")
                        print(">> Por favor, elija la opción 2.")
                        continue
                    else:
                        recorder.use_visualizer = True
                        break
                        
                elif modo == "2":
                    recorder.use_visualizer = False
                    break # Salimos del submenú para continuar con la grabación
                    
                elif modo == "3":
                    break # Salimos del submenú
                    
                else:
                    print(">> Opción no válida.")

            # Si el usuario eligió salir en el submenú, volvemos al menú principal
            if modo == "3":
                continue

            recorder.clear_memory()
            
            # Iniciar recepción Bluetooth 
            await ble.start_listening()
            
            if recorder.use_visualizer:
                recorder.start_visualizers(ble.connected_devices)

            print("\n" + "*"*40)
            print(" INICIANDO SECUENCIA DE GRABACIÓN CONTINUA")
            print("*"*40)

            # Guardamos la lista de MACs con las que empezamos para comprobar si alguna se cae
            mac_list = list(ble.connected_devices.keys())

            # Bucle principal de grabación por cada gesto 
            for gesture in gestures:
                await input_async(f"\n>> Pulse ENTER para comenzar a grabar '{gesture}' continuamente...")
                print(f"   [GRABANDO] Gesto: {gesture} | Esperando {num_frames} frames...")
                
                # Le indicamos al grabador interno qué gesto es y cuántos frames debe extraer
                recorder.start_recording(gesture, num_frames, mac_list)
                
                # Bucle de espera activa (No bloqueante) 
                last_printed = -1
                
                # Lista dinámica de los dispositivos que siguen vivos en esta grabación
                active_macs = mac_list.copy()

                # Mientras no todos los dispositivos activos hayan alcanzado el número de frames
                while not recorder.is_recording_complete(active_macs):
                    await asyncio.sleep(0.1) # Pausa mínima
                    
                    # Revisamos si alguno se ha caído
                    for mac in active_macs[:]: 
                        if mac not in ble.connected_devices:
                            print(f"\n   [AVISO] Dispositivo {mac} desconectado. Descartando sus datos...")
                            active_macs.remove(mac)
                            recorder.discard_device(mac) # Borramos lo que llevara grabado
                    
                    if not active_macs:
                        print("\n   [ERROR CRÍTICO] Todos los dispositivos se desconectaron. Abortando gesto.")
                        break
                    
                    # Extraemos el progreso para imprimirlo en la misma línea
                    current = recorder.get_max_frames_recorded()
                    if current != last_printed and current > 0:
                        print(f"\r   -> Grabados {current}/{num_frames} frames...", end='', flush=True)
                        last_printed = current
                
                # Cuando se alcanza la meta o se aborta por desconexión, paramos internamente
                recorder.stop_recording()
                print(f"\n   [DETENIDO] Grabación de '{gesture}' finalizada.")
            
            # Parada del sistema y guardado 
            # Cortamos la suscripción BLE a las pulseras
            await ble.stop_listening()
            if recorder.use_visualizer:
                recorder.stop_visualizers()

            # Volcamos todo lo que está en memoria (RAM) a los archivos físicos .csv
            archivos_creados = recorder.save_data(gestures, ble.connected_devices)
            print("\n>> SECUENCIA FINALIZADA. Archivos guardados:")
            for f in archivos_creados:
                print(f"   - {f}")
            await input_async("\nPulse ENTER para volver al menú...")

        elif choice == "3":
            if not ble.connected_devices: continue
            print("\n--- Seleccione dispositivo a desconectar ---")
            
            mac_list = list(ble.connected_devices.keys())
            for i, mac in enumerate(mac_list):
                print(f"[{i}] {ble.connected_devices[mac]['alias']} ({mac})")
            
            sel = await input_async(">> Nº disp. (o 'BACK' para volver): ")
            if sel.strip().upper() == "BACK": continue
            
            try:
                idx = int(sel)
                if 0 <= idx < len(mac_list):
                    await ble.disconnect_device(mac_list[idx])
            except ValueError:
                pass

        elif choice == "4":
            break

    # Cierre limpio
    await ble.disconnect_all()
    print("Sistema apagado.")

if __name__ == "__main__":
    # Necesario para el correcto funcionamiento de multiprocessing (las gráficas)
    mp.freeze_support() 
    try:
        # Iniciamos el bucle de eventos principal
        asyncio.run(main())
    except KeyboardInterrupt:
        # Salida limpia si el usuario pulsa Ctrl+C
        pass