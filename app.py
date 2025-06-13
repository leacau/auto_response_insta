from flask import Flask, request, jsonify, render_template
import os
import json
import logging
import time
import random
from datetime import datetime
from functools import lru_cache
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes
CONFIG_FILE = "config.json"
IMAGE_CACHE_DIR = 'static/cached_images'
MAX_WORKERS = 4
REQUEST_TIMEOUT = 30
DELAY_ENTRE_RESPUESTAS = int(os.getenv('DELAY_ENTRE_RESPUESTAS', 5))
MAX_POSTS = int(os.getenv('MAX_POSTS', 20))

# Credenciales desde .env
ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')
IG_USER_ID = os.getenv('INSTAGRAM_USER_ID')

GRAPH_URL = "https://graph.instagram.com/v23.0" 

os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

def load_config():
    """Cargar configuración desde config.json"""
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "keywords": {},
            "default_response": "Gracias por tu comentario",
            "responded_comments": {}
        }

def save_config(config):
    """Guardar configuración localmente"""
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

        url = f"{GRAPH_URL}/{IG_USER_ID}/media"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': MAX_POSTS,
            'fields': 'id,caption,media_type,media_url,thumbnail_url,like_count,comments_count,timestamp'
        }
        response = requests.get(url, params=params, timeout=30)
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
            thumbnail_url = post.get('thumbnail_url', post.get('media_url', '/static/images/placeholder.jpg'))

            processed_posts.append({
                "id": media_id,
                "caption": caption,
                "like_count": post.get('like_count', 0),
                "comment_count": post.get('comments_count', 0),
                "thumbnail": thumbnail_url
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
            'fields': 'id,caption,like_count,comments_count,timestamp,media_type,thumbnail_url,media_url'
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error al obtener detalle: {data['error']['message']}")
            return jsonify({
                "status": "error",
                "message": data['error']['message']
            }), 500

        media_type = data.get('media_type', 'UNKNOWN')
        media_url = data.get('media_url', '')
        thumbnail_url = data.get('thumbnail_url', '')

        if media_type == "IMAGE" and not thumbnail_url:
            thumbnail_url = media_url

        return jsonify({
            "status": "success",
            "post": {
                "id": data['id'],
                "caption": data.get('caption', 'Sin descripción'),
                "media_type": media_type,
                "url": media_url or "/static/images/placeholder.jpg",
                "thumbnail": thumbnail_url or "/static/images/placeholder.jpg",
                "like_count": data.get('like_count', 0),
                "comment_count": data.get('comments_count', 0),
                "timestamp": data.get('timestamp', '')
            }
        })
    except Exception as e:
        logger.error(f"Error obteniendo detalle del post: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/webhook', methods=['GET', 'POST'])
def handle_webhook():
    """Manejar eventos de webhook"""
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
        # Recibir evento de comentario
        data = request.get_json()
        logger.info("Webhook recibido:", data)

        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [])
        
        for change in changes:
            value = change.get('value', {})
            comment = value.get('comment', {})
            post_id = value.get('media_id', '') or value.get('post_id', '')
            user = value.get('from', {})

            if comment.get('text') and post_id:
                respond_to_comment(comment, post_id, user)

        return jsonify({"status": "ok"}), 200

def respond_to_comment(comment, post_id, user):
    """Responder a un comentario usando reglas por palabra clave"""
    config = load_config()
    text = comment['text'].lower()
    matched = False

    for keyword, responses in config.get('keywords', {}).items():
        if keyword.lower() in text:
            reply_text = random.choice(responses) if isinstance(responses, list) and responses else responses[0]
            send_instagram_comment(post_id, reply_text)
            log_activity(comment, reply_text, user, post_id)
            matched = True
            break

    if not matched and config.get('default_response'):
        reply_text = config['default_response']
        send_instagram_comment(post_id, reply_text)
        log_activity(comment, reply_text, user, post_id)

def send_instagram_comment(media_id, message):
    """Enviar respuesta vía Graph API"""
    url = f"{GRAPH_URL}/{media_id}/comments"
    payload = {
        'message': message,
        'access_token': ACCESS_TOKEN
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        logger.warning(f"No se pudo enviar el comentario: {response.text}")
    return response.json()

def log_activity(comment, reply, user, post_id):
    """Registrar actividad en historial"""
    config = load_config()
    timestamp = datetime.now().isoformat()
    comment_id = comment.get('id', 'anonimo')
    
    config['responded_comments'][comment_id] = {
        "usuario": user.get('username', 'Anónimo'),
        "comentario": comment.get('text', ''),
        "respuesta": reply,
        "fecha": timestamp
    }
    save_config(config)

@app.route('/api/save_keyword', methods=['POST'])
def save_keyword_for_post():
    """Guardar palabra clave para un post específico"""
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        config = data.get('config')

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)