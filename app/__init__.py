from flask import Flask, request, jsonify, redirect, url_for, render_template, session, current_app
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os
import logging
import logging.handlers
from datetime import datetime

# Use relative imports within the package
from .database import db
from . import i18n
from .utils.timezone_utils import format_datetime, PARIS_TIMEZONE

load_dotenv()

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# Helper function to check public routes
def is_public_route(app, req):
    # Check if the current route is marked as public
    if req.endpoint and req.endpoint in app.view_functions:
        view_function = app.view_functions[req.endpoint]
        if getattr(view_function, 'is_public', False):
            return True
    
    # Check specific paths that should be public
    public_paths = [
        '/api/docs/openapi.yaml',  # OpenAPI file
        '/health',  # Healthcheck endpoint for Docker
    ]
    # Also check for public files
    if req.path.startswith('/public/'):
        return True
        
    return req.path in public_paths

# CSRF configuration for APIs
def csrf_exempt_token_auth(req):
    """Checks if the request should be exempt from CSRF protection"""
    # Exempt requests with token authentication
    auth_header = req.headers.get('Authorization')
    if req.path.startswith('/api/') and auth_header and auth_header.startswith('Bearer '):
        return True
    return False

DATE_FORMAT = '%d/%m/%Y'

def format_date(value):
    """Jinja filter to format dates in dd/mm/yyyy format"""
    if not value:
        return ""
    try:
        if isinstance(value, datetime):
            return format_datetime(value, DATE_FORMAT)
        else:
            for fmt in ('%Y-%m-%d', DATE_FORMAT, '%Y/%m/%d'):
                try:
                    date_obj = datetime.strptime(value, fmt)
                    date_obj = PARIS_TIMEZONE.localize(date_obj)
                    return format_datetime(date_obj, DATE_FORMAT)
                except ValueError:
                    continue
            return value
    except Exception:
        return value

def create_app():
    app = Flask(__name__)
    
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['REMEMBER_COOKIE_SECURE'] = True
    app.config['VERIFY_SSL_CERTIFICATES'] = os.getenv('VERIFY_SSL_CERTIFICATES', 'False').lower() == 'true'
    
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        if database_url.startswith('mysql://'):
            database_url = database_url.replace('mysql://', 'mysql+pymysql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        db_user = os.getenv('DB_USER', 'listing_user')
        db_password = os.getenv('DB_PASSWORD', 'listing_password')
        db_host = os.getenv('DB_HOST', 'db')
        db_name = os.getenv('DB_NAME', 'listing_db')
        db_port = os.getenv('DB_PORT', '3306')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
    
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_timeout': 20, 'pool_pre_ping': True}
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    @app.before_request
    def csrf_protect():
        if is_public_route(app, request):
            return
        if not csrf_exempt_token_auth(request):
            csrf.protect()

    # Logging configuration
    log_level_str = os.getenv('LOG_LEVEL', 'DEBUG').upper()
    log_level = getattr(logging, log_level_str, logging.DEBUG)
    
    # Create the logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure the log format
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)
    
    # Configure the file handler
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    # Configure the console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add the new handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Configure the application logger
    app.logger.setLevel(log_level)
    for handler in app.logger.handlers[:]:
        app.logger.removeHandler(handler)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.propagate = False  # Avoid double logging
    
    # Configure SQLAlchemy logs
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)

    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        from .models.user import User
        return User.query.get(int(user_id))

    # Register Blueprints
    from .routes import auth_routes, list_routes, ui_routes, api_routes, api_auth_routes, api_docs_routes, json_config_routes, help_routes, public_files_routes, admin_routes
    app.register_blueprint(auth_routes.auth_bp)
    app.register_blueprint(list_routes.list_bp)
    app.register_blueprint(ui_routes.ui_bp)
    app.register_blueprint(api_routes.api_bp)
    app.register_blueprint(api_auth_routes.api_auth_bp)
    app.register_blueprint(api_docs_routes.api_docs_bp)
    app.register_blueprint(json_config_routes.json_config_bp)
    app.register_blueprint(help_routes.help_bp)
    app.register_blueprint(public_files_routes.public_files_bp)
    app.register_blueprint(admin_routes.admin_bp)

    i18n.init_app(app)
    app.jinja_env.filters['format_date'] = format_date

    @app.context_processor
    def inject_debug_mode():
        return {'debug_mode': current_app.debug}

    @app.route('/health')
    def health_check():
        setattr(health_check, 'is_public', True)
        return jsonify({"status": "healthy"})

    @app.errorhandler(403)
    def forbidden_error(error):
        ip_error_info = session.pop('ip_error_info', None)
        return render_template('errors/403.html', ip_error_info=ip_error_info), 403

    with app.app_context():
        from .services.scheduler_service import SchedulerService
        if not hasattr(app, 'scheduler'):
            app.scheduler = SchedulerService(app)
        try:
            db.create_all()
        except Exception as e:
            app.logger.error(f"Error creating database tables: {e}")

    return app