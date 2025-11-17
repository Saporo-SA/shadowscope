"""
Dashboard and main application routes.
"""

from typing import Any, Dict

from flask import Blueprint, Response, redirect, render_template, session, url_for

from app.utils.route_helpers import (
    get_user_context,
    handle_api_errors,
    require_auth,
)

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.app_context_processor
def inject_app_info() -> Dict[str, Any]:
    """Inject app information into all templates."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if token_data:
        # Azure Resources access requires REST token AND actual RBAC permissions
        has_resource_token = user_context.get('has_azure_resource_token', False)
        
        return {
            'app_info': {
                'app_name': token_data.get('app_name', 'Unknown App'),
                'permissions': sorted(token_data.get('roles', [])),
                'tenant_id': token_data.get('tenant_id', 'Unknown Tenant'),
                'app_id': token_data.get('appid', 'Unknown App'),
                'has_azure_resource_token': has_resource_token
            },
            'access': access,
            'has_azure_resource_token': has_resource_token
        }
    return {'app_info': {}, 'access': {}, 'has_azure_resource_token': False}


@dashboard_bp.route('/')
def index() -> Response:
    """Redirect to dashboard."""
    return redirect(url_for('dashboard.dashboard'))


@dashboard_bp.route('/dashboard')
@require_auth
@handle_api_errors
def dashboard() -> str:
    """
    Main dashboard with user context and permissions.
    
    Returns:
        str: Rendered dashboard template
    """
    context = get_user_context()
    
    return render_template('dashboard.html', 
                          access=context.get('access', {}), 
                          has_azure_resource_token=context.get('has_azure_resource_token', False))


@dashboard_bp.route('/about')
def about() -> str:
    """
    About page with information about ShadowScope and its creator.
    
    Returns:
        str: Rendered about template
    """
    return render_template('about.html')

