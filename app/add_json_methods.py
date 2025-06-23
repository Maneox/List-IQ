"""
Temporary script to add JSON configuration methods to the List model.
This script must be executed before starting the application.
"""

import json
from flask import current_app
from models.list import List

# Add the get_json_selected_columns property
def get_json_selected_columns(self):
    """Getter for json_selected_columns that converts the JSON string to a list"""
    if not self.json_selected_columns:
        return []
    try:
        return json.loads(self.json_selected_columns)
    except (json.JSONDecodeError, TypeError):
        current_app.logger.error(f"Error decoding json_selected_columns: {self.json_selected_columns}")
        return []

# Add the set_json_selected_columns method
def set_json_selected_columns(self, columns):
    """Setter for json_selected_columns that converts the list to a JSON string"""
    if columns is None:
        self.json_selected_columns = None
    else:
        self.json_selected_columns = json.dumps(columns)

# Add the needs_json_config method
def needs_json_config(self):
    """Checks if the list requires JSON configuration"""
    config = self.update_config
    return (self.update_type == 'automatic' and 
            config and 
            config.get('source') == 'api' and 
            config.get('api_type') == 'curl' and
            self.json_config_status != 'configured')

# Add the methods to the List model
List.get_json_selected_columns = property(get_json_selected_columns)
List.set_json_selected_columns = set_json_selected_columns
List.needs_json_config = needs_json_config

print("JSON configuration methods added to the List model successfully!")