import jwt
from typing import Optional, Dict, Any

def parse_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Parse JWT token and extract relevant claims.
    
    Args:
        token (str): JWT token string to parse
        
    Returns:
        Optional[Dict[str, Any]]: Dictionary containing parsed token data or None if parsing fails
    """
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        
        result = {
            'app_name': decoded.get('app_displayname', 'Unknown'),
            'roles': decoded.get('roles', []),
            'appid': decoded.get('appid', 'Unknown'),
            'tenant_id': decoded.get('tid', 'Unknown'),
            'oid': decoded.get('oid', None),
            'exp': decoded.get('exp', 0)
        }
        
        return result
    except Exception as e:
        # Token decoding failed - do not log sensitive data
        return None