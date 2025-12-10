# Tarea 2
Se encuentran adjuntos dos pares de archivos. Main-Server y main2 - server2.
El primer par corresponde a la primera versión (funcional) que incluye la conexión entre dispositivos por socket UDP o TCP y el intercambio entre protocolos; el envio de datos por JSON y las gráficas en tiempo real.
EL segundo par incluye la funcionalidad del calculo de los features(RMS, fft, picos) y el envio de estos juntos con los datos para graficar. Esta funcion entrega errores en la comunciaicon entre dispostivos
No logramos hacer la conexión con el sensor BME688, por lo que todo esta desarrollado sólo para le BMI270.



# Notas de Implementación y Decisiones Técnicas
 Edge Computing
* Ventana de Procesamiento ($N$): Se estableció un buffer de 256 muestras. Esto permite utilizar algoritmos de FFT de base 2 (Radix-2) de manera eficiente en memoria.
* Frecuencia de Muestreo ($Fs$): Configurada a 400 Hz en el sensor BMI270.
* Tasa de Actualización: La combinación de N=256 y Fs=400 Hz resulta en una tasa de actualización de características de aprox 1.56 Hz, ofreciendo un equilibrio óptimo entre "tiempo real" y estabilidad de lectura.

## 2. Abstracción de Hardware (HAL) - ESP32-S3¿
Durante la integración con el ESP-IDF v5.x en el SoC ESP32-S3, se tomaron las siguientes decisiones:
* **Fuente de Reloj (Clock Source):** Se forzó explícitamente el uso de `I2C_CLK_SRC_XTAL` (Cristal de 40MHz).
    * *Justificación:* El driver por defecto intenta derivar el reloj de fuentes internas (`RC_FAST` o `APB`) que generaban errores de precisión (`ESP_ERR_INVALID_ARG`) o identificadores desconocidos (`unknown clk src 21`) al intentar dividir la frecuencia para alcanzar los 100kHz estándar del bus I2C. El uso del XTAL garantiza una referencia de tiempo estable.
* **Inicialización del Sensor:** Se implementó una verificación de estado (`Internal Status 0x21`) post-carga del archivo de configuración. Si el sensor no reporta estado "Ready", el firmware detiene la ejecución para evitar el envío de datos espurios.

## 3. Protocolo de Comunicación y Máquina de Estados
La comunicación sigue un modelo Cliente-Servidor asíncrono con una máquina de estados simplificada para gestionar la conexión.
### Estados del Cliente (ESP32)
1.  **IDLE (Reposo):**
    * El cliente envía un mensaje de latido (`STATUS:IDLE`) cada **200ms**.
    * *Decisión de Diseño:* Se redujo el intervalo de 1000ms a 200ms para evitar que el `socket.timeout` del servidor (configurado en 500ms para no bloquear la GUI) cerrara la conexión prematuramente.
2.  **RUNNING (Medición):**
    * El cliente llena el buffer de 256 muestras, calcula los features y transmite un payload CSV.
    * **Payload:** `ax, ay, az, gx, gy, gz, rms, peaks, freq`.

### Control de Flujo (Piggybacking)
No existe un socket dedicado para comandos. Las órdenes de control (`CMD:START`, `CMD:STOP`, `CMD:SET_UDP`) se envían desde el servidor como respuesta (ACK) al paquete de datos o al latido del cliente. Esto simplifica la gestión de hilos en el microcontrolador.

## 4. Estructura del Software

### Firmware (`main2.c`)
* **Gestión de Memoria:** Se incrementó el Stack de la tarea principal a **16KB** (`16384` bytes) para acomodar los buffers de arreglos (`int16_t` y `cpx_t`) necesarios para la FFT sin provocar un desbordamiento de pila (*Stack Overflow*).
* **Recuperación de Errores:** Se implementó lógica de reconexión automática en caso de fallo en `send()` o `connect()`, con retardos no bloqueantes para no activar el Watchdog Timer.

### Servidor (`server_final.py`)
* **Multithreading:** Se separaron los hilos de escucha (TCP y UDP) del hilo principal de la GUI (`tkinter`) para evitar congelamientos durante la recepción de datos.
* **Visualización:** Se utilizan colas circulares (`collections.deque`) de longitud fija para la graficación en tiempo real, evitando el crecimiento indefinido del uso de memoria RAM durante sesiones largas.
* **Seguridad:** Se incluye la corrección de permisos para `matplotlib` en entornos Linux embebidos (`cache_frame_data=False`).
---
