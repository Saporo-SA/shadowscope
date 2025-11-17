"""
User Roles Manager
Aggregates Entra ID directory roles and Azure RBAC roles for a user
"""

import json
import os
import logging
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.utils.graph_api import GraphAPI
from app.modules.entraID.roles import EntraIDRoles
from app.modules.azresources.list_azresources import AzureResourceManager
from app.utils.azure_roles_loader import AzureRolesLoader
from app.utils.entra_roles_loader import EntraRolesLoader

logger = logging.getLogger(__name__)


class UserRolesManager:
    """Manages and aggregates all roles (Entra ID + Azure RBAC) for a user with parallel processing"""
    
    def __init__(self, graph_token: str = None, rest_token: str = None, max_workers: int = 10):
        try:
            from flask import session
            self.graph_token = graph_token if graph_token is not None else session.get('graph_token')
            self.rest_token = rest_token if rest_token is not None else session.get('rest_token')
        except RuntimeError:
            self.graph_token = graph_token
            self.rest_token = rest_token
        
        self.max_workers = max_workers
        self._role_cache = {}  # Cache for role definitions to avoid duplicate API calls
        
        if self.graph_token:
            self.graph_api = GraphAPI(self.graph_token, use_beta=True)
            self.entra_roles = EntraIDRoles(self.graph_api, [])
        else:
            self.graph_api = None
            self.entra_roles = None
        
        self.entra_roles_loader = EntraRolesLoader()
        
        if self.rest_token:
            self.resource_manager = AzureResourceManager(self.rest_token)
            self.azure_roles_loader = AzureRolesLoader()
        else:
            self.resource_manager = None
            self.azure_roles_loader = None
    
    def _get_entra_id_roles(self, user_id: str, user_groups: List[Dict] = None) -> List[Dict]:
        entra_roles = []
        role_ids_seen = {}
        
        try:
            # First, get DIRECT role assignments to identify which are truly direct
            # This is needed because transitiveRoleAssignments filters by user_id,
            # so principal_id will always be user_id, making it impossible to distinguish
            direct_assignments = set()
            try:
                direct_endpoint = f"roleManagement/directory/roleAssignments?$count=true&$filter=principalId eq '{user_id}'"
                direct_response = self.graph_api.get(direct_endpoint, custom_headers={'ConsistencyLevel': 'eventual'}, raw_response=True)
                if direct_response and direct_response.status_code == 200:
                    direct_data = direct_response.json()
                    direct_values = direct_data.get('value', [])
                    for direct_assignment in direct_values:
                        role_def_id = direct_assignment.get('roleDefinitionId')
                        directory_scope_raw = direct_assignment.get('directoryScopeId')
                        directory_scope = directory_scope_raw if directory_scope_raw else '/'
                        direct_key = f"{role_def_id}:{directory_scope}"
                        direct_assignments.add(direct_key)
                elif direct_response:
                    logger.warning(f"Direct role assignments request returned status {direct_response.status_code}")
            except Exception as e:
                logger.error(f"Could not fetch direct role assignments: {e}", exc_info=True)
            
            # Now get ALL transitive role assignments (direct + inherited)
            # This will include roles assigned directly AND via groups
            transitive_endpoint = f"roleManagement/directory/transitiveRoleAssignments?$count=true&$filter=principalId eq '{user_id}'"
            
            group_role_assignments = {}
            if user_groups:
                def fetch_group_roles(group):
                    group_id = group.get('id')
                    group_name = group.get('displayName', group_id)
                    try:
                        group_roles_endpoint = f"roleManagement/directory/roleAssignments?$count=true&$filter=principalId eq '{group_id}'"
                        group_roles_response = self.graph_api.get(group_roles_endpoint, custom_headers={'ConsistencyLevel': 'eventual'}, raw_response=True)
                        if group_roles_response and group_roles_response.status_code == 200:
                            group_roles_data = group_roles_response.json()
                            group_assignments = group_roles_data.get('value', [])
                            if group_assignments:
                                return (group_id, {
                                    'assignments': group_assignments,
                                    'group_name': group_name
                                })
                    except Exception:
                        pass
                    return None
                
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    results = executor.map(fetch_group_roles, user_groups)
                    for result in results:
                        if result:
                            group_id, group_data = result
                            group_role_assignments[group_id] = group_data
            
            try:
                response = self.graph_api.get(transitive_endpoint, custom_headers={'ConsistencyLevel': 'eventual'}, raw_response=True)
                if not response:
                    raise Exception("Failed to get transitive role assignments")
                response.raise_for_status()
                data = response.json()
                transitive_assignments = data.get('value', [])
                
                # Build a map of group IDs to group names for quick lookup
                group_map = {}
                if user_groups:
                    for group in user_groups:
                        group_map[group.get('id')] = group.get('displayName', group.get('id'))
                
                processed_role_keys = set()
                
                for assignment in transitive_assignments:
                    role_def_id = assignment.get('roleDefinitionId')
                    principal_id = assignment.get('principalId')
                    directory_scope_raw = assignment.get('directoryScopeId')
                    directory_scope = directory_scope_raw if directory_scope_raw else '/'
                    role_key = f"{role_def_id}:{directory_scope}"
                    is_direct = role_key in direct_assignments
                    
                    inherited_from_group = None
                    if not is_direct:
                        for group_id, group_data in group_role_assignments.items():
                            for group_assignment in group_data['assignments']:
                                group_role_def_id = group_assignment.get('roleDefinitionId')
                                group_directory_scope_raw = group_assignment.get('directoryScopeId')
                                group_directory_scope = group_directory_scope_raw if group_directory_scope_raw else '/'
                                group_role_key = f"{group_role_def_id}:{group_directory_scope}"
                                
                                if group_role_key == role_key:
                                    inherited_from_group = group_data['group_name']
                                    break
                            if inherited_from_group:
                                break
                    
                    assignment_type = 'Direct' if is_direct else 'Inherited'
                    
                    # Get role details from cache
                    if role_def_id not in role_ids_seen:
                        role_detail = self.entra_roles_loader.get_role_by_id(role_def_id)
                        
                        if role_detail:
                            role_ids_seen[role_def_id] = {
                                'role_name': role_detail.get('displayName', 'Unknown'),
                                'role_description': role_detail.get('description', ''),
                                'role_template_id': role_detail.get('id', role_def_id)
                            }
                        else:
                            logger.warning(f"Role definition {role_def_id} not found in cache")
                            role_ids_seen[role_def_id] = {
                                'role_name': 'Unknown',
                                'role_description': '',
                                'role_template_id': role_def_id
                            }
                    
                    role_info = role_ids_seen[role_def_id]
                    
                    if not directory_scope_raw or directory_scope_raw == '/':
                        scope = 'Tenant'
                    elif directory_scope_raw.startswith('/administrativeUnits/'):
                        scope = f'Administrative Unit: {directory_scope_raw.split("/")[-1]}'
                    elif directory_scope_raw.startswith('/') and len(directory_scope_raw) > 1:
                        app_id = directory_scope_raw.lstrip('/')
                        scope = f'Application: {app_id}'
                    else:
                        scope = 'Tenant'
                    
                    assignment_source = 'Directory Role'
                    if not is_direct:
                        if inherited_from_group:
                            assignment_source = f'Group: {inherited_from_group}'
                        elif principal_id in group_map:
                            assignment_source = f'Group: {group_map[principal_id]}'
                        elif principal_id != user_id:
                            assignment_source = f'Group: {principal_id}'
                        else:
                            assignment_source = 'Group: Unknown'
                    
                    entra_roles.append({
                        'role_id': role_def_id,
                        'role_name': role_info['role_name'],
                        'role_description': role_info['role_description'],
                        'role_template_id': role_info['role_template_id'],
                        'scope': scope,
                        'scope_type': 'EntraID',
                        'assignment_type': assignment_type,
                        'assignment_source': assignment_source
                    })
                    
                    # Track that we've processed this role+scope combination
                    processed_role_keys.add(role_key)
                
                for group_id, group_data in group_role_assignments.items():
                    group_name = group_data['group_name']
                    for group_assignment in group_data['assignments']:
                        group_role_def_id = group_assignment.get('roleDefinitionId')
                        group_directory_scope_raw = group_assignment.get('directoryScopeId')
                        group_directory_scope = group_directory_scope_raw if group_directory_scope_raw else '/'
                        group_role_key = f"{group_role_def_id}:{group_directory_scope}"
                        is_also_direct = group_role_key in direct_assignments
                        
                        if is_also_direct or group_role_key not in processed_role_keys:
                            if group_role_def_id not in role_ids_seen:
                                role_detail = self.entra_roles_loader.get_role_by_id(group_role_def_id)
                                
                                if role_detail:
                                    role_ids_seen[group_role_def_id] = {
                                        'role_name': role_detail.get('displayName', 'Unknown'),
                                        'role_description': role_detail.get('description', ''),
                                        'role_template_id': role_detail.get('id', group_role_def_id)
                                    }
                                else:
                                    role_ids_seen[group_role_def_id] = {
                                        'role_name': 'Unknown',
                                        'role_description': '',
                                        'role_template_id': group_role_def_id
                                    }
                            
                            group_role_info = role_ids_seen[group_role_def_id]
                            
                            if not group_directory_scope_raw or group_directory_scope_raw == '/':
                                group_scope = 'Tenant'
                            elif group_directory_scope_raw.startswith('/administrativeUnits/'):
                                group_scope = f'Administrative Unit: {group_directory_scope_raw.split("/")[-1]}'
                            elif group_directory_scope_raw.startswith('/') and len(group_directory_scope_raw) > 1:
                                app_id = group_directory_scope_raw.lstrip('/')
                                group_scope = f'Application: {app_id}'
                            else:
                                group_scope = 'Tenant'
                            
                            entra_roles.append({
                                'role_id': group_role_def_id,
                                'role_name': group_role_info['role_name'],
                                'role_description': group_role_info['role_description'],
                                'role_template_id': group_role_info['role_template_id'],
                                'scope': group_scope,
                                'scope_type': 'EntraID',
                                'assignment_type': 'Inherited',
                                'assignment_source': f'Group: {group_name}'
                            })
                            
                            if not is_also_direct:
                                processed_role_keys.add(group_role_key)
                
            except Exception as e:
                logger.error(f"Error using transitiveRoleAssignments API: {e}")
            
        except Exception as e:
            logger.error(f"Error getting Entra ID roles for user {user_id}: {e}")
        
        return entra_roles
    
    def _get_azure_rbac_roles(self, user_id: str) -> List[Dict]:
        azure_roles = []
        
        if not self.resource_manager:
            logger.warning("Resource manager not available for Azure RBAC roles")
            return azure_roles
        
        try:
            user_object_id = user_id
            
            # Load subscriptions from cache or API
            subscriptions = self._load_subscriptions_from_cache()
            if not subscriptions:
                subscriptions = self._fetch_subscriptions_from_api()
                if not subscriptions:
                    return azure_roles
            
            # Process all sources in parallel
            with ThreadPoolExecutor(max_workers=3) as executor:
                # Submit all three main tasks concurrently
                future_mg = executor.submit(self._get_management_group_roles, user_object_id)
                future_sub = executor.submit(self._get_subscription_roles, user_object_id, subscriptions)
                future_rg = executor.submit(self._get_resource_group_roles_optimized, user_object_id, subscriptions)
                
                # Collect results as they complete
                for future in as_completed([future_mg, future_sub, future_rg]):
                    try:
                        roles = future.result()
                        azure_roles.extend(roles)
                    except Exception as e:
                        logger.error(f"Error in parallel role fetching: {e}")
            
        except Exception as e:
            logger.error(f"Error getting Azure RBAC roles for {user_id}: {e}", exc_info=True)
        
        return azure_roles
    
    def _load_subscriptions_from_cache(self) -> List[Dict]:
        """Load subscriptions from cache file"""
        subscriptions_cache_path = 'results/subscriptions.json'
        try:
            if os.path.exists(subscriptions_cache_path):
                with open(subscriptions_cache_path, 'r') as f:
                    cached_data = json.load(f)
                    subscriptions = cached_data.get('subscriptions', [])
                    if subscriptions:
                        return subscriptions
        except Exception as e:
            pass
        return []
    
    def _fetch_subscriptions_from_api(self) -> List[Dict]:
        """Fetch subscriptions from Azure API"""
        try:
            subscriptions_url = "https://management.azure.com/subscriptions?api-version=2020-01-01"
            subscriptions_response = self.resource_manager._make_request(subscriptions_url)
            return subscriptions_response.get('value', [])
        except Exception as e:
            logger.error(f"Error fetching subscriptions from API: {e}")
            return []
    
    def _get_management_group_roles(self, user_object_id: str) -> List[Dict]:
        roles = []
        
        try:
            # Load management groups from cache or API
            management_groups = self._load_management_groups_from_cache()
            if not management_groups:
                management_groups = self._fetch_management_groups_from_api()
            
            if not management_groups:
                return roles
            
            # Process management groups in parallel
            def fetch_mg_roles(mg):
                mg_roles = []
                mg_id_raw = mg.get('id') or mg.get('name')
                if '/providers/Microsoft.Management/managementGroups/' in str(mg_id_raw):
                    mg_id = str(mg_id_raw).split('/providers/Microsoft.Management/managementGroups/')[-1].split('/')[0]
                else:
                    mg_id = mg_id_raw
                mg_name = mg.get('displayName') or mg.get('name') or mg_id
                
                try:
                    roles_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{user_object_id}'"
                    roles_response = self.resource_manager._make_request(roles_url)
                    
                    if roles_response and 'value' in roles_response:
                        for assignment in roles_response.get('value', []):
                            role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                            role_info = self._get_role_info(role_def_id)
                            
                            mg_roles.append({
                                'role_id': role_def_id,
                                'role_name': role_info.get('name', 'Unknown Role'),
                                'role_description': role_info.get('description', ''),
                                'scope': assignment.get('properties', {}).get('scope', ''),
                                'scope_type': 'ManagementGroup',
                                'scope_name': mg_name,
                                'assignment_type': 'Direct',
                                'assignment_source': f'Management Group: {mg_name}'
                            })
                except Exception as e:
                    pass
                
                return mg_roles
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(fetch_mg_roles, mg) for mg in management_groups]
                for future in as_completed(futures):
                    try:
                        mg_roles = future.result()
                        roles.extend(mg_roles)
                    except Exception as e:
                        logger.error(f"Error processing management group: {e}")
                    
        except Exception as e:
            logger.error(f"Error getting management group roles: {e}")
        
        return roles
    
    def _load_management_groups_from_cache(self) -> List[Dict]:
        """Load management groups from cache file"""
        mg_cache_path = 'results/management_groups.json'
        try:
            if os.path.exists(mg_cache_path):
                with open(mg_cache_path, 'r') as f:
                    cached_data = json.load(f)
                    mgs = cached_data.get('management_groups', [])
                    if mgs:
                        return mgs
        except Exception as e:
            pass
        return []
    
    def _fetch_management_groups_from_api(self) -> List[Dict]:
        """Fetch management groups from Azure API"""
        try:
            mg_url = "https://management.azure.com/providers/Microsoft.Management/managementGroups?api-version=2020-05-01"
            mg_response = self.resource_manager._make_request(mg_url)
            return mg_response.get('value', [])
        except Exception as e:
            logger.error(f"Error fetching management groups from API: {e}")
            return []
    
    def _get_subscription_roles(self, user_object_id: str, subscriptions: List[Dict]) -> List[Dict]:
        roles = []
        
        def fetch_sub_roles(sub):
            sub_roles = []
            sub_id = sub.get('subscriptionId') or sub.get('id')
            sub_name = sub.get('displayName') or sub.get('name') or sub_id
            
            if not sub_id:
                return sub_roles
            
            try:
                roles_url = f"https://management.azure.com/subscriptions/{sub_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{user_object_id}'"
                roles_response = self.resource_manager._make_request(roles_url)
                
                if roles_response and 'value' in roles_response:
                    for assignment in roles_response.get('value', []):
                        scope = assignment.get('properties', {}).get('scope', '')
                        
                        # Only include subscription-level assignments, not resource group level
                        if scope.count('/') == 2:  # /subscriptions/{id} format
                            role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                            role_info = self._get_role_info(role_def_id)
                            
                            sub_roles.append({
                                'role_id': role_def_id,
                                'role_name': role_info.get('name', 'Unknown Role'),
                                'role_description': role_info.get('description', ''),
                                'scope': scope,
                                'scope_type': 'Subscription',
                                'scope_name': sub_name,
                                'assignment_type': 'Direct',
                                'assignment_source': f'Subscription: {sub_name}'
                            })
            except Exception as e:
                pass
            
            return sub_roles
        
        # Process subscriptions in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(fetch_sub_roles, sub) for sub in subscriptions]
            for future in as_completed(futures):
                try:
                    sub_roles = future.result()
                    roles.extend(sub_roles)
                except Exception as e:
                    logger.error(f"Error processing subscription: {e}")
        
        return roles
    
    def _get_resource_group_roles_optimized(self, user_object_id: str, subscriptions: List[Dict]) -> List[Dict]:
        """
        OPTIMIZED: Fetch ALL role assignments at subscription level and filter by resource group scope.
        This eliminates hundreds of individual API calls per resource group.
        """
        roles = []
        
        def fetch_rg_roles_from_subscription(sub):
            rg_roles = []
            sub_id = sub.get('subscriptionId') or sub.get('id')
            sub_name = sub.get('displayName') or sub.get('name') or sub_id
            
            if not sub_id:
                return rg_roles
            
            try:
                # Fetch ALL role assignments for the subscription (includes resource group scopes)
                roles_url = f"https://management.azure.com/subscriptions/{sub_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{user_object_id}'"
                roles_response = self.resource_manager._make_request(roles_url)
                
                if roles_response and 'value' in roles_response:
                    for assignment in roles_response.get('value', []):
                        scope = assignment.get('properties', {}).get('scope', '')
                        if scope.lower().count('/resourcegroups/') > 0 and scope.count('/') == 4:
                            parts = scope.split('/')
                            if len(parts) == 5: 
                                rg_name = parts[4]
                                
                                role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                                role_info = self._get_role_info(role_def_id)
                                
                                rg_roles.append({
                                    'role_id': role_def_id,
                                    'role_name': role_info.get('name', 'Unknown Role'),
                                    'role_description': role_info.get('description', ''),
                                    'scope': scope,
                                    'scope_type': 'ResourceGroup',
                                    'scope_name': f'{sub_name}/{rg_name}',
                                    'assignment_type': 'Direct',
                                    'assignment_source': f'Resource Group: {rg_name} (Subscription: {sub_name})'
                                })
            except Exception as e:
                pass
            
            return rg_roles
        
        # Process subscriptions in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(fetch_rg_roles_from_subscription, sub) for sub in subscriptions]
            for future in as_completed(futures):
                try:
                    rg_roles = future.result()
                    roles.extend(rg_roles)
                except Exception as e:
                    logger.error(f"Error processing subscription for resource group roles: {e}")
        
        return roles
    
    def _get_role_info(self, role_definition_id: str) -> Dict:
        """Get role info with caching to avoid duplicate API calls"""
        # Check cache first
        if role_definition_id in self._role_cache:
            return self._role_cache[role_definition_id]
        
        if not self.azure_roles_loader:
            result = {'name': 'Unknown Role', 'description': ''}
            self._role_cache[role_definition_id] = result
            return result
        
        role_uuid = role_definition_id.split('/')[-1] if '/' in role_definition_id else role_definition_id
        
        role_def = self.azure_roles_loader.get_role_by_id(role_uuid)
        
        if role_def:
            result = {
                'name': role_def.get('RoleName', 'Unknown Role'),
                'description': role_def.get('Permissions', {}).get('Description', ''),
                'actions': role_def.get('Permissions', {}).get('Actions', [])
            }
            self._role_cache[role_definition_id] = result
            return result
        
        try:
            role_def = self.resource_manager._get_role_definition(role_definition_id)
            if role_def:
                result = {
                    'name': role_def.get('properties', {}).get('roleName', 'Unknown Role'),
                    'description': role_def.get('properties', {}).get('description', ''),
                    'actions': role_def.get('properties', {}).get('permissions', [{}])[0].get('actions', []) if role_def.get('properties', {}).get('permissions') else []
                }
                self._role_cache[role_definition_id] = result
                return result
        except Exception as e:
            logger.error(f"Error getting role info for {role_definition_id}: {e}", exc_info=True)
        
        result = {'name': 'Unknown Role', 'description': ''}
        self._role_cache[role_definition_id] = result
        return result
