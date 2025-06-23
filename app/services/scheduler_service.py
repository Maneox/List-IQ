from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import croniter
from datetime import datetime
from models.list import List, db
import logging
from flask import current_app
import json
import subprocess
import tempfile
import os

# Import timezone utilities
from utils.timezone_utils import get_paris_now, utc_to_paris, PARIS_TIMEZONE, format_datetime
from typing import Dict, Any, Optional, List as TypeList, Tuple
from services.list_service import ListService

logger = logging.getLogger(__name__)

class SchedulerService:
    _instance = None
    
    def __new__(cls, app=None):
        if cls._instance is None:
            cls._instance = super(SchedulerService, cls).__new__(cls)
            cls._instance.initialized = False
            # Use a BackgroundScheduler with a memory job store to avoid job loss
            cls._instance.scheduler = BackgroundScheduler({
                'apscheduler.jobstores.default': {
                    'type': 'memory'
                },
                'apscheduler.executors.default': {
                    'class': 'apscheduler.executors.pool:ThreadPoolExecutor',
                    'max_workers': '20'
                },
                'apscheduler.job_defaults.coalesce': 'false',
                'apscheduler.job_defaults.max_instances': '1',
                'apscheduler.timezone': 'Europe/Paris',
            })
            cls._instance.scheduler.start()
            logger.info("Scheduler started successfully")
        return cls._instance
    
    def __init__(self, app=None):
        # Avoid multiple initializations
        if hasattr(self, 'initialized') and self.initialized:
            return
            
        self.app = app
        self.initialized = True
        
        if app:
            with app.app_context():
                self._schedule_all_lists()
    
    def init_app(self, app):
        if self.app is None:
            self.app = app
            with app.app_context():
                self._schedule_all_lists()
    
    def _schedule_all_lists(self):
        """Schedules all active lists with automatic updates"""
        try:
            # Remove all existing jobs to avoid duplicates
            for job in self.scheduler.get_jobs():
                self.scheduler.remove_job(job.id)
                
            logger.info("All previous jobs have been deleted")
            
            # Reschedule all active lists
            lists = List.query.filter_by(update_type='automatic', is_active=True).all()
            
            if not lists:
                logger.warning("No active lists with automatic updates found")
                return
                
            logger.info(f"Scheduling {len(lists)} active lists with automatic updates")
            
            for list_obj in lists:
                self._schedule_list(list_obj)
                
            # Display all scheduled jobs
            jobs = self.scheduler.get_jobs()
            logger.info(f"Scheduled jobs: {len(jobs)}")
            for job in jobs:
                logger.info(f"  - {job.id}: {job.name}, next run: {job.next_run_time}")
                
            logger.info(f"Scheduling finished for {len(lists)} lists")
        except Exception as e:
            logger.error(f"Error scheduling lists: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _schedule_list(self, list_obj: List):
        """Schedules a list's update"""
        if not list_obj.update_schedule:
            logger.warning(f"List {list_obj.id} ({list_obj.name}): No schedule defined")
            return
            
        try:
            # Check that the cron expression is valid
            cron = croniter.croniter(list_obj.update_schedule)
            next_run = cron.get_next(datetime)
            
            # Create the cron trigger
            trigger = CronTrigger.from_crontab(list_obj.update_schedule)
            
            # Schedule the task
            job_id = f'list_{list_obj.id}'
            
            # Remove the existing job if it exists
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Existing job removed for list {list_obj.id} ({list_obj.name})")
            
            self.scheduler.add_job(
                func=self._update_list_data,
                trigger=trigger,
                args=[list_obj.id],
                id=job_id,
                name=f"Update list {list_obj.name}",
                misfire_grace_time=3600  # Allow missed updates to run within the hour
            )
            logger.info(f"Scheduling for list {list_obj.name} (ID: {list_obj.id}) with cron {list_obj.update_schedule}")
            logger.info(f"Next scheduled run: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Immediately run the update for testing
            # self._update_list_data(list_obj.id)
            
        except Exception as e:
            logger.error(f"Error scheduling list {list_obj.id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    @staticmethod
    def _execute_python_script(script_content: str) -> tuple[Optional[TypeList[Dict[str, Any]]], list[str]]:
        """Executes a Python script and returns the resulting JSON data and logs"""
        # List to store execution logs
        execution_logs = []
        
        try:
            # Create a temporary file for the script
            with tempfile.NamedTemporaryFile(delete=False, suffix='.py', mode='w') as temp_file:
                temp_filename = temp_file.name
                # Write the script content to the temporary file
                temp_file.write(script_content)
            
            log_message = f"Executing Python script: {temp_filename}"
            logger.info(log_message)
            execution_logs.append(log_message)
            
            # Prepare the execution environment
            script_globals = {}
            script_locals = {}
            
            # Custom function to capture prints
            def custom_print(*args, **kwargs):
                output = ' '.join(str(arg) for arg in args)
                execution_logs.append(f"SCRIPT OUTPUT: {output}")
                logger.info(f"SCRIPT OUTPUT: {output}")
            
            # Replace the standard print function with our custom one
            script_globals['print'] = custom_print
            
            # Configure proxy and SSL, and patch requests.get for the script environment
            try:
                from flask import current_app
                import os
                import urllib3
                import requests # Import requests here to patch it
                from requests.packages.urllib3.exceptions import InsecureRequestWarning
                
                # Get proxy and SSL configurations
                verify_ssl = current_app.config.get('VERIFY_SSL', 'false').lower() == 'true'
                http_proxy = current_app.config.get('HTTP_PROXY', os.environ.get('HTTP_PROXY', ''))
                https_proxy = current_app.config.get('HTTPS_PROXY', os.environ.get('HTTPS_PROXY', ''))
                no_proxy = current_app.config.get('NO_PROXY', os.environ.get('NO_PROXY', ''))
                
                # Also check lowercase variables for compatibility
                if not http_proxy: http_proxy = current_app.config.get('http_proxy', os.environ.get('http_proxy', ''))
                if not https_proxy: https_proxy = current_app.config.get('https_proxy', os.environ.get('https_proxy', ''))
                if not no_proxy: no_proxy = current_app.config.get('no_proxy', os.environ.get('no_proxy', ''))
                    
                ca_bundle = os.environ.get('REQUESTS_CA_BUNDLE', '')
                ssl_cert_file = os.environ.get('SSL_CERT_FILE', '')
                
                proxies = None
                if http_proxy or https_proxy:
                    proxies = {}
                    if http_proxy: proxies['http'] = http_proxy
                    if https_proxy: proxies['https'] = https_proxy
                    log_message = f"Using proxy for Python script: {proxies}"
                    logger.info(log_message)
                    execution_logs.append(log_message)
                else:
                    log_message = "No proxy used for Python script"
                    logger.info(log_message)
                    execution_logs.append(log_message)
                
                if not verify_ssl:
                    urllib3.disable_warnings(InsecureRequestWarning)
                    log_message = "SSL verification disabled for Python script"
                    logger.info(log_message)
                    execution_logs.append(log_message)
                
                if ca_bundle:
                    log_message = f"Using custom CA certificate: {ca_bundle}"
                    logger.info(log_message)
                    execution_logs.append(log_message)
                if ssl_cert_file:
                    log_message = f"Using custom SSL certificate: {ssl_cert_file}"
                    logger.info(log_message)
                    execution_logs.append(log_message)
                
                original_requests_get = requests.get # Save the original
                
                def patched_requests_get(url, **kwargs):
                    """Wrapper for requests.get that injects proxy and verify_ssl if not specified."""
                    if proxies and 'proxies' not in kwargs:
                        kwargs['proxies'] = proxies
                    if 'verify' not in kwargs:
                        kwargs['verify'] = verify_ssl
                    
                    log_msg = f"HTTP call (patched): GET {url} (proxy: {'yes' if kwargs.get('proxies') else 'no'}, verify_ssl: {kwargs.get('verify')})"
                    logger.info(log_msg)
                    execution_logs.append(log_msg)
                    return original_requests_get(url, **kwargs)
                
                requests.get = patched_requests_get # Apply the patch

                # Provide an http_get helper function for convenience
                def http_get_helper(url, headers=None, params=None, timeout=30):
                    request_params = {'timeout': timeout}
                    if headers: request_params['headers'] = headers
                    if params: request_params['params'] = params
                    # requests.get is already patched here
                    response = requests.get(url, **kwargs)
                    response.raise_for_status()
                    return response
                
                script_globals['http_get'] = http_get_helper
                script_globals['proxies'] = proxies # For reference in the user's script
                script_globals['verify_ssl'] = verify_ssl # For reference
                script_globals['requests'] = requests # Put the (patched) requests module in globals

            except Exception as e:
                log_message = f"Error configuring proxies and SSL for the script: {str(e)}"
                logger.error(log_message)
                execution_logs.append(f"Internal ERROR (proxy/SSL setup): {log_message}")
                # Fallback: ensure 'requests' is available even if the patch failed
                if 'requests' not in script_globals:
                    import requests as unpatched_requests # Use an alias to avoid confusion
                    script_globals['requests'] = unpatched_requests
                    execution_logs.append("WARNING: The original (unpatched) requests module is used due to a proxy/SSL configuration error.")
                

            
            # Add useful modules for scripts
            script_globals['requests'] = requests
            
            # Execute the script in a secure environment
            try:
                # Compile the script
                compiled_code = compile(script_content, '<string>', 'exec')
                
                # Execute the compiled code
                exec(compiled_code, script_globals, script_locals)
                
                # Check if the main function exists
                if 'main' in script_locals and callable(script_locals['main']):
                    # Call the main function
                    log_message = "Calling the script's main() function"
                    logger.info(log_message)
                    execution_logs.append(log_message)
                    
                    result = script_locals['main']()
                    
                    # Check that the result is a list
                    if isinstance(result, list):
                        log_message = f"Python script executed successfully, {len(result)} entries retrieved"
                        logger.info(log_message)
                        execution_logs.append(log_message)
                        
                        # Add a sample of the retrieved data for debugging
                        if result:
                            sample = result[0] if len(result) == 1 else result[:2]
                            log_message = f"Sample data: {json.dumps(sample, indent=2, ensure_ascii=False)}"
                            logger.info(log_message)
                            execution_logs.append(log_message)
                            
                        return result, execution_logs
                    else:
                        log_message = f"The Python script must return a list, but returned {type(result).__name__}"
                        logger.error(log_message)
                        execution_logs.append(f"ERROR: {log_message}")
                        return None, execution_logs
                else:
                    log_message = "The Python script must contain a 'main' function that returns the data"
                    logger.error(log_message)
                    execution_logs.append(f"ERROR: {log_message}")
                    return None, execution_logs
            except Exception as e:
                log_message = f"Error executing the Python script: {str(e)}"
                logger.error(log_message)
                execution_logs.append(f"ERROR: {log_message}")
                
                import traceback
                tb = traceback.format_exc()
                logger.error(tb)
                execution_logs.append(f"TRACEBACK: {tb}")
                return None, execution_logs
            finally:
                # Clean up the temporary file
                try:
                    os.unlink(temp_filename)
                except Exception:
                    pass
        except Exception as e:
            log_message = f"Error preparing the Python script: {str(e)}"
            logger.error(log_message)
            execution_logs.append(f"ERROR: {log_message}")
            return None, execution_logs
            
    @staticmethod
    def _execute_curl_command(curl_command: str, list_obj=None) -> Optional[TypeList[Dict[str, Any]]]:
        """Executes a curl command and returns the resulting JSON data
        
        Args:
            curl_command: The curl command to execute
            list_obj: The list object to apply the results limit
        """
        try:
            # Create a temporary file to store the output
            with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as temp_file:
                temp_filename = temp_file.name
            
            # Execute the curl command and redirect the output to the temporary file
            logger.info(f"Executing curl command: {curl_command}")
            process = subprocess.run(
                curl_command + f" > {temp_filename}", 
                shell=True, 
                capture_output=True, 
                text=True
            )
            
            if process.returncode != 0:
                logger.error(f"Curl command failed with error: {process.stderr}")
                return None
            
            # Read the temporary file
            with open(temp_filename, 'r') as f:
                content = f.read()
            
            # Delete the temporary file
            os.unlink(temp_filename)
            
            # Try to parse the content as JSON
            try:
                data = json.loads(content)
                return SchedulerService._normalize_json_data(data, list_obj)
            except json.JSONDecodeError:
                # Try to clean the content if it's not valid JSON
                logger.warning(f"Failed to parse JSON from curl output, attempting to clean content: {content[:100]}...")
                try:
                    # Try to find JSON in the content (sometimes surrounded by HTML or other characters)
                    import re
                    json_match = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
                    if json_match:
                        potential_json = json_match.group(0)
                        data = json.loads(potential_json)
                        return SchedulerService._normalize_json_data(data, list_obj)
                    else:
                        logger.error("No JSON-like content found in the response")
                        return None
                except Exception as e:
                    logger.error(f"Failed to clean and parse JSON: {str(e)}")
                    return None
        except Exception as e:
            logger.error(f"Error executing curl command: {str(e)}")
            return None
    
    def _modify_curl_for_pagination(self, curl_command, next_page_url):
        """Modifies a curl command to use the next page URL"""
        logger = logging.getLogger('services.scheduler_service')
        
        try:
            # Check that the next page URL is valid
            if not next_page_url or not isinstance(next_page_url, str):
                logger.error(f"Invalid next page URL: {next_page_url}")
                return None
            
            # Replace the URL in the curl command
            # Case 1: URL between single quotes
            if "'http" in curl_command:
                pattern = r"'(https?://[^']*)'" 
                modified_command = re.sub(pattern, f"'{next_page_url}'" if "'" not in next_page_url else f'"{next_page_url}"', curl_command, count=1)
            # Case 2: URL between double quotes
            elif '"http' in curl_command:
                pattern = r'"(https?://[^"]*)"'
                modified_command = re.sub(pattern, f'"{next_page_url}"' if '"' not in next_page_url else f"'{next_page_url}'", curl_command, count=1)
            # Case 3: URL without quotes
            else:
                pattern = r'(https?://[^\s]*)'
                modified_command = re.sub(pattern, next_page_url, curl_command, count=1)
            
            # Check that the command was actually modified
            if modified_command == curl_command:
                logger.error(f"Could not find the URL in the curl command: {curl_command}")
                return None
            
            logger.info(f"Curl command modified for pagination: {modified_command}")
            return modified_command
            
        except Exception as e:
            logger.error(f"Error modifying the curl command for pagination: {str(e)}")
            return None
    
    @staticmethod
    def _normalize_json_data(data, list_obj=None):
        """Normalizes JSON data to make it compatible with the expected format
        
        Args:
            data: The JSON data to normalize
            list_obj: The List object containing the JSON configuration (optional)
        """
        logger = logging.getLogger('services.scheduler_service')
        
        # If we have a specific JSON configuration, use it
        if list_obj and list_obj.json_config_status == 'configured' and list_obj.json_data_path:
            logger.info(f"Using JSON configuration for list {list_obj.id}")
            try:
                # Navigate through the data according to the specified path
                result_data = data
                for key in list_obj.json_data_path.split('.'):
                    if not key:
                        continue
                    
                    if isinstance(result_data, dict) and key in result_data:
                        result_data = result_data[key]
                    elif isinstance(result_data, list) and len(result_data) > 0:
                        # If it's a list, take the first element to continue navigation
                        # but keep the whole list as the final result
                        if key.isdigit():
                            # If the key is a number, use it as an index
                            index = int(key)
                            if index < len(result_data):
                                result_data = result_data[index]
                            else:
                                logger.error(f"Index {index} out of bounds for list of size {len(result_data)}")
                                return []
                        else:
                            # Otherwise, search for the key in all list elements
                            temp_data = []
                            for item in result_data:
                                if isinstance(item, dict) and key in item:
                                    temp_data.append(item[key])
                            result_data = temp_data if temp_data else result_data
                    else:
                        logger.error(f"Key {key} not found in the data")
                        return []
                
                # Filter columns according to the configuration
                if list_obj.json_selected_columns and isinstance(result_data, list):
                    selected_columns = list_obj.get_json_selected_columns
                    if selected_columns:
                        column_names = [col['name'] for col in selected_columns]
                        filtered_data = []
                        for item in result_data:
                            if isinstance(item, dict):
                                filtered_item = {col: item.get(col) for col in column_names if col in item}
                                filtered_data.append(filtered_item)
                            else:
                                filtered_data.append({"value": item})
                        return filtered_data
                
                # Ensure the result is a list of dictionaries
                if isinstance(result_data, list):
                    # Apply the results limit if defined
                    if list_obj.max_results > 0 and len(result_data) > list_obj.max_results:
                        logger.info(f"Results limit applied: {list_obj.max_results} out of {len(result_data)} available results")
                        result_data = result_data[:list_obj.max_results]
                    
                    if all(isinstance(item, dict) for item in result_data):
                        return result_data
                    return [item if isinstance(item, dict) else {"value": item} for item in result_data]
                elif isinstance(result_data, dict):
                    return [result_data]
                else:
                    return [{"value": result_data}]
                    
            except Exception as e:
                logger.error(f"Error normalizing JSON data with configuration: {str(e)}")
                # In case of error, use the standard method
        
        # Standard normalization method (without specific configuration)
        # Case 1: The data is a list
        if isinstance(data, list):
            # Apply the results limit if defined and if list_obj is provided
            logger.info(f"Checking conditions to apply limit: list_obj={list_obj is not None}, max_results={list_obj.max_results if list_obj else 'N/A'}, len(data)={len(data)}")
            
            if list_obj and list_obj.max_results > 0 and len(data) > list_obj.max_results:
                logger.info(f"Results limit applied: {list_obj.max_results} out of {len(data)} available results")
                data = data[:list_obj.max_results]
                logger.info(f"After limit: len(data)={len(data)}")
            else:
                logger.info(f"No limit applied. Possible reasons: list_obj absent, max_results=0 or len(data)<={list_obj.max_results if list_obj else 'N/A'}")
            
            # Case 1.1: List of objects (dictionaries) - ideal format
            if all(isinstance(item, dict) for item in data):
                return data
            # Case 1.2: List of simple values - convert them to dictionaries
            return [item if isinstance(item, dict) else {"value": item} for item in data]
        
        # Case 2: The data is a dictionary
        elif isinstance(data, dict):
            # Case 2.1: The dictionary contains a key that is a list (common API format)
            for key, value in data.items():
                if isinstance(value, list):
                    # Recurse to normalize this list
                    return SchedulerService._normalize_json_data(value, list_obj)
            
            # Case 2.2: The dictionary contains nested data
            # Look for common keys that might contain the main data
            common_data_keys = ["data", "results", "items", "content", "response", "genres"]
            # Add debugging to see the data structure
            logger.info(f"JSON data structure: {list(data.keys()) if isinstance(data, dict) else 'Not-a-dictionary'}")
            for key in common_data_keys:
                if key in data and (isinstance(data[key], list) or isinstance(data[key], dict)):
                    return SchedulerService._normalize_json_data(data[key], list_obj)
            
            # Case 2.3: The dictionary itself is a data entry
            return [data]
        
        # Case 3: The data is a simple value (number, string, etc.)
        elif data is not None:
            return [{"value": data}]
        
        # Case 4: The data is None
        else:
            return []
    
    def _update_list_data(self, list_id: int) -> tuple[bool, list[str]]:
        """Updates a list's data by its ID and returns a tuple (success, logs)"""
        # List to store execution logs
        execution_logs = []
        
        try:
            with self.app.app_context():
                # Get the list
                list_obj = List.query.get(list_id)
                if not list_obj:
                    error_msg = f"List {list_id} not found"
                    logger.error(error_msg)
                    execution_logs.append(f"ERROR: {error_msg}")
                    return False, execution_logs
                    
                logger.info(f"Starting update of list {list_id} ({list_obj.name}) at {get_paris_now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Get the update configuration
                config = list_obj.get_update_config
                if not config:
                    error_msg = f"No update configuration found for list {list_id}"
                    logger.error(error_msg)
                    execution_logs.append(f"ERROR: {error_msg}")
                    return False, execution_logs
                
                data = None
                # Get data according to the source
                if config.get('source') == 'url':
                    try:
                        # Check that fetch_data_from_url is a callable method
                        if callable(getattr(ListService, 'fetch_data_from_url', None)):
                            # Add logs to debug the CSV configuration
                            logger.info(f"Complete configuration for list {list_id}: {config}")
                            
                            # Check if a specific CSV configuration is present
                            csv_config = config.get('csv_config', {})
                            logger.info(f"Detected CSV configuration: {csv_config}")
                            
                            # Use DataImporter to take the CSV configuration into account
                            log_msg = f"Using DataImporter for list {list_id} to take CSV configuration into account"
                            logger.info(log_msg)
                            execution_logs.append(log_msg)
                            
                            # Display the list's configuration before import
                            config = list_obj.get_update_config
                            log_msg = f"List configuration before import: {config}"
                            logger.info(log_msg)
                            execution_logs.append(log_msg)
                            
                            # Display the current data format
                            log_msg = f"Current data format: {list_obj.data_source_format}"
                            logger.info(log_msg)
                            execution_logs.append(log_msg)
                            
                            # Check if is_json is present in the configuration
                            if 'is_json' in config:
                                log_msg = f"is_json in configuration: {config['is_json']} (type: {type(config['is_json']).__name__})"
                                logger.info(log_msg)
                                execution_logs.append(log_msg)
                            
                            # Use DataImporter to import data from the URL
                            from models.data_importer import DataImporter
                            importer = DataImporter(list_obj)
                            row_count = importer.import_data(force_update=False)
                            
                            log_msg = f"Import successful: {row_count} rows imported"
                            logger.info(log_msg)
                            execution_logs.append(log_msg)
                            
                            # Indicate that the update was successful
                            return True, execution_logs
                        else:
                            error_msg = "fetch_data_from_url is not callable in ListService"
                            logger.error(error_msg)
                            execution_logs.append(f"ERROR: {error_msg}")
                            return False, execution_logs
                    except Exception as e:
                        error_msg = f"Error processing data from URL: {str(e)}"
                        logger.error(error_msg)
                        logger.exception(e)  # Log the full exception
                        execution_logs.append(f"ERROR: {error_msg}")
                        
                        # Add the traceback for debugging
                        import traceback
                        tb = traceback.format_exc()
                        logger.error(tb)
                        execution_logs.append(f"TRACEBACK: {tb}")
                        
                        return False, execution_logs
                elif config.get('source') == 'api':
                    api_type = config.get('api_type')
                    if api_type == 'curl':
                        try:
                            # Execute the curl command
                            if 'curl_command' in config:
                                data = self._execute_curl_command(config['curl_command'], list_obj)
                            else:
                                logger.error(f"No curl command found in configuration for list {list_id}")
                                return
                        except Exception as e:
                            logger.error(f"Error in curl command execution: {str(e)}")
                            return
                    elif api_type == 'script':
                        try:
                            # Execute the Python script
                            script_content = None
                            
                            # Accept 'code' or 'script_content'
                            if 'code' in config:
                                script_content = config['code']
                            elif 'script_content' in config:
                                script_content = config['script_content']
                                
                            if script_content:
                                # Add comments to explain the use of proxy and SSL
                                proxy_info = """# Use of proxy and SSL:
# ========================
#
# IMPORTANT: The requests.get function has been modified to automatically use
# the proxy and SSL settings configured in the environment.
#
# You can therefore use requests.get normally without worrying about proxies:
# response = requests.get('https://api.example.com/data')
#
# You can also use the http_get function which is a shortcut:
# response = http_get('https://api.example.com/data', headers={'User-Agent': 'Mozilla/5.0'})
#
# The following variables are available if needed:
# - proxies: dictionary of configured proxies (http/https)
# - verify_ssl: boolean indicating if SSL verification is enabled
#
# Complete example:
#
# def main():
#     # Get data from an external API
#     response = requests.get('https://api.example.com/data')
#     data = response.json()
#     
#     # Process the data
#     results = []
#     for item in data['items']:
#         results.append({
#             'id': item['id'],
#             'name': item['name'],
#             'value': item['value']
#         })
#     
#     return results
"""
                                
                                # Add proxy information at the beginning of the script
                                enhanced_script = proxy_info + "\n\n" + script_content
                                
                                # Log the script execution with proxy
                                logger.info(f"Executing Python script for list {list_id} with proxy and SSL management")
                                
                                # The method now returns a tuple (data, logs)
                                data, script_logs = self._execute_python_script(enhanced_script)
                                
                                # Store the logs in the configuration to retrieve them later
                                list_obj._last_script_logs = script_logs
                                
                                if data is None:
                                    logger.error(f"Script execution returned no data for list {list_id}")
                                    return None, script_logs
                            else:
                                logger.error(f"No script content found in configuration for list {list_id}")
                                return None, ["ERROR: No script content found in the configuration"]
                        except Exception as e:
                            error_message = f"Error in script execution for list {list_id}: {str(e)}"
                            logger.error(error_message)
                            import traceback
                            tb = traceback.format_exc()
                            logger.error(tb)
                            return None, [error_message, f"TRACEBACK: {tb}"]
                    else:
                        logger.error(f"Unknown API type '{api_type}' for list {list_id}")
                        return
                
                # Check that the data has been retrieved correctly
                if data is None:
                    source_info = f"URL {config['url']}" if config.get('source') == 'url' else "curl command"
                    logger.error(f"No data retrieved from {source_info} for list {list_id}")
                    return
                
                logger.info(f"Data retrieved successfully for list {list_id} ({list_obj.name})")
                
                # Add debugging to see the retrieved data
                logger.info(f"Retrieved data: {str(data)[:500]}...") # Displays the first 500 characters
                logger.info(f"Number of entries: {len(data) if isinstance(data, list) else 'Not-a-list'}")
                
                # Normalize the data using the JSON configuration if available
                normalized_data = self._normalize_json_data(data, list_obj)
                
                # Handle pagination if enabled
                if (list_obj.json_config_status == 'configured' and 
                    list_obj.json_pagination_enabled and 
                    list_obj.json_next_page_path and 
                    config.get('source') == 'api' and 
                    config.get('api_type') == 'curl'):
                    
                    logger.info(f"Pagination enabled for list {list_id}")
                    page_count = 1
                    all_data = normalized_data
                    
                    # Get the next pages until the limit is reached
                    while page_count < list_obj.json_max_pages:
                        # Look for the next page URL in the data
                        next_page_url = None
                        next_page_data = data
                        
                        for key in list_obj.json_next_page_path.split('.'):
                            if not key:
                                continue
                            
                            if isinstance(next_page_data, dict) and key in next_page_data:
                                next_page_data = next_page_data[key]
                            else:
                                next_page_data = None
                                break
                        
                        next_page_url = next_page_data
                        
                        # If no next page URL, stop
                        if not next_page_url:
                            logger.info(f"No next page found after {page_count} pages")
                            break
                        
                        # Modify the curl command to use the next page URL
                        modified_curl = self._modify_curl_for_pagination(config['curl_command'], next_page_url)
                        if not modified_curl:
                            logger.error(f"Could not modify the curl command for pagination")
                            break
                        
                        # Execute the modified curl command
                        try:
                            page_data = self._execute_curl_command(modified_curl, list_obj)
                            if not page_data:
                                logger.error(f"No data retrieved for page {page_count + 1}")
                                break
                            
                            # Normalize the page data
                            page_normalized = self._normalize_json_data(page_data, list_obj)
                            
                            # Add the normalized data to the set of all data
                            all_data.extend(page_normalized)
                            
                            # Update the data for the next iteration
                            data = page_data
                            page_count += 1
                            
                            logger.info(f"Page {page_count} retrieved, {len(page_normalized)} entries added")
                        except Exception as e:
                            logger.error(f"Error getting page {page_count + 1}: {str(e)}")
                            break
                    
                    # Use the paginated data instead of the initial data
                    normalized_data = all_data
                    
                    # Apply the results limit to the set of paginated data
                    if list_obj.max_results > 0 and len(normalized_data) > list_obj.max_results:
                        logger.info(f"Results limit applied after pagination: {list_obj.max_results} out of {len(normalized_data)} available results")
                        normalized_data = normalized_data[:list_obj.max_results]
                    
                    logger.info(f"Pagination finished, {len(normalized_data)} entries in total")
                
                # Save the normalized data in the list
                success = ListService.update_list_data(list_id, normalized_data)
                
                if success:
                    logger.info(f"Data updated successfully for list {list_id} ({list_obj.name})")
                    execution_logs.append(f"INFO: Data updated successfully ({len(normalized_data)} entries)")
                    
                    # Update the last update date
                    list_obj.last_update = get_paris_now()
                    db.session.commit()
                    
                    # Check if public files are enabled and update the CSV and JSON files
                    try:
                        if list_obj.public_csv_enabled or list_obj.public_json_enabled:
                            logger.info(f"Updating public files for list {list_id}")
                            execution_logs.append("INFO: Updating public files")
                            
                            # Create the public files directory if it does not exist
                            public_files_dir = os.path.join(self.app.root_path, 'public_files')
                            os.makedirs(public_files_dir, exist_ok=True)
                            
                            # Get the list's data
                            data = list_obj.get_data()
                            
                            # Generate the CSV file if enabled
                            if list_obj.public_csv_enabled:
                                csv_path = os.path.join(public_files_dir, f'list_{list_id}.csv')
                                with open(csv_path, 'w', newline='', encoding='utf-8') as csv_file:
                                    import csv
                                    # Create the CSV writer
                                    writer = csv.writer(csv_file)
                                    
                                    # Write the header
                                    headers = [col.name for col in list_obj.columns]
                                    writer.writerow(headers)
                                    
                                    # Write the data
                                    for row in data:
                                        writer.writerow([row.get(header, '') for header in headers])
                                        
                                logger.info(f"Public CSV file updated for list {list_id}")
                                execution_logs.append("INFO: Public CSV file updated")
                            
                            # Generate the JSON file if enabled
                            if list_obj.public_json_enabled:
                                json_path = os.path.join(public_files_dir, f'list_{list_id}.json')
                                with open(json_path, 'w', encoding='utf-8') as json_file:
                                    # Filter the 'id' field from the data for JSON export
                                    filtered_data = []
                                    for row in data:
                                        filtered_row = {k: v for k, v in row.items() if k != 'id'}
                                        filtered_data.append(filtered_row)
                                    
                                    json.dump(filtered_data, json_file, ensure_ascii=False, indent=2)
                                    
                                logger.info(f"Public JSON file updated for list {list_id}")
                                execution_logs.append("INFO: Public JSON file updated")
                    except Exception as e:
                        logger.error(f"Error updating public files: {str(e)}")
                        execution_logs.append(f"WARNING: Error updating public files: {str(e)}")
                        # Do not block the data update if public file generation fails
                    
                    return True, execution_logs
                else:
                    logger.error(f"Error saving data for list {list_id}")
                    execution_logs.append("ERROR: Could not save data to the database")
                    return False, execution_logs
        except Exception as e:
            error_msg = f"Error updating list {list_id}: {str(e)}"
            logger.error(error_msg)
            execution_logs.append(f"ERROR: {error_msg}")
            
            import traceback
            tb = traceback.format_exc()
            logger.error(tb)
            execution_logs.append(f"TRACEBACK: {tb}")
            
            return False, execution_logs
    
    def schedule_list(self, list_obj):
        """Schedules a list's update"""
        if isinstance(list_obj, int):
            # If we received an ID instead of a list object
            with self.app.app_context():
                list_obj = List.query.get(list_obj)
                
        if list_obj and list_obj.is_active and list_obj.update_type == 'automatic':
            self._schedule_list(list_obj)
        else:
            if not list_obj:
                logger.error(f"List not found")
            elif not list_obj.is_active:
                logger.warning(f"List {list_obj.id} ({list_obj.name}) not active")
            elif list_obj.update_type != 'automatic':
                logger.warning(f"List {list_obj.id} ({list_obj.name}) not automatic (type: {list_obj.update_type})")
    
    def unschedule_list(self, list_id: int):
        """Unschedules a list"""
        job_id = f'list_{list_id}'
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Unscheduled list {list_id}")
    
    def shutdown(self):
        """Stops the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()