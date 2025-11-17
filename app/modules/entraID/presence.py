from typing import Dict, Optional
from app.utils.graph_api import GraphAPI
from app.auth.permissions import AzurePermissions

class EntraIDPresence:
    def __init__(self, graph_client: GraphAPI, permissions: list):
        self.graph = graph_client
        self.permissions = permissions
        
    def _has_base_permission(self, resource_type: str) -> bool:
        return bool(AzurePermissions(self.permissions).has_base_access(resource_type))

    def get_presence(self, user_id: str) -> Optional[Dict]:
        if not self._has_base_permission('presence'):
            return None
        
        try:
            endpoint = f"users/{user_id}/presence"
            result = self.graph.get(endpoint)
            return result if result else None
        except Exception:
            return None