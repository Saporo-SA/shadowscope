"""
EntraID Administrative Units routes.
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

from app.modules.entraID.administrative_units import EntraIDAdministrativeUnits
from app.modules.entraID.security_principals import SecurityPrincipals
from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import (
    handle_api_errors,
    get_user_context,
    require_auth,
    prepare_module_permissions,
)

admin_units_bp = Blueprint('admin_units', __name__)



@admin_units_bp.route('/administrative-units')
@require_auth
@handle_api_errors
def administrative_units():
    """List administrative units with caching."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    module_permissions = {
        'admin_units': prepare_module_permissions('admin_units', access)
    }

    admin_units_cache_path = 'results/admin_units.json'

    items = None
    try:
        if os.path.exists(admin_units_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(admin_units_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)

            if file_age < timedelta(hours=24):
                with open(admin_units_cache_path, 'r') as f:
                    items = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading administrative units cache file: {str(e)}")

    if not items:
        graph_client = GraphAPI(session['graph_token'])
        admin_units = EntraIDAdministrativeUnits(graph_client, token_data.get('roles', []))
        items = admin_units.get_administrative_units()

        if items:
            try:
                os.makedirs(os.path.dirname(admin_units_cache_path), exist_ok=True)
                with open(admin_units_cache_path, 'w') as f:
                    json.dump(items, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving administrative units cache file: {str(e)}")
    
    cache_time = None
    if os.path.exists(admin_units_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(admin_units_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('entraID/administrative_units.html', 
        items=items,
        access=access,
        module_permissions=module_permissions,
        cache_time=cache_time
    )


@admin_units_bp.route('/administrative-units/refresh')
def refresh_administrative_units():
    """Refresh administrative units from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('admin_units'):
        flash('You do not have permission to refresh administrative units data.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    admin_units_cache_path = 'results/admin_units.json'

    graph_client = GraphAPI(session['graph_token'])
    admin_units = EntraIDAdministrativeUnits(graph_client, token_data.get('roles', []))
    items = admin_units.get_administrative_units()

    if items:
        try:
            os.makedirs(os.path.dirname(admin_units_cache_path), exist_ok=True)
            with open(admin_units_cache_path, 'w') as f:
                json.dump(items, f, indent=2)
            flash(f"Successfully refreshed and cached {len(items)} administrative units.", "success")
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch administrative units from API.", "error")
    
    return redirect(url_for('admin_units.administrative_units'))


@admin_units_bp.route('/administrative-units/<unit_id>/edit-membership')
def edit_administrative_unit_membership(unit_id):
    """Edit administrative unit membership."""
    try:
        user_context = get_user_context()
        token_data = user_context.get('token_data', {})
        access = user_context.get('access', {})
        
        if not access.get('admin_units'):
            return redirect(url_for('admin_units.administrative_units'))
        
        graph_client = GraphAPI(session['graph_token'])
        admin_units = EntraIDAdministrativeUnits(graph_client, token_data.get('roles', []))
        
        unit = admin_units.get_administrative_unit(unit_id)
        if not unit:
            return "Administrative Unit not found", 404
            
        members = admin_units.get_administrative_unit_members(unit_id)
        users = SecurityPrincipals(graph_client, token_data.get('roles', [])).get_users()
        
        return render_template(
            'entraID/edit_administrative_unit_membership.html',
            access=access,
            unit=unit,
            members=members,
            users=users
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in edit_administrative_unit_membership: {str(e)}")
        return f"Server error: {str(e)}", 500


@admin_units_bp.route('/administrative-units/<unit_id>/update_membership', methods=['POST'])
def update_administrative_unit_membership(unit_id):
    """Update administrative unit membership."""
    new_members = request.form.getlist('new_members')

    graph = GraphAPI(session['graph_token'])
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    admin_units = EntraIDAdministrativeUnits(graph, token_data.get('roles', []))
    
    for member_id in new_members:
        admin_units.add_member_to_administrative_unit(unit_id, member_id)
    
    return jsonify({'success': True, 'message': 'Membership updated successfully!'})


@admin_units_bp.route('/administrative-units/<unit_id>/add_member', methods=['POST'])
def add_administrative_unit_member(unit_id):
    """Add member to administrative unit."""
    data = request.get_json()
    odata_id = data.get('@odata.id')
    
    if not odata_id:
        return jsonify({'success': False, 'message': '@odata.id is required'}), 400

    member_id = odata_id.split('/')[-1]
    
    graph = GraphAPI(session['graph_token'])
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    admin_units = EntraIDAdministrativeUnits(graph, token_data.get('roles', []))
    
    result = admin_units.add_member_to_administrative_unit(unit_id, member_id)
    
    if result.get('success'):
        return jsonify(result), 200
    return jsonify(result), 400


@admin_units_bp.route('/administrative-units/<unit_id>/remove_member', methods=['POST'])
def remove_administrative_unit_member(unit_id):
    """Remove member from administrative unit."""
    data = request.get_json()
    odata_id = data.get('@odata.id')
    
    if not odata_id:
        return jsonify({'success': False, 'message': '@odata.id is required'}), 400

    member_id = odata_id.split('/')[-1]
    
    graph = GraphAPI(session['graph_token'])
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    admin_units = EntraIDAdministrativeUnits(graph, token_data.get('roles', []))
    
    result = admin_units.remove_member_from_administrative_unit(unit_id, member_id)
    
    if result.get('success'):
        return jsonify(result), 200
    return jsonify(result), 400

