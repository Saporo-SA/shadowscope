"""
Entra ID Roles Loader
Loads and caches Entra ID role definitions from EntraIDRoleDefinitions.json
"""

import json
import os
from typing import Dict, List, Optional


class EntraRolesLoader:
    """Loads and provides access to Entra ID role definitions"""
    
    def __init__(self):
        """Initialize the loader and load role definitions"""
        self._roles_cache: Dict[str, Dict] = {}
        self._roles_by_name: Dict[str, Dict] = {}
        self._load_roles()
    
    def _load_roles(self):
        """Load Entra ID role definitions from JSON file"""
        import logging
        logger = logging.getLogger(__name__)
        
        roles_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'EntraIDRoleDefinitions.json')
        
        try:
            if not os.path.exists(roles_file):
                logger.warning(f"EntraIDRoleDefinitions.json not found at {roles_file}")
                self._roles_cache = {}
                self._roles_by_name = {}
                return
            
            with open(roles_file, 'r') as f:
                self._roles_cache = json.load(f)
            
            # Build name index
            for role_id, role_data in self._roles_cache.items():
                role_name = role_data.get('displayName', '').lower()
                if role_name:
                    self._roles_by_name[role_name] = role_data
            
            logger.info(f"Loaded {len(self._roles_cache)} Entra ID role definitions from cache")
            
        except Exception as e:
            logger.error(f"Error loading Entra ID role definitions: {e}")
            self._roles_cache = {}
            self._roles_by_name = {}
    
    def get_role_by_id(self, role_id: str) -> Optional[Dict]:
        """
        Get role definition by ID
        
        Args:
            role_id: The role definition ID
            
        Returns:
            Role definition dict or None if not found
        """
        return self._roles_cache.get(role_id)
    
    def get_role_by_name(self, role_name: str) -> Optional[Dict]:
        """
        Get role definition by display name (case-insensitive)
        
        Args:
            role_name: The role display name
            
        Returns:
            Role definition dict or None if not found
        """
        return self._roles_by_name.get(role_name.lower())
    
    def get_all_roles(self) -> Dict[str, Dict]:
        """
        Get all role definitions
        
        Returns:
            Dictionary of role_id -> role_definition
        """
        return self._roles_cache.copy()
    
    def search_roles(self, query: str) -> List[Dict]:
        """
        Search roles by name or description
        
        Args:
            query: Search query string
            
        Returns:
            List of matching role definitions
        """
        query_lower = query.lower()
        results = []
        
        for role_data in self._roles_cache.values():
            display_name = role_data.get('displayName', '').lower()
            description = role_data.get('description', '').lower()
            
            if query_lower in display_name or query_lower in description:
                results.append(role_data)
        
        return results

