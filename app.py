# from flask import Flask, request
# import requests
# import os

# TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

#   # <-- reemplazá esto con tu token real
# CHAT_ID = '8107106288'  # Tu chat_id personal
# def enviar_telegram(mensaje):
#     url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
#     data = {'chat_id': CHAT_ID, 'text': mensaje}
#     requests.post(url, data=data)

# app = Flask(__name__)

# @app.route('/confirm', methods=['GET'])
# def confirm():
#     email = request.args.get('email')
#     if not email:
#         return "❌ Falta el parámetro ?email=", 400

#     enviar_telegram(f"📩 Confirmación recibida de: {email}")
#     return "✅ Confirmación registrada. ¡Gracias!"

# @app.route('/')
# def home():
#     return "Servidor de confirmaciones activo."

# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=10000)

"""
Bot de Confirmación Telegram - Versión Profesional
Autor: Claude
Fecha: 03/05/2025
Descripción: Servicio para recibir confirmaciones por email y notificar a través de Telegram.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
import time
from functools import wraps

from flask import Flask, request, render_template, jsonify
import requests
from dotenv import load_dotenv

# Cargar variables de entorno desde archivo .env
load_dotenv()

# Configuración
class Config:
    """Configuración de la aplicación."""
    # Variables sensibles desde entorno
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '8107106288')
    
    # Configuración del servidor
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    PORT = int(os.environ.get('PORT', 10000))
    HOST = os.environ.get('HOST', '0.0.0.0')
    
    # Ruta para logs
    LOG_FILE = os.environ.get('LOG_FILE', 'application.log')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    # Límite de tasa (anti-flood)
    RATE_LIMIT = int(os.environ.get('RATE_LIMIT', 10))  # solicitudes
    RATE_WINDOW = int(os.environ.get('RATE_WINDOW', 60))  # segundos

    @classmethod
    def validate(cls):
        """Validar configuración crítica."""
        if not cls.TELEGRAM_TOKEN:
            raise ValueError("TELEGRAM_TOKEN no está configurado en las variables de entorno")
        if not cls.CHAT_ID:
            raise ValueError("TELEGRAM_CHAT_ID no está configurado en las variables de entorno")


# Configuración de logger
def setup_logger():
    """Configura el sistema de logging."""
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    
    logger = logging.getLogger('confirmation_bot')
    logger.setLevel(log_level)
    
    # Handler para archivo con rotación
    file_handler = RotatingFileHandler(
        Config.LOG_FILE, maxBytes=1024*1024*5, backupCount=5
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    
    # Formato del log
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# Inicialización
logger = setup_logger()
app = Flask(__name__)

# Sistema simple de limitación de tasa
request_history = {}

def rate_limit(func):
    """Decorador para limitar la tasa de solicitudes por IP."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        client_ip = request.remote_addr
        current_time = time.time()
        
        # Limpiar historial antiguo
        request_history.setdefault(client_ip, [])
        request_history[client_ip] = [
            timestamp for timestamp in request_history[client_ip]
            if current_time - timestamp < Config.RATE_WINDOW
        ]
        
        # Verificar límite
        if len(request_history[client_ip]) >= Config.RATE_LIMIT:
            logger.warning(f"Límite de tasa excedido para IP: {client_ip}")
            return jsonify({
                "status": "error",
                "message": "Demasiadas solicitudes. Inténtalo más tarde."
            }), 429
        
        # Registrar la solicitud
        request_history[client_ip].append(current_time)
        
        return func(*args, **kwargs)
    return wrapper


class TelegramNotifier:
    """Clase para manejar las notificaciones de Telegram."""
    
    @staticmethod
    def send_message(message):
        """Envía un mensaje a través de la API de Telegram.
        
        Args:
            message: Texto del mensaje a enviar
            
        Returns:
            bool: True si el envío fue exitoso, False en caso contrario
        """
        if not Config.TELEGRAM_TOKEN or not Config.CHAT_ID:
            logger.error("Configuración de Telegram incompleta")
            return False
            
        url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
        data = {
            'chat_id': Config.CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'  # Permite formateo HTML básico
        }
        
        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            
            if response.status_code == 200:
                logger.info(f"Mensaje enviado a Telegram: {message[:50]}...")
                return True
            else:
                logger.error(f"Error al enviar mensaje: {response.text}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en la solicitud a Telegram API: {str(e)}")
            return False


def validate_email(email):
    """Validación simple de formato de email.
    
    Args:
        email: String con dirección de email
        
    Returns:
        bool: True si el formato es válido
    """
    if not email:
        return False
        
    # Validación básica de formato
    if '@' not in email or '.' not in email:
        return False
        
    # Evitar inyecciones con caracteres sospechosos
    suspicious_chars = ['<', '>', '"', "'", ';', '\\', '/', '(', ')', '{', '}']
    if any(char in email for char in suspicious_chars):
        return False
        
    return True


@app.route('/confirm', methods=['GET'])
@rate_limit
def confirm():
    """Endpoint para recibir confirmaciones."""
    email = request.args.get('email', '')
    
    # Validar parámetro email
    if not validate_email(email):
        logger.warning(f"Intento con email inválido: {email}")
        return jsonify({
            "status": "error",
            "message": "Correo electrónico inválido o faltante"
        }), 400
    
    # Información extra (opcional)
    source = request.args.get('source', 'desconocido')
    user_agent = request.headers.get('User-Agent', 'desconocido')
    
    # Construir mensaje con formato HTML para Telegram
    message = (
        f"📩 <b>Confirmación recibida</b>\n"
        f"<b>Email:</b> {email}\n"
        f"<b>Fuente:</b> {source}\n"
        f"<b>Fecha:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"<b>Cliente:</b> {user_agent[:50]}..."
    )
    
    # Enviar notificación
    success = TelegramNotifier.send_message(message)
    
    if success:
        logger.info(f"Confirmación procesada para: {email}")
        return render_template_string(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Confirmación Exitosa</title>
                <style>
                    body { 
                        font-family: Arial, sans-serif; 
                        text-align: center; 
                        margin-top: 50px;
                        background-color: #f7f7f7;
                    }
                    .container {
                        background-color: white;
                        border-radius: 10px;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                        padding: 40px;
                        max-width: 500px;
                        margin: 0 auto;
                    }
                    .success {
                        color: #28a745;
                        font-size: 64px;
                        margin-bottom: 20px;
                    }
                    h1 { color: #333; }
                    p { color: #666; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success">✅</div>
                    <h1>¡Confirmación Registrada!</h1>
                    <p>Gracias por confirmar tu correo electrónico.</p>
                    <p>Te contactaremos pronto.</p>
                </div>
            </body>
            </html>
            """
        )
    else:
        logger.error(f"Error al procesar confirmación para: {email}")
        return jsonify({
            "status": "error",
            "message": "Error al procesar la confirmación"
        }), 500


@app.route('/')
def home():
    """Página principal del servicio."""
    return render_template_string(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Servicio de Confirmación</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    text-align: center; 
                    margin-top: 50px;
                    background-color: #f7f7f7;
                }
                .container {
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    padding: 40px;
                    max-width: 600px;
                    margin: 0 auto;
                }
                h1 { color: #333; }
                p { color: #666; }
                .status {
                    display: inline-block;
                    background-color: #28a745;
                    color: white;
                    padding: 5px 15px;
                    border-radius: 15px;
                    font-weight: bold;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Servidor de Confirmaciones</h1>
                <div class="status">Activo</div>
                <p>Este servicio procesa confirmaciones de correo electrónico.</p>
                <p>Para usar, envíe una solicitud GET a <code>/confirm?email=usuario@ejemplo.com</code></p>
            </div>
        </body>
        </html>
        """
    )


@app.route('/health')
def health_check():
    """Endpoint para verificación de estado del servicio."""
    return jsonify({
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": time.time()
    })


@app.errorhandler(404)
def page_not_found(e):
    """Manejador para ruta no encontrada."""
    return jsonify({
        "status": "error",
        "message": "Ruta no encontrada"
    }), 404


@app.errorhandler(500)
def server_error(e):
    """Manejador para errores internos."""
    logger.error(f"Error interno del servidor: {str(e)}")
    return jsonify({
        "status": "error",
        "message": "Error interno del servidor"
    }), 500


def render_template_string(template_string):
    """Función simple para renderizar template como string."""
    return template_string


if __name__ == '__main__':
    try:
        # Validar configuración antes de iniciar
        Config.validate()
        
        logger.info(f"Iniciando servidor en {Config.HOST}:{Config.PORT}")
        logger.info(f"Modo DEBUG: {Config.DEBUG}")
        
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG
        )
    except Exception as e:
        logger.critical(f"Error al iniciar la aplicación: {str(e)}")
        raise