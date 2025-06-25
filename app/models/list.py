from database import db
import json
import ipaddress
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List as TypeList
import croniter
import requests
import logging
import pytz
import io
import csv
from flask import current_app

# The import of import_csv_data is moved into the _import_csv_data method to avoid a circular import

# Import timezone management functions
from utils.timezone_utils import get_paris_now, utc_to_paris, PARIS_TIMEZONE
from .list_components import ListColumn, ListData
from .data_importer import DataImporter

class List(db.Model):
    __tablename__ = 'lists'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=get_paris_now)
    updated_at = db.Column(db.DateTime, default=get_paris_now,
                           onupdate=get_paris_now)

    # Valid update types
    UPDATE_TYPES = ['manual', 'automatic']
    UPDATE_SOURCES = ['url', 'script', 'api', 'curl']
    SCRIPT_LANGUAGES = ['python', 'powershell']
    DATA_FORMATS = ['csv', 'json']

    # Configuration for JSON import
    JSON_CONFIG_STATUS = ['not_configured', 'configured', 'in_progress']

    update_type = db.Column(db.String(20), nullable=False)
    update_schedule = db.Column(db.String(100))
    _update_config = db.Column('update_config', db.Text)
    last_update = db.Column(db.DateTime)

    # Fields for JSON import configuration
    json_config_status = db.Column(db.String(20), default='not_configured')
    json_data_path = db.Column(db.String(255))
    json_pagination_enabled = db.Column(db.Boolean, default=False)
    json_next_page_path = db.Column(db.String(255))
    json_max_pages = db.Column(db.Integer, default=10)
    json_selected_columns = db.Column(db.Text)  # Stored in JSON format

    # Data source format (csv or json)
    data_source_format = db.Column(db.String(20), default='csv')

    # Limit for the number of imported results (0 = no limit)
    max_results = db.Column(db.Integer, default=100)

    # We no longer use a property for data_source_format, but the DB column directly
    # The following methods are utilities for synchronizing the configuration

    def update_data_format_from_config(self):
        """Updates the data format from the configuration"""
        config = self.update_config
        if config:
            # Check if the format is explicitly defined in the configuration
            if 'format' in config and config['format'] in self.DATA_FORMATS:
                self.data_source_format = config['format']
                return

            # Check if is_json is defined
            if 'is_json' in config:
                self.data_source_format = 'json' if config['is_json'] else 'csv'
                return

            # Check if csv_config is present
            if 'csv_config' in config:
                self.data_source_format = 'csv'
                return

    def update_config_from_data_format(self):
        """Updates the configuration from the data format"""
        if self.data_source_format and self.data_source_format in self.DATA_FORMATS:
            config = self.update_config
            config['format'] = self.data_source_format
            config['is_json'] = (self.data_source_format == 'json')
            self.update_config = config

    @property
    def update_config(self):
        """Getter for update_config that converts the JSON string to a dictionary"""
        if not self._update_config:
            return {}
        try:
            return json.loads(self._update_config)
        except (json.JSONDecodeError, TypeError):
            current_app.logger.error(f"Error decoding update_config: {self._update_config}")
            return {}

    @update_config.setter
    def update_config(self, value):
        """Setter for update_config that converts the dictionary to a JSON string"""
        if isinstance(value, dict):
            self._update_config = json.dumps(value)
        elif isinstance(value, str):
            # Check if the string is already valid JSON
            try:
                json.loads(value)
                self._update_config = value
            except json.JSONDecodeError:
                current_app.logger.error(f"Invalid value for update_config: {value}")
                self._update_config = '{}'
        else:
            current_app.logger.error(f"Invalid type for update_config: {type(value)}")
            self._update_config = '{}'

    is_active = db.Column(db.Boolean, default=True)
    is_published = db.Column(db.Boolean, default=False)

    filter_enabled = db.Column(db.Boolean, default=False)
    filter_rules = db.Column(db.Text)

    ip_restriction_enabled = db.Column(db.Boolean, default=False)
    allowed_ips = db.Column(db.Text)

    # Options for public files
    public_csv_enabled = db.Column(db.Boolean, default=False)
    public_json_enabled = db.Column(db.Boolean, default=False)
    public_access_token = db.Column(db.String(64), unique=True)
    # Option : inclure les entêtes dans l'export CSV public
    public_csv_include_headers = db.Column(db.Boolean, default=True)

    @property
    def formatted_allowed_ips(self):
        """Returns the allowed IP addresses in a user-friendly format for display in forms"""
        if not self.allowed_ips:
            return ''

        try:
            # Attempt to parse as JSON
            # import json # Already imported at the top
            ips_list = json.loads(self.allowed_ips)
            if isinstance(ips_list, list):
                # Join IP addresses with semicolons
                return '; '.join(ips_list)
            return self.allowed_ips
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, return as is
            return self.allowed_ips

    # Virtual properties for compatibility with existing code
    @property
    def data_source_url(self):
        """Returns the data source URL from the update_config dictionary"""
        if not self.update_config:
            return None
        return self.update_config.get('url')

    # The data_source_format property has been replaced by a DB column
    # This method is kept for backward compatibility
    def get_data_source_format_from_config(self):
        """Returns the data source format from the update_config dictionary"""
        if not self.update_config:
            return None
        if self.update_config.get('is_json'):
            return 'json'
        return self.update_config.get('format', None)

    @property
    def auto_create_columns(self):
        return getattr(self, '_auto_create_columns', True)  # Default value for compatibility

    @auto_create_columns.setter
    def auto_create_columns(self, value):
        self._auto_create_columns = value

    # Relationships
    columns = db.relationship('ListColumn', backref='list', lazy='joined',
                              cascade='all, delete-orphan',
                              order_by='ListColumn.position')
    data = db.relationship('ListData', backref='list', lazy=True,
                           cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        # Validate the update type
        if 'update_type' in kwargs and kwargs['update_type'] not in self.UPDATE_TYPES:
            raise ValueError(f"Invalid update type. Possible values: {', '.join(self.UPDATE_TYPES)}")

        # Validate the update configuration
        if 'update_config' in kwargs and kwargs['update_config'] is not None:
            try:
                config = json.loads(kwargs['update_config']) if isinstance(kwargs['update_config'], str) else kwargs['update_config']

                # Check if it's an automatic list
                is_automatic = kwargs.get('update_type') == 'automatic'

                # For automatic lists, check the source
                if is_automatic:
                    if 'source' not in config or config['source'] not in self.UPDATE_SOURCES:
                        raise ValueError(f"Invalid source. Possible values: {', '.join(self.UPDATE_SOURCES)}")

                    if config['source'] == 'script':
                        if 'language' not in config or config['language'] not in self.SCRIPT_LANGUAGES:
                            raise ValueError(f"Invalid script language. Possible values: {', '.join(self.SCRIPT_LANGUAGES)}")
                        if 'script' not in config:
                            raise ValueError("The script is required for the 'script' source")
                    elif config['source'] == 'url':
                        if 'url' not in config:
                            raise ValueError("The URL is required for the 'url' source")

                        # Detect and set the data format for URL sources
                        # First, check if the format is explicitly defined
                        if 'format' in config and config['format'] in self.DATA_FORMATS:
                            # Use the explicit format
                            data_format = config['format']
                        # Then, check if is_json is defined
                        elif 'is_json' in config:
                            # Infer the format from is_json
                            data_format = 'json' if config['is_json'] else 'csv'
                        # Finally, try to infer the format from the URL
                        elif 'url' in config:
                            url = config['url'].lower()
                            if url.endswith('.json'):
                                data_format = 'json'
                                # Update is_json for consistency
                                config['is_json'] = True
                            elif url.endswith('.csv'):
                                data_format = 'csv'
                                # Update is_json for consistency
                                config['is_json'] = False
                            else:
                                # Default to CSV
                                data_format = 'csv'
                                config['is_json'] = False
                        else:
                            # Default to CSV
                            data_format = 'csv'
                            config['is_json'] = False

                        # Update the configuration with the detected format
                        config['format'] = data_format

                        # Update the configuration
                        if isinstance(kwargs['update_config'], str):
                            kwargs['update_config'] = json.dumps(config)
                        else:
                            kwargs['update_config'] = config

                        # Set data_source_format in kwargs
                        kwargs['data_source_format'] = data_format
                    elif config['source'] == 'api':
                        if 'api_type' not in config:
                            raise ValueError("The API type (curl or script) is required for the 'api' source")

                        if config['api_type'] == 'curl' and 'curl_command' not in config:
                            raise ValueError("The curl command is required for the 'curl' API type")
                        elif config['api_type'] == 'script':
                            # Accept 'script_content' as an alternative to 'code'
                            if 'code' not in config and 'script_content' not in config:
                                raise ValueError("The code and language are required for the 'script' API type")
                            if 'language' not in config:
                                raise ValueError("The language is required for the 'script' API type")

                            # If script_content is used, copy it to code for compatibility
                            if 'script_content' in config and 'code' not in config:
                                config['code'] = config['script_content']

                        # For the 'api' source, the URL is not required
                    elif config['source'] == 'curl':
                        if 'curl_command' not in config:
                            raise ValueError("The curl command is required for the 'curl' source")
            except json.JSONDecodeError:
                raise ValueError("Invalid update configuration: Invalid JSON")

        # Validate and correct the update schedule
        if ('update_type' in kwargs and kwargs['update_type'] == 'automatic' and
                'update_schedule' in kwargs and kwargs['update_schedule']):
            # Try to correct the cron format if necessary
            schedule = kwargs['update_schedule']

            # Check if the format is compressed (without spaces)
            if '*' in schedule and ' ' not in schedule:
                # Try to correct the compressed format
                try:
                    # Insert spaces between components
                    parts = []
                    current_part = ""
                    for char in schedule:
                        if char in "*/,0123456789":
                            current_part += char
                        elif char == '*':
                            if current_part and current_part != "*":
                                parts.append(current_part)
                                current_part = "*"
                            else:
                                current_part += char
                    if current_part:
                        parts.append(current_part)

                    # Ensure there are 5 parts
                    while len(parts) < 5:
                        parts.append("*")

                    # Rebuild the cron format with spaces
                    schedule = " ".join(parts[:5])
                    kwargs['update_schedule'] = schedule
                    current_app.logger.info(f"Corrected cron format: {schedule}")
                except Exception as format_error:
                    current_app.logger.error(f"Could not correct cron format: {str(format_error)}")

            # Validate the cron format
            try:
                croniter.croniter(kwargs['update_schedule'])
            except ValueError as e:
                # If the format is still invalid, use a default format
                current_app.logger.warning(f"Invalid cron format '{kwargs['update_schedule']}', using default format '*/5 * * * *'")
                kwargs['update_schedule'] = "*/5 * * * *"
                try:
                    croniter.croniter(kwargs['update_schedule'])
                except ValueError as e2:
                    raise ValueError(f"Invalid update schedule even after correction: {str(e2)}")

        # Validate filter rules
        if 'filter_rules' in kwargs and kwargs['filter_rules']:
            try:
                if isinstance(kwargs['filter_rules'], str):
                    json.loads(kwargs['filter_rules'])
                else:
                    kwargs['filter_rules'] = json.dumps(kwargs['filter_rules'])
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON filter rules")

        # Validate allowed IPs
        if 'allowed_ips' in kwargs and kwargs['allowed_ips']:
            try:
                if isinstance(kwargs['allowed_ips'], str):
                    json.loads(kwargs['allowed_ips'])
                else:
                    kwargs['allowed_ips'] = json.dumps(kwargs['allowed_ips'])
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON IP list")

        super(List, self).__init__(**kwargs)

    @property
    def get_update_config(self) -> Optional[Dict[str, Any]]:
        """Retrieves the update configuration"""
        # Directly use the update_config property which already returns a dictionary
        return self.update_config if self.update_config else None

    def set_update_config(self, config: Dict[str, Any]) -> None:
        """Sets the update configuration"""
        # Directly use the update_config property which already handles conversion
        self.update_config = config

    def is_update_due(self) -> bool:
        """Checks if an update is due"""
        if not self.update_type == 'automatic' or not self.update_schedule:
            return False

        if not self.last_update:
            return True

        try:
            # Ensure dates are timezone-aware
            last_update = self.last_update
            if last_update.tzinfo is None:
                last_update = last_update.replace(tzinfo=timezone.utc)

            # For a 5-minute interval, check if 5 minutes have passed
            if '*/5' in self.update_schedule:
                delta = datetime.now(timezone.utc) - last_update
                return delta.total_seconds() >= 300  # 5 minutes = 300 seconds

            # For other cases, use croniter
            cron = croniter.croniter(self.update_schedule, last_update)
            next_update = cron.get_next(datetime)
            if next_update.tzinfo is None:
                next_update = next_update.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= next_update
        except (ValueError, TypeError):
            return False

    async def perform_update(self) -> Optional[TypeList[Dict[str, Any]]]:
        """Performs a list update"""
        if not self.update_config:
            return None

        config = self.get_update_config
        source = config.get('source')

        if source == 'url':
            url = config.get('url')
            if not url:
                return None

            try:
                # Get parameters from Flask configuration
                try:
                    # First, try via current_app.config
                    verify_ssl = current_app.config.get('VERIFY_SSL', 'false').lower() == 'true'
                    http_proxy = current_app.config.get('HTTP_PROXY', os.environ.get('HTTP_PROXY', ''))
                    https_proxy = current_app.config.get('HTTPS_PROXY', os.environ.get('HTTPS_PROXY', ''))
                    no_proxy = current_app.config.get('NO_PROXY', os.environ.get('NO_PROXY', ''))
                    
                    # Also check lowercase variables
                    if not http_proxy:
                        http_proxy = current_app.config.get('http_proxy', os.environ.get('http_proxy', ''))
                    if not https_proxy:
                        https_proxy = current_app.config.get('https_proxy', os.environ.get('https_proxy', ''))
                    if not no_proxy:
                        no_proxy = current_app.config.get('no_proxy', os.environ.get('no_proxy', ''))
                        
                    # Check for custom certificates
                    ca_bundle = os.environ.get('REQUESTS_CA_BUNDLE', '')
                    ssl_cert_file = os.environ.get('SSL_CERT_FILE', '')
                    
                    if ca_bundle:
                        current_app.logger.info(f"List {self.id}: Using custom CA certificate: {ca_bundle}")
                    if ssl_cert_file:
                        current_app.logger.info(f"List {self.id}: Using custom SSL certificate: {ssl_cert_file}")
                        
                except Exception as e:
                    # Fallback to default values in case of error
                    current_app.logger.warning(f"Error retrieving environment variables: {str(e)}")
                    verify_ssl = False
                    http_proxy = ''
                    https_proxy = ''
                    no_proxy = ''
                
                # Configure proxy only if variables are defined and not empty
                proxies = None
                if http_proxy or https_proxy:
                    proxies = {}
                    if http_proxy:
                        proxies['http'] = http_proxy
                    if https_proxy:
                        proxies['https'] = https_proxy
                    current_app.logger.info(f"List {self.id}: Using proxy: {proxies}")
                else:
                    current_app.logger.info(f"List {self.id}: No proxy used")
                
                # Disable SSL warnings if necessary
                if not verify_ssl:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    current_app.logger.info(f"List {self.id}: SSL verification disabled")
                
                # Build request parameters
                request_params = {
                    'verify': verify_ssl
                }
                
                # Add proxy only if defined
                if proxies:
                    request_params['proxies'] = proxies
                
                # Execute request with appropriate parameters
                current_app.logger.info(f"List {self.id}: HTTP request to {url} with proxy={proxies} and verify_ssl={verify_ssl}")
                response = requests.get(url, **request_params)
                response.raise_for_status()
                data = response.json()
                self.last_update = datetime.now(timezone.utc)
                db.session.commit()
                return data
            except requests.exceptions.SSLError as e:
                current_app.logger.error(f"SSL error during list update {self.id}: {str(e)}")
                return None
            except requests.exceptions.ProxyError as e:
                current_app.logger.error(f"Proxy error during list update {self.id}: {str(e)}")
                return None
            except requests.RequestException as e:
                current_app.logger.error(f"HTTP error during list update {self.id}: {str(e)}")
                return None
            except json.JSONDecodeError as e:
                current_app.logger.error(f"JSON decoding error during list update {self.id}: {str(e)}")
                return None
            except Exception as e:
                current_app.logger.error(f"Unexpected error during list update {self.id}: {str(e)}")
                return None

        return None

    def is_ip_allowed(self, client_ip):
        """
        Checks if an IP address is allowed to access this list.

        Args:
            client_ip (str): The client's IP address to check

        Returns:
            bool: True if the IP is allowed, False otherwise
        """
        current_app.logger.info(f"Checking IP {client_ip} for list {self.id}")
        current_app.logger.info(f"IP restriction enabled: {self.ip_restriction_enabled}")
        current_app.logger.info(f"Allowed IPs: {self.allowed_ips}")

        # If IP restrictions are not enabled or if no IPs are specified, allow access
        if not self.ip_restriction_enabled or not self.allowed_ips:
            current_app.logger.info("IP restrictions disabled or no allowed IPs specified, access granted")
            return True

        # Special handling for localhost/127.0.0.1 - always allow local access
        if client_ip == '127.0.0.1' or client_ip == 'localhost' or client_ip == '::1':
            current_app.logger.info(f"Local access detected ({client_ip}), access granted")
            return True

        # Clean up the client IP (remove spaces, etc.)
        if client_ip:
            client_ip = client_ip.strip()
        else:
            current_app.logger.error("Client IP is empty or null")
            return False

        # Convert the client IP to an ipaddress object for easier comparisons
        try:
            client_ip_obj = ipaddress.ip_address(client_ip)
            current_app.logger.info(f"Valid client IP: {client_ip_obj}")
        except ValueError:
            # If the client IP is not valid, deny access
            current_app.logger.error(f"Invalid client IP: {client_ip}")
            return False

        # Go through all allowed IP rules
        # Handle both cases where allowed_ips is a string and where it's JSON
        allowed_ip_rules = []

        if isinstance(self.allowed_ips, str):
            # Clean up the allowed IPs string
            cleaned_ips = self.allowed_ips.strip()

            if cleaned_ips.startswith('[') or cleaned_ips.startswith('{'):
                try:
                    # Attempt to parse as JSON
                    # import json # Already imported
                    allowed_ips_data = json.loads(cleaned_ips)
                    if isinstance(allowed_ips_data, list):
                        allowed_ip_rules = allowed_ips_data
                    else:
                        allowed_ip_rules = [cleaned_ips]
                except json.JSONDecodeError:
                    # If it's not valid JSON, treat as a string with separators
                    allowed_ip_rules = [rule.strip() for rule in cleaned_ips.split(';') if rule.strip()]
            else:
                # Treat as a list of IPs separated by semicolons
                allowed_ip_rules = [rule.strip() for rule in cleaned_ips.split(';') if rule.strip()]
        else:
            allowed_ip_rules = [str(self.allowed_ips)]

        current_app.logger.info(f"Parsed IP rules: {allowed_ip_rules}")

        # Check each IP rule
        for rule in allowed_ip_rules:
            rule = str(rule).strip()
            current_app.logger.info(f"Checking rule: {rule}")

            # Case 1: Individual IP (e.g., 10.0.0.1)
            if '/' not in rule and '-' not in rule:
                try:
                    rule_ip = ipaddress.ip_address(rule)
                    current_app.logger.info(f"IP comparison: {client_ip_obj} == {rule_ip}")
                    if client_ip_obj == rule_ip:
                        current_app.logger.info(f"IP {client_ip} allowed (exact match with {rule})")
                        return True
                except ValueError as e:
                    current_app.logger.error(f"Error converting IP {rule}: {str(e)}")
                    continue

            # Case 2: CIDR range (e.g., 10.0.0.0/24)
            elif '/' in rule:
                try:
                    network = ipaddress.ip_network(rule, strict=False)
                    current_app.logger.info(f"Checking if {client_ip_obj} is in network {network}")
                    if client_ip_obj in network:
                        current_app.logger.info(f"IP {client_ip} allowed (in network {rule})")
                        return True
                except ValueError as e:
                    current_app.logger.error(f"Error converting network {rule}: {str(e)}")
                    continue

            # Case 3: IP range (e.g., 10.0.0.1-10.0.0.3)
            elif '-' in rule:
                try:
                    start_ip, end_ip = rule.split('-')
                    start_ip = ipaddress.ip_address(start_ip.strip())
                    end_ip = ipaddress.ip_address(end_ip.strip())

                    current_app.logger.info(f"Checking if {client_ip_obj} is in range {start_ip}-{end_ip}")

                    # Check if the client IP is in the range
                    if start_ip <= client_ip_obj <= end_ip:
                        current_app.logger.info(f"IP {client_ip} allowed (in range {start_ip}-{end_ip})")
                        return True
                except ValueError as e:
                    current_app.logger.error(f"Error converting range {rule}: {str(e)}")
                    continue

        # If no rule matches, deny access
        current_app.logger.warning(f"IP {client_ip} not allowed (no matching rule)")
        return False

    def generate_public_json(self):
        """Generates the public JSON data for the list"""
        data = self.get_data()
        
        if not data:
            return []
            
        # Filter the 'id' field from the data for JSON export
        filtered_data = []
        for row in data:
            filtered_row = {k: v for k, v in row.items() if k != 'id'}
            filtered_data.append(filtered_row)
        
        return filtered_data

    def get_data(self) -> TypeList[Dict[str, Any]]:
        """Fetches the list's data"""
        # from flask import current_app # Already imported
        current_app.logger.info(f"Fetching data for list {self.id}")
        
        try:
            # Check if the list exists and has columns
            if not self.id:
                current_app.logger.error("Attempting to fetch data for a list without an ID")
                return []

            # Fetch columns in advance to avoid session issues
            columns = list(self.columns)
            current_app.logger.info(f"Fetched columns: {[c.name for c in columns]}")

            # Create a dictionary of columns by position for faster access
            columns_by_position = {c.position: c for c in columns}

            # Fetch the data
            data_items = db.session.query(ListData).filter(
                ListData.list_id == self.id
            ).order_by(
                ListData.row_id,
                ListData.column_position
            ).all()

            current_app.logger.info(f"Number of data items fetched: {len(data_items)}")

            # Organize data by row
            rows = {}
            for item in data_items:
                # Create the row if it doesn't exist
                if item.row_id not in rows:
                    rows[item.row_id] = {'id': item.row_id}  # Use row_id as identifier

                # Get the corresponding column
                column = columns_by_position.get(item.column_position)

                # Add the value if the column exists
                if column:
                    rows[item.row_id][column.name] = item.value
                else:
                    current_app.logger.warning(f"Column not found for position {item.column_position}")

            # Convert to a list
            data = list(rows.values())
            current_app.logger.info(f"Number of rows fetched: {len(data)}")

            # Apply filters if necessary
            if self.filter_enabled:
                try:
                    filtered_data = self.apply_filters(data)
                    current_app.logger.info(f"Filtered data: {len(filtered_data)} rows")
                    return filtered_data
                except Exception as e:
                    current_app.logger.error(f"Error applying filters: {str(e)}")
                    import traceback
                    current_app.logger.error(traceback.format_exc())
                    # In case of error in filters, return unfiltered data
                    return data
            else:
                return data

        except Exception as e:
            current_app.logger.error(f"Error fetching data: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            # In case of error, return an empty list
            return []

    def apply_filters(self, data: TypeList[Dict[str, Any]]) -> TypeList[Dict[str, Any]]:
        """Applies filters to the data"""
        # from flask import current_app # Already imported

        # If filtering is not enabled or if there are no filter rules, return the data as is
        if not self.filter_enabled or not self.filter_rules:
            current_app.logger.info(f"Filtering not enabled or no rules for list {self.id}")
            return data

        # If the data is empty, return an empty list
        if not data:
            current_app.logger.info(f"No data to filter for list {self.id}")
            return []

        try:
            # Try to parse the filter rules as JSON
            current_app.logger.info(f"Raw filter rules: {self.filter_rules}")

            # Handle different rule formats
            if isinstance(self.filter_rules, list):
                filters = self.filter_rules
            elif isinstance(self.filter_rules, str):
                # Clean up the JSON string
                clean_rules = self.filter_rules.strip()
                if not clean_rules:
                    return data

                # Parse JSON rules
                filters = json.loads(clean_rules)
            else:
                current_app.logger.warning(f"Unsupported filter rule format: {type(self.filter_rules)}")
                return data

            # Check if filters are valid
            if not filters or not isinstance(filters, list):
                current_app.logger.info(f"Invalid or empty filters: {filters}")
                return data

            current_app.logger.info(f"Parsed filters: {filters}")

            # Apply filters to the data
            filtered_data = []
            for row in data:
                # Check each value in the row
                for key, value in row.items():
                    # Ignore the ID
                    if key == 'id':
                        continue

                    # Convert the value to a string for comparison
                    str_value = str(value).lower() if value is not None else ""

                    # Check if the value matches one of the filters
                    if any(str(filter_value).lower() in str_value for filter_value in filters):
                        filtered_data.append(row)
                        break

            current_app.logger.info(f"Filtering result: {len(filtered_data)} rows out of {len(data)}")
            return filtered_data

        except json.JSONDecodeError as e:
            current_app.logger.error(f"JSON decoding error of filter rules: {str(e)}")
            return data
        except Exception as e:
            current_app.logger.error(f"Error applying filters: {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            return data

    def save(self):
        """Saves the changes"""
        db.session.add(self)
        db.session.commit()

    def _create_columns_from_json_direct(self, json_obj):
        """Directly creates columns from a JSON object using a new session.
        This method is specifically designed to be used during data import."""
        # from flask import current_app # Already imported

        # Check that the list ID is valid
        if not self.id:
            current_app.logger.error("Cannot create columns: the list does not have a valid ID")
            return False

        # Ensure the list is properly committed in the main session first
        try:
            # Force a commit of the main session to ensure the list is saved
            db.session.commit()
            current_app.logger.info(f"Main session committed before direct column creation for list {self.id}")
        except Exception as e:
            current_app.logger.error(f"Error during main session commit: {str(e)}")
            # Continue despite the error

        # Wait a bit to ensure the transaction is completed
        import time
        time.sleep(2)  # Increase the wait time to 2 seconds

        # Explicitly check if the list exists in the database
        list_exists = db.session.query(db.exists().where(List.id == self.id)).scalar()
        if not list_exists:
            current_app.logger.warning(f"List with ID {self.id} does not exist in the database after commit")
            # Try to force the creation of the list
            try:
                db.session.add(self)
                db.session.commit()
                current_app.logger.info(f"List {self.id} forced into the database")

                # Check again
                list_exists = db.session.query(db.exists().where(List.id == self.id)).scalar()
                if not list_exists:
                    raise ValueError(f"List with ID {self.id} still does not exist after commit")
            except Exception as e:
                current_app.logger.error(f"Error during forced list commit: {str(e)}")
                # Switch directly to the fallback method
                return self._create_columns_fallback(json_obj)

        # Create the columns directly in the main session
        try:
            # Determine the starting position
            max_position = db.session.query(db.func.max(ListColumn.position)).filter(
                ListColumn.list_id == self.id
            ).scalar() or 0

            # Get existing columns
            existing_columns = db.session.query(ListColumn).filter(ListColumn.list_id == self.id).all()
            existing_column_names = [col.name for col in existing_columns]

            # Prepare the columns to add
            columns_to_add = []

            # Load selected columns from the JSON configuration
            selected_columns_config = []
            if self.json_selected_columns:
                try:
                    # import json as json_module # Use top-level json
                    selected_columns_config = json.loads(self.json_selected_columns)
                    current_app.logger.info(f"Loaded selected JSON columns: {selected_columns_config}")
                except Exception as e:
                    current_app.logger.error(f"Error loading selected JSON columns: {str(e)}")
                    # In case of error, use all columns
                    selected_columns_config = []

            # Create a dictionary of selected columns for quick lookup
            selected_column_names = [col['name'] for col in selected_columns_config] if selected_columns_config else []

            # If no columns are selected, use all columns
            use_all_columns = not selected_columns_config

            current_app.logger.info(f"Selected columns for creation: {selected_column_names if selected_column_names else 'all'}")

            # Create the columns
            for i, (name, value) in enumerate(json_obj.items()):
                # Check if the column already exists and if it is selected
                if name not in existing_column_names and (use_all_columns or name in selected_column_names):
                    # Determine the column type based on the value
                    column_type = 'text'
                    if isinstance(value, (int, float)):
                        column_type = 'number'
                    elif isinstance(value, bool):
                        column_type = 'boolean'

                    # If the column is in the selected columns, use the specified type
                    if not use_all_columns:
                        for col_config in selected_columns_config:
                            if col_config['name'] == name:
                                column_type = col_config['type']
                                break

                    # Create the column
                    column = ListColumn(
                        list_id=self.id,
                        name=name,
                        position=max_position + i + 1, # This should be relative to existing max_position for new columns
                        column_type=column_type
                    )
                    columns_to_add.append(column)
                    max_position +=1 # Increment max_position for next new column to maintain order

            # Add all columns in a single transaction
            if columns_to_add:
                try:
                    for column in columns_to_add:
                        db.session.add(column)
                    db.session.commit()
                    current_app.logger.info(f"Successfully added {len(columns_to_add)} columns to list {self.id} via main session")
                    return True
                except Exception as e:
                    current_app.logger.error(f"Error adding columns via main session: {str(e)}")
                    db.session.rollback()
                    # Try an alternative approach with a new session
                    return self._create_columns_fallback(json_obj)
            else:
                current_app.logger.info(f"No new columns to add for list {self.id}")
                return True
        except Exception as e:
            current_app.logger.error(f"Error during direct column creation: {str(e)}")
            # Try an alternative approach with a new session
            return self._create_columns_fallback(json_obj)

    def _create_columns_fallback(self, json_obj):
        """Fallback method to create columns if the main method fails.
        Uses a different approach with direct SQL queries."""
        # from flask import current_app # Already imported
        current_app.logger.info(f"Attempting to create columns with the fallback method for list {self.id}")

        try:
            # Use a direct database connection
            import pymysql
            import time

            # Force a commit of the main session to ensure the list is saved
            db.session.commit()

            # Wait a bit to ensure the transaction is completed
            time.sleep(2)

            # Check directly in the database if the list exists
            list_exists = db.session.query(db.exists().where(List.id == self.id)).scalar()
            if not list_exists:
                current_app.logger.error(f"List with ID {self.id} does not exist in the database before direct connection")
                # Try to force the creation of the list
                try:
                    db.session.add(self)
                    db.session.commit()
                    current_app.logger.info(f"List {self.id} forced into the database")
                except Exception as e:
                    current_app.logger.error(f"Could not force list creation: {str(e)}")
                    return False

            # Extract connection information from the database URL
            db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
            # Typical format: mysql+pymysql://user:password@host:port/dbname
            db_parts = db_uri.replace('mysql+pymysql://', '').split('@')
            user_pass = db_parts[0].split(':')  # user:password
            host_db = db_parts[1].split('/')    # host:port/dbname

            user = user_pass[0]
            password = user_pass[1] if len(user_pass) > 1 else ''
            host_uri_part = host_db[0]
            host = host_uri_part.split(':')[0] if ':' in host_uri_part else host_uri_part
            port = int(host_uri_part.split(':')[1]) if ':' in host_uri_part else 3306
            db_name = host_db[1].split('?')[0]  # dbname without parameters

            # Establish a direct connection
            connection = pymysql.connect(
                host=host,
                user=user,
                password=password,
                database=db_name,
                port=port,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

            try:
                with connection.cursor() as cursor:
                    # Check that the list exists
                    cursor.execute("SELECT id FROM lists WHERE id = %s", (self.id,))
                    list_result = cursor.fetchone()

                    if not list_result:
                        current_app.logger.error(f"List with ID {self.id} does not exist in the database (direct check)")
                        # Try to insert the list directly
                        try:
                            # Ensure all required fields for `lists` table are provided or have defaults in DB
                            # Minimal example:
                            cursor.execute(
                                "INSERT INTO lists (id, name, description, created_at, updated_at, update_type) "
                                "VALUES (%s, %s, %s, NOW(), NOW(), %s)", # Added update_type
                                (self.id, self.name or f"List {self.id}", self.description or '', self.update_type or 'manual')
                            )
                            connection.commit()
                            current_app.logger.info(f"List {self.id} inserted directly into the database")
                        except Exception as insert_error:
                            current_app.logger.error(f"Error during direct list insertion: {str(insert_error)}")
                            connection.close()
                            return False

                    # Get the maximum position
                    cursor.execute("SELECT MAX(position) as max_pos FROM list_columns WHERE list_id = %s", (self.id,))
                    max_result = cursor.fetchone()
                    max_position = max_result['max_pos'] if max_result and max_result['max_pos'] is not None else 0

                    # Get existing columns
                    cursor.execute("SELECT name FROM list_columns WHERE list_id = %s", (self.id,))
                    existing_columns_fetch = cursor.fetchall()
                    existing_column_names = [col['name'] for col in existing_columns_fetch]

                    # Add columns one by one
                    columns_added = 0
                    current_col_pos = max_position
                    for i, (name, value) in enumerate(json_obj.items()):
                        if name not in existing_column_names:
                            current_col_pos += 1 # Increment position for new column
                            # Determine the column type
                            column_type = 'text'
                            if isinstance(value, (int, float)):
                                column_type = 'number'
                            elif isinstance(value, bool):
                                column_type = 'boolean'

                            # Insert the column
                            try:
                                cursor.execute(
                                    "INSERT INTO list_columns (list_id, name, position, column_type, created_at) "
                                    "VALUES (%s, %s, %s, %s, NOW())",
                                    (self.id, name, current_col_pos, column_type)
                                )
                                columns_added += 1
                            except Exception as col_error:
                                current_app.logger.error(f"Error adding column {name}: {str(col_error)}")
                                # If one column fails, maybe rollback or log and continue?
                                # For now, it continues, which might lead to inconsistent state if some columns are added and others fail.

                    # Commit the changes
                    connection.commit()
                    current_app.logger.info(f"Successfully added {columns_added} columns to list {self.id} via direct connection")
                    return True
            except Exception as cursor_error:
                current_app.logger.error(f"Error executing SQL queries: {str(cursor_error)}")
                if connection.open: # Check if connection is still open before rollback
                    connection.rollback()
                return False
            finally:
                if connection.open:
                    connection.close()
        except Exception as e:
            current_app.logger.error(f"Error creating columns via fallback method: {str(e)}")
            return False

    # NOTE: This is the first definition of this method name in the file.
    def _create_columns_from_json(self, json_obj):
        """Creates columns from a JSON object"""
        # Check that the list ID is valid
        if not self.id:
            # Ensure the list is saved in the database
            try:
                db.session.add(self)
                db.session.commit()
                current_app.logger.info(f"List saved with ID: {self.id}")
            except Exception as e:
                current_app.logger.error(f"Error saving the list: {str(e)}")
                db.session.rollback()
                raise ValueError("Could not save the list. Cannot create columns.")

            if not self.id: # Re-check after commit
                raise ValueError("List ID is not valid after commit. Cannot create columns.")

        # Ensure the list is saved in the database
        try:
            # Check if the list exists in the database
            list_exists = db.session.query(db.exists().where(List.id == self.id)).scalar()
            if not list_exists:
                current_app.logger.warning(f"List with ID {self.id} does not exist in the database after check")
                # Commit the list if it doesn't exist yet
                db.session.add(self) # Should already be added if id was generated, or persisted.
                db.session.commit()
                current_app.logger.info(f"List {self.id} committed successfully")

                # Check again
                list_exists = db.session.query(db.exists().where(List.id == self.id)).scalar()
                if not list_exists:
                    raise ValueError(f"List with ID {self.id} still does not exist after commit")
        except Exception as e:
            current_app.logger.error(f"Error checking list existence: {str(e)}")
            db.session.rollback()
            raise

        # Determine the starting position
        max_position = db.session.query(db.func.max(ListColumn.position)).filter(
            ListColumn.list_id == self.id
        ).scalar() or 0

        # Prepare columns to add
        columns_to_add = []
        current_col_pos = max_position

        # Create the columns
        for i, (name, value) in enumerate(json_obj.items()):
            # Check if the column already exists
            if not any(col.name == name for col in self.columns): # self.columns might be stale if session not refreshed
                current_col_pos += 1
                # Determine column type based on value
                column_type = 'text'
                if isinstance(value, (int, float)):
                    column_type = 'number'
                elif isinstance(value, bool):
                    column_type = 'boolean'

                # Create the column
                column = ListColumn(
                    list_id=self.id,
                    name=name,
                    position=current_col_pos,
                    column_type=column_type
                )
                columns_to_add.append(column)

        # Add and commit all columns in a single transaction
        if columns_to_add:
            try:
                for column in columns_to_add:
                    db.session.add(column)
                db.session.commit()
                current_app.logger.info(f"Successfully added {len(columns_to_add)} columns to list {self.id}")
            except Exception as e:
                current_app.logger.error(f"Error adding columns: {str(e)}")
                db.session.rollback()
                # Do not raise an exception, continue with the list without columns

        # Reload the columns
        db.session.refresh(self)

    def _clear_existing_data(self):
        """Deletes all existing data from the list"""
        # from flask import current_app # Already imported
        # ListData is already imported at the top or defined in this file.
        try:
            # Count rows before deletion
            count_before = db.session.query(ListData).filter(ListData.list_id == self.id).count()
            current_app.logger.info(f"Deleting existing data for list {self.id}: {count_before} rows found")

            # Delete the data
            db.session.query(ListData).filter(ListData.list_id == self.id).delete(synchronize_session=False) # Added synchronize_session
            db.session.commit()

            # Check that the data has been deleted
            count_after = db.session.query(ListData).filter(ListData.list_id == self.id).count()
            current_app.logger.info(f"After deletion: {count_after} rows remaining")
        except Exception as e:
            current_app.logger.error(f"Error deleting existing data: {str(e)}")
            db.session.rollback()

    def _debug_log(self, message):
        """Utility function to write debug logs to a file"""
        import os
        log_dir = "/app/logs" # Consider making this configurable
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"csv_import_debug_{self.id}.log") # Ensure self.id is not None
        try:
            with open(log_file, "a", encoding='utf-8') as f: # Added encoding
                f.write(f"{datetime.now(timezone.utc).isoformat()} - {message}\n") # Added timestamp
        except Exception as e:
            current_app.logger.error(f"Failed to write to debug log {log_file}: {e}")


    def _import_csv_data(self, stream, config):
        """Imports CSV data into the list using the CSV import helper module

        Args:
            stream: The CSV data stream
            config: The import configuration

        Returns:
            The number of imported rows
        """
        # from flask import current_app # Already imported
        # Import here to avoid circular import
        from models.csv_import_helper import import_csv_data

        try:
            # Use the CSV import helper module
            current_app.logger.info(f"Starting CSV import for list {self.id}")
            self._debug_log(f"Starting CSV import for list {self.id}")

            # Call the CSV import function from the helper module
            rows_imported = import_csv_data(self, stream, config)

            current_app.logger.info(f"CSV import finished for list {self.id}: {rows_imported} rows imported")
            self._debug_log(f"CSV import finished for list {self.id}: {rows_imported} rows imported")

            return rows_imported
        except Exception as e:
            current_app.logger.error(f"Error during CSV import for list {self.id}: {str(e)}")
            self._debug_log(f"Error during CSV import for list {self.id}: {str(e)}")
            import traceback
            error_trace = traceback.format_exc()
            current_app.logger.error(error_trace)
            self._debug_log(error_trace)
            raise

    def import_data_from_url_fixed(self, force_update=False):
        """Corrected version of the method to import data from a URL

        This method replaces the import_data_from_url method which contains syntax errors.
        It uses the CSV import helper module to import CSV data.

        Args:
            force_update: If True, forces the update even if the last update is recent

        Returns:
            The number of imported rows or None in case of error
        """
        # from flask import current_app # Already imported
        # import io # Already imported
        # import csv # Already imported
        # import requests # Already imported
        # import json # Already imported

        # Check if the URL is defined
        if not self.data_source_url:
            current_app.logger.error(f"No data source URL defined for list {self.id}")
            return None

        # Check if an update is necessary
        last_update_attr = getattr(self, 'last_update_at', self.last_update)
        if not force_update and last_update_attr:
            now = get_paris_now()
            if isinstance(last_update_attr, datetime):
                if last_update_attr.tzinfo is None or last_update_attr.tzinfo.utcoffset(last_update_attr) is None:
                    last_update_dt = pytz.utc.localize(last_update_attr) if last_update_attr.tzinfo is None else last_update_attr
                else:
                    last_update_dt = last_update_attr
                last_update_paris = utc_to_paris(last_update_dt)
                delta = now - last_update_paris
                delta_seconds = delta.total_seconds()
                # Check for negative delta (timezone or clock issue)
                if delta_seconds < 0:
                    current_app.logger.warning(f"Negative delta detected for list {self.id} ({delta_seconds} seconds). Forcing update.")
                    # Force update despite negative delta
                elif delta_seconds < 300 and 'force_update' not in config:
                    current_app.logger.info(f"Last update too recent for list {self.id} ({delta_seconds} seconds)")
                    return None
            else:
                current_app.logger.warning(f"Invalid last update attribute for list {self.id} in import_data_from_url_fixed: {last_update_attr}")


        # Get the update configuration
        config = self.get_update_config
        if isinstance(config, str): # Ensure config is dict
            try:
                config = json.loads(config)
            except: config = {}


        # Determine the data format
        is_json = False
        if 'csv_config' in config:
            is_json = False
        elif config.get('is_json') is False:
            is_json = False
        elif config.get('format') == 'csv' and self.data_source_format != 'json':
            is_json = False
        elif config.get('is_json') is True:
            is_json = True
        elif self.data_source_format == 'json':
            is_json = True
        elif self.data_source_url and self.data_source_url.lower().endswith('.json'): # Check data_source_url not None
            is_json = True

        # Log the detected format
        current_app.logger.info(f"Detected format for list {self.id} (fixed method): {'JSON' if is_json else 'CSV'}")

        
        # Add detailed logs for debugging
        current_app.logger.info(f"Starting import from URL for list {self.id}")
        current_app.logger.info(f"Data source URL: {self.data_source_url}")
        current_app.logger.info(f"Data source format: {self.data_source_format}")
        
        # Download URL content
        try:
            # Get parameters from Flask configuration
            try:
                # First try via current_app.config
                verify_ssl = current_app.config.get('VERIFY_SSL', 'false').lower() == 'true'
                http_proxy = current_app.config.get('HTTP_PROXY', '')
                https_proxy = current_app.config.get('HTTPS_PROXY', '')
            except Exception as e:
                # Fallback to default values in case of error
                current_app.logger.warning(f"Error retrieving environment variables: {str(e)}")
                verify_ssl = config.get('verify_ssl', False)
                http_proxy = ''
                https_proxy = ''
            
            # Configure proxy only if variables are defined and not empty
            proxies = None
            if http_proxy or https_proxy:
                proxies = {}
                if http_proxy:
                    proxies['http'] = http_proxy
                if https_proxy:
                    proxies['https'] = https_proxy
                current_app.logger.info(f"List {self.id}: Using proxy: {proxies}")
            else:
                current_app.logger.info(f"List {self.id}: No proxy used")
            
            # Disable SSL warnings if necessary
            if not verify_ssl:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Download content with proxy (if defined) and SSL parameters
            current_app.logger.info(f"List {self.id}: HTTP request with proxy={proxies} and verify_ssl={verify_ssl}")
            
            # Build request parameters
            request_params = {
                'verify': verify_ssl
            }
            
            # Add proxy only if defined
            if proxies:
                request_params['proxies'] = proxies
                
            # Execute request with appropriate parameters
            response = requests.get(self.data_source_url, **request_params)

            # Check status code
            if response.status_code != 200:
                current_app.logger.error(f"Error downloading URL for list {self.id}: {response.status_code}")
                return None

            # Get content
            content = response.text

            # Process data based on format
            if is_json:
                # Import JSON data
                try:
                    # Convert content to JSON object
                    json_data = json.loads(content)

                    # Clear existing data
                    self._clear_existing_data()

                    # Import JSON data
                    rows_imported = self._import_json_data(json_data)
                    current_app.logger.info(f"JSON import (fixed method) for list {self.id}: {rows_imported} rows.")
                    
                    setattr(self, 'last_update_at', datetime.now(timezone.utc))
                    db.session.commit()

                    if hasattr(self, 'public_csv_enabled') and hasattr(self, 'public_json_enabled'):
                        if self.public_csv_enabled or self.public_json_enabled:
                            if hasattr(self, 'generate_public_files'):
                                self.generate_public_files()
                    return rows_imported
                except json.JSONDecodeError as e:
                    current_app.logger.error(f"Error decoding JSON for list {self.id} (fixed method): {str(e)}")
                    return None
            else: # CSV
                # Import CSV data
                try:
                    # Create a stream from the content
                    stream = io.StringIO(content)

                    # Import CSV data using our helper module
                    rows_imported = self._import_csv_data(stream, config)

                    # Update the last update date
                    setattr(self, 'last_update_at', datetime.now(timezone.utc))
                    db.session.commit()

                    # Generate public files if necessary
                    if hasattr(self, 'public_csv_enabled') and hasattr(self, 'public_json_enabled'):
                        if self.public_csv_enabled or self.public_json_enabled:
                            if hasattr(self, 'generate_public_files'):
                                self.generate_public_files()

                    return rows_imported
                except Exception as e:
                    current_app.logger.error(f"Error during CSV import for list {self.id} (fixed method): {str(e)}")
                    import traceback
                    current_app.logger.error(traceback.format_exc())
                    return None
        except Exception as e:
            current_app.logger.error(f"Error during data import for list {self.id} (fixed method): {str(e)}")
            import traceback
            current_app.logger.error(traceback.format_exc())
            return None

    # _debug_log is already defined earlier. Duplicated definition removed.

    def _import_rows_from_csv_alternative(self, csv_reader, columns_map): # Renamed 'columns' to 'columns_map' to avoid conflict
        """Alternative CSV import method using direct SQL insertions"""
        # from flask import current_app # Already imported
        import sqlalchemy # For text
        from sqlalchemy import text # Specifically for text

        self._debug_log(f"=== Starting alternative CSV import for list {self.id} ===")
        current_app.logger.info(f"Using alternative CSV import method for list {self.id}")

        # Count imported rows
        row_count = 0

        # Check if the CSV reader has fields
        if not hasattr(csv_reader, 'fieldnames') or not csv_reader.fieldnames:
            error_msg = f"CSV reader has no defined fields for list {self.id}"
            current_app.logger.error(error_msg)
            self._debug_log(error_msg)
            return 0

        # Check if columns are available for import
        if not columns_map:
            error_msg = f"No columns available for import for list {self.id}"
            current_app.logger.error(error_msg)
            self._debug_log(error_msg)
            return 0

        self._debug_log(f"Alternative method - Available columns: {list(columns_map.keys())}")
        
        connection = None # Initialize connection to None
        try:
            # Use a direct database connection for bulk insertions
            connection = db.engine.connect()

            # Create a transaction
            transaction = connection.begin()

            # Add data row by row
            for row_idx, row_data_dict in enumerate(csv_reader): # Use enumerate for row_id
                try:
                    self._debug_log(f"Processing row: {row_data_dict}")
                    current_row_id = row_idx + 1  # Unique row ID (1-based)

                    # Insert each cell individually
                    for col_name, column_obj in columns_map.items():
                        value = row_data_dict.get(col_name, '') # Get value from CSV row
                        if value is None:
                            value = ''

                        # Convert values according to column type
                        if column_obj.column_type == 'number':
                            try:
                                value = float(value) if value else None
                            except (ValueError, TypeError):
                                value = None # Or some other default for numbers

                        # Insert directly into the database
                        sql = text("""
                        INSERT INTO list_data (list_id, row_id, column_position, value, created_at, updated_at)
                        VALUES (:list_id, :row_id, :column_position, :value, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = NOW()
                        """) # Used VALUES(value) for ON DUPLICATE KEY UPDATE

                        connection.execute(sql, {
                            'list_id': self.id,
                            'row_id': current_row_id,
                            'column_position': column_obj.position,
                            'value': str(value) if value is not None else ''
                        })

                    row_count += 1

                    # Progress log
                    if row_count % 10 == 0: # Changed from 100 to 10 for more frequent logging if desired
                        self._debug_log(f"Alternative method - {row_count} rows processed")
                        current_app.logger.info(f"Alternative method - {row_count} rows processed")

                except Exception as e:
                    self._debug_log(f"Error processing row {row_count + 1}: {str(e)}")
                    current_app.logger.error(f"Error processing row {row_count + 1}: {str(e)}")
                    # Continue with the next row
            
            # Commit the transaction
            transaction.commit()

            self._debug_log(f"Alternative method - Import finished, {row_count} rows imported")
            current_app.logger.info(f"Alternative method - Import finished, {row_count} rows imported")
            return row_count

        except Exception as e:
            self._debug_log(f"Error during alternative import: {str(e)}")
            current_app.logger.error(f"Error during alternative import: {str(e)}")
            import traceback
            tb = traceback.format_exc()
            self._debug_log(f"Traceback: {tb}")
            current_app.logger.error(tb)
            if connection and 'transaction' in locals() and transaction.is_active: # Check connection and transaction
                transaction.rollback()
            return 0 # Return 0 on error
        finally:
            # Close the connection
            if connection: # Check if connection was established
                connection.close()

    def _import_rows_from_csv(self, csv_reader, columns_map): # Renamed 'columns' to 'columns_map'
        """Imports rows from a CSV reader"""
        # from flask import current_app # Already imported
        # import sqlalchemy # For text
        from sqlalchemy import text # Specifically for text

        # Initialize the log file
        self._debug_log(f"=== Starting CSV import for list {self.id} ===")

        # Count imported rows
        row_count = 0

        # Check if the CSV reader has fields
        if not hasattr(csv_reader, 'fieldnames') or not csv_reader.fieldnames:
            error_msg = f"CSV reader has no defined fields for list {self.id}"
            current_app.logger.error(error_msg)
            self._debug_log(error_msg)
            return 0

        # Check if columns are available for import
        if not columns_map:
            error_msg = f"No columns available for import for list {self.id}"
            current_app.logger.error(error_msg)
            self._debug_log(error_msg)
            return 0

        self._debug_log(f"Starting CSV import for list {self.id} with {len(columns_map)} columns")
        self._debug_log(f"CSV fields: {csv_reader.fieldnames}")
        self._debug_log(f"Available columns: {list(columns_map.keys())}")
        current_app.logger.info(f"Starting CSV import for list {self.id} with {len(columns_map)} columns")
        current_app.logger.info(f"CSV fields: {csv_reader.fieldnames}")
        current_app.logger.info(f"Available columns: {list(columns_map.keys())}")

        # Use a direct database connection for bulk insertions
        connection = None # Initialize connection to None
        transaction = None # Initialize transaction
        try:
            connection = db.engine.connect()
            transaction = connection.begin()

            # Add data row by row
            for row_idx, row_data_dict in enumerate(csv_reader): # Use enumerate for row_id
                try:
                    self._debug_log(f"Processing row: {row_data_dict}")
                    current_app.logger.info(f"Processing row: {row_data_dict}")

                    current_row_id = row_idx + 1  # Unique row ID (1-based)

                    # Insert each cell individually
                    for col_name, column_obj in columns_map.items():
                        # Get the column value from the CSV row
                        value = row_data_dict.get(col_name, '')
                        self._debug_log(f"Column {col_name}: value={value}, type={column_obj.column_type}, position={column_obj.position}")
                        current_app.logger.info(f"Column {col_name}: value={value}, type={column_obj.column_type}")

                        # Set the value based on column type
                        if column_obj.column_type == 'number':
                            try:
                                # Try to convert to number
                                value = float(value) if value else None
                            except (ValueError, TypeError):
                                # If conversion fails, use None
                                value = None

                        # Insert directly into the database with duplicate handling
                        sql = text("""
                        INSERT INTO list_data (list_id, row_id, column_position, value, created_at, updated_at)
                        VALUES (:list_id, :row_id, :column_position, :value, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = NOW()
                        """) # Used VALUES(value)

                        connection.execute(sql, {
                            'list_id': self.id,
                            'row_id': current_row_id,
                            'column_position': column_obj.position,
                            'value': str(value) if value is not None else ''
                        })

                    row_count += 1

                    # Progress log
                    if row_count % 10 == 0: # Changed from 100 to 10 for more frequent logging
                        self._debug_log(f"{row_count} rows processed")
                        current_app.logger.info(f"{row_count} rows processed")

                except Exception as e:
                    error_msg = f"Error processing row {row_count + 1}: {str(e)}"
                    self._debug_log(error_msg)
                    current_app.logger.error(error_msg)

                    # Add the full error traceback
                    import traceback
                    tb = traceback.format_exc()
                    self._debug_log(f"Traceback: {tb}")
                    current_app.logger.error(tb)
                    # Continue with the next row

            # Commit the transaction
            transaction.commit()

            # Check the total number of entries after import
            count_sql = text("SELECT COUNT(*) FROM list_data WHERE list_id = :list_id")
            count_result = connection.execute(count_sql, {'list_id': self.id}).scalar()

            self._debug_log(f"Import finished. Total entries in database: {count_result}")
            current_app.logger.info(f"Import finished. Total entries in database: {count_result}")

            return row_count

        except Exception as e:
            error_msg = f"Error during CSV import: {str(e)}"
            self._debug_log(error_msg)
            current_app.logger.error(error_msg)

            # Add the full error traceback
            import traceback
            tb = traceback.format_exc()
            self._debug_log(f"Traceback: {tb}")
            current_app.logger.error(tb)

            # Rollback the transaction in case of error
            if transaction and transaction.is_active: # Check if transaction was started and is active
                transaction.rollback()
            raise # Re-raise the exception
        finally:
            # Close the connection
            if connection is not None:
                connection.close()

    def _import_json_data(self, json_data_input): # Renamed json_data to json_data_input
        """Imports data from JSON content"""
        # from flask import current_app # Already imported
        from utils.timezone_utils import get_paris_now # Already imported

        # Make a mutable copy if json_data_input is a list, or extract data if it's a dict
        processed_json_data = []

        # Check that the data is valid
        if not json_data_input:
            current_app.logger.error(f"No JSON data to import for list {self.id}")
            raise ValueError("No JSON data to import")

        # Check that the data is a list or a dictionary with a data path
        if isinstance(json_data_input, list):
            processed_json_data = list(json_data_input) # Make a copy
        elif isinstance(json_data_input, dict) and self.json_data_path:
            try:
                # Navigate through the data according to the configured path
                data_ptr = json_data_input
                for key in self.json_data_path.split('.'):
                    if not key: continue # Skip empty parts if path is like "a..b"
                    if key.isdigit() and isinstance(data_ptr, list) and int(key) < len(data_ptr):
                        data_ptr = data_ptr[int(key)]
                    elif isinstance(data_ptr, dict) and key in data_ptr:
                        data_ptr = data_ptr[key]
                    # Added robust path navigation attempt for lists when key is not an index
                    elif isinstance(data_ptr, list) and len(data_ptr) > 0 and isinstance(data_ptr[0], dict) and key in data_ptr[0]:
                        # This is ambiguous. If data_ptr is a list, and key is not digit, what to do?
                        # Original logic implies trying the first element if it's a dict and contains the key.
                        # This part is complex. Let's simplify or stick to strict path.
                        # For now, assuming key must be in dict or be an index for list.
                        # A more robust JSONPath library might be better here.
                        current_app.logger.warning(f"JSON path '{self.json_data_path}' encountered a list with a non-numeric key '{key}'. Non-standard behavior.")
                        data_ptr = None # Path broken
                        break
                    else:
                        current_app.logger.warning(f"Invalid JSON path: {self.json_data_path} at key '{key}'")
                        data_ptr = None
                        break

                # Check that the extracted data is a list
                if isinstance(data_ptr, list):
                    processed_json_data = data_ptr
                else:
                    current_app.logger.error(f"Data extracted via json_data_path is not a list: {type(data_ptr).__name__}")
                    raise ValueError(f"Data extracted via json_data_path is not a list: {type(data_ptr).__name__}")
            except Exception as e:
                current_app.logger.error(f"Error navigating JSON data with json_data_path: {str(e)}")
                raise ValueError(f"Error navigating JSON data: {str(e)}")
        else:
            current_app.logger.error(f"JSON data is not a list and json_data_path is not configured or applicable: {type(json_data_input).__name__}")
            raise ValueError(f"JSON data is not a list and json_data_path is not configured or applicable.")

        # Check that the list is not empty
        if len(processed_json_data) == 0:
            current_app.logger.warning(f"Empty JSON list for list {self.id} after initial processing")
            return 0

        # Check that all list items are dictionaries
        if not all(isinstance(item, dict) for item in processed_json_data): # Check all items
            first_non_dict_type = next((type(item).__name__ for item in processed_json_data if not isinstance(item, dict)), "unknown")
            current_app.logger.error(f"Not all JSON items are dictionaries. First non-dict type: {first_non_dict_type}")
            raise ValueError(f"Not all JSON items are dictionaries. First non-dict type: {first_non_dict_type}")

        # Check that the list exists in the database
        try:
            from sqlalchemy.orm import Session as SQLASession # Alias to avoid conflict if Session is used elsewhere
            from sqlalchemy import create_engine

            engine = create_engine(current_app.config['SQLALCHEMY_DATABASE_URI'])
            # Using 'with' ensures the session is closed.
            with SQLASession(engine) as session: # Use aliased Session
                list_exists = session.query(db.exists().where(List.id == self.id)).scalar()
            # Session is automatically closed here
            
            if not list_exists:
                current_app.logger.error(f"List with ID {self.id} does not exist in the database")
                # Attempt to save the current list instance if it's the one we're working with
                if self.id is not None : # Check if current instance has an ID
                    try:
                        db.session.add(self) # Add current instance to session
                        db.session.commit() # Commit it
                        current_app.logger.info(f"List {self.id} auto-saved because it was not found.")
                        list_exists = True # Assume it exists now
                    except Exception as save_err:
                        current_app.logger.error(f"Failed to auto-save list {self.id}: {save_err}")
                        db.session.rollback()
                        # Fall through to raise error if still not exists
                if not list_exists : # Re-check or if self.id was None
                    raise ValueError(f"List with ID {self.id} does not exist in the database and could not be auto-saved.")


            current_app.logger.info(f"List {self.id} successfully verified before JSON import")
        except Exception as e:
            current_app.logger.error(f"Error checking list existence: {str(e)}")
            raise ValueError(f"Error checking list existence: {str(e)}")

        # If auto_create_columns is enabled, create necessary columns
        if self.auto_create_columns:
            # Use the first object to determine columns
            try:
                # First try with the direct method
                # Ensure processed_json_data[0] is not empty if it's a dict
                if processed_json_data and isinstance(processed_json_data[0], dict) and processed_json_data[0]:
                    success = self._create_columns_from_json_direct(processed_json_data[0])
                    if not success:
                        current_app.logger.warning(f"Direct column creation failed, trying standard method")
                        self._create_columns_from_json(processed_json_data[0]) # This is the first definition one
                elif processed_json_data and isinstance(processed_json_data[0], dict) and not processed_json_data[0]:
                     current_app.logger.warning(f"First JSON object is an empty dictionary, cannot determine columns automatically.")
                else: # Should not happen if checks above passed.
                     current_app.logger.warning(f"First JSON object is not a dictionary or the list is empty, cannot determine columns automatically.")


                # Refresh the list object to ensure columns are loaded
                db.session.refresh(self)
            except Exception as e:
                current_app.logger.error(f"Error creating columns: {str(e)}")
                # Continue without columns, do not block the import

        # Get existing columns (potentially refreshed)
        current_list_columns = {col.name: col for col in self.columns}

        # Filter columns according to JSON configuration if it exists
        json_selected_columns_config = None
        if self.json_selected_columns:
            try:
                # import json # Already imported
                json_selected_columns_config = json.loads(self.json_selected_columns)
                current_app.logger.info(f"Loaded selected JSON columns: {json_selected_columns_config}")
            except Exception as e:
                current_app.logger.error(f"Error loading selected JSON columns: {str(e)}")

        columns_for_import = current_list_columns # Default to all current columns
        if json_selected_columns_config and isinstance(json_selected_columns_config, list): # Ensure it's a list of dicts
            # Create a dictionary of selected columns with their type
            selected_columns_map = {col_conf.get('name'): col_conf.get('type') for col_conf in json_selected_columns_config if isinstance(col_conf, dict) and col_conf.get('name')}
            
            current_app.logger.info(f"Selected columns for import: {list(selected_columns_map.keys())}")

            # Filter columns to use - ONLY the selected ones
            filtered_columns_temp = {}
            for col_name, col_obj in current_list_columns.items():
                if col_name in selected_columns_map:
                    # Update column type if necessary
                    new_type = selected_columns_map[col_name]
                    if new_type and col_obj.column_type != new_type:
                        col_obj.column_type = new_type
                        db.session.add(col_obj) # Stage for commit
                    filtered_columns_temp[col_name] = col_obj
                    current_app.logger.info(f"Column '{col_name}' selected for import")
                else:
                    current_app.logger.info(f"Column '{col_name}' ignored (not selected)")
            
            # Use ONLY the filtered columns
            columns_for_import = filtered_columns_temp
            if db.session.dirty: # If any column types were changed
                db.session.commit()
        
        # Check that all columns from the JSON (first object) match the columns to import
        if processed_json_data and isinstance(processed_json_data[0], dict):
            json_keys_from_first_obj = set(processed_json_data[0].keys())
            import_column_names = set(columns_for_import.keys())

            if not json_keys_from_first_obj.issubset(import_column_names): # Check if all keys in JSON are columns we plan to import
                # This check might be too strict. We might only want to import available columns.
                # The concern is if `auto_create_columns` is off and JSON has keys not in `columns_for_import`.
                missing_from_import_schema = json_keys_from_first_obj - import_column_names
                current_app.logger.warning(f"JSON keys {missing_from_import_schema} not present in selected/existing columns. This data will not be imported.")

                if self.auto_create_columns: # If auto_create is on, these missing columns should be created.
                    try:
                        # If columns are selected, only create missing columns that are also selected
                        if json_selected_columns_config:
                            # Filter missing columns to keep only the selected ones
                            missing_selected = {key for key in missing_from_import_schema if key in selected_columns_map}
                            if missing_selected:
                                missing_data_schema = {key: processed_json_data[0].get(key, '') for key in missing_selected}
                                current_app.logger.info(f"Creating selected missing columns: {missing_selected}")
                            else:
                                missing_data_schema = {}
                                current_app.logger.info(f"No missing columns are selected. No columns will be created.")
                        else:
                            # If no columns are selected, create all missing columns
                            missing_data_schema = {key: processed_json_data[0].get(key, '') for key in missing_from_import_schema}
                            
                        if missing_data_schema: # Only create if there's something to create
                            success = self._create_columns_from_json_direct(missing_data_schema)
                            if not success:
                                current_app.logger.warning(f"Direct creation of missing columns failed, trying standard method.")
                                self._create_columns_from_json(missing_data_schema) # First definition
                            
                            db.session.refresh(self) # Refresh self to get new columns
                            current_list_columns = {col.name: col for col in self.columns} # Update current_list_columns
                            
                            # Re-filter columns according to selection
                            if json_selected_columns_config: # If columns are selected
                                temp_re_filtered = {}
                                for col_name, col_obj in current_list_columns.items():
                                    if col_name in selected_columns_map: # selected_columns_map from earlier
                                        temp_re_filtered[col_name] = col_obj
                                        current_app.logger.info(f"Column '{col_name}' added to import columns after creation")
                                columns_for_import = temp_re_filtered
                            else: # If no columns are selected, use all columns
                                columns_for_import = current_list_columns


                            import_column_names = set(columns_for_import.keys()) # Update for re-check
                            if not json_keys_from_first_obj.issubset(import_column_names):
                                still_missing = json_keys_from_first_obj - import_column_names
                                current_app.logger.warning(f"Columns still missing after creation attempt: {', '.join(still_missing)}. This data will be ignored.")
                    except Exception as e:
                        current_app.logger.error(f"Error creating missing columns: {str(e)}")
                elif not self.auto_create_columns and missing_from_import_schema:
                    # If auto_create_columns is off, and JSON has columns not in the (selected) schema, this is an issue.
                    # Original code raised ValueError. This might be too strict if we just want to import what matches.
                    # For now, log warning as above, data for these columns will be skipped by _import_rows_from_json.
                    # raise ValueError(f"Invalid columns in JSON (auto_create_columns=off): {', '.join(missing_from_import_schema)}")
                    pass


        # Delete existing data and unselected columns if necessary
        try:
            # If columns were selected via JSON configuration
            if json_selected_columns_config and isinstance(json_selected_columns_config, list):
                selected_column_names = [col_conf.get('name') for col_conf in json_selected_columns_config if isinstance(col_conf, dict) and col_conf.get('name')]
                current_app.logger.info(f"Selected columns in JSON configuration: {selected_column_names}")
                
                # Identify columns to delete (those that are not selected)
                columns_to_delete = []
                for col_name, col_obj in current_list_columns.items():
                    if col_name not in selected_column_names:
                        columns_to_delete.append(col_obj)
                
                # Delete data from unselected columns
                if columns_to_delete:
                    column_positions_to_delete = [col.position for col in columns_to_delete]
                    column_names_to_delete = [col.name for col in columns_to_delete]
                    
                    current_app.logger.info(f"Deleting data for unselected columns: {column_names_to_delete}")
                    db.session.query(ListData).filter(
                        ListData.list_id == self.id,
                        ListData.column_position.in_(column_positions_to_delete)
                    ).delete(synchronize_session=False)
                    
                    # Delete unselected columns
                    current_app.logger.info(f"Deleting unselected columns: {column_names_to_delete}")
                    for col in columns_to_delete:
                        db.session.delete(col)
                    
                    db.session.commit()
                    current_app.logger.info(f"Unselected columns deleted successfully for list {self.id}")
                
                # Delete data from selected columns to replace with new ones
                selected_column_positions = [col.position for col_name, col in current_list_columns.items() if col_name in selected_column_names]
                if selected_column_positions:
                    current_app.logger.info(f"Deleting data for selected columns: {selected_column_names}")
                    db.session.query(ListData).filter(
                        ListData.list_id == self.id,
                        ListData.column_position.in_(selected_column_positions)
                    ).delete(synchronize_session=False)
                    db.session.commit()
            else:
                # If no columns are selected, delete all data
                current_app.logger.info(f"Deleting all data for list {self.id} (no column selection)")
                db.session.query(ListData).filter(ListData.list_id == self.id).delete()
                db.session.commit()
            
            current_app.logger.info(f"Data cleanup completed successfully for list {self.id}")
        except Exception as e:
            current_app.logger.error(f"Error during data and column cleanup: {str(e)}")
            db.session.rollback()

        # Import the data
        try:
            row_count = self._import_rows_from_json(processed_json_data, columns_for_import)

            # Update the last update date with Paris time
            self.last_update = get_paris_now()
            self.save() # Calls db.session.commit()

            current_app.logger.info(f"{row_count} rows imported successfully for list {self.id}")
            return row_count
        except Exception as e:
            current_app.logger.error(f"Error importing JSON rows: {str(e)}")
            # Try to continue despite the error - original comment.
            # However, it's better to rollback or handle consistently.
            # For now, returning 0 as per original intent.
            db.session.rollback() # Rollback partial import if error in _import_rows_from_json
            return 0

    def _import_rows_from_json(self, json_data_list, columns_map_for_import): # Renamed params
        """Imports rows from JSON data"""
        # from flask import current_app # Already imported
        row_count = 0
        next_row_id = 1 # Assuming row_id is 1-based sequential for the import batch

        # Log for debugging
        current_app.logger.info(f"Starting import of {len(json_data_list)} JSON rows with {len(columns_map_for_import)} selected columns")
        if columns_map_for_import:
            current_app.logger.info(f"Selected columns for import: {', '.join(columns_map_for_import.keys())}")
        else: # No columns to import into
            current_app.logger.warning(f"No columns defined for JSON import for list {self.id}. No data will be imported.")
            return 0
            
        # Check if columns were selected via JSON configuration
        json_selected_columns = []
        if self.json_selected_columns:
            try:
                json_selected_columns = json.loads(self.json_selected_columns)
                selected_column_names = [col.get('name') for col in json_selected_columns if isinstance(col, dict) and col.get('name')]
                current_app.logger.info(f"Selected columns in JSON configuration: {selected_column_names}")
                
                # Check that all selected columns are in columns_map_for_import
                # If not, it means the filtering was not correctly applied
                if selected_column_names:
                    for col_name in list(columns_map_for_import.keys()):
                        if col_name not in selected_column_names:
                            current_app.logger.warning(f"Column '{col_name}' present in columns_map_for_import but not in JSON configuration. It will be ignored.")
                            del columns_map_for_import[col_name]
            except Exception as e:
                current_app.logger.error(f"Error loading selected columns: {str(e)}")
                
        # Final log of columns that will be used for import
        current_app.logger.info(f"Final columns for import: {', '.join(columns_map_for_import.keys())}")
        if not columns_map_for_import:
            current_app.logger.warning(f"No columns available for import after filtering. No data will be imported.")
            return 0


        list_data_objects_to_add = [] # Batch add

        for json_obj in json_data_list:
            if not isinstance(json_obj, dict): # Should have been caught earlier
                current_app.logger.warning(f"Item in json_data_list is not a dictionary: {json_obj}. Ignored.")
                continue

            # Log for debugging
            current_app.logger.debug(f"Processing JSON object: {json_obj}")

            # Only process columns that are in the 'columns_map_for_import' dictionary
            # This dictionary has already been filtered to contain only selected/existing columns
            processed_this_row = False
            for col_name, column_obj in columns_map_for_import.items():
                # Check if the column exists in the JSON object
                if col_name in json_obj:
                    value = json_obj[col_name]
                    # Convert the value to a string
                    str_value = str(value) if value is not None else ''

                    # Format the value if necessary
                    if column_obj.column_type == 'date' and str_value:
                        # Attempt to convert the date to a standard format
                        try:
                            # from datetime import datetime # Already imported at top
                            # This date parsing logic is very basic. A robust library might be better.
                            # Or, ensure dates are already in a consistent format.
                            # Example formats:
                            possible_fmts = ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S',
                                             '%Y-%m-%d %H:%M:%S', '%Y-%m-%d',
                                             '%d/%m/%Y %H:%M:%S', '%d/%m/%Y',
                                             '%m/%d/%Y %H:%M:%S', '%m/%d/%Y')
                            parsed_date = None
                            for fmt in possible_fmts:
                                try:
                                    parsed_date = datetime.strptime(str_value, fmt)
                                    str_value = parsed_date.strftime('%Y-%m-%d') # Standard internal format
                                    break
                                except ValueError:
                                    continue
                            if parsed_date is None and str_value: # If no format matched and value is not empty
                                current_app.logger.debug(f"Date value '{str_value}' for column '{col_name}' could not be parsed. Kept as is.")
                        except Exception as date_parse_err:
                            current_app.logger.warning(f"Date parsing error for '{str_value}': {date_parse_err}. Kept as is.")


                    list_data_objects_to_add.append(ListData(
                        list_id=self.id,
                        column_position=column_obj.position,
                        row_id=next_row_id,
                        value=str_value
                    ))
                    processed_this_row = True
                else:
                    # If the column (expected in our import schema) does not exist in the JSON object, add an empty value
                    current_app.logger.debug(f"Column {col_name} not found in JSON object, adding empty value for row_id {next_row_id}")
                    list_data_objects_to_add.append(ListData(
                        list_id=self.id,
                        column_position=column_obj.position,
                        row_id=next_row_id,
                        value='' # Empty string for missing value in this row for an expected column
                    ))
                    processed_this_row = True # Still counts as processing the row for this column

            if processed_this_row: # Only increment row_id if we actually processed columns for this json_obj
                row_count += 1
                next_row_id += 1
        
        if list_data_objects_to_add:
            db.session.add_all(list_data_objects_to_add)
            # Commit is usually done by the calling method (_import_json_data) after `save()`
            # db.session.commit() # If this method should be autonomous for commit
        return row_count

    def import_data_from_url(self, force_update=True):
        """Imports data from the list's configured URL.
        
        This method is called from the /update_from_url route.
        It forces the data import even if the last update is recent.
        
        Returns:
            int: The number of imported rows or 0 on failure
        """
        current_app.logger.info(f"List {self.id}: Attempting import from URL with force_update=True")
        
        # Check if we have a configured URL
        if not self.data_source_url:
            current_app.logger.error(f"List {self.id}: No source URL configured")
            return 0
        
        try:
            # Get parameters from Flask configuration
            try:
                # First try via current_app.config
                verify_ssl = current_app.config.get('VERIFY_SSL', 'false').lower() == 'true'
                http_proxy = current_app.config.get('HTTP_PROXY', os.environ.get('HTTP_PROXY', ''))
                https_proxy = current_app.config.get('HTTPS_PROXY', os.environ.get('HTTPS_PROXY', ''))
                no_proxy = current_app.config.get('NO_PROXY', os.environ.get('NO_PROXY', ''))
                
                # Also check lowercase variables
                if not http_proxy:
                    http_proxy = current_app.config.get('http_proxy', os.environ.get('http_proxy', ''))
                if not https_proxy:
                    https_proxy = current_app.config.get('https_proxy', os.environ.get('https_proxy', ''))
                if not no_proxy:
                    no_proxy = current_app.config.get('no_proxy', os.environ.get('no_proxy', ''))
                    
                # Check for custom certificates
                ca_bundle = os.environ.get('REQUESTS_CA_BUNDLE', '')
                ssl_cert_file = os.environ.get('SSL_CERT_FILE', '')
                
                if ca_bundle:
                    current_app.logger.info(f"List {self.id}: Using custom CA certificate: {ca_bundle}")
                if ssl_cert_file:
                    current_app.logger.info(f"List {self.id}: Using custom SSL certificate: {ssl_cert_file}")
                    
            except Exception as e:
                # Fallback to default values in case of error
                current_app.logger.warning(f"Error retrieving environment variables: {str(e)}")
                verify_ssl = False
                http_proxy = ''
                https_proxy = ''
                no_proxy = ''
            
            # Configure proxy only if variables are defined and not empty
            proxies = None
            if http_proxy or https_proxy:
                proxies = {}
                if http_proxy:
                    proxies['http'] = http_proxy
                if https_proxy:
                    proxies['https'] = https_proxy
                current_app.logger.info(f"List {self.id}: Using proxy: {proxies}")
            else:
                current_app.logger.info(f"List {self.id}: No proxy used")
            
            # Disable SSL warnings if necessary
            if not verify_ssl:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                current_app.logger.info(f"List {self.id}: SSL verification disabled")
            
            # Build request parameters
            request_params = {
                'verify': verify_ssl
            }
            
            # Add proxy only if defined
            if proxies:
                request_params['proxies'] = proxies
            
            # Execute request with appropriate parameters
            current_app.logger.info(f"List {self.id}: HTTP request to {self.data_source_url} with proxy={proxies} and verify_ssl={verify_ssl}")
            response = requests.get(self.data_source_url, **request_params)
            response.raise_for_status()
            
            # Determine data format (CSV or JSON)
            content_type = response.headers.get('Content-Type', '')
            is_json = 'json' in content_type.lower() or self.data_source_format == 'json'
            
            # Process data according to its format
            if is_json:
                # Process JSON data
                json_data = response.json()
                row_count = self._import_json_data(json_data)
            else:
                # Process CSV data
                csv_config = {}
                if self.update_config:
                    config = self.get_update_config
                    csv_config = config.get('csv_config', {})
                row_count = self._import_csv_data(response.text, csv_config)
            
            # Update the last update date
            self.last_update = datetime.now(timezone.utc)
            db.session.commit()
            
            # Generate public files if necessary
            if self.is_published:
                if self.public_json_enabled:
                    self.generate_public_json()
                # Add other formats here if needed
            
            current_app.logger.info(f"List {self.id}: Import successful, {row_count} rows imported.")
            return row_count
            
        except requests.exceptions.SSLError as e:
            current_app.logger.error(f"SSL error during import from URL for list {self.id}: {str(e)}")
            return 0
        except requests.exceptions.ProxyError as e:
            current_app.logger.error(f"Proxy error during import from URL for list {self.id}: {str(e)}")
            return 0
        except requests.RequestException as e:
            current_app.logger.error(f"HTTP error during import from URL for list {self.id}: {str(e)}")
            return 0
        except json.JSONDecodeError as e:
            current_app.logger.error(f"JSON decoding error during import from URL for list {self.id}: {str(e)}")
            return 0
        except Exception as e:
            current_app.logger.error(f"Exception during import from URL for list {self.id}: {str(e)}")
            current_app.logger.exception(e)
            return 0
            
    def update_from_url(self):
        """Updates data using DataImporter to handle different sources."""
        # flask.current_app is imported at the top of models/list.py
        current_app.logger.info(f"List {self.id}: Attempting update via DataImporter.")
        importer = DataImporter(self) # DataImporter will be imported
        try:
            # Force update to bypass the elapsed time check
            # DataImporter handles its own logging for success/failure of specific steps
            # and updates self.list_instance.last_update.
            lines_imported = importer.import_data(force_update=True)

            if lines_imported is not None:
                # This means the import process completed; 0 lines is a valid outcome if the source was empty.
                current_app.logger.info(f"List {self.id}: DataImporter.import_data processed {lines_imported} rows.")
                return True # Indicate the import process ran successfully
            else:
                # This means import_data returned None, indicating an explicit skip (e.g., too recent update)
                # or an internal error that DataImporter handled and logged.
                current_app.logger.warning(f"List {self.id}: DataImporter.import_data returned None. The update may have been skipped or failed.")
                return False # Indicate import was skipped or failed
        except Exception as e:
            # This catches unexpected exceptions raised directly from importer.import_data()
            current_app.logger.error(f"List {self.id}: Unexpected exception during call to DataImporter.import_data(): {str(e)}")
            current_app.logger.exception(e) # Log full traceback
            return False # Indicate failure

    def import_data_from_api_curl(self):
        """Imports data from an API via a curl command"""
        import os
        # import json # Already imported

        # Check that the configuration is complete
        current_config = self.update_config # Property returns dict
        if not current_config or not current_config.get('curl_command'):
            current_app.logger.error(f"List {self.id}: curl command not defined in update_config")
            raise ValueError("curl command not defined in update_config")

        # JSON path and selected columns are used by _import_json_data, not directly here for curl execution
        # but they are essential for the import process that follows.
        if not self.json_data_path: # Used by _import_json_data
            current_app.logger.error(f"List {self.id}: JSON path (json_data_path) not defined")
            raise ValueError("JSON path (json_data_path) not defined")

        if not self.json_selected_columns: # Used by _import_json_data
            current_app.logger.error(f"List {self.id}: JSON columns (json_selected_columns) not selected")
            raise ValueError("JSON columns (json_selected_columns) not selected")

        try:
            # Execute the curl command
            curl_command = current_config.get('curl_command')
            current_app.logger.info(f"List {self.id}: Executing curl command: {curl_command}")

            # Using subprocess is generally safer and more flexible than os.popen
            import subprocess
            process = subprocess.Popen(curl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output, error = process.communicate()

            if process.returncode != 0:
                current_app.logger.error(f"List {self.id}: curl command error (code: {process.returncode}): {error}")
                raise ValueError(f"curl command error: {error}")
            
            if not output:
                current_app.logger.error(f"List {self.id}: No output from curl command")
                raise ValueError("No output from curl command")

            # Parse the JSON output
            try:
                raw_data = json.loads(output)
                current_app.logger.info(f"List {self.id}: JSON data successfully retrieved from API Curl")
                # Call the standard JSON import method
                return self._import_json_data(raw_data)
            except json.JSONDecodeError as e_json: # More specific exception
                current_app.logger.error(f"List {self.id}: Error parsing JSON from curl output: {str(e_json)}")
                current_app.logger.debug(f"Raw Curl output: {output[:500]}...") # Log some output for debugging
                raise ValueError(f"Error parsing JSON from curl output: {str(e_json)}")
        except ValueError: # Re-raise ValueErrors from checks or subprocess error
            raise
        except Exception as e: # Catch other unexpected errors
            current_app.logger.error(f"List {self.id}: Unexpected error importing data from API Curl: {str(e)}")
            current_app.logger.exception(e) # Log full traceback
            # Wrap in ValueError or a custom exception type
            raise ValueError(f"Unexpected error importing from API Curl: {str(e)}")

    # NOTE: This is the second definition of this method name in the file.
    def _create_columns_from_json(self, json_obj):
        """Creates columns from a JSON object.
        This method is used when the direct method fails."""
        # from flask import current_app # Already imported
        # from models.list_column import ListColumn # Not needed if ListColumn is in same file, but good for clarity if it were separate.
                                                # ListColumn is defined below in this file.

        current_app.logger.info(f"Creating columns (standard/fallback method) from a JSON object for list {self.id}")

        if not json_obj or not isinstance(json_obj, dict): # Added type check
            current_app.logger.error(f"Invalid or empty JSON object for list {self.id} in _create_columns_from_json (standard).")
            return False

        try:
            # Ensure List ID is set, try to save if not (similar to the other _create_columns_from_json)
            if not self.id:
                try:
                    db.session.add(self)
                    db.session.commit()
                    current_app.logger.info(f"List (ID: {self.id}) saved before creating columns (standard).")
                    if not self.id: # Should be set now
                        raise ValueError("List ID not set even after save attempt.")
                except Exception as e_save:
                    db.session.rollback()
                    current_app.logger.error(f"Error saving list before creating columns (standard): {e_save}")
                    return False


            # Determine starting position
            max_position = db.session.query(db.func.max(ListColumn.position)).filter(
                ListColumn.list_id == self.id
            ).scalar() or 0

            # Get existing columns (refresh to be sure)
            db.session.refresh(self) # Refresh the list object itself to get current columns
            existing_column_names = [col.name for col in self.columns]
            
            new_columns_added_this_call = []
            current_col_pos = max_position

            # Create the columns
            for i, (name, value) in enumerate(json_obj.items()):
                # Check if column already exists
                if name not in existing_column_names:
                    current_col_pos +=1
                    # Determine column type based on value
                    column_type = 'text' # Default

                    if isinstance(value, (int, float)):
                        column_type = 'number'
                    elif isinstance(value, bool):
                        column_type = 'boolean'
                    elif isinstance(value, str):
                        # Attempt to detect dates (basic regex)
                        import re # Import locally for this specific use
                        if re.fullmatch(r'\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?', value): # ISO 8601-like
                            column_type = 'date'
                        # Attempt to detect IP addresses (basic regex)
                        elif re.fullmatch(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', value):
                            column_type = 'ip'
                        # Add more type detections if needed

                    # Create the column
                    try:
                        column = ListColumn(
                            list_id=self.id,
                            name=name,
                            position=current_col_pos,
                            column_type=column_type
                        )
                        db.session.add(column)
                        new_columns_added_this_call.append(name)
                        current_app.logger.info(f"Column '{name}' (type: {column_type}, pos: {current_col_pos}) prepared for addition to list {self.id} (standard).")
                    except Exception as e_col_create: # Catch specific errors if possible (e.g., IntegrityError)
                        current_app.logger.error(f"Error preparing column {name} for list {self.id}: {str(e_col_create)}")
                        # Potentially rollback if one column creation fails in a batch
            
            # Commit the changes (if any new columns were staged)
            if new_columns_added_this_call:
                db.session.commit()
                current_app.logger.info(f"{len(new_columns_added_this_call)} columns ({', '.join(new_columns_added_this_call)}) successfully created for list {self.id} (standard).")
            else:
                current_app.logger.info(f"No new columns to create for list {self.id} (standard).")
            return True
        except Exception as e:
            current_app.logger.error(f"Global error during column creation (standard) for list {self.id}: {str(e)}")
            db.session.rollback()
            return False

    # NOTE: This is the second definition of this method name in the file.
    def _create_columns_fallback(self, json_obj):
        """Fallback method to create columns if the main method fails.
        Uses a different approach with direct SQL queries."""
        # from flask import current_app # Already imported
        current_app.logger.info(f"Attempting to create columns with the fallback method (calling _create_columns_from_json) for list {self.id}")

        # This fallback seems to be different from the first _create_columns_fallback
        # The first one used pymysql direct connection.
        # This one calls the _create_columns_from_json (the second definition of it).
        try:
            # Force a commit of the main session to ensure the list is saved (if pending)
            if db.session.dirty or db.session.new or db.session.deleted:
                db.session.commit()

            # Wait a bit to ensure the transaction is completed (optional, can be short)
            import time
            time.sleep(0.1) # Reduced sleep time

            # Check directly in the database if the list exists (using SQLAlchemy ORM)
            list_exists = db.session.query(db.exists().where(List.id == self.id)).scalar()
            if not list_exists:
                current_app.logger.error(f"List with ID {self.id} does not exist in the database before calling _create_columns_from_json (fallback).")
                # Try to force the creation of the list if self.id is set
                if self.id is not None:
                    try:
                        db.session.add(self) # Add current instance
                        db.session.commit()
                        current_app.logger.info(f"List {self.id} forced into database (fallback).")
                    except Exception as e_save_fallback:
                        current_app.logger.error(f"Error during forced list commit (fallback): {str(e_save_fallback)}")
                        return False # Cannot proceed if list doesn't exist and cannot be saved
                else: # self.id is None, cannot save
                    return False


            # Use the standard method (the second _create_columns_from_json) as a last resort
            return self._create_columns_from_json(json_obj) # Calls the second definition
        except Exception as e:
            current_app.logger.error(f"Error creating columns with the fallback method (calling _create_columns_from_json): {str(e)}")
            db.session.rollback() # Ensure rollback on error
            return False