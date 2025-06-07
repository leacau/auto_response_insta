# app.py
import os
import json
import logging
import time
from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    ClientLoginRequired
)

# Configura logging
logging.basicConfig(filename='logs/errors.log', level=logging.INFO)

def load_config():
    with open('config.json') as f:
        return json.load(f)

def reply_based_on_keyword(text, config):
    text_lower = text.lower()
    for keyword, response in config['keywords'].items():
        if keyword in text_lower:
            return response
    return config['default_response']

def main():
    cl = Client()
    try:
        # Login con reintentos
        cl.login(os.getenv('INSTAGRAM_USER'), os.getenv('INSTAGRAM_PASSWORD'))
        
        while True:
            try:
                config = load_config()
                posts = cl.user_medias(cl.user_id, amount=3)  # Solo últimos 3 posts
                for post in posts:
                    comments = cl.media_comments(post.pk)
                    for comment in comments:
                        if not comment.has_liked:
                            response = reply_based_on_keyword(comment.text, config)
                            cl.media_comment(post.pk, response)
                            cl.comment_like(comment.pk)
                            logging.info(f"Respondido: {comment.text[:30]}...")
                            time.sleep(15)  # Cumple límites de la API

            except (ChallengeRequired, ClientError) as e:
                logging.error(f"Error API: {e}")
                time.sleep(60 * 15)  # Espera 15 min si hay error

            time.sleep(60 * 10)  # Ciclo cada 10 minutos

    except Exception as e:
        logging.critical(f"Error crítico: {e}")
        raise

if __name__ == "__main__":
    main()