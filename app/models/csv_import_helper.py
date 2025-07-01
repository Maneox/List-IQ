#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV import helper module for the List model
"""
import csv
import io
import json
from typing import Dict, Any, List
from flask import current_app
from .list import ListColumn, ListData
from .. import db
from sqlalchemy import text

def read_csv_with_config(file_obj, csv_config=None, list_obj=None):
    """
    Reads a CSV file with the specified configuration
    
    Args:
        file_obj: The CSV data stream
        csv_config: The CSV configuration
        list_obj: The associated List object
        
    Returns:
        A DictReader or SimpleTextReader object to read the CSV data
    """
    # Default parameters
    delimiter = ','
    has_headers = True
    
    # Use configuration if available
    if csv_config:
        # Get the separator from the configuration
        delimiter_from_config = csv_config.get('separator', ',')
        
        # Check that the separator is a single character
        if len(delimiter_from_config) != 1:
            current_app.logger.warning(f"The separator '{delimiter_from_config}' is not a single character, using default separator ','")
        else:
            delimiter = delimiter_from_config
            
        has_headers = csv_config.get('has_header', True)
    
    # Read the first lines for detection
    file_obj.seek(0)
    first_line = file_obj.readline().strip()
    file_obj.seek(0)
    
    # Check if it's a simple text file (one value per line without a delimiter)
    is_simple_text = False
    if not has_headers and delimiter not in first_line and first_line:
        is_simple_text = True
        current_app.logger.info(f"Detected a simple text file (one value per line without a delimiter)")
        
        # For simple text files, use custom column names
        if csv_config and 'column_names' in csv_config and csv_config['column_names']:
            column_name = csv_config['column_names'][0]
            current_app.logger.info(f"Simple text file: using custom column name '{column_name}'")
            
            # Reset the file to read from the beginning
            file_obj.seek(0)
            
            # Create a custom reader for simple text files
            class SimpleTextReader:
                """Custom reader for simple text files (one value per line)"""
                def __init__(self, file_obj, column_name):
                    self.file_obj = file_obj
                    self.fieldnames = [column_name]
                    self.line_num = 0
                    current_app.logger.info(f"SimpleTextReader initialized with column name: {column_name}")
                    
                def __iter__(self):
                    return self
                    
                def __next__(self):
                    line = self.file_obj.readline()
                    if not line:
                        raise StopIteration
                        
                    self.line_num += 1
                    line = line.strip()
                    if line:
                        return {self.fieldnames[0]: line}
                    else:
                        return {self.fieldnames[0]: ''}
            
            return SimpleTextReader(file_obj, column_name)
        else:
            # Use a default column name
            column_name = "Column1"
            if list_obj and list_obj.columns and len(list_obj.columns) > 0:
                # Use the name of the first existing column
                column_name = list_obj.columns[0].name
            
            current_app.logger.info(f"Simple text file: using default column name '{column_name}'")
            file_obj.seek(0)
            return SimpleTextReader(file_obj, column_name)
    
    # Try to detect the CSV dialect
    try:
        second_line = file_obj.readline()
        file_obj.seek(0)
        dialect = csv.Sniffer().sniff(first_line + '\n' + second_line)
        
        # If a delimiter is specified in the configuration, use it
        if csv_config and 'separator' in csv_config:
            delimiter = csv_config['separator']
        else:
            delimiter = dialect.delimiter
            
        current_app.logger.info(f"CSV dialect detected: delimiter='{delimiter}', quotechar='{dialect.quotechar}'")
    except Exception as e:
        current_app.logger.warning(f"Could not detect CSV dialect: {str(e)}. Using default settings.")
    
    # Generate column names if no headers
    fieldnames = None
    if not has_headers:
        # Read the first line to determine the number of columns
        file_obj.seek(0)
        first_row = next(csv.reader([file_obj.readline()], delimiter=delimiter))
        file_obj.seek(0)
        
        # Generate column names
        fieldnames = [f"Column{i+1}" for i in range(len(first_row))]
        
        # Use custom column names if available
        if csv_config and 'column_names' in csv_config and csv_config['column_names']:
            custom_names = csv_config['column_names']
            for i in range(min(len(fieldnames), len(custom_names))):
                if custom_names[i]:
                    fieldnames[i] = custom_names[i]
        
        current_app.logger.info(f"No headers, using column names: {fieldnames}")
    
    # Create the CSV reader
    if has_headers:
        return csv.DictReader(file_obj, delimiter=delimiter)
    else:
        return csv.DictReader(file_obj, fieldnames=fieldnames, delimiter=delimiter)


def import_ip_file(list_obj, content, csv_config):
    """
    Special function to import a file of IP addresses
    
    Args:
        list_obj: The List object to import data into
        content: The file content
        csv_config: The CSV configuration
        
    Returns:
        The number of imported rows
    """
    current_app.logger.info("Using special method to import IP address file")
    
    # Get the custom column name if defined
    column_name = "IP"
    if 'column_names' in csv_config and csv_config['column_names'] and csv_config['column_names'][0]:
        column_name = csv_config['column_names'][0]
    
    current_app.logger.info(f"Using column name '{column_name}' for IP addresses")
    
    # Check if the column already exists
    existing_column = db.session.query(ListColumn).filter(
        ListColumn.list_id == list_obj.id,
        ListColumn.name == column_name
    ).first()
    
    # Create the column if it doesn't exist
    if not existing_column and list_obj.auto_create_columns:
        # Determine the column type
        col_type = 'text'
        if 'column_types' in csv_config and '0' in csv_config['column_types']:
            col_type = csv_config['column_types']['0']
        
        # Create the column
        new_column = ListColumn(
            list_id=list_obj.id,
            name=column_name,
            position=0,  # Always position 0 for IP address files
            column_type=col_type
        )
        db.session.add(new_column)
        db.session.commit()
        current_app.logger.info(f"Column created for IP addresses: {column_name} (type: {col_type}, position: 0)")
        column = new_column
    else:
        column = existing_column
    
    # Delete existing data
    try:
        count_before = db.session.query(ListData).filter(ListData.list_id == list_obj.id).count()
        current_app.logger.info(f"Deleting existing data: {count_before} rows found")
        
        db.session.query(ListData).filter(ListData.list_id == list_obj.id).delete()
        db.session.commit()
        current_app.logger.info("Existing data deleted successfully")
    except Exception as e:
        current_app.logger.error(f"Error while deleting existing data: {str(e)}")
        db.session.rollback()
    
    # Import IP addresses line by line
    lines = content.strip().split('\n')
    row_count = 0
    connection = db.engine.connect()
    transaction = connection.begin()
    
    try:
        for line in lines:
            ip = line.strip()
            if ip:  # Ignore empty lines
                row_id = row_count + 1
                
                # Debugging to understand the retrieved values
                if row_count < 3:  # Limit the number of logs to avoid overload
                    current_app.logger.info(f"Line {row_id}, IP address: '{ip}'")
                
                # Insert directly into the database
                sql = text("""
                INSERT INTO list_data (list_id, row_id, column_position, value, created_at, updated_at)
                VALUES (:list_id, :row_id, :column_position, :value, NOW(), NOW())
                ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = NOW()
                """)
                
                connection.execute(
                    sql, 
                    {
                        'list_id': list_obj.id,
                        'row_id': row_id,
                        'column_position': 0,  # Always position 0 for IP address files
                        'value': ip
                    }
                )
                
                row_count += 1
                
                # Progress log
                if row_count % 100 == 0:
                    current_app.logger.info(f"{row_count} rows processed")
        
        # Commit the transaction
        transaction.commit()
        
        # Check the total number of entries after import
        count_sql = text("SELECT COUNT(*) FROM list_data WHERE list_id = :list_id")
        count_result = connection.execute(count_sql, {'list_id': list_obj.id}).scalar()
        
        current_app.logger.info(f"Import finished. {row_count} rows imported, {count_result} entries in the database")
        return row_count
    
    except Exception as e:
        current_app.logger.error(f"Error during IP address import: {str(e)}")
        
        # Rollback the transaction in case of error
        if transaction.is_active:
            transaction.rollback()
        
        # Reraise the exception for upstream error handling
        raise
    finally:
        # Close the connection
        connection.close()

def import_csv_data(list_obj, stream, config: Dict[str, Any]) -> int:
    """
    Imports CSV data into a list
    
    Args:
        list_obj: The List object to import data into
        stream: The CSV data stream
        config: The import configuration
        
    Returns:
        The number of imported rows
    """
    try:
        # Configure CSV parameters
        csv_config = config.get('csv_config', {})
        
        # Get the separator and check if it's valid
        delimiter_from_config = csv_config.get('delimiter', csv_config.get('separator', ','))
        
        # Check that the separator is a single character
        if len(delimiter_from_config) != 1:
            current_app.logger.warning(f"The separator '{delimiter_from_config}' is not a single character, using default separator ','")
            delimiter = ','
        else:
            delimiter = delimiter_from_config
            
        # Log the separator used for debugging
        current_app.logger.info(f"Separator used for CSV import: '{delimiter}' (ASCII code: {ord(delimiter)})")
            
        has_headers = csv_config.get('has_headers', csv_config.get('has_header', True))
        columns_to_import = csv_config.get('columns_to_import', [])
        
        # Check if we have an IP address file
        stream.seek(0)
        content = stream.read()
        stream.seek(0)
        
        # Special detection for IP address files - only if no specific separator is configured
        is_ip_file = False
        
        # Only perform IP address detection if the default separator (comma) is used
        # or if the file is treated as a simple text file (no separator)
        if delimiter == ',' or not csv_config.get('separator'):
            lines = content.strip().split('\n')
            if len(lines) > 0:
                first_line = lines[0].strip()
                # Check if the first line looks like an IP address
                if '.' in first_line and not has_headers and len(first_line.split('.')) == 4:
                    # Check if all parts are digits
                    parts = first_line.split('.')
                    if all(part.isdigit() for part in parts):
                        is_ip_file = True
                        current_app.logger.info(f"Detected an IP address file, special handling")
        
        # If it is an IP address file AND no specific separator is configured, special handling
        if is_ip_file and delimiter == ',':
            return import_ip_file(list_obj, content, csv_config)
        
        # If a specific separator is configured (like tab), use that separator even for IP addresses
        if is_ip_file and delimiter != ',':
            current_app.logger.info(f"IP address file detected but a specific separator '{delimiter}' is configured. Using standard CSV processing.")
        
        current_app.logger.info(f"CSV import with delimiter='{delimiter}', headers={has_headers}, columns to import={columns_to_import}")
        
        # Reset the file cursor
        stream.seek(0)
        
        # Read the first lines to determine the headers
        csv_reader = read_csv_with_config(stream, csv_config, list_obj)
        
        # Convert column indices to integers if necessary
        columns_to_import = [int(idx) if isinstance(idx, str) and idx.isdigit() else idx for idx in columns_to_import]
        current_app.logger.info(f"Column indices after conversion: {columns_to_import}")
        
        # Check that indices are in the valid range
        valid_indices = [idx for idx in columns_to_import if isinstance(idx, int) and 0 <= idx < len(csv_reader.fieldnames)]
        if len(valid_indices) != len(columns_to_import):
            invalid_indices = [idx for idx in columns_to_import if not isinstance(idx, int) or idx < 0 or idx >= len(csv_reader.fieldnames)]
            current_app.logger.warning(f"Invalid column indices ignored: {invalid_indices}")
        
        # Filter columns based on selected indices
        if valid_indices:
            columns_to_use = [csv_reader.fieldnames[i] for i in valid_indices]
        else:
            columns_to_use = csv_reader.fieldnames
        
        current_app.logger.info(f"Columns to use: {columns_to_use}")
        
        # Get existing columns
        columns = {col.name: col for col in list_obj.columns}
        
        # Check that all CSV columns match
        csv_columns = set(columns_to_use)
        list_columns = set(columns.keys())
        
        # Special detection for simple text files (one value per line)
        # or IP address files
        is_simple_text_file = False
        # Reset cursor to read the first line
        stream.seek(0)
        first_line = stream.readline().strip()
        stream.seek(0)
        
        # Check if it is an IP address file
        is_ip_file = csv_config.get('is_ip_file', False) if csv_config else False
        
        if is_ip_file or (not has_headers and len(csv_reader.fieldnames) == 1 and delimiter not in first_line and first_line):
            is_simple_text_file = True
            current_app.logger.info(f"Detected a simple text file (one value per line)")
            
            # For simple text files, use custom column names
            if 'column_names' in csv_config and csv_config['column_names']:
                # Replace column names with those defined in the configuration
                custom_column_name = csv_config['column_names'][0]
                current_app.logger.info(f"Using custom column name for simple text file: {custom_column_name}")
                
                # Check if the column already exists
                existing_column = db.session.query(ListColumn).filter(
                    ListColumn.list_id == list_obj.id,
                    ListColumn.name == custom_column_name
                ).first()
                
                if not existing_column and list_obj.auto_create_columns:
                    # Create the column with the custom name
                    col_type = 'text'  # Default type
                    if 'column_types' in csv_config and '0' in csv_config['column_types']:
                        col_type = csv_config['column_types']['0']
                        
                    new_column = ListColumn(
                        list_id=list_obj.id,
                        name=custom_column_name,
                        position=0,  # Always position 0 for simple text files
                        column_type=col_type
                    )
                    db.session.add(new_column)
                    db.session.commit()
                    current_app.logger.info(f"Column created for simple text file: {custom_column_name} (type: {col_type}, position: 0)")
        
        if not csv_columns.issubset(list_columns):
            missing_columns = csv_columns - list_columns
            if list_obj.auto_create_columns:
                current_app.logger.info(f"Automatically creating missing columns: {missing_columns}")
                
                # Create missing columns
                for col_name in missing_columns:
                    # Determine the column index
                    col_index = csv_reader.fieldnames.index(col_name)
                    
                    # Determine the column type from the CSV configuration if available
                    col_type = 'text'  # Default type
                    if 'column_types' in csv_config and str(col_index) in csv_config['column_types']:
                        col_type = csv_config['column_types'][str(col_index)]
                    
                    # For simple text files, use position 0
                    if is_simple_text_file:
                        col_index = 0
                        current_app.logger.info(f"Simple text file: using position 0 for column '{col_name}'")
                    
                    # Create the column
                    new_column = ListColumn(
                        list_id=list_obj.id,
                        name=col_name,
                        position=col_index,
                        column_type=col_type
                    )
                    db.session.add(new_column)
                    current_app.logger.info(f"Column created: {col_name} (type: {col_type}, position: {col_index})")
                
                # Commit to save new columns
                db.session.commit()
                
                # Update the columns dictionary
                columns = {col.name: col for col in list_obj.columns}
            else:
                raise ValueError(f"Invalid columns in CSV: {', '.join(missing_columns)}")
        
        # Option to remove columns that are no longer present in the data source
        remove_unused_columns = csv_config.get('remove_unused_columns', True)
        current_app.logger.info(f"Remove unused columns: {remove_unused_columns}")
        
        if remove_unused_columns:
            # Identify columns that are no longer present in the data source
            unused_columns = list_columns - csv_columns
            if unused_columns:
                current_app.logger.info(f"Unused columns to be deleted: {unused_columns}")
                for col_name in unused_columns:
                    if col_name in columns:
                        current_app.logger.info(f"Deleting column: {col_name}")
                        # Delete the column
                        db.session.delete(columns[col_name])
                
                # Commit to save deletions
                db.session.commit()
                
                # Update the columns dictionary
                columns = {col.name: col for col in list_obj.columns}
        
        # Filter columns to include only the selected ones
        filtered_columns = {name: col for name, col in columns.items() if name in columns_to_use}
        current_app.logger.info(f"Filtered columns for import: {list(filtered_columns.keys())}")
        
        # Check that we have filtered columns
        if not filtered_columns and columns_to_use:
            current_app.logger.warning(f"No filtered columns found despite having columns to use: {columns_to_use}")
            current_app.logger.warning(f"Available columns: {list(columns.keys())}")
            
            # It's possible that the column names do not match exactly
            # Let's try to match columns by position instead of by name
            if len(columns) == len(columns_to_use) == 1:
                # Special case: only one column on each side, let's use it directly
                col_name = list(columns.keys())[0]
                col = list(columns.values())[0]
                filtered_columns = {columns_to_use[0]: col}
                current_app.logger.info(f"Using column '{col_name}' (position {col.position}) for '{columns_to_use[0]}'")
        
        # Clear existing data before import
        try:
            # Count rows before deletion
            count_before = db.session.query(ListData).filter(ListData.list_id == list_obj.id).count()
            current_app.logger.info(f"Deleting existing data: {count_before} rows found")
            
            # Delete the data
            db.session.query(ListData).filter(ListData.list_id == list_obj.id).delete()
            db.session.commit()
            
            # Check that the data has been deleted
            count_after = db.session.query(ListData).filter(ListData.list_id == list_obj.id).count()
            current_app.logger.info(f"After deletion: {count_after} rows remaining")
        except Exception as e:
            current_app.logger.error(f"Error while deleting existing data: {str(e)}")
            db.session.rollback()
        
        # Reset file cursor for data import
        stream.seek(0)
        
        # Determine if it's a simple text file (one value per line without a delimiter)
        # or an IP address file
        is_simple_text = False
        is_ip_file = csv_config.get('is_ip_file', False) if csv_config else False
        
        if is_ip_file or (not has_headers and delimiter not in first_line and first_line):
            is_simple_text = True
            current_app.logger.info(f"Detected a simple text or IP address file (one value per line without a delimiter)")
            
            # Reset the file to read from the beginning
            stream.seek(0)
            
            # Use our custom reader for simple text files
            column_name = csv_reader.fieldnames[0]
            if 'column_names' in csv_config and csv_config['column_names']:
                # Use the custom column name if it is defined
                column_name = csv_config['column_names'][0]
                current_app.logger.info(f"Using custom column name: {column_name}")
                
            # Check if the column already exists in the list
            existing_columns = {col.name: col for col in db.session.query(ListColumn).filter(ListColumn.list_id == list_obj.id).all()}
            if column_name not in existing_columns and list_obj.auto_create_columns:
                # Create the column with the custom name
                col_type = 'text'  # Default type
                if 'column_types' in csv_config and '0' in csv_config['column_types']:
                    col_type = csv_config['column_types']['0']
                    
                new_column = ListColumn(
                    list_id=list_obj.id,
                    name=column_name,
                    position=0,  # Always position 0 for simple text files
                    column_type=col_type
                )
                db.session.add(new_column)
                db.session.commit()
                current_app.logger.info(f"Column created for simple text file: {column_name} (type: {col_type}, position: 0)")
                
                # Refresh columns after creation
                filtered_columns = {column_name: new_column}
                
            # Create a custom reader for simple text files
            class SimpleTextReader:
                """Custom reader for simple text files (one value per line)"""
                def __init__(self, file_obj, column_name):
                    self.file_obj = file_obj
                    self.fieldnames = [column_name]
                    self.line_num = 0
                    current_app.logger.info(f"SimpleTextReader initialized with column name: {column_name}")
                    
                def __iter__(self):
                    return self
                    
                def __next__(self):
                    line = self.file_obj.readline()
                    if not line:
                        raise StopIteration
                        
                    self.line_num += 1
                    line = line.strip()
                    if line:
                        return {self.fieldnames[0]: line}
                    else:
                        return {self.fieldnames[0]: ''}
            
            csv_reader = SimpleTextReader(stream, column_name)
        elif has_headers:
            # Skip the first line if it contains headers
            csv_reader = csv.DictReader(stream, delimiter=delimiter)
        else:
            csv_reader = csv.DictReader(stream, fieldnames=fieldnames, delimiter=delimiter)
        
        # Import data row by row
        row_count = 0
        connection = db.engine.connect()
        transaction = connection.begin()
        
        try:
            for row in csv_reader:
                try:
                    row_id = row_count + 1  # Unique row ID
                    
                    # Insert each cell individually
                    for col_name, column in filtered_columns.items():
                        # Get the column value from the CSV row
                        value = row.get(col_name, '')
                        
                        # Debugging to understand the retrieved values
                        if row_count < 3:  # Limit the number of logs to avoid overload
                            current_app.logger.info(f"Row {row_id}, column '{col_name}' (position {column.position}): value='{value}'")
                            current_app.logger.info(f"Full row content: {row}")
                        
                        # Set the value based on the column type
                        if column.column_type == 'number':
                            try:
                                # Try to convert to number
                                value = float(value) if value else None
                            except (ValueError, TypeError):
                                # If conversion fails, use None
                                value = None
                        
                        # For simple text files, force position to 0
                        column_position = column.position
                        if is_simple_text:
                            column_position = 0
                            current_app.logger.info(f"Simple text file: using position 0 for column '{column.name}'")
                        
                        # Insert directly into the database
                        sql = text("""
                        INSERT INTO list_data (list_id, row_id, column_position, value, created_at, updated_at)
                        VALUES (:list_id, :row_id, :column_position, :value, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = NOW()
                        """)
                        
                        connection.execute(
                            sql, 
                            {
                                'list_id': list_obj.id,
                                'row_id': row_id,
                                'column_position': column_position,
                                'value': str(value) if value is not None else ''
                            }
                        )
                    
                    row_count += 1
                    
                    # Progress log
                    if row_count % 100 == 0:
                        current_app.logger.info(f"{row_count} rows processed")
                        
                except Exception as e:
                    current_app.logger.error(f"Error processing row {row_count + 1}: {str(e)}")
                    # Continue with the next row
            
            # Commit the transaction
            transaction.commit()
            
            # Check the total number of entries after import
            count_sql = text("SELECT COUNT(*) FROM list_data WHERE list_id = :list_id")
            count_result = connection.execute(count_sql, {'list_id': list_obj.id}).scalar()
            
            current_app.logger.info(f"Import finished. {row_count} rows imported, {count_result} entries in the database")
            return row_count
            
        except Exception as e:
            current_app.logger.error(f"Error during CSV import: {str(e)}")
            
            # Rollback the transaction in case of error
            if transaction.is_active:
                transaction.rollback()
            
            # Reraise the exception for upstream error handling
            raise
        finally:
            # Close the connection
            connection.close()
            
    except Exception as e:
        current_app.logger.error(f"Error during CSV import: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        raise