"""
SharePoint routes
"""

import json
import os
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.modules.office365.sharepoint import SharePoint
from app.utils.graph_api import GraphAPI
from app.utils.route_helpers import get_user_context, prepare_module_permissions

sharepoint_bp = Blueprint('sharepoint', __name__)



@sharepoint_bp.route('/sharepoint/sites')
def list_sharepoint_sites():
    """List SharePoint sites."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('sharepoint', {}).get('base', False):
        flash('You do not have permission to access SharePoint sites.', 'error')
        return redirect(url_for('auth.login'))
    
    module_permissions = {
        'sharepoint': prepare_module_permissions('sharepoint', access)
    }
    
    sites_cache_path = 'results/sharepoint_sites.json'
    
    items = None
    try:
        if os.path.exists(sites_cache_path) and 'refresh' not in request.args:
            file_time = os.path.getmtime(sites_cache_path)
            file_age = datetime.now() - datetime.fromtimestamp(file_time)
            
            if file_age < timedelta(hours=24):
                with open(sites_cache_path, 'r') as f:
                    items = json.load(f)
    except Exception as e:
        current_app.logger.error(f"Error reading SharePoint sites cache file: {str(e)}")

    if not items:
        graph_api = GraphAPI(session['graph_token'])
        sharepoint_module = SharePoint(graph_api)
        items = sharepoint_module.list_sites()

        if items:
            try:
                os.makedirs(os.path.dirname(sites_cache_path), exist_ok=True)
                with open(sites_cache_path, 'w') as f:
                    json.dump(items, f, indent=2)
            except Exception as e:
                current_app.logger.error(f"Error saving SharePoint sites cache file: {str(e)}")
    
    cache_time = None
    if os.path.exists(sites_cache_path):
        cache_time = datetime.fromtimestamp(os.path.getmtime(sites_cache_path)).strftime('%Y-%m-%d %H:%M:%S')
    
    return render_template('sharepoint/sites.html', 
                          items=items, 
                          access=access,
                          module_permissions=module_permissions,
                          cache_time=cache_time)


@sharepoint_bp.route('/sharepoint/sites/refresh')
def refresh_sharepoint_sites():
    """Refresh SharePoint sites from API."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    if not token_data:
        return redirect(url_for('auth.login'))
    
    permissions = user_context.get('permissions')
    if not permissions or not permissions.has_base_access('sharepoint'):
        flash('You do not have permission to refresh SharePoint sites data.', 'error')
        return redirect(url_for('auth.login'))
    
    sites_cache_path = 'results/sharepoint_sites.json'
    
    graph_api = GraphAPI(session['graph_token'])
    sharepoint_module = SharePoint(graph_api)
    items = sharepoint_module.list_sites()

    if items:
        try:
            os.makedirs(os.path.dirname(sites_cache_path), exist_ok=True)
            with open(sites_cache_path, 'w') as f:
                json.dump(items, f, indent=2)
            flash(f"Successfully refreshed and cached {len(items)} SharePoint sites.", "success")
        except Exception as e:
            flash(f"Error saving cache file: {str(e)}", "error")
    else:
        flash("Failed to fetch SharePoint sites from API.", "error")
    
    return redirect(url_for('sharepoint.list_sharepoint_sites'))


@sharepoint_bp.route('/sharepoint/sites/<site_id>/drives')
def list_site_drives(site_id):
    """List site drives."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('sharepoint', {}).get('base', False):
        flash('You do not have permission to access SharePoint drives.', 'error')
        return redirect(url_for('sharepoint.list_sharepoint_sites'))
    
    graph_api = GraphAPI(session['graph_token'])
    sharepoint_module = SharePoint(graph_api)

    site = sharepoint_module.get_site_details(site_id)
    if not site:
        flash("SharePoint site not found", "error")
        return redirect(url_for('sharepoint.list_sharepoint_sites'))

    items = sharepoint_module.list_site_drives(site_id)
    
    return render_template('sharepoint/drives.html', 
                          site=site,
                          items=items, 
                          access=access)


@sharepoint_bp.route('/sharepoint/sites/<site_id>/drives/<drive_id>/download')
def download_drive(site_id, drive_id):
    """Download drive (not fully supported - redirects to items)."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('sharepoint', {}).get('base', False):
        flash('You do not have permission to download SharePoint files.', 'error')
        return redirect(url_for('sharepoint.list_sharepoint_sites'))
    
    graph_api = GraphAPI(session['graph_token'])
    
    try:
        drive_url = f'/sites/{site_id}/drives/{drive_id}'
        drive_info = graph_api.get(drive_url)
        
        if not drive_info:
            flash('Could not retrieve drive information.', 'error')
            return redirect(url_for('sharepoint.list_site_drives', site_id=site_id))
        
        flash(f'Direct download of entire drives is not supported. Please navigate to specific files to download them.', 'warning')
        return redirect(url_for('sharepoint.list_drive_items', site_id=site_id, drive_id=drive_id))
        
    except Exception as e:
        current_app.logger.error(f"Error downloading drive: {e}")
        flash(f"Error downloading drive: {str(e)}", "error")
        return redirect(url_for('sharepoint.list_site_drives', site_id=site_id))


@sharepoint_bp.route('/sharepoint/sites/<site_id>/drives/<drive_id>/items')
def list_drive_items(site_id, drive_id):
    """List drive items."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('sharepoint', {}).get('base', False):
        flash('You do not have permission to access SharePoint drive items.', 'error')
        return redirect(url_for('sharepoint.list_sharepoint_sites'))
    
    graph_api = GraphAPI(session['graph_token'])
    sharepoint_module = SharePoint(graph_api)
    
    site = sharepoint_module.get_site_details(site_id)
    if not site:
        flash("SharePoint site not found", "error")
        return redirect(url_for('sharepoint.list_sharepoint_sites'))

    drive = None
    drives = sharepoint_module.list_site_drives(site_id)
    for d in drives:
        if d.get('id') == drive_id:
            drive = d
            break
            
    if not drive:
        flash("SharePoint drive not found", "error")
        return redirect(url_for('sharepoint.list_site_drives', site_id=site_id))

    folder_path = request.args.get('path', '')

    parent_folder = None
    current_folder = None
    if folder_path:
        path_parts = folder_path.split('/')
        if len(path_parts) > 0:
            current_folder = path_parts[-1]
            parent_folder = '..' 

    items = sharepoint_module.list_drive_items(drive_id, folder_path)
    
    return render_template('sharepoint/drive_items.html', 
                          site=site,
                          drive=drive,
                          items=items, 
                          current_folder=current_folder,
                          parent_folder=parent_folder,
                          access=access)


@sharepoint_bp.route('/sharepoint/sites/<site_id>/drives/<drive_id>/items/<item_id>/download')
def download_drive_item(site_id, drive_id, item_id):
    """Download a specific drive item."""
    user_context = get_user_context()
    token_data = user_context.get('token_data', {})
    access = user_context.get('access', {})
    
    if not access.get('sharepoint', {}).get('base', False):
        flash('You do not have permission to download SharePoint files.', 'error')
        return redirect(url_for('sharepoint.list_sharepoint_sites'))
    
    graph_api = GraphAPI(session['graph_token'])
    
    try:
        content_url = f'/drives/{drive_id}/items/{item_id}/content'
        response = graph_api.get(content_url, raw_response=True)
        
        if response.status_code == 302 or response.is_redirect:
            return redirect(response.headers['Location'])
        
        if response.status_code == 200:
            filename = f"file_{item_id}"
            
            content_disposition = response.headers.get('content-disposition')
            if content_disposition and 'filename=' in content_disposition:
                import re
                filename_match = re.search(r'filename="?([^";]+)', content_disposition)
                if filename_match:
                    filename = filename_match.group(1)
            
            return Response(
                response.content,
                mimetype=response.headers.get('content-type', 'application/octet-stream'),
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )
        
        sharepoint_module = SharePoint(graph_api)
        download_url = sharepoint_module.get_download_url(drive_id, item_id)
        
        if download_url:
            return redirect(download_url)
        
        flash("Failed to get download URL for file", "error")
        return redirect(url_for('sharepoint.list_drive_items', site_id=site_id, drive_id=drive_id))
        
    except Exception as e:
        current_app.logger.error(f"Error downloading file: {str(e)}")
        flash(f"Error downloading file: {str(e)}", "error")
        return redirect(url_for('sharepoint.list_drive_items', site_id=site_id, drive_id=drive_id))

