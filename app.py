from flask import Flask, request, jsonify, send_from_directory, render_template
import logging
import os
from dotenv import load_dotenv
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
GRAPH_URL = "https://graph.instagram.com/v23.0" 

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/get_posts', methods=['GET'])
def get_user_posts():
    """Obtener publicaciones del usuario"""
    try:
        url = f"{GRAPH_URL}/{IG_USER_ID}/media"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': 20,
            'fields': 'id,caption,media_type,media_url,thumbnail_url,like_count,comments_count,timestamp'
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error de Instagram: {data['error']['message']}")
            return jsonify({"status": "error", "message": data['error']['message']}), 500

        posts = data.get('data', [])
        paginated_medias = posts[:5]  # Ejemplo simple, puedes mejorar con paginación real

        processed_posts = []
        for post in paginated_medias:
            media_id = post['id']
            thumbnail_url = post.get('thumbnail_url') or post.get('media_url')

            processed_posts.append({
                "id": media_id,
                "caption": post.get('caption', 'Sin descripción'),
                "thumbnail": thumbnail_url or "/static/images/placeholder.jpg",
                "like_count": post.get('like_count', 0),
                "comment_count": post.get('comments_count', 0)
            })

        return jsonify({
            "status": "success",
            "posts": processed_posts,
            "total": len(posts),
            "has_next": False
        })

    except Exception as e:
        logger.error(f"Error obteniendo posts: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/post/<post_id>', methods=['GET'])
def get_post_details(post_id):
    """Obtener detalles completos de un post"""
    try:
        url = f"{GRAPH_URL}/{post_id}"
        params = {
            'access_token': ACCESS_TOKEN,
            'fields': 'id,caption,like_count,comments_count,timestamp,thumbnail_url,media_url'
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error obteniendo detalle: {data['error']['message']}")
            return jsonify({"status": "error", "message": data['error']['message']}), 500

        return jsonify({
            "status": "success",
            "post": {
                "id": data['id'],
                "caption": data.get('caption', 'Sin descripción'),
                "thumbnail": data.get('thumbnail_url', '') or data.get('media_url', ''),
                "like_count": data.get('like_count', 0),
                "comment_count": data.get('comments_count', 0),
                "timestamp": data.get('timestamp', '')
            }
        })

    except Exception as e:
        logger.error(f"Error obteniendo detalle del post: {str(e)}")
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
                
            # 4. Enviar respuesta
            reply_url = f"{GRAPH_URL}/{comment_id}/replies"
            reply_data = {
                'message': response_text,
                'access_token': ACCESS_TOKEN
            }
            
            try:
                reply_response = requests.post(reply_url, data=reply_data, timeout=30)
                reply_result = reply_response.json()
                
                if 'error' in reply_result:
                    logger.error(f"Error respondiendo comentario: {reply_result['error']['message']}")
                    continue
                    
                # Registrar la respuesta
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
                
            except Exception as e:
                logger.error(f"Error al responder comentario {comment_id}: {str(e)}")
                continue
                
        # 5. Actualizar config con nuevos comentarios respondidos
        config['responded_comments'] = responded_comments
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        return jsonify({
            "status": "success",
            "message": f"Procesados {len(new_responses)} comentarios",
            "new_responses": new_responses
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
