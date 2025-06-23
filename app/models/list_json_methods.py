"""
This file contains the methods to be added to the List model for JSON configuration.
"""

def get_json_selected_columns(self):
    """Getter for json_selected_columns that converts the JSON string to a list"""
    if not self.json_selected_columns:
        return []
    try:
        import json
        from flask import current_app
        return json.loads(self.json_selected_columns)
    except (json.JSONDecodeError, TypeError):
        current_app.logger.error(f"Error decoding json_selected_columns: {self.json_selected_columns}")
        return []
        
def set_json_selected_columns(self, columns):
    """Setter for json_selected_columns that converts the list to a JSON string"""
    import json
    if columns is None:
        self.json_selected_columns = None
    else:
        self.json_selected_columns = json.dumps(columns)
        
def needs_json_config(self):
    """Checks if the list requires JSON configuration"""
    config = self.update_config
    
    # Check if it's a Curl API type list
    is_curl_api = (self.update_type == 'automatic' and 
                  config and 
                  config.get('source') == 'api' and 
                  config.get('api_type') == 'curl' and
                  self.json_config_status != 'configured')
    
    # Check if it's a JSON type list via URL
    is_json_url = (self.update_type == 'automatic' and 
                  config and 
                  config.get('source') == 'url' and 
                  (config.get('is_json') == True or config.get('format') == 'json') and
                  self.json_config_status != 'configured')
    
    return is_curl_api or is_json_url