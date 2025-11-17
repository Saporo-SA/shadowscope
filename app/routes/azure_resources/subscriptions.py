"""
Azure Subscriptions routes - Fully migrated from routes_old.py
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

subscriptions_bp = Blueprint('subscriptions', __name__)


@subscriptions_bp.route('/subscriptions')
@require_auth
@require_azure_resource_permission('list_subscriptions')
@handle_api_errors
def subscriptions():
    """List Azure subscriptions with caching."""
    has_resource_token = 'rest_token' in session and session['rest_token']
    
    from app.modules.azresources.subscriptions.subscriptions import AzureSubscriptions
    
    subscriptions_cache_path = 'results/subscriptions.json'
    
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        
        result = None
        try:
            if os.path.exists(subscriptions_cache_path) and 'refresh' not in request.args:
                file_time = os.path.getmtime(subscriptions_cache_path)
                file_age = datetime.now() - datetime.fromtimestamp(file_time)
                
                if file_age < timedelta(hours=24):
                    with open(subscriptions_cache_path, 'r') as f:
                        cached_data = json.load(f)
                        # Apply pagination to cached data
                        all_subscriptions = cached_data.get('subscriptions', [])
                        total_count = len(all_subscriptions)
                        paginated_subscriptions = all_subscriptions[offset:offset + limit]
                        
                        result = {
                            'subscriptions': paginated_subscriptions,
                            'total_count': total_count,
                            'limit': limit,
                            'offset': offset,
                            'has_more': (offset + limit) < total_count
                        }
        except Exception as e:
            current_app.logger.error(f"Error reading subscriptions cache file: {str(e)}")
        
        if not result:
            subscription_manager = AzureSubscriptions()
            result = subscription_manager.list_subscriptions(limit=limit, offset=offset)
            
            if result and result.get('subscriptions'):
                try:
                    os.makedirs(os.path.dirname(subscriptions_cache_path), exist_ok=True)
                    # Store all subscriptions for cache, not just paginated ones
                    cache_data = {
                        'subscriptions': result.get('subscriptions', []),
                        'cached_at': datetime.now().isoformat()
                    }
                    with open(subscriptions_cache_path, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                except Exception as e:
                    current_app.logger.error(f"Error saving subscriptions cache file: {str(e)}")
        
        if isinstance(result, dict):
            subscriptions_list = result.get('subscriptions', [])
            pagination_info = {
                'total_count': result.get('total_count', 0),
                'limit': result.get('limit', limit),
                'offset': result.get('offset', offset),
                'has_more': result.get('has_more', False),
                'error': result.get('error')
            }
        else:
            subscriptions_list = result if isinstance(result, list) else []
            pagination_info = {
                'total_count': len(subscriptions_list),
                'limit': limit,
                'offset': offset,
                'has_more': False,
                'error': None
            }
        
        cache_time = None
        if os.path.exists(subscriptions_cache_path):
            cache_time = datetime.fromtimestamp(os.path.getmtime(subscriptions_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template('azresources/subscriptions/subscriptions.html', 
                             subscriptions=subscriptions_list, 
                             has_azure_resource_token=has_resource_token,
                             pagination=pagination_info,
                             cache_time=cache_time)
    except Exception as e:
        current_app.logger.error(f"Error listing subscriptions: {e}")
        flash(f"Error listing subscriptions: {str(e)}", "error")
        return redirect(url_for('dashboard.dashboard'))


@subscriptions_bp.route('/subscriptions/refresh')
@require_auth
@require_azure_resource_permission('list_subscriptions')
@handle_api_errors
def refresh_subscriptions():
    """Refresh subscriptions data from API."""
    try:
        subscriptions_cache_path = 'results/subscriptions.json'
        if os.path.exists(subscriptions_cache_path):
            os.remove(subscriptions_cache_path)
            current_app.logger.info("Subscriptions cache cleared")
        flash('Subscriptions cache cleared. Data will be refreshed on next load.', 'success')
    except Exception as e:
        current_app.logger.error(f"Error clearing subscriptions cache: {e}")
        flash(f"Error clearing cache: {str(e)}", "error")
    
    return redirect(url_for('subscriptions.subscriptions'))


@subscriptions_bp.route('/graph-subscriptions/<subscription_id>')
def subscription_details(subscription_id):
    """Get subscription details."""
    if 'rest_token' not in session:
        return redirect(url_for('auth.login'))
    
    has_resource_token = 'rest_token' in session and session['rest_token']
    
    from app.modules.azresources.subscriptions.subscriptions import AzureSubscriptions
    
    try:
        subscription_manager = AzureSubscriptions()
        subscription = subscription_manager.get_subscription_details(subscription_id)
        return render_template('azresources/subscriptions/subscriptions_details.html', 
                             subscription=subscription, 
                             has_azure_resource_token=has_resource_token)
    except Exception as e:
        current_app.logger.error(f"Error getting subscription details: {e}")
        flash(f"Error getting subscription details: {str(e)}", "error")
        return redirect(url_for('subscriptions.subscriptions'))
