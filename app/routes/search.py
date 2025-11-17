"""
Search functionality routes.
"""

from flask import Blueprint, current_app, jsonify, request, session

from app.modules.search import SearchModule
from app.utils.route_helpers import get_user_context

search_bp = Blueprint('search', __name__)


@search_bp.route('/search', methods=['POST'])
def search_content():
    """Endpoint to search Microsoft 365 content using Graph API search."""
    if 'graph_token' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        query = data.get('query')
        
        page = data.get('page', 1)
        limit = min(data.get('limit', 500), 500)
        
        if not query or len(query.strip()) == 0:
            return jsonify({'success': False, 'message': 'Search query is required'}), 400
            
        user_context = get_user_context()
        permissions = user_context.get('permissions')
        if not permissions:
            return jsonify({
                'success': False, 
                'message': 'You do not have permissions to search files. Need Sites.Read.All permission.'
            }), 403
        
        has_file_search_access = permissions.has_base_access('sharepoint')
        
        if not has_file_search_access:
            return jsonify({
                'success': False, 
                'message': 'You do not have permissions to search files. Need Sites.Read.All permission.'
            }), 403
        
        search_module = SearchModule(session['graph_token'], permissions=permissions)
        search_results = search_module.search_content(query, page, limit)
        
        return jsonify(search_results)
    
    except Exception as e:
        current_app.logger.error(f"Search error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

