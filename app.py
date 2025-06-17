from flask import Flask, request, jsonify, send_from_directory, render_template
import logging
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
load_dotenv()
import json
import logging
import time
import requests
from datetime import datetime
import random
from glob import glob
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes
ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')
IG_USER_ID = os.getenv('INSTAGRAM_USER_ID')
MAX_POSTS = int(os.getenv('MAX_POSTS', 100))  # Máximo de posts a obtener
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))  # Timeout para las solicitudes a la API
GRAPH_URL = "https://graph.instagram.com/v23.0" 
IMAGE_CACHE_DIR = 'static/cached_images'

@app.route('/politica_de_privacidad')
def privacy_policy():
    """Redirige a la pantalla de política de privacidad"""
    return render_template('index.html')  # La lógica de redirección se manejará en el frontend


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/get_posts', methods=['GET'])
def get_user_posts():
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
            thumbnail_url = post.get('thumbnail_url')
            if not thumbnail_url and media_type == "IMAGE":
                thumbnail_url = post.get('media_url')

            cached_thumbnail = download_and_cache_image(thumbnail_url, media_id)
            processed_posts.append({
                "id": media_id,
                "caption": caption,
                "media_type": media_type,
                "like_count": like_count,
                "comment_count": comment_count,
                "thumbnail": cached_thumbnail or "/static/images/placeholder.jpg"
            })

        logger.info(f"Processed posts: {processed_posts}")  # Debugging
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
@app.route('/api/post/<post_id>', methods=['GET'])
def get_post_details(post_id):
    """Obtener detalles completos de un post"""
    try:
        # Primero obtener los datos básicos del post
        url = f"{GRAPH_URL}/{post_id}"
        params = {
            'access_token': ACCESS_TOKEN,
            'fields': 'id,caption,media_type,media_url,thumbnail_url,like_count,comments_count,timestamp'
        }
        response = requests.get(url, params=params, timeout=30)
        post_data = response.json()

        if 'error' in post_data:
            logger.error(f"Error obteniendo detalle del post: {post_data['error']['message']}")
            return jsonify({"status": "error", "message": post_data['error']['message']}), 500

        # Formatear la respuesta
        result = {
            "status": "success",
            "post": {
                "id": post_data.get('id'),
                "caption": post_data.get('caption', 'Sin descripción'),
                "thumbnail": post_data.get('thumbnail_url') or post_data.get('media_url', ''),
                "like_count": post_data.get('like_count', 0),
                "comment_count": post_data.get('comments_count', 0),
                "timestamp": post_data.get('timestamp', '')
            }
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error obteniendo detalle del post: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/post/<post_id>/comments', methods=['GET'])
def get_post_comments(post_id):
    """Obtener comentarios de un post específico"""
    try:
        # Obtener comentarios de la API de Instagram
        comments_url = f"{GRAPH_URL}/{post_id}/comments"
        params = {
            'access_token': ACCESS_TOKEN,
            'fields': 'id,text,username,timestamp'
        }
        response = requests.get(comments_url, params=params, timeout=30)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error obteniendo comentarios: {data['error']['message']}")
            return jsonify({"status": "error", "message": data['error']['message']}), 500

        # También obtener comentarios respondidos del archivo de configuración
        config_path = f"config_{post_id}.json"
        responded_comments = {}
        try:
            with open(config_path) as f:
                config = json.load(f)
                responded_comments = config.get('responded_comments', {})
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Procesar comentarios
        comments = []
        for comment in data.get('data', []):
            comment_id = comment['id']
            comment_key = f"{post_id}_{comment_id}"
            
            comments.append({
                'id': comment_id,
                'username': comment.get('username', 'Anónimo'),
                'text': comment.get('text', ''),
                'timestamp': comment.get('timestamp', ''),
                'responded': comment_key in responded_comments
            })

        return jsonify({
            "status": "success",
            "comments": comments
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo comentarios del post: {str(e)}")
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


@app.route('/api/list_rules', methods=['GET'])
def list_all_rules():
    """Mostrar todas las reglas guardadas"""
    try:
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

@app.route('/cached_images/<filename>')
def serve_cached_image(filename):
    return send_from_directory('static/cached_images', filename)

@app.route('/api/get_history', methods=['GET'])
def get_history():
    """Obtener historial de todos los comentarios respondidos"""
    try:
        rule_files = glob("config_*.json")
        all_history = {}
        
        for file in rule_files:
            with open(file) as f:
                config = json.load(f)
                if 'responded_comments' in config:
                    all_history.update(config['responded_comments'])
                    
        return jsonify({
            "status": "success",
            "history": all_history
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo historial: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/process_comments', methods=['POST'])
def process_comments():
    """Revisar comentarios nuevos y responder según las reglas"""
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        
        if not post_id:
            return jsonify({"status": "error", "message": "Se requiere post_id"}), 400

        # 1. Obtener comentarios del post
        comments_url = f"{GRAPH_URL}/{post_id}/comments"
        params = {
            'access_token': ACCESS_TOKEN,
            'fields': 'id,text,username,timestamp'
        }
        response = requests.get(comments_url, params=params, timeout=30)
        comments_data = response.json()

        if 'error' in comments_data:
            logger.error(f"Error obteniendo comentarios: {comments_data['error']['message']}")
            return jsonify({"status": "error", "message": comments_data['error']['message']}), 500

        # 2. Cargar reglas para este post
        config_path = f"config_{post_id}.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {"keywords": {}, "default_response": "Gracias por tu comentario"}

        # 3. Procesar cada comentario
        responded_comments = config.get('responded_comments', {})
        new_responses = []
        
        for comment in comments_data.get('data', []):
            comment_id = comment['id']
            comment_key = f"{post_id}_{comment_id}"
            
            # Saltar si ya respondimos a este comentario
            if comment_key in responded_comments:
                continue
                
            comment_text = comment['text'].lower()
            username = comment['username']
            timestamp = comment['timestamp']
            
            # Buscar coincidencias con palabras clave
            response_text = None
            matched_keyword = None
            
            for keyword, responses in config['keywords'].items():
                if keyword.lower() in comment_text:
                    matched_keyword = keyword
                    response_text = random.choice(responses)
                    break
                    
            # Si no hay coincidencia, usar respuesta por defecto
            if not response_text:
                response_text = config['default_response']
                matched = False
            else:
                matched = True
                
            # 4. Enviar respuesta (simulado para pruebas)
            # En producción, descomenta esto:
            
            reply_url = f"{GRAPH_URL}/{comment_id}/replies"
            reply_data = {
                'message': response_text,
                'access_token': ACCESS_TOKEN
            }
            
            reply_response = requests.post(reply_url, data=reply_data, timeout=30)
            reply_result = reply_response.json()
            
            if 'error' in reply_result:
                logger.error(f"Error respondiendo comentario: {reply_result['error']['message']}")
                continue
            logger.info(f"Respuesta enviada a {username}: {response_text}")
            
            # Registrar la respuesta (incluso en modo simulado)
            responded_comments[comment_key] = {
                'usuario': username,
                'comentario': comment['text'],
                'respuesta': response_text,
                'fecha': timestamp,
                'matched': matched
            }
            
            new_responses.append({
                'comment_id': comment_id,
                'response': response_text,
                'matched_keyword': matched_keyword
            })
            
            # Esperar para no exceder límites de la API
            time.sleep(int(os.getenv('DELAY_ENTRE_RESPUESTAS', 5)))
                
        # 5. Actualizar config con nuevos comentarios respondidos
        config['responded_comments'] = responded_comments
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        return jsonify({
            "status": "success",
            "message": f"Procesados {len(new_responses)} comentarios",
            "new_responses": new_responses,
            'test_comments': comments_data.get('data', [])  # Para depuración
        })
        
    except Exception as e:
        logger.error(f"Error en process_comments: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
def auto_process_comments():
    """Tarea programada para procesar comentarios automáticamente"""
    with app.app_context():
        try:
            # Obtener posts con reglas configuradas
            rule_files = glob("config_*.json")
            for file in rule_files:
                post_id = file.replace('config_', '').replace('.json', '')
                # Llamar al endpoint para procesar comentarios
                with app.test_client() as client:
                    client.post('/api/process_comments', 
                              json={'post_id': post_id},
                              headers={'Content-Type': 'application/json'})
                    
        except Exception as e:
            logger.error(f"Error en auto_process_comments: {str(e)}")

if os.getenv('AUTO_PROCESS_ENABLED', 'false').lower() == 'true':
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_process_comments, 'interval', minutes=20)
    scheduler.start()
    logger.info("Programador de procesamiento automático iniciado")

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
