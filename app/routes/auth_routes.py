from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app


LOGIN_ROUTE = 'auth.login'
from flask_login import login_user, logout_user, login_required, current_user
from services.auth_service import AuthService
import logging

auth_bp = Blueprint('auth', __name__)

def _get_credentials(req):
    """Extracts credentials and data from the request."""
    if req.is_json:
        data = req.get_json()
    else:
        data = req.form
    return data.get('username'), data.get('password'), data

def _log_event(logger_func, message):
    """Logs a security event with IP and User-Agent."""
    ip_address = request.remote_addr
    user_agent = request.user_agent.string
    logger_func(f"{message} - IP: {ip_address} - Agent: {user_agent}")

def _handle_successful_login(user, data):
    """Handles the logic for a successful login."""
    login_user(user)
    admin_logger = current_app.config.get('ADMIN_LOGGER')
    if admin_logger:
        _log_event(admin_logger.info, f"Successful login - User: {user.username} (ID: {user.id})")
    
    next_url = data.get('next') or request.args.get('next')
    if next_url:
        return redirect(next_url)
    if request.is_json:
        return jsonify({
            'message': 'Logged in successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'is_admin': user.is_admin
            }
        })
    return redirect(url_for('ui.lists'))

def _handle_failed_login(username):
    """Handles the logic for a failed login attempt."""
    admin_logger = current_app.config.get('ADMIN_LOGGER')
    if admin_logger:
        _log_event(admin_logger.warning, f"Failed login attempt - User: {username}")
        
    if request.is_json:
        return jsonify({'error': 'Invalid username or password'}), 401
    flash('Invalid username or password', 'error')
    return redirect(url_for(LOGIN_ROUTE))

@auth_bp.route('/api/auth/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if current_user.is_authenticated:
        return redirect(url_for('ui.lists'))
        
    if request.method == 'GET':
        next_url = request.args.get('next')
        return render_template('auth/login.html', next=next_url)
        
    # POST request
    username, password, data = _get_credentials(request)
    
    if not username or not password:
        flash('Username and password are required', 'error')
        return redirect(url_for(LOGIN_ROUTE))
        
    # First, try local authentication, then fall back to LDAP
    user = AuthService.authenticate_local(username, password)
    if not user:
        user = AuthService.authenticate_ldap(username, password)
        
    if user:
        return _handle_successful_login(user, data)
    else:
        return _handle_failed_login(username)

@auth_bp.route('/api/auth/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for(LOGIN_ROUTE))