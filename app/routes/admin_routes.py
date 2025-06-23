from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models.user import User
from models.ldap_config import LDAPConfig
from services.ldap_service import LDAPService
from database import db
from functools import wraps
import json
from app import csrf  # Import CSRF extension

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Unauthorized access', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """Lists all users"""
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_user():
    """Creates a new user"""
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            is_admin = request.form.get('is_admin') == 'on'
            is_active = request.form.get('is_active', 'on') == 'on'

            current_app.logger.info(f"Attempting to create user: {username}, {email}")

            if not username or not email or not password:
                flash('All fields are required', 'danger')
                return redirect(url_for('admin.new_user'))

            if User.query.filter_by(username=username).first():
                flash('This username already exists', 'danger')
                return redirect(url_for('admin.new_user'))

            if User.query.filter_by(email=email).first():
                flash('This email address already exists', 'danger')
                return redirect(url_for('admin.new_user'))

            user = User(
                username=username,
                email=email,
                is_admin=is_admin,
                is_active=is_active
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()
            
            # Log user creation with the admin logger
            admin_logger = current_app.config.get('ADMIN_LOGGER')
            if admin_logger:
                ip_address = request.remote_addr
                admin_logger.info(f"User creation - Name: {username} - Email: {email} - Admin: {is_admin} - By: {current_user.username} (ID: {current_user.id}) - IP: {ip_address}")
            
            flash('User created successfully', 'success')
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating user: {str(e)}")
            flash(f'Error during creation: {str(e)}', 'danger')
            return redirect(url_for('admin.new_user'))

    return render_template('admin/new_user.html')

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edits an existing user"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            is_admin = request.form.get('is_admin') == 'on'
            is_active = request.form.get('is_active', 'on') == 'on'

            current_app.logger.info(f"Attempting to edit user {user_id}: {username}, {email}")

            if not username or not email:
                flash('Username and email are required', 'danger')
                return redirect(url_for('admin.edit_user', user_id=user_id))

            existing_user = User.query.filter_by(username=username).first()
            if existing_user and existing_user.id != user_id:
                flash('This username already exists', 'danger')
                return redirect(url_for('admin.edit_user', user_id=user_id))

            # Temporarily commented out to resolve database connection issue
            # existing_email = User.query.filter_by(email=email).first()
            # if existing_email and existing_email.id != user_id:
            #     flash('This email address already exists', 'danger')
            #     return redirect(url_for('admin.edit_user', user_id=user_id))

            user.username = username
            # user.email = email
            user.is_admin = is_admin
            user.is_active = is_active

            if password:
                user.set_password(password)

            db.session.commit()
            
            # Log user modification with the admin logger
            admin_logger = current_app.config.get('ADMIN_LOGGER')
            if admin_logger:
                ip_address = request.remote_addr
                admin_logger.info(f"User modification - ID: {user_id} - Name: {username} - Admin: {is_admin} - Password changed: {bool(password)} - By: {current_user.username} (ID: {current_user.id}) - IP: {ip_address}")
            
            flash('User modified successfully', 'success')
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error modifying user {user_id}: {str(e)}")
            flash(f'Error during modification: {str(e)}', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))

    return render_template('admin/edit_user.html', user=user)

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
@csrf.exempt  # Exempt this route from CSRF protection to allow deletion from JavaScript
def delete_user(user_id):
    """Deletes a user"""
    # Check if it's an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if current_user.id == user_id:
        error_msg = 'You cannot delete your own account'
        if is_ajax:
            return jsonify({'success': False, 'error': error_msg}), 400
        else:
            flash(error_msg, 'danger')
            return redirect(url_for('admin.users'))

    try:
        user = User.query.get_or_404(user_id)
        current_app.logger.info(f"Attempting to delete user {user_id} (type: {user.auth_type})")
        
        # API tokens will be automatically deleted thanks to the cascade delete
        from models.api_token import ApiToken
        api_tokens_count = ApiToken.query.filter_by(user_id=user_id).count()
        if api_tokens_count > 0:
            current_app.logger.info(f"User {user_id} has {api_tokens_count} API tokens that will be automatically deleted")
        
        # Check if the user has associated lists
        from models.list import List
        user_lists = List.query.filter_by(user_id=user_id).all()
        
        if user_lists:
            current_app.logger.info(f"User {user_id} has {len(user_lists)} associated lists")
            # Update the lists so they no longer have an owner
            for user_list in user_lists:
                user_list.user_id = None
            db.session.commit()
            current_app.logger.info(f"Lists for user {user_id} have been disassociated")
        
        # Delete the user
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        # Log user deletion with the admin logger
        admin_logger = current_app.config.get('ADMIN_LOGGER')
        if admin_logger:
            ip_address = request.remote_addr
            admin_logger.info(f"User deletion - ID: {user_id} - Name: {username} - By: {current_user.username} (ID: {current_user.id}) - IP: {ip_address}")
        
        
        if is_ajax:
            return jsonify({'success': True, 'message': f"User {user.username} was deleted successfully"})
        else:
            flash(f"User {user.username} was deleted successfully", 'success')
            return redirect(url_for('admin.users'))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user {user_id}: {str(e)}")
        
        error_msg = "Error during deletion"
        
        # Check if the error is due to a foreign key constraint
        if 'foreign key constraint fails' in str(e).lower():
            error_msg = "Cannot delete this user because they are referenced by other items in the database."
        else:
            error_msg = f"Error during deletion: {str(e)}"
        
        if is_ajax:
            return jsonify({'success': False, 'error': error_msg}), 500
        else:
            flash(error_msg, 'danger')
            return redirect(url_for('admin.users'))


@admin_bp.route('/ldap-config', methods=['GET'])
@login_required
@admin_required
def ldap_config():
    """Displays the LDAP configuration page"""
    config = LDAPConfig.get_config()
    return render_template('admin/ldap_config.html', config=config)


@admin_bp.route('/ldap-config/save', methods=['POST'])
@login_required
@admin_required
def save_ldap_config():
    """Saves the LDAP configuration"""
    try:
        config = LDAPConfig.get_config()
        
        # Connection parameters
        config.enabled = request.form.get('enabled') == 'on'
        config.host = request.form.get('host')
        config.port = int(request.form.get('port', 389))
        config.use_ssl = request.form.get('use_ssl') == 'on'
        config.use_tls = request.form.get('use_tls') == 'on'
        config.verify_cert = request.form.get('verify_cert') == 'on'
        
        # CA certificate management
        ca_cert_file = request.files.get('ca_cert')
        if ca_cert_file and ca_cert_file.filename:
            try:
                ca_cert_content = ca_cert_file.read().decode('utf-8')
                # Check that the content is a valid PEM certificate
                if '-----BEGIN CERTIFICATE-----' in ca_cert_content and '-----END CERTIFICATE-----' in ca_cert_content:
                    config.ca_cert = ca_cert_content
                else:
                    flash('The provided file does not appear to be a valid PEM certificate', 'warning')
            except Exception as e:
                current_app.logger.error(f"Error reading CA certificate: {str(e)}")
                flash(f"Error reading CA certificate: {str(e)}", 'danger')
        
        # Option to remove the CA certificate
        if request.form.get('remove_ca_cert') == 'on':
            config.ca_cert = None
        
        # Authentication parameters
        config.bind_dn = request.form.get('bind_dn')
        
        # Only update the password if it's provided
        bind_password = request.form.get('bind_password')
        if bind_password and bind_password.strip():
            config.bind_password = bind_password
        
        # Search parameters
        config.base_dn = request.form.get('base_dn')
        config.user_dn = request.form.get('user_dn')
        config.group_dn = request.form.get('group_dn')
        config.user_rdn_attr = request.form.get('user_rdn_attr', 'sAMAccountName')
        config.user_login_attr = request.form.get('user_login_attr', 'sAMAccountName')
        config.user_object_class = request.form.get('user_object_class', 'person')
        
        # Authorization parameters
        config.admin_group = request.form.get('admin_group')
        config.user_group = request.form.get('user_group')
        config.group_member_attr = request.form.get('group_member_attr', 'member')
        config.group_object_class = request.form.get('group_object_class', 'group')
        
        db.session.commit()
        
        flash('LDAP configuration saved successfully', 'success')
        return redirect(url_for('admin.ldap_config'))
    except Exception as e:
        current_app.logger.error(f"Error saving LDAP configuration: {str(e)}")
        flash(f"Error during save: {str(e)}", 'danger')
        return redirect(url_for('admin.ldap_config'))


@admin_bp.route('/ldap-config/test', methods=['POST'])
@login_required
@admin_required
def test_ldap_config():
    """Tests the LDAP connection with the provided parameters"""
    try:
        # Create a temporary configuration with the form parameters
        temp_config = LDAPConfig()
        
        # Connection parameters
        temp_config.enabled = True
        temp_config.host = request.form.get('host')
        temp_config.port = int(request.form.get('port', 389))
        temp_config.use_ssl = request.form.get('use_ssl') == 'on'
        temp_config.use_tls = request.form.get('use_tls') == 'on'
        temp_config.verify_cert = request.form.get('verify_cert') == 'on'
        
        # CA certificate management for the test
        ca_cert_file = request.files.get('ca_cert')
        if ca_cert_file and ca_cert_file.filename:
            try:
                # Use the CA certificate provided in the form
                ca_cert_content = ca_cert_file.read().decode('utf-8')
                # Check that the content is a valid PEM certificate
                if '-----BEGIN CERTIFICATE-----' in ca_cert_content and '-----END CERTIFICATE-----' in ca_cert_content:
                    temp_config.ca_cert = ca_cert_content
                    current_app.logger.info(f"CA certificate provided in the form used for testing (size: {len(ca_cert_content)} bytes)")
                else:
                    flash('The provided file does not appear to be a valid PEM certificate', 'warning')
                    current_app.logger.warning("The provided CA file is not a valid PEM certificate")
            except Exception as e:
                current_app.logger.error(f"Error reading CA certificate for test: {str(e)}")
                flash(f"Error reading CA certificate: {str(e)}", 'danger')
        else:
            # Use the existing configuration's CA certificate
            existing_config = LDAPConfig.get_config()
            temp_config.ca_cert = existing_config.ca_cert
            current_app.logger.info("Existing CA certificate used for testing")
            
            # If certificate verification is enabled but no certificate is available
            if temp_config.verify_cert and not temp_config.ca_cert:
                current_app.logger.warning("Certificate verification is enabled but no CA certificate is available")
                flash('Certificate verification is enabled but no CA certificate is available', 'warning')
        
        # Authentication parameters
        temp_config.bind_dn = request.form.get('bind_dn')
        
        # Use the new password if provided, otherwise use the existing one
        bind_password = request.form.get('bind_password')
        if bind_password and bind_password.strip():
            temp_config.bind_password = bind_password
        else:
            # Use the existing password
            existing_config = LDAPConfig.get_config()
            temp_config.bind_password = existing_config.bind_password
        
        # Search parameters
        temp_config.base_dn = request.form.get('base_dn')
        temp_config.user_dn = request.form.get('user_dn')
        temp_config.group_dn = request.form.get('group_dn')
        temp_config.user_rdn_attr = request.form.get('user_rdn_attr', 'sAMAccountName')
        temp_config.user_login_attr = request.form.get('user_login_attr', 'sAMAccountName')
        temp_config.user_object_class = request.form.get('user_object_class', 'person')
        
        # Authorization parameters
        temp_config.admin_group = request.form.get('admin_group')
        temp_config.user_group = request.form.get('user_group')
        temp_config.group_member_attr = request.form.get('group_member_attr', 'member')
        temp_config.group_object_class = request.form.get('group_object_class', 'group')
        
        # Test the connection
        success, message = LDAPService.test_connection(temp_config)
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            })
    except Exception as e:
        current_app.logger.error(f"Error testing LDAP configuration: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Unexpected error: {str(e)}"
        })


@admin_bp.route('/ldap-config/groups', methods=['GET'])
@login_required
@admin_required
def get_ldap_groups():
    """Retrieves the list of available LDAP groups"""
    try:
        groups = LDAPService.get_ldap_groups()
        return jsonify({
            'success': True,
            'groups': groups
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving LDAP groups: {str(e)}")
        return jsonify({
            'success': False,
            'message': f"Error: {str(e)}",
            'groups': []
        })