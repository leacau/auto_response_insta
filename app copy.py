from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import json
import logging
import time
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
from functools import lru_cache
from dotenv import load_dotenv


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

        # Obtener URL correcta según tipo de contenido
        media_url = data.get('media_url', '')
        thumbnail_url = data.get('thumbnail_url', '')

        # Si es un álbum de imágenes, obtener la primera imagen
        if media_type == 'CAROUSEL_ALBUM':
            children = data.get('children', {}).get('data', [])
            if children and len(children) > 0:
                first_child = children[0]
                media_url = first_child.get('media_url', '')
                thumbnail_url = first_child.get('media_url', '') or thumbnail_url

        elif media_type == 'IMAGE':
            thumbnail_url = media_url  # Para IMAGE, usar media_url como fallback

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)