from app.utils.graph_api import GraphAPI
from app.auth.permissions import AzurePermissions
from typing import List, Dict, Optional
from flask import current_app

class EntraIDRoles:
    """
    Entra ID Directory Roles management class.
    
    Provides methods to manage Azure AD directory roles including listing roles,
    retrieving role details, and managing role assignments.
    """
    
    def __init__(self, graph_client: GraphAPI, permissions: List[str]):
        """
        Initialize Roles manager with Graph API client and permissions.
        
        Args:
            graph_client (GraphAPI): Authenticated Graph API client instance
            permissions (List[str]): List of Azure AD permissions for the current user
        """
        self.graph = graph_client
        self.permissions = permissions

    def get_roles(self, force_refresh: bool = False) -> List[Dict]:
        """Gets all directory roles."""
        try:
            roles = self.graph.get_paginated("directoryRoles")
            return roles if roles else []
        except Exception as e:
            current_app.logger.error(f"Error getting roles: {str(e)}")
            return []
    
    def get_role(self, role_id: str) -> Optional[Dict]:
        """Gets details of a specific role."""
        try:
            role = self.graph.get(f"directoryRoles/{role_id}")
            if role:
                role_permissions = self.graph.get(f"directoryRoles/{role_id}/rolePermissions")
                if role_permissions and 'value' in role_permissions:
                    role['rolePermissions'] = role_permissions.get('value', [])
                else:
                    role['rolePermissions'] = []
            return role
        except Exception as e:
            current_app.logger.error(f"Error getting role {role_id}: {str(e)}")
            return None
            
    def get_role_members(self, role_id: str) -> List[Dict]:
        """Gets members of a specific role."""
        try:
            role = self.get_role(role_id)
            if not role:
                return []
            
            members = self.graph.get_paginated(f"directoryRoles/{role_id}/members")
            return members if members else []
            
        except Exception as e:
            current_app.logger.error(f"Error getting members for role {role_id}: {str(e)}")
            
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    if 'error' in error_data:
                        error_code = error_data['error'].get('code', '')
                        if error_code in ['Authorization_RequestDenied', 'AccessDenied']:
                            return []
                except (ValueError, KeyError, TypeError) as parse_error:
                    current_app.logger.warning(f"Error parsing error response: {parse_error}")
                    
            return []
            
    def assign_role_to_user(self, role_id: str, user_id: str) -> bool:
        """Assigns a role to a user."""
        try:
            payload = {
                "@odata.id": f"{self.graph.base_url}/users/{user_id}"
            }
            response = self.graph.post(f"directoryRoles/{role_id}/members/$ref", payload)
            return response.status_code == 204
        except Exception as e:
            current_app.logger.error(f"Error assigning role {role_id} to user {user_id}: {str(e)}")
            return False
            
    def remove_role_from_user(self, role_id: str, user_id: str) -> bool:
        """Removes a role from a user."""
        try:
            response = self.graph.delete(f"directoryRoles/{role_id}/members/{user_id}/$ref")
            return response.status_code == 204
        except Exception as e:
            current_app.logger.error(f"Error removing role {role_id} from user {user_id}: {str(e)}")
            return False