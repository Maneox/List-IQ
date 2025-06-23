import os
import json
import csv
import logging
from flask import current_app
from models.list import List

logger = logging.getLogger(__name__)

def update_public_files(list_obj):
    """
    Updates the public CSV and JSON files for a given list
    
    Args:
        list_obj: The list object to update
    
    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        # Check if public files are enabled
        if not list_obj.public_csv_enabled and not list_obj.public_json_enabled:
            return True
        
        # Create the public files directory if it does not exist
        public_files_dir = os.path.join(current_app.root_path, 'public_files')
        os.makedirs(public_files_dir, exist_ok=True)
        
        # Get the list's data
        data = list_obj.get_data()
        
        # Generate the CSV file if enabled
        if list_obj.public_csv_enabled:
            csv_path = os.path.join(public_files_dir, f'list_{list_obj.id}.csv')
            with open(csv_path, 'w', newline='', encoding='utf-8') as csv_file:
                # Create the CSV writer
                writer = csv.writer(csv_file)
                
                # Write the header
                headers = [col.name for col in list_obj.columns]
                writer.writerow(headers)
                
                # Write the data
                for row in data:
                    writer.writerow([row.get(header, '') for header in headers])
                    
            logger.info(f"Public CSV file updated for list {list_obj.id}")
        
        # Generate the JSON file if enabled
        if list_obj.public_json_enabled:
            json_path = os.path.join(public_files_dir, f'list_{list_obj.id}.json')
            with open(json_path, 'w', encoding='utf-8') as json_file:
                # Filter the 'id' field from the data for JSON export
                filtered_data = []
                for row in data:
                    filtered_row = {k: v for k, v in row.items() if k != 'id'}
                    filtered_data.append(filtered_row)
                
                json.dump(filtered_data, json_file, ensure_ascii=False, indent=2)
                
            logger.info(f"Public JSON file updated for list {list_obj.id}")
        
        return True
    except Exception as e:
        logger.error(f"Error updating public files for list {list_obj.id}: {str(e)}")
        return False