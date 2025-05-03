from flask import Flask, request
import requests
import os

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

  # <-- reemplazá esto con tu token real
CHAT_ID = '8107106288'  # Tu chat_id personal
def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {'chat_id': CHAT_ID, 'text': mensaje}
    requests.post(url, data=data)

app = Flask(__name__)

@app.route('/confirm', methods=['GET'])
def confirm():
    email = request.args.get('email')
    if not email:
        return "❌ Falta el parámetro ?email=", 400

    enviar_telegram(f"📩 Confirmación recibida de: {email}")
    return "✅ Confirmación registrada. ¡Gracias!"

@app.route('/')
def home():
    return "Servidor de confirmaciones activo."

if __name__ == '__main__':
    app.run()
