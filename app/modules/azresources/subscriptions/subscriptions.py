import requests
import logging
from flask import session
from app.modules.azresources.list_azresources import AzureResourceManager
from app.modules.azresources.management_groups.management_groups import AzureManagementGroups

logger = logging.getLogger(__name__)

class AzureSubscriptions:
    def __init__(self, access_token=None):
        self.resource_manager = AzureResourceManager(access_token)
        self.management_groups = AzureManagementGroups(access_token)
        
    def list_subscriptions(self, limit=50, offset=0):
        """
        List available subscriptions with pagination support
        
        Args:
            limit: Maximum number of subscriptions to return (default: 50)
            offset: Number of subscriptions to skip (default: 0)
        
        Returns:
            Dictionary containing subscriptions and pagination info
        """
        try:
            # Get all available subscriptions with pagination
            all_subscriptions = {}
            
            # Try to get all available subscriptions with limit
            try:
                subs_url = f"https://management.azure.com/subscriptions?api-version=2020-01-01&$top={limit}"
                subs_response = self.resource_manager._make_request(subs_url)
                
                if subs_response and 'value' in subs_response:
                    for sub in subs_response.get('value', []):
                        sub_id = sub.get('subscriptionId')
                        if not sub_id:
                            continue
                        
                        # Initialize record for this subscription
                        all_subscriptions[sub_id] = {
                            'id': sub_id,
                            'name': sub.get('displayName', f"Subscription {sub_id}"),
                            'state': sub.get('state', 'Unknown'),
                            'tenantId': sub.get('tenantId', ''),
                            'roles': [],
                            'inheritedRoles': [],
                            'hasDirectAssignment': False
                        }
            except Exception as e:
                logger.error(f"Error getting all subscriptions: {e}")
            
            # If couldn't get subscriptions by the above method,
            # try an alternative method using service principal roles
            if not all_subscriptions:
                sp_roles = self.resource_manager.get_sp_roles()
                
                for resource in sp_roles:
                    if resource['ResourceType'] == 'Subscription':
                        # Skip entries without subscription ID
                        if not resource.get('SubscriptionID'):
                            continue
                            
                        sub_id = resource['SubscriptionID']
                        # Only add if not already in the dictionary
                        if sub_id not in all_subscriptions:
                            all_subscriptions[sub_id] = {
                                'id': sub_id,
                                'name': resource['SubscriptionName'],
                                'roles': [],
                                'inheritedRoles': [],
                                'hasDirectAssignment': False
                            }
            
            # Get service principal roles to check where it has direct access
            sp_roles = self.resource_manager.get_sp_roles()
            
            # Map service principal roles to subscriptions
            for resource in sp_roles:
                if resource['ResourceType'] == 'Subscription' and resource.get('SubscriptionID'):
                    sub_id = resource['SubscriptionID']
                    
                    if sub_id in all_subscriptions:
                        all_subscriptions[sub_id]['hasDirectAssignment'] = True
                        # Check if the role already exists to avoid duplicates
                        role_exists = False
                        for role in all_subscriptions[sub_id]['roles']:
                            if role['name'] == resource['RoleName']:
                                role_exists = True
                                break
                        
                        if not role_exists:
                            all_subscriptions[sub_id]['roles'].append({
                                'name': resource['RoleName'],
                                'scope': resource['RoleScope'],
                                'description': resource['RoleDescription']
                            })
            
            # Process role inheritance from Management Groups
            try:
                # For each subscription, check parent Management Groups and their roles
                for sub_id, sub_info in all_subscriptions.items():
                    try:
                        # Get Management Groups hierarchy for this subscription
                        mg_hierarchy = self.management_groups.get_management_groups_for_subscription(sub_id)
                        
                        # Track roles already added to avoid duplicates
                        # The dictionary maps role name -> {level, name}
                        added_inherited_roles = {}
                        
                        # For each Management Group in hierarchy, get roles and mark as inherited
                        # Iterate in reverse order to process from highest to lowest level
                        for mg in sorted(mg_hierarchy, key=lambda x: x.get('level', 0)):
                            mg_id = mg.get('id')
                            if not mg_id:
                                continue
                                
                            # Get Management Group details, including roles
                            try:
                                roles_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview"
                                roles_response = self.resource_manager._make_request(roles_url)
                                
                                if roles_response and 'value' in roles_response:
                                    for assignment in roles_response.get('value', []):
                                        role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                                        principal_id = assignment.get('properties', {}).get('principalId')
                                        
                                        # Check if the role is for the current service principal
                                        if role_def_id and principal_id == self.resource_manager.principal_id:
                                            try:
                                                role_def = self.resource_manager._get_role_definition(role_def_id)
                                                role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                                                role_description = role_def.get('properties', {}).get('description', '')
                                                
                                                # Check if we haven't already added this role from a higher level
                                                if role_name not in added_inherited_roles:
                                                    # This is the first time we see this role
                                                    added_inherited_roles[role_name] = {
                                                        'level': mg.get('level', 0),
                                                        'name': mg.get('name'),
                                                        'type': mg.get('type', 'Management Group'),
                                                        'description': role_description
                                                    }
                                            except Exception as e:
                                                logger.error(f"Error processing role definition: {e}")
                            except Exception as e:
                                logger.error(f"Error getting roles for management group {mg_id}: {e}")
                        
                        # Now add inherited roles based on collected information
                        for role_name, source_info in added_inherited_roles.items():
                            # Check if this role is not the same as one already in direct roles
                            role_is_direct = False
                            for direct_role in sub_info['roles']:
                                if direct_role['name'] == role_name:
                                    role_is_direct = True
                                    break
                            
                            # If not a direct role, add as inherited
                            if not role_is_direct:
                                sub_info['inheritedRoles'].append({
                                    'name': role_name,
                                    'description': source_info['description'],
                                    'inheritedFrom': source_info['name'],
                                    'inheritedFromType': source_info['type']
                                })
                    except Exception as e:
                        logger.error(f"Error processing management groups for subscription {sub_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing role inheritance: {e}")
            
            # Get more details for each subscription
            for sub_id, sub_info in all_subscriptions.items():
                try:
                    # Try to get details like state and tenantId if not present
                    if not sub_info.get('state') or not sub_info.get('tenantId'):
                        sub_url = f"https://management.azure.com/subscriptions/{sub_id}?api-version=2020-01-01"
                        sub_response = self.resource_manager._make_request(sub_url)
                        
                        if sub_response:
                            sub_info['state'] = sub_response.get('state', 'Unknown')
                            sub_info['tenantId'] = sub_response.get('tenantId', '')
                except Exception as e:
                    logger.error(f"Error getting details for subscription {sub_id}: {e}")
            
            # Convert to list for return
            result = list(all_subscriptions.values())
            
            # Return with pagination info
            return {
                'subscriptions': result,
                'total_count': len(result),
                'limit': limit,
                'offset': offset,
                'has_more': len(result) == limit
            }
            
        except Exception as e:
            logger.error(f"Error listing subscriptions: {e}")
            # Return empty result with error info instead of just empty list
            return {
                'subscriptions': [],
                'total_count': 0,
                'limit': limit,
                'offset': offset,
                'has_more': False,
                'error': str(e)
            }
    
    def get_subscription_details(self, subscription_id):
        """
        Get detailed information about a specific subscription
        
        Args:
            subscription_id: The ID of the subscription
            
        Returns:
            Dictionary containing subscription details and resources
        """
        # Validate input
        if not subscription_id or not isinstance(subscription_id, str):
            raise ValueError("Invalid subscription_id: must be a non-empty string")
        
        # Basic UUID format validation
        import re
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', subscription_id, re.IGNORECASE):
            raise ValueError("Invalid subscription_id format: must be a valid UUID")
        
        try:
            # Make a request to get subscription details
            url = f"https://management.azure.com/subscriptions/{subscription_id}?api-version=2020-01-01"
            response = self.resource_manager._make_request(url)
            
            # Get all resource groups in this subscription
            resource_groups_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups?api-version=2021-04-01"
            resource_groups_response = self.resource_manager._make_request(resource_groups_url)
            
            # Get role assignments for this subscription
            role_assignments_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview"
            role_assignments_response = self.resource_manager._make_request(role_assignments_url)
            role_assignments = role_assignments_response.get('value', [])
            
            # Process role assignments to get role definitions
            roles_info = []
            for assignment in role_assignments:
                role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                principal_id = assignment.get('properties', {}).get('principalId')
                
                if role_def_id:
                    try:
                        # Get role definition details
                        role_def = self.resource_manager._get_role_definition(role_def_id)
                        role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                        role_description = role_def.get('properties', {}).get('description', '')
                        
                        roles_info.append({
                            'roleId': role_def_id,
                            'roleName': role_name,
                            'principalId': principal_id,
                            'description': role_description,
                            'isInherited': False
                        })
                    except Exception:
                        # Continue if we can't get role definition
                        continue
            
            # Get Management Groups for this subscription to show roles inheritance
            inherited_roles_info = []
            
            # Track roles already added to avoid duplicates
            added_inherited_roles = {}
            
            try:
                mg_hierarchy = self.management_groups.get_management_groups_for_subscription(subscription_id)
                
                # For each Management Group in hierarchy, get roles and mark as inherited
                # Process from highest to lowest level
                for mg in sorted(mg_hierarchy, key=lambda x: x.get('level', 0)):
                    mg_id = mg.get('id')
                    if not mg_id:
                        continue
                        
                    # Get Management Group roles
                    roles_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview"
                    roles_response = self.resource_manager._make_request(roles_url)
                    
                    if roles_response and 'value' in roles_response:
                        for assignment in roles_response.get('value', []):
                            role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                            principal_id = assignment.get('properties', {}).get('principalId')
                            
                            # Check if the role is for the current service principal
                            if role_def_id and principal_id == self.resource_manager.principal_id:
                                try:
                                    role_def = self.resource_manager._get_role_definition(role_def_id)
                                    role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                                    role_description = role_def.get('properties', {}).get('description', '')
                                    
                                    # Check if we haven't already added this role from a higher level
                                    if role_name not in added_inherited_roles:
                                        # This is the first time we see this role
                                        added_inherited_roles[role_name] = {
                                            'level': mg.get('level', 0),
                                            'id': role_def_id,
                                            'name': mg.get('name'),
                                            'type': mg.get('type', 'Management Group'),
                                            'description': role_description,
                                            'principalId': principal_id
                                        }
                                except Exception as e:
                                    logger.error(f"Error processing role definition: {e}")
            except Exception as e:
                logger.error(f"Error processing management groups for subscription {subscription_id}: {e}")
            
            # Now add inherited roles based on collected information
            for role_name, source_info in added_inherited_roles.items():
                # Check if this role is not the same as one already in direct roles
                role_is_direct = False
                for direct_role in roles_info:
                    if direct_role['roleName'] == role_name:
                        role_is_direct = True
                        break
                
                # If not a direct role, add as inherited
                if not role_is_direct:
                    inherited_roles_info.append({
                        'roleId': source_info['id'],
                        'roleName': role_name,
                        'principalId': source_info['principalId'],
                        'description': source_info['description'],
                        'isInherited': True,
                        'inheritedFrom': source_info['name'],
                        'inheritedFromType': source_info['type']
                    })
            
            # Determine highest role level for hierarchy diagram
            has_direct_roles = False
            for role in roles_info:
                if role['principalId'] == self.resource_manager.principal_id:
                    has_direct_roles = True
                    break
                    
            has_inherited_roles = len(inherited_roles_info) > 0
                    
            # MODIFICATION HERE: Prioritize the highest level in the hierarchy
            if has_inherited_roles:
                highest_role_level = "management-group"
            elif has_direct_roles:
                highest_role_level = "subscription"
            else:
                highest_role_level = "unknown"
            
            # Build the detailed response
            subscription_details = {
                'id': response.get('subscriptionId'),
                'name': response.get('displayName'),
                'state': response.get('state'),
                'tenantId': response.get('tenantId'),
                'resourceGroups': resource_groups_response.get('value', []),
                'roleAssignments': roles_info,
                'inheritedRoleAssignments': inherited_roles_info,
                'highest_role_level': highest_role_level,
                'show_management_groups': has_inherited_roles,
                'managementGroups': mg_hierarchy if 'mg_hierarchy' in locals() and mg_hierarchy else []
            }
            
            return subscription_details
            
        except Exception as e:
            raise