from app import create_app

app = create_app()

if __name__ == '__main__':
    # Use configuration from app.config (loaded from config.py)
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 5000)
    debug = app.config.get('DEBUG', True)
    
    app.run(host=host, port=port, debug=debug, use_reloader=True)