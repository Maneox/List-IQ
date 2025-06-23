from flask import Blueprint, render_template

help_bp = Blueprint('help_bp', __name__)

@help_bp.route('/automatic-lists-guide')
def automatic_lists_guide():
    """Displays the user guide for automatic lists."""
    return render_template('help/automatic_lists_guide.html')

@help_bp.route('/python-api-help')
def python_api_help():
    """Displays the help page for Python API scripts."""
    return render_template('help/python_api_help.html')

@help_bp.route('/curl-api-help')
def curl_api_help():
    """Displays the help page for Curl API commands."""
    return render_template('help/curl_api_help.html')

@help_bp.route('/json-config-help')
def json_config_help():
    """Displays the help page for JSON configuration."""
    return render_template('help/json_config_help.html')