from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import login_required, current_user
from models.list import List
from services.list_service import ListService

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/')
def index():
    """Home page - Redirects to the lists page"""
    return redirect(url_for('ui.lists'))

@ui_bp.route('/lists')
@login_required
def lists():
    """Lists index page"""
    # Clear the SQLAlchemy session cache to force a data reload
    db.session.expire_all()
    
    # Get all lists directly from the database for verification
    all_lists = db.session.query(List.id, List.name, List.is_published).all()
    current_app.logger.info(f"ALL LISTS IN DB: {[(l.id, l.name, l.is_published) for l in all_lists]}")
    
    if current_user.is_admin:
        # Administrators see all lists
        lists = List.query.all()
        current_app.logger.info(f"ADMIN - All lists: {[l.name for l in lists]}")
    else:
        # Standard users only see published lists
        # Execute a raw SQL query to ensure filtering works
        from sqlalchemy import text
        result = db.session.execute(text("SELECT * FROM lists WHERE is_published = 1"))
        list_ids = [row[0] for row in result]
        current_app.logger.info(f"Published list IDs (raw SQL): {list_ids}")
        
        # Use these IDs to get the lists
        lists = List.query.filter(List.id.in_(list_ids)).all()
        current_app.logger.info(f"USER - Filtered lists: {[l.name for l in lists]}")
    
    return render_template('lists/index.html', lists=lists)

@ui_bp.route('/lists/new')
@login_required
def new_list():
    """New list creation page"""
    if not current_user.is_admin:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('ui.lists'))
    # Correction : passer list=None et columns=[] pour éviter erreur 500
    return render_template('lists/edit.html', list=None, columns=[])

@ui_bp.route('/lists/<int:list_id>')
@login_required
def view_list(list_id):
    """List view page"""
    list_obj = List.query.get_or_404(list_id)
    
    # Check permissions
    # Access allowed if:
    # 1. The user is an admin (can see all lists)
    # 2. The list is published (visible to all users)
    if not (current_user.is_admin or list_obj.is_published == 1):
        flash('Unauthorized access - This list is not published', 'danger')
        current_app.logger.info(f"UI - Access denied to list {list_id} for user {current_user.id} - is_published: {list_obj.is_published}")
        return redirect(url_for('ui.lists'))
        
    # Check IP restrictions if enabled
    if list_obj.ip_restriction_enabled:
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if not list_obj.is_ip_allowed(client_ip):
            flash('Access from this IP is not authorized', 'danger')
            return redirect(url_for('ui.lists'))
    
    # Get the list data
    list_data = list_obj.get_data()
    
    return render_template('lists/view.html', list=list_obj, list_data=list_data)

@ui_bp.route('/lists/<int:list_id>/edit')
@login_required
def edit_list(list_id):
    """List edit page"""
    list_obj = List.query.get_or_404(list_id)
    
    # Modification allowed only if the user is an admin
    if not current_user.is_admin:
        flash('Unauthorized access - Only administrators can edit lists', 'danger')
        return redirect(url_for('ui.lists'))
    return render_template('lists/edit.html', list=list_obj)