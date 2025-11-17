from typing import Dict, List, Union
from app.utils.graph_api import GraphAPI
from flask import current_app
from app.auth.permissions import AzurePermissions

class SecurityPrincipals:
    def __init__(self, graph_client: GraphAPI, permissions: List[str]):
        self.graph = graph_client
        self.permissions = permissions
        
    def _has_base_permission(self, resource_type: str) -> bool:
        return bool(AzurePermissions(self.permissions).has_base_access(resource_type))

    def _has_feature_permission(self, resource_type: str, feature: str) -> bool:
        return bool(AzurePermissions(self.permissions).has_feature_access(resource_type, feature))

    def get_users(self) -> Union[List[Dict], None]:
        if not self._has_base_permission('users'):
            return None
            
        try:
            users = self.graph.get_paginated("users")
            return [{
                **u,
                'type': 'user',
                'icon': 'bi-person'
            } for u in users]
        except Exception as e:
            current_app.logger.error(f"Error fetching users: {str(e)}")
            return None
            
    def get_user(self, user_id: str) -> Union[Dict, None]:
        """Get a specific user by ID"""
        if not self._has_base_permission('users'):
            return None
            
        try:
            # Request accountEnabled explicitly to ensure it's returned
            user = self.graph.get(f"users/{user_id}?$select=id,displayName,userPrincipalName,mail,jobTitle,department,officeLocation,accountEnabled,businessPhones,mobilePhone,preferredLanguage,givenName,surname")
            if user:
                return {
                    **user,
                    'type': 'user',
                    'icon': 'bi-person'
                }
            return None
        except Exception as e:
            current_app.logger.error(f"Error fetching user {user_id}: {str(e)}")
            return None