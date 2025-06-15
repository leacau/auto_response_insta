from flask import Flask, request, jsonify, render_template, send_from_directory, Response
import os
import json
import logging
import time
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
from functools import lru_cache
from dotenv import load_dotenv
import hashlib
import hmac
import random


# Cargar variables de entorno
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes
CONFIG_FILE = "config.json"
IMAGE_CACHE_DIR = 'static/cached_images'
MAX_WORKERS = 4
REQUEST_TIMEOUT = 30
DELAY_ENTRE_RESPUESTAS = 5

# Credenciales desde .env
load_dotenv()
ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')
IG_USER_ID = os.getenv('INSTAGRAM_USER_ID')
MAX_POSTS = int(os.getenv('MAX_POSTS'))

if not ACCESS_TOKEN or not IG_USER_ID:
    raise ValueError("Faltan INSTAGRAM_ACCESS_TOKEN o INSTAGRAM_USER_ID en .env")

GRAPH_URL = "https://graph.instagram.com/v23.0" 

os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "keywords": {},
            "default_response": "¡Gracias por tu comentario!",
            "responded_comments": {}
        }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/get_posts', methods=['GET'])
def get_user_posts():
    """Obtener publicaciones del usuario con miniaturas correctas"""
    try:
        page = int(request.args.get('page', 1))
        per_page = 5
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page

        # Obtener lista de posts
        url = f"{GRAPH_URL}/{IG_USER_ID}/media"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': MAX_POSTS,
            'fields': 'id,caption,media_type,media_url,thumbnail_url,like_count,comments_count,timestamp'
        }
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error de Instagram: {data['error']['message']}")
            return jsonify({
                "status": "error",
                "message": data['error']['message']
            }), 500

        posts = data.get('data', [])
        total_posts = len(posts)
        paginated_medias = posts[start_idx:end_idx]

        processed_posts = []
        for post in paginated_medias:
            media_id = post['id']
            caption = post.get('caption', 'Sin descripción')[:80] + ("..." if len(post.get('caption', '')) > 80 else "")
            media_type = post.get('media_type', 'UNKNOWN')
            like_count = post.get('like_count', 0)
            comment_count = post.get('comments_count', 0)
         

            # Si es IMAGE y no tiene thumbnail_url, usar media_url si existe
            thumbnail_url = post.get('thumbnail_url')
            if not thumbnail_url:
                thumbnail_url = post.get('media_url')

            # Descargar y cachear si es necesario
            cached_thumbnail = download_and_cache_image(thumbnail_url, media_id)

            processed_posts.append({
                "id": media_id,
                "caption": caption,
                "media_type": media_type,
                "like_count": like_count,
                "comment_count": comment_count,
                "thumbnail": cached_thumbnail or "/static/images/placeholder.jpg"
            })

        return jsonify({
            "status": "success",
            "posts": processed_posts,
            "total": total_posts,
            "page": page,
            "per_page": per_page,
            "has_next": end_idx < total_posts
        })

    except Exception as e:
        logger.error(f"Error obteniendo posts: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/post/<post_id>', methods=['GET'])
def get_post_details(post_id):
    """Obtener detalles completos de un post específico"""
    try:
        url = f"{GRAPH_URL}/{post_id}"
        params = {
            'access_token': ACCESS_TOKEN,
            'fields': 'id,caption,like_count,comments_count,timestamp,media_type,thumbnail_url,media_url,children{media_url}'
        }
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error obteniendo detalle: {data['error']['message']}")
            return jsonify({
                "status": "error",
                "message": data['error']['message']
            }), 500

        media_type = data.get('media_type', 'UNKNOWN')
        caption = data.get('caption', 'Sin descripción')
        like_count = data.get('like_count', 0)
        comment_count = data.get('comments_count', 0)
        timestamp = data.get('timestamp', '')

        # Obtener URL correcta
        media_url = data.get('media_url', '')
        thumbnail_url = data.get('thumbnail_url', '')

        # Si es CAROUSEL, obtener la primera imagen
        if media_type == 'CAROUSEL_ALBUM':
            children = data.get('children', {}).get('data', [])
            if children and len(children) > 0:
                first_child = children[0]
                media_url = first_child.get('media_url', '')
                thumbnail_url = first_child.get('media_url', '') or thumbnail_url

        elif media_type == 'IMAGE':
            thumbnail_url = media_url  # Fallback

        return jsonify({
            "status": "success",
            "post": {
                "id": data['id'],
                "caption": caption,
                "media_type": media_type,
                "url": media_url,
                "thumbnail": thumbnail_url or "/static/images/placeholder.jpg",
                "like_count": like_count,
                "comment_count": comment_count,
                "timestamp": timestamp
            }
        })

    except Exception as e:
        logger.error(f"Error obteniendo detalle del post: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    

def download_and_cache_image(image_url: str, post_id: str) -> str:
    """Descargar y cachear imágenes localmente"""
    if not image_url:
        return "/static/images/placeholder.jpg"

    filename = secure_filename(f"ig_{post_id}.jpg")
    filepath = os.path.join(IMAGE_CACHE_DIR, filename)

    # Si ya está cacheada, devolverla
    if os.path.exists(filepath):
        return f"/{filepath}"

    try:
        response = requests.get(
            image_url,
            headers={'User-Agent': 'Mozilla/5.0'},
            stream=True,
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return f"/{filepath}"
        else:
            logger.warning(f"No se pudo descargar la miniatura de {image_url}")
            return "/static/images/placeholder.jpg"
    except Exception as e:
        logger.error(f"Error descargando imagen: {str(e)}")
        return "/static/images/placeholder.jpg"

@app.route('/api/save_keyword', methods=['POST'])
def save_keyword_for_post():
    """Guardar palabra clave para un post específico"""
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        config = data.get('config')

        # Simulamos guardar por post
        # Puedes mejorar esto usando un archivo por post si lo necesitas
        with open(f"config_{post_id}.json", 'w') as f:
            json.dump(config, f, indent=2)
        
        return jsonify({
            "status": "success",
            "message": "Palabra clave guardada correctamente"
        })

    except Exception as e:
        logger.error(f"Error guardando palabra clave: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    

# Ruta para servir miniaturas caché
@app.route('/cached_images/<filename>')
def serve_cached_image(filename):
    return send_from_directory(IMAGE_CACHE_DIR, filename)

@app.route('/webhook', methods=['GET', 'POST'])
def handle_webhook():
    if request.method == 'GET':
        # Verificación de webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode == 'subscribe' and token == os.getenv('WEBHOOK_VERIFY_TOKEN'):
            return Response(challenge, mimetype='text/plain')
        else:
            return jsonify({"status": "error", "message": "Verificación fallida"}), 403

    elif request.method == 'POST':
        data = request.json
        logger.info("Webhook recibido:", data)
        return jsonify({"status": "ok"}), 200


def respond_to_comment(comment_text, post_id, user):
    """Responder a comentario basado en palabras clave o respuesta predeterminada"""
    config = load_config()  # Carga configuración global (default_response, keywords)
    matched = False

    # Buscar coincidencias con palabras clave
    for keyword, responses in config.get('keywords', {}).items():
        if keyword.lower() in comment_text:
            reply_text = random.choice(responses) if isinstance(responses, list) and responses else responses[0]
            send_instagram_comment(post_id, reply_text)
            log_activity(comment_text, post_id, reply_text, user, matched=True)
            matched = True
            break

    # Si no hay palabra clave, usar respuesta predeterminada
    if not matched:
        default_response = config.get('default_response', '')
        if default_response:
            send_instagram_comment(post_id, default_response)
            log_activity(comment_text, post_id, default_response, user, matched=False)
def send_instagram_comment(media_id, message):
    """Enviar comentario a través de Graph API"""
    url = f"{GRAPH_URL}/{media_id}/comments"
    payload = {
        'message': message,
        'access_token': ACCESS_TOKEN
    }
    try:
        response = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            logger.warning(f"No se pudo enviar el comentario: {response.text}")
        return response.json()
    except Exception as e:
        logger.error(f"Error enviando comentario: {str(e)}")
        return None

def log_activity(comment_text, post_id, reply_text, user, matched=True):
    """Registrar historial de comentarios respondidos"""
    config = load_config()
    timestamp = datetime.now().isoformat()

    config['responded_comments'][f"{post_id}_{timestamp}"] = {
        "usuario": user.get('username', 'Anónimo'),
        "comentario": comment_text,
        "respuesta": reply_text,
        "fecha": timestamp,
        "matched": matched
    }

    save_config(config)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
