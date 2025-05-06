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

from flask import Flask, request, jsonify,redirect, render_template_string
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
    
    # Construir mensaje con formato HTML para Telegram
    message = (
        f"📩 <b>Confirmación recibida</b>\n"
        f"<b>Email:</b> {email} - <b>{time.strftime('%d%b%Y %H:%M')}</b>"
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
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        text-align: center; 
                        margin-top: 30px;
                        background-color: black;
                        color: #333;
                    }
                    .container {
                        background-color: white;
                        border-radius: 12px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                        padding: 40px;
                        max-width: 550px;
                        margin: 0 auto;
                    }
                    .success {
                        color: #28a745;
                        font-size: 64px;
                        margin-bottom: 20px;
                    }
                    h1 { 
                        color: #2a4365; 
                        margin-bottom: 20px;
                    }
                    p { 
                        color: #4a5568; 
                        font-size: 16px;
                        line-height: 1.6;
                    }
                    .profile {
                        margin-top: 40px;
                        padding-top: 30px;
                        border-top: 1px solid #e2e8f0;
                    }
                    .profile-name {
                        font-weight: bold;
                        font-size: 20px;
                        color: #2d3748;
                        margin-bottom: 5px;
                    }
                    .profile-title {
                        font-style: italic;
                        color: #4a5568;
                        margin-bottom: 15px;
                    }
                    .contact-info {
                        margin-top: 15px;
                        font-size: 14px;
                    }
                    .contact-item {
                        margin: 5px 0;
                    }
                    .social-links {
                        margin-top: 15px;
                    }
                    .social-link {
                        display: inline-block;
                        margin: 0 10px;
                        color: #3182ce;
                        text-decoration: none;
                        font-weight: 500;
                    }
                    .social-link:hover {
                        text-decoration: underline;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success">✅</div>
                    <h1>¡Confirmación Registrada!</h1>
                    <p>Gracias por confirmar tu correo electrónico.</p>
                    
                    <div class="profile">
                        <div class="profile-name">Julio A. Lazarte</div>
                        <div class="profile-title">Científico de Datos &amp; BI | Cucher Mercados</div>
                        
                        <div class="contact-info">
                          <div style="display: flex; align-items: center; gap: 8px;justify-content: center;">
                          <img src="https://raw.githubusercontent.com/JulioLaz/confirma_telegram/main/whatsapp_24.png" alt="WhatsApp Icon" width="24" height="24">

                           <span style="font-size: 16px;">+54 9 381 5260176</span>
                          </div>
                       </div>
                        
                        <div class="social-links">
                            <a href="#" class="social-link">Portfolio</a>
                            <a href="#" class="social-link">LinkedIn</a>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
        )
                        #    <img src="C:\JulioPrograma\BOT_TELEGRAM\BOT_TELEGRAM\whatsapp_24.png" alt="WhatsApp Icon" width="24" height="24">
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
            <title>Servicio de Confirmación | Julio Lazarte</title>
            <style>
                body { 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    text-align: center; 
                    margin: 0;
                    padding: 0;
                    background-color: #f0f2f5;
                    color: #333;
                }
                .header {
                    background-color: #2a4365;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }
                .container {
                    background-color: white;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    padding: 40px;
                    max-width: 700px;
                    margin: 30px auto;
                }
                h1 { 
                    color: #2a4365; 
                    margin-bottom: 20px;
                }
                p { 
                    color: #4a5568; 
                    font-size: 16px;
                    line-height: 1.6;
                    margin-bottom: 15px;
                }
                .status {
                    display: inline-block;
                    background-color: #28a745;
                    color: white;
                    padding: 5px 15px;
                    border-radius: 15px;
                    font-weight: bold;
                    margin-bottom: 20px;
                }
                code {
                    background-color: #f1f5f9;
                    padding: 3px 6px;
                    border-radius: 4px;
                    font-family: 'Courier New', monospace;
                    font-size: 14px;
                }
                .card {
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    padding: 20px;
                    margin-top: 30px;
                    background-color: #f8fafc;
                }
                .profile {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    margin-top: 40px;
                    padding-top: 30px;
                    border-top: 1px solid #e2e8f0;
                }
                .profile-name {
                    font-weight: bold;
                    font-size: 22px;
                    color: #2d3748;
                    margin-bottom: 5px;
                }
                .profile-title {
                    font-style: italic;
                    color: #4a5568;
                    margin-bottom: 15px;
                    font-size: 16px;
                }
                .contact-info {
                    margin-top: 15px;
                    font-size: 15px;
                }
                .contact-item {
                    margin: 8px 0;
                }
                .social-links {
                    margin-top: 20px;
                }
                .social-link {
                    display: inline-block;
                    margin: 0 10px;
                    color: #3182ce;
                    text-decoration: none;
                    padding: 8px 15px;
                    border: 1px solid #3182ce;
                    border-radius: 20px;
                    font-weight: 500;
                    transition: all 0.3s ease;
                }
                .social-link:hover {
                    background-color: #3182ce;
                    color: white;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h2>Sistema de Confirmación de Datos</h2>
            </div>
            <div class="container">
                <h1>Servidor de Confirmaciones</h1>
                <div class="status">Activo</div>
                <p>Este servicio procesa confirmaciones de correo electrónico de manera segura y eficiente.</p>
                
                <div class="card">
                    <p><strong>Uso del API:</strong></p>
                    <p>Para confirmar un correo electrónico, envíe una solicitud GET a:</p>
                    <code>/confirm?email=usuario@ejemplo.com</code>
                    <p>Parámetros opcionales:</p>
                    <code>/confirm?email=usuario@ejemplo.com&source=formulario</code>
                </div>
                
                <div class="profile">
                    <div class="profile-name">Julio A. Lazarte</div>
                    <div class="profile-title">Científico de Datos &amp; BI | Cucher Mercados</div>
                    
                    <div class="contact-info">
                        <div class="contact-item">📧 julioalbertolazarte00@gmail.com</div>
                        <div class="contact-item">📱 +54 9 381 5260176</div>
                    </div>
                    
                    <div class="social-links">
                        <a href="#" class="social-link">Portfolio</a>
                        <a href="#" class="social-link">LinkedIn</a>
                    </div>
                </div>
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


@app.route('/download')
@rate_limit
def track_download():
    archivo = request.args.get('archivo')
    usuario = request.args.get('user', 'Desconocido')

    # Mensaje oculto para Telegram
    mensaje = (
        f"📥 <b>Descarga registrada</b>\n"
        f"<b>Archivo:</b> {archivo}\n"
        f"<b>Usuario:</b> {usuario}\n"
        f"🕒 {time.strftime('%d-%b-%Y %H:%M')}"
    )
    TelegramNotifier.send_message(mensaje)

    # URLs reales de descarga desde Google Drive
    urls_descarga = {
        "presupuesto_general": "https://docs.google.com/spreadsheets/d/1HLQ23BEoa2fu5jsTAPr4qg8IVncbCG1o/export?format=xlsx",
        "por_proveedor": "https://docs.google.com/spreadsheets/d/1wpkmu7WK_1wxNMhwj7JcZGJ_z8a63oSm/export?format=xlsx",
        "nuevos_articulos": "https://docs.google.com/spreadsheets/d/1OFgxjmlURSp2gOeRJQUkHvhyPSR-fyol/export?format=xlsx",
        "alertas": "https://docs.google.com/spreadsheets/d/1bC8dW7BXl9fygM6WkW9PPgqtKtNfYcGW/export?format=xlsx"
    }

    # Redirigir al archivo correcto o a home si no existe
    return redirect(urls_descarga.get(archivo, "/"))

@app.route('/dashboard')
@rate_limit
def track_dashboard_access():
    usuario = request.args.get('user', 'Desconocido')

    mensaje = (
        f"📊 <b>Dashboard accedido</b>\n"
        f"<b>Usuario:</b> {usuario}\n"
        f"🕒 {time.strftime('%d-%b-%Y %H:%M')}"
    )
    TelegramNotifier.send_message(mensaje)

    # Redirigir al dashboard real (por ejemplo, Looker Studio)
    return redirect("https://lookerstudio.google.com/reporting/1a1abd1e-a896-49bd-b8d0-fdbde4135633")



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