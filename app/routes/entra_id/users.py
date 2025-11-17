"""
EntraID Users routes.
"""

import json
import os
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.modules.entraID.security_principals import SecurityPrincipals
from app.utils.graph_api import GraphAPI
from app.modules.entraID.presence import EntraIDPresence as PresenceModule
from app.utils.route_helpers import (
    handle_api_errors,
    get_user_context,
    require_auth,
    prepare_module_permissions,
)

users_bp = Blueprint('users', __name__)



@users_bp.route('/users/<user_id>')
@require_auth
def user_details(user_id):
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    try:
        users_cache_path = 'results/users.json'
        user = None
        need_refresh = 'refresh' in request.args
        
        # Load user from cache
        if os.path.exists(users_cache_path):
            try:
                with open(users_cache_path, 'r') as f:
                    cached_users = json.load(f)
                    if isinstance(cached_users, list):
                        for cached_user in cached_users:
                            if cached_user.get('id') == user_id:
                                user = cached_user
                                break
            except Exception:
                pass
        
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('users.list_users'))
        
        # Extract cached data
        roles_data = {
            'entra_id_roles': user.get('_entra_id_roles', []),
            'azure_rbac_roles': user.get('_azure_rbac_roles', [])
        }
        user_groups = user.get('_groups', [])
        
        # Check if cache exists - verify both timestamp and actual data presence
        has_entra_roles = bool(user.get('_entra_id_roles'))
        has_azure_roles = bool(user.get('_azure_rbac_roles'))
        has_roles_cache = '_roles_cached_at' in user and (has_entra_roles or has_azure_roles)
        has_groups_cache = '_groups_cached_at' in user and bool(user.get('_groups'))
        
        # Refresh data if needed
        user_principal_name = user.get('userPrincipalName')
        graph = GraphAPI(session['graph_token'])
        
        # Get presence data - always fetch on page load if we have permission
        presence = user.get('presence')
        if access.get('presence', {}).get('base', False):
            try:
                presence_module = PresenceModule(graph, token_data.get('roles', []))
                fetched_presence = presence_module.get_presence(user_id)
                if fetched_presence:
                    presence = fetched_presence
                    user['presence'] = presence
            except Exception as e:
                current_app.logger.error(f"Error loading presence: {e}", exc_info=True)
                if not presence:
                    presence = user.get('presence')
        
        # Fast path: use cache if exists and no refresh requested
        if not need_refresh and has_roles_cache and has_groups_cache:
            return render_template(
                'entraID/user_details.html',
                user=user,
                roles_data=roles_data,
                user_groups=user_groups,
                access=access,
                presence=presence
            )
        
        # Load groups first if needed (required for role type detection)
        if need_refresh or not has_groups_cache:
            if access.get('groups', {}).get('base', False):
                try:
                    member_of = graph.get_paginated(f"users/{user_id}/memberOf")
                    if member_of:
                        user_groups = []
                        for item in member_of:
                            if item.get('@odata.type') == '#microsoft.graph.group':
                                user_groups.append({
                                    'id': item.get('id'),
                                    'displayName': item.get('displayName', 'Unknown'),
                                    'mail': item.get('mail'),
                                    'groupTypes': item.get('groupTypes', []),
                                    'securityEnabled': item.get('securityEnabled', False),
                                    'membershipType': 'Direct'
                                })
                except Exception as e:
                    current_app.logger.error(f"Error loading user groups: {e}", exc_info=True)
        
        # Use cached data if available, only fetch what's missing
        if not need_refresh and has_roles_cache:
            pass
        elif need_refresh or not has_roles_cache:
            if access.get('roles', {}).get('base', False) or ('rest_token' in session and session.get('rest_token')):
                try:
                    from app.modules.user_roles.user_roles_manager import UserRolesManager
                    
                    if access.get('roles', {}).get('base', False):
                        roles_manager = UserRolesManager(
                            graph_token=session.get('graph_token'),
                            rest_token=None
                        )
                        if roles_manager.graph_api and roles_manager.entra_roles:
                            # Pass user_groups to avoid extra request
                            roles_data['entra_id_roles'] = roles_manager._get_entra_id_roles(user_id, user_groups=user_groups if user_groups else None)
                    
                    if 'rest_token' in session and session.get('rest_token'):
                        roles_manager = UserRolesManager(
                            graph_token=session.get('graph_token'),
                            rest_token=session.get('rest_token')
                        )
                        if roles_manager.resource_manager:
                            roles_data['azure_rbac_roles'] = roles_manager._get_azure_rbac_roles(user_id)
                except Exception as e:
                    current_app.logger.error(f"Error loading roles: {e}", exc_info=True)
        
        # Update cache if data was refreshed or presence was fetched
        if need_refresh or not has_roles_cache or not has_groups_cache or presence:
            try:
                with open(users_cache_path, 'r') as f:
                    users_list = json.load(f)
                    if not isinstance(users_list, list):
                        users_list = []
                
                for i, u in enumerate(users_list):
                    if u.get('id') == user_id:
                        if need_refresh or not has_roles_cache:
                            users_list[i]['_entra_id_roles'] = roles_data['entra_id_roles']
                            users_list[i]['_azure_rbac_roles'] = roles_data['azure_rbac_roles']
                            users_list[i]['_roles_cached_at'] = datetime.now().isoformat()
                        if need_refresh or not has_groups_cache:
                            users_list[i]['_groups'] = user_groups
                            users_list[i]['_groups_cached_at'] = datetime.now().isoformat()
                        if presence:
                            users_list[i]['presence'] = presence
                            users_list[i]['_presence_cached_at'] = datetime.now().isoformat()
                        user = users_list[i]
                        break
                
                os.makedirs(os.path.dirname(users_cache_path), exist_ok=True)
                with open(users_cache_path, 'w') as f:
                    json.dump(users_list, f, indent=2, default=str)
            except Exception:
                pass
        
        return render_template(
            'entraID/user_details.html',
            user=user,
            roles_data=roles_data,
            user_groups=user_groups,
            access=access,
            presence=presence
        )
        
    except Exception as e:
        current_app.logger.error(f"Error loading user details: {e}")
        flash(f'Error loading user details: {str(e)}', 'error')
        return redirect(url_for('users.list_users'))


@users_bp.route('/users')
@require_auth
@handle_api_errors
def list_users():
    """List EntraID users with caching."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    module_permissions = {
        'users': prepare_module_permissions('users', access)
    }
    
    users_cache_path = 'results/users.json'
    
    users = None
    try:
        if os.path.exists(users_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(users_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(users_cache_path, 'r') as f:
                    users = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading cache file: {str(e)}")
    
    if not users:
        graph = GraphAPI(session['graph_token'])
        users = SecurityPrincipals(graph, token_data.get('roles', [])).get_users()
        
        if users:
            try:
                with open(users_cache_path, 'w') as f:
                    json.dump(users, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving cache file: {str(e)}")
    
    cache_time = None
    if os.path.exists(users_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(users_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('entraID/users.html',
        items=users,
        access=access,
        module_permissions=module_permissions,
        cache_time=cache_time
    )


@users_bp.route('/users/refresh')
@require_auth
def refresh_users():
    """Refresh users data from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('users'):
        flash('You do not have permission to refresh user data.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    users_cache_path = 'results/users.json'
    
    graph = GraphAPI(session['graph_token'])
    users = SecurityPrincipals(graph, token_data.get('roles', [])).get_users()
    
    if users:
        try:
            os.makedirs(os.path.dirname(users_cache_path), exist_ok=True)
            with open(users_cache_path, 'w') as f:
                json.dump(users, f, indent=2)
            flash(f"Successfully refreshed and cached {len(users)} users.", "success")
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch users from API.", "error")
    
    return redirect(url_for('users.list_users'))


@users_bp.route('/users/<user_id>/reset_auth_methods', methods=['POST'])
@require_auth
@handle_api_errors
def reset_auth_methods(user_id):
    """Resets all authentication methods for a specific user."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return jsonify({'success': False, 'message': 'Invalid token. Please log in again.'}), 401
    
    permissions = user_context.get('permissions')
    if not permissions:
        return jsonify({'success': False, 'message': 'Invalid token. Please log in again.'}), 401
    
    if not permissions.has_base_access('users'):
        return jsonify({'success': False, 'message': 'You do not have base permissions to manage users'}), 403
    
    if not permissions.has_feature_access('users', 'reset_auth_methods'):
        return jsonify({'success': False, 'message': 'You do not have permission to reset authentication methods'}), 403
    
    try:
        graph = GraphAPI(session['graph_token'])
        
        auth_methods = [
            'microsoftAuthenticatorMethods',
            'fido2Methods', 
            'windowsHelloForBusinessMethods',
            'emailMethods',
            'phoneMethods',
            'softwareOathMethods',
            'temporaryAccessPassMethods',
            'passwordMethods'
        ]
        
        reset_count = 0
        
        for method_type in auth_methods:
            try:
                endpoint = f"users/{user_id}/authentication/{method_type}"
                response = graph.get(endpoint)
                
                if response and 'value' in response:
                    methods = response['value']
                    
                    for method in methods:
                        if 'id' in method:
                            method_id = method['id']
                            try:
                                graph.delete(f"{endpoint}/{method_id}")
                                reset_count += 1
                            except Exception:
                                continue
            except Exception:
                continue
        
        if reset_count == 0:
            return jsonify({
                'success': True,
                'message': 'No deletable authentication methods found. Some methods may be protected by policy.',
                'data': {'count': 0}
            })
            
        return jsonify({
            'success': True,
            'message': f'Successfully processed {reset_count} authentication methods. Some methods may be protected by policy and could not be deleted.',
            'data': {'count': reset_count}
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error resetting authentication methods: {str(e)}',
            'data': {}
        }), 500

