"""
Azure RBAC access checker utility
Validates if Service Principal has any Azure Resource access
"""

import requests
from typing import Dict, Any
from flask import current_app


def check_azure_resource_access(rest_token: str) -> Dict[str, Any]:
    """
    Check if Service Principal has access to any Azure resources.
    
    Makes a lightweight API call to test access. Returns quickly with cached result.
    
    Args:
        rest_token: Azure Management API access token
        
    Returns:
        Dict with:
            - has_access (bool): True if SP has any Azure resource access
            - error (str): Error message if check failed
    """
    try:
        # Try to list subscriptions - lightweight call to test access
        url = "https://management.azure.com/subscriptions"
        params = {"api-version": "2022-12-01"}
        headers = {
            "Authorization": f"Bearer {rest_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            subscriptions = data.get('value', [])
            return {
                'has_access': len(subscriptions) > 0,
                'subscription_count': len(subscriptions),
                'error': None
            }
        elif response.status_code == 403:
            # Forbidden - no access
            return {
                'has_access': False,
                'subscription_count': 0,
                'error': 'No Azure RBAC permissions assigned'
            }
        else:
            # Other error
            return {
                'has_access': False,
                'subscription_count': 0,
                'error': f'API returned status {response.status_code}'
            }
            
    except requests.exceptions.Timeout:
        # Timeout - assume no access to be safe
        current_app.logger.warning("Timeout checking Azure resource access")
        return {
            'has_access': False,
            'subscription_count': 0,
            'error': 'Timeout checking access'
        }
    except Exception as e:
        current_app.logger.error(f"Error checking Azure resource access: {str(e)}")
        return {
            'has_access': False,
            'subscription_count': 0,
            'error': str(e)
        }

