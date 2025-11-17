from flask import Flask
from flask_session import Session
from .config import config
import os

def create_app(config_name=None):
    """Application factory with configuration support"""
    app = Flask(__name__)
    
    # Determine configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app.config.from_object(config[config_name])
    
    # Ensure SECRET_KEY is a string (not None or bytes) - required for Flask-Session
    secret_key = app.config.get('SECRET_KEY')
    if not secret_key or not isinstance(secret_key, str):
        app.config['SECRET_KEY'] = 'dev-key-change-in-production'
    elif isinstance(secret_key, bytes):
        app.config['SECRET_KEY'] = secret_key.decode('utf-8')
    
    # Configure server-side sessions to avoid cookie size limits
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'flask_session')
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    # Ensure SESSION_KEY_PREFIX is a string (not bytes)
    app.config['SESSION_KEY_PREFIX'] = 'shadowscope:'
    # Additional session configuration to prevent bytes issues
    app.config['SESSION_COOKIE_NAME'] = 'shadowscope_session'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # Ensure session directory exists
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
    
    # Initialize Flask-Session
    Session(app)
    
    # Workaround: Monkey-patch session interface to ensure session_id is always string
    # This fixes the TypeError: cannot use a string pattern on a bytes-like object
    # The issue occurs when Flask-Session tries to set cookie with bytes session_id
    # Access session_interface through app, not Session object
    original_save_session = app.session_interface.save_session
    
    def patched_save_session(app_instance, session_obj, response):
        # Ensure session_id is string before saving cookie
        # Patch the response.set_cookie to handle bytes conversion
        original_set_cookie = response.set_cookie
        
        def safe_set_cookie(key, value='', max_age=None, expires=None, path='/', 
                           domain=None, secure=False, httponly=False, samesite=None):
            # Convert value to string if it's bytes
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            return original_set_cookie(key, value, max_age, expires, path, 
                                     domain, secure, httponly, samesite)
        
        response.set_cookie = safe_set_cookie
        
        try:
            return original_save_session(app_instance, session_obj, response)
        finally:
            # Restore original method
            response.set_cookie = original_set_cookie
    
    app.session_interface.save_session = patched_save_session
    
    # Register all modular blueprints
    from app.routes import register_blueprints
    register_blueprints(app)
    
    return app