from functools import wraps
from flask import jsonify, current_app, request
from flask_login import current_user
import ipaddress

def admin_required(f):
    """
    Decorator to check if the user is an administrator.
    To be used for routes that require administrator privileges.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        
        if not current_user.is_admin:
            current_app.logger.info(f"Admin access denied for user {current_user.id}")
            return jsonify({'error': 'Access denied - Administrator privileges required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def public_route(f):
    """
    Decorator for public routes that do not require authentication.
    To be used for routes accessing public CSV and JSON files.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    
    return decorated_function


def check_ip_access(list_obj):
    """
    Checks if the client's IP address is allowed to access the list.
    
    Args:
        list_obj: The list object to check
        
    Returns:
        bool: True if access is allowed, False otherwise
    """
    if not list_obj.ip_restriction_enabled or not list_obj.allowed_ips:
        return True
        
    client_ip = request.remote_addr
    if not client_ip:
        current_app.logger.warning("Could not determine client's IP address")
        return False
        
    # Get the list of allowed IPs
    try:
        import json
        allowed_ips = json.loads(list_obj.allowed_ips)
    except Exception as e:
        current_app.logger.error(f"Error reading allowed IPs: {str(e)}")
        return False
        
    # Check if the client's IP is in the list of allowed IPs
    for ip_rule in allowed_ips:
        try:
            # Check if it's a CIDR range
            if '/' in ip_rule:
                network = ipaddress.ip_network(ip_rule, strict=False)
                client_ip_obj = ipaddress.ip_address(client_ip)
                if client_ip_obj in network:
                    return True
            # Check if it's an IP range (format: start-end)
            elif '-' in ip_rule:
                start_ip, end_ip = ip_rule.split('-')
                start_ip_obj = ipaddress.ip_address(start_ip.strip())
                end_ip_obj = ipaddress.ip_address(end_ip.strip())
                client_ip_obj = ipaddress.ip_address(client_ip)
                if start_ip_obj <= client_ip_obj <= end_ip_obj:
                    return True
            # Check if it's an exact IP
            else:
                if client_ip == ip_rule.strip():
                    return True
        except Exception as e:
            current_app.logger.error(f"Error checking IP rule {ip_rule}: {str(e)}")
            continue
            
    return False