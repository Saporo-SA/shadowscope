"""
Intune routes for device management.
"""

import json
import os
import base64
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

from app.modules.intune.intune import Intune
from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import (
    handle_api_errors,
    get_user_context,
    require_auth,
    prepare_module_permissions,
)

intune_bp = Blueprint('intune', __name__)


def get_device_icon(operating_system: str, device_type: str = None) -> str:
    """
    Get Bootstrap Icons class name based on operating system and device type.
    
    Args:
        operating_system: The operating system name (e.g., 'Windows', 'iOS', 'Android')
        device_type: Optional device type (e.g., 'Mobile', 'Desktop', 'Tablet')
    
    Returns:
        Bootstrap Icons class name
    """
    if not operating_system:
        return 'bi-device-hdd'
    
    os_lower = operating_system.lower()
    device_type_lower = (device_type or '').lower()
    
    # Check device type first for more specific icons
    if 'tablet' in device_type_lower or 'ipad' in os_lower:
        return 'bi-tablet'
    elif 'mobile' in device_type_lower or 'phone' in device_type_lower:
        return 'bi-phone'
    elif 'desktop' in device_type_lower:
        return 'bi-display'
    elif 'laptop' in device_type_lower:
        return 'bi-laptop'
    
    # Then check operating system
    if 'windows' in os_lower:
        return 'bi-windows'
    elif 'ios' in os_lower or 'iphone' in os_lower:
        return 'bi-phone'
    elif 'android' in os_lower:
        return 'bi-phone'
    elif 'macos' in os_lower or 'mac os' in os_lower or 'darwin' in os_lower:
        return 'bi-apple'
    elif 'linux' in os_lower:
        return 'bi-ubuntu'
    else:
        return 'bi-device-hdd'


@intune_bp.app_context_processor
def inject_device_icon_helper():
    """Inject device icon helper function into templates."""
    return {'get_device_icon': get_device_icon}


@intune_bp.route('/intune')
@require_auth
@handle_api_errors
def intune_devices():
    """List Intune devices."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('intune', {}).get('base', False):
        flash('You do not have permission to access Intune.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    module_permissions = {
        'intune': prepare_module_permissions('intune', access)
    }
    
    devices_cache_path = 'results/intune_devices.json'
    
    devices = None
    try:
        if os.path.exists(devices_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(devices_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(devices_cache_path, 'r') as f:
                    devices = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading Intune devices cache file: {str(e)}")
    
    if not devices:
        graph_api = GraphAPI(session['graph_token'])
        intune_module = Intune(graph_api)
        devices = intune_module.get_intune_devices()
        
        if devices:
            try:
                os.makedirs(os.path.dirname(devices_cache_path), exist_ok=True)
                with open(devices_cache_path, 'w') as f:
                    json.dump(devices, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving Intune devices cache file: {str(e)}")
    
    cache_time = None
    if os.path.exists(devices_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(devices_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('intune/devices.html', 
                         devices=devices, 
                         access=access, 
                         module_permissions=module_permissions, 
                         cache_time=cache_time)


@intune_bp.route('/intune/refresh')
@require_auth
def refresh_devices():
    """Refresh Intune devices data from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
        
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('intune'):
        flash('You do not have permission to refresh Intune devices data.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    devices_cache_path = 'results/intune_devices.json'
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    devices = intune_module.get_intune_devices()
    
    if devices:
        try:
            os.makedirs(os.path.dirname(devices_cache_path), exist_ok=True)
            with open(devices_cache_path, 'w') as f:
                json.dump(devices, f, indent=2)
            flash(f"Successfully refreshed and cached {len(devices)} Intune devices.", "success")
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch Intune devices from API.", "error")
    
    return redirect(url_for('intune.intune_devices'))

@intune_bp.route('/intune/run-script')
@require_auth
def run_script():
    """Run a script on an Intune device."""
    user_context = get_user_context()
    
    script_id = request.args.get('script_id')
    device_id = request.args.get('device_id')
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    result = intune_module.run_script(script_id, device_id)
    
    return jsonify(result)


@intune_bp.route('/intune/manage')
@require_auth
@handle_api_errors
def manage_scripts():
    """Display Intune scripts management page."""
    user_context = get_user_context()
    access = user_context.get('access', {})
    
    if not access.get('intune', {}).get('base', False):
        flash('You do not have permission to access Intune.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    module_permissions = {
        'intune': prepare_module_permissions('intune', access)
    }
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    devices = intune_module.get_intune_devices()
    
    return render_template('intune/manage.html',
                         access=access,
                         module_permissions=module_permissions,
                         devices=devices)


@intune_bp.route('/intune/manage/scripts')
@require_auth
def get_scripts():
    """API endpoint to fetch all scripts."""
    user_context = get_user_context()
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('intune'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    scripts = intune_module.get_scripts()
    
    for script in scripts:
        if script.get('scriptContent'):
            try:
                script['scriptContent'] = base64.b64decode(script['scriptContent']).decode('utf-8')
            except Exception:
                pass
    
    return jsonify(scripts)


@intune_bp.route('/intune/manage/scripts/<script_id>')
@require_auth
def get_script(script_id):
    """Get a specific script by ID."""
    user_context = get_user_context()
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('intune'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    script = intune_module.get_script(script_id)
    
    if script is None:
        return jsonify({'error': 'Script not found'}), 404
    
    if script.get('scriptContent'):
        try:
            script['scriptContent'] = base64.b64decode(script['scriptContent']).decode('utf-8')
        except Exception:
            pass
    
    return jsonify(script)


@intune_bp.route('/intune/manage/scripts', methods=['POST'])
@require_auth
def create_script():
    """Create a new script."""
    user_context = get_user_context()
    permissions = user_context.get('permissions')
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request data'}), 400
    
    platform = data.get('platform', 'Windows')
    platform_lower = platform.lower() if platform else 'windows'
    
    if platform_lower == 'linux':
        if not permissions or not permissions.has_feature_access('intune', 'linux_scripts'):
            return jsonify({'error': 'Unauthorized: Linux scripts require DeviceManagementConfiguration.ReadWrite.All and DeviceManagementEndpointSecurity.ReadWrite.All'}), 403
    else:
        if not permissions or not permissions.has_feature_access('intune', 'windows_macos_scripts'):
            return jsonify({'error': 'Unauthorized: Windows/macOS scripts require DeviceManagementScripts.ReadWrite.All'}), 403
    
    name = data.get('name')
    description = data.get('description', '')
    script_content = data.get('script_content', '')
    run_as_account = data.get('run_as_account', 'system')
    enforce_signature_check = data.get('enforce_signature_check', False)
    run_as32bit = data.get('run_as32bit', False)
    script_type = data.get('script_type', 'PowerShell')
    
    if not name or not script_content:
        return jsonify({'error': 'Name and script content are required'}), 400
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    result = intune_module.create_script(
        name=name,
        description=description,
        script_content=script_content,
        run_as_account=run_as_account,
        enforce_signature_check=enforce_signature_check,
        run_as32bit=run_as32bit,
        script_type=script_type,
        platform=platform
    )
    
    if result.get('success'):
        return jsonify(result), 201
    else:
        return jsonify(result), 400


@intune_bp.route('/intune/manage/scripts/<script_id>', methods=['PATCH'])
@require_auth
def update_script(script_id):
    """Update an existing script."""
    user_context = get_user_context()
    permissions = user_context.get('permissions')
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    
    script = intune_module.get_script(script_id)
    if not script:
        return jsonify({'error': 'Script not found'}), 404
    
    platform = script.get('platform', 'Windows')
    platform_lower = platform.lower() if platform else 'windows'
    
    if platform_lower == 'linux':
        if not permissions or not permissions.has_feature_access('intune', 'linux_scripts'):
            return jsonify({'error': 'Unauthorized: Linux scripts require DeviceManagementConfiguration.ReadWrite.All and DeviceManagementEndpointSecurity.ReadWrite.All'}), 403
    else:
        if not permissions or not permissions.has_feature_access('intune', 'windows_macos_scripts'):
            return jsonify({'error': 'Unauthorized: Windows/macOS scripts require DeviceManagementScripts.ReadWrite.All'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request data'}), 400
    
    result = intune_module.update_script(
        script_id=script_id,
        name=data.get('name'),
        description=data.get('description'),
        script_content=data.get('script_content'),
        run_as_account=data.get('run_as_account'),
        enforce_signature_check=data.get('enforce_signature_check'),
        run_as32bit=data.get('run_as32bit')
    )
    
    if result.get('success'):
        return jsonify(result), 200
    else:
        return jsonify(result), 400


@intune_bp.route('/intune/manage/scripts/<script_id>', methods=['DELETE'])
@require_auth
def delete_script(script_id):
    """Delete a script."""
    user_context = get_user_context()
    permissions = user_context.get('permissions')
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    
    script = intune_module.get_script(script_id)
    if not script:
        return jsonify({'error': 'Script not found'}), 404
    
    platform = script.get('platform', 'Windows')
    platform_lower = platform.lower() if platform else 'windows'
    
    if platform_lower == 'linux':
        if not permissions or not permissions.has_feature_access('intune', 'linux_scripts'):
            return jsonify({'error': 'Unauthorized: Linux scripts require DeviceManagementConfiguration.ReadWrite.All and DeviceManagementEndpointSecurity.ReadWrite.All'}), 403
    else:
        if not permissions or not permissions.has_feature_access('intune', 'windows_macos_scripts'):
            return jsonify({'error': 'Unauthorized: Windows/macOS scripts require DeviceManagementScripts.ReadWrite.All'}), 403
    
    result = intune_module.delete_script(script_id)
    
    if result.get('success'):
        return jsonify(result), 200
    else:
        return jsonify(result), 400


@intune_bp.route('/intune/manage/groups')
@require_auth
def get_groups():
    """Get list of groups for script assignment."""
    user_context = get_user_context()
    access = user_context.get('access', {})
    
    if not access.get('groups', {}).get('base', False):
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        graph_api = GraphAPI(session['graph_token'])
        groups = graph_api.get_paginated("groups")
        
        if not groups:
            groups = []
        
        groups_list = [
            {
                'id': group.get('id'),
                'displayName': group.get('displayName'),
                'mail': group.get('mail')
            }
            for group in groups
        ]
        
        return jsonify(groups_list), 200
    except Exception as e:
        current_app.logger.error(f"Error fetching groups: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@intune_bp.route('/intune/manage/scripts/<script_id>/execute', methods=['POST'])
@require_auth
def execute_script(script_id):
    """Execute a script by assigning it based on assignment type.
    
    Note: Execution cannot be forced - this only assigns the script.
    Actual execution is handled by Intune service.
    """
    user_context = get_user_context()
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid request data'}), 400
    
    assignment_type = data.get('assignment_type')
    if not assignment_type:
        return jsonify({'error': 'Assignment type is required'}), 400
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    
    if assignment_type == 'select_groups':
        group_id = data.get('group_id')
        if not group_id:
            return jsonify({'error': 'Group ID is required for select_groups assignment'}), 400
        result = intune_module.execute_script(script_id, assignment_type='select_groups', group_id=group_id)
    elif assignment_type == 'all_devices':
        result = intune_module.execute_script(script_id, assignment_type='all_devices')
    elif assignment_type == 'all_users':
        result = intune_module.execute_script(script_id, assignment_type='all_users')
    else:
        return jsonify({'error': 'Invalid assignment type'}), 400
    
    if result.get('success'):
        return jsonify(result), 200
    else:
        return jsonify(result), 400


@intune_bp.route('/intune/manage/scripts/<script_id>/run-summary')
@require_auth
def get_script_run_summary(script_id):
    """Get run summary for a script execution."""
    user_context = get_user_context()
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('intune'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    graph_api = GraphAPI(session['graph_token'])
    intune_module = Intune(graph_api)
    run_summary = intune_module.get_script_run_summary(script_id)
    
    if run_summary is None:
        return jsonify({'error': 'Run summary not found'}), 404
    
    return jsonify(run_summary), 200