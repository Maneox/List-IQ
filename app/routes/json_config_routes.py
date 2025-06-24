# Standard imports
import json
import subprocess
import re
import os
from werkzeug.utils import secure_filename
from exceptions import ConfigurationError, CurlExecutionError

# Constants for curl error messages
CURL_COMMAND_NOT_DEFINED = "Curl command not defined"
CURL_NO_OUTPUT = "Curl command returned no output"
CURL_EXECUTION_FAILED = "Curl command failed: {error}"
CURL_UNEXPECTED_ERROR = "An unexpected error occurred during curl execution: {error}"
CURL_URL_NOT_DEFINED = "URL not defined"
MIME_TYPE_JSON = "application/json"
PUBLIC_JSON_PATH = "/public/json/"

# Flask imports
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from routes.decorators import admin_required

# Application imports
from models.list import List
from database import db, csrf
from services.scheduler_service import SchedulerService

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
    """Page de configuration pour l'import JSON (refactorisée)"""
    from models.list import List
    list_obj, config = _get_list_and_config(list_id)

    if not (_is_curl_api(list_obj, config) or _is_json_url(list_obj, config)):
        return _handle_error('Cette liste ne nécessite pas de configuration JSON', 'list_bp.view_list', list_id)

    if request.method == 'POST':
        form_data = _extract_form_data(request.form)
        selected_columns = _get_selected_columns(request.form)
        form_data['selected_columns'] = selected_columns
        _update_list_config(list_obj, form_data)
        try:
            _import_data(list_obj)
            flash('Configuration JSON enregistrée et import réussi', 'success')
        except Exception as e:
            current_app.logger.error(f"Erreur lors de l'import : {str(e)}")
            flash(f'Configuration JSON enregistrée mais erreur lors de l\'import : {str(e)}', 'warning')
        return redirect(url_for('list_bp.view_list', list_id=list_id))

    # Préparation de l'aperçu
    raw_data_preview, columns_preview = _prepare_preview(list_obj, config)
    return render_template('lists/json_config.html', 
                          list=list_obj, 
                          raw_data_preview=raw_data_preview, 
                          columns_preview=columns_preview)

# --- Sous-fonction pour l’aperçu JSON/colonnes ---
def _prepare_preview(list_obj, config):
    """
    Prépare l’aperçu des données JSON et des colonnes détectées
    à partir de la configuration de la liste (Curl ou URL).
    Retourne (raw_data_preview, columns_preview).
    """
    import re
    import json
    import subprocess
    import requests
    raw_data_preview = None
    columns_preview = []
    output = None
    # 1. Détection de la source
    is_curl_api = _is_curl_api(list_obj, config)
    is_json_url = _is_json_url(list_obj, config)
    try:
        if is_curl_api:
            curl_command = config.get('curl_command', '')
            if not curl_command:
                raise ConfigurationError(CURL_COMMAND_NOT_DEFINED)
            try:
                result = subprocess.run(curl_command, shell=True, capture_output=True, text=True, check=True)
                output = result.stdout
                if not output:
                    raise CurlExecutionError(CURL_NO_OUTPUT)
            except subprocess.CalledProcessError as e:
                raise CurlExecutionError(f"Curl command failed: {e.stderr}") from e
            except Exception as e:
                raise CurlExecutionError(f"Unexpected error during curl execution: {e}") from e
        elif is_json_url:
            url = config.get('url', '')
            if not url:
                raise ConfigurationError(CURL_URL_NOT_DEFINED)
            # Détection URL interne (application)
            import os
            app_domain = os.environ.get('SERVER_NAME') or (hasattr(current_app, 'config') and current_app.config.get('SERVER_NAME', 'localhost'))
            internal_domains = ["localhost:5000", "web:5000", "nginx", app_domain]
            is_internal_url = any(domain in url for domain in internal_domains)
            if is_internal_url and PUBLIC_JSON_PATH in url:
                parts = url.split(PUBLIC_JSON_PATH)
                if len(parts) == 2:
                    public_id = parts[1].split("?")[0].strip()
                    from models.list import List
                    source_list = List.query.filter_by(public_access_token=public_id).first()
                    if source_list:
                        json_data = source_list.generate_public_json()
                        output = json.dumps(json_data)
                    else:
                        raise ConfigurationError(f"List with public ID {public_id} not found")
                else:
                    raise ConfigurationError(f"Invalid internal URL format: {url}")
            else:
                headers = {'Accept': MIME_TYPE_JSON}
                try:
                    response = requests.get(url, headers=headers, timeout=30, verify=os.environ.get('VERIFY_SSL', True)) #utiliser la variable d'environement VERIFY_SSL 
                    response.raise_for_status()
                    try:
                        json_data = response.json()
                        output = json.dumps(json_data)
                    except ValueError:
                        output = response.text
                except Exception as e:
                    raise CurlExecutionError(f"Error getting data: {str(e)}")
        else:
            raise ConfigurationError("Unsupported data source for preview")
        # 2. Parsing JSON
        raw_data = {}
        if output:
            try:
                raw_data = json.loads(output)
                raw_data_preview = json.dumps(raw_data, indent=2, ensure_ascii=False)
            except Exception as e:
                current_app.logger.error(f"Error parsing JSON: {str(e)}")
                current_app.logger.error(f"Raw output: {output[:200]}...")
                raise ConfigurationError(f"Erreur lors de l'analyse du JSON : {str(e)}")
        # 3. Navigation dans le chemin JSON (si défini)
        data = raw_data
        if getattr(list_obj, 'json_data_path', None):
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
                        data = None
                        break
            except Exception:
                data = None
        # 4. Extraction des colonnes (échantillon)
        sample_data = {}
        if data:
            if isinstance(data, dict):
                sample_data = data
            elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                sample_data = data[0]
        for key, value in sample_data.items():
            column_type = 'text'
            if isinstance(value, (int, float)):
                column_type = 'number'
            elif isinstance(value, str):
                if re.match(r'\d{4}-\d{2}-\d{2}', value):
                    column_type = 'date'
                elif re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', value):
                    column_type = 'ip'
            columns_preview.append({'name': key, 'type': column_type, 'include': True})
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la préparation de l'aperçu JSON : {str(e)}")
    return raw_data_preview, columns_preview

# --- Sous-fonctions privées ---
def _get_list_and_config(list_id):
    from models.list import List
    list_obj = List.query.get_or_404(list_id)
    config = list_obj.update_config
    return list_obj, config

def _is_curl_api(list_obj, config):
    return (
        list_obj.update_type == 'automatic' and
        config and
        config.get('source') == 'api' and
        config.get('api_type') == 'curl'
    )

def _is_json_url(list_obj, config):
    return (
        list_obj.update_type == 'automatic' and
        config and
        config.get('source') == 'url' and
        (config.get('is_json') is True or config.get('format') == 'json')
    )

def _extract_form_data(form):
    return {
        'data_path': form.get('data_path', ''),
        'pagination_enabled': 'pagination_enabled' in form,
        'next_page_path': form.get('next_page_path', ''),
        'max_pages': int(form.get('max_pages', 10)),
    }

def _get_selected_columns(form):
    selected_columns = []
    for key, value in form.items():
        if key.startswith('include_column_'):
            column_name = key.replace('include_column_', '')
            column_type = form.get(f'column_type_{column_name}', 'text')
            selected_columns.append({
                'name': column_name,
                'type': column_type
            })
    return selected_columns

def _update_list_config(list_obj, form_data):
    list_obj.json_data_path = form_data['data_path']
    list_obj.json_pagination_enabled = form_data['pagination_enabled']
    list_obj.json_next_page_path = form_data['next_page_path']
    list_obj.json_max_pages = form_data['max_pages']
    list_obj.json_selected_columns = json.dumps(form_data['selected_columns'])
    list_obj.json_config_status = 'configured'
    list_obj.data_source_format = 'json'
    config = list_obj.update_config
    config['format'] = 'json'
    config['is_json'] = True
    list_obj.update_config = config
    db.session.commit()
    db.session.refresh(list_obj)

def _import_data(list_obj):
    if list_obj.data_source_format != 'json':
        list_obj.data_source_format = 'json'
        config = list_obj.update_config
        config['format'] = 'json'
        config['is_json'] = True
        list_obj.update_config = config
        db.session.commit()
        db.session.refresh(list_obj)
    if not list_obj.update_from_url():
        raise ConfigurationError("Erreur lors de la mise à jour des données")

    
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
                current_app.logger.error(CURL_COMMAND_NOT_DEFINED)
                raise ConfigurationError(CURL_COMMAND_NOT_DEFINED)
            
            current_app.logger.info(f"Executing curl command: {curl_command}")
            
            # Execute the curl command and capture the output
            try:
                result = subprocess.run(curl_command, shell=True, capture_output=True, text=True, check=True)
                output = result.stdout
                
                if not output:
                    current_app.logger.error(CURL_NO_OUTPUT)
                    raise CurlExecutionError(CURL_NO_OUTPUT)
            except subprocess.CalledProcessError as e:
                error_message = CURL_EXECUTION_FAILED.format(error=e.stderr)
                current_app.logger.error(f"Error executing curl command: {e}")
                current_app.logger.error(f"Error output: {e.stderr}")
                raise CurlExecutionError(error_message) from e
            except Exception as e:
                error_message = CURL_UNEXPECTED_ERROR.format(error=e)
                current_app.logger.error(f"Exception executing curl command: {e}")
                raise CurlExecutionError(error_message) from e
        
        elif is_json_url:
            # Get the URL from the configuration
            url = config.get('url', '')
            if not url:
                current_app.logger.error(CURL_URL_NOT_DEFINED)
                raise ConfigurationError(CURL_URL_NOT_DEFINED)
            
            current_app.logger.info(f"Getting JSON data from URL: {url}")
            
            # Detect if the URL points to our own application
            import os
            
            # Get the application domain from the SERVER_NAME environment variable
            # or from the Flask configuration
            app_domain = os.environ.get('SERVER_NAME') or current_app.config.get('SERVER_NAME', 'localhost')
            current_app.logger.info(f"Application domain detected: {app_domain}")
            
            # Add other possible internal domains
            internal_domains = ["localhost:5000", "web:5000", "nginx", app_domain]
            
            is_internal_url = False
            for domain in internal_domains:
                if domain in url:
                    is_internal_url = True
                    break
            
            if is_internal_url and PUBLIC_JSON_PATH in url:
                current_app.logger.info("Detected an internal URL, using an alternative method")
                
                # Extract the public list identifier from the URL
                # Expected format: .../public/json/IDENTIFIER
                parts = url.split(PUBLIC_JSON_PATH)
                if len(parts) == 2:
                    public_id = parts[1].split("?")[0].strip()
                    
                    # Use an alternative method to get the data
                    from models.list import List
                    
                    # Search for the list corresponding to this public identifier
                    source_list = List.query.filter_by(public_access_token=public_id).first()
                    
                    if source_list:
                        current_app.logger.info(f"Internal list found with ID {source_list.id}")
                        # Directly generate the JSON data
                        json_data = source_list.generate_public_json()
                        output = json.dumps(json_data)
                        current_app.logger.info(f"JSON data retrieved directly: {output[:200]}...")
                    else:
                        current_app.logger.error(f"Internal list with public ID {public_id} not found")
                        raise ConfigurationError(f"List with public ID {public_id} not found")
                else:
                    current_app.logger.error(f"Invalid internal URL format: {url}")
                    raise ConfigurationError(f"Invalid internal URL format: {url}")
            else:
                # Standard method for external URLs
                import requests
                headers = {'Accept': MIME_TYPE_JSON}
                try:
                    # Disable SSL verification to bypass certificate errors
                    response = requests.get(url, headers=headers, timeout=30, verify=os.environ.get('VERIFY_SSL', True))
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
                    raise CurlExecutionError(f"SSL error: {str(ssl_err)}")
                except Exception as e:
                    current_app.logger.error(f"Error getting data from URL: {str(e)}")
                    raise CurlExecutionError(f"Error getting data: {str(e)}")
        
        else:
            current_app.logger.error("Unsupported data source")
            raise UnsupportedDataSourceError("Error: unsupported data source")
        
        # Parse the JSON output
        if output:
            try:
                raw_data = json.loads(output)
                current_app.logger.info("JSON data retrieved successfully")
                
                # Format the JSON data for display
                raw_data_preview = json.dumps(raw_data, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error parsing JSON: {str(e)}")
                current_app.logger.error(f"Raw output: {output[:200]}...")
                raise ConfigurationError(f"Erreur lors de l'analyse du JSON : {str(e)}")
        
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
        if request.content_type and MIME_TYPE_JSON in request.content_type:
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
                result['message'] = CURL_COMMAND_NOT_DEFINED
                return jsonify(result)
            
            current_app.logger.info(f"Executing curl command: {curl_command}")
            
            # Execute the curl command and capture the output
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
                result['message'] = CURL_URL_NOT_DEFINED
                return jsonify(result)
            
            current_app.logger.info(f"Getting JSON data from URL: {url}")
            
            # Get data from the URL
            try:
                import requests
                headers = {'Accept': MIME_TYPE_JSON}
                # Disable SSL verification to bypass certificate errors
                response = requests.get(url, headers=headers, timeout=30, verify=os.environ.get('VERIFY_SSL', True))
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