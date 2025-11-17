import time

from flask import redirect, url_for, session
from msal import ConfidentialClientApplication

from app.utils.jwt_parser import parse_jwt_token

def authenticate_service_principal(tenant_id, client_id, client_secret, api_type="graph_api"):
    """
    Authenticate a service principal and get an access token
    
    Args:
        tenant_id: Azure tenant ID
        client_id: Service Principal client ID
        client_secret: Service Principal client secret
        api_type: Type of API to authenticate for:
                 "graph_api" - Microsoft Graph API
                 "azure_ARM_api" - Azure Resource Management API
    
    Returns:
        Access token string or None if authentication failed
    """
    # Validate API type first
    if api_type == "graph_api":
        scopes = ["https://graph.microsoft.com/.default"]
    elif api_type == "azure_api":
        scopes = ["https://management.azure.com/.default"]
    else:
        raise ValueError(f"Unknown API type: {api_type}")
    
    try:
        # Configure MSAL client
        app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}"
        )
        
        # Get access token
        result = app.acquire_token_for_client(scopes=scopes)
        
        # Check for errors in the result
        if 'error' in result:
            error_code = result.get('error', '')
            error_description = result.get('error_description', '')
            
            if error_code == 'invalid_client':
                raise Exception(f"Invalid Client ID or Client Secret: {error_description}")
            elif error_code == 'invalid_tenant':
                raise Exception(f"Invalid Tenant ID: {error_description}")
            elif error_code == 'unauthorized_client':
                raise Exception(f"Unauthorized Client: {error_description}")
            elif error_code == 'invalid_grant':
                raise Exception(f"Invalid credentials: {error_description}")
            else:
                raise Exception(f"Authentication error ({error_code}): {error_description}")
        
        access_token = result.get('access_token')
        if not access_token:
            raise Exception("No access token received from authentication service")
        
        return access_token
        
    except Exception as e:
        # Re-raise the exception without adding extra text
        raise e

def authenticate_with_token(token):
    """Authenticates using a pre-generated token"""
    try:
        if token and token.strip():
            return token.strip()
        return None
    except Exception as e:
        # Token authentication failed
        return None

def azure_logout():
    """Performs secure logout and archives results folder"""
    from app.utils.archive_utils import archive_results_folder, cleanup_old_archives
    from app.auth.creds_manager import CredsManager
    
    # Delete .creds file
    try:
        CredsManager.delete_credentials()
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Error deleting credentials file: {str(e)}")
        except RuntimeError:
            import logging
            logging.getLogger(__name__).error(f"Error deleting credentials file: {str(e)}")
    
    # Archive results folder before logout
    try:
        archive_path = archive_results_folder()
        if archive_path:
            try:
                from flask import current_app
                current_app.logger.info(f"Results folder archived to: {archive_path}")
            except RuntimeError:
                # Not in Flask context, use regular logging
                import logging
                logging.getLogger(__name__).info(f"Results folder archived to: {archive_path}")
        
        # Clean up old archives (keep only last 10)
        cleanup_old_archives(max_archives=10)
        
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Error during results archiving: {str(e)}")
        except RuntimeError:
            # Not in Flask context, use regular logging
            import logging
            logging.getLogger(__name__).error(f"Error during results archiving: {str(e)}")
    
    # Clear local session
    session.clear()
    
    # Redirect to login page
    return redirect(url_for('auth.login'))

def get_tokens_for_all_apis(tenant_id, client_id, client_secret):
    """
    Gets access tokens for both Microsoft Graph API and Azure Management API
    
    Returns:
        Dictionary with keys 'graph_token' and 'rest_token'
    """
    try:
        graph_token = authenticate_service_principal(tenant_id, client_id, client_secret, "graph_api")
        rest_token = authenticate_service_principal(tenant_id, client_id, client_secret, "azure_api")
        
        # Check if tokens were obtained successfully
        if not graph_token:
            raise Exception("Failed to obtain Microsoft Graph API token. Check your credentials and permissions.")
        
        if not rest_token:
            raise Exception("Failed to obtain Azure Resource Management API token. Check your credentials and permissions.")
        
        return {
            'graph_token': graph_token,
            'rest_token': rest_token
        }
    except Exception as e:
        # Re-raise the exception without adding extra text
        raise e

def refresh_tokens_if_needed():
    """
    Check and refresh tokens if they are about to expire (< 5 minutes)
    Uses credentials from .creds file
    
    Returns:
        bool: True if tokens were checked/refreshed, False if no credentials available
    """
    from app.auth.creds_manager import CredsManager
    
    if 'graph_token' not in session:
        return False
    
    creds = CredsManager.load_credentials()
    if not creds:
        return False
    
    try:
        token_data = parse_jwt_token(session['graph_token'])
        if not token_data:
            return False
        
        exp = token_data.get('exp', 0)
        now = int(time.time())
        time_left = exp - now
        
        if time_left < 300:
            try:
                from flask import current_app
                current_app.logger.info(f"Token expiring in {time_left}s, refreshing...")
            except RuntimeError:
                pass
            
            session['graph_token'] = authenticate_service_principal(
                creds['tenant_id'],
                creds['client_id'],
                creds['client_secret'],
                "graph_api"
            )
            
            if 'rest_token' in session and session['rest_token']:
                rest_token_data = parse_jwt_token(session['rest_token'])
                if rest_token_data:
                    rest_exp = rest_token_data.get('exp', 0)
                    rest_time_left = rest_exp - now
                    
                    if rest_time_left < 300:
                        session['rest_token'] = authenticate_service_principal(
                            creds['tenant_id'],
                            creds['client_id'],
                            creds['client_secret'],
                            "azure_api"
                        )
            
            return True
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"Error refreshing tokens: {str(e)}")
        except RuntimeError:
            pass
        return False
    
    return True
