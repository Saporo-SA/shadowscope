"""
EntraID Groups routes.
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

from app.modules.entraID.groups import EntraIDGroups
from app.modules.entraID.security_principals import SecurityPrincipals
from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import (
    get_standard_context,
    get_user_context,
    handle_api_errors,
    log_user_action,
    parse_jwt_safely,
    prepare_module_permissions,
    require_auth,
    require_permission,
    validate_id_parameter,
)

groups_bp = Blueprint('groups', __name__)



@groups_bp.route('/groups')
@require_auth
@handle_api_errors
def list_groups():
    """List EntraID groups with caching."""
    context = get_standard_context()
    access = context.get('access', {})
    
    module_permissions = {
        'groups': prepare_module_permissions('groups', access)
    }
    
    groups_cache_path = 'results/groups.json'
    
    groups = None
    try:
        if os.path.exists(groups_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(groups_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(groups_cache_path, 'r') as f:
                    groups = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading groups cache file: {str(e)}")
    
    if not groups:
        graph = GraphAPI(session['graph_token'])
        token_data = context.get('token_data', {})
        groups = EntraIDGroups(graph, token_data.get('roles', [])).get_groups()
        
        if groups:
            try:
                os.makedirs(os.path.dirname(groups_cache_path), exist_ok=True)
                with open(groups_cache_path, 'w') as f:
                    json.dump(groups, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving groups cache file: {str(e)}")
    
    cache_time = None
    if os.path.exists(groups_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(groups_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    log_user_action("view_groups", "groups", {"count": len(groups) if groups else 0})
    
    return render_template('entraID/groups.html',
        items=groups,
        access=access,
        module_permissions=module_permissions,
        cache_time=cache_time
    )


@groups_bp.route('/groups/refresh')
@require_auth
@handle_api_errors
def refresh_groups():
    """Refresh groups data from API."""
    context = get_user_context()
    permissions = context.get('permissions')
    if not permissions or not permissions.has_base_access('groups'):
        flash('You do not have permission to refresh group data.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    groups_cache_path = 'results/groups.json'
    
    graph = GraphAPI(session['graph_token'])
    token_data = context.get('token_data', {})
    groups = EntraIDGroups(graph, token_data.get('roles', [])).get_groups()
    
    if groups:
        try:
            os.makedirs(os.path.dirname(groups_cache_path), exist_ok=True)
            with open(groups_cache_path, 'w') as f:
                json.dump(groups, f, indent=2)
            flash(f"Successfully refreshed and cached {len(groups)} groups.", "success")
            log_user_action("refresh_groups", "groups", {"count": len(groups)})
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch groups from API.", "error")
    
    return redirect(url_for('groups.list_groups'))


@groups_bp.route('/groups/<group_id>/membership')
@require_auth
@handle_api_errors
def edit_group_membership(group_id):
    """Edit group membership."""
    group_id = validate_id_parameter('group_id', group_id)
    
    context = get_user_context()
    permissions = context.get('permissions')
    if not permissions:
        flash('Invalid token. Please log in again.', 'error')
        return redirect(url_for('auth.login'))
    
    access = permissions.check_access()
    
    graph = GraphAPI(session['graph_token'])
    groups_module = EntraIDGroups(graph, context.get('token_data', {}).get('roles', []))
    
    group = groups_module.get_group(group_id)
    if not group:
        return "Group not found", 404
    
    members = groups_module.get_group_members(group_id)
    token_data = context.get('token_data', {})
    users = SecurityPrincipals(graph, token_data.get('roles', [])).get_users()
    
    log_user_action("view_group_membership", "groups", {"group_id": group_id})
    
    return render_template(
        'entraID/edit_membership.html',
        access=access,
        group=group,
        members=members,
        users=users
    )


@groups_bp.route('/groups/<group_id>/add_member', methods=['POST'])
@require_auth
@require_permission('Group.ReadWrite.All')
@handle_api_errors
def add_group_member(group_id):
    """Add member to group."""
    group_id = validate_id_parameter('group_id', group_id)
    
    data = request.get_json()
    if not data or not data.get('member_id'):
        return jsonify({'success': False, 'message': 'Member ID is required'}), 400
    
    member_id = validate_id_parameter('member_id', data.get('member_id'))
    
    context = get_user_context()
    graph = GraphAPI(session['graph_token'])
    token_data = context.get('token_data', {})
    groups_module = EntraIDGroups(graph, token_data.get('roles', []))
    
    result = groups_module.add_member_to_group(group_id, member_id)
    
    if result.get('success'):
        log_user_action("add_group_member", "groups", {
            "group_id": group_id,
            "member_id": member_id
        })
    
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400


@groups_bp.route('/groups/<group_id>/remove_member', methods=['POST'])
@require_auth
@require_permission('Group.ReadWrite.All')
@handle_api_errors
def remove_group_member(group_id):
    """Remove member from group."""
    group_id = validate_id_parameter('group_id', group_id)
    
    data = request.get_json()
    if not data or not data.get('member_id'):
        return jsonify({'success': False, 'message': 'Member ID is required'}), 400
    
    member_id = validate_id_parameter('member_id', data.get('member_id'))
    
    context = get_user_context()
    graph = GraphAPI(session['graph_token'])
    token_data = context.get('token_data', {})
    groups_module = EntraIDGroups(graph, token_data.get('roles', []))
    
    result = groups_module.remove_member_from_group(group_id, member_id)
    
    if result.get('success'):
        log_user_action("remove_group_member", "groups", {
            "group_id": group_id,
            "member_id": member_id
        })
    
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400

