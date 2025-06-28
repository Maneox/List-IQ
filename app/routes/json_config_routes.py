# Standard imports
import json
import subprocess
import re
import os
from functools import wraps

# Flask imports
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from .decorators import admin_required

# Application imports
from ..models.list import List
from ..database import db, csrf
from ..services.scheduler_service import SchedulerService

json_config_bp = Blueprint('json_config_bp', __name__)

def check_list_ownership(f):
    @wraps(f)
    def decorated_function(list_id, *args, **kwargs):
        list_obj = List.query.get_or_404(list_id)
        
        # No ownership check for now
        # as the List model does not have a user_id attribute
        
        return f(list_id=list_id, list_obj=list_obj, *args, **kwargs)
    return decorated_function

@json_config_bp.route('/json-config/<int:list_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def json_config(list_id):
    """Configuration page for JSON import"""
    current_app.logger.info(f"Accessing JSON configuration page for list {list_id}")
    
    # Explicitly import List in this function to avoid scope issues
    from ..models.list import List
    
    # Get the list object
    list_obj = List.query.get_or_404(list_id)
    current_app.logger.info(f"List retrieved: {list_obj.name}")
    
    # Check if the list uses Curl API or JSON via URL
    config = list_obj.update_config
    current_app.logger.info(f"Configuration: {config}")
    
    # Check if it's a Curl API or JSON via URL type list
    is_curl_api = (list_obj.update_type == 'automatic' and 
                  config and 
                  config.get('source') == 'api' and 
                  config.get('api_type') == 'curl')
    
    is_json_url = (list_obj.update_type == 'automatic' and 
                  config and 
                  config.get('source') == 'url' and 
                  (config.get('is_json') == True or config.get('format') == 'json'))
    
    if not (is_curl_api or is_json_url):
        flash('This list does not require JSON configuration', 'warning')
        return redirect(url_for('list_bp.view_list', list_id=list_id))
    
    # Form processing
    if request.method == 'POST':
        # Get form data
        data_path = request.form.get('data_path', '')
        pagination_enabled = 'pagination_enabled' in request.form
        next_page_path = request.form.get('next_page_path', '')
        max_pages = int(request.form.get('max_pages', 10))
        
        # Get selected columns
        selected_columns = []
        for key, value in request.form.items():
            if key.startswith('include_column_'):
                column_name = key.replace('include_column_', '')
                column_type = request.form.get(f'column_type_{column_name}', 'text')
                selected_columns.append({
                    'name': column_name,
                    'type': column_type
                })
        
        # Update the configuration
        list_obj.json_data_path = data_path
        list_obj.json_pagination_enabled = pagination_enabled
        list_obj.json_next_page_path = next_page_path
        list_obj.json_max_pages = max_pages
        list_obj.json_selected_columns = json.dumps(selected_columns)
        list_obj.json_config_status = 'configured'
        
        # Explicitly set the data format to "json"
        list_obj.data_source_format = 'json'
        current_app.logger.info(f"Data format set to 'json' for list {list_id}")
        
        # Also update the configuration to ensure consistency
        config = list_obj.update_config
        config['format'] = 'json'
        config['is_json'] = True
        list_obj.update_config = config
        current_app.logger.info(f"Configuration updated with format='json' and is_json=True for list {list_id}")
        
        # Save the changes
        db.session.commit()
        
        # Check after saving that the format is correctly set
        db.session.refresh(list_obj)
        current_app.logger.info(f"After saving: format={list_obj.data_source_format}, config={list_obj.update_config}")
        
        # Trigger data import immediately
        try:
            # Check one last time that the format is correctly set to JSON
            if list_obj.data_source_format != 'json':
                current_app.logger.warning(f"Format still incorrect before import: {list_obj.data_source_format}. Forcing correction.")
                list_obj.data_source_format = 'json'
                config = list_obj.update_config
                config['format'] = 'json'
                config['is_json'] = True
                list_obj.update_config = config
                db.session.commit()
                db.session.refresh(list_obj)
            
            current_app.logger.info(f"Triggering data import for list {list_id} with format={list_obj.data_source_format}")
            
            # Directly use the update_from_url method of the List object
            # The update_from_url method already passes force_update=True to DataImporter.import_data
            if list_obj.update_from_url():
                current_app.logger.info(f"List {list_id} updated successfully")
                flash('JSON configuration saved and data import successful', 'success')
            else:
                current_app.logger.error(f"Failed to update list {list_id}")
                flash('JSON configuration saved but error during data import', 'warning')
                
        except Exception as e:
            current_app.logger.error(f"Error during data import: {str(e)}")
            flash(f'JSON configuration saved but error during data import: {str(e)}', 'warning')
        
        return redirect(url_for('list_bp.view_list', list_id=list_id))
    
    # Get raw data for preview
    raw_data_preview = None
    columns_preview = []
    output = None
    
    try:
        # Determine the data source (Curl API or JSON URL)
        is_curl_api = (list_obj.update_type == 'automatic' and 
                      config and 
                      config.get('source') == 'api' and 
                      config.get('api_type') == 'curl')
        
        is_json_url = (list_obj.update_type == 'automatic' and 
                      config and 
                      config.get('source') == 'url' and 
                      (config.get('is_json') == True or config.get('format') == 'json'))
        
        current_app.logger.info(f"Source type: is_curl_api={is_curl_api}, is_json_url={is_json_url}")
        
        # Get data according to the source
        if is_curl_api:
            # Execute the curl command to get the data
            curl_command = config.get('curl_command', '')
            if not curl_command:
                current_app.logger.error("Curl command not defined")
                raise Exception("Curl error: command not defined")
            
            # Détection d'un curl auto-bouclant sur l'API publique JSON du service
            from ..utils.internal_access import get_internal_list_data_from_public_json_url
            import re
            try:
                # Regex robuste : capture la première URL http(s) se terminant par /public/json/<token>
                match = re.search(r"https?://[^\s'\"]+/public/json/[\w-]+", curl_command)
                if match:
                    target_url = match.group(0)
                    current_app.logger.info(f"[OPTIM] Detected curl command targeting public JSON endpoint: {target_url}")
                    internal_data = get_internal_list_data_from_public_json_url(target_url)
                    if internal_data is not None:
                        output = json.dumps(internal_data)
                        current_app.logger.info(f"[OPTIM] JSON data retrieved directly via ORM (no curl): {output[:200]}...")
                    else:
                        # Fallback : exécution shell si ce n'est pas interne
                        current_app.logger.info("[OPTIM] Target URL is not internal or data not found, executing curl as usual.")
                        result = subprocess.run(curl_command, shell=True, capture_output=True, text=True, check=True)
                        output = result.stdout
                else:
                    # Cas général : exécution shell normale
                    current_app.logger.info("[OPTIM] No public JSON endpoint detected in curl_command, executing curl as usual.")
                    result = subprocess.run(curl_command, shell=True, capture_output=True, text=True, check=True)
                    output = result.stdout

                if not output:
                    current_app.logger.error("Error executing curl command: no output")
                    raise Exception("Curl error: no output")
            except subprocess.CalledProcessError as e:
                current_app.logger.error(f"Error executing curl command: {e}")
                current_app.logger.error(f"Error output: {e.stderr}")
                raise Exception(f"Curl error: {e}")
            except Exception as e:
                current_app.logger.error(f"Exception executing curl command: {e}")
                raise Exception(f"Curl error: {e}")
        
        elif is_json_url:
            # Get the URL from the configuration
            url = config.get('url', '')
            if not url:
                current_app.logger.error("URL not defined")
                raise Exception("Error: URL not defined")
            
            current_app.logger.info(f"Getting JSON data from URL: {url}")
            
            # Utilisation de la fonction utilitaire pour accès direct interne
            from ..utils.internal_access import get_internal_list_data_from_public_json_url
            internal_data = get_internal_list_data_from_public_json_url(url)
            if internal_data is not None:
                output = json.dumps(internal_data)
                current_app.logger.info(f"JSON data retrieved directly (internal utility): {output[:200]}...")
            else:
                # Standard method for external URLs
                import requests
                headers = {'Accept': 'application/json'}
                try:
                    # Disable SSL verification to bypass certificate errors
                    response = requests.get(url, headers=headers, timeout=30, verify=False)
                    response.raise_for_status()  # Raises an exception if the HTTP status is an error code
                    
                    # Check if the response is valid JSON
                    try:
                        # Try to parse directly as JSON
                        json_data = response.json()
                        output = json.dumps(json_data)
                        current_app.logger.info(f"JSON data retrieved successfully: {output[:200]}...")
                    except ValueError:
                        # If not valid JSON, use the raw text
                        output = response.text
                        current_app.logger.info(f"URL request result (raw text): {output[:200]}...")
                except requests.exceptions.SSLError as ssl_err:
                    current_app.logger.error(f"SSL error while getting data: {str(ssl_err)}")
                    raise Exception(f"SSL error: {str(ssl_err)}")
                except Exception as e:
                    current_app.logger.error(f"Error getting data from URL: {str(e)}")
                    raise Exception(f"Error getting data: {str(e)}")
        
        else:
            current_app.logger.error("Unsupported data source")
            raise Exception("Error: unsupported data source")
        
        # Parse the JSON output
        if output:
            try:
                raw_data = json.loads(output)
                current_app.logger.info(f"JSON data retrieved successfully")
                
                # Format the JSON data for display
                raw_data_preview = json.dumps(raw_data, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error parsing JSON: {str(e)}")
                current_app.logger.error(f"Raw output: {output[:200]}...")
                # Do not raise an exception here, but set raw_data_preview with the raw data
                raw_data_preview = output[:1000] + "..." if len(output) > 1000 else output
                raw_data = {}
        
        # Prepare the column preview if a path is defined
        data = raw_data
        if list_obj.json_data_path:
            try:
                for key in list_obj.json_data_path.split('.'):
                    if not key:
                        continue
                    if key.isdigit() and isinstance(data, list) and int(key) < len(data):
                        data = data[int(key)]
                    elif isinstance(data, dict) and key in data:
                        data = data[key]
                    elif isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    else:
                        current_app.logger.warning(f"Invalid JSON path: {list_obj.json_data_path}")
                        data = None
                        break
            except Exception as e:
                current_app.logger.error(f"Error navigating JSON data: {str(e)}")
                data = None
        
        # Determine available columns
        if data:
            if isinstance(data, dict):
                sample_data = data
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                sample_data = data[0]
            else:
                sample_data = {}
            
            for key, value in sample_data.items():
                column_type = 'text'
                if isinstance(value, (int, float)):
                    column_type = 'number'
                elif isinstance(value, str):
                    # Attempt to detect dates
                    if re.match(r'\d{4}-\d{2}-\d{2}', value):
                        column_type = 'date'
                    # Attempt to detect IP addresses
                    elif re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', value):
                        column_type = 'ip'
                
                columns_preview.append({
                    'name': key,
                    'type': column_type,
                    'include': True
                })
    except Exception as e:
        current_app.logger.error(f"Error getting JSON data: {str(e)}")
    
    return render_template('lists/json_config.html', 
                          list=list_obj, 
                          raw_data_preview=raw_data_preview,
                          columns_preview=columns_preview)

@json_config_bp.route('/test-json-path/<int:list_id>', methods=['POST'])
@login_required
@admin_required
def test_json_path(list_id):
    """Test a JSON path"""
    # Explicitly import necessary modules
    import json
    import os
    from flask import jsonify
    
    current_app.logger.info(f"Starting JSON path test for list {list_id}")
    current_app.logger.info(f"Content type: {request.content_type}")
    current_app.logger.info(f"Received data: {request.data}")
    
    # Initialize the result
    result = {
        'success': False,
        'message': '',
        'data': None
    }
    
    try:
        # Get the list object
        list_obj = List.query.get_or_404(list_id)
        
        # Get the JSON path
        data_path = ''
        
        # Check if data is in JSON or form-data format
        if request.content_type and 'application/json' in request.content_type:
            try:
                # Use request.json instead of request.get_json()
                data = request.json
                current_app.logger.info(f"Received JSON data: {data}")
                if data and 'data_path' in data:
                    data_path = data['data_path']
            except Exception as e:
                current_app.logger.error(f"Error getting JSON data: {str(e)}")
                result['message'] = f"Error getting JSON data: {str(e)}"
                return jsonify(result)
        else:
            data_path = request.form.get('data_path', '')
            current_app.logger.info(f"Received form data: {request.form}")
        
        current_app.logger.info(f"Testing JSON path: {data_path} for list {list_id}")
        
        # Get the configuration
        config = list_obj.update_config
        current_app.logger.info(f"Configuration: {config}")
        
        # Determine the data source (Curl API or JSON URL)
        is_curl_api = (list_obj.update_type == 'automatic' and 
                      config and 
                      config.get('source') == 'api' and 
                      config.get('api_type') == 'curl')
        
        is_json_url = (list_obj.update_type == 'automatic' and 
                      config and 
                      config.get('source') == 'url' and 
                      (config.get('is_json') == True or config.get('format') == 'json'))
        
        # Get data according to the source
        if is_curl_api:
            # Execute the curl command to get the data
            curl_command = config.get('curl_command', '')
            if not curl_command:
                result['message'] = "Curl command not defined"
                return jsonify(result)

            # Détection d'un curl auto-bouclant sur l'API publique JSON du service
            from ..utils.internal_access import get_internal_list_data_from_public_json_url
            import re
            match = re.search(r"https?://[^\s'\"]+/public/json/[\w-]+", curl_command)
            if match:
                target_url = match.group(0)
                current_app.logger.info(f"[OPTIM] Detected curl command targeting public JSON endpoint: {target_url}")
                internal_data = get_internal_list_data_from_public_json_url(target_url)
                if internal_data is not None:
                    output = json.dumps(internal_data)
                    current_app.logger.info(f"[OPTIM] JSON data retrieved directly via ORM (no curl): {output[:200]}...")
                else:
                    # Fallback : exécution shell si ce n'est pas interne
                    current_app.logger.info("[OPTIM] Target URL is not internal or data not found, executing curl as usual.")
                    try:
                        stream = os.popen(curl_command)
                        output = stream.read()
                        current_app.logger.info(f"Curl command result: {output[:200]}...")
                        if not output:
                            result['message'] = "Error executing curl command: no output"
                            return jsonify(result)
                    except Exception as e:
                        current_app.logger.error(f"Error executing curl command: {str(e)}")
                        result['message'] = f"Error executing curl command: {str(e)}"
                        return jsonify(result)
            else:
                # Cas général : exécution shell normale
                current_app.logger.info("[OPTIM] No public JSON endpoint detected in curl_command, executing curl as usual.")
                try:
                    stream = os.popen(curl_command)
                    output = stream.read()
                    current_app.logger.info(f"Curl command result: {output[:200]}...")
                    if not output:
                        result['message'] = "Error executing curl command: no output"
                        return jsonify(result)
                except Exception as e:
                    current_app.logger.error(f"Error executing curl command: {str(e)}")
                    result['message'] = f"Error executing curl command: {str(e)}"
                    return jsonify(result)

        
        elif is_json_url:
            # Get the URL from the configuration
            url = config.get('url', '')
            if not url:
                result['message'] = "URL not defined"
                return jsonify(result)
            
            current_app.logger.info(f"Getting JSON data from URL: {url}")
            
            # Get data from the URL
            try:
                import requests
                headers = {'Accept': 'application/json'}
                # Disable SSL verification to bypass certificate errors
                response = requests.get(url, headers=headers, timeout=30, verify=False)
                response.raise_for_status()  # Raises an exception if the HTTP status is an error code
                
                # Check if the response is valid JSON
                try:
                    # Try to parse directly as JSON
                    json_data = response.json()
                    output = json.dumps(json_data)
                    current_app.logger.info(f"JSON data retrieved successfully: {output[:200]}...")
                except ValueError:
                    # If not valid JSON, use the raw text
                    output = response.text
                    current_app.logger.info(f"URL request result (raw text): {output[:200]}...")
                
                if not output:
                    result['message'] = "Error retrieving data from URL: no data"
                    return jsonify(result)
            except requests.exceptions.SSLError as ssl_err:
                current_app.logger.error(f"SSL error getting data: {str(ssl_err)}")
                result['message'] = f"SSL error: {str(ssl_err)}"
                return jsonify(result)
            except Exception as e:
                current_app.logger.error(f"Error getting data from URL: {str(e)}")
                result['message'] = f"Error getting data from URL: {str(e)}"
                return jsonify(result)
        
        else:
            result['message'] = "Unsupported data source"
            return jsonify(result)
        
        # Parse the JSON output
        try:
            raw_data = json.loads(output)
            current_app.logger.info("JSON parsing successful")
        except Exception as e:
            current_app.logger.error(f"Error parsing JSON: {str(e)}")
            result['message'] = f"Error parsing JSON: {str(e)}"
            return jsonify(result)
        
        # Navigate through the data according to the provided path
        try:
            data = raw_data
            path_parts = data_path.split('.')
            current_app.logger.info(f"Path parts: {path_parts}")
            
            for key in path_parts:
                if not key:
                    continue
                
                current_app.logger.info(f"Processing key: {key}, current data type: {type(data).__name__}")
                
                if key.isdigit() and isinstance(data, list) and int(key) < len(data):
                    data = data[int(key)]
                elif isinstance(data, dict) and key in data:
                    data = data[key]
                elif isinstance(data, list) and len(data) > 0:
                    # If an element of a list is requested without specifying an index, take the first one
                    data = data[0]
                    # If the key exists in this element, use it
                    if isinstance(data, dict) and key in data:
                        data = data[key]
                    else:
                        current_app.logger.warning(f"Key '{key}' not found in the list element")
                        result['message'] = f"Key '{key}' not found in the list element"
                        return jsonify(result)
                else:
                    current_app.logger.warning(f"Key '{key}' not found in the data")
                    result['message'] = f"Key '{key}' not found in the data"
                    return jsonify(result)
            
            # Check that the extracted data is usable
            if isinstance(data, (dict, list)):
                if isinstance(data, list) and len(data) > 0:
                    # Display the first element as an example
                    sample = data[0] if isinstance(data[0], dict) else data
                    result['success'] = True
                    result['message'] = f"Valid path. {len(data)} elements found."
                    result['data'] = sample
                else:
                    result['success'] = True
                    result['message'] = "Valid path."
                    result['data'] = data
            else:
                result['message'] = f"The path points to a simple value ({type(data).__name__}), not an object or a list"
                
        except Exception as e:
            current_app.logger.error(f"Error navigating JSON data: {str(e)}")
            result['message'] = f"Error navigating JSON data: {str(e)}"
    except Exception as e:
        current_app.logger.error(f"Error testing JSON path: {str(e)}")
        result['message'] = f"Error testing JSON path: {str(e)}"
    
    current_app.logger.info(f"Final result: {result}")
    return jsonify(result)