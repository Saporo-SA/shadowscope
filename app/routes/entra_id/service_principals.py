"""
EntraID Service Principals routes.
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

from app.modules.entraID.service_principals import EntraIDServicePrincipals
from app.utils.route_helpers import get_user_context, prepare_module_permissions

service_principals_bp = Blueprint('service_principals', __name__)



@service_principals_bp.route('/service-principals')
def list_service_principals():
    """List service principals with caching."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    module_permissions = {
        'service_principals': prepare_module_permissions('service_principals', access)
    }
    
    sp_cache_path = 'results/service_principals.json'
    
    items = None
    try:
        if os.path.exists(sp_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(sp_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(sp_cache_path, 'r') as f:
                    items = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading service principals cache file: {str(e)}")
    
    if not items:
        service_principals = EntraIDServicePrincipals(session['graph_token'])
        result = service_principals.list_service_principals()
        
        if result['success']:
            items = result['data']
            
            if items:
                try:
                    os.makedirs(os.path.dirname(sp_cache_path), exist_ok=True)
                    with open(sp_cache_path, 'w') as f:
                        json.dump(items, f, indent=2)
                except Exception as e:
                    current_app.logger.error(f"Error saving service principals cache file: {str(e)}")
        else:
            flash(result['message'], 'error')
            return redirect(url_for('dashboard.dashboard'))
    
    cache_time = None
    if os.path.exists(sp_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(sp_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('entraID/service_principals.html', 
                         items=items, 
                         access=access,
                         module_permissions=module_permissions,
                         cache_time=cache_time)


@service_principals_bp.route('/service-principals/refresh')
def refresh_service_principals():
    """Refresh service principals from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('service_principals'):
        flash('You do not have permission to refresh service principals data.', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    sp_cache_path = 'results/service_principals.json'
    
    service_principals = EntraIDServicePrincipals(session['graph_token'])
    result = service_principals.list_service_principals()
    
    if result['success']:
        items = result['data']
        if items:
            try:
                os.makedirs(os.path.dirname(sp_cache_path), exist_ok=True)
                with open(sp_cache_path, 'w') as f:
                    json.dump(items, f, indent=2)
                flash(f"Successfully refreshed and cached {len(items)} service principals.", "success")
            except Exception as e:
                flash(f"Error saving cache file: {str(e)}", "error")
        else:
            flash("No service principals data returned from API.", "warning")
    else:
        flash(f"Failed to fetch service principals from API: {result.get('message', 'Unknown error')}", "error")
    
    return redirect(url_for('service_principals.list_service_principals'))


@service_principals_bp.route('/service-principals/<service_principal_id>')
def manage_service_principal(service_principal_id):
    """Manage a specific service principal."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    access = user_context.get('access', {})
    
    if not access.get('service_principals', {}).get('base', False):
        flash('Insufficient permissions to manage service principals', 'error')
        return redirect(url_for('dashboard.dashboard'))
    
    module_permissions = {
        'service_principals': prepare_module_permissions('service_principals', access)
    }
    
    service_principals = EntraIDServicePrincipals(session['graph_token'])
    result = service_principals.get_service_principal(service_principal_id)
    
    if result['success']:
        return render_template('entraID/manage_service_principal.html', 
                             sp=result['data'], 
                             access=access,
                             module_permissions=module_permissions)
    else:
        flash(result['message'], 'error')
        return redirect(url_for('service_principals.list_service_principals'))


@service_principals_bp.route('/service-principals/<service_principal_id>/addpassword', methods=['POST'])
def add_service_principal_password(service_principal_id):
    """Add password to service principal."""
    if 'graph_token' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return jsonify({'error': 'Invalid token'}), 401
    
    service_principals = EntraIDServicePrincipals(session['graph_token'])
    result = service_principals.add_password(service_principal_id)
    
    if result['success']:
        # Get the appId from the service principal
        sp_result = service_principals.get_service_principal(service_principal_id)
        if sp_result['success']:
            result['data']['appId'] = sp_result['data'].get('appId')
            result['data']['tenantId'] = token_data.get('tenant_id')
        
        return jsonify(result['data'])
    else:
        status_code = 400 if result.get('code') == 'CannotUpdateLockedServicePrincipalProperty' else 500
        return jsonify({
            'error': True,
            'message': result['message'],
            'code': result.get('code', 'UnknownError')
        }), status_code


@service_principals_bp.route('/service-principals/lateral-move', methods=['POST'])
def lateral_move_with_new_secret():
    """Perform automatic lateral movement (re-authentication) with new secret."""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['client_id', 'client_secret', 'tenant_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400
        
        # Immediately try to authenticate with new credentials
        from app.auth.azure_auth import get_tokens_for_all_apis
        from app.auth.creds_manager import CredsManager
        
        current_app.logger.info("Lateral movement: Attempting authentication with new credentials")
        
        tokens = get_tokens_for_all_apis(
            data['tenant_id'],
            data['client_id'],
            data['client_secret']
        )
        
        graph_token = tokens.get('graph_token')
        rest_token = tokens.get('rest_token')
        
        if not graph_token or not rest_token:
            return jsonify({
                'success': False,
                'message': 'Failed to obtain tokens with new credentials'
            }), 400
        
        # Update session with new tokens
        session['graph_token'] = graph_token
        session['rest_token'] = rest_token
        
        # Save new credentials
        CredsManager.save_credentials(
            data['tenant_id'],
            data['client_id'],
            data['client_secret']
        )
        
        # Update session roles
        from app.utils.jwt_parser import parse_jwt_token
        token_data = parse_jwt_token(graph_token)
        session['roles'] = token_data.get('roles', [])
        
        # Check Azure RBAC access
        from app.utils.azure_rbac_checker import check_azure_resource_access
        try:
            access_check = check_azure_resource_access(rest_token)
            session['has_azure_rbac_access'] = access_check.get('has_access', False)
        except Exception as e:
            current_app.logger.warning(f"Could not check Azure resource access: {str(e)}")
            session['has_azure_rbac_access'] = False
        
        current_app.logger.info("Lateral movement successful - session updated with new credentials")
        
        return jsonify({
            'success': True,
            'message': 'Lateral movement successful! Session updated.',
            'app_name': token_data.get('app_name', 'Unknown'),
            'roles': token_data.get('roles', [])
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in lateral movement: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error during lateral movement: {str(e)}'
        }), 500


@service_principals_bp.route('/service-principals/graph-permissions', methods=['GET'])
def get_graph_permissions():
    """Get available Graph API permissions."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_feature_access('service_principals', 'manage_role_assignments'):
        return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
        
    service_principals = EntraIDServicePrincipals(session['graph_token'])
    result = service_principals.get_graph_permissions()
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400


@service_principals_bp.route('/service-principals/<service_principal_id>/permissions', methods=['GET'])
def get_service_principal_permissions(service_principal_id):
    """Get current permissions assigned to a service principal."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_feature_access('service_principals', 'manage_role_assignments'):
        return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
        
    service_principals = EntraIDServicePrincipals(session['graph_token'])
    result = service_principals.get_service_principal_permissions(service_principal_id)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400


@service_principals_bp.route('/service-principals/<service_principal_id>/add-permissions', methods=['POST'])
def add_service_principal_permissions(service_principal_id):
    """Add permissions to service principal."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_feature_access('service_principals', 'manage_role_assignments'):
        return jsonify({'success': False, 'message': 'Insufficient permissions'}), 403
    
    data = request.get_json()
    permission_ids = data.get('permissionIds', [])
    
    if not permission_ids:
        return jsonify({'success': False, 'message': 'No permission IDs provided'}), 400
    
    service_principals = EntraIDServicePrincipals(session['graph_token'])
    result = service_principals.add_permissions(service_principal_id, permission_ids)
    
    if result['success']:
        return jsonify(result)
    else:
        return jsonify(result), 400

