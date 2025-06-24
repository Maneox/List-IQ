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

@api_bp.route('/api/lists/<int:list_id>', methods=['PUT'])
@login_required
def update_list(list_id):
    """Update an existing list"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    list_obj = List.query.get_or_404(list_id)
    data = request.get_json()
    
    try:
        # Update basic fields
        if 'name' in data:
            list_obj.name = data['name']
        if 'description' in data:
            list_obj.description = data['description']
        if 'update_type' in data:
            list_obj.update_type = data['update_type']
        # Store the old schedule to detect changes
        old_schedule = list_obj.update_schedule
        if 'update_schedule' in data:
            list_obj.update_schedule = data['update_schedule']
            
            # Check if the schedule has been changed
            if old_schedule != list_obj.update_schedule and list_obj.update_type == 'automatic':
                current_app.logger.info(f"API: Schedule changed for list {list_obj.id}: {old_schedule} -> {list_obj.update_schedule}")
                try:
                    # Reschedule the task with the new schedule
                    scheduler = SchedulerService(current_app)
                    scheduler._schedule_list(list_obj)
                    current_app.logger.info(f"API: Task rescheduled successfully for list {list_obj.id}")
                except Exception as e:
                    current_app.logger.error(f"API: Error rescheduling task for list {list_obj.id}: {str(e)}")
        if 'update_config' in data:
            if isinstance(data['update_config'], dict):
                list_obj.set_update_config(data['update_config'])
        if 'is_active' in data:
            list_obj.is_active = data['is_active']
        if 'is_published' in data:
            list_obj.is_published = data['is_published']
        
        # Update columns
        if 'columns' in data:
            existing_columns = {col.name: col for col in list_obj.columns}
            new_columns = []
            
            for i, column_data in enumerate(data['columns']):
                column_name = column_data['name']
                if column_name in existing_columns:
                    # Update existing column
                    column = existing_columns[column_name]
                    column.position = i
                    column.column_type = column_data.get('type', column.column_type)
                    new_columns.append(column)
                else:
                    # Create a new column
                    new_column = ListColumn(
                        name=column_name,
                        position=i,
                        column_type=column_data.get('type', 'text')
                    )
                    new_columns.append(new_column)
            
            # Update the columns
            list_obj.columns = new_columns
        
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

@api_bp.route('/api/lists/<int:list_id>/import', methods=['POST'])
@login_required
def import_data(list_id):
    """Import data from a CSV file"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    # Debug logs
    current_app.logger.info(f"Looking for list with ID: {list_id}")
    list_obj = List.query.get_or_404(list_id)
    current_app.logger.info(f"Found list: {list_obj.name} (ID: {list_obj.id})")
    current_app.logger.info(f"List columns: {[f'{col.name} (pos: {col.position})' for col in list_obj.columns]}")
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
        
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Unsupported file format. Use CSV.'}), 400
    
    try:
        # Create a dictionary of columns for quick access
        columns_dict = {col.name: col for col in list_obj.columns}
        
        # Read the CSV file
        csv_content = file.read().decode('utf-8-sig')  # Handle UTF-8 BOM
        stream = io.StringIO(csv_content)
        csv_reader = csv.DictReader(stream)
        
        # Debug logs
        current_app.logger.info(f"CSV fieldnames: {csv_reader.fieldnames}")
        
        # Check columns
        if not csv_reader.fieldnames:
            return jsonify({'error': 'The CSV file is empty or poorly formatted'}), 400
            
        file_columns = set(csv_reader.fieldnames)
        list_columns = set(columns_dict.keys())
        
        if not file_columns.issubset(list_columns):
            invalid_columns = file_columns - list_columns
            return jsonify({
                'error': f'Invalid columns found: {", ".join(invalid_columns)}',
                'details': {
                    'file_columns': list(file_columns),
                    'expected_columns': list(list_columns)
                }
            }), 400
            
        # Import data
        row_count = 0
        error_rows = []
        
        for row_num, row in enumerate(csv_reader, start=1):
            try:
                # Validate and format the data
                validated_data = {}
                for col_name, value in row.items():
                    if col_name in columns_dict:
                        try:
                            validated_data[col_name] = validate_value(value, columns_dict[col_name].column_type)
                        except ValueError as ve:
                            raise ValueError(f"Row {row_num}, column '{col_name}': {str(ve)}")
                
                # Add validated data
                for col_name, value in validated_data.items():
                    column = columns_dict[col_name]
                    data = ListData(
                        list_id=list_obj.id,
                        row_id=row_num,
                        column_position=column.position,
                        value=value
                    )
                    db.session.add(data)
                
                row_count += 1
                
                # Commit every 100 rows to avoid memory overload
                if row_count % 100 == 0:
                    db.session.commit()
                    current_app.logger.info(f"Committed {row_count} rows")
                
            except Exception as e:
                error_rows.append({
                    'row': row_num,
                    'error': str(e),
                    'data': row
                })
                current_app.logger.error(f"Error on row {row_num}: {str(e)}")
                continue
        
        # Final commit
        if row_count % 100 != 0:
            db.session.commit()
        
        # Update the last update date
        list_obj.last_update = get_paris_now()
        db.session.commit()
        
        # Update public files if enabled
        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
            try:
                update_public_files(list_obj)
                current_app.logger.info(f"Public files updated for list {list_id} after import")
            except Exception as e:
                current_app.logger.error(f"Error updating public files after import: {str(e)}")
                # Do not block the response if updating public files fails
        
        # Prepare the response
        response = {
            'message': 'Import finished',
            'stats': {
                'total_rows': row_count,
                'successful_rows': row_count - len(error_rows),
                'error_rows': len(error_rows)
            }
        }
        
        if error_rows:
            response['errors'] = error_rows[:10]  # Limit to 10 errors in the response
            response['message'] = 'Import finished with errors'
            
        return jsonify(response)
        
    except Exception as e:
        current_app.logger.error(f"Import error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'error': 'Error during import',
            'details': str(e)
        }), 500

@api_bp.route('/api/lists/<int:list_id>/export', methods=['GET'])
@login_required
def export_list_data(list_id):
    """Export list data in CSV or JSON format"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    list_obj = List.query.get_or_404(list_id)
    format_type = request.args.get('format', 'csv')
    
    if format_type not in ['csv', 'json']:
        return jsonify({'error': 'Unsupported format'}), 400
    
    # Get the data
    data = list_obj.get_data()
    
    if format_type == 'json':
        return jsonify(data)
    else:  # CSV
        if not data:
            return jsonify({'error': 'No data to export'}), 404
            
        # Create the CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write the header
        headers = [col.name for col in list_obj.columns]
        writer.writerow(headers)
        
        # Write the data
        for row in data:
            writer.writerow([row.get(header, '') for header in headers])
        
        # Prepare the response
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{list_obj.name}_{get_paris_now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

@api_bp.route('/api/lists/<int:list_id>/rows/delete-multiple', methods=['POST'])
@login_required
def delete_multiple_rows(list_id):
    """Delete multiple data rows"""
    if not current_user.is_admin:
        return jsonify(UNAUTHORIZED_ACCESS), 403
        
    data = request.get_json()
    
    if not data or not data.get('row_ids'):
        return jsonify({'error': 'Row IDs required'}), 400
    
    row_ids = data.get('row_ids')
    
    try:
        # Delete the rows
        deleted_count = 0
        for row_id in row_ids:
            row = ListData.query.filter_by(list_id=list_id, id=row_id).first()
            if row:
                db.session.delete(row)
                deleted_count += 1
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'{deleted_count} row(s) deleted successfully'
        })
    except Exception as e:
        current_app.logger.error(f"Error during multiple deletion: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500