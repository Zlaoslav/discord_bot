import logging
import secrets
import time

try:
    from pyngrok import ngrok, conf
    _HAS_PYNGROK = True
except Exception:
    _HAS_PYNGROK = False

logger = logging.getLogger('discord_bot.tunnel')

_ACTIVE_TUNNEL = None


def start_tunnel(local_port: int = 8000, authtoken: str = None):
    """Start an ngrok tunnel to local_port and store public URL and secret in DB (if available).
    Returns dict with keys: public_url, secret, tunnel (ngrok object)
    """
    if not _HAS_PYNGROK:
        raise RuntimeError("pyngrok is not installed; please add pyngrok to requirements and install it")

    if authtoken:
        try:
            conf.get_default().auth_token = authtoken
            ngrok.set_auth_token(authtoken)
            logger.info('ngrok auth token set')
        except Exception as e:
            logger.warning('Failed to set ngrok auth token: %s', e)

    # create tunnel
    try:
        t = ngrok.connect(addr=str(local_port), proto='http', bind_tls=True)
        public = t.public_url
        secret = secrets.token_urlsafe(24)
        _ACTIVE_TUNNEL = t

        # try to store in DB if helper available
        try:
            from .web import _get_conn
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO tunnels(public_url, secret, created) VALUES (?, ?, ?)", (public, secret, int(time.time())))
            conn.commit()
            conn.close()
        except Exception:
            logger.exception('Failed to save tunnel info to DB')

        logger.info('ngrok tunnel started: %s', public)
        return { 'public_url': public, 'secret': secret, 'tunnel': t }
    except Exception as e:
        logger.exception('Failed to start ngrok tunnel')
        raise


def stop_tunnel():
    try:
        if _ACTIVE_TUNNEL:
            ngrok.disconnect(_ACTIVE_TUNNEL.public_url)
            ngrok.kill()
    except Exception:
        logger.exception('Error stopping ngrok tunnel')
