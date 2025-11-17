"""
Authentication routes.
Handles login, logout, and token management.
"""

import re
from typing import Union

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.auth.azure_auth import azure_logout
from app.utils.jwt_parser import parse_jwt_token
from app.utils.route_helpers import require_auth

auth_bp = Blueprint('auth', __name__)


def _extract_aadsts_code(error: Exception) -> str:
    """
    Extract AADSTS error code from exception if present.
    
    Args:
        error: Exception object that may contain AADSTS code
        
    Returns:
        AADSTS code string if found, None otherwise
    """
    error_str = str(error)
    if 'AADSTS' in error_str:
        match = re.search(r'AADSTS\d+', error_str)
        if match:
            return match.group()
    return None


def _flash_with_aadsts(message: str, error: Exception):
    """
    Flash error message with AADSTS code if present.
    
    Args:
        message: Base error message to display
        error: Exception that may contain AADSTS code
    """
    aadsts_code = _extract_aadsts_code(error)
    if aadsts_code:
        flash(f"{message}: {aadsts_code}", 'error')
    else:
        flash(message, 'error')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login() -> Union[str, Response]:
    """Handle user login with Azure credentials."""
    if 'graph_token' in session:
        return redirect(url_for('dashboard.dashboard'))
    
    if request.method == 'POST':
        graph_token_input = request.form.get('graph_token', '').strip()
        rest_token_input = request.form.get('rest_token', '').strip()
        
        if graph_token_input:
            from app.auth.azure_auth import authenticate_with_token
            try:
                graph_token = authenticate_with_token(graph_token_input)
                
                if graph_token:
                    session['graph_token'] = graph_token
                    
                    token_data = parse_jwt_token(graph_token)
                    session['roles'] = token_data.get('roles', [])
                    
                    if rest_token_input:
                        rest_token = authenticate_with_token(rest_token_input)
                        if rest_token:
                            session['rest_token'] = rest_token
                            
                            from app.utils.azure_rbac_checker import check_azure_resource_access
                            try:
                                access_check = check_azure_resource_access(rest_token)
                                session['has_azure_rbac_access'] = access_check.get('has_access', False)
                                if access_check.get('subscription_count', 0) > 0:
                                    current_app.logger.info(f"Azure Resources: {access_check['subscription_count']} subscription(s) accessible")
                                elif access_check.get('error'):
                                    current_app.logger.warning(f"Azure Resources: {access_check['error']}")
                            except Exception as e:
                                current_app.logger.warning(f"Could not check Azure resource access: {str(e)}")
                                session['has_azure_rbac_access'] = False
                            
                            flash('Login successful with both tokens!', 'success')
                        else:
                            session['rest_token'] = None
                            session['has_azure_rbac_access'] = False
                            flash('Login successful with Graph token! Azure Management token was invalid.', 'warning')
                    else:
                        session['rest_token'] = None
                        session['has_azure_rbac_access'] = False
                        flash('Login successful with Graph token! (Azure Resources access not available)', 'success')
                    
                    return redirect(url_for('dashboard.dashboard'))
                else:
                    flash("Invalid or expired Graph API token. Please provide a valid access token.", 'error')
                    return render_template('login.html')
                    
            except Exception as e:
                current_app.logger.error(f"Token authentication error: {str(e)}")
                flash("Token authentication failed. Please verify your token is valid.", 'error')
                return render_template('login.html')
        
        tenant_id = request.form.get('tenant_id', '').strip()
        client_id = request.form.get('client_id', '').strip()
        client_secret = request.form.get('client_secret', '').strip()
        
        if tenant_id and client_id and client_secret:
            try:
                from app.auth.azure_auth import get_tokens_for_all_apis
                from app.auth.creds_manager import CredsManager
                
                tokens = get_tokens_for_all_apis(
                    tenant_id, 
                    client_id, 
                    client_secret
                )
                
                graph_token = tokens.get('graph_token')
                rest_token = tokens.get('rest_token')
                
                if graph_token and rest_token:
                    session['graph_token'] = graph_token
                    session['rest_token'] = rest_token
                    
                    CredsManager.save_credentials(tenant_id, client_id, client_secret)
                    
                    # Check if SP has Azure resource access
                    from app.utils.azure_rbac_checker import check_azure_resource_access
                    try:
                        access_check = check_azure_resource_access(rest_token)
                        session['has_azure_rbac_access'] = access_check.get('has_access', False)
                        if access_check.get('subscription_count', 0) > 0:
                            current_app.logger.info(f"Azure Resources: {access_check['subscription_count']} subscription(s) accessible")
                        elif access_check.get('error'):
                            current_app.logger.warning(f"Azure Resources: {access_check['error']}")
                    except Exception as e:
                        current_app.logger.warning(f"Could not check Azure resource access: {str(e)}")
                        session['has_azure_rbac_access'] = False
                    
                    token_data = parse_jwt_token(graph_token)
                    session['roles'] = token_data.get('roles', [])
                    
                    # Start background data collection only if user has permissions
                    try:
                        from app.auth.permissions import AzurePermissions
                        permissions = AzurePermissions(token_data.get('roles', []))
                        
                        has_entra_permissions = (
                            permissions.has_base_access('users') or
                            permissions.has_base_access('roles') or
                            permissions.has_base_access('groups')
                        )
                        has_azure_permissions = (
                            rest_token and
                            session.get('has_azure_rbac_access', False)
                        )
                        
                        if has_entra_permissions or has_azure_permissions:
                            from app.utils.background_collector import BackgroundDataCollector
                            collector = BackgroundDataCollector(
                                graph_token=graph_token,
                                rest_token=rest_token if has_azure_permissions else None,
                                user_permissions=token_data.get('roles', [])
                            )
                            collector.start_collection()
                            session['background_collector_started'] = True
                            current_app.logger.info("Background data collection started")
                    except Exception as e:
                        current_app.logger.warning(f"Could not start background collection: {e}")
                    
                    flash('Login successful!', 'success')
                    return redirect(url_for('dashboard.dashboard'))
                else:
                    flash("Could not obtain required tokens. Please check your credentials.", 'error')
                    return render_template('login.html')
                    
            except Exception as e:
                current_app.logger.error(f"Authentication error: {str(e)}")
                
                # Provide more specific error messages
                error_message = str(e).lower()
                
                if 'invalid_client' in error_message or 'unauthorized_client' in error_message or 'invalid client id or client secret' in error_message:
                    _flash_with_aadsts("Invalid Client ID or Client Secret", e)
                elif 'invalid_tenant' in error_message or 'tenant_not_found' in error_message or 'unable to get authority configuration' in error_message:
                    flash("Invalid Tenant ID. Please verify the tenant identifier is correct.", 'error')
                elif 'insufficient_privileges' in error_message or 'forbidden' in error_message:
                    flash("Insufficient privileges. The service principal may not have the required permissions.", 'error')
                elif 'network' in error_message or 'connection' in error_message or 'timeout' in error_message:
                    flash("Network error. Please check your internet connection and try again.", 'error')
                elif 'invalid_grant' in error_message:
                    flash("Invalid credentials. Please check your Client ID and Client Secret.", 'error')
                elif 'application with identifier' in error_message and 'was not found' in error_message:
                    _flash_with_aadsts("Application not found in tenant", e)
                else:
                    _flash_with_aadsts("Authentication error", e)
                
                return render_template('login.html')
        else:
            flash("Please fill in all required fields.", 'error')
            return render_template('login.html')
    
    return render_template('login.html')


@auth_bp.route('/logout')
def logout() -> Response:
    """Handle user logout."""
    return azure_logout()


@auth_bp.route('/get_token')
@require_auth
def get_token() -> Response:
    """Get current Graph API token."""
    return jsonify({'token': session['graph_token']})


@auth_bp.route('/refresh_token', methods=['POST'])
@require_auth
def refresh_token() -> Response:
    """Force token refresh if credentials available."""
    from app.auth.azure_auth import refresh_tokens_if_needed
    from app.auth.creds_manager import CredsManager
    
    creds = CredsManager.load_credentials()
    if not creds:
        return jsonify({
            'success': False,
            'message': 'No credentials available for token refresh. Please login with Service Principal.'
        }), 400
    
    try:
        success = refresh_tokens_if_needed()
        if success:
            return jsonify({
                'success': True,
                'message': 'Token refreshed successfully',
                'token': session.get('graph_token')
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Token refresh not needed or failed'
            }), 400
    except Exception as e:
        current_app.logger.error(f"Error refreshing token: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error refreshing token: {str(e)}'
        }), 500

