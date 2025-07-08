from flask import Flask, request, jsonify, render_template, Response
import os
import json
import logging
import time
import requests
from datetime import datetime
import random
from glob import glob
import firebase_admin
from firebase_admin import credentials, db

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables desde .env
from dotenv import load_dotenv
load_dotenv()

# Constantes
ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')
IG_USER_ID = os.getenv('INSTAGRAM_USER_ID')
WEBHOOK_VERIFY_TOKEN = os.getenv('WEBHOOK_VERIFY_TOKEN', 'politics_privacy_token')
GRAPH_URL = "https://graph.instagram.com/v23.0" 
CONFIG_DIR = "config_posts"
HISTORY_FILE = "config_global.json"

# Inicializar Firebase solo si no está ya inicializado
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("firebase_credentials.json")
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://leandrochena---sitio-oficial-default-rtdb.firebaseio.com/' 
        })
    except Exception as e:
        logger.error(f"No se pudo conectar a Firebase: {str(e)}")

os.makedirs(CONFIG_DIR, exist_ok=True)

def get_config_path(post_id):
    return os.path.join(CONFIG_DIR, f"config_{post_id}.json")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/webhook', methods=['GET', 'POST'])
def handle_webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode and token == WEBHOOK_VERIFY_TOKEN:
            logger.info("Webhook verificado")
            return Response(challenge, mimetype='text/plain'), 200
        else:
            logger.warning("Verificación de webhook fallida")
            return jsonify({"status": "error", "message": "Verificación fallida"}), 403

    elif request.method == 'POST':
        data = request.json
        logger.info("Evento recibido: %s", data)

        try:
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    comment_text = value.get('text', '').lower()
                    post_id = value.get('media_id', '') or value.get('post_id', '')
                    from_user = value.get('from', {})  # Aquí se define from_user

                    if not post_id or not comment_text:
                        continue

                    config = load_config_for_post(post_id)
                    matched = False

                    # Buscar coincidencias con palabras clave
                    for keyword, responses in config.get('keywords', {}).items():
                        if keyword.lower() in comment_text:
                            reply_text = random.choice(responses) if isinstance(responses, list) and len(responses) > 0 else responses[0]
                            send_instagram_comment(post_id, reply_text)
                            log_activity(comment_text, post_id, reply_text, from_user=from_user, matched=True)
                            matched = True
                            break

                    # Si no hay match, usar respuesta predeterminada
                    if not matched:
                        default_response = config.get('default_response', '')
                        if default_response:
                            send_instagram_comment(post_id, default_response)
                            log_activity(comment_text, post_id, default_response, from_user=from_user, matched=False)

            return jsonify({"status": "success", "message": "Evento procesado"}), 200

        except Exception as e:
            logger.error(f"Error procesando evento: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500


def load_config_for_post(post_id):
    """Carga configuración específica para un post desde Firebase o archivo local"""
    try:
        ref = db.reference(f'posts/{post_id}')
        config = ref.get()
    except Exception as e:
        logger.error(f"Error cargando configuración desde Firebase: {str(e)}")
        config = None

    if config is None:
        # Intentar cargar desde archivo local
        try:
            with open(get_config_path(post_id)) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as ex:
            logger.error(f"Error leyendo configuración local: {ex}")
            config = {
                "keywords": {},
                "default_response": "Gracias por tu comentario 😊",
                "enabled": False,
            }

    if "enabled" not in config:
        config["enabled"] = False
    return config


def save_config_for_post(post_id, config):
    """Guarda configuración por post en Firebase, con fallback local"""
    success = False
    try:
        ref = db.reference(f'posts/{post_id}')
        ref.set(config)
        success = True
    except Exception as e:
        logger.error(f"Error guardando en Firebase: {str(e)}")

    if not success:
        try:
            with open(get_config_path(post_id), 'w') as f:
                json.dump(config, f, indent=2)
            success = True
        except Exception as ex:
            logger.error(f"Error guardando configuración local: {ex}")
    return success


def send_instagram_comment(media_id, message):
    """Enviar comentario vía Graph API"""
    url = f"{GRAPH_URL}/{media_id}/comments"
    payload = {
        'message': message,
        'access_token': ACCESS_TOKEN
    }
    response = requests.post(url, data=payload, timeout=30)
    return response.json()


def log_activity(comment_text, media_id, reply_text, from_user, matched=True):
    """Registrar actividad globalmente"""
    try:
        with open(HISTORY_FILE) as f:
            main_config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        main_config = {"responded_comments": {}}

    timestamp = datetime.now().isoformat()
    comment_id = f"{media_id}_{timestamp}"

    main_config['responded_comments'][comment_id] = {
        "usuario": from_user.get('username', 'anonimo'),
        "comentario": comment_text,
        "respuesta": reply_text,
        "fecha": timestamp,
        "matched": matched
    }

    with open(HISTORY_FILE, 'w') as f:
        json.dump(main_config, f, indent=2)


@app.route('/api/get_posts', methods=['GET'])
def get_user_posts():
    try:
        page = int(request.args.get('page', 1))
        per_page = 8
        start_idx = (page - 1) * per_page

        url = f"{GRAPH_URL}/{IG_USER_ID}/media"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': 50,
            'fields': 'id,caption,like_count,comments_count,timestamp,thumbnail_url,media_url'
        }

        posts = []
        while url:
            response = requests.get(url, params=params if params else {}, timeout=30)
            data = response.json()

            if 'error' in data:
                logger.error(f"Error obteniendo posts: {data['error']['message']}")
                return jsonify({"status": "error", "message": data['error']['message']}), 500

            posts.extend(data.get('data', []))
            url = data.get('paging', {}).get('next')
            params = None

        total = len(posts)
        paginated = posts[start_idx:start_idx + per_page]

        processed = []
        for post in paginated:
            processed.append({
                "id": post['id'],
                "caption": post.get('caption', 'Sin descripción'),
                "like_count": post.get('like_count', 0),
                "comment_count": post.get('comments_count', 0),
                "thumbnail": post.get('thumbnail_url', post.get('media_url', '/static/images/placeholder.jpg')),
                "timestamp": post.get('timestamp', '')
            })

        return jsonify({
            "status": "success",
            "posts": processed,
            "total": total,
            "has_next": start_idx + per_page < total
        })

    except Exception as e:
        logger.error(f"Error obteniendo posts: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/post/<post_id>', methods=['GET'])
def get_post_details(post_id):
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

        config = load_config_for_post(post_id)

        return jsonify({
            "status": "success",
            "post": {
                "id": data['id'],
                "caption": data.get('caption', 'Sin descripción'),
                "like_count": data.get('like_count', 0),
                "comment_count": data.get('comments_count', 0),
                "timestamp": data.get('timestamp', ''),
                "thumbnail": data.get('thumbnail_url', data.get('media_url', '/static/images/placeholder.jpg')),
                "enabled": config.get('enabled', False)
            }
        })

    except Exception as e:
        logger.error(f"Error obteniendo detalles del post: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/comments/<post_id>', methods=['GET'])
def get_post_comments(post_id):
    try:
        url = f"{GRAPH_URL}/{post_id}/comments"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': 100,
            'fields': 'text,from{username},timestamp'
        }

        comments = []
        while url:
            response = requests.get(url, params=params if params else {}, timeout=30)
            data = response.json()

            if 'error' in data:
                logger.error(f"Error obteniendo comentarios: {data['error']['message']}")
                return jsonify({"status": "error", "message": data['error']['message']}), 500

            for c in data.get('data', []):
                user = c.get('from', {}) or {}
                comments.append({
                    "id": c.get('id', ''),
                    "text": c.get('text', 'Comentario no disponible'),
                    "username": user.get('username', 'usuario_anonimo'),
                    "timestamp": c.get('timestamp', '')
                })

            url = data.get('paging', {}).get('next')
            params = None

        total = len(comments)

        return jsonify({
            "status": "success",
            "comments": comments,
            "total": total
        })

    except Exception as e:
        logger.error(f"Error obteniendo comentarios: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/add_rule', methods=['POST'])
def add_new_keyword_rule():
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        keyword = data.get('keyword')
        responses = data.get('responses')

        if not post_id or not keyword or not responses:
            return jsonify({"status": "error", "message": "Faltan datos"}), 400

        # Cargar configuración actual (Firebase o local)
        config = load_config_for_post(post_id)

        # Procesar respuestas
        if isinstance(responses, list):
            response_list = [r.strip() for r in responses if r.strip()]
        elif isinstance(responses, str):
            response_list = [r.strip() for r in responses.split(',') if r.strip()]
        else:
            return jsonify({"status": "error", "message": "Formato de respuesta inválido"}), 400

        if len(response_list) > 7:
            return jsonify({"status": "error", "message": "Máximo 7 respuestas por palabra clave"}), 400

        # Actualizar configuración
        config.setdefault("keywords", {})[keyword] = response_list
        if save_config_for_post(post_id, config):
            return jsonify({"status": "success", "message": "Regla agregada correctamente"})
        return jsonify({"status": "error", "message": "No se pudo guardar"}), 500
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

        config = load_config_for_post(post_id)
        if keyword in config.get("keywords", {}):
            del config["keywords"][keyword]
            if save_config_for_post(post_id, config):
                return jsonify({"status": "success", "message": "Palabra clave eliminada"})
            return jsonify({"status": "error", "message": "No se pudo guardar"}), 500
        return jsonify({"status": "error", "message": "Palabra clave no encontrada"}), 404
    except Exception as e:
        logger.error(f"Error borrando regla: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/set_auto', methods=['POST'])
def set_auto_reply():
    """Activar o desactivar respuestas automáticas para un post"""
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        enabled = data.get('enabled')
        if post_id is None or enabled is None:
            return jsonify({"status": "error", "message": "Faltan datos"}), 400
        success = False
        try:
            ref = db.reference(f'posts/{post_id}')
            current = ref.get() or {}
            ref.update({"enabled": bool(enabled)})
            success = True
        except Exception as e:
            logger.error(f"Error actualizando en Firebase: {str(e)}")

        if not success:
            try:
                path = get_config_path(post_id)
                config = load_config_for_post(post_id)
                config["enabled"] = bool(enabled)
                with open(path, 'w') as f:
                    json.dump(config, f, indent=2)
                success = True
            except Exception as ex:
                logger.error(f"Error guardando configuración local: {ex}")

        if success:
            return jsonify({"status": "success", "enabled": bool(enabled)})
        return jsonify({"status": "error", "message": "No se pudo actualizar"}), 500
    except Exception as e:
        logger.error(f"Error actualizando auto respuesta: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/list_rules', methods=['GET'])
def list_all_rules():
    rules = {}
    try:
        ref = db.reference('posts')
        rules = ref.get() or {}
    except Exception as e:
        logger.error(f"Error listando reglas desde Firebase: {str(e)}")
        # Fallback: cargar reglas desde archivos locales
        for path in glob(os.path.join(CONFIG_DIR, 'config_*.json')):
            try:
                with open(path) as f:
                    cfg = json.load(f)
                post_id = os.path.splitext(os.path.basename(path))[0].replace('config_', '')
                rules[post_id] = cfg
            except Exception as ex:
                logger.error(f"Error leyendo {path}: {ex}")

    result = []
    for post_id, config in rules.items():
        if isinstance(config, dict):
            result.append({
                "post_id": post_id,
                "keywords": config.get("keywords", {}),
                "default_response": config.get("default_response", "")
            })
    return jsonify({"status": "success", "rules": result})


@app.route('/api/get_history', methods=['GET'])
def get_history():
    try:
        with open(HISTORY_FILE) as f:
            main_config = json.load(f)

        history = main_config.get('responded_comments', {})
        return jsonify({
            "status": "success",
            "history": history
        })
    except Exception as e:
        logger.error(f"Error obteniendo historial: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/api/process_comments', methods=['POST'])
def process_comments_manually():
    """Procesar comentarios manualmente para testeo"""
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        comment_text = data.get('comment_text', '').lower()

        if not post_id or not comment_text:
            return jsonify({
                "status": "error",
                "message": "Faltan datos (post_id o comment_text)"
            }), 400

        config = load_config_for_post(post_id)
        matched = False
        reply_text = ""

        # Buscar coincidencias con palabras clave
        for keyword, responses in config.get('keywords', {}).items():
            if keyword.lower() in comment_text:
                reply_text = random.choice(responses) if isinstance(responses, list) and len(responses) > 0 else responses[0]
                log_activity(comment_text, post_id, reply_text, {"username": "test_user"}, matched=True)
                matched = True
                break

        # Si no hay palabra clave, usar default_response
        if not matched:
            default_response = config.get('default_response', '')
            if default_response:
                reply_text = default_response
                log_activity(comment_text, post_id, reply_text, {"username": "test_user"}, matched=False)

        return jsonify({
            "status": "success",
            "matched": matched,
            "response": reply_text
        })

    except Exception as e:
        logger.error(f"Error en /api/process_comments: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
