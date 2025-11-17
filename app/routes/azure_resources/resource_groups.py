"""
Azure Resource Groups routes - Fully migrated from routes_old.py
"""

import json
import os
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.utils.route_helpers import handle_api_errors, require_auth, require_azure_resource_permission

resource_groups_bp = Blueprint('resource_groups', __name__)


@resource_groups_bp.route('/resource-groups')
@require_auth
@require_azure_resource_permission('list_resource_groups')
@handle_api_errors
def azure_resource_groups():
    """List Azure resource groups with caching."""
    has_resource_token = 'rest_token' in session and session['rest_token']
    
    from app.modules.azresources.resource_groups.resource_groups import AzureResourceGroups
    
    resource_groups_cache_path = 'results/resource_groups.json'
    
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(limit, 1), 100)
        
        result = None
        try:
            if os.path.exists(resource_groups_cache_path) and 'refresh' not in request.args:
                file_time = os.path.getmtime(resource_groups_cache_path)
                file_age = datetime.now() - datetime.fromtimestamp(file_time)
                
                if file_age < timedelta(hours=24):
                    with open(resource_groups_cache_path, 'r') as f:
                        cached_data = json.load(f)
                        cached_rg_list = cached_data.get('resource_groups', [])
                        result = {
                            'resource_groups': cached_rg_list[:limit],
                            'total_count': len(cached_rg_list),
                            'limit': limit,
                            'has_more': len(cached_rg_list) > limit
                        }
        except Exception as e:
            current_app.logger.error(f"Error reading resource groups cache file: {str(e)}")
        
        if not result:
            rg_manager = AzureResourceGroups()
            result = rg_manager.list_resource_groups(limit=limit)
            
            if result and result.get('resource_groups'):
                try:
                    os.makedirs(os.path.dirname(resource_groups_cache_path), exist_ok=True)
                    cache_data = {
                        'resource_groups': result.get('resource_groups', []),
                        'cached_at': datetime.now().isoformat()
                    }
                    with open(resource_groups_cache_path, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                except Exception as e:
                    current_app.logger.error(f"Error saving resource groups cache file: {str(e)}")
        
        if isinstance(result, dict):
            resource_groups_list = result.get('resource_groups', [])
            pagination_info = {
                'total_count': result.get('total_count', 0),
                'limit': result.get('limit', limit),
                'has_more': result.get('has_more', False),
                'error': result.get('error')
            }
        else:
            resource_groups_list = result if isinstance(result, list) else []
            pagination_info = {
                'total_count': len(resource_groups_list),
                'limit': limit,
                'has_more': False,
                'error': None
            }
        
        cache_time = None
        if os.path.exists(resource_groups_cache_path):
            cache_time = datetime.fromtimestamp(os.path.getmtime(resource_groups_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template('azresources/resource_groups/resource_groups.html', 
                             resource_groups=resource_groups_list, 
                             has_azure_resource_token=has_resource_token,
                             pagination=pagination_info,
                             cache_time=cache_time)
    except Exception as e:
        current_app.logger.error(f"Error listing resource groups: {e}")
        flash(f"Error listing resource groups: {str(e)}", "error")
        return redirect(url_for('dashboard.dashboard'))


@resource_groups_bp.route('/resource-groups/refresh')
@require_auth
@require_azure_resource_permission('list_resource_groups')
@handle_api_errors
def refresh_resource_groups():
    """Refresh resource groups data from API."""
    try:
        resource_groups_cache_path = 'results/resource_groups.json'
        if os.path.exists(resource_groups_cache_path):
            os.remove(resource_groups_cache_path)
            current_app.logger.info("Resource groups cache cleared")
        flash('Resource groups cache cleared. Data will be refreshed on next load.', 'success')
    except Exception as e:
        current_app.logger.error(f"Error clearing resource groups cache: {e}")
        flash(f"Error clearing cache: {str(e)}", "error")
    
    return redirect(url_for('resource_groups.azure_resource_groups'))


@resource_groups_bp.route('/resource-groups/<subscription_id>/<resource_group_name>')
def resource_group_details(subscription_id, resource_group_name):
    """Get resource group details."""
    if 'rest_token' not in session:
        return redirect(url_for('auth.login'))
    
    has_resource_token = 'rest_token' in session and session['rest_token']
    
    from app.modules.azresources.resource_groups.resource_groups import AzureResourceGroups
    
    try:
        rg_manager = AzureResourceGroups()
        resource_group = rg_manager.get_resource_group_details(subscription_id, resource_group_name)
        return render_template('azresources/resource_groups/resource_groups_details.html', 
                             resource_group=resource_group, 
                             has_azure_resource_token=has_resource_token)
    except Exception as e:
        current_app.logger.error(f"Error getting resource group details: {e}")
        flash(f"Error getting resource group details: {str(e)}", "error")
        return redirect(url_for('resource_groups.azure_resource_groups'))
