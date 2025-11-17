"""
Azure Management Groups routes - Fully migrated from routes_old.py
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

management_groups_bp = Blueprint('management_groups', __name__)


@management_groups_bp.route('/management-groups')
@require_auth
@require_azure_resource_permission('list_management_groups')
@handle_api_errors
def management_groups():
    """List Azure management groups with caching."""
    has_resource_token = 'rest_token' in session and session['rest_token']
    
    from app.modules.azresources.management_groups.management_groups import AzureManagementGroups
    
    management_groups_cache_path = 'results/management_groups.json'
    
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = min(max(limit, 1), 100)
        
        result = None
        try:
            if os.path.exists(management_groups_cache_path) and 'refresh' not in request.args:
                file_time = os.path.getmtime(management_groups_cache_path)
                file_age = datetime.now() - datetime.fromtimestamp(file_time)
                
                if file_age < timedelta(hours=24):
                    with open(management_groups_cache_path, 'r') as f:
                        cached_data = json.load(f)
                        cached_mg_list = cached_data.get('management_groups', [])
                        result = {
                            'management_groups': cached_mg_list[:limit],
                            'total_count': len(cached_mg_list),
                            'limit': limit,
                            'has_more': len(cached_mg_list) > limit
                        }
        except Exception as e:
            current_app.logger.error(f"Error reading management groups cache file: {str(e)}")
        
        if not result:
            mg_manager = AzureManagementGroups()
            result = mg_manager.list_management_groups(limit=limit)
            
            if result and result.get('management_groups'):
                try:
                    os.makedirs(os.path.dirname(management_groups_cache_path), exist_ok=True)
                    cache_data = {
                        'management_groups': result.get('management_groups', []),
                        'cached_at': datetime.now().isoformat()
                    }
                    with open(management_groups_cache_path, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                except Exception as e:
                    current_app.logger.error(f"Error saving management groups cache file: {str(e)}")
        
        if isinstance(result, dict):
            management_groups_list = result.get('management_groups', [])
            pagination_info = {
                'total_count': result.get('total_count', 0),
                'limit': result.get('limit', limit),
                'has_more': result.get('has_more', False),
                'error': result.get('error')
            }
        else:
            management_groups_list = result if isinstance(result, list) else []
            pagination_info = {
                'total_count': len(management_groups_list),
                'limit': limit,
                'has_more': False,
                'error': None
            }
        
        cache_time = None
        if os.path.exists(management_groups_cache_path):
            cache_time = datetime.fromtimestamp(os.path.getmtime(management_groups_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template('azresources/management_groups/management_groups.html', 
                             management_groups=management_groups_list, 
                             has_azure_resource_token=has_resource_token,
                             pagination=pagination_info,
                             cache_time=cache_time)
    except Exception as e:
        current_app.logger.error(f"Error listing management groups: {e}")
        flash(f"Error listing management groups: {str(e)}", "error")
        return redirect(url_for('dashboard.dashboard'))


@management_groups_bp.route('/management-groups/refresh')
@require_auth
@require_azure_resource_permission('list_management_groups')
@handle_api_errors
def refresh_management_groups():
    """Refresh management groups data from API."""
    try:
        management_groups_cache_path = 'results/management_groups.json'
        if os.path.exists(management_groups_cache_path):
            os.remove(management_groups_cache_path)
            current_app.logger.info("Management groups cache cleared")
        flash('Management groups cache cleared. Data will be refreshed on next load.', 'success')
    except Exception as e:
        current_app.logger.error(f"Error clearing management groups cache: {e}")
        flash(f"Error clearing cache: {str(e)}", "error")
    
    return redirect(url_for('management_groups.management_groups'))


@management_groups_bp.route('/management-groups/<management_group_id>')
def management_group_details(management_group_id):
    """Get management group details."""
    if 'rest_token' not in session:
        return redirect(url_for('auth.login'))
    
    has_resource_token = 'rest_token' in session and session['rest_token']
    
    from app.modules.azresources.management_groups.management_groups import AzureManagementGroups
    
    try:
        mg_manager = AzureManagementGroups()
        management_group = mg_manager.get_management_group_details(management_group_id)
        return render_template('azresources/management_groups/management_groups_detail.html', 
                             management_group=management_group, 
                             has_azure_resource_token=has_resource_token)
    except Exception as e:
        current_app.logger.error(f"Error getting management group details: {e}")
        flash(f"Error getting management group details: {str(e)}", "error")
        return redirect(url_for('management_groups.management_groups'))
