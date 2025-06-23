from functools import wraps
from flask import request, current_app

def public_route(view_function):
    """
    Decorator to mark a route as public (no authentication required).
    """
    endpoint = view_function.__name__
    view_function.is_public = True
    
    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        return view_function(*args, **kwargs)
    
    decorated_function.is_public = True
    return decorated_function