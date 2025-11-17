"""
Background Data Collector
Collects data asynchronously in the background without blocking the UI
"""

import json
import os
import threading
import logging
from datetime import datetime
from typing import Dict, List
from app.utils.graph_api import GraphAPI
from app.modules.entraID.security_principals import SecurityPrincipals
from app.modules.entraID.roles import EntraIDRoles
from app.modules.entraID.groups import EntraIDGroups
from app.modules.azresources.subscriptions.subscriptions import AzureSubscriptions
from app.modules.azresources.management_groups.management_groups import AzureManagementGroups
from app.modules.azresources.resource_groups.resource_groups import AzureResourceGroups
from app.auth.permissions import AzurePermissions

logger = logging.getLogger(__name__)


class BackgroundDataCollector:
    """Collects data in background and caches it"""
    
    def __init__(self, graph_token: str, rest_token: str = None, user_permissions: List[str] = None):
        """
        Initialize background collector
        
        Args:
            graph_token: Microsoft Graph API token
            rest_token: Azure REST API token (optional)
            user_permissions: List of user permissions
        """
        self.graph_token = graph_token
        self.rest_token = rest_token
        self.user_permissions = user_permissions or []
        self.status = {
            'users': {'status': 'pending', 'progress': 0, 'error': None},
            'roles': {'status': 'pending', 'progress': 0, 'error': None},
            'groups': {'status': 'pending', 'progress': 0, 'error': None},
            'subscriptions': {'status': 'pending', 'progress': 0, 'error': None},
            'management_groups': {'status': 'pending', 'progress': 0, 'error': None},
            'resource_groups': {'status': 'pending', 'progress': 0, 'error': None},
        }
        self.collection_thread = None
        self.is_running = False
    
    def start_collection(self):
        """Start background data collection"""
        if self.is_running:
            return
        
        self.is_running = True
        self.collection_thread = threading.Thread(target=self._collect_all, daemon=True)
        self.collection_thread.start()
    
    def _collect_all(self):
        """Collect all data in priority order"""
        try:
            # Priority 1: Critical data (cache for quick access)
            self._collect_priority_1()
            
            # Priority 2: Important data
            if self.rest_token:
                self._collect_priority_2()
            
        except Exception as e:
            logger.error(f"Error in background collection: {e}", exc_info=True)
        finally:
            self.is_running = False
    
    def _collect_priority_1(self):
        """Collect critical data: Users, Roles, Groups"""
        try:
            permissions = AzurePermissions(self.user_permissions)
            graph = GraphAPI(self.graph_token)
            
            # Collect Users
            if permissions.has_base_access('users'):
                self.status['users']['status'] = 'collecting'
                try:
                    users_module = SecurityPrincipals(graph, self.user_permissions)
                    users = users_module.get_users()
                    if users:
                        self._save_cache('users.json', users)
                    self.status['users'] = {'status': 'completed', 'progress': 100, 'error': None}
                except Exception as e:
                    self.status['users'] = {'status': 'error', 'progress': 0, 'error': str(e)}
                    logger.error(f"Error collecting users: {e}", exc_info=True)
            
            # Collect Roles
            if permissions.has_base_access('roles'):
                self.status['roles']['status'] = 'collecting'
                try:
                    roles_module = EntraIDRoles(graph, self.user_permissions)
                    roles = roles_module.get_roles()
                    if roles:
                        self._save_cache('roles.json', roles)
                    self.status['roles'] = {'status': 'completed', 'progress': 100, 'error': None}
                except Exception as e:
                    self.status['roles'] = {'status': 'error', 'progress': 0, 'error': str(e)}
                    logger.error(f"Error collecting roles: {e}", exc_info=True)
            
            # Collect Groups
            if permissions.has_base_access('groups'):
                self.status['groups']['status'] = 'collecting'
                try:
                    groups_module = EntraIDGroups(graph, self.user_permissions)
                    groups = groups_module.get_groups()
                    if groups:
                        self._save_cache('groups.json', groups)
                    self.status['groups'] = {'status': 'completed', 'progress': 100, 'error': None}
                except Exception as e:
                    self.status['groups'] = {'status': 'error', 'progress': 0, 'error': str(e)}
                    logger.error(f"Error collecting groups: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"Error in priority 1 collection: {e}", exc_info=True)
    
    def _collect_priority_2(self):
        """Collect important data: Azure Resources"""
        if not self.rest_token:
            return
        
        try:
            # Collect Subscriptions
            self.status['subscriptions']['status'] = 'collecting'
            try:
                subscriptions_module = AzureSubscriptions(self.rest_token)
                result = subscriptions_module.list_subscriptions(limit=100, offset=0)
                if result and result.get('subscriptions'):
                    self._save_cache('subscriptions.json', {
                        'subscriptions': result.get('subscriptions', []),
                        'cached_at': datetime.now().isoformat()
                    })
                self.status['subscriptions'] = {'status': 'completed', 'progress': 100, 'error': None}
            except Exception as e:
                self.status['subscriptions'] = {'status': 'error', 'progress': 0, 'error': str(e)}
                logger.error(f"Error collecting subscriptions: {e}", exc_info=True)
            
            # Collect Management Groups
            self.status['management_groups']['status'] = 'collecting'
            try:
                mg_module = AzureManagementGroups(self.rest_token)
                result = mg_module.list_management_groups(limit=100)
                if result and result.get('management_groups'):
                    self._save_cache('management_groups.json', {
                        'management_groups': result.get('management_groups', []),
                        'cached_at': datetime.now().isoformat()
                    })
                self.status['management_groups'] = {'status': 'completed', 'progress': 100, 'error': None}
            except Exception as e:
                self.status['management_groups'] = {'status': 'error', 'progress': 0, 'error': str(e)}
                logger.error(f"Error collecting management groups: {e}", exc_info=True)
            
            # Collect Resource Groups
            self.status['resource_groups']['status'] = 'collecting'
            try:
                rg_module = AzureResourceGroups(self.rest_token)
                result = rg_module.list_resource_groups(limit=100)
                if result and result.get('resource_groups'):
                    self._save_cache('resource_groups.json', {
                        'resource_groups': result.get('resource_groups', []),
                        'cached_at': datetime.now().isoformat()
                    })
                self.status['resource_groups'] = {'status': 'completed', 'progress': 100, 'error': None}
            except Exception as e:
                self.status['resource_groups'] = {'status': 'error', 'progress': 0, 'error': str(e)}
                logger.error(f"Error collecting resource groups: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"Error in priority 2 collection: {e}", exc_info=True)
    
    def _save_cache(self, filename: str, data: Dict):
        """Save data to cache file"""
        cache_dir = 'results'
        os.makedirs(cache_dir, exist_ok=True)
        
        cache_path = os.path.join(cache_dir, filename)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving cache {filename}: {e}", exc_info=True)
    
    def get_status(self) -> Dict:
        """Get current collection status"""
        return self.status.copy()
    
    def is_complete(self) -> bool:
        """Check if all collections are complete"""
        return all(
            status['status'] in ['completed', 'error'] 
            for status in self.status.values()
        )

