from flask import Flask, request, jsonify, redirect, url_for, render_template, session
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os
import logging
import logging.handlers
from datetime import datetime
from database import db

# Import the internationalization module
import i18n

# Import timezone utilities
from utils.timezone_utils import get_paris_now, utc_to_paris, PARIS_TIMEZONE, format_datetime

load_dotenv()

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()

# CSRF configuration for APIs
def csrf_exempt_token_auth(request):
    """Checks if the request should be exempt from CSRF protection"""
    # Exempt requests with token authentication
    if request.path.startswith('/api/') and request.headers.get('Authorization') and request.headers.get('Authorization').startswith('Bearer '):
        return True
    return False

# Timezone management functions have been moved to utils.timezone_utils

def format_date(value):
    """Jinja filter to format dates in dd/mm/yyyy format"""
    if not value:
        return ""
    try:
        # If the value is already a date
        if isinstance(value, datetime):
            # Use our utility function to convert and format
            return format_datetime(value, '%d/%m/%Y')
        else:
            # Try different date formats
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    date_obj = datetime.strptime(value, fmt)
                    # Add the Paris timezone and format
                    date_obj = PARIS_TIMEZONE.localize(date_obj)
                    return format_datetime(date_obj, '%d/%m/%Y')
                except ValueError:
                    continue
            # Return the original value if no format matches
            return value
    except Exception:
        return value  # In case of an error, return the original value

def create_app(config_name=None):
    app = Flask(__name__)
    
    # Configure ProxyFix to handle X-Forwarded-* headers
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
    
    # Disable template caching for development
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    
    # Server configuration
    server_name = os.getenv('SERVER_NAME')
    # Disabling SERVER_NAME verification to allow healthcheck
    # if server_name:
    #     app.config['SERVER_NAME'] = server_name
    
    # Configuration for HTTPS
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['REMEMBER_COOKIE_SECURE'] = True
    
    # Configuration for SSL certificate verification during external requests
    # By default, certificates are not verified unless a custom certificate is provided
    app.config['VERIFY_SSL_CERTIFICATES'] = os.getenv('VERIFY_SSL_CERTIFICATES', 'False').lower() == 'true'
    
    # Use the database configuration from the DATABASE_URL variable if it exists
    # otherwise use individual variables or default values
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        # Replace mysql:// with mysql+pymysql:// to use the PyMySQL driver
        if database_url.startswith('mysql://'):
            database_url = database_url.replace('mysql://', 'mysql+pymysql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Fallback to individual variables
        db_host = os.getenv('DB_HOST', 'db')  
        db_user = os.getenv('DB_USER', 'listing_user')  
        db_password = os.getenv('DB_PASSWORD', 'listing_password')  
        db_name = os.getenv('DB_NAME', 'listing_db')  
        db_port = os.getenv('DB_PORT', '3306')
        
        app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
    
    # Add connection options to improve reliability
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 280,  
        'pool_timeout': 20,   
        'pool_pre_ping': True 
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    # Configure CSRF protection with exemption for token-authenticated APIs
    csrf.init_app(app)

    # # Rendre csrf_token disponible dans tous les templates
    # @app.context_processor
    # def inject_csrf_token():
    #     return dict(csrf_token=generate_csrf)
    
    # Define the CSRF exemption function
    app.config['WTF_CSRF_CHECK_DEFAULT'] = False
    
    @csrf.exempt
    def csrf_exempt_api_routes():
        pass
    
    # Use the before_request decorator to check for CSRF exemptions
    @app.before_request
    def csrf_protect():
        # Exempt public routes from CSRF protection
        if is_public_route():
            return None
            
        if not csrf_exempt_token_auth(request):
            if request.endpoint not in csrf._exempt_views:
                csrf.protect()
    
    # CSRF exemption for certain API routes
    @csrf.exempt
    def csrf_exempt_route():
        # Exemption for user deletion routes
        if request.path.startswith('/admin/users/') and request.path.endswith('/delete'):
            return True
        return False
    
    migrate.init_app(app, db)
    
    # Configure logging
    # Determine the log level from the LOG_LEVEL environment variable
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    app.logger.setLevel(log_level)
    
    # Handler for the console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    app.logger.addHandler(console_handler)
    
    # Create log directories if they don't exist
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    cron_logs_dir = os.path.join(logs_dir, 'cron')
    admin_logs_dir = os.path.join(logs_dir, 'admin')
    os.makedirs(cron_logs_dir, exist_ok=True)
    os.makedirs(admin_logs_dir, exist_ok=True)
    
    # Configure a log file for the main application with rotation
    app_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(logs_dir, 'app.log'),
        when='midnight',
        interval=1,
        backupCount=30  # Keep 30 days of logs
    )
    app_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    app.logger.addHandler(app_handler)
    
    # Configuration of the specific logger for cron jobs
    cron_logger = logging.getLogger('services.scheduler_service')
    cron_logger.setLevel(log_level)
    
    # Handler for cron log files with daily rotation
    cron_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(cron_logs_dir, 'cron.log'),
        when='midnight',
        interval=1,
        backupCount=30  # Keep 30 days of logs
    )
    cron_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    cron_logger.addHandler(cron_handler)
    
    # Ensure cron logs are not propagated to parent handlers
    cron_logger.propagate = False
    
    # Configuration of the specific logger for administration actions
    admin_logger = logging.getLogger('admin')
    admin_logger.setLevel(log_level)
    
    # Handler for admin log files with daily rotation
    admin_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(admin_logs_dir, 'admin.log'),
        when='midnight',
        interval=1,
        backupCount=30  # Keep 30 days of logs
    )
    admin_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    admin_logger.addHandler(admin_handler)
    
    # Ensure admin logs are not propagated to parent handlers
    admin_logger.propagate = False
    
    # Make the loggers available in the application
    app.config['ADMIN_LOGGER'] = admin_logger
    app.config['CRON_LOGGER'] = cron_logger
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    
    # Function to check if a route is public
    def is_public_route():
        # Check if the current route is marked as public
        if request.endpoint:
            view_function = app.view_functions.get(request.endpoint)
            if view_function and getattr(view_function, 'is_public', False):
                return True
        
        # Check specific routes that should be public
        public_paths = [
            '/api/docs/openapi.yaml',  # OpenAPI file
            '/health',  # Healthcheck endpoint for Docker
        ]
        return request.path in public_paths
    
    # Configure the login manager to exempt public routes
    @login_manager.unauthorized_handler
    def unauthorized():
        if is_public_route():
            # If it's a public route, let it pass without authentication
            return None
        # Otherwise, redirect to the login page
        return redirect(url_for('auth.login'))
        
    # Add a before_request decorator to handle public route authentication
    @app.before_request
    def handle_public_routes():
        # If it's a public route, no authentication check is needed
        if is_public_route():
            return None
    
    @login_manager.user_loader
    def load_user(user_id):
        from models.user import User
        return User.query.get(int(user_id))
    
    # Import models to ensure they are registered with SQLAlchemy
    from models.user import User
    from models.list import List, ListColumn, ListData
    from models.ldap_config import LDAPConfig
    from models.api_token import ApiToken
    
    # Add JSON configuration methods to the List model
    try:
        import add_json_methods
        app.logger.info("JSON configuration methods added to the List model")
    except Exception as e:
        app.logger.error(f"Error adding JSON configuration methods: {str(e)}")
    
    # Register blueprints
    from routes.auth_routes import auth_bp
    from routes.list_routes import list_bp
    from routes.ui_routes import ui_bp
    from routes.api_routes import api_bp
    from routes.api_auth_routes import api_auth_bp
    from routes.api_docs_routes import api_docs_bp
    from routes.json_config_routes import json_config_bp
    from routes.help_routes import help_bp
    from routes.public_files_routes import public_files_bp
    from routes.admin_routes import admin_bp
    
    app.register_blueprint(list_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(api_auth_bp)
    app.register_blueprint(api_docs_bp)
    app.register_blueprint(json_config_bp)
    app.register_blueprint(help_bp)
    app.register_blueprint(public_files_bp)
    app.register_blueprint(admin_bp)
    
    # Initialize internationalization
    i18n.init_app(app)
    
    # Add custom filters
    app.jinja_env.filters['format_date'] = format_date

    # Injecte debug_mode dans tous les templates Jinja2
    @app.context_processor
    def inject_debug_mode():
        from flask import current_app
        return dict(debug_mode=current_app.debug)
    
    # Healthcheck endpoint for Docker
    @app.route('/health')
    def health_check():
        # Mark this route as public so it's accessible without authentication
        # and regardless of the configured SERVER_NAME
        health_check.is_public = True
        return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200
    
    # Custom error handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        # Get IP error information from the session if it exists
        ip_error_info = session.get('ip_error_info', None)
        # Delete the information from the session after retrieving it
        if 'ip_error_info' in session:
            session.pop('ip_error_info')
        return render_template('errors/403.html', ip_error_info=ip_error_info), 403

    # Filter to format dates and times
    def datetime_filter(value):
        if not value:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return value
        if isinstance(value, datetime):
            return value.strftime('%d/%m/%Y %H:%M')
        return value

    app.jinja_env.filters['datetime'] = datetime_filter
    
    # Create database tables
    with app.app_context():
        try:
            db.create_all()
            app.logger.info("Database tables created successfully")
        except Exception as e:
            app.logger.error(f"Error creating database tables: {str(e)}")
            raise
    
    # Initialize the scheduler service for cron jobs
    from services.scheduler_service import SchedulerService
    scheduler = SchedulerService(app)
    app.scheduler = scheduler  # Store the instance for later access if needed
    
    return app

# Only create the application if the script is executed directly
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)
else:
    # Create the application for imports (WSGI, etc.)
    app = create_app()