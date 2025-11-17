import requests
from app.modules.azresources.list_azresources import AzureResourceManager
from app.modules.azresources.management_groups.management_groups import AzureManagementGroups

class AzureResourceGroups:
    def __init__(self, access_token=None):
        self.resource_manager = AzureResourceManager(access_token)
        self.management_groups = AzureManagementGroups(access_token)
        
    def list_resource_groups(self, limit=50):
        """
        List resource groups with pagination support
        
        Args:
            limit: Maximum number of resource groups to return (default: 50)
        
        Returns:
            Dictionary containing resource groups and pagination info
        """
        from flask import current_app
        
        try:
            # First, get all subscriptions directly from API
            subscriptions_url = "https://management.azure.com/subscriptions?api-version=2020-01-01"
            subscriptions_response = self.resource_manager._make_request(subscriptions_url)
            subscriptions = subscriptions_response.get('value', [])
            
            # Store subscription-level roles to track inheritance
            subscription_roles = {}
            principal_id = self.resource_manager.principal_id
            
            # Get subscription-level roles directly from API
            for sub in subscriptions:
                sub_id = sub.get('subscriptionId')
                sub_name = sub.get('displayName', 'Unknown')
                
                if not sub_id:
                    continue
                
                try:
                    # Get role assignments at subscription level
                    sub_roles_url = f"https://management.azure.com/subscriptions/{sub_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{principal_id}'"
                    sub_roles_response = self.resource_manager._make_request(sub_roles_url)
                    sub_role_assignments = sub_roles_response.get('value', [])
                    
                    if sub_role_assignments:
                        subscription_roles[sub_id] = {
                            'name': sub_name,
                            'roles': []
                        }
                        
                        for assignment in sub_role_assignments:
                            role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                            if role_def_id:
                                try:
                                    role_def = self.resource_manager._get_role_definition(role_def_id)
                                    role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                                    role_description = role_def.get('properties', {}).get('description', '')
                                    
                                    subscription_roles[sub_id]['roles'].append({
                                        'name': role_name,
                                        'scope': assignment.get('properties', {}).get('scope', ''),
                                        'description': role_description
                                    })
                                except Exception as e:
                                    current_app.logger.error(f"Error getting role definition for subscription {sub_id}: {e}")
                except Exception as e:
                    current_app.logger.error(f"Error getting subscription roles for {sub_id}: {e}")
                    continue
            
            # Filter for resource group resources and remove duplicates
            resource_group_resources = {}
            
            # For each subscription (even if no subscription-level roles), get resource groups
            for sub in subscriptions:
                sub_id = sub.get('subscriptionId')
                sub_name = sub.get('displayName', 'Unknown')
                
                if not sub_id:
                    continue
                
                try:
                    # Get all resource groups for this subscription
                    resource_groups_url = f"https://management.azure.com/subscriptions/{sub_id}/resourcegroups?api-version=2019-10-01"
                    resource_groups_response = self.resource_manager._make_request(resource_groups_url)
                    
                    for rg in resource_groups_response.get('value', []):
                        rg_name = rg.get('name')
                        rg_key = f"{sub_id}/{rg_name}"
                        
                        if rg_key not in resource_group_resources:
                            resource_group_resources[rg_key] = {
                                'name': rg_name,
                                'subscriptionId': sub_id,
                                'subscriptionName': sub_name,
                                'resourceId': rg.get('id'),
                                'roles': [],
                                'inheritedRoles': [],
                                'hasDirectAssignment': False
                            }
                        
                        # Check for direct role assignments at resource group level
                        try:
                            rg_roles_url = f"https://management.azure.com/subscriptions/{sub_id}/resourcegroups/{rg_name}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{principal_id}'"
                            rg_roles_response = self.resource_manager._make_request(rg_roles_url)
                            rg_role_assignments = rg_roles_response.get('value', [])
                            
                            if rg_role_assignments:
                                resource_group_resources[rg_key]['hasDirectAssignment'] = True
                                
                                for assignment in rg_role_assignments:
                                    role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                                    if role_def_id:
                                        try:
                                            role_def = self.resource_manager._get_role_definition(role_def_id)
                                            role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                                            role_description = role_def.get('properties', {}).get('description', '')
                                            
                                            # Check if role already exists
                                            role_exists = False
                                            for existing_role in resource_group_resources[rg_key]['roles']:
                                                if existing_role['name'] == role_name:
                                                    role_exists = True
                                                    break
                                            
                                            if not role_exists:
                                                resource_group_resources[rg_key]['roles'].append({
                                                    'name': role_name,
                                                    'scope': assignment.get('properties', {}).get('scope', ''),
                                                    'description': role_description
                                                })
                                        except Exception as e:
                                            current_app.logger.error(f"Error getting role definition for RG {rg_name}: {e}")
                        except Exception as e:
                            pass
                        
                        # Add inherited roles from subscription if available
                        # Only add inherited roles that are not already direct roles
                        if sub_id in subscription_roles:
                            inherited_roles_list = []
                            for inherited_role in subscription_roles[sub_id]['roles']:
                                # Check if this role is already assigned directly
                                role_is_direct = False
                                for direct_role in resource_group_resources[rg_key]['roles']:
                                    if direct_role['name'] == inherited_role['name']:
                                        role_is_direct = True
                                        break
                                
                                # Only add as inherited if not already direct
                                if not role_is_direct:
                                    inherited_roles_list.append(inherited_role)
                            
                            resource_group_resources[rg_key]['inheritedRoles'] = inherited_roles_list
                except Exception as e:
                    current_app.logger.error(f"Error getting resource groups for subscription {sub_id}: {e}")
                    continue
            
            # Filter to only include resource groups with roles (direct or inherited)
            filtered_resources = {}
            for rg_key, rg_data in resource_group_resources.items():
                if rg_data['roles'] or rg_data['inheritedRoles']:
                    filtered_resources[rg_key] = rg_data
            
            result = list(filtered_resources.values())
            
            # Apply limit after filtering
            if limit:
                result = result[:limit]
            
            # Return with pagination info
            return {
                'resource_groups': result,
                'total_count': len(result),
                'limit': limit,
                'has_more': len(filtered_resources) > limit
            }
            
        except Exception as e:
            current_app.logger.error(f"Error in list_resource_groups: {e}")
            # Return empty result with error info instead of raising
            return {
                'resource_groups': [],
                'total_count': 0,
                'limit': limit,
                'has_more': False,
                'error': str(e)
            }
    
    def get_resource_group_details(self, subscription_id, resource_group_name):
        """
        Get detailed information about a specific resource group
        
        Args:
            subscription_id: Subscription ID
            resource_group_name: Resource group name
            
        Returns:
            Dictionary containing resource group details and its resources
        """
        try:
            # Get resource group details using an older, stable API version
            url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups/{resource_group_name}?api-version=2019-10-01"
            response = self.resource_manager._make_request(url)
            
            # Get resources in the resource group
            resources_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups/{resource_group_name}/resources?api-version=2019-10-01"
            resources_response = self.resource_manager._make_request(resources_url)
            
            # Get role assignments for this resource group
            role_assignments_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups/{resource_group_name}/providers/Microsoft.Authorization/roleAssignments?api-version=2018-09-01-preview"
            role_assignments_response = self.resource_manager._make_request(role_assignments_url)
            role_assignments = role_assignments_response.get('value', [])
            
            # Get subscription information for inherited roles
            sub_url = f"https://management.azure.com/subscriptions/{subscription_id}?api-version=2019-10-01"
            sub_response = self.resource_manager._make_request(sub_url)
            sub_name = sub_response.get('displayName', 'Unknown Subscription')
            
            # Get role assignments at subscription level (inherited)
            sub_roles_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2018-09-01-preview"
            sub_roles_response = self.resource_manager._make_request(sub_roles_url)
            sub_role_assignments = sub_roles_response.get('value', [])
            
            # Try to get management groups for subscription with improved error handling
            management_groups = []
            subscription_management_groups = None
            try:
                # Set a 5-second timeout to avoid blocks
                subscription_management_groups = self.management_groups.get_management_groups_for_subscription(subscription_id)
                if subscription_management_groups:
                    # Filter only necessary data to reduce information volume
                    management_groups = [{
                        'name': mg.get('name', 'Unknown'),
                        'id': mg.get('id', ''),
                        'type': mg.get('type', ''),
                        'level': mg.get('level', 0)
                    } for mg in subscription_management_groups if mg]
            except Exception as e:
                # Capture any error and continue, just logging the problem
                management_groups = [{"name": "Error", "message": "Management Group data could not be retrieved or access is limited"}]
            
            # Process direct role assignments
            roles_info = []
            try:
                for assignment in role_assignments:
                    role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                    principal_id = assignment.get('properties', {}).get('principalId')
                    
                    if role_def_id:
                        # First try to get complete role definition
                        try:
                            role_def = self.resource_manager._get_role_definition(role_def_id)
                            roles_info.append({
                                'roleId': role_def_id,
                                'roleName': role_def.get('properties', {}).get('roleName', 'Unknown Role'),
                                'principalId': principal_id,
                                'description': role_def.get('properties', {}).get('description', ''),
                                'isInherited': False
                            })
                        except Exception:
                            # Fallback method to extract role name
                            role_name = role_def_id.split('/')[-1] if '/' in role_def_id else 'Unknown Role'
                            roles_info.append({
                                'roleId': role_def_id,
                                'roleName': role_name,
                                'principalId': principal_id,
                                'description': '',
                                'isInherited': False
                            })
            except Exception as e:
                # Ensure a default value even in case of error
                roles_info = []
            
            # Get inherited roles
            inherited_roles_info = []
            try:
                for assignment in sub_role_assignments:
                    role_def_id = assignment.get('properties', {}).get('roleDefinitionId')
                    principal_id = assignment.get('properties', {}).get('principalId')
                    
                    if role_def_id and principal_id == self.resource_manager.principal_id:
                        # First try to get role definition for more complete information
                        try:
                            role_def = self.resource_manager._get_role_definition(role_def_id)
                            inherited_roles_info.append({
                                'roleId': role_def_id,
                                'roleName': role_def.get('properties', {}).get('roleName', 'Unknown Role'),
                                'principalId': principal_id,
                                'description': role_def.get('properties', {}).get('description', ''),
                                'isInherited': True,
                                'inheritedFrom': 'Subscription'
                            })
                        except Exception:
                            # If getting definition fails, use simplified method
                            role_name = role_def_id.split('/')[-1] if '/' in role_def_id else 'Unknown Role'
                            inherited_roles_info.append({
                                'roleId': role_def_id,
                                'roleName': role_name,
                                'principalId': principal_id,
                                'description': '',
                                'isInherited': True,
                                'inheritedFrom': 'Subscription'
                            })
            except Exception as e:
                # Ensure a default value even in case of error
                inherited_roles_info = []
            
            # Get only essential resource information (name, type, ID)
            detailed_resources = []
            try:
                for resource in resources_response.get('value', []):
                    try:
                        resource_info = {
                            'id': resource.get('id'),
                            'name': resource.get('name'),
                            'type': resource.get('type')
                        }
                        detailed_resources.append(resource_info)
                    except Exception as e:
                        # Include the resource with minimal information
                        detailed_resources.append({
                            'id': resource.get('id', 'Unknown'),
                            'name': resource.get('name', 'Unknown'),
                            'type': resource.get('type', 'Unknown')
                        })
            except Exception as e:
                # Ensure we have a default value
                detailed_resources = []
            
            # Build final response
            resource_group_details = {
                'id': response.get('id'),
                'name': response.get('name'),
                'location': response.get('location'),
                'properties': response.get('properties', {}),
                'resources': detailed_resources,
                'roleAssignments': roles_info,
                'inheritedRoleAssignments': inherited_roles_info,
                'subscriptionId': subscription_id,
                'subscriptionName': sub_name,
                'managementGroups': management_groups
            }
            
            # Check where the role is applied (Management Group, Subscription, Resource Group)
            has_direct_roles = False
            highest_role_level = "resource-group"  # Default

            # Check if has direct role in resource group
            for role in roles_info:
                if role['principalId'] == self.resource_manager.principal_id:
                    has_direct_roles = True
                    highest_role_level = "resource-group"
                    break

            # Check if has roles inherited from subscription
            has_subscription_roles = False
            for role in inherited_roles_info:
                if role['principalId'] == self.resource_manager.principal_id:
                    has_subscription_roles = True
                    # If no direct role in resource group, update highest level
                    if not has_direct_roles:
                        highest_role_level = "subscription"
                    break

            # Check if has roles inherited from management group
            # Since we don't have direct access to management group roles,
            # We infer this based on the existence of management groups and
            # whether we have roles at the subscription level
            has_mg_roles = False
            if management_groups and len(management_groups) > 0:
                # If we have roles on subscription but not on resource group, we might have roles on management group
                # Or if we have access to management group information, we probably have some access there
                if (has_subscription_roles and not has_direct_roles) or subscription_management_groups:
                    has_mg_roles = True
                    highest_role_level = "management-group"

            # Add flags to control display of each hierarchy level
            resource_group_details['show_management_groups'] = highest_role_level == "management-group"
            resource_group_details['show_subscription'] = highest_role_level in ["management-group", "subscription"]
            resource_group_details['highest_role_level'] = highest_role_level
            
            return resource_group_details
            
        except Exception as e:
            raise