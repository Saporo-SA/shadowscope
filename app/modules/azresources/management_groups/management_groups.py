import requests
import logging
from app.modules.azresources.list_azresources import AzureResourceManager

logger = logging.getLogger(__name__)

class AzureManagementGroups:
    def __init__(self, access_token=None):
        self.resource_manager = AzureResourceManager(access_token)
        
    def list_management_groups(self, limit=50):
        """
        List management groups with pagination support
        
        Args:
            limit: Maximum number of management groups to return (default: 50)
        
        Returns:
            Dictionary containing management groups and pagination info
        """
        try:
            # Get all available management groups
            all_management_groups = {}
            
            # Get list of all management groups with limit
            try:
                mg_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups?api-version=2020-05-01&$top={limit}"
                mg_response = self.resource_manager._make_request(mg_url)
                
                if mg_response and 'value' in mg_response:
                    for mg in mg_response.get('value', []):
                        mg_id = mg.get('name')
                        if not mg_id:
                            continue
                            
                        # Initialize record for this management group
                        display_name = mg.get('properties', {}).get('displayName', mg_id)
                        tenant_id = mg.get('properties', {}).get('tenantId', '')
                        is_root = mg_id == tenant_id
                        
                        all_management_groups[mg_id] = {
                            'id': mg_id,
                            'name': display_name,
                            'displayName': display_name,
                            'tenantId': tenant_id,
                            'isRoot': is_root,
                            'type': 'RootManagementGroup' if is_root else 'ManagementGroup',
                            'roles': [],
                            'inheritedRoles': [],
                            'hasDirectAssignment': False
                        }
            except Exception as e:
                logger.error(f"Error getting all management groups: {e}")
            
            # If couldn't get management groups by the above method,
            # try an alternative method using service principal roles
            if not all_management_groups:
                # Get service principal roles
                sp_roles = self.resource_manager.get_sp_roles()
                
                # Filter for management group resources
                for resource in sp_roles:
                    # Management groups have a specific format in the scope
                    if '/providers/Microsoft.Management/managementGroups/' in resource['RoleScope']:
                        # Extract management group ID from scope
                        parts = resource['RoleScope'].split('/providers/Microsoft.Management/managementGroups/')
                        if len(parts) > 1:
                            mg_id = parts[1].split('/')[0]
                            
                            if mg_id not in all_management_groups:
                                all_management_groups[mg_id] = {
                                    'id': mg_id,
                                    'name': f"Management Group {mg_id}",
                                    'displayName': f"Management Group {mg_id}",
                                    'roles': [],
                                    'inheritedRoles': [],
                                    'hasDirectAssignment': True
                                }
                            
                            all_management_groups[mg_id]['roles'].append({
                                'name': resource['RoleName'],
                                'scope': resource['RoleScope'],
                                'description': resource['RoleDescription']
                            })
            
            # Get service principal roles to check where it has direct access
            sp_roles = self.resource_manager.get_sp_roles()
            
            # Structure to store service principal roles for inheritance
            direct_roles_by_mg = {}
            
            # Map service principal roles to management groups
            for resource in sp_roles:
                if '/providers/Microsoft.Management/managementGroups/' in resource['RoleScope']:
                    parts = resource['RoleScope'].split('/providers/Microsoft.Management/managementGroups/')
                    if len(parts) > 1:
                        mg_id = parts[1].split('/')[0]
                        
                        if mg_id in all_management_groups:
                            all_management_groups[mg_id]['hasDirectAssignment'] = True
                            
                            # Save this role for inheritance processing later
                            if mg_id not in direct_roles_by_mg:
                                direct_roles_by_mg[mg_id] = []
                                
                            # Add the role if it doesn't already exist
                            role_exists = False
                            for role in all_management_groups[mg_id]['roles']:
                                if role['name'] == resource['RoleName']:
                                    role_exists = True
                                    break
                            
                            if not role_exists:
                                new_role = {
                                    'name': resource['RoleName'],
                                    'scope': resource['RoleScope'],
                                    'description': resource['RoleDescription']
                                }
                                all_management_groups[mg_id]['roles'].append(new_role)
                                direct_roles_by_mg[mg_id].append(new_role)
            
            # Also fetch role assignments directly for each management group (more reliable)
            principal_id = self.resource_manager.principal_id
            if principal_id:
                for mg_id in list(all_management_groups.keys()):
                    try:
                        # Get role assignments directly for this management group
                        roles_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{principal_id}'"
                        roles_response = self.resource_manager._make_request(roles_url)
                        
                        if roles_response and 'value' in roles_response:
                            for assignment in roles_response.get('value', []):
                                role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                                
                                if role_def_id:
                                    try:
                                        role_def = self.resource_manager._get_role_definition(role_def_id)
                                        role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                                        role_description = role_def.get('properties', {}).get('description', '')
                                        
                                        # Check if role already exists
                                        role_exists = False
                                        for existing_role in all_management_groups[mg_id]['roles']:
                                            if existing_role['name'] == role_name:
                                                role_exists = True
                                                break
                                        
                                        if not role_exists:
                                            new_role = {
                                                'name': role_name,
                                                'scope': assignment.get('properties', {}).get('scope', ''),
                                                'description': role_description
                                            }
                                            all_management_groups[mg_id]['roles'].append(new_role)
                                            all_management_groups[mg_id]['hasDirectAssignment'] = True
                                            
                                            # Also add to direct_roles_by_mg for inheritance
                                            if mg_id not in direct_roles_by_mg:
                                                direct_roles_by_mg[mg_id] = []
                                            direct_roles_by_mg[mg_id].append(new_role)
                                    except Exception as e:
                                        logger.error(f"Error processing role definition for MG {mg_id}: {e}")
                    except Exception as e:
                        logger.error(f"Error getting direct role assignments for management group {mg_id}: {e}")
            
            # Build management groups hierarchy for role propagation
            hierarchy_map = {}
            
            # Get detailed information for each management group
            for mg_id in all_management_groups:
                try:
                    # Get more details for each management group
                    expanded_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}?$expand=children&api-version=2020-05-01"
                    expanded_response = self.resource_manager._make_request(expanded_url)
                    
                    if expanded_response:
                        # Update name and ID
                        display_name = expanded_response.get('properties', {}).get('displayName', all_management_groups[mg_id]['name'])
                        all_management_groups[mg_id]['name'] = display_name
                        all_management_groups[mg_id]['displayName'] = display_name
                        
                        # Check if it's root
                        tenant_id = expanded_response.get('properties', {}).get('tenantId', '')
                        is_root = mg_id == tenant_id
                        all_management_groups[mg_id]['isRoot'] = is_root
                        all_management_groups[mg_id]['tenantId'] = tenant_id
                        
                        # Process children to build hierarchy
                        children = expanded_response.get('properties', {}).get('children', [])
                        all_management_groups[mg_id]['childrenCount'] = len(children)
                        
                        # Store parent-child relationships for role propagation
                        for child in children:
                            child_type = child.get('type', '')
                            if 'managementGroups' in child_type:
                                child_id = child.get('name')
                                if child_id and child_id in all_management_groups:
                                    if mg_id not in hierarchy_map:
                                        hierarchy_map[mg_id] = []
                                    hierarchy_map[mg_id].append(child_id)
                except Exception as e:
                    logger.error(f"Error in _build_management_group_hierarchy: {e}")
                    # If we can't get details, continue with what we have
                    continue
            
            # Function to propagate roles recursively
            def propagate_roles(parent_id, inherited_from, inherited_roles):
                if parent_id not in hierarchy_map:
                    return
                
                for child_id in hierarchy_map[parent_id]:
                    # Add inherited roles from parent to child
                    if child_id in all_management_groups:
                        for role in inherited_roles:
                            # Create a copy of the role with inheritance information
                            inherited_role = role.copy()
                            inherited_role['inheritedFrom'] = inherited_from
                            
                            # Check if this inherited role already exists (same role from same source)
                            role_exists = False
                            for existing_role in all_management_groups[child_id]['inheritedRoles']:
                                if existing_role['name'] == inherited_role['name'] and existing_role.get('inheritedFrom') == inherited_role['inheritedFrom']:
                                    role_exists = True
                                    break
                            
                            # Always add inherited roles, even if the same role exists as direct
                            # This shows that the role is inherited from parent AND possibly assigned directly
                            if not role_exists:
                                all_management_groups[child_id]['inheritedRoles'].append(inherited_role)
                        
                        # Continue propagating to children of this group
                        # Parent roles plus direct roles of this group
                        all_roles = inherited_roles.copy()
                        if child_id in direct_roles_by_mg:
                            all_roles.extend(direct_roles_by_mg[child_id])
                        
                        # Propagate to children of this group
                        propagate_roles(child_id, all_management_groups[child_id]['name'], all_roles)
            
            # Start propagation from all groups that have direct roles assigned
            # Process from root to children (top-down)
            processed_groups = set()
            
            def process_group_roles(mg_id):
                """Process roles for a management group and propagate to children"""
                if mg_id in processed_groups:
                    return
                
                processed_groups.add(mg_id)
                
                # If this group has direct roles, propagate them to children
                if mg_id in direct_roles_by_mg and mg_id in hierarchy_map:
                    propagate_roles(mg_id, all_management_groups[mg_id]['name'], direct_roles_by_mg[mg_id])
                
                # Continue processing children
                if mg_id in hierarchy_map:
                    for child_id in hierarchy_map[mg_id]:
                        if child_id in all_management_groups:
                            process_group_roles(child_id)
            
            # Start from root groups
            for mg_id in all_management_groups:
                if all_management_groups[mg_id]['isRoot']:
                    process_group_roles(mg_id)
            
            result = list(all_management_groups.values())
            
            # Return with pagination info
            return {
                'management_groups': result,
                'total_count': len(result),
                'limit': limit,
                'has_more': len(result) == limit
            }
            
        except Exception as e:
            logger.error(f"Error in list_management_groups: {e}")
            # Return empty result with error info instead of raising
            return {
                'management_groups': [],
                'total_count': 0,
                'limit': limit,
                'has_more': False,
                'error': str(e)
            }
    
    def get_management_group_details(self, management_group_id):
        """
        Get detailed information about a specific management group
        
        Args:
            management_group_id: ID do grupo de gerenciamento
            
        Returns:
            Dictionary containing management group details and its resources
        """
        try:
            # Make a request to get management group details
            url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{management_group_id}?api-version=2021-04-01&$expand=children"
            response = self.resource_manager._make_request(url)
            
            # Process the management group details
            name = response.get('name')
            display_name = response.get('properties', {}).get('displayName', name)
            
            # Get children (subscriptions and other management groups)
            children = response.get('properties', {}).get('children', [])
            
            # Separate children into management groups and subscriptions
            management_group_children = []
            subscription_children = []
            
            for child in children:
                child_type = child.get('type', '')
                if 'managementGroups' in child_type:
                    management_group_children.append({
                        'id': child.get('name'),
                        'name': child.get('properties', {}).get('displayName', child.get('name')),
                        'type': 'Management Group'
                    })
                elif 'subscriptions' in child_type:
                    subscription_children.append({
                        'id': child.get('name'),
                        'name': child.get('properties', {}).get('displayName', child.get('name')),
                        'type': 'Subscription'
                    })
            
            # Check if this is a root management group
            is_root = name == response.get('properties', {}).get('tenantId')
            
            # Get parent management group if not root
            parent_management_group = None
            if not is_root:
                try:
                    parent_details = response.get('properties', {}).get('details', {})
                    parent_info = parent_details.get('parent', {})
                    if parent_info:
                        parent_id = parent_info.get('id', '').split('/')[-1]
                        parent_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{parent_id}?api-version=2021-04-01"
                        parent_response = self.resource_manager._make_request(parent_url)
                        
                        if parent_response:
                            parent_management_group = {
                                'id': parent_response.get('name'),
                                'name': parent_response.get('properties', {}).get('displayName', parent_id),
                                'type': 'RootManagementGroup' if parent_id == parent_response.get('properties', {}).get('tenantId') else 'ManagementGroup'
                            }
                except Exception as e:
                    logger.error(f"Error getting parent management group: {e}")
            
            # Build the management group hierarchy
            management_groups_hierarchy = []
            if is_root:
                # If root, just include this management group
                management_groups_hierarchy.append({
                    'id': name,
                    'name': display_name,
                    'type': 'RootManagementGroup'
                })
            else:
                # Build the hierarchy from parent to this management group
                try:
                    hierarchy = []
                    self._build_management_group_hierarchy(management_group_id, hierarchy)
                    management_groups_hierarchy = hierarchy
                    management_groups_hierarchy.reverse()  # Reverse to get from root to current
                except Exception as e:
                    logger.error(f"Error in _build_management_group_hierarchy: {e}")
                    # Fallback to at least include this management group
                    management_groups_hierarchy.append({
                        'id': name,
                        'name': display_name,
                        'type': 'ManagementGroup'
                    })
            
            # Determine highest role level for the hierarchy diagram
            if is_root:
                highest_role_level = "root-management-group"
            else:
                highest_role_level = "management-group"
            
            # Build the detailed response
            management_group_details = {
                'id': response.get('id'),
                'name': name,
                'displayName': display_name,
                'tenantId': response.get('properties', {}).get('tenantId'),
                'type': 'RootManagementGroup' if is_root else 'ManagementGroup',
                'managementGroups': management_group_children,
                'subscriptions': subscription_children,
                'inheritanceMessage': 'Roles assigned at this Management Group level are inherited by all child Management Groups and Subscriptions.',
                'parentManagementGroup': parent_management_group,
                'isRoot': is_root,
                'managementGroupsHierarchy': management_groups_hierarchy,
                'highest_role_level': highest_role_level,
                'show_parent': not is_root,
                'show_children': True,
                'tags': response.get('tags', {})
            }
            
            return management_group_details
            
        except Exception as e:
            logger.error(f"Error getting management group details: {e}")
            raise 
            
    def get_management_groups_for_subscription(self, subscription_id):
        """
        Get the management groups hierarchy for a specific subscription
        
        Args:
            subscription_id: The ID of the subscription
            
        Returns:
            List of dictionaries containing management group information, from root to direct parent
        """
        try:
            management_groups = []
            
            # Get all management groups first
            mg_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups?api-version=2020-05-01"
            mg_response = self.resource_manager._make_request(mg_url)
            
            if not mg_response or 'value' not in mg_response:
                return []
                
            # Find which management groups contain our subscription
            for mg in mg_response.get('value', []):
                mg_id = mg.get('name')
                if not mg_id:
                    continue
                    
                # Get expanded details for this management group to see its children
                expanded_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}?$expand=children&api-version=2020-05-01"
                expanded_response = self.resource_manager._make_request(expanded_url)
                
                if not expanded_response:
                    continue
                    
                # Check if this management group contains our subscription
                children = expanded_response.get('properties', {}).get('children', [])
                sub_path = f"/subscriptions/{subscription_id}"
                
                for child in children:
                    if child.get('type', '') == '/subscriptions' and child.get('id', '').endswith(sub_path):
                        # This management group contains our subscription
                        mg_type = 'RootManagementGroup' if mg_id == expanded_response.get('properties', {}).get('tenantId') else 'ManagementGroup'
                        
                        management_groups.append({
                            'id': mg_id,
                            'name': expanded_response.get('properties', {}).get('displayName', mg_id),
                            'type': mg_type,
                            'level': 0 if mg_type == 'RootManagementGroup' else 1
                        })
                        
                        # Now build the management group hierarchy upward
                        self._build_management_group_hierarchy(mg_id, management_groups)
                        break
            
            # Reverse the list so it's from root to direct parent
            management_groups.reverse()
            
            # Add level information (distance from root)
            for i, mg in enumerate(management_groups):
                mg['level'] = i
                
            return management_groups
            
        except Exception as ex:
            return []
            
    def _build_management_group_hierarchy(self, current_mg_id, management_groups):
        """
        Recursively build the hierarchy of parent management groups
        
        Args:
            current_mg_id: The current management group ID
            management_groups: List to add parent management groups to
        """
        try:
            # Get details of this management group to find its parent
            mg_details_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{current_mg_id}?api-version=2020-05-01"
            mg_details = self.resource_manager._make_request(mg_details_url)
            
            if not mg_details or 'properties' not in mg_details:
                return
                
            # Check if this management group has a parent
            parent_info = mg_details.get('properties', {}).get('details', {}).get('parent')
            if not parent_info:
                return
                
            parent_id = parent_info.get('id', '').split('/')[-1]
            if not parent_id:
                return
                
            # Get details of the parent management group
            parent_details_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{parent_id}?api-version=2020-05-01"
            parent_details = self.resource_manager._make_request(parent_details_url)
            
            if not parent_details:
                return
                
            # Determine if this is the root management group
            mg_type = 'RootManagementGroup' if parent_id == parent_details.get('properties', {}).get('tenantId') else 'ManagementGroup'
            
            # Add the parent to our list
            management_groups.append({
                'id': parent_id,
                'name': parent_details.get('properties', {}).get('displayName', parent_id),
                'type': mg_type
            })
            
            # Continue building the hierarchy upward
            self._build_management_group_hierarchy(parent_id, management_groups)
        except Exception as e:
            logger.error(f"Error in _build_management_group_hierarchy: {e}")
