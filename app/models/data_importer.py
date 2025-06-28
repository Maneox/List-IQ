# models/data_importer.py
from flask import current_app
import requests
import json
import csv
import io
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List as TypeList
from sqlalchemy.exc import SQLAlchemyError

from .list_components import ListColumn, ListData
from .. import db

try:
    from app.utils.date_utils import get_paris_now
except ImportError:
    get_paris_now = lambda: datetime.now(timezone.utc)

class DataImporter:
    def __init__(self, list_instance):
        self.list_instance = list_instance
        self.config = list_instance.update_config
        self.logger = current_app.logger

    def import_data(self, force_update=False) -> Optional[int]:
        source = self.config.get('source')
        api_type = self.config.get('api_type')
        lines_imported = None

        self.logger.info(f"List {self.list_instance.id}: Starting import. Source: {source}, API Type: {api_type}")

        try:
            self._clear_existing_data()

            if source == 'url':
                lines_imported = self._import_data_from_url_source(force_update=force_update)
            elif source == 'curl' or (source == 'api' and api_type == 'curl'):
                lines_imported = self._import_data_from_api_curl_source()
            else:
                self.logger.warning(f"List {self.list_instance.id}: Unsupported import source '{source}'.")
                return None

            if lines_imported is not None:
                self.list_instance.last_update = get_paris_now()
                db.session.add(self.list_instance)
                db.session.commit()
                self.logger.info(f"List {self.list_instance.id}: Import successful, {lines_imported} lines imported. Last update set.")
            else:
                self.logger.info(f"List {self.list_instance.id}: Import returned no lines or was cancelled.")
            
            return lines_imported

        except Exception as e:
            db.session.rollback()
            self.logger.error(f"List {self.list_instance.id}: Major error during import_data: {e}", exc_info=True)
            return None

    def _clear_existing_data(self) -> None:
        self.logger.info(f"List {self.list_instance.id}: Clearing existing data and columns.")
        try:
            # Delete data
            ListData.query.filter_by(list_id=self.list_instance.id).delete(synchronize_session='fetch')
            
            # Delete columns
            ListColumn.query.filter_by(list_id=self.list_instance.id).delete(synchronize_session='fetch')
            
            # Flush to ensure deletions are taken into account
            db.session.flush()
            
            # Refresh the list_instance object to avoid issues with deleted objects
            db.session.refresh(self.list_instance)
            
            self.logger.info(f"List {self.list_instance.id}: Successfully cleared data and columns.")
        except SQLAlchemyError as e:
            self.logger.error(f"List {self.list_instance.id}: Error clearing data: {e}", exc_info=True)
            raise # Reraise so the main transaction is rolled back

    def _create_columns_from_json_direct(self, json_obj_list: TypeList[Dict[str, Any]]) -> bool:
        if not isinstance(json_obj_list, list) or not json_obj_list:
            self.logger.warning(f"List {self.list_instance.id}: JSON object for column creation is not a list or is empty.")
            return False
        
        # Check if a data path is configured
        data_path = self.config.get('json_data_path', '')
        if data_path:
            self.logger.info(f"List {self.list_instance.id}: Data path configured: {data_path}")
        
        sample_item = json_obj_list[0]
        if not isinstance(sample_item, dict):
            self.logger.warning(f"List {self.list_instance.id}: First item in JSON object is not a dictionary.")
            return False
            
        # Check if the JSON has a nested structure (e.g., a 'people' key containing an array of objects)
        # Try to find an array in the JSON object
        nested_array = None
        
        # If a path is configured, try to use it directly
        if data_path and data_path in sample_item and isinstance(sample_item[data_path], list) and len(sample_item[data_path]) > 0:
            nested_array = sample_item[data_path]
            self.logger.info(f"List {self.list_instance.id}: Using configured data path '{data_path}' to access data")
        else:
            # Otherwise, try to automatically find an array in the JSON object
            for key, value in sample_item.items():
                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                    nested_array = value
                    self.logger.info(f"List {self.list_instance.id}: Nested JSON structure detected with key '{key}'")
                    break
                
        # If a nested array was found, use its first element as a sample
        if nested_array:
            sample_item = nested_array[0]
            self.logger.info(f"List {self.list_instance.id}: Using nested element as sample: {sample_item}")
            # Replace json_obj_list with the nested array for further processing
            json_obj_list = nested_array

        existing_columns_map = {col.name: col for col in self.list_instance.columns}
        new_columns_created_count = 0
        current_max_position = max([col.position for col in self.list_instance.columns] + [-1])
        
        # Check if specific columns were selected in the JSON configuration
        selected_columns = []
        if hasattr(self.list_instance, 'json_selected_columns') and self.list_instance.json_selected_columns:
            try:
                selected_columns = json.loads(self.list_instance.json_selected_columns)
                self.logger.info(f"List {self.list_instance.id}: Selected columns in JSON configuration: {selected_columns}")
            except json.JSONDecodeError:
                self.logger.warning(f"List {self.list_instance.id}: Could not decode selected columns: {self.list_instance.json_selected_columns}")
        
        # Create a set of selected column names for faster lookup
        selected_column_names = {col['name'] for col in selected_columns} if selected_columns else set()
        
        new_column_objects = []
        for key in sample_item.keys():
            # If columns are selected, only create those
            if selected_column_names and key not in selected_column_names:
                self.logger.info(f"List {self.list_instance.id}: Column {key} ignored as it was not selected in the JSON configuration")
                continue
                
            if key not in existing_columns_map:
                current_max_position += 1
                # Look for the column type in the selected columns
                column_type = 'text'
                for col in selected_columns:
                    if col['name'] == key and 'type' in col:
                        column_type = col['type']
                        break
                        
                col = ListColumn(list_id=self.list_instance.id, name=key, column_type=column_type, position=current_max_position)
                new_column_objects.append(col)
                existing_columns_map[key] = col # Add to map for subsequent checks within this import
                new_columns_created_count += 1
        
        if new_column_objects:
            db.session.add_all(new_column_objects)
            db.session.flush() # to get IDs
            db.session.refresh(self.list_instance) # Refresh the object to update the columns relationship
            self.logger.info(f"List {self.list_instance.id}: Created {new_columns_created_count} new columns from JSON (direct). Current columns: {len(self.list_instance.columns)}")
            # Check that columns are correctly associated with the list
            if not self.list_instance.columns:
                self.logger.warning(f"List {self.list_instance.id}: Columns were created but not associated with list. Forcing refresh.")
                db.session.expire(self.list_instance, ['columns']) # Force a reload of the columns
        return new_columns_created_count > 0

    def _create_columns_fallback(self, json_obj_list: TypeList[Dict[str, Any]]) -> bool:
        self.logger.info(f"List {self.list_instance.id}: Attempting to create columns using fallback method.")
        if not isinstance(json_obj_list, list) or not json_obj_list:
            self.logger.warning(f"List {self.list_instance.id}: Fallback - JSON object is not a list or is empty.")
            return False
            
        # Check if a data path is configured
        data_path = self.config.get('json_data_path', '')
        if data_path:
            self.logger.info(f"List {self.list_instance.id}: Data path configured (fallback): {data_path}")
            
        sample_item = json_obj_list[0]
        if not isinstance(sample_item, dict):
            self.logger.warning(f"List {self.list_instance.id}: Fallback - First item in JSON object is not a dict.")
            return False
            
        # Check if the JSON has a nested structure (e.g., a 'people' key containing an array of objects)
        # Try to find an array in the JSON object
        nested_array = None
        
        # If a path is configured, try to use it directly
        if data_path and data_path in sample_item and isinstance(sample_item[data_path], list) and len(sample_item[data_path]) > 0:
            nested_array = sample_item[data_path]
            self.logger.info(f"List {self.list_instance.id}: Using configured data path '{data_path}' to access data (fallback)")
            # Use the first element of the array as a sample
            sample_item = nested_array[0]
            self.logger.info(f"List {self.list_instance.id}: Using nested element as sample (fallback): {sample_item}")
            # Replace json_obj_list with the nested array for further processing
            json_obj_list = nested_array
            
        # Check if specific columns were selected in the JSON configuration
        selected_columns = []
        if hasattr(self.list_instance, 'json_selected_columns') and self.list_instance.json_selected_columns:
            try:
                selected_columns = json.loads(self.list_instance.json_selected_columns)
                self.logger.info(f"List {self.list_instance.id}: Selected columns in JSON configuration (fallback): {selected_columns}")
            except json.JSONDecodeError:
                self.logger.warning(f"List {self.list_instance.id}: Could not decode selected columns: {self.list_instance.json_selected_columns}")
        
        # Create a set of selected column names for faster lookup
        selected_column_names = {col['name'] for col in selected_columns} if selected_columns else set()

        # This fallback uses direct SQL, which is generally discouraged if ORM can be used.
        # However, porting as-is first.
        conn = db.engine.connect()
        trans = conn.begin()
        try:
            existing_column_names_query = db.session.query(ListColumn.name).filter_by(list_id=self.list_instance.id).all()
            existing_column_names = [name for (name,) in existing_column_names_query]
            
            current_max_position_query = db.session.query(db.func.max(ListColumn.position)).filter_by(list_id=self.list_instance.id).scalar()
            current_position = (current_max_position_query or -1) + 1
            
            new_cols_added_count = 0
            for key in sample_item.keys():
                # If columns are selected, only create those
                if selected_column_names and key not in selected_column_names:
                    self.logger.info(f"List {self.list_instance.id}: Column {key} ignored as it was not selected in the JSON configuration (fallback)")
                    continue
                    
                if key not in existing_column_names:
                    # Look for the column type in the selected columns
                    column_type = 'text'
                    for col in selected_columns:
                        if col['name'] == key and 'type' in col:
                            column_type = col['type']
                            break
                            
                    conn.execute(ListColumn.__table__.insert().values(
                        list_id=self.list_instance.id,
                        name=key,
                        column_type=column_type, # Use the type from selected columns if available
                        position=current_position
                    ))
                    existing_column_names.append(key) # Keep track locally
                    current_position += 1
                    new_cols_added_count += 1
            trans.commit()
            if new_cols_added_count > 0:
                self.logger.info(f"List {self.list_instance.id}: Fallback method created {new_cols_added_count} new columns.")
                db.session.expire(self.list_instance, ['columns']) # Expire to refresh from DB
            return new_cols_added_count > 0
        except Exception as e:
            trans.rollback()
            self.logger.error(f"List {self.list_instance.id}: Fallback column creation failed: {e}", exc_info=True)
            return False
        finally:
            conn.close()

    def _create_columns_from_json(self, json_obj_list: TypeList[Dict[str, Any]]) -> bool:
        if self._create_columns_from_json_direct(json_obj_list):
            return True
        self.logger.warning(f"List {self.list_instance.id}: Direct column creation from JSON failed, trying fallback.")
        return self._create_columns_fallback(json_obj_list)

    def _import_rows_from_json(self, json_data_list: TypeList[Dict[str, Any]], columns_map: Dict[str, ListColumn]) -> int:
        if not isinstance(json_data_list, list):
            self.logger.error(f"List {self.list_instance.id}: JSON data for row import is not a list.")
            return 0

        # Check if specific columns were selected in the JSON configuration
        selected_column_names = set()
        selected_columns_config = []
        if hasattr(self.list_instance, 'json_selected_columns') and self.list_instance.json_selected_columns:
            try:
                selected_columns_config = json.loads(self.list_instance.json_selected_columns)
                selected_column_names = {col['name'] for col in selected_columns_config}
                self.logger.info(f"List {self.list_instance.id}: Importing data only for selected columns: {selected_column_names}")
            except json.JSONDecodeError:
                self.logger.warning(f"List {self.list_instance.id}: Could not decode selected columns: {self.list_instance.json_selected_columns}")

        # Log available columns in columns_map for debugging
        self.logger.info(f"List {self.list_instance.id}: Available columns in columns_map: {list(columns_map.keys())}")
        
        # Check if the selected columns exist in columns_map
        if selected_column_names:
            missing_columns = selected_column_names - set(columns_map.keys())
            if missing_columns:
                self.logger.warning(f"List {self.list_instance.id}: Some selected columns do not exist in columns_map: {missing_columns}")
            
            available_selected_columns = selected_column_names.intersection(set(columns_map.keys()))
            self.logger.info(f"List {self.list_instance.id}: Available selected columns: {available_selected_columns}")
        
        # Apply row limit if configured
        max_results = getattr(self.list_instance, 'max_results', 0)
        if max_results > 0 and len(json_data_list) > max_results:
            self.logger.info(f"List {self.list_instance.id}: Limiting to {max_results} rows out of {len(json_data_list)} available")
            json_data_list = json_data_list[:max_results]
        
        # Prepare data for insertion
        new_data_items = []
        rows_imported_count = 0
        
        for row_index, item in enumerate(json_data_list):
            if not isinstance(item, dict):
                self.logger.warning(f"List {self.list_instance.id}: Item at index {row_index} is not a dict, skipping.")
                continue
                
            has_data_for_row = False
            
            # Log available keys in this item for debugging
            self.logger.info(f"List {self.list_instance.id}: Available keys in item {row_index}: {list(item.keys())}")
            
            for col_name, value in item.items():
                # If specific columns were selected, ignore the others
                if selected_column_names and col_name not in selected_column_names:
                    continue
                    
                column = columns_map.get(col_name)
                if column:
                    # Convert the value to a string if necessary
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    
                    self.logger.info(f"List {self.list_instance.id}: Adding value for column '{col_name}'")
                    new_data_items.append(ListData(
                        list_id=self.list_instance.id,
                        row_id=row_index, 
                        column_position=column.position,
                        value=str(value) if value is not None else None
                    ))
                    has_data_for_row = True
                else:
                    self.logger.warning(f"List {self.list_instance.id}: Column '{col_name}' not found in columns_map")
            
            if has_data_for_row:
                rows_imported_count += 1
                if row_index < 3:  # Log only the first few rows to avoid log flooding
                    self.logger.info(f"List {self.list_instance.id}: Row {row_index} imported successfully")
            else:
                self.logger.warning(f"List {self.list_instance.id}: No data imported for row {row_index}")
        
        if new_data_items:
            db.session.bulk_save_objects(new_data_items)
            # No commit here
        self.logger.info(f"List {self.list_instance.id}: Prepared {len(new_data_items)} data cells for {rows_imported_count} rows from JSON data.")
        return rows_imported_count

    def _process_json_data(self, json_input: Any) -> Optional[int]:
        if isinstance(json_input, str):
            try:
                self.logger.info(f"List {self.list_instance.id}: Parsing JSON string input")
                json_data_parsed = json.loads(json_input)
                self.logger.info(f"List {self.list_instance.id}: JSON parsed successfully")
            except json.JSONDecodeError as e:
                self.logger.error(f"List {self.list_instance.id}: Invalid JSON string: {e}", exc_info=True)
                raise ValueError(f"Invalid JSON string: {e}") from e
        elif isinstance(json_input, (list, dict)):
            self.logger.info(f"List {self.list_instance.id}: Using pre-parsed JSON input of type {type(json_input)}")
            json_data_parsed = json_input
        else:
            self.logger.error(f"List {self.list_instance.id}: Unsupported JSON input type: {type(json_input)}")
            raise TypeError(f"Unsupported JSON input type: {type(json_input)}")

        # Ensure the data format is set to JSON
        if hasattr(self.list_instance, 'data_source_format'):
            self.list_instance.data_source_format = 'json'
            self.logger.info(f"List {self.list_instance.id}: Data format set to 'json'")
            db.session.flush()  # Ensure the change is saved
        
        # Log initial JSON structure for debugging
        if isinstance(json_data_parsed, dict):
            self.logger.info(f"List {self.list_instance.id}: Available root JSON keys: {list(json_data_parsed.keys())}")
        elif isinstance(json_data_parsed, list):
            self.logger.info(f"List {self.list_instance.id}: Root JSON is a list of {len(json_data_parsed)} elements")
        
        # Get the configured JSON data path
        data_path = ''
        if hasattr(self.list_instance, 'json_data_path') and self.list_instance.json_data_path:
            data_path = self.list_instance.json_data_path
            self.logger.info(f"List {self.list_instance.id}: Using configured JSON data path: '{data_path}'")
        else:
            data_path = self.config.get('json_data_path', '')
            self.logger.info(f"List {self.list_instance.id}: Using JSON data path from config: '{data_path}'")
        
        records_list = json_data_parsed
        if data_path:
            try:
                # Process the path part by part
                path_parts = [part for part in data_path.split('.') if part]  # Filter out empty parts
                self.logger.info(f"List {self.list_instance.id}: Path parts: {path_parts}")
                
                for key_part in path_parts:
                    if isinstance(records_list, dict):
                        if key_part in records_list:
                            records_list = records_list[key_part]
                            self.logger.info(f"List {self.list_instance.id}: Navigating path: '{key_part}' (type: dict)")
                        else:
                            available_keys = list(records_list.keys())
                            self.logger.error(f"List {self.list_instance.id}: Key '{key_part}' not found in dictionary. Available keys: {available_keys}")
                            raise KeyError(f"Path part '{key_part}' not found in dictionary. Available keys: {available_keys}")
                    elif isinstance(records_list, list):
                        if key_part.isdigit() and int(key_part) < len(records_list):
                            records_list = records_list[int(key_part)]
                            self.logger.info(f"List {self.list_instance.id}: Navigating path: '{key_part}' (type: list)")
                        else:
                            self.logger.error(f"List {self.list_instance.id}: Index '{key_part}' invalid for a list of size {len(records_list)}")
                            raise IndexError(f"Path part '{key_part}' is an invalid index for list of size {len(records_list)}.")
                    else:
                        self.logger.error(f"List {self.list_instance.id}: Cannot navigate path part '{key_part}'. Current type: {type(records_list)}")
                        raise TypeError(f"Cannot navigate path part '{key_part}' on type {type(records_list)}.")
            except (KeyError, IndexError, TypeError) as e:
                self.logger.error(f"List {self.list_instance.id}: json_data_path '{data_path}' not found in JSON structure: {e}")
                # Show JSON structure to help with debugging
                if isinstance(json_data_parsed, dict):
                    self.logger.error(f"List {self.list_instance.id}: Root JSON structure (keys): {list(json_data_parsed.keys())}")
                elif isinstance(json_data_parsed, list) and len(json_data_parsed) > 0:
                    self.logger.error(f"List {self.list_instance.id}: Root JSON structure: list of {len(json_data_parsed)} elements")
                    if isinstance(json_data_parsed[0], dict):
                        self.logger.error(f"List {self.list_instance.id}: First element (keys): {list(json_data_parsed[0].keys())}")
                raise
                if isinstance(json_data_parsed, dict):
                    self.logger.error(f"List {self.list_instance.id}: Available root JSON keys: {list(json_data_parsed.keys())}")
                raise ValueError(f"json_data_path '{data_path}' not found: {str(e)}") from e

        # Check if records_list is empty
        if records_list is None:
            self.logger.error(f"List {self.list_instance.id}: Empty JSON data after path navigation")
            return 0

        # Log the result after path navigation
        self.logger.info(f"List {self.list_instance.id}: Data type after navigation: {type(records_list)}")
        if isinstance(records_list, dict):
            self.logger.info(f"List {self.list_instance.id}: Available keys after navigation: {list(records_list.keys())}")
        elif isinstance(records_list, list):
            self.logger.info(f"List {self.list_instance.id}: Number of elements after navigation: {len(records_list)}")
            if len(records_list) > 0:
                self.logger.info(f"List {self.list_instance.id}: Type of first element: {type(records_list[0])}")
                if isinstance(records_list[0], dict):
                    self.logger.info(f"List {self.list_instance.id}: Keys of first element: {list(records_list[0].keys())}")

        # Ensure records_list is a list for consistent processing
        if isinstance(records_list, dict):
            # If we have a single object, convert it to a list with one item
            self.logger.info(f"List {self.list_instance.id}: Converting single JSON object to list for processing")
            records_list = [records_list]
        elif not isinstance(records_list, list):
            # If it's not a list or dict, try to convert it to a list
            try:
                if hasattr(records_list, '__iter__') and not isinstance(records_list, str):
                    records_list = list(records_list)
                    self.logger.info(f"List {self.list_instance.id}: Converted iterable to list with {len(records_list)} items")
                else:
                    # If it's a scalar value, wrap it in a list
                    records_list = [{'value': records_list}]
                    self.logger.info(f"List {self.list_instance.id}: Wrapped scalar value in list")
            except Exception as e:
                self.logger.error(f"List {self.list_instance.id}: Failed to convert {type(records_list)} to list: {e}")
                raise ValueError(f"Cannot process JSON data: expected list or dict after path navigation, got {type(records_list)}") from e

        # Check again if records_list is a non-empty list
        if not isinstance(records_list, list) or not records_list:
            self.logger.error(f"List {self.list_instance.id}: Invalid JSON data after conversion: {type(records_list)}")
            return 0

        # Create columns if needed
        if not self.list_instance.columns or getattr(self.list_instance, 'auto_create_columns', True):
            self.logger.info(f"List {self.list_instance.id}: Creating columns from JSON data")
            self._create_columns_from_json_direct(records_list)
        else:
            self.logger.info(f"List {self.list_instance.id}: Using existing columns (auto_create_columns is disabled)")

        # Get column mapping
        columns_map = {col.name: col for col in self.list_instance.columns}
        self.logger.info(f"List {self.list_instance.id}: Available columns for import: {list(columns_map.keys())}")
        
        # Import rows
        return self._import_rows_from_json(records_list, columns_map)

    def _import_rows_from_json(self, records_list: list, columns_map: Dict[str, ListColumn]) -> int:
        """Import rows from JSON data into the database."""
        rows_imported_count = 0
        new_data_items = []
        
        # Get the configured row limit
        max_results = getattr(self.list_instance, 'max_results', 0)
        if max_results > 0:
            self.logger.info(f"List {self.list_instance.id}: Limit configured to {max_results} rows for JSON import")
        
        # Get JSON configuration for column filtering
        json_config = self.config.get('json_config', {})
        columns_to_import = json_config.get('columns_to_import', [])
        
        # Counter for the row limit
        row_count = 0
        
        for row_index, record in enumerate(records_list):
            # Check if we have reached the configured limit
            if max_results > 0 and row_count >= max_results:
                self.logger.info(f"List {self.list_instance.id}: Limit of {max_results} rows reached, stopping JSON import")
                break
            
            # Skip non-dict records
            if not isinstance(record, dict):
                self.logger.warning(f"List {self.list_instance.id}: Skipping non-dict record at index {row_index}: {type(record)}")
                continue
                
            has_data_for_row = False
            
            # If we have specific columns to import, only use those
            if columns_to_import:
                for col_name, column_obj in columns_map.items():
                    if col_name in columns_to_import and col_name in record:
                        value = record[col_name]
                        new_data_items.append(ListData(
                            list_id=self.list_instance.id,
                            row_id=row_index,
                            column_position=column_obj.position,
                            value=str(value) if value is not None else None
                        ))
                        has_data_for_row = True
            else:
                # Default behavior: import all available columns
                for col_name, column_obj in columns_map.items():
                    if col_name in record:
                        value = record[col_name]
                        new_data_items.append(ListData(
                            list_id=self.list_instance.id,
                            row_id=row_index,
                            column_position=column_obj.position,
                            value=str(value) if value is not None else None
                        ))
                        has_data_for_row = True
            
            if has_data_for_row:
                rows_imported_count += 1
                row_count += 1
        
        # Insert data into database
        if new_data_items:
            db.session.bulk_save_objects(new_data_items)
            self.logger.info(f"List {self.list_instance.id}: Inserted {len(new_data_items)} data cells for {rows_imported_count} rows from JSON data.")
        else:
            self.logger.warning(f"List {self.list_instance.id}: No data items to insert from JSON records.")
        
        return rows_imported_count

    def _create_columns_from_csv_header(self, header_row: TypeList[str]) -> Dict[str, ListColumn]:
        existing_columns_map = {col.name: col for col in self.list_instance.columns}
        new_column_objects = []
        current_max_position = max([col.position for col in self.list_instance.columns] + [-1])
        final_columns_map = existing_columns_map.copy()
        
        # Check if we have a CSV configuration with specific columns to import
        csv_config = self.config.get('csv_config', {})
        columns_to_import = csv_config.get('columns_to_import', [])
        
        self.logger.info(f"List {self.list_instance.id}: CSV configuration for import: {csv_config}")
        
        # If we have a list of columns to import, we only create those columns
        if columns_to_import:
            self.logger.info(f"List {self.list_instance.id}: Filtering columns according to configuration: {columns_to_import}")
            
            # Create a dictionary of filtered columns
            filtered_columns = {}
            for col_idx in columns_to_import:
                if isinstance(col_idx, int) and 0 <= col_idx < len(header_row):
                    col_name = header_row[col_idx].strip()
                    if col_name:
                        filtered_columns[col_idx] = col_name
            
            self.logger.info(f"List {self.list_instance.id}: Filtered columns: {filtered_columns}")
            
            # Create only the filtered columns
            for idx, col_name in filtered_columns.items():
                if col_name not in final_columns_map:
                    current_max_position += 1
                    # Check if a specific type is defined for this column
                    column_types = csv_config.get('column_types', {})
                    column_type = column_types.get(str(idx), 'text')
                    
                    col = ListColumn(list_id=self.list_instance.id, name=col_name, column_type=column_type, position=current_max_position)
                    new_column_objects.append(col)
                    final_columns_map[col_name] = col
        else:
            # Default behavior: create all columns
            for idx, col_name in enumerate(header_row):
                col_name = col_name.strip()
                if not col_name:
                    self.logger.warning(f"List {self.list_instance.id}: Empty column name in CSV header at index {idx}, skipping.")
                    continue
                if col_name not in final_columns_map:
                    current_max_position += 1
                    col = ListColumn(list_id=self.list_instance.id, name=col_name, column_type='text', position=current_max_position)
                    new_column_objects.append(col)
                    final_columns_map[col_name] = col
        
        if new_column_objects:
            db.session.add_all(new_column_objects)
            db.session.flush() # Get IDs
            self.logger.info(f"List {self.list_instance.id}: Created {len(new_column_objects)} new columns from CSV header.")
        return final_columns_map

    def _import_rows_from_csv(self, csv_reader: csv.reader, header_row: TypeList[str], columns_map: Dict[str, ListColumn]) -> int:
        rows_imported_count = 0
        new_data_items = []
        header_to_index = {name.strip(): i for i, name in enumerate(header_row)}
        
        # Check if we have a CSV configuration with specific columns to import
        csv_config = self.config.get('csv_config', {})
        columns_to_import = csv_config.get('columns_to_import', [])
        
        # Get the configured row limit
        max_results = getattr(self.list_instance, 'max_results', 0)
        if max_results > 0:
            self.logger.info(f"List {self.list_instance.id}: Limit configured to {max_results} rows for CSV import")
        
        # Create a mapping between column indices and column names
        column_indices = {}
        if columns_to_import:
            for col_idx in columns_to_import:
                if isinstance(col_idx, int) and 0 <= col_idx < len(header_row):
                    col_name = header_row[col_idx].strip()
                    if col_name:
                        column_indices[col_name] = col_idx
        
        # Counter for the row limit
        row_count = 0
        
        for row_index, row_values in enumerate(csv_reader):
            # Check if we have reached the configured limit
            if max_results > 0 and row_count >= max_results:
                self.logger.info(f"List {self.list_instance.id}: Limit of {max_results} rows reached, stopping CSV import")
                break
                
            has_data_for_row = False
            
            # If we have specific columns to import, only use those
            if columns_to_import:
                for col_name, column_obj in columns_map.items():
                    # Check if this column is in our filtered list
                    if col_name in column_indices:
                        col_idx = column_indices[col_name]
                        if col_idx < len(row_values):
                            value = row_values[col_idx]
                            new_data_items.append(ListData(
                                list_id=self.list_instance.id,
                                row_id=row_index,
                                column_position=column_obj.position,
                                value=str(value) if value is not None else None
                            ))
                            has_data_for_row = True
            else:
                # Default behavior: import all columns
                for col_name, column_obj in columns_map.items():
                    col_idx = header_to_index.get(col_name)
                    if col_idx is not None and col_idx < len(row_values):
                        value = row_values[col_idx]
                        new_data_items.append(ListData(
                            list_id=self.list_instance.id,
                            row_id=row_index,
                            column_position=column_obj.position,
                            value=str(value) if value is not None else None
                        ))
                        has_data_for_row = True
            
            if has_data_for_row:
                rows_imported_count += 1
                row_count += 1
        
        if new_data_items:
            db.session.bulk_save_objects(new_data_items)
        self.logger.info(f"List {self.list_instance.id}: Prepared {len(new_data_items)} data cells for {rows_imported_count} rows from CSV data.")
        return rows_imported_count

    def _process_csv_data(self, csv_content_stream: io.StringIO) -> Optional[int]:
        # Get the CSV configuration
        csv_config = self.config.get('csv_config', {})
        
        # Strictly use the configured separator if it exists
        if 'separator' in csv_config and csv_config['separator']:
            separator = csv_config['separator']
            self.logger.info(f"List {self.list_instance.id}: Strictly using configured separator: '{separator}' (ASCII code: {ord(separator)})")
            csv_content_stream.seek(0)
            csv_reader_obj = csv.reader(csv_content_stream, delimiter=separator)
        else:
            # Only if no separator is configured, use automatic detection
            try:
                # Attempt to sniff the dialect
                dialect = csv.Sniffer().sniff(csv_content_stream.read(1024*5)) # Read more data for sniffing
                csv_content_stream.seek(0) # Rewind stream after sniffing
                csv_reader_obj = csv.reader(csv_content_stream, dialect)
                self.logger.info(f"List {self.list_instance.id}: CSV dialect sniffed: delimiter='{dialect.delimiter}', quotechar='{dialect.quotechar}'.") 
            except Exception as e:
                self.logger.warning(f"List {self.list_instance.id}: Could not sniff CSV dialect, falling back to default (comma, doublequote). Error: {e}")
                csv_content_stream.seek(0)
                csv_reader_obj = csv.reader(csv_content_stream) # Default dialect

        # Check if the file has a header or if we should use custom names
        has_header = csv_config.get('has_header', True)
        custom_column_names = csv_config.get('column_names', [])
        
        if has_header:
            # If the file has a header, use the first row as column names
            try:
                header_row = [h.strip() for h in next(csv_reader_obj)]
                self.logger.info(f"List {self.list_instance.id}: CSV header detected: {header_row}")
            except StopIteration:
                self.logger.info(f"List {self.list_instance.id}: CSV file is empty or has no header.")
                return 0
            
            if not any(header_row):
                self.logger.info(f"List {self.list_instance.id}: CSV header is empty.")
                return 0
        else:
            # If the file has no header, use custom column names
            try:
                # Read the first data row to determine the number of columns
                first_row = next(csv_reader_obj)
                # Go back to the beginning of the file for import
                csv_content_stream.seek(0)
                csv_reader_obj = csv.reader(csv_content_stream, delimiter=csv_config.get('separator', ','))
                
                # Determine column names
                if custom_column_names and len(custom_column_names) > 0:
                    # Use custom names if defined
                    header_row = []
                    for i in range(len(first_row)):
                        if i < len(custom_column_names) and custom_column_names[i]:
                            header_row.append(custom_column_names[i])
                        else:
                            header_row.append(f"Column{i+1}")
                    self.logger.info(f"List {self.list_instance.id}: Using custom column names: {header_row}")
                else:
                    # Generate default column names
                    header_row = [f"Column{i+1}" for i in range(len(first_row))]
                    self.logger.info(f"List {self.list_instance.id}: Generating default column names: {header_row}")
            except StopIteration:
                self.logger.info(f"List {self.list_instance.id}: CSV file is empty.")
                return 0

        if self.config.get('auto_create_columns', True):
            columns_map = self._create_columns_from_csv_header(header_row)
        else:
            columns_map = {col.name: col for col in self.list_instance.columns if col.name in header_row}

        if not columns_map:
            self.logger.error(f"List {self.list_instance.id}: No columns defined or created/matched for CSV import based on header.")
            return 0

        return self._import_rows_from_csv(csv_reader_obj, header_row, columns_map)

    def _import_data_from_url_source(self, force_update=False) -> Optional[int]:
        # If force_update is True, completely ignore the elapsed time check
        if force_update:
            self.logger.info(f"List {self.list_instance.id}: Force update requested, bypassing time check.")
        elif self.list_instance.last_update:
            # Handle timezone issue
            try:
                now = get_paris_now()
                last_update = self.list_instance.last_update
                
                # Check if last_update is timezone-aware
                if last_update.tzinfo is None:
                    # Convert last_update to UTC
                    import pytz
                    last_update = pytz.utc.localize(last_update)
                
                # Calculate time difference
                delta_seconds = (now - last_update).total_seconds()
                
                # Check if the update is too recent
                # If delta_seconds is negative, it means last_update is in the future,
                # which is likely due to a clock or timezone issue.
                # In this case, we force the update.
                if delta_seconds > 0 and delta_seconds < self.config.get('min_update_interval', 300):
                    self.logger.info(f"List {self.list_instance.id}: Update not forced and last update too recent ({delta_seconds} seconds). Skipping URL import.")
                    return None
            except Exception as e:
                self.logger.warning(f"List {self.list_instance.id}: Error checking update time: {e}, proceeding with update.")
                # In case of error, continue with the update

        url = self.config.get('url')
        if not url:
            self.logger.error(f"List {self.list_instance.id}: No URL configured for import.")
            raise ValueError("No URL configured for import.")

        self.logger.info(f"List {self.list_instance.id}: Importing data from URL: {url}")
        try:
            # Detect if the URL points to our own application
            from flask import current_app
            import os
            
            # Get the application domain from the SERVER_NAME environment variable
            # or from the Flask configuration
            app_domain = os.environ.get('SERVER_NAME') or current_app.config.get('SERVER_NAME', 'localhost')
            self.logger.info(f"List {self.list_instance.id}: Application domain detected: {app_domain}")
            
            # Add other possible internal domains
            internal_domains = ["localhost:5000", "web:5000", "nginx", app_domain]
            
            is_internal_url = False
            for domain in internal_domains:
                if domain in url:
                    is_internal_url = True
                    break
            
            if is_internal_url and "/public/json/" in url:
                self.logger.info(f"List {self.list_instance.id}: Detected an internal URL, using an alternative method")
                
                # Extract the public list identifier from the URL
                # Expected format: .../public/json/IDENTIFIER
                parts = url.split("/public/json/")
                if len(parts) == 2:
                    public_id = parts[1].split("?")[0].strip()
                    
                    # Use an alternative method to fetch the data
                    from .list import List
                    from flask import current_app
                    
                    # Find the list corresponding to this public identifier
                    list_obj = List.query.filter_by(public_access_token=public_id).first()
                    
                    if list_obj:
                        self.logger.info(f"List {self.list_instance.id}: Internal list found with ID {list_obj.id}")
                        # Directly generate the JSON data
                        json_data = list_obj.generate_public_json()
                        # Create a response object similar to requests'
                        class MockResponse:
                            def __init__(self, json_data):
                                self.json_data = json_data
                                self.headers = {"Content-Type": "application/json"}
                                self.status_code = 200
                            
                            def json(self):
                                return self.json_data
                            
                            def raise_for_status(self):
                                pass
                        
                        response = MockResponse(json_data)
                    else:
                        self.logger.error(f"List {self.list_instance.id}: Internal list with public ID {public_id} not found")
                        raise ValueError(f"List with public ID {public_id} not found")
                else:
                    self.logger.error(f"List {self.list_instance.id}: Invalid internal URL format: {url}")
                    raise ValueError(f"Invalid internal URL format: {url}")
            else:
                # Standard method for external URLs
                # Get parameters from environment variables or Flask configuration
                try:
                    # Get proxy variables from environment variables (priority)
                    import os
                    
                    # Get proxy variables (uppercase and lowercase)
                    http_proxy = os.environ.get('HTTP_PROXY', os.environ.get('http_proxy', ''))
                    https_proxy = os.environ.get('HTTPS_PROXY', os.environ.get('https_proxy', ''))
                    no_proxy = os.environ.get('NO_PROXY', os.environ.get('no_proxy', ''))
                    
                    # Get SSL verification variable
                    verify_ssl_env = os.environ.get('VERIFY_SSL', '')
                    
                    # If VERIFY_SSL environment variable is set, use it
                    # Otherwise, use Flask configuration
                    if verify_ssl_env:
                        verify_ssl = verify_ssl_env.lower() == 'true'
                        self.logger.info(f"List {self.list_instance.id}: Using environment variable VERIFY_SSL={verify_ssl_env}")
                    else:
                        # Fallback to Flask configuration
                        verify_ssl = current_app.config.get('VERIFY_SSL', 'false').lower() == 'true'
                        self.logger.info(f"List {self.list_instance.id}: Using Flask configuration VERIFY_SSL={verify_ssl}")
                    
                    # If proxy environment variables are empty, try via Flask configuration
                    if not http_proxy:
                        http_proxy = current_app.config.get('HTTP_PROXY', '')
                    if not https_proxy:
                        https_proxy = current_app.config.get('HTTPS_PROXY', '')
                    if not no_proxy:
                        no_proxy = current_app.config.get('NO_PROXY', '')
                        
                    # Detailed logs about the variables used
                    self.logger.info(f"List {self.list_instance.id}: Detected proxy variables - HTTP_PROXY={http_proxy}, HTTPS_PROXY={https_proxy}, NO_PROXY={no_proxy}")
                    
                except Exception as e:
                    # Fallback to default values in case of error
                    self.logger.warning(f"List {self.list_instance.id}: Error retrieving environment variables: {str(e)}")
                    verify_ssl = False
                    http_proxy = ''
                    https_proxy = ''
                
                # Configure the proxy only if variables are defined and not empty
                proxies = None
                if http_proxy or https_proxy:
                    proxies = {}
                    if http_proxy:
                        proxies['http'] = http_proxy
                    if https_proxy:
                        proxies['https'] = https_proxy
                    if no_proxy:
                        # Add NO_PROXY to the environment so requests picks it up
                        os.environ['NO_PROXY'] = no_proxy
                    self.logger.info(f"List {self.list_instance.id}: Using proxy: {proxies}")
                else:
                    self.logger.info(f"List {self.list_instance.id}: No proxy used")
                
                # Disable SSL warnings if necessary
                if not verify_ssl:
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    self.logger.info(f"List {self.list_instance.id}: SSL verification disabled, warnings suppressed")
                
                # Check if custom certificates are available
                ca_bundle = os.environ.get('REQUESTS_CA_BUNDLE', '')
                ssl_cert_file = os.environ.get('SSL_CERT_FILE', '')
                
                if ca_bundle:
                    self.logger.info(f"List {self.list_instance.id}: Using custom certificate bundle: {ca_bundle}")
                if ssl_cert_file:
                    self.logger.info(f"List {self.list_instance.id}: Using custom SSL certificate file: {ssl_cert_file}")
                
                # Download content with proxy (if defined) and SSL parameters
                self.logger.info(f"List {self.list_instance.id}: HTTP request to {url} with proxy={proxies} and verify_ssl={verify_ssl}")
                
                # Build the request parameters
                request_params = {
                    'timeout': self.config.get('timeout', 30),
                    'verify': verify_ssl
                }
                
                # Add proxy only if defined
                if proxies:
                    request_params['proxies'] = proxies
                
                # Add custom headers if configured
                headers = self.config.get('headers', {})
                if headers:
                    request_params['headers'] = headers
                    self.logger.info(f"List {self.list_instance.id}: Adding custom headers: {headers}")
                
                try:
                    # Execute the request with appropriate parameters
                    self.logger.info(f"List {self.list_instance.id}: Executing HTTP request with parameters: {request_params}")
                    response = requests.get(url, **request_params)
                    
                    # Detailed log of the response
                    self.logger.info(f"List {self.list_instance.id}: HTTP response received - Status: {response.status_code}, Content-Type: {response.headers.get('Content-Type', 'not specified')}")
                    
                    # Raise an exception for HTTP errors
                    response.raise_for_status()
                except requests.exceptions.SSLError as ssl_err:
                    self.logger.error(f"List {self.list_instance.id}: SSL error during request to {url}: {ssl_err}", exc_info=True)
                    self.logger.error(f"List {self.list_instance.id}: Check SSL certificate configuration or disable SSL verification with VERIFY_SSL=false")
                    raise
                except requests.exceptions.ProxyError as proxy_err:
                    self.logger.error(f"List {self.list_instance.id}: Proxy error during request to {url}: {proxy_err}", exc_info=True)
                    self.logger.error(f"List {self.list_instance.id}: Check proxy configuration: HTTP_PROXY={http_proxy}, HTTPS_PROXY={https_proxy}")
                    raise
                except requests.exceptions.RequestException as req_err:
                    self.logger.error(f"List {self.list_instance.id}: Error during request to {url}: {req_err}", exc_info=True)
                    raise

            content_type = response.headers.get('Content-Type', '').lower()
            # data_source_format from list config should be the primary determinant
            # Fallback to content-type or URL extension if not set or ambiguous
            list_format_config = self.list_instance.data_source_format.lower() 
            is_json = list_format_config == 'json' or ('json' in content_type and list_format_config != 'csv') or (url.endswith('.json') and list_format_config != 'csv')
            is_csv = list_format_config == 'csv' or ('csv' in content_type and list_format_config != 'json') or (url.endswith('.csv') and list_format_config != 'json')
            
            # If format is explicitly set, use it. Otherwise, try to infer.
            if not is_json and not is_csv:
                if 'json' in content_type or url.endswith('.json'): is_json = True
                elif 'csv' in content_type or url.endswith('.csv'): is_csv = True
                # Add more inferences if needed

            lines_imported = 0
            if is_json:
                self.logger.info(f"List {self.list_instance.id}: Processing as JSON from URL.")
                lines_imported = self._process_json_data(response.json())
            elif is_csv:
                self.logger.info(f"List {self.list_instance.id}: Processing as CSV from URL.")
                # response.text will use detected encoding or fallback. 
                # For more control, response.content and decode with chardet if issues arise.
                csv_stream = io.StringIO(response.text)
                lines_imported = self._process_csv_data(csv_stream)
            else:
                self.logger.warning(f"List {self.list_instance.id}: Could not determine data format from URL/headers (Content-Type: {content_type}, URL: {url}, ConfigFormat: {list_format_config}). Attempting JSON then CSV.")
                try:
                    self.logger.info(f"List {self.list_instance.id}: Attempting JSON parse as fallback.")
                    lines_imported = self._process_json_data(response.json())
                except (json.JSONDecodeError, ValueError) as e_json:
                    self.logger.warning(f"List {self.list_instance.id}: Fallback JSON parse failed ({e_json}), attempting CSV parse.")
                    try:
                        csv_stream = io.StringIO(response.text)
                        lines_imported = self._process_csv_data(csv_stream)
                    except Exception as e_csv:
                        self.logger.error(f"List {self.list_instance.id}: Fallback CSV parse also failed ({e_csv}). Cannot process data from URL.")
                        raise ValueError("Could not determine data format from URL and fallbacks failed.") from e_csv
            return lines_imported

        except requests.RequestException as e:
            # This exception is already handled in the try/except block above
            # But we keep it to catch any unhandled exceptions
            self.logger.error(f"List {self.list_instance.id}: Request failed for URL {url}: {e}", exc_info=True)
            raise
        except Exception as e:
            self.logger.error(f"List {self.list_instance.id}: Error processing data from URL {url}: {e}", exc_info=True)
            raise

    def _import_data_from_api_curl_source(self) -> Optional[int]:
        curl_command_template = self.config.get('curl_command')
        if not curl_command_template:
            self.logger.error(f"List {self.list_instance.id}: No cURL command configured.")
            raise ValueError("No cURL command configured for import.")

        # Basic placeholder replacement (e.g., for API keys, though secure handling is better)
        # For now, assume command is ready or simple placeholders are used.
        curl_command = curl_command_template # Potentially format with dynamic values if needed

        # Check if we are in an API curl JSON configuration
        api_type = self.config.get('api_type', '')
        format_config = self.config.get('format', '').lower()
        
        # Check if the list has a JSON configuration
        has_json_config = False
        if hasattr(self.list_instance, 'json_data_path') and self.list_instance.json_data_path:
            has_json_config = True
            self.logger.info(f"List {self.list_instance.id}: JSON configuration detected with json_data_path: {self.list_instance.json_data_path}")
        
        # Force JSON format if a JSON configuration is present
        if has_json_config:
            self.logger.info(f"List {self.list_instance.id}: Forcing format to JSON due to the presence of a JSON configuration")
            self.list_instance.data_source_format = 'json'
            
            # Also update the configuration
            config = self.list_instance.update_config
            config['format'] = 'json'
            config['is_json'] = True
            self.list_instance.update_config = config
            
            # Force immediate save
            db.session.commit()
        # Otherwise, use the configured format
        elif format_config:
            self.logger.info(f"List {self.list_instance.id}: Format configured in config: {format_config}")
            self.list_instance.data_source_format = format_config
            db.session.commit()
        
        # Check and log the current JSON configuration after update
        self.logger.info(f"List {self.list_instance.id}: Current JSON configuration - data_source_format: {self.list_instance.data_source_format}")
        if hasattr(self.list_instance, 'json_data_path'):
            self.logger.info(f"List {self.list_instance.id}: json_data_path configured: {self.list_instance.json_data_path}")
        
        # Check selected columns
        selected_columns = []
        if hasattr(self.list_instance, 'json_selected_columns') and self.list_instance.json_selected_columns:
            try:
                selected_columns = json.loads(self.list_instance.json_selected_columns)
                self.logger.info(f"List {self.list_instance.id}: json_selected_columns configured: {selected_columns}")
            except json.JSONDecodeError:
                self.logger.warning(f"List {self.list_instance.id}: Could not decode json_selected_columns: {self.list_instance.json_selected_columns}")

        # Ensure the configuration is saved before executing the command
        db.session.flush()

        # Détection d'un curl auto-bouclant sur l'API publique JSON du service
        from app.utils.internal_access import get_internal_list_data_from_public_json_url
        import re
        match = re.search(r"https?://[^\s'\"]+/public/json/[\w-]+", curl_command)
        if match:
            target_url = match.group(0)
            self.logger.info(f"[OPTIM] DataImporter: Detected curl command targeting public JSON endpoint: {target_url}")
            internal_data = get_internal_list_data_from_public_json_url(target_url)
            if internal_data is not None:
                output_data = json.dumps(internal_data)
                self.logger.info(f"[OPTIM] DataImporter: JSON data retrieved directly via ORM (no curl): {output_data[:200]}...")
                
                # Traiter les données JSON récupérées via ORM
                self.logger.info(f"List {self.list_instance.id}: Processing ORM-retrieved JSON data")
                try:
                    lines_imported = self._process_json_data(internal_data)
                    self.logger.info(f"List {self.list_instance.id}: ORM optimization successful, {lines_imported} lines imported")
                    return lines_imported
                except Exception as e:
                    self.logger.error(f"List {self.list_instance.id}: Error processing ORM-retrieved JSON data: {e}", exc_info=True)
                    raise
            else:
                # Fallback : exécution shell si ce n'est pas interne
                self.logger.info("[OPTIM] DataImporter: Target URL is not internal or data not found, executing curl as usual.")
                try:
                    process = subprocess.run(curl_command, shell=True, capture_output=True, text=True, check=False, timeout=self.config.get('timeout', 60))
                    if process.returncode != 0:
                        self.logger.error(f"List {self.list_instance.id}: cURL command failed with return code {process.returncode}: {process.stderr}")
                        raise ValueError(f"cURL command failed with return code {process.returncode}: {process.stderr}")
                    output_data = process.stdout
                    if not output_data:
                        self.logger.warning(f"List {self.list_instance.id}: cURL command returned empty output.")
                        return 0
                    output_sample = output_data[:500] + '...' if len(output_data) > 500 else output_data
                    self.logger.info(f"List {self.list_instance.id}: cURL output sample: {output_sample}")
                except Exception as e:
                    self.logger.error(f"List {self.list_instance.id}: Error executing cURL command: {e}", exc_info=True)
                    raise
        else:
            # Cas général : exécution shell normale
            self.logger.info("[OPTIM] DataImporter: No public JSON endpoint detected in curl_command, executing curl as usual.")
            try:
                process = subprocess.run(curl_command, shell=True, capture_output=True, text=True, check=False, timeout=self.config.get('timeout', 60))
                if process.returncode != 0:
                    self.logger.error(f"List {self.list_instance.id}: cURL command failed with return code {process.returncode}: {process.stderr}")
                    raise ValueError(f"cURL command failed with return code {process.returncode}: {process.stderr}")
                output_data = process.stdout
                if not output_data:
                    self.logger.warning(f"List {self.list_instance.id}: cURL command returned empty output.")
                    return 0
                output_sample = output_data[:500] + '...' if len(output_data) > 500 else output_data
                self.logger.info(f"List {self.list_instance.id}: cURL output sample: {output_sample}")
            except Exception as e:
                self.logger.error(f"List {self.list_instance.id}: Error executing cURL command: {e}", exc_info=True)
                raise

            # Use the same logic as for URL import
            # Determine the format based on configuration and content
            list_format_config = self.list_instance.data_source_format.lower() if self.list_instance.data_source_format else ''
            self.logger.info(f"List {self.list_instance.id}: Format configured in the database: {list_format_config}")
            
            # Check if the content looks like JSON
            is_json = False
            parsed_json = None
            try:
                # Try to parse as JSON
                parsed_json = json.loads(output_data)
                is_json = True
                self.logger.info(f"List {self.list_instance.id}: cURL output successfully parsed as JSON.")
                # Log the JSON structure for debugging
                if isinstance(parsed_json, dict):
                    self.logger.info(f"List {self.list_instance.id}: Available root JSON keys: {list(parsed_json.keys())}")
                elif isinstance(parsed_json, list) and len(parsed_json) > 0:
                    self.logger.info(f"List {self.list_instance.id}: Root JSON is a list of {len(parsed_json)} elements")
                    if isinstance(parsed_json[0], dict):
                        self.logger.info(f"List {self.list_instance.id}: First element (keys): {list(parsed_json[0].keys())}")
            except json.JSONDecodeError as e:
                self.logger.info(f"List {self.list_instance.id}: cURL output is not JSON: {e}")
            
            # Check if the content looks like CSV
            is_csv = False
            if not is_json:
                csv_stream = io.StringIO(output_data)
                try:
                    # Try to read as CSV
                    dialect = csv.Sniffer().sniff(csv_stream.read(1024))
                    csv_stream.seek(0)
                    is_csv = True
                    self.logger.info(f"List {self.list_instance.id}: cURL output appears to be CSV.")
                except csv.Error as e:
                    self.logger.warning(f"List {self.list_instance.id}: cURL output doesn't appear to be CSV either: {e}")
                    csv_stream.seek(0)
            
            # Prioritize the configured format
            if list_format_config == 'json':
                is_json = True
                is_csv = False
                self.logger.info(f"List {self.list_instance.id}: Format forced to JSON according to configuration")
            elif list_format_config == 'csv':
                # Check if a JSON configuration is present despite the configured CSV format
                if hasattr(self.list_instance, 'json_data_path') and self.list_instance.json_data_path:
                    self.logger.warning(f"List {self.list_instance.id}: Format configured as CSV but JSON configuration detected. Forcing to JSON.")
                    is_json = True
                    is_csv = False
                    # Update the configuration to avoid this issue in the future
                    self.list_instance.data_source_format = 'json'
                    config = self.list_instance.update_config
                    config['format'] = 'json'
                    config['is_json'] = True
                    self.list_instance.update_config = config
                    db.session.commit()
                else:
                    is_json = False
                    is_csv = True
            else:
                is_json = False
                is_csv = True
                self.logger.info(f"List {self.list_instance.id}: Format forced to CSV according to configuration")
        
        # Process data according to the determined format
        lines_imported = 0
        if is_json:
            self.logger.info(f"List {self.list_instance.id}: Processing cURL output as JSON")
            # Create an object similar to requests' response.json()
            class JsonResponse:
                def __init__(self, data):
                    self._data = data
                
                def json(self):
                    if isinstance(self._data, str):
                        return json.loads(self._data)
                    return self._data
            
            try:
                # Use the exact same approach as for URL
                self.logger.info(f"List {self.list_instance.id}: Creating a mock response.json() object for curl")
                response = JsonResponse(output_data)
                lines_imported = self._process_json_data(response.json())
                
                # Ensure we return the number of imported lines
                if lines_imported is not None:
                    self.logger.info(f"List {self.list_instance.id}: Successfully imported {lines_imported} lines from JSON data")
                    return lines_imported
                else:
                    self.logger.warning(f"List {self.list_instance.id}: No lines were imported from JSON data")
                    return 0
            except Exception as e:
                self.logger.error(f"List {self.list_instance.id}: Error processing JSON data: {e}", exc_info=True)
                raise
            
        elif is_csv:
            self.logger.info(f"List {self.list_instance.id}: Processing cURL output as CSV")
            try:
                csv_stream = io.StringIO(output_data)
                lines_imported = self._process_csv_data(csv_stream)
                self.logger.info(f"List {self.list_instance.id}: Successfully imported {lines_imported} lines from CSV data")
                return lines_imported
            except Exception as e:
                self.logger.error(f"List {self.list_instance.id}: Error processing CSV data: {e}", exc_info=True)
                raise
        else:
            self.logger.warning(f"List {self.list_instance.id}: Could not determine data format, trying JSON then CSV as fallback")
            try:
                self.logger.info(f"List {self.list_instance.id}: Attempting JSON parse")
                json_data = json.loads(output_data)
                lines_imported = self._process_json_data(json_data)
                if lines_imported is not None and lines_imported > 0:
                    self.logger.info(f"List {self.list_instance.id}: Successfully imported {lines_imported} lines from JSON data (fallback)")
                    return lines_imported
            except (json.JSONDecodeError, ValueError) as e_json:
                self.logger.warning(f"List {self.list_instance.id}: JSON parse failed ({e_json}), attempting CSV")
                try:
                    csv_stream = io.StringIO(output_data)
                    lines_imported = self._process_csv_data(csv_stream)
                    self.logger.info(f"List {self.list_instance.id}: Successfully imported {lines_imported} lines from CSV data (fallback)")
                    return lines_imported
                except Exception as e_csv:
                    self.logger.error(f"List {self.list_instance.id}: CSV parse also failed ({e_csv})")
                    raise ValueError("Could not determine data format") from e_csv