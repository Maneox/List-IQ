from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from ..services.auth_service import AuthService
import logging

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/auth/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('ui.lists'))
        
    if request.method == 'GET':
        next_url = request.args.get('next')
        return render_template('auth/login.html', next=next_url)
        
    # Get form data
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form
        
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        flash(_('Username and password are required'), 'error')
        return redirect(url_for('auth.login'))
        
    # First, try local authentication
    user = AuthService.authenticate_local(username, password)
    
    # If local authentication fails, try LDAP
    if not user:
        user = AuthService.authenticate_ldap(username, password)
        
    if user:
        login_user(user)
        
        # Log the login event
        admin_logger = current_app.config.get('ADMIN_LOGGER')
        if admin_logger:
            ip_address = request.remote_addr
            user_agent = request.user_agent.string
            admin_logger.info(f"Successful login - User: {user.username} (ID: {user.id}) - IP: {ip_address} - Agent: {user_agent}")
        
        next_url = data.get('next') or request.args.get('next')
        if next_url:
            return redirect(next_url)
        if request.is_json:
            return jsonify({
                'message': _('Logged in successfully'),
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'is_admin': user.is_admin
                }
            })
        return redirect(url_for('ui.lists'))
    else:
        if request.is_json:
            return jsonify({'error': _('Invalid username or password')}), 401
        flash(_('Invalid username or password'), 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/api/auth/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))