from app.utils.graph_api import GraphAPI
from app.auth.permissions import AzurePermissions
from typing import Dict, List, Optional
import logging
from app.utils.jwt_parser import parse_jwt_token
from flask import current_app

logger = logging.getLogger(__name__)

class EntraIDServicePrincipals:
    """
    Entra ID Service Principals management class.
    
    Handles operations for Azure AD service principals including listing,
    retrieving details, managing permissions, and password/secret management.
    """
    
    def __init__(self, token: str):
        """
        Initialize Service Principals manager with authentication token.
        
        Args:
            token (str): Microsoft Graph API access token
        """
        self.graph_api = GraphAPI(token)
        token_data = parse_jwt_token(token)
        self.permissions = AzurePermissions(token_data.get('roles', []))

    def list_service_principals(self, filter_type: str = None):
        """
        Lists all Service Principals using pagination to ensure all are returned
        """
        try:
            endpoint = 'servicePrincipals'
            
            # Add filter if specified
            if filter_type:
                endpoint += f"?$filter=appOwnerOrganizationId eq '{filter_type}'"
                
            # Use the paginated method to get all items
            service_principals = self.graph_api.get_paginated(endpoint)
            
            if service_principals:
                # Add a limit of 500 to prevent overwhelming the UI
                return {
                    'success': True,
                    'data': service_principals[:500]  # Limit to 500 for performance
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to list Service Principals: Empty response'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to list Service Principals: {str(e)}"
            }
            
    def get_service_principal(self, service_principal_id: str):
        """
        Get a specific Service Principal and its permissions
        """
        try:
            # Get the service principal details
            url = f'/servicePrincipals/{service_principal_id}'
            sp_response = self.graph_api.get(url)
            
            if not sp_response:
                return {
                    'success': False,
                    'message': 'Service Principal not found'
                }
            
            service_principal = sp_response
            
            # First, get the Microsoft Graph Service Principal to map permission IDs to names
            graph_sp_filter = "displayName eq 'Microsoft Graph'"
            graph_sp_url = f'/servicePrincipals?$filter={graph_sp_filter}'
            graph_sp_response = self.graph_api.get(graph_sp_url)
            
            # Create a map of appRole IDs to display names for easy lookup
            app_role_map = {}
            if graph_sp_response and 'value' in graph_sp_response and len(graph_sp_response['value']) > 0:
                graph_sp = graph_sp_response['value'][0]
                if 'appRoles' in graph_sp:
                    for role in graph_sp['appRoles']:
                        app_role_map[role.get('id')] = {
                            'displayName': role.get('displayName', 'Unknown Permission'),
                            'description': role.get('description', ''),
                            'value': role.get('value', '')
                        }
            
            # Get appRoleAssignments for this service principal
            role_url = f'/servicePrincipals/{service_principal_id}/appRoleAssignments'
            role_response = self.graph_api.get(role_url)
            
            if role_response and 'value' in role_response:
                role_assignments = role_response.get('value', [])
                
                # Add friendly names using the map
                for role in role_assignments:
                    role_id = role.get('appRoleId')
                    if role_id in app_role_map:
                        role['permissionName'] = app_role_map[role_id]['displayName']
                        role['permissionValue'] = app_role_map[role_id]['value']
                        role['permissionDescription'] = app_role_map[role_id]['description']
                    else:
                        role['permissionName'] = 'Unknown Permission'
                        role['permissionValue'] = ''
                        role['permissionDescription'] = ''
                
                # Add the role assignments to the service principal object
                service_principal['appRoleAssignments'] = role_assignments
            else:
                service_principal['appRoleAssignments'] = []
            
            return {
                'success': True,
                'data': service_principal
            }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Failed to get Service Principal: {str(e)}"
            }
            
    def add_password(self, service_principal_id: str):
        """
        Adds a new password (secret) to the Service Principal
        Args:
            service_principal_id: ID do Service Principal
            display_name: Nome do secret
            
        Returns:
            Dictionary with the operation result
        """
        try:
            # Check permissions
            if not self.permissions.check_access().get('service_principals', {}).get('features', {}).get('manage_apps', False):
                return {
                    'success': False,
                    'message': 'Insufficient permissions to add passwords to Service Principals'
                }
                
            # Create the request payload
            payload = {
                "passwordCredential": {
                    "displayName": 'Microsoft Graph API Services'
                }
            }
            
            # First, get the service principal to determine its type
            sp_response = self.graph_api.get(f'servicePrincipals/{service_principal_id}')
            if not sp_response or 'appId' not in sp_response:
                return {
                    'success': False,
                    'message': 'Failed to get service principal or appId not found',
                    'code': 'ServicePrincipalNotFound'
                }
            
            app_id = sp_response['appId']
            service_principal_type = sp_response.get('servicePrincipalType', '')
            tags = sp_response.get('tags', [])
            
            # Check if it's a managed identity
            is_managed_identity = (
                service_principal_type == 'ManagedIdentity' or
                'tags' in sp_response and 'WindowsAzureActiveDirectoryManagedIdentity' in sp_response['tags']
            )
            
            if is_managed_identity:
                # Managed identities cannot have passwords/secrets added
                return {
                    'success': False,
                    'message': 'Managed identities cannot have passwords/secrets added.',
                    'code': 'ManagedIdentityNotSupported'
                }
            else:
                # For enterprise apps, first try to find the registered application
                app_filter = f"appId eq '{app_id}'"
                app_response = self.graph_api.get(f'applications?$filter={app_filter}')
                
                if app_response and 'value' in app_response and app_response['value']:
                    # Application found - use applications endpoint
                    application_id = app_response['value'][0]['id']
                    response = self.graph_api.post(f'applications/{application_id}/addPassword', payload)
                else:
                    # Application not found - this is an enterprise app without registered application
                    # Use servicePrincipals endpoint as fallback
                    response = self.graph_api.post(f'servicePrincipals/{service_principal_id}/addPassword', payload)
            
            if not response:
                return {
                    'success': False,
                    'message': 'Empty response from Graph API',
                    'code': 'EmptyResponse'
                }

            # Parse response even for errors
            response_data = response.json()
            if 'error' in response_data:
                error_code = response_data['error'].get('code', 'UnknownError')
                error_message = response_data['error'].get('message', 'Unknown error')
                return {
                    'success': False,
                    'message': error_message,
                    'code': error_code
                }

            return {
                'success': True,
                'data': response_data
            }
                
        except Exception as e:
            error_message = str(e)
            error_code = 'UnknownError'
            if "CannotUpdateLockedServicePrincipalProperty" in error_message:
                error_code = 'CannotUpdateLockedServicePrincipalProperty'
                error_message = "Cannot add secret: Service principal is locked."
            return {
                'success': False,
                'message': error_message,
                'code': error_code
            }
            
    def get_graph_permissions(self):
        """
        Retrieves all available Microsoft Graph API permissions
        
        Returns:
            Dictionary with the operation result
        """
        try:
            # Check permissions
            if not self.permissions.has_feature_access('service_principals', 'manage_role_assignments'):
                return {
                    'success': False,
                    'message': 'Insufficient permissions to view Graph API permissions'
                }
                
            # Get Microsoft Graph Service Principal
            graph_sp_filter = "displayName eq 'Microsoft Graph'"
            graph_sp_url = f'/servicePrincipals?$filter={graph_sp_filter}'
            graph_sp_response = self.graph_api.get(graph_sp_url)
            
            if not graph_sp_response or 'value' not in graph_sp_response or not graph_sp_response['value']:
                return {
                    'success': False,
                    'message': 'Microsoft Graph service principal not found'
                }
                
            graph_sp = graph_sp_response['value'][0]
            
            # Extract app roles (permissions)
            if 'appRoles' not in graph_sp or not graph_sp['appRoles']:
                return {
                    'success': False,
                    'message': 'No permissions found in Microsoft Graph service principal'
                }
                
            # Format permissions for easier consumption
            permissions = []
            for role in graph_sp['appRoles']:
                # Skip permissions that are not applicable to applications
                # isEnabled=true filter ensures the permission is active
                # allowedMemberTypes contains 'Application' ensures it can be assigned to apps
                if role.get('isEnabled', False) and 'Application' in role.get('allowedMemberTypes', []):
                    permissions.append({
                        'id': role.get('id'),
                        'displayName': role.get('displayName', 'Unknown Permission'),
                        'description': role.get('description', ''),
                        'value': role.get('value', '')
                    })
            
            # Sort permissions by display name
            permissions = sorted(permissions, key=lambda x: x.get('displayName', '').lower())
            
            return {
                'success': True,
                'data': permissions
            }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Error retrieving Graph permissions: {str(e)}"
            }
            
    def add_permissions(self, service_principal_id: str, permission_ids: list):
        """
        Adds one or more permissions (appRoles) to a service principal
        
        Args:
            service_principal_id: ID of the service principal
            permission_ids: List of permission IDs to add
            
        Returns:
            Dictionary with the operation result
        """
        try:
            # Check permissions
            if not self.permissions.has_feature_access('service_principals', 'manage_role_assignments'):
                return {
                    'success': False,
                    'message': 'Insufficient permissions to manage app permissions'
                }
                
            # Get Microsoft Graph Service Principal ID
            graph_sp_filter = "displayName eq 'Microsoft Graph'"
            graph_sp_url = f'/servicePrincipals?$filter={graph_sp_filter}'
            graph_sp_response = self.graph_api.get(graph_sp_url)
            
            if not graph_sp_response or 'value' not in graph_sp_response or not graph_sp_response['value']:
                return {
                    'success': False,
                    'message': 'Microsoft Graph service principal not found'
                }
                
            graph_sp_id = graph_sp_response['value'][0]['id']
            
            # Get existing permissions to avoid duplicates
            role_url = f'/servicePrincipals/{service_principal_id}/appRoleAssignments'
            role_response = self.graph_api.get(role_url)
            
            existing_permissions = []
            if role_response and 'value' in role_response:
                existing_permissions = [role.get('appRoleId') for role in role_response.get('value', [])]
            
            # Add each permission
            success_count = 0
            failed_permissions = []
            skipped_permissions = []
            
            for permission_id in permission_ids:
                # Skip if already assigned
                if permission_id in existing_permissions:
                    skipped_permissions.append(permission_id)
                    continue
                    
                # Create the request payload according to Microsoft documentation
                # https://learn.microsoft.com/en-us/graph/api/serviceprincipal-post-approleassignments
                payload = {
                    "principalId": service_principal_id,
                    "resourceId": graph_sp_id,
                    "appRoleId": permission_id
                }
                
                # Make the API request
                try:
                    response = self.graph_api.post(f'servicePrincipals/{service_principal_id}/appRoleAssignments', payload)
                    
                    if response and response.status_code < 300:
                        success_count += 1
                    else:
                        failed_permissions.append(permission_id)
                        current_app.logger.warning(f"Permission {permission_id} failed to add")
                        
                except Exception as e:
                    current_app.logger.error(f"Exception adding permission {permission_id}: {str(e)}")
                    failed_permissions.append(permission_id)
            
            # Calculate effective result
            new_permissions_count = len(permission_ids) - len(skipped_permissions)
            
            if len(skipped_permissions) == len(permission_ids):
                # All permissions were already assigned
                result = {
                    'success': True,
                    'message': f'All {len(permission_ids)} permission(s) were already assigned'
                }
            elif success_count == new_permissions_count:
                # All new permissions were added successfully
                if len(skipped_permissions) > 0:
                    result = {
                        'success': True,
                        'message': f'Successfully added {success_count} new permission(s), {len(skipped_permissions)} already existed'
                    }
                else:
                    result = {
                        'success': True,
                        'message': f'Successfully added {success_count} permission(s)'
                    }
            elif success_count > 0:
                result = {
                    'success': True,
                    'message': f'Added {success_count} permission(s), {len(failed_permissions)} failed, {len(skipped_permissions)} already existed'
                }
            else:
                if len(skipped_permissions) > 0:
                    result = {
                        'success': True,
                        'message': f'No new permissions added - {len(skipped_permissions)} already existed, {len(failed_permissions)} failed'
                    }
                else:
                    result = {
                        'success': False,
                        'message': 'Failed to add any permissions'
                    }
            
            return result
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Error adding permissions: {str(e)}"
            }

    def get_service_principal_permissions(self, service_principal_id: str):
        """
        Gets the current permissions assigned to a service principal
        
        Args:
            service_principal_id: ID of the service principal
            
        Returns:
            Dictionary with the operation result
        """
        try:
            
            # Check permissions
            if not self.permissions.has_feature_access('service_principals', 'manage_role_assignments'):
                return {
                    'success': False,
                    'message': 'Insufficient permissions to view app permissions'
                }
                
            # Get Microsoft Graph Service Principal ID and permissions
            graph_sp_filter = "displayName eq 'Microsoft Graph'"
            graph_sp_url = f'/servicePrincipals?$filter={graph_sp_filter}&$select=id,appRoles'
            graph_sp_response = self.graph_api.get(graph_sp_url)
            
            if not graph_sp_response or 'value' not in graph_sp_response or not graph_sp_response['value']:
                return {
                    'success': False,
                    'message': 'Microsoft Graph service principal not found'
                }
                
            graph_sp = graph_sp_response['value'][0]
            graph_sp_id = graph_sp['id']
            available_permissions = {role['id']: role for role in graph_sp.get('appRoles', [])}
            
            # Get current permissions assigned to this service principal
            role_url = f'/servicePrincipals/{service_principal_id}/appRoleAssignments'
            role_response = self.graph_api.get(role_url)
            
            assigned_permissions = []
            if role_response and 'value' in role_response:
                for assignment in role_response['value']:
                    # Only include Microsoft Graph permissions
                    if assignment.get('resourceId') == graph_sp_id:
                        app_role_id = assignment.get('appRoleId')
                        
                        if app_role_id in available_permissions:
                            permission_info = available_permissions[app_role_id]
                            assigned_permissions.append({
                                'id': app_role_id,
                                'value': permission_info.get('value', ''),
                                'displayName': permission_info.get('displayName', ''),
                                'description': permission_info.get('description', ''),
                                'assignedAt': assignment.get('createdDateTime', ''),
                                'assignmentId': assignment.get('id', '')
                            })
                        else:
                            current_app.logger.warning(f"Permission ID {app_role_id} not found in available permissions")
            
            return {
                'success': True,
                'permissions': assigned_permissions,
                'count': len(assigned_permissions)
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f"Error getting service principal permissions: {str(e)}"
            }