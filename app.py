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
logging.basicConfig(level=logging.INFO)

# Credenciales desde .env
load_dotenv()
ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')
IG_USER_ID = os.getenv('INSTAGRAM_USER_ID')
MAX_POSTS = int(os.getenv('MAX_POSTS'))

if not ACCESS_TOKEN or not IG_USER_ID:
    raise ValueError("Faltan INSTAGRAM_ACCESS_TOKEN o INSTAGRAM_USER_ID en .env")

GRAPH_URL = "https://graph.instagram.com/v23.0" 

os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

def load_config_for_post(post_id):
    """Cargar configuración específica por post"""
    config_path = f"config_{post_id}.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "keywords": {},
            "default_response": "Gracias por tu comentario",
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
    """Manejar eventos de webhook desde Meta"""
    if request.method == 'GET':
        # Verificación inicial del webhook
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode and token == os.getenv('WEBHOOK_VERIFY_TOKEN'):
            return Response(challenge, mimetype='text/plain')
        else:
            return jsonify({"status": "error", "message": "Verificación fallida"}), 403

    elif request.method == 'POST':
        data = request.json
        logger.info("Webhook recibido:", data)

        try:
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    comment_text = value.get('text', '').lower()
                    post_id = value.get('media_id', '') or value.get('post_id', '')
                    user = value.get('from', {})

                    if comment_text and post_id:
                        respond_to_comment(comment_text, post_id, user)

            return jsonify({"status": "success", "message": "Evento procesado"})
        except Exception as e:
            logger.error(f"Error procesando webhook: {str(e)}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500


def respond_to_comment(comment_text, post_id, user):
    config = load_config_for_post(post_id)
    matched = False

    # Buscar coincidencias con palabras clave
    for keyword, responses in config.get('keywords', {}).items():
        if keyword.lower() in comment_text:
            reply_text = random.choice(responses) if isinstance(responses, list) and len(responses) > 0 else responses[0]
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

    time.sleep(DELAY_ENTRE_RESPUESTAS)

def send_instagram_comment(media_id, message):
    """Enviar comentario vía Graph API"""
    url = f"{GRAPH_URL}/{media_id}/comments"
    payload = {
        'message': message,
        'access_token': ACCESS_TOKEN
    }
    response = requests.post(url, data=payload, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        logger.warning(f"No se pudo enviar el comentario: {response.text}")
    return response.json()

def log_activity(comment_text, media_id, reply_text, user, matched=True):
    """Registrar actividad en historial global"""
    config_path = "config.json"

    try:
        with open(config_path) as f:
            main_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        main_config = {
            "responded_comments": {}
        }

    timestamp = datetime.now().isoformat()
    comment_id = f"{media_id}_{timestamp}"

    main_config['responded_comments'][comment_id] = {
        "usuario": user.get('username', 'Anónimo'),
        "comentario": comment_text,
        "respuesta": reply_text,
        "fecha": timestamp,
        "matched": matched
    }

    with open(config_path, 'w') as f:
        json.dump(main_config, f, indent=2)

@app.route('/api/list_rules', methods=['GET'])
def list_all_rules():
    """Mostrar todas las reglas guardadas"""
    try:
        from glob import glob
        import os

        rule_files = glob("config_*.json")
        rules = []

        for file in rule_files:
            with open(file) as f:
                config = json.load(f)
                post_id = config.get('post_id', file.replace('config_', '').replace('.json', ''))
                rules.append({
                    "post_id": post_id,
                    "keywords": config.get('keywords', {}),
                    "file": file
                })

        return jsonify({"status": "success", "rules": rules})
    except Exception as e:
        logger.error(f"Error listando reglas: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/add_rule', methods=['POST'])
def add_new_keyword_rule():
    """Agregar una palabra clave nueva a un post específico"""
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        keyword = data.get('keyword')
        responses = data.get('responses')

        if not post_id or not keyword or not responses:
            return jsonify({"status": "error", "message": "Faltan datos"}), 400

        config_path = f"config_{post_id}.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {"keywords": {}, "default_response": "Gracias por tu comentario"}

        response_list = [r.strip() for r in responses.split(",") if r.strip()]
        if len(response_list) > 7:
            return jsonify({"status": "error", "message": "Máximo 7 respuestas por palabra clave"}), 400

        config["keywords"][keyword] = response_list

        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return jsonify({"status": "success", "message": "Regla agregada correctamente"})
    except Exception as e:
        logger.error(f"Error al agregar regla: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/delete_rule', methods=['POST'])
def delete_keyword_rule():
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        keyword = data.get('keyword')

        if not post_id or not keyword:
            return jsonify({"status": "error", "message": "Datos incompletos"}), 400

        config_path = f"config_{post_id}.json"

        if not os.path.exists(config_path):
            return jsonify({"status": "error", "message": "Archivo no encontrado"}), 404

        with open(config_path) as f:
            config = json.load(f)

        if keyword in config.get('keywords', {}):
            del config['keywords'][keyword]

        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return jsonify({"status": "success", "message": "Regla eliminada"})
    except Exception as e:
        logger.error(f"Error borrando regla: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))