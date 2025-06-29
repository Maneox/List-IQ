from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, current_app, send_file, session, g
from flask_login import login_required, current_user
from ..models.list import List, ListColumn, ListData
from ..models.user import User
from ..database import db, csrf
from datetime import datetime
import json
import csv
import io
import re
import os
import requests

# Import timezone utilities
from ..utils.timezone_utils import get_paris_now, utc_to_paris, PARIS_TIMEZONE, format_datetime
import uuid
import subprocess
import ipaddress
from sqlalchemy import text, exc
from sqlalchemy.orm import joinedload
from functools import wraps
from .api_auth_routes import token_auth_required
from ..services.scheduler_service import SchedulerService
from .decorators import admin_required
from ..services.public_files_service import update_public_files

list_bp = Blueprint('list_bp', __name__)

# Route to access the JSON configuration of a list
@list_bp.route('/lists/<int:list_id>/json-config', methods=['GET'])
@login_required
def json_config_redirect(list_id):
    """Redirect to the JSON configuration page"""
    list_obj = List.query.get_or_404(list_id)
    
    # Check if the list uses the Curl API
    config = list_obj.update_config
    if list_obj.update_type == 'automatic' and config and config.get('source') == 'api' and config.get('api_type') == 'curl':
        # Redirect to the new URL path
        return redirect(url_for('json_config_bp.json_config', list_id=list_id))
    else:
        flash('This list does not require JSON configuration', 'warning')
        return redirect(url_for('list_bp.view_list', list_id=list_id))

@list_bp.route('/lists/<int:list_id>/csv-config', methods=['GET'])
@login_required
@admin_required
def csv_config(list_id):
    """Displays the CSV configuration page"""
    list_obj = List.query.get_or_404(list_id)
    
    # Check if the list is of automatic type and uses CSV format
    update_config = list_obj.get_update_config
    is_csv = False
    
    if list_obj.update_type == 'automatic':
        if 'format' in update_config and update_config['format'] == 'csv':
            is_csv = True
        elif 'is_json' in update_config and not update_config['is_json']:
            is_csv = True
    
    if not is_csv:
        flash('This list does not require CSV configuration', 'warning')
        return redirect(url_for('list_bp.view_list', list_id=list_id))
    
    return render_template('lists/csv_config.html', list=list_obj)

@list_bp.route('/lists/<int:list_id>/preview-csv', methods=['POST'])
@login_required
@csrf.exempt
def preview_csv(list_id):
    """Generates a preview of the CSV data"""
    try:
        # Debug log for the complete request
        current_app.logger.info(f"====== Start of preview_csv request ======")
        current_app.logger.info(f"Request received: {request.method} {request.path}")
        current_app.logger.info(f"Headers: {dict(request.headers)}")
        current_app.logger.info(f"Raw content: {request.data.decode('utf-8', errors='replace') if request.data else 'No content'}")
        current_app.logger.info(f"Content-Type: {request.content_type}")
        current_app.logger.info(f"Mimetype: {request.mimetype}")
        
        # Check if the list ID is valid
        try:
            list_obj = List.query.get_or_404(list_id)
            current_app.logger.info(f"List found: ID={list_obj.id}, Name={list_obj.name}")
        except Exception as e:
            current_app.logger.error(f"Error getting list {list_id}: {str(e)}")
            return jsonify({'error': f"List not found: {str(e)}"}), 404
        
        # Check if the data is in JSON format
        if not request.is_json:
            current_app.logger.error(f"Data is not in JSON format. Content-Type: {request.content_type}")
            return jsonify({'error': 'Data must be in JSON format. Make sure the Content-Type is application/json'}), 400
        
        # Try to parse the JSON data
        try:
            data = request.get_json(force=True, silent=False)
            current_app.logger.info(f"Received JSON data: {data}")
        except Exception as e:
            current_app.logger.error(f"Error parsing JSON: {str(e)}")
            return jsonify({'error': f'Could not parse JSON data: {str(e)}'}), 400
        
        # Check if the data is null or empty
        if data is None:
            current_app.logger.error("Null JSON data")
            return jsonify({'error': 'Null or invalid JSON data'}), 400
        
        # Check if the data contains the required fields
        if 'separator' not in data:
            current_app.logger.error("'separator' field missing from JSON data")
            return jsonify({'error': "The 'separator' field is required"}), 400
        
        if 'has_header' not in data:
            current_app.logger.error("'has_header' field missing from JSON data")
            return jsonify({'error': "The 'has_header' field is required"}), 400
        
        # Log received data for debugging
        current_app.logger.info(f"Data received for preview: {data}")        # Get configuration parameters
        separator = data.get('separator', ',')
        
        # Handle special separators like tab
        if separator == '\\t':
            separator = '\t'  # Convert to a real tab character
        elif separator == '\\n':
            separator = '\n'  # Convert to a real newline character
        elif separator == '\\r':
            separator = '\r'  # Convert to a real carriage return character
        
        has_header = data.get('has_header', True)
        column_names = data.get('column_names', [])
        
        # Log received parameters for debugging
        current_app.logger.info(f"CSV preview parameters: separator='{separator}', has_header={has_header}, column_names={column_names}")
        
        # Get the data source URL
        current_app.logger.info(f"Getting update configuration for list {list_obj.id}")
        update_config = list_obj.get_update_config
        current_app.logger.info(f"Update configuration: {update_config}")
        
        url = update_config.get('url') if update_config else None
        current_app.logger.info(f"URL extracted from configuration: {url}")
        
        if not url:
            current_app.logger.error("No data source URL defined")
            return jsonify({'error': 'No data source URL defined. Please configure a URL in the list settings.'}), 400
        
        current_app.logger.info(f"Getting data from URL: {url}")
        
        # Get data from the URL
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            csv_content = response.content.decode('utf-8')
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error getting data from URL: {str(e)}")
            return jsonify({'error': f"Error getting data: {str(e)}"}), 400
        except UnicodeDecodeError as e:
            current_app.logger.error(f"Error decoding CSV content: {str(e)}")
            return jsonify({'error': f"Error decoding CSV content: {str(e)}"}), 400
        
        # Check that the content is not empty
        if not csv_content.strip():
            current_app.logger.error("The CSV content is empty")
            return jsonify({'error': 'The CSV content is empty'}), 400
        
        # Log the first few lines of the CSV content for debugging
        preview_lines = csv_content.split('\n')[:3]
        current_app.logger.info(f"CSV content preview:\n{preview_lines}")
        
        # Process the CSV data
        csv_file = io.StringIO(csv_content)
        
        try:
            # Log for debugging
            current_app.logger.info(f"Processing CSV with separator: '{separator}', has_header: {has_header}")
            
            # Read data with the specified separator
            if has_header:
                # Read the first line as the header
                csv_reader = csv.reader(csv_file, delimiter=separator)
                headers = next(csv_reader)
                current_app.logger.info(f"Headers detected: {headers}")
            else:
                # Use manual column names if provided
                csv_reader = csv.reader(csv_file, delimiter=separator)
                
                # Read the first line to determine the number of columns
                first_line = next(csv_reader)
                csv_file.seek(0)  # Reset the cursor
                csv_reader = csv.reader(csv_file, delimiter=separator)
                
                # Generate column names
                if column_names and len(column_names) > 0:
                    # Use the provided names, complete if necessary
                    headers = column_names
                    if len(headers) < len(first_line):
                        headers.extend([f'Col{i+1}' for i in range(len(headers), len(first_line))])
                else:
                    # Generate names automatically
                    headers = [f'Col{i+1}' for i in range(len(first_line))]
                
                current_app.logger.info(f"Column names used: {headers}")
            
            # Read a sample of data (up to 10 rows)
            data = []
            row_count = 0
            
            # If no header, reset the cursor to include the first row
            if not has_header:
                csv_file.seek(0)
                csv_reader = csv.reader(csv_file, delimiter=separator)
            
            for row in csv_reader:
                if row:  # Ignore empty rows
                    data.append(row)
                    row_count += 1
                    if row_count >= 10:  # Limit to 10 rows
                        break
            
            current_app.logger.info(f"Preview: {row_count} rows read")
            
            # Prepare the response
            preview = {
                'headers': headers,
                'data': data
            }
            
            return jsonify({'preview': preview})
        
        except Exception as e:
            current_app.logger.error(f"Error during CSV preview: {str(e)}")
            current_app.logger.exception(e)  # Log the full exception
            return jsonify({'error': f"Error during preview: {str(e)}"}), 500
        
    except Exception as e:
        current_app.logger.error(f"Error during CSV preview: {str(e)}")
        return jsonify({'error': str(e)}), 400

@list_bp.route('/lists/<int:list_id>/save-csv-config', methods=['POST'])
@login_required
@admin_required
@csrf.exempt
def save_csv_config(list_id):
    """Saves the CSV configuration and imports the data"""
    try:
        list_obj = List.query.get_or_404(list_id)
        data = request.get_json()        # Get configuration parameters
        separator = data.get('separator', ',')
        
        # Handle special separators like tab
        if separator == '\\t':
            separator = '\t'  # Convert to a real tab character
        elif separator == '\\n':
            separator = '\n'  # Convert to a real newline character
        elif separator == '\\r':
            separator = '\r'  # Convert to a real carriage return character
        
        # Check that the separator is a single character
        if len(separator) != 1:
            current_app.logger.error(f"The separator '{separator}' is not a single character")
            return jsonify({'error': "The separator must be a single character"}), 400
            
        has_header = data.get('has_header', True)
        column_names = data.get('column_names', [])
        columns_to_import = data.get('columns_to_import', [])
        column_types = data.get('column_types', {})
        preview_enabled = data.get('preview_enabled', True)
        
        # Log received parameters for debugging
        current_app.logger.info(f"CSV configuration parameters: separator='{separator}', has_header={has_header}, column_names={column_names}, columns_to_import={columns_to_import}, column_types={column_types}")
        
        # Update the list's configuration
        update_config = list_obj.get_update_config
        
        # Ensure the format is set to CSV
        update_config['format'] = 'csv'
        update_config['is_json'] = False
        
        # Add the CSV configuration
        update_config['csv_config'] = {
            'separator': separator,
            'has_header': has_header,
            'preview_columns': preview_enabled,
            'remove_unused_columns': True  # Option to remove unused columns
        }
        
        # Add column names if necessary
        if not has_header and column_names:
            update_config['csv_config']['column_names'] = column_names
        
        # Add columns to import if preview is enabled
        if preview_enabled and columns_to_import:
            update_config['csv_config']['columns_to_import'] = columns_to_import
            
        # Add column types if provided
        if column_types:
            update_config['csv_config']['column_types'] = column_types
        
        # Save the configuration
        list_obj.update_config = json.dumps(update_config)
        db.session.commit()
        
        # Import the data
        try:
            # Force refresh of list properties to ensure the configuration is applied
            db.session.refresh(list_obj)
            
            # Import data with the new configuration using DataImporter
            from ..models.data_importer import DataImporter
            importer = DataImporter(list_obj)
            row_count = importer.import_data(force_update=True)
            flash(f'{row_count if row_count is not None else 0} rows imported successfully', 'success')
        except Exception as import_error:
            # Keep only the flash message for the user
            flash(f"Error importing data: {str(import_error)}", 'danger')
        
        return jsonify({'success': True})
        
    except Exception as e:
        # Simplify error handling
        return jsonify({'error': str(e)}), 400

def check_ip_restriction(f):
    @wraps(f)
    def decorated_function(list_id, *args, **kwargs):
        list_obj = List.query.get(list_id)
        if not list_obj:
            return jsonify({'error': 'List not found'}), 404
            
        if list_obj.ip_restriction_enabled:
            # Get client IP, considering different possible configurations
            # Priority order for IP detection
            client_ip = None
            
            # Detailed debug of HTTP headers for IP detection
            print("\n" + "=" * 50)
            print(f"REQUEST TO: {request.path}")
            print(f"REMOTE ADDRESS: {request.remote_addr}")
            print("IP HEADER CONTENTS:")
            
            # Display the content of each specific header
            headers_to_check = ['True-Client-IP', 'X-Client-IP', 'X-Real-IP', 'X-Forwarded-For']
            for header in headers_to_check:
                value = request.headers.get(header, 'NOT PRESENT')
                print(f"  {header}: {value}")
            print("=" * 50 + "\n")
            
            # 1. Check common headers for proxies
            # Priority order for headers
            for header in headers_to_check:
                if header in request.headers and request.headers[header]:
                    client_ip = request.headers[header]
                    current_app.logger.info(f"IP detected from header {header}: {client_ip}")
                    break
                    
            # Add extra logs for debugging
            current_app.logger.info(f"Environment: {current_app.config.get('ENV', 'not defined')}")
            current_app.logger.info(f"Server address: {request.host}")
            
            # 2. If no IP is found in the headers, use the remote IP
            if not client_ip:
                client_ip = request.remote_addr
                current_app.logger.info(f"IP detected from remote_addr: {client_ip}")
            
            # Save the original IP for the error message
            original_ip = client_ip
            
            # If X-Forwarded-For contains multiple IPs, take the first one (real client)
            if client_ip and ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()
                current_app.logger.info(f"IP extracted from list: {client_ip}")
            
            # Log all information for debugging
            current_app.logger.info(f"Final client IP: {client_ip}")
            current_app.logger.info(f"Request headers: {dict(request.headers)}")
            current_app.logger.info(f"Remote addr: {request.remote_addr}")
            
            if not list_obj.is_ip_allowed(client_ip):
                # Store error information in the session for the error handler
                session['ip_error_info'] = {
                    'detected_ip': client_ip,
                    'original_header': original_ip,
                    'remote_addr': request.remote_addr,
                    'allowed_ips': list_obj.allowed_ips
                }
                # Use abort(403) to trigger the custom error handler
                abort(403)
                
        return f(list_id, *args, **kwargs)
    return decorated_function

def check_list_access(f):
    @wraps(f)
    def decorated_function(list_id, *args, **kwargs):
        list_obj = List.query.get(list_id)
        if not list_obj:
            return jsonify({'error': 'List not found'}), 404
        
        # Access allowed if:
        # 1. The user is an admin (can see all lists)
        # 2. The list is published (visible to all users)
        if current_user.is_admin or list_obj.is_published == 1:
            return f(list_id, *args, **kwargs)
        
        # Log for debugging
        current_app.logger.info(f"Access denied to list {list_id} for user {current_user.id} - is_published: {list_obj.is_published}")
        
        return jsonify({'error': 'Unauthorized access - This list is not published'}), 403
    return decorated_function

def check_list_ownership(f):
    @wraps(f)
    def decorated_function(list_id, *args, **kwargs):
        list_obj = List.query.get(list_id)
        if not list_obj:
            return jsonify({'error': 'List not found'}), 404
        
        # Modification allowed only if the user is an admin
        if current_user.is_admin:
            return f(list_id, *args, **kwargs)
        
        return jsonify({'error': 'Unauthorized access - Only administrators can modify lists'}), 403
    return decorated_function

def format_date_for_db(date_str):
    """Converts a date to DD/MM/YYYY format"""
    if not date_str:
        return None
        
    try:
        # If the date is already in DD/MM/YYYY format
        if len(date_str.split('/')) == 3:
            date_obj = datetime.strptime(date_str, '%d/%m/%Y')
            return date_str
            
        # Otherwise, try to parse and convert
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%d/%m/%Y')
        
    except ValueError as e:
        raise ValueError(f"Invalid date format. Use DD/MM/YYYY format: {str(e)}")

@list_bp.route('/lists/<int:list_id>')
@login_required
@check_list_access
@check_ip_restriction
def view_list(list_id):
    """Displays a specific list"""
    try:
        # Get the list
        list_obj = List.query.get_or_404(list_id)
        
        # Get all data for the list
        current_app.logger.info(f"Getting data for list {list_id}")
        
        # Check if the list has data
        data_count = db.session.query(db.func.count(ListData.id)).filter(ListData.list_id == list_id).scalar()
        current_app.logger.info(f"Number of data entries for list {list_id}: {data_count}")
        
        # Get all columns for the list
        columns = db.session.query(ListColumn).filter(ListColumn.list_id == list_id).order_by(ListColumn.position).all()
        current_app.logger.info(f"Columns for list {list_id}: {[col.name for col in columns]}")
        
        # Debug: Display columns with their positions
        for col in columns:
            current_app.logger.info(f"Column: {col.name}, Position: {col.position}, ID: {col.id}")
        
        # Debug: Display raw data
        raw_data = db.session.query(
            ListData.row_id,
            ListData.column_position,
            ListData.value
        ).filter(
            ListData.list_id == list_id
        ).all()
        
        for data in raw_data:
            current_app.logger.info(f"Raw data: row_id={data.row_id}, column_position={data.column_position}, value={data.value}")
        
        # Create a dictionary to map positions to column names
        position_to_name = {col.position: col.name for col in columns}
        current_app.logger.info(f"Position -> name mapping: {position_to_name}")
        
        # Get all list data with a direct approach
        # Create a query that gets all data with column names
        data_with_names = []
        for data in raw_data:
            if data.column_position in position_to_name:
                data_with_names.append({
                    'row_id': data.row_id,
                    'column_name': position_to_name[data.column_position],
                    'value': data.value
                })
                current_app.logger.info(f"Data with name: row_id={data.row_id}, column_name={position_to_name[data.column_position]}, value={data.value}")
            else:
                current_app.logger.warning(f"Column position {data.column_position} not found in mapping")
        
        # Organize data by row
        rows = {}
        for data in data_with_names:
            if data['row_id'] not in rows:
                rows[data['row_id']] = {'row_id': data['row_id']}
            
            # Add the value to the row's dictionary
            rows[data['row_id']][data['column_name']] = data['value']
            current_app.logger.info(f"Associated value '{data['value']}' with column '{data['column_name']}' for row {data['row_id']}")

        # Convert the dictionary to a list
        rows_list = list(rows.values())
        
        return render_template(
            'lists/view.html',
            list=list_obj,
            rows=rows_list,
            title=list_obj.name
        )
        
    except Exception as e:
        current_app.logger.error(f"Error displaying list {list_id}: {str(e)}")
        current_app.logger.exception(e)
        flash('An error occurred while displaying the list: ' + str(e), 'error')
        return redirect(url_for('list_bp.lists_ui'))

@list_bp.route('/api/lists', methods=['POST'])
@token_auth_required
def create_list():
    try:
        data = request.get_json()
        
        # Get the admin logger for administrative actions
        admin_logger = current_app.config.get('ADMIN_LOGGER')
        
        # Log the list creation attempt
        if admin_logger:
            ip_address = request.remote_addr
            user_info = "Unknown user"
            if hasattr(g, 'current_user') and g.current_user:
                user_info = f"{g.current_user.username} (ID: {g.current_user.id})"
            admin_logger.info(f"List creation attempt - User: {user_info} - IP: {ip_address}")
        
        current_app.logger.info(f"Data received: {data}")
        
        # Check that columns are well defined
        columns = data.get('columns', [])
        current_app.logger.info(f"Columns received: {columns}")
        
        if not isinstance(columns, list):
            return jsonify({'error': 'The columns field must be a list'}), 400
        
        formatted_columns = []
        for idx, col in enumerate(columns):
            if not isinstance(col, dict) or 'name' not in col:
                return jsonify({'error': 'Each column must have at least a name field'}), 400
            
            column = {
                'name': col['name'],
                'position': idx,
                'column_type': col.get('column_type', 'text')  # Changed from type to column_type
                }
            formatted_columns.append(column)
        
        current_app.logger.info(f"Formatted columns: {formatted_columns}")
        
        # Debug received data
        current_app.logger.info(f"Received data: {data}")
        
        # Prepare the update configuration
        # If update_config is already provided in the data, use it as a base
        update_config = {}
        if 'update_config' in data:
            if isinstance(data.get('update_config'), dict):
                update_config = data.get('update_config')
            elif isinstance(data.get('update_config'), str):
                try:
                    update_config = json.loads(data.get('update_config'))
                    current_app.logger.info(f"JSON configuration parsed successfully")
                except json.JSONDecodeError as e:
                    current_app.logger.error(f"Error parsing update_config: {e}")
        
        current_app.logger.info(f"Initial configuration: {update_config}")
        
        # Check if the format is specified in the configuration
        if 'format' in update_config:
            current_app.logger.info(f"Format specified in configuration: {update_config['format']}")
            data_source_format = update_config['format']
        else:
            data_source_format = data.get('data_source_format')
            current_app.logger.info(f"Format specified in data: {data_source_format}")
        
        # Get the source from update_config if available
        source = 'url'  # Default value
        if isinstance(data.get('update_config'), dict) and 'source' in data.get('update_config'):
            source = data.get('update_config').get('source')
        else:
            source = data.get('source', 'url')
            
        current_app.logger.info(f"Detected source: {source}")
        
        # Initialize data_source_url here to avoid UnboundLocalError
        data_source_url = None
        
        # Check if the URL is in data or in update_config
        url = data.get('url') or data.get('data_source_url')
        
        # Check if the URL is in update_config
        if not url and isinstance(data.get('update_config'), dict) and 'url' in data.get('update_config'):
            url = data.get('update_config').get('url')
        elif not url and isinstance(data.get('update_config'), str):
            try:
                update_config_dict = json.loads(data.get('update_config'))
                if isinstance(update_config_dict, dict) and 'url' in update_config_dict:
                    url = update_config_dict.get('url')
            except json.JSONDecodeError:
                pass
        
        current_app.logger.info(f"Extracted URL: {url}")
        
        if data.get('update_type') == 'automatic':
            # Preserve existing values in update_config if they exist
            # Only set the source if it is not already set
            if 'source' not in update_config:
                update_config['source'] = source
            
            # Debug configuration values
            current_app.logger.info(f"Configuration after processing: {update_config}")
            
            # Check if URL is provided for the 'url' source
            if update_config.get('source') == 'url' and not url:
                current_app.logger.error(f"Missing URL for 'url' source. Data: {data}")
                return jsonify({'error': "URL is required for 'url' source"}), 400
            
            # Always include the URL if it is provided and the source is 'url'
            if url and update_config.get('source') == 'url':
                update_config['url'] = url
                # Ensure data_source_url is also set
                data_source_url = url
                
            # Determine if the format is JSON based on data_source_format or update_config
            # First check if is_json is already defined in update_config
            if 'is_json' in update_config:
                # Preserve the existing value
                current_app.logger.info(f"Using is_json already defined in update_config: {update_config['is_json']}")
                is_json = update_config['is_json']
            else:
                # Otherwise, determine based on data_source_format
                is_json = data.get('is_json', False)
                if data.get('data_source_format') == 'json':
                    is_json = True
                elif data.get('data_source_format') == 'csv':
                    is_json = False
                update_config['is_json'] = is_json
                current_app.logger.info(f"is_json set to {is_json} based on data_source_format")
            
            # Ensure the format is correctly saved in update_config
            if 'format' not in update_config and data.get('data_source_format'):
                update_config['format'] = data.get('data_source_format')
                
        # The data format has already been retrieved above
        auto_create_columns = data.get('auto_create_columns', True)
        
        try:
            # Create the list without importing data immediately
            # Temporarily disable auto_create_columns to avoid automatic import
            auto_create_columns_original = auto_create_columns
            
            try:
                # Create the list without auto-creation of columns
                # Update the configuration to include the URL if necessary
                if data_source_url and 'url' not in update_config:
                    update_config['url'] = data_source_url
                
                # Check if is_json is already defined in the configuration
                if 'is_json' in update_config:
                    # Explicitly convert to boolean to avoid type issues
                    is_json = bool(update_config['is_json'])
                    # Ensure the value is correctly interpreted if it's a string
                    if isinstance(update_config['is_json'], str):
                        is_json = update_config['is_json'].lower() == 'true'
                    
                    current_app.logger.info(f"Using is_json from configuration: {is_json}")
                    
                    # If is_json is True, ensure format is set to 'json'
                    if is_json:
                        update_config['format'] = 'json'
                        data_source_format = 'json'
                        current_app.logger.info("JSON format set automatically because is_json is True")
                    # If is_json is False, ensure format is set to 'csv'
                    else:
                        update_config['format'] = 'csv'
                        data_source_format = 'csv'
                        current_app.logger.info("CSV format set automatically because is_json is False")
                else:
                    # Determine if the format is JSON based on data_source_format or URL extension
                    is_json = data.get('is_json', False)
                    
                    # First check if the format is explicitly specified
                    if data_source_format == 'json':
                        is_json = True
                        current_app.logger.info("JSON format explicitly specified")
                    elif data_source_format == 'csv':
                        is_json = False
                        current_app.logger.info("CSV format explicitly specified")
                    # Otherwise, try to determine from the URL, but only if the format is not already specified
                    elif not data_source_format and url:
                        if url.lower().endswith('.json'):
                            is_json = True
                            data_source_format = 'json'
                            current_app.logger.info("JSON format detected from URL extension")
                        elif url.lower().endswith('.csv'):
                            is_json = False
                            data_source_format = 'csv'
                            current_app.logger.info("CSV format detected from URL extension")
                    
                    # Save the configuration
                    update_config['is_json'] = is_json
                
                # Ensure the format is saved in the configuration
                if data_source_format and 'format' not in update_config:
                    update_config['format'] = data_source_format
                elif 'format' in update_config:
                    # Use the format already defined in the configuration
                    data_source_format = update_config['format']
                    current_app.logger.info(f"Format used from configuration: {data_source_format}")
                
                current_app.logger.info(f"is_json configuration set to {is_json} during list creation")
                current_app.logger.info(f"Data format: {data_source_format}")
                current_app.logger.info(f"Complete configuration: {update_config}")
                
                # Prepare allowed_ips to always be valid JSON
                allowed_ips = data.get('allowed_ips')
                if allowed_ips == '' or allowed_ips is None:
                    allowed_ips = json.dumps([])  # Valid empty JSON
                elif isinstance(allowed_ips, str) and not allowed_ips.startswith('[') and not allowed_ips.startswith('{'):
                    # If it's a string but not JSON, convert it to a JSON list
                    # First, split by comma or semicolon
                    ip_list = []
                    for ip in re.split(r'[,;]', allowed_ips):
                        if ip.strip():
                            ip_list.append(ip.strip())
                    allowed_ips = json.dumps(ip_list)
                    current_app.logger.info(f"Allowed IPs converted to JSON: {allowed_ips}")
                
                # Get the results limit (default value: 100)
                max_results = data.get('max_results', 100)
                try:
                    max_results = int(max_results)
                except (ValueError, TypeError):
                    max_results = 100
                
                # Process the schedule
                update_schedule = data.get('update_schedule')
                current_app.logger.info(f"Schedule received: {update_schedule}")
                
                # If the schedule is empty or None and the update type is automatic,
                # check if a schedule is defined in the configuration
                if (not update_schedule or update_schedule == 'None') and data.get('update_type') == 'automatic':
                    # Check if a schedule is defined in the configuration
                    if 'schedule' in update_config:
                        update_schedule = update_config['schedule']
                        current_app.logger.info(f"Using schedule from configuration: {update_schedule}")
                    else:
                        # Leave the schedule as None
                        update_schedule = None
                        current_app.logger.info("No schedule defined")
                
                # Explicitly determine the data format
                explicit_format = None
                if data_source_format:
                    explicit_format = data_source_format
                    current_app.logger.info(f"Format explicitly defined: {explicit_format}")
                elif 'format' in update_config:
                    explicit_format = update_config['format']
                    current_app.logger.info(f"Format defined in configuration: {explicit_format}")
                elif 'is_json' in update_config:
                    explicit_format = 'json' if update_config['is_json'] else 'csv'
                    current_app.logger.info(f"Format inferred from is_json: {explicit_format}")
                
                # Create the list object
                list_obj = List(
                    name=data.get('name'),
                    description=data.get('description'),
                    user_id=current_user.id,  # Assign the current user as the owner
                    update_type=data.get('update_type', 'manual'),
                    update_schedule=update_schedule,
                    update_config=json.dumps(update_config) if update_config else None,
                    is_active=data.get('is_active', True),
                    is_published=data.get('is_published', False),
                    filter_enabled=data.get('filter_enabled', False),
                    filter_rules=data.get('filter_rules'),
                    ip_restriction_enabled=data.get('ip_restriction_enabled', False),
                    allowed_ips=allowed_ips,
                    max_results=max_results
                )
                
                # Explicitly set the data format
                if explicit_format and explicit_format in list_obj.DATA_FORMATS:
                    # Use the column attribute directly instead of the property
                    list_obj.data_source_format = explicit_format
                    current_app.logger.info(f"Data format explicitly set: {explicit_format}")
                    
                    # Ensure the configuration is consistent
                    config = list_obj.update_config
                    config['format'] = explicit_format
                    config['is_json'] = (explicit_format == 'json')
                    list_obj.update_config = config
                
                # Add the list to the session
                db.session.add(list_obj)
                
                # Commit to get a valid ID
                db.session.commit()
                current_app.logger.info(f"List created with ID: {list_obj.id}")
                
                # Add columns manually
                if formatted_columns:
                    try:
                        for idx, col_data in enumerate(formatted_columns):
                            # Create the column with the list ID
                            column = ListColumn(
                                list_id=list_obj.id,
                                name=col_data['name'],
                                position=col_data.get('position', idx),
                                column_type=col_data.get('column_type', 'text')
                            )
                            db.session.add(column)
                            current_app.logger.info(f"Column {col_data['name']} added for list {list_obj.id}")
                        
                        # Commit the columns
                        db.session.commit()
                        current_app.logger.info(f"All columns were added successfully for list {list_obj.id}")
                    except Exception as col_error:
                        db.session.rollback()
                        current_app.logger.error(f"Error adding columns: {str(col_error)}")
                        return jsonify({'error': f"Error adding columns: {str(col_error)}"}), 500
                
                # Ensure the list is correctly persisted
                db.session.commit()
                current_app.logger.info(f"List created successfully, ID: {list_obj.id}")
                
                # Refresh the list object from the database
                db.session.refresh(list_obj)
                
                # Check that the list actually exists in the database
                list_exists = db.session.query(db.exists().where(List.id == list_obj.id)).scalar()
                if not list_exists:
                    current_app.logger.error(f"List with ID {list_obj.id} does not exist in the database after creation")
                    return jsonify({'error': "Error creating the list"}), 500
                
                # Do not import data automatically upon list creation
                # to allow the user to configure CSV options
                # Completely disable automatic import
                if False:  # Disabled to allow manual configuration
                    try:
                        # Create columns manually before importing data
                        # To do this, we will first get a sample of the data
                        import requests
                        import time
                        
                        # Wait a bit to ensure the list is saved in the database
                        current_app.logger.info(f"Waiting 2 seconds to ensure list {list_obj.id} is saved...")
                        time.sleep(2)
                        
                        # Check that the list still exists in the database
                        list_check = db.session.query(List).filter(List.id == list_obj.id).first()
                        if not list_check:
                            current_app.logger.error(f"List with ID {list_obj.id} no longer exists in the database after waiting")
                            return jsonify({'error': "Error creating the list"}), 500
                        
                        # Do not try to modify auto_create_columns directly as it's a property
                        # Store the value in the private attribute _auto_create_columns
                        list_obj._auto_create_columns = True
                        db.session.commit()
                        
                        try:
                            # Get a sample of the data to create the columns
                            current_app.logger.info(f"Getting a data sample from {data_source_url}")
                            response = requests.get(data_source_url, timeout=30)
                            response.raise_for_status()
                            
                            # Create columns manually
                            from sqlalchemy.orm import Session
                            from sqlalchemy import create_engine
                            import csv
                            import io
                            
                            # Use the same connection URL as the application
                            engine = create_engine(current_app.config['SQLALCHEMY_DATABASE_URI'])
                            session = Session(engine)
                            
                            # Determine the starting position for new columns
                            max_position = session.query(db.func.max(ListColumn.position)).filter(
                                ListColumn.list_id == list_obj.id
                            ).scalar() or -1
                            
                            # Create a dictionary to store columns by name
                            columns_dict = {}
                            sample_data = None
                            
                            # Determine the data format from the configuration
                            # Get the update configuration
                            update_config = list_obj.get_update_config
                            current_app.logger.info(f"Update configuration for column creation: {update_config}")
                            
                            # Check if the configuration exists and contains the is_json key
                            is_json_format = False
                            if update_config:
                                # Check if is_json is present in the configuration
                                is_json_format = update_config.get('is_json', False)
                                # If is_json is not present, check the URL to determine the format
                                if 'is_json' not in update_config and 'url' in update_config:
                                    url = update_config.get('url', '')
                                    is_json_format = url.lower().endswith('.json')
                                    # Update the configuration with the correct is_json value
                                    update_config['is_json'] = is_json_format
                                    list_obj.update_config = update_config
                                    db.session.commit()
                                    current_app.logger.info(f"Configuration updated with is_json={is_json_format}")
                            
                            current_app.logger.info(f"Format determined for column creation: {'JSON' if is_json_format else 'CSV'}")
                            
                            sample_data = None
                            
                            try:
                                if is_json_format:
                                    # Process JSON data
                                    current_app.logger.info("Attempting to create columns from JSON")
                                    json_data = response.json()
                                    if isinstance(json_data, list) and len(json_data) > 0:
                                        current_app.logger.info(f"Creating columns for list {list_obj.id} from JSON")
                                        sample_data = json_data[0]
                                else:
                                    # Process CSV data
                                    current_app.logger.info("Attempting to create columns from CSV")
                                    csv_content = response.content.decode('utf-8')
                                    
                                    # Detect the delimiter used in the CSV file
                                    sample_line = csv_content.split('\n')[0] if '\n' in csv_content else csv_content
                                    delimiter = ','
                                    
                                    # Check possible delimiters (comma, semicolon, vertical bar)
                                    delimiters = [',', ';', '|']
                                    delimiter_counts = {d: sample_line.count(d) for d in delimiters}
                                    
                                    # Choose the most frequent delimiter
                                    max_count = 0
                                    for d, count in delimiter_counts.items():
                                        if count > max_count:
                                            max_count = count
                                            delimiter = d
                                    
                                    current_app.logger.info(f"Delimiter detected for CSV: '{delimiter}'")
                                    
                                    # Use the detected delimiter to read the CSV
                                    csv_file = io.StringIO(csv_content)
                                    
                                    # Check if the first line contains headers
                                    has_headers = csv_config.get('has_headers', True)
                                    
                                    if has_headers:
                                        # Use headers from the first line
                                        csv_reader = csv.DictReader(csv_file, delimiter=delimiter)
                                    else:
                                        # Use manual column names if provided
                                        manual_column_names = csv_config.get('column_names', [])
                                        if manual_column_names:
                                            csv_reader = csv.DictReader(csv_file, fieldnames=manual_column_names, delimiter=delimiter)
                                        else:
                                            # Generate column names automatically (Col1, Col2, etc.)
                                            # First, read the first line to determine the number of columns
                                            first_line = csv_content.split('\n')[0] if '\n' in csv_content else csv_content
                                            num_columns = len(first_line.split(delimiter))
                                            auto_column_names = [f'Col{i+1}' for i in range(num_columns)]
                                            
                                            # Reset the file cursor
                                            csv_file.seek(0)
                                            csv_reader = csv.DictReader(csv_file, fieldnames=auto_column_names, delimiter=delimiter)
                                    
                                    # Convert the CSV to a dictionary
                                    rows = list(csv_reader)
                                    if rows:
                                        current_app.logger.info(f"Creating columns for list {list_obj.id} from CSV")
                                        sample_data = rows[0]
                            except Exception as format_error:
                                current_app.logger.error(f"Error creating columns in {'JSON' if is_json_format else 'CSV'} format: {str(format_error)}")
                                # Try the other format in case of failure
                                try:
                                    if is_json_format:
                                        # Try CSV as a fallback
                                        current_app.logger.info("Fallback attempt to create columns from CSV")
                                        csv_content = response.content.decode('utf-8')
                                        
                                        # Detect the delimiter used in the CSV file
                                        sample_line = csv_content.split('\n')[0] if '\n' in csv_content else csv_content
                                        delimiter = ','
                                        
                                        # Check possible delimiters (comma, semicolon, vertical bar)
                                        delimiters = [',', ';', '|']
                                        delimiter_counts = {d: sample_line.count(d) for d in delimiters}
                                        
                                        # Choose the most frequent delimiter
                                        max_count = 0
                                        for d, count in delimiter_counts.items():
                                            if count > max_count:
                                                max_count = count
                                                delimiter = d
                                        
                                        current_app.logger.info(f"Delimiter detected for CSV (fallback): '{delimiter}'")
                                        
                                        # Use the detected delimiter to read the CSV
                                        csv_file = io.StringIO(csv_content)
                                        
                                        # Check if the first line contains headers
                                        has_headers = csv_config.get('has_headers', True)
                                        
                                        if has_headers:
                                            # Use headers from the first line
                                            csv_reader = csv.DictReader(csv_file, delimiter=delimiter)
                                        else:
                                            # Use manual column names if provided
                                            manual_column_names = csv_config.get('column_names', [])
                                            if manual_column_names:
                                                csv_reader = csv.DictReader(csv_file, fieldnames=manual_column_names, delimiter=delimiter)
                                            else:
                                                # Generate column names automatically (Col1, Col2, etc.)
                                                # First, read the first line to determine the number of columns
                                                first_line = csv_content.split('\n')[0] if '\n' in csv_content else csv_content
                                                num_columns = len(first_line.split(delimiter))
                                                auto_column_names = [f'Col{i+1}' for i in range(num_columns)]
                                                
                                                # Reset the file cursor
                                                csv_file.seek(0)
                                                csv_reader = csv.DictReader(csv_file, fieldnames=auto_column_names, delimiter=delimiter)
                                        
                                        # Convert the CSV to a dictionary
                                        rows = list(csv_reader)
                                        if rows:
                                            current_app.logger.info(f"Fallback creation of columns from CSV")
                                            sample_data = rows[0]
                                except Exception as backup_error:
                                    current_app.logger.error(f"Error during fallback attempt for column creation: {str(backup_error)}")
                            
                            # If we have sample data, create the columns
                            if sample_data:
                                for idx, (name, value) in enumerate(sample_data.items()):
                                    # Determine the column type
                                    column_type = 'text'
                                    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
                                        column_type = 'number'
                                    elif isinstance(value, bool) or value.lower() in ('true', 'false'):
                                        column_type = 'boolean'
                                    
                                    # Create the column with a unique position
                                    try:
                                        position = idx
                                        column = ListColumn(
                                            list_id=list_obj.id,
                                            name=name,
                                            position=position,
                                            column_type=column_type
                                        )
                                        session.add(column)
                                        session.commit()
                                        
                                        # Store the column in the dictionary
                                        columns_dict[name] = column
                                        current_app.logger.info(f"Column {name} created successfully for list {list_obj.id} (position {position})")
                                    except Exception as col_error:
                                        current_app.logger.error(f"Error creating column {name}: {str(col_error)}")
                                        session.rollback()
                                
                                session.close()
                        except Exception as sample_error:
                            current_app.logger.error(f"Error getting sample: {str(sample_error)}")
                        
                        # Refresh the list object
                        db.session.refresh(list_obj)
                        
                        # Import data manually
                        current_app.logger.info(f"Manually importing data from {data_source_url}")
                        
                        try:
                            # Instead of using the import_data_from_url method, import directly here
                            # as virtual properties may not work correctly
                            response = requests.get(data_source_url, timeout=30)
                            response.raise_for_status()
                            
                            # Determine the data format from the configuration
                            # Get the update configuration
                            update_config = list_obj.get_update_config
                            current_app.logger.info(f"Update configuration: {update_config}")
                            
                            # Check if the configuration exists and contains the is_json key
                            is_json_format = False
                            if update_config:
                                # Check if is_json is present in the configuration
                                is_json_format = update_config.get('is_json', False)
                                # If is_json is not present, check the URL to determine the format
                                if 'is_json' not in update_config and 'url' in update_config:
                                    url = update_config.get('url', '')
                                    is_json_format = url.lower().endswith('.json')
                                    # Update the configuration with the correct is_json value
                                    update_config['is_json'] = is_json_format
                                    list_obj.update_config = update_config
                                    db.session.commit()
                                    current_app.logger.info(f"Configuration updated with is_json={is_json_format}")
                            
                            current_app.logger.info(f"Format determined from configuration: {'JSON' if is_json_format else 'CSV'}")
                            
                            # Import data according to the determined format
                            json_data = None
                            
                            try:
                                if is_json_format:
                                    # Use JSON import directly
                                    current_app.logger.info("Attempting to import in JSON format")
                                    json_data = response.json()
                                    current_app.logger.info(f"JSON imported with {len(json_data)} data rows")
                                else:
                                    # Use CSV import
                                    current_app.logger.info("Attempting to import in CSV format")
                                    import csv
                                    import io
                                    
                                    # Convert the response to CSV rows
                                    csv_content = response.content.decode('utf-8')
                                    csv_file = io.StringIO(csv_content)
                                    
                                    # Detect the delimiter used in the CSV file
                                    sample_line = csv_content.split('\n')[0] if '\n' in csv_content else csv_content
                                    delimiter = ','
                                    
                                    # Check possible delimiters (comma, semicolon, vertical bar)
                                    delimiters = [',', ';', '|']
                                    delimiter_counts = {d: sample_line.count(d) for d in delimiters}
                                    
                                    # Choose the most frequent delimiter
                                    max_count = 0
                                    for d, count in delimiter_counts.items():
                                        if count > max_count:
                                            max_count = count
                                            delimiter = d
                                    
                                    current_app.logger.info(f"Delimiter detected for CSV: '{delimiter}'")
                                    
                                    # Reset the file cursor
                                    csv_file.seek(0)
                                    
                                    # Use the detected delimiter
                                    csv_reader = csv.DictReader(csv_file, delimiter=delimiter)
                                    
                                    # Convert the CSV to a list of dictionaries (like JSON)
                                    json_data = [row for row in csv_reader]
                                    current_app.logger.info(f"CSV imported and converted to {len(json_data)} data rows")
                            except Exception as format_error:
                                current_app.logger.error(f"Error importing in {'JSON' if is_json_format else 'CSV'} format: {str(format_error)}")
                                # Try the other format in case of failure
                                try:
                                    if is_json_format:
                                        # Try CSV as a fallback
                                        current_app.logger.info("Fallback attempt to import in CSV format")
                                        import csv
                                        import io
                                        
                                        csv_content = response.content.decode('utf-8')
                                        csv_file = io.StringIO(csv_content)
                                        
                                        # Detect the delimiter used in the CSV file
                                        sample_line = csv_content.split('\n')[0] if '\n' in csv_content else csv_content
                                        delimiter = ','
                                        
                                        # Check possible delimiters (comma, semicolon, vertical bar)
                                        delimiters = [',', ';', '|']
                                        delimiter_counts = {d: sample_line.count(d) for d in delimiters}
                                        
                                        # Choose the most frequent delimiter
                                        max_count = 0
                                        for d, count in delimiter_counts.items():
                                            if count > max_count:
                                                max_count = count
                                                delimiter = d
                                        
                                        current_app.logger.info(f"Delimiter detected for CSV (fallback): '{delimiter}'")
                                        
                                        # Reset the file cursor
                                        csv_file.seek(0)
                                        
                                        # Use the detected delimiter
                                        csv_reader = csv.DictReader(csv_file, delimiter=delimiter)
                                        
                                        json_data = [row for row in csv_reader]
                                        current_app.logger.info(f"CSV successfully imported as fallback: {len(json_data)} rows")
                                    else:
                                        # Try JSON as a fallback
                                        current_app.logger.info("Fallback attempt to import in JSON format")
                                        json_data = response.json()
                                        current_app.logger.info(f"JSON successfully imported as fallback: {len(json_data)} rows")
                                except Exception as backup_error:
                                    current_app.logger.error(f"Error during fallback attempt: {str(backup_error)}")
                            
                            # If data was imported, process it
                            if json_data:
                                # Create a separate session for import
                                from sqlalchemy.orm import Session
                                from sqlalchemy import create_engine
                                
                                engine = create_engine(current_app.config['SQLALCHEMY_DATABASE_URI'])
                                session = Session(engine)
                                
                                # Get the list from the new session
                                list_from_db = session.query(List).filter(List.id == list_obj.id).first()
                                
                                if list_from_db:
                                    # Delete existing data
                                    session.query(ListData).filter(ListData.list_id == list_obj.id).delete()
                                    session.commit()
                                    
                                    # Import new data
                                    current_app.logger.info(f"Importing {len(json_data)} rows of JSON data")
                                    
                                    # Simplified approach: get only column names and positions
                                    # to avoid session issues
                                    column_info = session.query(ListColumn.name, ListColumn.position).filter(
                                        ListColumn.list_id == list_obj.id
                                    ).all()
                                    
                                    # Create a simple dictionary with column names and positions
                                    # No SQLAlchemy objects, just simple values
                                    position_map = {name: position for name, position in column_info}
                                    current_app.logger.info(f"Columns retrieved for import: {position_map}")
                                    
                                    # Import each row
                                    for row_idx, row_data in enumerate(json_data):
                                        for col_name, value in row_data.items():
                                            # Use the simple dictionary to find the column position
                                            if col_name in position_map:
                                                position = position_map[col_name]
                                                
                                                # Create the data entry with the column position directly
                                                data_entry = ListData(
                                                    list_id=list_obj.id,
                                                    row_id=row_idx + 1,
                                                    column_position=position,
                                                    value=str(value)
                                                )
                                                session.add(data_entry)
                                                current_app.logger.info(f"Adding value '{value}' for column '{col_name}' (position {position}) in row {row_idx + 1}")
                                            else:
                                                current_app.logger.warning(f"Column '{col_name}' not found for list {list_obj.id}")
                                        
                                        # Commit every 100 rows
                                        if (row_idx + 1) % 100 == 0:
                                            session.commit()
                                            current_app.logger.info(f"Imported {row_idx + 1} rows...")
                                    
                                    # Final commit
                                    session.commit()
                                    current_app.logger.info(f"Import finished: {len(json_data)} rows imported")
                                    
                                    # Update the last update date
                                    list_from_db.last_update = get_paris_now()
                                    session.commit()
                                else:
                                    current_app.logger.error(f"List {list_obj.id} not found in the database during import")
                                
                                session.close()
                        except Exception as import_error:
                            current_app.logger.error(f"Error during direct data import: {str(import_error)}")
                        
                        # Refresh the list object to get created columns
                        db.session.refresh(list_obj)
                    except Exception as import_error:
                        current_app.logger.error(f"Error importing data: {str(import_error)}")
                        # Do not fail list creation if import fails
            except Exception as e:
                current_app.logger.error(f"Error creating list: {str(e)}")
                return jsonify({'error': str(e)}), 500
            
            # Common response for all created lists
            response_data = {
                'id': list_obj.id,
                'name': list_obj.name,
                'description': list_obj.description,
                'columns': [{'name': col.name, 'position': col.position, 'type': col.column_type} 
                          for col in list_obj.columns]
            }
            
            # If a data source URL is specified, attempt to import the data
            if data_source_url and data.get('data_source_format'):
                try:
                    # Update data source properties
                    list_obj.data_source_url = data_source_url
                    list_obj.data_source_format = data.get('data_source_format')
                    list_obj.auto_create_columns = auto_create_columns
                    list_obj.save()
                    
                    # Import the data
                    row_count = list_obj.import_data_from_url()
                    current_app.logger.info(f"Import successful: {row_count} rows imported")
                    
                    response_data['import_result'] = f"{row_count} rows imported successfully"
                except Exception as e:
                    current_app.logger.error(f"Error importing data: {str(e)}")
                    current_app.logger.exception(e)
                    response_data['import_error'] = str(e)
            
            # If the list is automatic and has a URL, force a full data update
            # even if the initial import failed
            if list_obj.update_type == 'automatic' and list_obj.data_source_url:
                try:
                    # Use the scheduler service to update the data completely
                    from ..services.scheduler_service import SchedulerService
                    scheduler = SchedulerService(current_app)
                    success, logs = scheduler._update_list_data(list_obj.id)
                    
                    if success:
                        current_app.logger.info(f"Full data update successful for list {list_obj.id}")
                        response_data['update_result'] = "All columns and data were imported successfully"
                    else:
                        current_app.logger.warning(f"Full data update failed for list {list_obj.id}: {logs}")
                        response_data['update_warning'] = "Some columns may not have been imported correctly"
                except Exception as update_error:
                    current_app.logger.error(f"Error during full data update: {str(update_error)}")
                    response_data['update_error'] = str(update_error)
                    # Do not block list creation if the update fails
            
            # Return the response
            return jsonify(response_data), 201
            
        except Exception as e:
            current_app.logger.error(f"Error creating list: {str(e)}")
            current_app.logger.exception(e)
            return jsonify({'error': str(e)}), 400
        
    except Exception as e:
        current_app.logger.error(f"Error creating list: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({'error': str(e)}), 400

@list_bp.route('/api/lists', methods=['GET'])
@token_auth_required
def get_lists():
    # Clear the SQLAlchemy session cache to force a reload of the data
    db.session.expire_all()
    
    # Get all lists directly from the database for verification
    all_lists = db.session.query(List.id, List.name, List.is_published).all()
    current_app.logger.info(f"API - ALL LISTS IN DB: {[(l.id, l.name, l.is_published) for l in all_lists]}")
    
    if current_user.is_admin:
        # Administrators see all lists
        lists = List.query.all()
        current_app.logger.info(f"API - ADMIN - All lists: {[l.name for l in lists]}")
    else:
        # Standard users only see published lists
        # Execute a raw SQL query to ensure filtering works
        from sqlalchemy import text
        result = db.session.execute(text("SELECT * FROM lists WHERE is_published = 1"))
        list_ids = [row[0] for row in result]
        current_app.logger.info(f"API - Published list IDs (raw SQL): {list_ids}")
        
        # Use these IDs to get the lists
        lists = List.query.filter(List.id.in_(list_ids)).all()
        current_app.logger.info(f"API - USER - Filtered lists: {[l.name for l in lists]}")
    
    return jsonify([{
        'id': lst.id,
        'name': lst.name,
        'description': lst.description,
        'update_type': lst.update_type,
        'is_active': lst.is_active,
        'is_published': lst.is_published,
        'last_update': lst.last_update.isoformat() if lst.last_update else None
    } for lst in lists])

@list_bp.route('/api/lists/<int:list_id>', methods=['GET'])
@token_auth_required
@check_list_access
@check_ip_restriction
def get_list(list_id):
    list_obj = List.query.get(list_id)
    return jsonify({
        'id': list_obj.id,
        'name': list_obj.name,
        'description': list_obj.description,
        'update_type': list_obj.update_type,
        'update_schedule': list_obj.update_schedule,
        'is_active': list_obj.is_active,
        'is_published': list_obj.is_published,
        'filter_enabled': list_obj.filter_enabled,
        'filter_rules': json.loads(list_obj.filter_rules) if list_obj.filter_rules else None,
        'ip_restriction_enabled': list_obj.ip_restriction_enabled,
        'allowed_ips': json.loads(list_obj.allowed_ips) if list_obj.allowed_ips else None,
        'columns': [{'name': col.name, 'position': col.position} 
                   for col in list_obj.columns],
        'last_update': list_obj.last_update.isoformat() if list_obj.last_update else None
    })

@list_bp.route('/api/lists/<int:list_id>', methods=['PUT', 'POST'])
@token_auth_required
@check_list_ownership
def update_list(list_id):
    """Updates an existing list or creates it if it does not exist"""
    try:
        current_app.logger.info(f"Attempting to update list {list_id}")
        
        # Check if the list actually exists in the database
        list_exists = db.session.query(db.exists().where(List.id == list_id)).scalar()
        
        # Get data from the form or JSON depending on the request type
        if request.is_json:
            data = request.get_json()
            current_app.logger.info(f"Received JSON data for list {list_id}")
        else:
            data = request.form.to_dict()
            current_app.logger.info(f"Received form data for list {list_id}: {data}")
            
            # Convertir toutes les cases à cocher en booléen (True si présente, False sinon)
            checkbox_keys = [
                'is_active', 'is_published', 'ip_restriction_enabled',
                'public_csv_enabled', 'public_json_enabled', 'regenerate_token',
                'public_csv_include_headers', 'public_txt_enabled', 'public_txt_include_headers'
            ]
            for key in checkbox_keys:
                data[key] = key in data
                current_app.logger.info(f"Value of {key}: {data[key]}")
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        if not list_exists:
            current_app.logger.warning(f"List with ID {list_id} does not exist in the database. Attempting to create.")
            
            # Create a new list with the specified ID
            try:
                # Create a new list object
                list_obj = List(
                    id=list_id,
                    name=data.get('name', f'List {list_id}'),
                    description=data.get('description', ''),
                    user_id=current_user.id,  # Assign the current user as the owner
                    update_type=data.get('update_type', 'manual'),
                    update_schedule=data.get('update_schedule'),
                    update_config=data.get('update_config'),
                    is_active=data.get('is_active', True),
                    is_published=data.get('is_published', False),
                    filter_enabled=data.get('filter_enabled', False),
                    filter_rules=data.get('filter_rules'),
                    ip_restriction_enabled=data.get('ip_restriction_enabled', False),
                    allowed_ips=data.get('allowed_ips'),
                    data_source_url=data.get('data_source_url'),
                    data_source_format=data.get('data_source_format'),
                    auto_create_columns=data.get('auto_create_columns', True)
                )
                
                # Add the list to the session
                db.session.add(list_obj)
                
                # Force a commit to ensure the list is created
                db.session.commit()
                
                # Refresh the list object from the database
                db.session.refresh(list_obj)
                
                # Check that the list actually exists in the database
                list_exists = db.session.query(db.exists().where(List.id == list_id)).scalar()
                if not list_exists:
                    current_app.logger.error(f"List with ID {list_id} could not be created")
                    return jsonify({'error': f"Could not create list with ID {list_id}"}), 500
                    
                current_app.logger.info(f"List {list_id} created successfully")
            except Exception as create_error:
                db.session.rollback()
                current_app.logger.error(f"Error creating list {list_id}: {str(create_error)}")
                return jsonify({'error': f"Error creating list: {str(create_error)}"}), 500
        else:
            # Get the existing list
            list_obj = List.query.get(list_id)
        
        # data est déjà défini plus haut (JSON ou formulaire)
        if not data:
            return jsonify({'error': 'No data received'}), 400
            
        current_app.logger.debug(f"Data received: {data}")
        
        # Update basic fields
        list_obj.name = data.get('name', list_obj.name)
        list_obj.description = data.get('description', list_obj.description)
        
        # Assign an owner if the list doesn't have one
        if list_obj.user_id is None:
            list_obj.user_id = current_user.id
            current_app.logger.info(f"Owner assigned to list {list_id}: user {current_user.id}")
        
        list_obj.update_type = data.get('update_type', list_obj.update_type)
        list_obj.is_active = data.get('is_active', list_obj.is_active)
        list_obj.is_published = data.get('is_published', list_obj.is_published)
        
        # Update the results limit
        if 'max_results' in data:
            try:
                max_results = int(data.get('max_results', 100))
                list_obj.max_results = max_results
                current_app.logger.info(f"Results limit updated: {max_results}")
            except (ValueError, TypeError):
                current_app.logger.warning(f"Invalid value for max_results: {data.get('max_results')}")
                # Keep the existing value
        
        # Update data source parameters
        if 'data_source_url' in data:
            list_obj.data_source_url = data.get('data_source_url')
        if 'data_source_format' in data:
            list_obj.data_source_format = data.get('data_source_format')
        if 'auto_create_columns' in data:
            list_obj.auto_create_columns = data.get('auto_create_columns')
        
        # Update security parameters
        list_obj.ip_restriction_enabled = data.get('ip_restriction_enabled', list_obj.ip_restriction_enabled)
        
        # Prepare allowed_ips to always be valid JSON
        allowed_ips = data.get('allowed_ips', list_obj.allowed_ips)
        if allowed_ips == '' or allowed_ips is None:
            allowed_ips = json.dumps([])  # Valid empty JSON
        elif isinstance(allowed_ips, str) and not allowed_ips.startswith('[') and not allowed_ips.startswith('{'):
            # If it's a string but not JSON, convert it to a JSON list
            # First, split by comma or semicolon
            ip_list = []
            for ip in re.split(r'[,;]', allowed_ips):
                if ip.strip():
                    ip_list.append(ip.strip())
            allowed_ips = json.dumps(ip_list)
            current_app.logger.info(f"Allowed IPs converted to JSON: {allowed_ips}")
        
        list_obj.allowed_ips = allowed_ips
        
        # Update public file options
        list_obj.public_csv_enabled = data.get('public_csv_enabled', list_obj.public_csv_enabled)
        list_obj.public_json_enabled = data.get('public_json_enabled', list_obj.public_json_enabled)
        list_obj.public_csv_include_headers = data.get('public_csv_include_headers', True)
        # Gestion des options TXT public
        list_obj.public_txt_enabled = data.get('public_txt_enabled', list_obj.public_txt_enabled)
        list_obj.public_txt_column = data.get('public_txt_column', list_obj.public_txt_column)
        list_obj.public_txt_include_headers = data.get('public_txt_include_headers', True)
        current_app.logger.info(f"Public access options - CSV: {list_obj.public_csv_enabled}, JSON: {list_obj.public_json_enabled}, Include headers: {list_obj.public_csv_include_headers}")
        
        # Generate an access token if necessary
        if (list_obj.public_csv_enabled or list_obj.public_json_enabled or list_obj.public_txt_enabled) and \
           (not list_obj.public_access_token or data.get('regenerate_token', False)):
            # Import the token generation function
            from .public_files_routes import generate_access_token
            list_obj.public_access_token = generate_access_token()
            current_app.logger.info(f"New access token generated for list {list_id}")
        
        # Supprimer le token uniquement si AUCUN export public n'est activé (CSV, JSON, TXT)
        if not list_obj.public_csv_enabled and not list_obj.public_json_enabled and not list_obj.public_txt_enabled:
            list_obj.public_access_token = None
            current_app.logger.info(f"Access token deleted for list {list_id} as public access is disabled (aucun format public)")
        
        # Update the configuration if necessary
        old_schedule = list_obj.update_schedule
        if list_obj.update_type == 'automatic':
            # Get the existing configuration
            existing_config = list_obj.get_update_config
            
            # Get the new configuration
            new_config = data.get('update_config', {})
            
            # Preserve the CSV configuration if it exists and is not in the new data
            if 'csv_config' in existing_config and 'csv_config' not in new_config:
                current_app.logger.info(f"Preserving existing CSV configuration for list {list_id}")
                new_config['csv_config'] = existing_config['csv_config']
                
                # Ensure the format is consistent with the CSV configuration
                if 'format' not in new_config:
                    new_config['format'] = 'csv'
                if 'is_json' not in new_config:
                    new_config['is_json'] = False
            
            # Preserve JSON parameters if they exist and are not in the new data
            json_params = ['is_json', 'format', 'json_data_path', 'json_pagination_enabled', 'json_next_page_path', 'json_max_pages']
            if existing_config.get('is_json') == True and 'is_json' not in new_config:
                current_app.logger.info(f"Preserving existing JSON configuration for list {list_id}")
                
                # Copy existing JSON parameters
                for param in json_params:
                    if param in existing_config and param not in new_config:
                        new_config[param] = existing_config[param]
                
                # Ensure the format is consistent with the JSON configuration
                new_config['is_json'] = True
                new_config['format'] = 'json'
            
            # Preserve the source and URL if they are not in the new data
            if 'source' in existing_config and 'source' not in new_config:
                new_config['source'] = existing_config['source']
            if 'url' in existing_config and 'url' not in new_config:
                new_config['url'] = existing_config['url']
                
            # Update the configuration
            list_obj.update_config = new_config
            list_obj.update_schedule = data.get('update_schedule')
            
            # Check if the schedule has been changed
            if old_schedule != list_obj.update_schedule:
                current_app.logger.info(f"Schedule changed for list {list_id}: {old_schedule} -> {list_obj.update_schedule}")
                try:
                    # Reschedule the task with the new schedule
                    scheduler = SchedulerService(current_app)
                    scheduler._schedule_list(list_obj)
                    current_app.logger.info(f"Task rescheduled successfully for list {list_id}")
                except Exception as e:
                    current_app.logger.error(f"Error rescheduling task for list {list_id}: {str(e)}")
            
        # Update columns
        if 'columns' in data:
            current_app.logger.info(f"Updating columns: {data['columns']}")
            
            # Get current columns
            current_columns = {col.name: col for col in list_obj.columns}
            new_columns = {col['name']: col for col in data['columns']}
            
            # Check if columns have actually changed
            columns_changed = False
            
            # Check if the number of columns has changed
            if len(current_columns) != len(new_columns):
                columns_changed = True
            else:
                # Check if the names or types of columns have changed
                for col_name, col_data in new_columns.items():
                    if col_name not in current_columns or current_columns[col_name].column_type != col_data['column_type']:
                        columns_changed = True
                        break
            
            # If columns have changed and the list contains data, block the update
            if columns_changed:
                has_data = db.session.query(ListData).filter_by(list_id=list_id).first() is not None
                if has_data:
                    return jsonify({
                        'error': 'Cannot modify columns: the list already contains data. Please delete all data before modifying columns.'
                    }), 400
            
            # First, set all positions to temporary negative values
            for idx, col in enumerate(list_obj.columns):
                col.position = -(idx + 1)  # -1, -2, -3, etc.
            db.session.flush()
            
            # Delete columns that are no longer present
            for col_name in current_columns:
                if col_name not in new_columns:
                    current_app.logger.info(f"Deleting column {col_name}")
                    db.session.delete(current_columns[col_name])
            
            # Update or create columns with new positions
            # Ensure the list actually exists in the database
            list_exists = db.session.query(db.exists().where(List.id == list_id)).scalar()
            if not list_exists:
                current_app.logger.error(f"List with ID {list_id} does not exist in the database")
                return jsonify({'error': "The list does not exist in the database"}), 404
            
            # Force a commit to ensure all previous modifications are persisted
            db.session.commit()
            
            # Update or create columns with new positions
            for position, (col_name, col_data) in enumerate(new_columns.items()):
                if col_name in current_columns:
                    current_app.logger.info(f"Updating column {col_name}")
                    current_columns[col_name].column_type = col_data['column_type']
                    current_columns[col_name].position = position
                else:
                    current_app.logger.info(f"Creating column {col_name}")
                    try:
                        # Check again that the list exists
                        list_check = db.session.query(List).get(list_id)
                        if not list_check:
                            current_app.logger.error(f"List with ID {list_id} does not exist before creating column {col_name}")
                            return jsonify({'error': f"The list does not exist before creating column {col_name}"}), 404
                        
                        new_col = ListColumn(
                            name=col_name,
                            column_type=col_data['column_type'],
                            list_id=list_id,
                            position=position
                        )
                        db.session.add(new_col)
                        # Flush after each column addition to detect errors immediately
                        db.session.flush()
                        current_app.logger.info(f"Column {col_name} created successfully for list {list_id}")
                    except Exception as col_err:
                        current_app.logger.error(f"Error creating column {col_name}: {str(col_err)}")
                        db.session.rollback()
                        return jsonify({'error': f"Error creating column {col_name}: {str(col_err)}"}), 500
            
            # Final flush to ensure all modifications are ready to be committed
            db.session.flush()
        
        db.session.commit()
        current_app.logger.info(f"List {list_id} updated successfully")
        
        # Redirection adaptée selon le type de requête
        wants_json = request.is_json or request.accept_mimetypes.best == 'application/json' or \
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if wants_json:
            return jsonify({
                'message': 'List updated successfully',
                'redirect': url_for('list_bp.view_list', list_id=list_id)
            })
        else:
            return redirect(url_for('list_bp.view_list', list_id=list_id))
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating list {list_id}: {str(e)}")
        return jsonify({'error': f"Error updating list: {str(e)}"}), 500

@list_bp.route('/api/lists/<int:list_id>', methods=['DELETE'])
@token_auth_required
@check_list_ownership
@csrf.exempt  # To allow deletion from an HTML form
def delete_list(list_id):
    """Deletes a list and all its associated data"""
    try:
        list_obj = List.query.get(list_id)
        if not list_obj:
            return jsonify({'error': 'List not found'}), 404
        
        current_app.logger.info(f"Deleting list {list_id}")
        
        # First, delete the data
        ListData.query.filter_by(list_id=list_id).delete()
        
        # Delete the columns
        ListColumn.query.filter_by(list_id=list_id).delete()
        
        # Delete the list
        db.session.delete(list_obj)
        db.session.commit()
        
        current_app.logger.info(f"List {list_id} deleted successfully")
        return jsonify({'message': 'List deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting list {list_id}: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({'error': str(e)}), 400

@list_bp.route('/api/lists/<int:list_id>/data', methods=['POST'])
@token_auth_required
@admin_required
@check_list_access
def add_list_data(list_id):
    """Adds a data row to a list"""
    try:
        # Get the data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        # Get the list and its columns
        list_obj = List.query.get_or_404(list_id)
        columns = {col.name: col for col in list_obj.columns}
        
        # Check that all required columns are present
        missing_columns = set(columns.keys()) - set(data.keys())
        if missing_columns:
            return jsonify({
                'error': f'Missing columns: {", ".join(missing_columns)}'
            }), 400
            
        # Find the next available row_id
        max_row_id = db.session.query(db.func.max(ListData.row_id)).filter(
            ListData.list_id == list_id
        ).scalar()
        next_row_id = (max_row_id or 0) + 1
        
        # Create the data entries
        row_data = []
        for col_name, value in data.items():
            if col_name in columns:
                column = columns[col_name]
                # Validate and format the value according to the type
                if column.column_type == 'date':
                    try:
                        # Convert to DD/MM/YYYY format if not already
                        if value:
                            value = format_date_for_db(value)
                    except ValueError as e:
                        return jsonify({'error': f'Invalid date format for {col_name}: {str(e)}'}), 400
                elif column.column_type == 'number':
                    try:
                        value = int(value)
                    except ValueError:
                        return jsonify({'error': f'Invalid number format for {col_name}'}), 400
                elif column.column_type == 'ip':
                    try:
                        # Validate the IP address (with CIDR support)
                        if '/' in value:
                            # CIDR format
                            ip, mask = value.split('/')
                            # Validate the IP address
                            ipaddress.ip_address(ip)
                            # Validate the mask
                            mask_int = int(mask)
                            if ':' in ip:  # IPv6
                                if not (0 <= mask_int <= 128):
                                    raise ValueError("IPv6 mask must be between 0 and 128")
                            else:  # IPv4
                                if not (0 <= mask_int <= 32):
                                    raise ValueError("IPv4 mask must be between 0 and 32")
                        else:
                            # Simple IP format
                            ipaddress.ip_address(value)
                    except ValueError as e:
                        return jsonify({'error': f'Invalid IP format for {col_name}: {str(e)}'}), 400
                
                row_data.append(ListData(
                    list_id=list_id,
                    column_position=column.position,
                    row_id=next_row_id,
                    value=str(value) if value is not None else None
                ))
                
        # Save the data
        db.session.add_all(row_data)
        db.session.commit()
        
        # Update public files if enabled
        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
            try:
                update_public_files(list_obj)
                current_app.logger.info(f"Public files updated for list {list_id} after addition")
            except Exception as e:
                current_app.logger.error(f"Error updating public files: {str(e)}")
                # Do not block the response if updating public files fails
        
        return jsonify({
            'message': 'Row added successfully',
            'row_id': next_row_id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding data: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({'error': str(e)}), 400

@list_bp.route('/api/lists/<int:list_id>/data', methods=['GET'])
@token_auth_required
@check_list_access
@check_ip_restriction
def get_list_data(list_id):
    list_obj = List.query.get(list_id)
    return jsonify(list_obj.get_data())

@list_bp.route('/api/lists/<int:list_id>/data/<int:row_id>', methods=['DELETE'])
@token_auth_required
@admin_required
@check_list_ownership
@csrf.exempt
def delete_row(list_id, row_id):
    """Deletes a data row from a list"""
    try:
        current_app.logger.debug(f"Attempting to delete row {row_id} from list {list_id}")
        
        # Check that the list exists
        list_obj = List.query.get(list_id)
        if not list_obj:
            current_app.logger.error(f"List {list_id} not found")
            return jsonify({'error': 'List not found'}), 404

        # Delete all data for the row
        deleted = ListData.query.filter_by(
            list_id=list_id,
            row_id=row_id
        ).delete()

        if deleted > 0:
            db.session.commit()
            current_app.logger.info(f"Row {row_id} from list {list_id} deleted successfully")
            
            # Update public files if enabled
            if list_obj.public_csv_enabled or list_obj.public_json_enabled:
                try:
                    update_public_files(list_obj)
                    current_app.logger.info(f"Public files updated for list {list_id}")
                except Exception as e:
                    current_app.logger.error(f"Error updating public files: {str(e)}")
                    # Do not block the response if updating public files fails
            
            return jsonify({'message': 'Row deleted successfully'})
        else:
            current_app.logger.warning(f"Row {row_id} not found in list {list_id}")
            return jsonify({'error': 'Row not found'}), 404

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting row {row_id}: {str(e)}")
        return jsonify({'error': f'Error during deletion: {str(e)}'}), 400

@list_bp.route('/api/lists/<int:list_id>/data/<int:row_id>', methods=['GET'])
@token_auth_required
@check_list_access
def get_row_data(list_id, row_id):
    """Gets the data for a specific row"""
    try:
        # Check that the list exists
        list_obj = List.query.get(list_id)
        if not list_obj:
            return jsonify({'error': 'List not found'}), 404

        # Get all data for the row
        data_entries = ListData.query.filter_by(
            list_id=list_id,
            row_id=row_id
        ).all()

        if not data_entries:
            current_app.logger.warning(f"No data found for row {row_id} of list {list_id}")
            return jsonify({'error': 'Row not found'}), 404

        # Organize the data
        response_data = {
            'row_id': row_id,
            'data': {}
        }

        # Create a dictionary of columns for quick access
        columns_by_position = {col.position: col for col in list_obj.columns}

        # Organize data by column
        for entry in data_entries:
            column = columns_by_position.get(entry.column_position)
            if column:
                response_data['data'][column.name] = entry.value

        current_app.logger.debug(f"Data retrieved for row {row_id}: {response_data}")
        return jsonify(response_data)

    except Exception as e:
        current_app.logger.error(f"Error retrieving row {row_id}: {str(e)}")
        return jsonify({'error': f'Error during retrieval: {str(e)}'}), 400

@list_bp.route('/api/lists/<int:list_id>/data/<int:row_id>', methods=['PUT'])
@token_auth_required
@admin_required
@check_list_ownership
@csrf.exempt
def update_row_data(list_id, row_id):
    """Updates the data for a specific row"""
    try:
        # Check that the list exists
        list_obj = List.query.get(list_id)
        if not list_obj:
            return jsonify({'error': 'List not found'}), 404

        # Get the JSON data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid data'}), 400

        # Check that the row exists
        existing_data = ListData.query.filter_by(
            list_id=list_id,
            row_id=row_id
        ).first()
        if not existing_data:
            return jsonify({'error': 'Row not found'}), 404

        # Update each column
        for column in list_obj.columns:
            value = data.get(column.name)
            if value is not None:  # Allow empty values
                # Check date format if necessary
                if column.column_type == 'date':
                    try:
                        # Test different date formats
                        valid_date = False
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y']:
                            try:
                                datetime.strptime(value, fmt)
                                valid_date = True
                                break
                            except ValueError:
                                continue
                        if not valid_date:
                            return jsonify({'error': f'Invalid date format for column {column.name}'}), 400
                    except ValueError:
                        return jsonify({'error': f'Invalid date format for column {column.name}'}), 400

                # Update or create the entry
                data_entry = ListData.query.filter_by(
                    list_id=list_id,
                    row_id=row_id,
                    column_position=column.position
                ).first()

                if data_entry:
                    data_entry.value = value
                else:
                    data_entry = ListData(
                        list_id=list_id,
                        row_id=row_id,
                        column_position=column.position,
                        value=value
                    )
                    db.session.add(data_entry)

        db.session.commit()
        current_app.logger.info(f"Row {row_id} of list {list_id} updated successfully")
        
        # Update public files if enabled
        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
            try:
                update_public_files(list_obj)
                current_app.logger.info(f"Public files updated for list {list_id}")
            except Exception as e:
                current_app.logger.error(f"Error updating public files: {str(e)}")
                # Do not block the response if updating public files fails
        
        return jsonify({'message': 'Data updated successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating row {row_id}: {str(e)}")
        return jsonify({'error': f'Error during update: {str(e)}'}), 400

@list_bp.route('/api/lists/<int:list_id>/import', methods=['POST'])
@token_auth_required
@check_list_ownership
@csrf.exempt
def import_list_data(list_id):
    """Import data from a CSV or JSON file"""
    try:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        # Check the file type (CSV or JSON)
        file_extension = file.filename.split('.')[-1].lower()
        
        if file_extension not in ['csv', 'json']:
            return jsonify({'error': 'The file must be in CSV or JSON format'}), 400
            
        # Read the file content
        file_content = file.stream.read().decode("UTF8")
        
        # Get the list and its columns
        list_obj = List.query.get_or_404(list_id)
        columns = {col.name: col for col in list_obj.columns}
        list_columns = set(columns.keys())
        
        # Process according to the file type
        if file_extension == 'csv':
            # CSV processing
            stream = io.StringIO(file_content, newline=None)
            
            # Get CSV configuration from the list if it exists
            update_config = list_obj.get_update_config
            csv_config = update_config.get('csv_config', {}) if update_config else {}
            
            # Use the configured delimiter or comma by default
            delimiter = csv_config.get('separator', ',')
            
            # Check if the first line contains headers
            has_headers = csv_config.get('has_headers', True)
            
            if has_headers:
                # Use headers from the first line
                csv_reader = csv.DictReader(stream, delimiter=delimiter)
            else:
                # Use manual column names if provided
                manual_column_names = csv_config.get('column_names', [])
                if manual_column_names:
                    csv_reader = csv.DictReader(stream, fieldnames=manual_column_names, delimiter=delimiter)
                else:
                    # Generate column names automatically (Col1, Col2, etc.)
                    # First, read the first line to determine the number of columns
                    first_line = file_content.split('\n')[0] if '\n' in file_content else file_content
                    num_columns = len(first_line.split(delimiter))
                    auto_column_names = [f'Col{i+1}' for i in range(num_columns)]
                    
                    # Reset the file cursor
                    stream.seek(0)
                    csv_reader = csv.DictReader(stream, fieldnames=auto_column_names, delimiter=delimiter)
            
            # Check that all CSV columns match
            if not csv_reader.fieldnames:
                return jsonify({'error': 'The CSV file does not contain column headers'}), 400
                
            csv_columns = set(csv_reader.fieldnames)
            
            if not csv_columns.issubset(list_columns):
                invalid_columns = csv_columns - list_columns
                return jsonify({
                    'error': f'Invalid columns in CSV: {", ".join(invalid_columns)}'
                }), 400
                
            # Convert to a list for processing
            rows = list(csv_reader)
            
            # Apply the results limit if defined
            if list_obj.max_results > 0 and len(rows) > list_obj.max_results:
                current_app.logger.info(f"Results limit applied during CSV import: {list_obj.max_results} out of {len(rows)} available results")
                rows = rows[:list_obj.max_results]
        else:
            # JSON processing
            try:
                json_data = json.loads(file_content)
                
                # Check that the JSON is a list of objects
                if not isinstance(json_data, list):
                    return jsonify({'error': 'The JSON file must contain a list of objects'}), 400
                    
                if not all(isinstance(row, dict) for row in json_data):
                    return jsonify({'error': 'The JSON file must contain a list of objects'}), 400
                    
                # Check that all keys of the JSON objects match the list's columns
                all_keys = set()
                for row in json_data:
                    all_keys.update(row.keys())
                    
                if not all_keys.issubset(list_columns):
                    invalid_columns = all_keys - list_columns
                    return jsonify({
                        'error': f'Invalid columns in JSON: {", ".join(invalid_columns)}'
                    }), 400
                    
                rows = json_data
                
                # Apply the results limit if defined
                if list_obj.max_results > 0 and len(rows) > list_obj.max_results:
                    current_app.logger.info(f"Results limit applied during JSON import: {list_obj.max_results} out of {len(rows)} available results")
                    rows = rows[:list_obj.max_results]
            except json.JSONDecodeError as e:
                return jsonify({'error': f'JSON decoding error: {str(e)}'}), 400
        
        # Find the next available row_id
        max_row_id = db.session.query(db.func.max(ListData.row_id)).filter(
            ListData.list_id == list_id
        ).scalar()
        next_row_id = (max_row_id or 0) + 1
            
        # Import the data
        row_count = 0
        for row in rows:
            row_data = []
            for col_name, value in row.items():
                if col_name in columns:
                    column = columns[col_name]
                    # Convert to string if necessary
                    if not isinstance(value, str):
                        value = str(value)
                    # Format the date if necessary
                    if column.column_type == 'date':
                        value = format_date_for_db(value)
                    row_data.append(ListData(
                        list_id=list_id,
                        column_position=column.position,
                        row_id=next_row_id,
                        value=value
                    ))
            if row_data:
                db.session.add_all(row_data)
                row_count += 1
                next_row_id += 1
                
        db.session.commit()
        
        # Update public files if enabled
        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
            try:
                update_public_files(list_obj)
                current_app.logger.info(f"Public files updated for list {list_id} after import")
            except Exception as e:
                current_app.logger.error(f"Error updating public files: {str(e)}")
                # Do not block the response if updating public files fails
        
        return jsonify({
            'message': f'{row_count} rows imported successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing data: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({'error': str(e)}), 400

@list_bp.route('/api/lists/<int:list_id>/export', methods=['GET'])
@token_auth_required
@check_list_access
@check_ip_restriction
def export_list_data(list_id):
    """Export list data in CSV or JSON format"""
    format_type = request.args.get('format', 'csv')
    
    if format_type not in ['json', 'csv']:
        return jsonify({'error': 'Unsupported format'}), 400
        
    try:
        # Get the list object
        list_obj = List.query.get_or_404(list_id)
        
        # Get the data
        data = list_obj.get_data()
        
        if format_type == 'json':
            # Return the data as-is, including the 'id' field
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
            response = send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'{list_obj.name}_{get_paris_now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
            return response
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@list_bp.route('/api/lists/<int:list_id>/data/bulk-delete', methods=['POST'])
@token_auth_required
@admin_required
@check_list_ownership
@csrf.exempt
def bulk_delete_rows(list_id):
    """Deletes multiple data rows from a list"""
    try:
        # Debug logging
        current_app.logger.info(f"Starting multiple deletion for list {list_id}")
        
        # Check that the list exists
        list_obj = List.query.get(list_id)
        if not list_obj:
            current_app.logger.error(f"List {list_id} not found")
            return jsonify({'error': 'List not found'}), 404

        # Get the IDs of the rows to delete
        data = request.get_json()
        current_app.logger.info(f"Data received: {data}")
        
        if not data or 'row_ids' not in data:
            current_app.logger.error("Invalid data or 'row_ids' missing")
            return jsonify({'error': 'Invalid data'}), 400

        row_ids = data['row_ids']
        if not isinstance(row_ids, list):
            current_app.logger.error(f"Invalid data format for row_ids: {type(row_ids)}")
            return jsonify({'error': 'Invalid data format'}), 400

        current_app.logger.info(f"Attempting to delete {len(row_ids)} rows: {row_ids}")
        
        # Delete all selected rows
        deleted_count = 0
        for row_id in row_ids:
            try:
                deleted = ListData.query.filter_by(
                    list_id=list_id,
                    row_id=row_id
                ).delete()
                current_app.logger.info(f"Deleting row {row_id}: {deleted} record(s) affected")
                if deleted > 0:
                    deleted_count += 1
            except Exception as e:
                current_app.logger.error(f"Error deleting row {row_id}: {str(e)}")

        # Commit only if rows have been deleted
        if deleted_count > 0:
            db.session.commit()
            current_app.logger.info(f"{deleted_count} rows deleted successfully in list {list_id}")
            
            # Update public files if enabled
            if list_obj.public_csv_enabled or list_obj.public_json_enabled:
                try:
                    update_public_files(list_obj)
                    current_app.logger.info(f"Public files updated for list {list_id} after bulk deletion")
                except Exception as e:
                    current_app.logger.error(f"Error updating public files: {str(e)}")
                    # Do not block the response if updating public files fails
            
            return jsonify({
                'message': f'{deleted_count} row(s) deleted successfully',
                'deleted_count': deleted_count,
                'success': True
            })
        else:
            current_app.logger.warning(f"No rows could be deleted among the {len(row_ids)} requested rows")
            return jsonify({
                'error': 'No rows could be deleted',
                'success': False
            }), 404

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error during multiple deletion: {str(e)}")
        return jsonify({
            'error': f'Error during deletion: {str(e)}',
            'success': False
        }), 400

@list_bp.route('/lists/<int:list_id>/edit')
@login_required
@admin_required
@check_list_ownership
def edit_list_ui(list_id):
    """Displays the list edit form"""
    try:
        list_obj = List.query.get_or_404(list_id)
        return render_template('lists/edit.html', list=list_obj)
    except Exception as e:
        current_app.logger.error(f"Error displaying the edit form: {str(e)}")
        current_app.logger.exception(e)
        return f"An error occurred while displaying the edit form: {str(e)}", 500

from sqlalchemy import text

@list_bp.route('/lists')
@login_required
def lists_ui():
    """Displays the lists page"""
    try:
        # Use a raw SQL query to get all lists
        # This avoids issues of mismatch between the model and the table
        result = db.session.execute(text("SELECT * FROM lists ORDER BY name"))
        lists = []
        for row in result:
            # Convert each row to a dictionary
            list_dict = {}
            for column, value in row._mapping.items():
                list_dict[column] = value
            lists.append(list_dict)
            
        return render_template('lists/index.html', lists=lists)
    except Exception as e:
        current_app.logger.error(f"Error displaying lists: {str(e)}")
        current_app.logger.exception(e)
        return f"An error occurred while displaying the lists: {str(e)}", 500

@list_bp.route('/debug/list-columns')
@login_required
def debug_list_columns():
    """Temporary route to display the structure of the lists table"""
    try:
        # Get information about the columns of the lists table
        result = db.session.execute(text("SHOW COLUMNS FROM lists"))
        columns = []
        for row in result:
            columns.append(dict(row._mapping))
            
        # Get a data sample
        data_result = db.session.execute(text("SELECT * FROM lists LIMIT 1"))
        sample_data = []
        for row in data_result:
            row_dict = {}
            for column, value in row._mapping.items():
                row_dict[column] = value
            sample_data.append(row_dict)
            
        return jsonify({
            'columns': columns,
            'sample_data': sample_data
        })
    except Exception as e:
        current_app.logger.error(f"Error displaying the structure of the lists table: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({'error': str(e)}), 500


@list_bp.route('/api/lists/<int:list_id>/update-from-url', methods=['POST'])
@token_auth_required
@check_list_ownership
def update_list_from_url(list_id):
    """Updates a list's data from its source URL"""
    try:
        list_obj = List.query.get_or_404(list_id)
        
        if not list_obj.data_source_url:
            return jsonify({
                'error': 'No data source URL defined for this list',
                'success': False
            }), 400
            
        if not list_obj.data_source_format or list_obj.data_source_format not in list_obj.DATA_FORMATS:
            return jsonify({
                'error': f"Unsupported data format. Valid formats: {', '.join(list_obj.DATA_FORMATS)}",
                'success': False
            }), 400
        
        # Import data from the URL
        row_count = list_obj.import_data_from_url()
        
        return jsonify({
            'message': f'{row_count} rows imported successfully',
            'row_count': row_count,
            'success': True
        })
        
    except Exception as e:
        current_app.logger.error(f"Error updating from URL: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


@list_bp.route('/lists/<int:list_id>/update-data', methods=['POST'])
@login_required
@admin_required
@check_list_ownership
def update_list_data(list_id):
    """Updates an automatic list's data using its scheduler service"""
    try:
        list_obj = List.query.get_or_404(list_id)
        
        # Check that the list is of automatic type
        if list_obj.update_type != 'automatic':
            return jsonify({
                'error': 'This list is not configured for automatic updates',
                'success': False
            }), 400
        
        # Check that the update configuration exists
        config = list_obj.get_update_config
        if not config:
            return jsonify({
                'error': 'No update configuration found for this list',
                'success': False
            }), 400
        
        # Execute the update using the scheduler service
        scheduler = SchedulerService(current_app)
        success, logs = scheduler._update_list_data(list_id)
        
        # If the update was successful, update the last update date
        if success:
            list_obj.last_update = get_paris_now()
            db.session.commit()
        
        # Prepare the response with the execution logs
        response = {
            'success': success,
            'logs': logs
        }
        
        if success:
            response['message'] = 'Data updated successfully'
        else:
            # Extract the error message from the logs if available
            error_logs = [log for log in logs if log.startswith('ERROR:')]
            if error_logs:
                response['error'] = error_logs[0].replace('ERROR: ', '')
            else:
                response['error'] = 'Error during data update'
        
        return jsonify(response)
        
    except Exception as e:
        current_app.logger.error(f"Error updating data: {str(e)}")
        current_app.logger.exception(e)
        return jsonify({
            'error': str(e),
            'success': False,
            'logs': [f"ERROR: {str(e)}", "An unexpected error occurred during the data update."]
        }), 500