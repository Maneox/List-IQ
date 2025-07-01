import os
import json
import csv
import logging
from flask import current_app
from ..models.list import List
from ..database import db

logger = logging.getLogger(__name__)

def update_public_files(list_obj):
    """
    Updates the public CSV and JSON files for a given list
    
    Args:
        list_obj: The list object to update (can be an ID or a List instance)
    
    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        # If list_obj is an ID, load the list from the database
        if isinstance(list_obj, int):
            list_obj = db.session.get(List, list_obj)
        
        # If list_obj is still not a List instance, log an error and return
        if not isinstance(list_obj, List):
            logger.error(f"Invalid list object provided to update_public_files: {type(list_obj)}")
            return False
            
        # Check if public files are enabled
        if not list_obj.public_csv_enabled and not list_obj.public_json_enabled:
            return True
        
        # Create the public files directory if it does not exist
        public_files_dir = os.path.join(current_app.root_path, 'public_files')
        os.makedirs(public_files_dir, exist_ok=True)
        
        # Refresh the object to ensure we have the latest data
        db.session.refresh(list_obj)
        
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
                # Use the list's generate_public_json method to ensure consistent column filtering
                # This will exclude only the primary key column and maintain column order
                filtered_data = list_obj.generate_public_json()
                json.dump(filtered_data, json_file, ensure_ascii=False, indent=2)
                
            logger.info(f"Public JSON file updated for list {list_obj.id}")
        
        return True
    except Exception as e:
        logger.error(f"Error updating public files for list {list_obj.id}: {str(e)}")
        return False