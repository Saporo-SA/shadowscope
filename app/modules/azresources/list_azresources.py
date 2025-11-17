import requests
import logging
from flask import current_app, session
from app.utils.jwt_parser import parse_jwt_token
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class AzureResourceManager:
    def __init__(self, access_token=None):
        # Use rest_token from session if available and no token provided
        # Check if we're in an application context before accessing session
        if access_token is None:
            try:
                # Try to access session - will raise RuntimeError if outside app context
                if 'rest_token' in session:
                    self.access_token = session['rest_token']
                    # Parse token to extract object ID
                    token_data = parse_jwt_token(self.access_token)
                    # Only use oid, do not try appid as fallback
                    self.principal_id = token_data.get('oid') if token_data else None
                else:
                    self.access_token = None
                    self.principal_id = None
            except RuntimeError:
                # Outside application context - use provided token or None
                self.access_token = access_token
                self.principal_id = None
                if access_token:
                    # Parse provided token to extract object ID
                    token_data = parse_jwt_token(access_token)
                    # Only use oid, do not try appid as fallback
                    self.principal_id = token_data.get('oid') if token_data else None
        else:
            self.access_token = access_token
            self.principal_id = None
            if access_token:
                # Parse provided token to extract object ID
                token_data = parse_jwt_token(access_token)
                # Only use oid, do not try appid as fallback
                self.principal_id = token_data.get('oid') if token_data else None
                
        self.role_definitions_cache = {}
        self.cache_ttl = 300  # 5 minutes
        self.cache_timestamps = {}
        
    def set_token(self, access_token):
        self.access_token = access_token
        if access_token:
            # Update principal_id when token is set
            token_data = parse_jwt_token(access_token)
            # Only use oid, do not try appid as fallback
            self.principal_id = token_data.get('oid') if token_data else None
    
    def _make_request(self, url, params=None):
        """Helper method to make authenticated requests to Azure API"""
        if not self.access_token:
            # Try to get the token from session if not set (only if in app context)
            try:
                if 'rest_token' in session:
                    self.access_token = session['rest_token']
                else:
                    raise ValueError("Access token not set. Call set_token() first or ensure 'rest_token' is in session")
            except RuntimeError:
                raise ValueError("Access token not set. Call set_token() first")
                
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            # Validate URL format - check that it starts with https://
            if not url.startswith('https://'):
                # If URL starts with '/', prepend the Azure Management API base URL
                if url.startswith('/'):
                    fixed_url = f"https://management.azure.com{url}"
                    logger.warning(f"Fixed invalid URL format. '{url}' changed to '{fixed_url}'")
                    url = fixed_url
                else:
                    logger.error(f"Invalid URL '{url}': URL must start with 'https://' or '/'")
                    raise ValueError(f"Invalid URL '{url}': No scheme supplied. URL must start with 'https://'")
            
            # Retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    timeout = 30 + (attempt * 10)  # 30s, 40s, 50s
                    response = requests.get(url, headers=headers, params=params, timeout=timeout)
                    break
                except requests.exceptions.Timeout:
                    if attempt == max_retries - 1:
                        raise
                    logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries}), retrying...")
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
            
            # Check authorization errors
            if response.status_code == 401:
                logger.error(f"Authorization error (401) for {url}. Token may be invalid or expired.")
                raise ValueError(f"Authorization failed for {url}: Token may be invalid or expired")
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Request to {url} timed out after 10 seconds")
            raise ValueError(f"Request to {url} timed out")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making request to {url}: {e}")
            raise
            
    def get_sp_roles(self, principal_id=None):
        """
        Get all resources a service principal has access to, along with their roles and scopes
        
        Args:
            principal_id: The object ID of the service principal. If None, uses the ID from the token.
            
        Returns:
            List of dictionaries containing resource information and role assignments
        """
        if principal_id is None:
            principal_id = self.principal_id
            
        if principal_id is None:
            # The service principal must have a valid oid
            raise ValueError("No principal ID (oid) provided and couldn't extract from token. The service principal must have a valid object ID.")
            
        results = []
        
        try:
            # First try with a simple call to check if we have access
            # Get all subscriptions
            subscriptions_url = "https://management.azure.com/subscriptions?api-version=2020-01-01"
            try:
                # OPTIMIZATION 1: Add timeout to avoid long blocks
                subscriptions_response = self._make_request(subscriptions_url)
                subscriptions = subscriptions_response.get('value', [])
                logger.info(f"Found {len(subscriptions)} subscriptions")
                
                # OPTIMIZATION 2: Parallelize role assignment calls across subscriptions
                def process_subscription(sub):
                    """Process a single subscription's role assignments"""
                    sub_id = sub.get('subscriptionId')
                    sub_name = sub.get('displayName')
                    sub_results = []
                    
                    try:
                        sub_roles_url = f"https://management.azure.com/subscriptions/{sub_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{principal_id}'"
                        sub_roles_response = self._make_request(sub_roles_url)
                        sub_roles = sub_roles_response.get('value', [])
                        
                        # Process subscription-level roles
                        for role in sub_roles:
                            role_def_id = role.get('properties', {}).get('roleDefinitionId')
                            role_scope = role.get('properties', {}).get('scope')
                            
                            # Get role definition details (uses cache)
                            try:
                                role_def = self._get_role_definition(role_def_id)
                                role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                                role_description = role_def.get('properties', {}).get('description', '')
                            except Exception as e:
                                role_name = "Error retrieving role definition"
                                role_description = f"Error: {str(e)}"
                            
                            # Determine the resource type based on scope
                            resource_type = "Subscription"
                            resource_name = sub_name
                            resource_id = role_scope
                            
                            # If scope points to a resource group or resource
                            if '/resourceGroups/' in role_scope:
                                parts = role_scope.split('/resourceGroups/')
                                if len(parts) > 1:
                                    rg_and_rest = parts[1].split('/')
                                    resource_name = rg_and_rest[0]
                                    resource_type = "ResourceGroup"
                                    
                                    # If there are more parts, it's a resource within the resource group
                                    if len(rg_and_rest) > 2:
                                        resource_type = '/'.join(rg_and_rest[1:])
                                        resource_name = rg_and_rest[-1]
                            
                            # Add to results
                            sub_results.append({
                                'ResourceID': resource_id,
                                'ResourceName': resource_name,
                                'ResourceType': resource_type,
                                'RoleName': role_name,
                                'RoleScope': role_scope,
                                'RoleDescription': role_description,
                                'SubscriptionID': sub_id,
                                'SubscriptionName': sub_name
                            })
                    except Exception as e:
                        current_app.logger.error(f"Error getting subscription role assignments for {sub_id}: {e}")
                    
                    return sub_results
                
                # Process subscriptions in parallel (max 10 concurrent)
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_sub = {executor.submit(process_subscription, sub): sub for sub in subscriptions}
                    for future in as_completed(future_to_sub):
                        try:
                            sub_results = future.result()
                            results.extend(sub_results)
                        except Exception as e:
                            sub = future_to_sub[future]
                            logger.error(f"Error processing subscription {sub.get('subscriptionId')}: {e}")
            
            except Exception as e:
                logger.warning(f"No subscription access or error listing subscriptions: {e}")
                # If we can't access subscriptions, we try to check management groups
                try:
                    # Try to check if service principal has access to management groups
                    mg_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups?api-version=2020-05-01"
                    mg_response = self._make_request(mg_url)
                    management_groups = mg_response.get('value', [])
                    
                    for mg in management_groups:
                        mg_id = mg.get('name')
                        mg_name = mg.get('properties', {}).get('displayName', mg_id)
                        
                        # Check role assignments in the management group
                        try:
                            mg_roles_url = f"https://management.azure.com/providers/Microsoft.Management/managementGroups/{mg_id}/providers/Microsoft.Authorization/roleAssignments?api-version=2020-04-01-preview&$filter=principalId eq '{principal_id}'"
                            mg_roles_response = self._make_request(mg_roles_url)
                            mg_roles = mg_roles_response.get('value', [])
                            
                            for role in mg_roles:
                                role_def_id = role.get('properties', {}).get('roleDefinitionId')
                                role_scope = role.get('properties', {}).get('scope')
                                
                                # Get role definition details
                                try:
                                    role_def = self._get_role_definition(role_def_id)
                                    role_name = role_def.get('properties', {}).get('roleName', 'Unknown Role')
                                    role_description = role_def.get('properties', {}).get('description', '')
                                except Exception as e:
                                    role_name = "Error retrieving role definition"
                                    role_description = f"Error: {str(e)}"
                                
                                results.append({
                                    'ResourceID': f"/providers/Microsoft.Management/managementGroups/{mg_id}",
                                    'ResourceName': mg_name,
                                    'ResourceType': "ManagementGroup",
                                    'RoleName': role_name,
                                    'RoleScope': role_scope,
                                    'RoleDescription': role_description,
                                    'SubscriptionID': None,
                                    'SubscriptionName': None
                                })
                        except Exception as e:
                            logger.error(f"Error getting management group role assignments for {mg_id}: {e}")
                except Exception as e:
                    logger.error(f"Error accessing management groups: {e}")
                
        except Exception as e:
            logger.error(f"Error in get_sp_roles: {e}")
        
        return results
    
    def _get_role_definition(self, role_definition_id):
        """Helper method to get details of a role definition with TTL cache and thread-safe access"""
        import time
        import threading
        
        # Thread-safe cache access
        if not hasattr(self, '_cache_lock'):
            self._cache_lock = threading.Lock()
        
        with self._cache_lock:
            # Check if cached and not expired
            if (role_definition_id in self.role_definitions_cache and 
                role_definition_id in self.cache_timestamps and
                time.time() - self.cache_timestamps[role_definition_id] < self.cache_ttl):
                return self.role_definitions_cache[role_definition_id]
            
            # Clean expired cache entries periodically (every 100th call)
            current_time = time.time()
            if len(self.cache_timestamps) > 0 and len(self.cache_timestamps) % 100 == 0:
                expired_keys = [key for key, timestamp in self.cache_timestamps.items() 
                            if current_time - timestamp >= self.cache_ttl]
                for key in expired_keys:
                    self.role_definitions_cache.pop(key, None)
                    self.cache_timestamps.pop(key, None)
        
        # Extract the UUID from the role definition ID
        role_uuid = role_definition_id.split('/')[-1]
        
        url = f"https://management.azure.com/providers/Microsoft.Authorization/roleDefinitions/{role_uuid}?api-version=2022-04-01"
        
        try:
            role_def = self._make_request(url)
            # Cache with timestamp (thread-safe)
            with self._cache_lock:
                self.role_definitions_cache[role_definition_id] = role_def
                self.cache_timestamps[role_definition_id] = time.time()
            return role_def
        except Exception as e:
            raise