from typing import Dict, List, Union
from app.auth.permissions import AzurePermissions
from app.utils.graph_api import GraphAPI
from flask import current_app
import requests

class EntraIDAdministrativeUnits:
    """
    Entra ID Administrative Units management class.
    
    Handles operations for Azure AD administrative units including listing,
    retrieving details, and managing administrative unit memberships.
    """
    
    def __init__(self, graph_client: GraphAPI, permissions: List[str]):
        """
        Initialize Administrative Units manager with Graph API client and permissions.
        
        Args:
            graph_client (GraphAPI): Authenticated Graph API client instance
            permissions (List[str]): List of Azure AD permissions for the current user
        """
        self.graph = graph_client
        self.permissions = permissions
        
    def _has_base_permission(self, resource_type: str) -> bool:
        return bool(AzurePermissions(self.permissions).has_base_access(resource_type))

    def _has_feature_permission(self, resource_type: str, feature: str) -> bool:
        return bool(AzurePermissions(self.permissions).has_feature_access(resource_type, feature))

    def get_administrative_units(self) -> List[Dict]:
        if not self._has_base_permission('admin_units'):
            return []
        return self.graph.get_paginated("directory/administrativeUnits")

    def get_administrative_unit(self, unit_id: str) -> Union[Dict, None]:
        if not self._has_base_permission('admin_units'):
            return None
        return self.graph.get(f"directory/administrativeUnits/{unit_id}")

    def get_administrative_unit_members(self, unit_id: str) -> List[Dict]:
        if not self._has_base_permission('admin_units'):
            return []
        return self.graph.get_paginated(f"directory/administrativeUnits/{unit_id}/members")

    def add_member_to_administrative_unit(self, unit_id: str, member_id: str) -> Dict:
        try:
            if not self._has_feature_permission('admin_units', 'manage_members'):
                return {"success": False, "message": "Insufficient permissions"}

            url = f"directory/administrativeUnits/{unit_id}/members/$ref"
            data = {"@odata.id": f"{self.graph.base_url}/users/{member_id}"}
            response = self.graph.post(url, data)
            
            # Check if the user is already a member
            if response.status_code == 400 and any(msg in response.text.lower() for msg in ["already exists", "conflicting object", "duplicate", "present in the directory"]):
                return {"success": False, "message": "User is already a member of this administrative unit"}
            
            # Check if the operation was successful
            if response.status_code in [204, 201]:
                return {"success": True, "message": "Member added successfully"}
                
            error_message = "Failed to add member"
            if hasattr(response, 'text') and response.text:
                try:
                    error_data = response.json()
                    error_message = error_data.get('error', {}).get('message', error_message)
                except (ValueError, KeyError, TypeError) as parse_error:
                    current_app.logger.warning(f"Error parsing error response: {parse_error}")
                    error_message = response.text
                    
            return {"success": False, "message": error_message}
            
        except requests.exceptions.HTTPError as e:
            current_app.logger.error(f"HTTP Error adding member to administrative unit: {e.response.text}")
            error_message = "Graph API Error"
            if hasattr(e.response, 'text') and e.response.text:
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('error', {}).get('message', error_message)
                except (ValueError, KeyError, TypeError) as parse_error:
                    current_app.logger.warning(f"Error parsing error response: {parse_error}")
                    error_message = e.response.text
            return {"success": False, "message": error_message}
        except Exception as e:
            current_app.logger.error(f"Unexpected error adding member to administrative unit: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def remove_member_from_administrative_unit(self, unit_id: str, member_id: str) -> Dict:
        try:
            if not self._has_feature_permission('admin_units', 'manage_members'):
                return {"success": False, "message": "Insufficient permissions"}

            url = f"directory/administrativeUnits/{unit_id}/members/{member_id}/$ref"
            response = self.graph.delete(url)
            
            if response.status_code == 204:
                return {"success": True, "message": "Member removed successfully"}
            return {"success": False, "message": "Failed to remove member"}
            
        except requests.exceptions.HTTPError as e:
            current_app.logger.error(f"HTTP Error removing member from administrative unit: {e.response.text}")
            return {"success": False, "message": f"Graph API Error: {e.response.text}"}