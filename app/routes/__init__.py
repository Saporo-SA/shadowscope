from flask import Flask

def register_blueprints(app: Flask) -> None:
    # Auth routes
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    
    # Dashboard and search
    from app.routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    from app.routes.search import search_bp
    app.register_blueprint(search_bp)
    
    # EntraID routes
    from app.routes.entra_id.groups import groups_bp
    app.register_blueprint(groups_bp)
    
    from app.routes.entra_id.users import users_bp
    app.register_blueprint(users_bp)
    
    from app.routes.entra_id.service_principals import service_principals_bp
    app.register_blueprint(service_principals_bp)
    
    from app.routes.entra_id.administrative_units import admin_units_bp
    app.register_blueprint(admin_units_bp)
    
    from app.routes.entra_id.roles import roles_bp
    app.register_blueprint(roles_bp)
    
    # Office365 routes
    from app.routes.office365.teams import teams_bp
    app.register_blueprint(teams_bp)
    
    from app.routes.office365.sharepoint import sharepoint_bp
    app.register_blueprint(sharepoint_bp)
    
    from app.routes.office365.outlook import outlook_bp
    app.register_blueprint(outlook_bp)
    
    # Azure Resources routes
    from app.routes.azure_resources.subscriptions import subscriptions_bp
    app.register_blueprint(subscriptions_bp)
    
    from app.routes.azure_resources.management_groups import management_groups_bp
    app.register_blueprint(management_groups_bp)
    
    from app.routes.azure_resources.resource_groups import resource_groups_bp
    app.register_blueprint(resource_groups_bp)
    
    # Notifications routes
    from app.routes.notifications import notifications_bp
    app.register_blueprint(notifications_bp)
    
    # Intune routes
    from app.routes.intune.intune import intune_bp
    app.register_blueprint(intune_bp)

