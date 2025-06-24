from flask import Blueprint, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models.list import List, ListColumn, ListData
from database import db
import csv
import io
import json
from datetime import datetime
import ipaddress
from typing import Any, Dict

# Constants
UNAUTHORIZED_ACCESS = {'error': 'Unauthorized access'}

# Import timezone utilities
from utils.timezone_utils import get_paris_now, utc_to_paris, PARIS_TIMEZONE, format_datetime
from services.public_files_service import update_public_files
from services.scheduler_service import SchedulerService

api_bp = Blueprint('api_bp', __name__)

def validate_value(value: str, column_type: str) -> str:
    """Validates and formats a value according to the column type"""
    if not value or value.strip() == '':
        return ''
        
    try:
        if column_type == 'ip':
            # Validate the IP address
            ipaddress.ip_address(value.strip())
            return value.strip()
        elif column_type == 'number':
            # Validate the number
            float(value.strip())
            return value.strip()
        elif column_type == 'date':
            # Validate the date (ISO format)
            datetime.fromisoformat(value.strip())
            return value.strip()
        else:  # text
            return value.strip()
    except Exception:
        raise ValueError(f"Invalid value for type {column_type}: {value}")

@api_bp.route('/api/lists', methods=['POST'])
@login_required
def create_list():
    """Create a new list"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400
            
        # Create the list
        list_obj = List(
            name=data['name'],
            description=data.get('description', ''),
            update_type=data.get('update_type', 'manual'),
            is_active=data.get('is_active', True),
            is_published=data.get('is_published', False)
        )
        db.session.add(list_obj)
        db.session.flush()
        
        # Add the columns
        if data.get('columns'):
            for i, col in enumerate(data['columns']):
                column = ListColumn(
                    list=list_obj,
                    name=col['name'],
                    position=col.get('position', i),
                    column_type=col.get('type', 'text')
                )
                db.session.add(column)
        
        db.session.commit()
        
        # Update public files if enabled
        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
            try:
                update_public_files(list_obj)
                current_app.logger.info(f"Public files updated for list {list_obj.id} after import")
            except Exception as e:
                current_app.logger.error(f"Error updating public files after import: {str(e)}")
                # Do not block the response if updating public files fails
        
        return jsonify({
            'message': 'List created successfully',
            'list_id': list_obj.id
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"Error creating list: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def _validate_import_file(request_files):
    """Validates the uploaded file."""
    if 'file' not in request_files:
        raise ValueError('No file provided')
    file = request_files['file']
    if file.filename == '':
        raise ValueError('No file selected')
    if not file.filename.endswith('.csv'):
        raise ValueError('Unsupported file format. Use CSV.')
    return file

def _validate_csv_columns(csv_reader, list_columns):
    """Validates the columns of the CSV file."""
    if not csv_reader.fieldnames:
        raise ValueError('The CSV file is empty or poorly formatted')
    file_columns = set(csv_reader.fieldnames)
    if not file_columns.issubset(list_columns):
        invalid_columns = file_columns - list_columns
        invalid_cols_str = ', '.join(invalid_columns)
        raise ValueError(f'Invalid columns found: {invalid_cols_str}')

def _process_import_row(row_num, row, columns_dict, list_id):
    """Processes and validates a single row from the CSV."""
    validated_data = {}
    for col_name, value in row.items():
        if col_name in columns_dict:
            try:
                validated_data[col_name] = validate_value(value, columns_dict[col_name].column_type)
            except ValueError as ve:
                raise ValueError(f"Row {row_num}, column '{col_name}': {str(ve)}")
    
    for col_name, value in validated_data.items():
        column = columns_dict[col_name]
        data = ListData(
            list_id=list_id,
            row_id=row_num,
            column_position=column.position,
            value=value
        )
        db.session.add(data)

def _update_public_files_safely(list_obj):
    """Updates public files and logs errors without raising them."""
    if list_obj.public_csv_enabled or list_obj.public_json_enabled:
        try:
            update_public_files(list_obj)
            current_app.logger.info(f"Public files updated for list {list_obj.id} after import")
        except Exception as e:
            current_app.logger.error(f"Error updating public files after import: {str(e)}")

@api_bp.route('/api/lists/<int:list_id>/import', methods=['POST'])
@login_required
def import_data(list_id):
    """Import data from a CSV file"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403

    list_obj = List.query.get_or_404(list_id)
    
    try:
        file = _validate_import_file(request.files)
        columns_dict = {col.name: col for col in list_obj.columns}
        
        csv_content = file.read().decode('utf-8-sig')
        stream = io.StringIO(csv_content)
        csv_reader = csv.DictReader(stream)
        
        _validate_csv_columns(csv_reader, set(columns_dict.keys()))
        
        row_count = 0
        error_rows = []
        for row_num, row in enumerate(csv_reader, start=1):
            try:
                _process_import_row(row_num, row, columns_dict, list_obj.id)
                row_count += 1
                if row_count % 100 == 0:
                    db.session.commit()
            except Exception as e:
                error_rows.append({'row': row_num, 'error': str(e), 'data': row})
                current_app.logger.error(f"Error on row {row_num}: {str(e)}")

        db.session.commit()
        list_obj.last_update = get_paris_now()
        db.session.commit()
        
        _update_public_files_safely(list_obj)

        response = {
            'message': 'Import finished',
            'stats': {
                'total_rows': row_count + len(error_rows),
                'successful_rows': row_count,
                'error_rows': len(error_rows)
            }
        }
        if error_rows:
            response['errors'] = error_rows[:10]
            response['message'] = 'Import finished with errors'
        
        return jsonify(response)

    except Exception as e:
        current_app.logger.error(f"Import error for list {list_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Error during import', 'details': str(e)}), 500

def _update_basic_fields(list_obj, data):
    """Updates basic fields of a list object from request data."""
    if 'name' in data:
        list_obj.name = data['name']
    if 'description' in data:
        list_obj.description = data['description']
    if 'update_type' in data:
        list_obj.update_type = data['update_type']
    if 'is_active' in data:
        list_obj.is_active = data['is_active']
    if 'is_published' in data:
        list_obj.is_published = data['is_published']
    if 'update_config' in data and isinstance(data['update_config'], dict):
        list_obj.set_update_config(data['update_config'])

def _update_schedule(list_obj, data, app_context):
    """Updates the schedule for a list and reschedules the task if necessary."""
    old_schedule = list_obj.update_schedule
    if 'update_schedule' in data:
        list_obj.update_schedule = data['update_schedule']
        
        if old_schedule != list_obj.update_schedule and list_obj.update_type == 'automatic':
            app_context.logger.info(f"API: Schedule changed for list {list_obj.id}: {old_schedule} -> {list_obj.update_schedule}")
            try:
                scheduler = SchedulerService(app_context)
                scheduler._schedule_list(list_obj)
                app_context.logger.info(f"API: Task rescheduled successfully for list {list_obj.id}")
            except Exception as e:
                app_context.logger.error(f"API: Error rescheduling task for list {list_obj.id}: {str(e)}")

def _update_columns(list_obj, data):
    """Updates the columns of a list from request data."""
    if 'columns' in data:
        existing_columns = {col.name: col for col in list_obj.columns}
        new_columns = []
        
        for i, column_data in enumerate(data['columns']):
            column_name = column_data['name']
            if column_name in existing_columns:
                column = existing_columns[column_name]
                column.position = i
                column.column_type = column_data.get('type', column.column_type)
                new_columns.append(column)
            else:
                new_column = ListColumn(
                    name=column_name,
                    position=i,
                    column_type=column_data.get('type', 'text')
                )
                new_columns.append(new_column)
        
        list_obj.columns = new_columns

@api_bp.route('/api/lists/<int:list_id>', methods=['PUT'])
@login_required
def update_list(list_id):
    """Update an existing list"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    list_obj = List.query.get_or_404(list_id)
    data = request.get_json()
    
    try:
        _update_basic_fields(list_obj, data)
        _update_schedule(list_obj, data, current_app)
        _update_columns(list_obj, data)
        
        db.session.commit()
        return jsonify({
            'message': 'List updated successfully',
            'id': list_obj.id
        })
    except Exception as e:
        current_app.logger.error(f"Error during update: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/api/lists/<int:list_id>', methods=['DELETE'])
@login_required
def delete_list(list_id):
    """Delete a list and all its associated data"""
    if not current_user.is_admin:
        current_app.logger.warning(f"Attempt to delete list {list_id} by a non-admin user")
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    try:
        # Get the list
        list_obj = List.query.get_or_404(list_id)
        current_app.logger.info(f"Attempting to delete list {list_id} - {list_obj.name}")
        
        # Check if the list can be deleted
        if list_obj.is_published:
            current_app.logger.warning(f"Attempt to delete published list {list_id}")
            return jsonify({
                'error': 'Cannot delete a published list',
                'details': 'Please unpublish the list first'
            }), 400
            
        # Get stats for the log
        columns_count = len(list_obj.columns)
        data_count = ListData.query.filter_by(list_id=list_id).count()
        
        current_app.logger.info(f"Deleting list {list_id} with {columns_count} columns and {data_count} entries")
        
        # Delete the list (cascade delete will handle columns and data)
        db.session.delete(list_obj)
        db.session.commit()
        
        current_app.logger.info(f"List {list_id} deleted successfully")
        return jsonify({
            'message': 'List deleted successfully',
            'details': {
                'list_id': list_id,
                'name': list_obj.name,
                'columns_deleted': columns_count,
                'data_entries_deleted': data_count
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error deleting list {list_id}: {str(e)}")
        db.session.rollback()
        return jsonify({
            'error': 'Error deleting the list',
            'details': str(e)
        }), 500

@api_bp.route('/api/lists/<int:list_id>/data/<int:row_id>', methods=['DELETE'])
@login_required
def delete_row(list_id, row_id):
    """Delete a data row"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    list_obj = List.query.get_or_404(list_id)
    row = ListData.query.filter_by(list_id=list_id, id=row_id).first_or_404()
    
    try:
        db.session.delete(row)
        db.session.commit()
        
        # Update public files if enabled
        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
            try:
                update_public_files(list_obj)
                current_app.logger.info(f"Public files updated for list {list_id} after deletion")
            except Exception as e:
                current_app.logger.error(f"Error updating public files after deletion: {str(e)}")
                # Do not block the response if updating public files fails
        
        return jsonify({'message': 'Row deleted successfully'})
    except Exception as e:
        current_app.logger.error(f"Error deleting row: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/api/lists/<int:list_id>/data/<int:row_id>', methods=['GET'])
@login_required
def get_row(list_id, row_id):
    """Get a data row"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    list_obj = List.query.get_or_404(list_id)
    data = list_obj.get_data()
    row = next((row for row in data if row.get('id') == row_id), None)
    
    if not row:
        return jsonify({'error': 'Row not found'}), 404
        
    return jsonify(row)

@api_bp.route('/api/lists/<int:list_id>/data/<int:row_id>', methods=['PUT'])
@login_required
def update_row(list_id, row_id):
    """Update a data row"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    list_obj = List.query.get_or_404(list_id)
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Invalid data'}), 400
    
    try:
        # Update each column
        for column in list_obj.columns:
            if column.name in data:
                # Validate the value
                value = validate_value(data[column.name], column.column_type)
                
                # Update or create the data
                row_data = ListData.query.filter_by(
                    list_id=list_id,
                    row_id=row_id,
                    column_position=column.position
                ).first()
                
                if row_data:
                    row_data.value = value
                else:
                    row_data = ListData(
                        list_id=list_id,
                        row_id=row_id,
                        column_position=column.position,
                        value=value
                    )
                    db.session.add(row_data)
        
        db.session.commit()
        
        # Update public files if enabled
        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
            try:
                update_public_files(list_obj)
                current_app.logger.info(f"Public files updated for list {list_id}")
            except Exception as e:
                current_app.logger.error(f"Error updating public files: {str(e)}")
                # Do not block the response if updating public files fails
        
        return jsonify({'message': 'Row updated successfully'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Error during update: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500