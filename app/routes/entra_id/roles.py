"""
EntraID Roles routes.
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

from app.modules.entraID.roles import EntraIDRoles
from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import (
    handle_api_errors,
    get_user_context,
    require_auth,
    prepare_module_permissions,
)

roles_bp = Blueprint('roles', __name__)



@roles_bp.route('/roles')
@require_auth
@handle_api_errors
def list_roles():
    """Lists all Entra ID roles."""
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        if not token_data:
            flash('Invalid token. Please login again.', 'error')
            return redirect(url_for('auth.login'))
            
        access = user_context.get('access', {})
        
        if not access.get('roles', {}).get('base', False):
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('dashboard.dashboard'))
        
        module_permissions = {
            'roles': prepare_module_permissions('roles', access)
        }
        
        roles_cache_path = 'results/roles.json'
        
        roles = None
        try:
            if os.path.exists(roles_cache_path) and 'refresh' not in request.args:
                file_time = os.path.getmtime(roles_cache_path)
                file_age = datetime.now() - datetime.fromtimestamp(file_time)
                
                if file_age < timedelta(hours=24):
                    with open(roles_cache_path, 'r') as f:
                        roles = json.load(f)
        except Exception as e:
            current_app.logger.error(f"Error reading roles cache file: {str(e)}")
        
        graph = GraphAPI(session['graph_token'])
        roles_module = EntraIDRoles(graph, token_data.get('roles', []))
        roles = roles_module.get_roles()
        
        if roles:
            try:
                os.makedirs(os.path.dirname(roles_cache_path), exist_ok=True)
                with open(roles_cache_path, 'w') as f:
                    json.dump(roles, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving roles cache file: {str(e)}")
        
        cache_time = None
        if os.path.exists(roles_cache_path):
            cache_time = datetime.fromtimestamp(os.path.getmtime(roles_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template('entraID/roles.html', 
                             roles=roles, 
                             access=access,
                             module_permissions=module_permissions,
                             cache_time=cache_time)
                             
    except Exception as e:
        current_app.logger.error(f"Error in list_roles: {str(e)}")
        flash(f'Error loading roles: {str(e)}', 'error')
        return redirect(url_for('dashboard.dashboard'))


@roles_bp.route('/roles/refresh')
def refresh_roles():
    """Updates the Entra ID roles cache."""
    try:
        if 'graph_token' not in session:
            flash('Session expired. Please login again.', 'error')
            return redirect(url_for('auth.login'))
            
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        if not access.get('roles', {}).get('base', False):
            flash('You do not have permission to manage roles.', 'error')
            return redirect(url_for('dashboard.dashboard'))
        
        graph = GraphAPI(session['graph_token'])
        roles_module = EntraIDRoles(graph, token_data.get('roles', []))
        roles = roles_module.get_roles(force_refresh=True)
        
        roles_cache_path = 'results/roles.json'
        if roles:
            try:
                os.makedirs(os.path.dirname(roles_cache_path), exist_ok=True)
                with open(roles_cache_path, 'w') as f:
                    json.dump(roles, f, indent=2)
                flash('Roles cache updated successfully!', 'success')
            except Exception as e:
                flash(f'Error saving cache: {str(e)}', 'error')
        else:
            flash('No roles found.', 'warning')
            
        return redirect(url_for('roles.list_roles'))
        
    except Exception as e:
        flash(f'Error updating roles cache: {str(e)}', 'error')
        return redirect(url_for('roles.list_roles'))


@roles_bp.route('/role_members/<role_id>')
def role_members(role_id):
    """Displays members of a specific role."""
    if 'graph_token' not in session:
        flash('Session expired. Please login again.', 'error')
        return redirect(url_for('auth.login'))
    
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('roles', {}).get('base', False):
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    try:
        graph = GraphAPI(session['graph_token'])
        roles_module = EntraIDRoles(graph, token_data.get('roles', []))
        
        role = roles_module.get_role(role_id)
        if not role:
            flash('Role not found.', 'error')
            return redirect(url_for('roles.list_roles'))
            
        members = roles_module.get_role_members(role_id)
        
        return render_template('entraID/role_members.html',
                        role=role,
                        members=members,
                        access=access)
    except Exception as e:
        current_app.logger.error(f"Error in role_members: {str(e)}")
        flash(f'Error loading role members: {str(e)}', 'error')
        return redirect(url_for('roles.list_roles'))


@roles_bp.route('/roles/<role_id>/members/add', methods=['POST'])
def add_role_member(role_id):
    """Adds a member to a role."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        permissions = user_context.get('permissions')
        if not permissions or not permissions.has_feature_access('roles', 'manage_role_assignments'):
            return jsonify({'success': False, 'message': 'Insufficient permissions to manage role members'}), 403
        
        data = request.get_json()
        member_id = data.get('member_id')
        
        if not member_id:
            return jsonify({'success': False, 'message': 'Member ID is required'}), 400
        
        graph = GraphAPI(session['graph_token'])
        roles_module = EntraIDRoles(graph, token_data.get('roles', []))
        result = roles_module.assign_role_to_user(role_id, member_id)
        
        if result:
            return jsonify({'success': True, 'message': 'Member added successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to add member to role'}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error adding member to role: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@roles_bp.route('/roles/<role_id>/members/<member_id>/remove', methods=['POST'])
def remove_role_member(role_id, member_id):
    """Removes a member from a role."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        permissions = user_context.get('permissions')
        if not permissions or not permissions.has_feature_access('roles', 'manage_role_assignments'):
            return jsonify({'success': False, 'message': 'Insufficient permissions to manage role members'}), 403
        
        graph = GraphAPI(session['graph_token'])
        roles_module = EntraIDRoles(graph, token_data.get('roles', []))
        result = roles_module.remove_role_from_user(role_id, member_id)
        
        if result:
            return jsonify({'success': True, 'message': 'Member removed successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to remove member from role'}), 500
            
    except Exception as e:
        current_app.logger.error(f"Error removing member from role: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

