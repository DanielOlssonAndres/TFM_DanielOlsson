import struct # Para desempaquetar datos binarios

# Constante de los dispositivos ESP32. Número de muestras por paquete
SAMPLES_PER_PACKET = 35

# Función para decodificar un paquete de datos binarios recibido por BLE
def decode_packet(data):
    
    # El paquete debe tener exactamente 218 bytes
    # 4 (seq) + 4 (time) + 35 * (2(x)+2(y)+2(z)) = 218
    expected_size = 4 + 4 + (SAMPLES_PER_PACKET * 6)
    
    # Comprobamos el tamaño del paquete (si se perdieron datos por el camino)
    if len(data) != expected_size:
        print(f"Tamaño de paquete incorrecto: Recibido {len(data)}, Esperado {expected_size}")
        return None # No se devolve nada si el tamaño es incorrecto

    # Desempaquetamiento la Cabecera (8 bytes)
    # '<' = Little Endian (Estándar en ESP32)
    # 'I' = Unsigned Int (4 bytes)
    header_format = '<II' 
    # Calculo del tamaño de la cabecera
    header_size = struct.calcsize(header_format)
    
    # Obtenemos los valores para el ID de secuencia y timestamp
    sequence_id, timestamp = struct.unpack(header_format, data[:header_size])

    # Obtenemos las muetsras de lo que queda del paquete
    raw_samples = data[header_size:]
    # Lista para guardar las muestras decodificadas
    samples = []

    # Desempaquetamiento de las muestras (6 bytes cada una: X,Y,Z)
    # Iteramos cada 6 bytes (X, Y, Z son int16 = 'h')
    # 'h' = short (2 bytes con signo)
    sample_format = '<hhh'
    
    for i in range(SAMPLES_PER_PACKET):
        start = i * 6
        end = start + 6
        chunk = raw_samples[start:end]
        
        # Desempaquetamos los valores X, Y, Z en numeros python
        x, y, z = struct.unpack(sample_format, chunk)
        
        # Se meten las muestras en la lista
        samples.append({
            "x": x,
            "y": y,
            "z": z
        })

    # Se devuelve toda la información del paquete decodificada
    return {
        "sequence_id": sequence_id,
        "timestamp_start": timestamp,
        "samples": samples
    }