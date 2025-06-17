from flask import Flask, request, jsonify, send_from_directory, render_template, Response
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
MAX_COMMENTS = int(os.getenv('MAX_COMMENTS', 100))  # Máximo de comentarios a obtener por post

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
        url = f"{GRAPH_URL}/{IG_USER_ID}/media"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': 20,
            'fields': 'id,caption,like_count,comments_count,timestamp,thumbnail_url,media_url'
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error obteniendo posts: {data['error']['message']}")
            return jsonify({"status": "error", "message": data['error']['message']}), 500

        posts = data.get('data', [])
        total = len(posts)
        per_page = 5
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated = posts[start_idx:end_idx]

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
            "has_next": end_idx < total
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

        return jsonify({
            "status": "success",
            "post": {
                "id": data['id'],
                "caption": data.get('caption', 'Sin descripción'),
                "like_count": data.get('like_count', 0),
                "comment_count": data.get('comments_count', 0),
                "timestamp": data.get('timestamp', ''),
                "thumbnail": data.get('thumbnail_url', data.get('media_url', '/static/images/placeholder.jpg'))
            }
        })

    except Exception as e:
        logger.error(f"Error obteniendo detalle del post: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/comments/<post_id>', methods=['GET'])
def get_post_comments(post_id):
    logger.info(f"Obteniendo comentarios para el post {post_id}")
    try:
        url = f"{GRAPH_URL}/{post_id}/comments"
        params = {
            'access_token': ACCESS_TOKEN,
            'limit': 100,
            'fields': 'text,from{username},timestamp'
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()

        if 'error' in data:
            logger.error(f"Error obteniendo comentarios: {data['error']['message']}")
            return jsonify({"status": "error", "message": data['error']['message']}), 500

        comments = []
        for c in data.get('data', []):
            user = c.get('from', {}) or {}
            comments.append({
                "id": c.get('id', ''),
                "text": c.get('text', 'Sin comentario'),
                "username": user.get('username', 'usuario_anonimo'),
                "timestamp": c.get('timestamp', '')
            })

        return jsonify({
            "status": "success",
            "comments": comments
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

        config_path = f"config_{post_id}.json"
        try:
            with open(config_path) as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {"keywords": {}, "default_response": "Gracias por tu comentario"}

        config["keywords"][keyword] = responses;

        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return jsonify({"status": "success", "message": "Regla agregada correctamente"})
    except Exception as e:
        logger.error(f"Error al agregar regla: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/list_rules', methods=['GET'])
def list_all_rules():
    try:
        from glob import glob
        rule_files = glob("config_*.json")
        rules = []

        for file in rule_files:
            with open(file) as f:
                config = json.load(f)
                post_id = file.replace('config_', '').replace('.json', '')
                rules.append({
                    "post_id": post_id,
                    "keywords": config.get('keywords', {})
                })

        return jsonify({"status": "success", "rules": rules})
    except Exception as e:
        logger.error(f"Error listando reglas: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get_history', methods=['GET'])
def get_history():
    try:
        config_path = "config_global.json"
        with open(config_path) as f:
            main_config = json.load(f)

        return jsonify({"status": "success", "history": main_config.get('responded_comments', {})})
    except Exception as e:
        logger.error(f"Error obteniendo historial: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)