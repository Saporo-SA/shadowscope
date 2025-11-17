"""
Azure Roles Loader
Loads and caches Azure RBAC role definitions from AllAzureRoles.json
"""

import json
import os
from typing import Dict, List, Optional
from flask import current_app

class AzureRolesLoader:
    """Singleton class to load and cache Azure RBAC role definitions"""
    
    _instance = None
    _roles_cache = None
    _roles_by_id = None
    _roles_by_name = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AzureRolesLoader, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._roles_cache is None:
            self._load_roles()
    
    def _load_roles(self):
        """Load Azure roles from JSON file"""
        import logging
        logger = logging.getLogger(__name__)
        
        roles_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'AllAzureRoles.json')
        
        try:
            if not os.path.exists(roles_file):
                try:
                    current_app.logger.warning(f"AllAzureRoles.json not found at {roles_file}")
                except RuntimeError:
                    logger.warning(f"AllAzureRoles.json not found at {roles_file}")
                self._roles_cache = []
                self._roles_by_id = {}
                self._roles_by_name = {}
                return
            
            with open(roles_file, 'r', encoding='utf-8') as f:
                raw_roles = json.load(f)
            
            self._roles_cache = raw_roles if isinstance(raw_roles, list) else []
            self._roles_by_id = {role.get('RoleID'): role for role in self._roles_cache if role.get('RoleID')}
            self._roles_by_name = {role.get('RoleName'): role for role in self._roles_cache if role.get('RoleName')}
            
            try:
                current_app.logger.info(f"Loaded {len(self._roles_cache)} Azure RBAC roles")
            except RuntimeError:
                logger.info(f"Loaded {len(self._roles_cache)} Azure RBAC roles")
            
        except Exception as e:
            try:
                current_app.logger.error(f"Error loading Azure roles: {e}")
            except RuntimeError:
                logger.error(f"Error loading Azure roles: {e}")
            self._roles_cache = []
            self._roles_by_id = {}
            self._roles_by_name = {}
    
    def get_role_by_id(self, role_id: str) -> Optional[Dict]:
        """Get role definition by RoleID"""
        return self._roles_by_id.get(role_id)
    
    def get_role_by_name(self, role_name: str) -> Optional[Dict]:
        """Get role definition by RoleName"""
        return self._roles_by_name.get(role_name)
    
    def get_all_roles(self) -> List[Dict]:
        """Get all role definitions"""
        return self._roles_cache.copy() if self._roles_cache else []
    
    def reload(self):
        """Reload roles from file"""
        self._load_roles()

