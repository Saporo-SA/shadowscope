"""
Route helper functions for ShadowScope
Common utilities for route handling with proper validation and error handling
"""

import datetime
from flask import request, session, redirect, url_for, flash, current_app
from functools import wraps
from typing import Callable, Any, Dict, Optional


def require_auth(f: Callable) -> Callable:
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'graph_token' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        
        from app.auth.azure_auth import refresh_tokens_if_needed
        refresh_tokens_if_needed()
        
        return f(*args, **kwargs)
    return decorated_function


def require_azure_resource_permission(feature: str = None):
    """
    Decorator to require Azure Resource Management token.
    
    Note: Actual RBAC permissions are validated by Azure API calls,
    not by token inspection. This decorator only ensures the REST token exists.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if Azure Resource token exists
            if 'rest_token' not in session or not session['rest_token']:
                flash('Azure Resource Management token required for this operation.', 'error')
                return redirect(url_for('auth.login'))
            
            # Token exists - actual permissions are validated by API calls
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_permission(permission: str):
    """Decorator to require specific permission"""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'graph_token' not in session:
                flash("Authentication required", 'error')
                return redirect(url_for('auth.login'))
            
            from app.utils.jwt_parser import parse_jwt_token
            from app.auth.permissions import AzurePermissions
            
            token_data = parse_jwt_token(session['graph_token'])
            permissions = AzurePermissions(token_data.get('roles', []))
            
            # Check if permission is in the user's roles
            if permission not in permissions.roles:
                flash(f"Permission '{permission}' required", 'error')
                return redirect(url_for('dashboard.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator




def handle_api_errors(f: Callable) -> Callable:
    """Decorator to handle API errors gracefully"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            error_message = str(e)
            current_app.logger.error(f"Error in {f.__name__}: {error_message}")
            
            # Handle authentication-related errors
            if 'authentication' in error_message.lower() or 'token' in error_message.lower():
                flash("Authentication error. Please log in again.", 'error')
                return redirect(url_for('auth.login'))
            
            # Handle authorization errors
            if 'permission' in error_message.lower() or 'authorization' in error_message.lower():
                flash("You don't have permission to perform this action.", 'error')
                return redirect(url_for('dashboard.dashboard'))
            
            # Generic error handling
            flash("An unexpected error occurred. Please try again.", 'error')
            return redirect(request.referrer or url_for('dashboard.dashboard'))
    return decorated_function


def validate_id_parameter(param_name: str, value: str) -> str:
    """Validate ID parameter (UUID)"""
    if not value:
        raise ValueError(f"{param_name} is required")
    
    # Basic UUID validation
    import re
    uuid_pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
    if not re.match(uuid_pattern, value.lower()):
        raise ValueError(f"{param_name} must be a valid UUID")
    
    return value


def get_user_context() -> Dict[str, Any]:
    """Get current user context from session"""
    if 'graph_token' not in session:
        return {}
    
    from app.utils.jwt_parser import parse_jwt_token
    from app.auth.permissions import AzurePermissions
    
    token_data = parse_jwt_token(session['graph_token'])
    permissions = AzurePermissions(token_data.get('roles', []))
    
    return {
        'token_data': token_data,
        'permissions': permissions,
        'access': permissions.check_access(),
        'has_azure_resource_token': (
            'rest_token' in session and 
            session['rest_token'] and
            session.get('has_azure_rbac_access', False)
        )
    }


def log_user_action(action: str, resource: str = None, details: Dict = None):
    """Log user action for audit purposes"""
    user_context = get_user_context()
    user_id = user_context.get('token_data', {}).get('oid', 'unknown')
    
    current_app.logger.info(f"User action: {action}", extra={
        'user_id': user_id,
        'action': action,
        'resource': resource,
        'details': details or {}
    })


def get_standard_context() -> Dict[str, Any]:
    """Get standard context for all routes - eliminates duplication"""
    context = {
        'has_azure_resource_token': 'rest_token' in session and session.get('rest_token')
    }
    
    if 'graph_token' in session:
        user_context = get_user_context()
        context.update(user_context)
    
    return context


def parse_jwt_safely() -> Dict[str, Any]:
    """Safely parse JWT token with error handling"""
    try:
        if 'graph_token' not in session:
            return {}
        
        from app.utils.jwt_parser import parse_jwt_token
        return parse_jwt_token(session['graph_token'])
    except Exception as e:
        current_app.logger.warning(f"Failed to parse JWT token: {str(e)}")
        return {}


def format_message_dates(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format date fields in a message object.
    
    Args:
        message (Dict[str, Any]): Message object to format
        
    Returns:
        Dict[str, Any]: Message object with formatted dates
    """
    if 'receivedDateTime' in message:
        iso_date_string = message['receivedDateTime']
        try:
            # Handle timezone suffix - convert Z to +00:00
            date_str = iso_date_string.replace('Z', '+00:00')
            
            # Try parsing with timezone
            if '+' in date_str or date_str.endswith('00:00'):
                # Remove timezone for simple parsing
                date_str = date_str.split('+')[0].split('.')[0]
            dt = datetime.datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
            message['formattedDate'] = dt.strftime('%Y-%m-%d %H:%M')
        except (ValueError, TypeError, AttributeError):
            # Fallback to original date string
            message['formattedDate'] = iso_date_string
    return message


def prepare_module_permissions(module_name: str, access_data: dict) -> dict:
    """
    Prepare module permissions for template rendering.
    
    This is a shared utility function used across all route blueprints
    to format permission data for templates.
    
    Args:
        module_name: Name of the module (e.g., 'users', 'groups')
        access_data: Access control dictionary from AzurePermissions.check_access()
        
    Returns:
        dict: Formatted permission info with base_perms and features
    """
    module_info = {}
    
    token_data = parse_jwt_safely()
    from app.auth.permissions import AzurePermissions
    permissions = AzurePermissions(token_data.get('roles', []))
    
    if module_name in access_data and access_data[module_name].get('base'):
        module_info['base_perms'] = list(permissions.modules[module_name]['base'])
        
        module_info['features'] = {}
        features = permissions.modules[module_name].get('features', {})
        
        for feature_name, feature_perms in features.items():
            display_name = ' '.join(word.capitalize() for word in feature_name.split('_'))
            
            # Safely get features dict, default to empty dict if None
            module_features = access_data[module_name].get('features', {}) or {}
            
            # Use the enabled status from access_data (which uses any() logic)
            enabled_status = module_features.get(feature_name, False)
            
            module_info['features'][feature_name] = {
                'display_name': display_name,
                'enabled': enabled_status,
                'perms': list(feature_perms)
            }
    
    return module_info

