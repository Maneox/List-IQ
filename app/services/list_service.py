from typing import List as TypeList, Dict, Any, Optional
from datetime import datetime
from ..models.list import List, ListColumn, ListData
from .. import db
import requests
import json
import os

class ListService:
    @staticmethod
    def create_list(name: str, description: Optional[str] = None,
                   columns: Optional[list] = None,
                   update_type: str = 'manual',
                   update_schedule: Optional[str] = None,
                   update_config: Optional[Dict] = None,
                   is_active: bool = True,
                   is_published: bool = False,
                   filter_enabled: bool = False,
                   filter_rules: Optional[str] = None,
                   ip_restriction_enabled: bool = False,
                   allowed_ips: Optional[str] = None,
                   data_source_url: Optional[str] = None,
                   data_source_format: Optional[str] = None,
                   auto_create_columns: bool = False) -> List:
        """Creates a new list"""
        
        try:
            # Extract the URL from update_config if not provided directly
            if not data_source_url and update_config:
                config_dict = update_config
                if isinstance(update_config, str):
                    try:
                        config_dict = json.loads(update_config)
                    except json.JSONDecodeError:
                        config_dict = {}
                
                if isinstance(config_dict, dict) and 'url' in config_dict:
                    data_source_url = config_dict['url']
                    print(f"URL extracted from update_config: {data_source_url}")
            
            # Create the update configuration in JSON format
            if update_config and isinstance(update_config, dict):
                # Ensure the URL is also in update_config if provided
                if data_source_url and 'url' not in update_config:
                    update_config['url'] = data_source_url
                update_config = json.dumps(update_config)
            
            # Check and correct the cron schedule format
            if update_schedule and not update_schedule.strip().count(' ') >= 4:
                # If the format is not correct, use a default format
                update_schedule = "*/5 * * * *"  # Every 5 minutes
            
            # First, create the list without columns
            list_obj = List(
                name=name,
                description=description,
                update_type=update_type,
                update_schedule=update_schedule,
                update_config=update_config,
                is_active=is_active,
                is_published=is_published,
                filter_enabled=filter_enabled,
                filter_rules=filter_rules,
                ip_restriction_enabled=ip_restriction_enabled,
                allowed_ips=allowed_ips,
                data_source_url=data_source_url,
                data_source_format=data_source_format,
                auto_create_columns=auto_create_columns
            )
            
            # Add the list to the session
            db.session.add(list_obj)
            
            # Commit the list BEFORE adding columns to ensure the ID is valid
            # and that the list actually exists in the database
            db.session.commit()
            
            # Ensure the ID is valid after the commit
            if not list_obj.id:
                raise ValueError("Could not get a valid ID for the list")
                
            print(f"List created with ID: {list_obj.id}")
            
            # Now that the list has a valid ID and is saved, add the columns
            column_objects = []
            if columns:
                try:
                    for idx, col_data in enumerate(columns):
                        if not isinstance(col_data, dict):
                            raise ValueError("Columns must be dictionaries")
                        if 'name' not in col_data:
                            raise ValueError("Each column must have a name")
                        
                        # Create the column with the list's ID
                        column = ListColumn(
                            list_id=list_obj.id,
                            name=col_data['name'],
                            position=col_data.get('position', idx),
                            column_type=col_data.get('column_type', 'text')
                        )
                        db.session.add(column)
                        column_objects.append(column)
                    
                    # Commit the columns in a separate transaction
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    print(f"Error adding columns: {str(e)}")
                    # Do not raise an exception here, continue with the list without columns
            
            # Refresh the list object to ensure all columns are loaded
            db.session.refresh(list_obj)
            
            # Import data from the URL if specified
            # Do not automatically import CSV data as it requires prior configuration
            if data_source_url and data_source_format and update_type == 'automatic' and data_source_format.lower() != 'csv':
                try:
                    print(f"Attempting to import from URL: {data_source_url}")
                    from ..models.data_importer import DataImporter
                    importer = DataImporter(list_obj)
                    importer.import_data(force_update=False)
                except Exception as e:
                    print(f"Error importing data from URL: {str(e)}")
            elif data_source_format and data_source_format.lower() == 'csv':
                print(f"CSV import disabled during creation. Please configure the import via the 'CSV Configuration' menu.")
            
            return list_obj
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating list: {str(e)}")
            raise
    
    @staticmethod
    def update_list(list_id: int, data: Dict[str, Any]) -> bool:
        """Updates a list"""
        try:
            list_obj = List.query.get(list_id)
            if not list_obj:
                return False
            
            # Update basic fields
            for field in ['name', 'description', 'update_type', 'update_schedule',
                        'is_active', 'is_published']:
                if field in data:
                    setattr(list_obj, field, data[field])
            
            # Update configuration
            if 'update_config' in data:
                config = data['update_config']
                if isinstance(config, str):
                    try:
                        config = json.loads(config)
                    except json.JSONDecodeError:
                        return False
                list_obj.set_update_config(config)
            
            db.session.commit()
            
            # If the URL has changed, update the data immediately
            old_config = list_obj.get_update_config()
            if (old_config and 'url' in old_config and 
                'update_config' in data and 
                isinstance(data['update_config'], dict) and
                'url' in data['update_config'] and 
                old_config['url'] != data['update_config']['url']):
                
                new_data = ListService.fetch_data_from_url(
                    data['update_config']['url'],
                    data['update_config'].get('is_json', True)
                )
                if new_data:
                    return ListService.update_list_data(list_id, new_data)
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"Error updating list: {str(e)}")
            return False
            
    @staticmethod
    def update_list_data(list_id: int, data: TypeList[Dict[str, Any]]) -> bool:
        """Updates a list's data"""
        list_obj = List.query.get(list_id)
        if not list_obj:
            return False

        try:
            # Apply the results limit if defined
            if list_obj.max_results > 0 and len(data) > list_obj.max_results:
                print(f"ListService: Results limit applied: {list_obj.max_results} out of {len(data)} available results")
                data = data[:list_obj.max_results]
            
            # Delete old data
            ListData.query.filter_by(list_id=list_id).delete()
            
            # Create or update columns
            if data and len(data) > 0:
                columns = list(data[0].keys())
                column_objects = []
                
                # Create or update columns
                for position, col_name in enumerate(columns):
                    col = ListColumn.query.filter_by(list_id=list_id, name=col_name).first()
                    if not col:
                        # Detect column type
                        col_type = 'text'  # Default type
                        if col_name.lower() in ['date', 'datetime']:
                            col_type = 'date'
                        elif col_name.lower() in ['ip', 'ipaddress', 'ip_address']:
                            col_type = 'ip'
                        elif col_name.lower() in ['number', 'num', 'level']:
                            col_type = 'number'

                        col = ListColumn(
                            list_id=list_id,
                            name=col_name,
                            position=position,
                            column_type=col_type
                        )
                        db.session.add(col)
                    else:
                        col.position = position
                    column_objects.append(col)
                
                db.session.flush()

                # Add the new data
                for row_idx, row_data in enumerate(data):
                    for col_name, value in row_data.items():
                        col = next((c for c in column_objects if c.name == col_name), None)
                        if col:
                            # Validate and format the value according to the column type
                            formatted_value = value
                            try:
                                if col.column_type == 'date' and value:
                                    # Try different date formats
                                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y']:
                                        try:
                                            formatted_value = datetime.strptime(str(value), fmt).strftime('%Y-%m-%d')
                                            break
                                        except ValueError:
                                            continue
                                elif col.column_type == 'number' and value:
                                    formatted_value = float(value)
                            except (ValueError, TypeError):
                                formatted_value = str(value)

                            data_entry = ListData(
                                list_id=list_id,
                                column_position=col.position,
                                row_id=row_idx,
                                value=str(formatted_value)
                            )
                            db.session.add(data_entry)

            list_obj.last_update = datetime.now()
            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            print(f"Error updating list data: {str(e)}")
            return False
    
    @staticmethod
    def check_and_update_lists() -> None:
        """Checks and updates all automatic lists"""
        lists = List.query.filter_by(
            update_type='automatic',
            is_active=True
        ).all()
        
        for list_obj in lists:
            if list_obj.is_update_due():
                list_obj.perform_update()
    
    @staticmethod
    def get_list(list_id: int) -> Optional[List]:
        """Gets a list by its ID"""
        return List.query.get(list_id)
    
    @staticmethod
    def get_lists(include_inactive: bool = False) -> TypeList[List]:
        """Gets all lists"""
        query = List.query
        if not include_inactive:
            query = query.filter_by(is_active=True)
        return query.all()
    
    @staticmethod
    def delete_list(list_id: int) -> bool:
        """Deletes a list"""
        list_obj = List.query.get(list_id)
        if not list_obj:
            return False
        
        db.session.delete(list_obj)
        db.session.commit()
        return True
    
    @staticmethod
    def import_data_from_file(list_id: int, file_content: str) -> bool:
        """Imports data from a CSV file"""
        list_obj = List.query.get(list_id)
        if not list_obj:
            return False

        try:
            # Split the content into lines
            lines = [line.strip() for line in file_content.splitlines() if line.strip()]
            if not lines:
                raise ValueError("The file is empty")

            # Extract headers
            headers = [h.strip() for h in lines[0].split(',')]

            # Validate headers against existing columns
            existing_columns = {col.name: col.column_type for col in list_obj.columns}
            invalid_columns = []

            for header in headers:
                if header in existing_columns:
                    # Check if the column type is compatible
                    if existing_columns[header] == 'date':
                        # Check the date format in the data
                        for line in lines[1:]:
                            values = line.split(',')
                            value_idx = headers.index(header)
                            if value_idx < len(values):
                                value = values[value_idx].strip()
                                if value:  # Ignore empty values
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
                                            invalid_columns.append(f"Column '{header}' contains invalid dates")
                                            break
                                    except ValueError:
                                        invalid_columns.append(f"Column '{header}' contains invalid dates")
                                        break

            if invalid_columns:
                raise ValueError("Invalid columns found: " + ", ".join(invalid_columns))

            # Prepare the data
            data = []
            for line in lines[1:]:  # Ignore the header row
                values = [v.strip() for v in line.split(',')]
                if len(values) != len(headers):
                    continue  # Ignore poorly formatted rows
                
                row_data = {}
                for header, value in zip(headers, values):
                    row_data[header] = value
                data.append(row_data)

            # Update the data
            return ListService.update_list_data(list_id, data)

        except Exception as e:
            print(f"Error importing data: {str(e)}")
            raise ValueError(str(e))

    @staticmethod
    def import_from_file(list_id: int, file_path: str, file_type: str = 'csv') -> bool:
        """Imports data from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                if file_type == 'json':
                    data = json.loads(content)
                    return ListService.update_list_data(list_id, data)
                else:  # csv
                    return ListService.import_data_from_file(list_id, content)
        except Exception as e:
            raise ValueError(f"Error reading the file: {str(e)}")
    
    @staticmethod
    def fetch_data_from_url(url: str, is_json: bool = True) -> Optional[TypeList[Dict[str, Any]]]:
        """Fetches data from a URL"""
        try:
            print(f"Fetching data from URL: {url}")  # Debug log
            
            # Get proxy environment variables
            proxies = {}
            http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
            https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            no_proxy = os.environ.get('NO_PROXY') or os.environ.get('no_proxy')
            
            # Configure proxies if they are defined
            if http_proxy:
                proxies['http'] = http_proxy
                print(f"Using HTTP proxy: {http_proxy}")
            if https_proxy:
                proxies['https'] = https_proxy
                print(f"Using HTTPS proxy: {https_proxy}")
            
            # Configure SSL verification
            verify_ssl = os.environ.get('VERIFY_SSL', 'true').lower() != 'false'
            print(f"SSL verification: {'enabled' if verify_ssl else 'disabled'}")
            
            # Make the request with proxy parameters
            response = requests.get(url, proxies=proxies if proxies else None, verify=verify_ssl)
            response.raise_for_status()
            
            if is_json:
                print(f"Response content (JSON): {response.text[:200]}...")  # Debug log
                try:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        return [data]
                    else:
                        print(f"Unexpected JSON data type: {type(data)}")  # Debug log
                        return None
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}, switching to text mode")  # Debug log
                    is_json = False  # Switch to text mode if JSON parsing fails
            
            if not is_json:
                print(f"Processing as text: {response.text[:200]}...")  # Debug log
                # For text files, create a list of dictionaries
                lines = response.text.splitlines()
                # Filter empty lines and comments
                lines = [line.strip() for line in lines 
                        if line.strip() and not line.strip().startswith('#')]
                return [{"IP": line} for line in lines]
                
        except requests.exceptions.RequestException as e:
            print(f"Request error: {str(e)}")  # Debug log
            return None
        except Exception as e:
            print(f"Unexpected error in fetch_data_from_url: {str(e)}")  # Debug log
            return None
    
    @staticmethod
    def get_filtered_data(list_id: int, ip: Optional[str] = None) -> Optional[TypeList[Dict[str, Any]]]:
        """Gets a list's filtered data"""
        list_obj = List.query.get(list_id)
        if not list_obj:
            return None
        
        # Check IP restrictions
        if list_obj.ip_restriction_enabled and ip:
            if not list_obj.is_ip_allowed(ip):
                return None
        
        # Get the data
        data = list_obj.get_data()
        
        # Apply filters if necessary
        if list_obj.filter_enabled:
            data = list_obj.apply_filters(data)
        
        return data