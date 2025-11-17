from typing import Dict, List, Union
from app.utils.graph_api import GraphAPI
from app.auth.permissions import AzurePermissions
from flask import current_app
import requests

class EntraIDGroups:
    """
    Entra ID Groups management class.
    
    Provides methods to manage Azure AD groups including listing groups,
    retrieving group details, and managing group memberships.
    """
    
    def __init__(self, graph_client: GraphAPI, permissions: List[str]):
        """
        Initialize Groups manager with Graph API client and permissions.
        
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

    def get_groups(self) -> List[Dict]:
        return self.graph.get_paginated("groups")

    def get_group(self, group_id: str) -> Union[Dict, None]:
        return self.graph.get(f"groups/{group_id}?$select=id,displayName,onPremisesSyncEnabled,isAssignableToRole,membershipRule")

    def get_group_members(self, group_id: str) -> List[Dict]:
        return self.graph.get_paginated(f"groups/{group_id}/members")

    def add_member_to_group(self, group_id: str, member_id: str) -> Dict:
        try:
            if not self._has_feature_permission('groups','manage_members'):
                return {"success": False, "message": "Insufficient permissions"}

            url = f"groups/{group_id}/members/$ref"
            data = {"@odata.id": f"{self.graph.base_url}/users/{member_id}"}
            response = self.graph.post(url, data)
            
            if response.status_code == 204:
                return {"success": True, "message": "Member added successfully"}
            return {"success": False, "message": "Failed to add member"}
            
        except requests.exceptions.HTTPError as e:
            current_app.logger.error(f"HTTP Error adding member to group: {e.response.text}")
            return {"success": False, "message": f"Graph API Error: {e.response.text}"}
        except Exception as e:
            current_app.logger.error(f"Unexpected error adding member to group: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}

    def remove_member_from_group(self, group_id: str, member_id: str) -> Dict:
        try:
            if not self._has_base_permission('groups'):
                return {"success": False, "message": "No base permissions for groups"}
            
            if not self._has_feature_permission('groups','manage_members'):
                return {"success": False, "message": "No permissions to manage members"}

            url = f"groups/{group_id}/members/{member_id}/$ref"
            response = self.graph.delete(url)
            
            if response.status_code == 204:
                return {"success": True, "message": "Member removed successfully"}
            return {"success": False, "message": "Failed to remove member"}
            
        except requests.exceptions.HTTPError as e:
            current_app.logger.error(f"HTTP Error removing member from group: {e.response.text}")
            return {"success": False, "message": f"Graph API Error: {e.response.text}"}
        except Exception as e:
            current_app.logger.error(f"Unexpected error removing member from group: {str(e)}")
            return {"success": False, "message": f"Unexpected error: {str(e)}"}