from flask import Flask, request, jsonify, render_template, Response
import os
import json
import logging
import time
import threading
import requests
from datetime import datetime, timedelta
import random
from glob import glob
import firebase_admin
from firebase_admin import credentials, db
from firebase_admin import auth
from functools import wraps
from flask import redirect

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
GRAPH_URL = "https://graph.instagram.com/v23.0"  # Volver a la API de Instagram
CONFIG_DIR = "config_posts"
HISTORY_FILE = "config_global.json"

# Inicializar Firebase
def init_firebase():
    """Inicializa Firebase utilizando credenciales de variables de entorno."""
    if firebase_admin._apps:
        return
    try:
        cred_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
        if cred_json:
            cred_info = json.loads(cred_json)
            cred = credentials.Certificate(cred_info)
        else:
            cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH', 'firebase_credentials.json')
            cred = credentials.Certificate(cred_path)

        firebase_admin.initialize_app(cred, {
            'databaseURL': os.getenv('FIREBASE_DATABASE_URL')
        })
    except Exception as e:
        logger.error(f"No se pudo conectar a Firebase: {str(e)}")

init_firebase()

os.makedirs(CONFIG_DIR, exist_ok=True)

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        session_cookie = request.cookies.get('session')
        if not session_cookie:
            if request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
            return redirect('/login')
        try:
            auth.verify_session_cookie(session_cookie, check_revoked=True)
        except Exception as e:
            logger.warning(f'Session verify failed: {str(e)}')
            if request.path.startswith('/api/'):
                return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
            return redirect('/login')
        return view(*args, **kwargs)
    return wrapped

def schedule_action(delay, func, *args, **kwargs):
    """Ejecuta una función después de cierto delay sin bloquear el flujo"""
    def _run():
        time.sleep(delay)
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error en acción diferida: {str(e)}")

    threading.Thread(target=_run, daemon=True).start()

def get_config_path(post_id):
    return os.path.join(CONFIG_DIR, f"config_{post_id}.json")

@app.route('/')
@login_required
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/firebase-config.js')
def firebase_config_js():
    config = {
        'apiKey': os.getenv('FIREBASE_API_KEY'),
        'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN'),
        'projectId': os.getenv('FIREBASE_PROJECT_ID'),
    }
    # Optional parameters
    opt_keys = {
        'storageBucket': 'FIREBASE_STORAGE_BUCKET',
        'messagingSenderId': 'FIREBASE_MESSAGING_SENDER_ID',
        'appId': 'FIREBASE_APP_ID'
    }
    for key, env in opt_keys.items():
        val = os.getenv(env)
        if val:
            config[key] = val
    js = f"const firebaseConfig = {json.dumps(config)};\nfirebase.initializeApp(firebaseConfig);"
    return Response(js, mimetype='application/javascript')

@app.route('/sessionLogin', methods=['POST'])
def session_login():
    try:
        id_token = request.json.get('idToken')
        expires = timedelta(days=5)
        session_cookie = auth.create_session_cookie(id_token, expires_in=expires)
        resp = jsonify({'status': 'success'})
        resp.set_cookie('session', session_cookie, max_age=expires.total_seconds(), httponly=True)
        return resp
    except Exception as e:
        logger.error(f'Session login error: {str(e)}')
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

@app.route('/sessionLogout', methods=['POST'])
def session_logout():
    resp = jsonify({'status': 'success'})
    resp.delete_cookie('session')
    return resp

@app.route('/privacy')
def privacy_page():
    return render_template('privacy.html')

@app.route('/legal')
def legal_page():
    return render_template('legal.html')

@app.route('/unsubscribe')
def unsubscribe_page():
    return render_template('unsubscribe.html')

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
                    post_id = (
                        value.get('media_id')
                        or value.get('post_id')
                        or (value.get('media') or {}).get('id')
                        or (value.get('post') or {}).get('id')
                        or ''
                    )
                    comment_id = (
                        value.get('comment_id')
                        or value.get('id')
                        or (value.get('comment') or {}).get('id')
                    )
                    comment_time = value.get('timestamp') or value.get('created_time')
                    from_user = value.get('from', {})
                    
                    if not post_id or not comment_id or not comment_text:
                        logger.warning("Datos incompletos en comentario")
                        continue
                    
                    if has_responded(comment_id):
                        logger.info(f"Comentario {comment_id} ya procesado")
                        continue

                    config = load_config_for_post(post_id)

                    if not config.get("enabled", False):
                        logger.info("Auto respuesta desactivada para %s", post_id)
                        continue

                    enabled_since = config.get("enabled_since")
                    if enabled_since and comment_time:
                        try:
                            ct = datetime.fromisoformat(comment_time.replace('Z','+00:00'))
                            es = datetime.fromisoformat(enabled_since)
                            if ct < es:
                                logger.info("Comentario previo a activación")
                                continue
                        except Exception as e:
                            logger.error(f"Error procesando fechas: {str(e)}")

                    matched = False
                    reply_text = ""

                    # Buscar coincidencias con palabras clave
                    for keyword, responses in config.get('keywords', {}).items():
                        if keyword.lower() in comment_text:
                            reply_text = random.choice(responses) if isinstance(responses, list) and responses else responses
                            schedule_action(10, send_comment_reply, comment_id, reply_text)
                            dm_text = config.get('dm_message')
                            if dm_text and from_user.get('id'):
                                schedule_action(
                                    20,
                                    send_direct_message,
                                    from_user['id'],
                                    dm_text,
                                    config.get('dm_button_text'),
                                    config.get('dm_button_url'),
                                )

                            matched = True
                            break  # Solo procesar primera coincidencia

                    # Registrar actividad si hubo match
                    if matched:
                        log_activity(
                            comment_id, 
                            comment_text, 
                            post_id, 
                            reply_text, 
                            from_user, 
                            matched=True
                        )

            return jsonify({"status": "success", "message": "Evento procesado"}), 200

        except Exception as e:
            logger.error(f"Error procesando evento: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

def send_comment_reply(comment_id, text):
    """Responde a un comentario existente usando la API de Instagram"""
    url = f"{GRAPH_URL}/{comment_id}/replies"
    payload = {
        "message": text,
        "access_token": ACCESS_TOKEN
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        data = response.json()
        if "error" in data:
            logger.error(f"Error respondiendo comentario: {data['error']['message']}")
            return {"error": data['error']['message']}
        return data
    except Exception as e:
        logger.error(f"Excepción al responder comentario: {str(e)}")
        return {"error": str(e)}

def send_direct_message(user_id, text, button_text=None, button_url=None):
    """Envía un mensaje directo utilizando la API de Instagram"""
    url = f"{GRAPH_URL}/{IG_USER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"recipient": {"id": user_id}}
    if button_text and button_url:
        payload["message"] = {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": text,
                    "buttons": [
                        {"type": "web_url", "url": button_url, "title": button_text}
                    ],
                },
            }
        }
    else:
        payload["message"] = {"text": text}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        data = response.json()
        if "error" in data:
            logger.error(f"Error enviando DM: {data['error']['message']}")
            return {"error": data['error']['message']}
        return data
    except Exception as e:
        logger.error(f"Excepción enviando DM: {str(e)}")
        return {"error": str(e)}

def load_config_for_post(post_id):
    """Carga configuración específica para un post"""
    config = {
        "keywords": {},
        "default_response": "",
        "dm_message": "",
        "dm_button_text": "",
        "dm_button_url": "",
        "enabled": False,
        "enabled_since": None,
    }
    
    try:
        ref = db.reference(f'posts/{post_id}')
        fb_config = ref.get() or {}
        config.update(fb_config)
    except Exception as e:
        logger.error(f"Error cargando Firebase: {str(e)}")
        try:
            with open(get_config_path(post_id)) as f:
                file_config = json.load(f)
                config.update(file_config)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    return config

def save_config_for_post(post_id, config):
    """Guarda configuración por post en Firebase o localmente"""
    try:
        ref = db.reference(f'posts/{post_id}')
        ref.set(config)
        return True
    except Exception as e:
        logger.error(f"Error guardando en Firebase: {str(e)}")
        try:
            with open(get_config_path(post_id), 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error guardando localmente: {str(e)}")
            return False

def log_activity(comment_id, comment_text, media_id, reply_text, from_user, 
                 matched=True):
    """Registra actividad en el historial"""
    try:
        # Cargar configuración existente
        try:
            with open(HISTORY_FILE) as f:
                history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            history = {"responded_comments": {}}
        
        # Crear nueva entrada
        timestamp = datetime.now().isoformat()
        entry = {
            "usuario": from_user.get('username', ''),
            "user_id": from_user.get('id', ''),
            "comentario": comment_text,
            "respuesta": reply_text,
            "fecha": timestamp,
            "matched": matched
        }
        
        # Guardar
        history['responded_comments'][comment_id] = entry
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
            
    except Exception as e:
        logger.error(f"Error registrando actividad: {str(e)}")

def has_responded(comment_id):
    """Verifica si ya se respondió a un comentario"""
    try:
        with open(HISTORY_FILE) as f:
            history = json.load(f)
        return comment_id in history.get('responded_comments', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return False

@app.route('/api/get_posts', methods=['GET'])
@login_required
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
@login_required
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
                "enabled": config.get('enabled', False),
                "dm_message": config.get('dm_message', ''),
                "dm_button_text": config.get('dm_button_text', ''),
                "dm_button_url": config.get('dm_button_url', '')
            }
        })

    except Exception as e:
        logger.error(f"Error obteniendo detalles del post: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/comments/<post_id>', methods=['GET'])
@login_required
def get_post_comments(post_id):
    try:
        url = f"{GRAPH_URL}/{post_id}/comments"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': 100,
            'fields': 'text,from{id,username},timestamp,comment_count',
            'filter': 'toplevel'
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
                    "user_id": user.get('id', ''),
                    "timestamp": c.get('timestamp', ''),
                    "comment_count": c.get('comment_count', 0)
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


@app.route('/api/replies/<comment_id>', methods=['GET'])
@login_required
def get_comment_replies(comment_id):
    try:
        url = f"{GRAPH_URL}/{comment_id}/replies"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': 100,
            'fields': 'text,from{id,username},timestamp'
        }

        replies = []
        while url:
            response = requests.get(url, params=params if params else {}, timeout=30)
            data = response.json()

            if 'error' in data:
                logger.error(f"Error obteniendo respuestas: {data['error']['message']}")
                return jsonify({"status": "error", "message": data['error']['message']}), 500

            for r in data.get('data', []):
                user = r.get('from', {}) or {}
                replies.append({
                    "id": r.get('id', ''),
                    "text": r.get('text', 'Comentario no disponible'),
                    "username": user.get('username', 'usuario_anonimo'),
                    "user_id": user.get('id', ''),
                    "timestamp": r.get('timestamp', '')
                })

            url = data.get('paging', {}).get('next')
            params = None

        return jsonify({"status": "success", "replies": replies})

    except Exception as e:
        logger.error(f"Error obteniendo respuestas: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/add_rule', methods=['POST'])
@login_required
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
@login_required
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
@login_required
def set_auto_reply():
    """Activar o desactivar respuestas automáticas para un post"""
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        enabled = data.get('enabled')
        if post_id is None or enabled is None:
            return jsonify({"status": "error", "message": "Faltan datos"}), 400
        success = False
        timestamp = datetime.utcnow().isoformat()
        try:
            ref = db.reference(f'posts/{post_id}')
            current = ref.get() or {}
            update = {"enabled": bool(enabled)}
            if enabled:
                update["enabled_since"] = timestamp
            ref.update(update)
            success = True
        except Exception as e:
            logger.error(f"Error actualizando en Firebase: {str(e)}")

        if not success:
            try:
                path = get_config_path(post_id)
                config = load_config_for_post(post_id)
                config["enabled"] = bool(enabled)
                if enabled:
                    config["enabled_since"] = timestamp
                with open(path, 'w') as f:
                    json.dump(config, f, indent=2)
                success = True
            except Exception as ex:
                logger.error(f"Error guardando configuración local: {ex}")

        if success:
            return jsonify({"status": "success", "enabled": bool(enabled)})
        return jsonify({"status": "error", "message": "No se pudo actualizar"}), 500
    except Exception as e:
        logger.error(f"Error actualizando DM: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/list_rules', methods=['GET'])
@login_required
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

@app.route('/api/set_dm', methods=['POST'])
@login_required
def set_dm_message():
    try:
        data = request.get_json()
        post_id = data.get('post_id')
        dm_message = data.get('dm_message')
        button_text = data.get('button_text')
        button_url = data.get('button_url')
        
        if not post_id:
            return jsonify({"status": "error", "message": "Missing post_id"}), 400

        config = load_config_for_post(post_id)
        config['dm_message'] = dm_message
        config['dm_button_text'] = button_text
        config['dm_button_url'] = button_url

        if save_config_for_post(post_id, config):
            return jsonify({"status": "success", "message": "DM message updated"})
        return jsonify({"status": "error", "message": "Failed to save"}), 500

    except Exception as e:
        logger.error(f"Error setting DM message: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/get_history', methods=['GET'])
@login_required
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
@login_required
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
                log_activity(None, comment_text, post_id, reply_text, {"username": "test_user"}, matched=True)
                matched = True
                break

        # Si no hay palabra clave, no se genera respuesta
        # (se eliminó el if vacío que causaba el error)

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
