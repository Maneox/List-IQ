from flask import Blueprint, jsonify, send_file, current_app, request, abort, session
from models.list import List
from database import db
import io
import csv
import json
import uuid
import secrets
import os
import ipaddress
from datetime import datetime

# Import timezone utilities
from utils.timezone_utils import get_paris_now, format_datetime
from functools import wraps
from routes.decorators import public_route

public_files_bp = Blueprint('public_files_bp', __name__)

@public_files_bp.route('/favicon.ico')
@public_route
def favicon():
    """Serve the favicon.ico from the static folder"""
    try:
        # First, try to serve from the root
        favicon_path = os.path.join(current_app.root_path, 'favicon.ico')
        if os.path.exists(favicon_path):
            return send_file(favicon_path, mimetype='image/x-icon')
            
        # Then, try from the static folder
        favicon_path = os.path.join(current_app.root_path, 'static', 'favicon.ico')
        if os.path.exists(favicon_path):
            return send_file(favicon_path, mimetype='image/x-icon')
            
        # Finally, try from the static/images folder
        favicon_path = os.path.join(current_app.root_path, 'static', 'images', 'favicon.ico')
        if os.path.exists(favicon_path):
            return send_file(favicon_path, mimetype='image/x-icon')
            
        # If no favicon is found, return a 404 error
        current_app.logger.warning("Favicon.ico not found in standard locations")
        abort(404)
    except Exception as e:
        current_app.logger.error(f"Error accessing favicon: {str(e)}")
        abort(500)

def check_ip_access(list_obj):
    """
    Checks if the client's IP is allowed to access the list
    """
    if not list_obj.ip_restriction_enabled:
        return True
        
    # Get the client IP, considering different possible configurations
    client_ip = request.remote_addr
    
    # Check if the application is behind a proxy
    if request.headers.get('X-Forwarded-For'):
        client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    
    # Check if the IP is allowed
    if not list_obj.allowed_ips:
        return False
        
    try:
        allowed_ips = json.loads(list_obj.allowed_ips)
        if client_ip in allowed_ips:
            return True
            
        # Check if the IP is in an authorized subnet
        client_ip_obj = ipaddress.ip_address(client_ip)
        
        for allowed_ip in allowed_ips:
            if '/' in allowed_ip:  # It's a CIDR subnet
                try:
                    network = ipaddress.ip_network(allowed_ip, strict=False)
                    if client_ip_obj in network:
                        return True
                except ValueError:
                    continue
    except (json.JSONDecodeError, ValueError):
        current_app.logger.error(f"Invalid allowed IPs format for list {list_obj.id}")
        return False
        
    return False

def generate_access_token():
    """
    Generates a unique access token for public files
    """
    return secrets.token_urlsafe(32)

@public_files_bp.route('/public/csv/<token>')
@public_route
def get_public_csv(token):
    """
    Public access to a list's CSV file with token and IP restriction checks
    """
    # Find the list by its access token
    list_obj = List.query.filter_by(public_access_token=token).first()
    
    if not list_obj or not list_obj.public_csv_enabled:
        abort(404)
    
    # Check IP restrictions
    if list_obj.ip_restriction_enabled and not check_ip_access(list_obj):
        current_app.logger.warning(f"Unauthorized access attempt to the public CSV file of list {list_obj.id} from {request.remote_addr}")
        # Store IP error information in the session
        session['ip_error_info'] = {
            'detected_ip': request.remote_addr,
            'original_header': request.headers.get('X-Forwarded-For', request.remote_addr),
            'allowed_ips': list_obj.allowed_ips
        }
        abort(403)
    
    try:
        # Check if a pre-generated CSV file exists
        csv_path = os.path.join(current_app.root_path, 'public_files', f'list_{list_obj.id}.csv')
        if os.path.exists(csv_path):
            # Serve the pre-generated file
            return send_file(
                csv_path,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'{list_obj.name}_{get_paris_now().strftime("%Y%m%d_%H%M%S")}.csv'
            )
        
        # If the pre-generated file does not exist, generate the CSV on the fly
        data = list_obj.get_data()
        
        if not data:
            return jsonify({'error': 'No data available'}), 404
            
        # Create the CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write the header
        headers = [col.name for col in list_obj.columns]
        writer.writerow(headers)
        
        # Write the data
        for row in data:
            writer.writerow([row.get(header, '') for header in headers])
        
        # Prepare the response
        output.seek(0)
        response = send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{list_obj.name}_{get_paris_now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
        return response
    except Exception as e:
        current_app.logger.error(f"Error accessing public CSV file: {str(e)}")
        abort(500)

@public_files_bp.route('/public/json/<token>')
@public_route
def get_public_json(token):
    """
    Public access to a list's JSON file with token and IP restriction checks
    """
    # Find the list by its access token
    list_obj = List.query.filter_by(public_access_token=token).first()
    
    if not list_obj or not list_obj.public_json_enabled:
        abort(404)
    
    # Check IP restrictions
    if list_obj.ip_restriction_enabled and not check_ip_access(list_obj):
        current_app.logger.warning(f"Unauthorized access attempt to the public JSON file of list {list_obj.id} from {request.remote_addr}")
        # Store IP error information in the session
        session['ip_error_info'] = {
            'detected_ip': request.remote_addr,
            'original_header': request.headers.get('X-Forwarded-For', request.remote_addr),
            'allowed_ips': list_obj.allowed_ips
        }
        abort(403)
    
    try:
        # Check if a pre-generated JSON file exists
        json_path = os.path.join(current_app.root_path, 'public_files', f'list_{list_obj.id}.json')
        if os.path.exists(json_path):
            # Serve the pre-generated file
            with open(json_path, 'r', encoding='utf-8') as json_file:
                data = json.load(json_file)
            return jsonify(data)
        
        # If the pre-generated file does not exist, generate the JSON on the fly
        data = list_obj.get_data()
        
        if not data:
            return jsonify({'error': 'No data available'}), 404
            
        # Filter the 'id' field from the data for JSON export
        filtered_data = []
        for row in data:
            filtered_row = {k: v for k, v in row.items() if k != 'id'}
            filtered_data.append(filtered_row)
        
        return jsonify(filtered_data)
    except Exception as e:
        current_app.logger.error(f"Error accessing public JSON file: {str(e)}")
        abort(500)