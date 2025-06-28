from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for, flash, session
from flask_login import login_required, current_user, login_user
from ..models.api_token import ApiToken
from ..models.user import User
from ..database import db, csrf
from datetime import datetime
import secrets
from functools import wraps

api_auth_bp = Blueprint('api_auth', __name__)

def generate_token():
    """
    Generates a unique random token
    
    Returns:
        str: 64-character hexadecimal token
    """
    return secrets.token_hex(32)  # 64 hexadecimal characters

@api_auth_bp.route('/api/auth/token', methods=['POST'])
@login_required
@csrf.exempt
def create_token():
    """
    Creates a new API token for the logged-in user
    """
    # Handle both JSON requests and form requests
    if request.is_json:
        data = request.get_json()
    else:
        # For standard form submissions
        data = request.form.to_dict()
    
    if not data or not data.get('name'):
        return jsonify({'error': 'Token name is required'}), 400
    
    # Generate a unique token
    token_value = generate_token()
    
    # Process the expiration date if provided
    expires_at = None
    if data.get('expires_at') and data.get('expires_at') != 'null' and data.get('expires_at') != '':
        try:
            # Handle different possible date formats
            expires_at_str = data['expires_at']
            current_app.logger.info(f"Attempting to convert date: {expires_at_str}")
            
            try:
                # First, try ISO format
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            except ValueError:
                # Try HTML datetime-local format
                try:
                    expires_at = datetime.strptime(expires_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    # Last attempt with a more generic format
                    expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S')
            
            current_app.logger.info(f"Converted expiration date: {expires_at}")
        except Exception as e:
            current_app.logger.error(f"Error converting date: {str(e)}")
            return jsonify({'error': 'Invalid expiration date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'}), 400
    
    # Create the token in the database
    token = ApiToken(
        user_id=current_user.id,
        token=token_value,
        name=data['name'],
        expires_at=expires_at
    )
    
    db.session.add(token)
    db.session.commit()
    
    # Log token creation
    current_app.logger.info(f"API token '{token.name}' created for user {current_user.username}")
    
    # Determine if the request comes from an HTML form or an API
    is_html_request = request.content_type and 'application/json' not in request.content_type
    is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Prepare the response
    response_data = {
        'token': token_value,
        'name': token.name,
        'expires_at': token.expires_at.isoformat() if token.expires_at else None,
        'created_at': token.created_at.isoformat()
    }
    
    # For AJAX or API requests, return JSON
    if is_ajax_request or not is_html_request:
        return jsonify(response_data), 201
    
    # For standard HTML requests, directly render the token display page
    return render_template('api_tokens/token_display.html',
                           token_value=token_value,
                           token_name=token.name,
                           token_created_at=token.created_at,
                           token_expires_at=token.expires_at)

@api_auth_bp.route('/api/auth/tokens', methods=['GET'])
@login_required
def list_tokens():
    """
    Lists all API tokens for the logged-in user
    """
    tokens = ApiToken.query.filter_by(user_id=current_user.id).all()
    
    return jsonify([token.to_dict() for token in tokens])

@api_auth_bp.route('/api/auth/tokens/<int:token_id>', methods=['DELETE', 'POST'])
@login_required
@csrf.exempt
def revoke_token(token_id):
    """
    Revokes a specific API token
    Supports both DELETE (API) and POST (form) requests
    """
    token = ApiToken.query.filter_by(id=token_id, user_id=current_user.id).first_or_404()
    
    # Log token revocation
    current_app.logger.info(f"API token '{token.name}' revoked by user {current_user.username}")
    
    db.session.delete(token)
    db.session.commit()
    
    # Determine if the request comes from an HTML form or an API
    is_html_request = request.content_type and 'application/json' not in request.content_type
    is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Redirect to the token management page if the request comes from the browser and is not AJAX
    if is_html_request and not is_ajax_request:
        flash('Token revoked successfully', 'success')
        return redirect(url_for('api_auth.manage_tokens'))
    
    # Otherwise, return a JSON response for API or AJAX calls
    return jsonify({
        'message': 'Token revoked successfully',
        'token_id': token_id,
        'status': 'success'
    })

@api_auth_bp.route('/tokens', methods=['GET'])
@login_required
def manage_tokens():
    """
    Displays the API token management page
    """
    from flask import session
    
    # Get the user's tokens
    tokens = ApiToken.query.filter_by(user_id=current_user.id).all()
    
    # Check if a new token is present in the session
    new_token_data = None
    if 'new_token' in session:
        try:
            new_token_data = session.pop('new_token')  # Get and remove from the session
        except Exception:
            pass
    
    return render_template('api_tokens/index.html', tokens=tokens, new_token_data=new_token_data)

def token_auth_required(f):
    """
    Decorator to authenticate API requests via token
    Also supports session authentication for compatibility
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if token authentication is provided
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            # If no Authorization header, try session authentication
            if current_user.is_authenticated:
                return f(*args, **kwargs)
            return jsonify({'error': 'Authentication required'}), 401
        
        # Extract the token
        token_value = auth_header.split(' ')[1]
        
        # Search for the token in the database
        token = ApiToken.query.filter_by(token=token_value, is_active=True).first()
        
        if not token:
            return jsonify({'error': 'Invalid or revoked token'}), 401
        
        # Check if the token has expired
        if token.is_expired():
            return jsonify({'error': 'Token expired'}), 401
        
        # Update the last used date
        token.last_used_at = datetime.utcnow()
        db.session.commit()
        
        # Load the user associated with the token
        user = User.query.get(token.user_id)
        if not user or not user.is_active:
            return jsonify({'error': 'Inactive or deleted user'}), 401
        
        # Set the current user for this request
        # Use login_user with remember=False to avoid creating a session cookie
        login_user(user, remember=False)
        
        # Log token authentication
        current_app.logger.debug(f"User {user.username} authenticated via API token")
        
        # Check if the user has the admin role
        if not hasattr(user, 'is_admin'):
            user.is_admin = user.role == 'admin' if hasattr(user, 'role') else False
        
        # Log token usage (DEBUG level)
        current_app.logger.debug(f"API token '{token.name}' used to access {request.path}")
        
        return f(*args, **kwargs)
    
    return decorated_function