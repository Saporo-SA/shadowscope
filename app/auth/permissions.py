class AzurePermissions:
    """
    Azure AD Permissions management class.
    
    Handles permission checks for various Microsoft 365 and Azure AD modules
    including users, groups, teams, SharePoint, Outlook, and administrative units.
    """
    
    def __init__(self, roles):
        """
        Initialize permissions manager with user roles.
        
        Args:
            roles: List of Azure AD roles/permissions assigned to the user
        """
        self.roles = roles
        
        # Definition of base and specific permissions by module
        self.modules = {
            
            # Microsoft 365 - Search
            'search': {
                'base': {'Sites.Read.All', 'Files.Read.All', 'Mail.Read', 'Mail.Read.All', 'ChannelMessage.Read.All'},
                'features': {
                    'search_sharepoint': {'Sites.Read.All', 'Files.Read.All'},
                    'search_outlook': {'Mail.Read', 'Mail.Read.All'},
                    'search_teams': {'ChannelMessage.Read.All'},
                    'search_chat_messages': {'ChatMessage.Read.All', 'ChatMessage.ReadWrite.All', 'Chat.Read.All', 'Chat.ReadWrite.All'}
                }
            },
            
            # Entra ID - Users
            'users': {
                'base': {'User.Read.All', 'User.ReadWrite.All', 'Directory.Read.All','Directory.ReadWrite.All'},
                'features': {
                    'reset_auth_methods': {'UserAuthenticationMethod.ReadWrite.All'},
                }
            },
            
            # Entra ID - Groups
            'groups': {
                'base': {'Group.Read.All', 'Group.ReadWrite.All', 'GroupMember.ReadWrite.All', 'Directory.Read.All', 'Directory.ReadWrite.All' },
                'features': {
                    'manage_members': {'Group.ReadWrite.All','Directory.ReadWrite.All','GroupMember.ReadWrite.All'},
                    'manage_groups': {'Group.ReadWrite.All','GroupMember.ReadWrite.All'},
                }
            },
            
            # Entra ID - Administrative Units
            'admin_units': {
                'base': {'AdministrativeUnit.Read.All','AdministrativeUnit.ReadWrite.All','Directory.Read.All', 'Directory.ReadWrite.All' },
                'features': {
                    'manage_members': {'AdministrativeUnit.ReadWrite.All'},
                }
            },
            
            
            # Entra ID - Service Principals
            'service_principals': {
                'base': {'Application.Read.All', 'Application.ReadWrite.All', 'Directory.Read.All', 'Directory.ReadWrite.All'},
                'features': {
                    'manage_apps': {'Application.ReadWrite.All'},
                    'manage_role_assignments': {'AppRoleAssignment.ReadWrite.All'}
                }
            },
            
            # Microsoft 365 - Teams
            'teams': {
                'base': {'Team.ReadBasic.All', 'Team.Read.All', 'Team.ReadWrite.All','TeamMember.ReadWrite.All', 'TeamSettings.Read.All', 'TeamSettings.ReadWrite.All'},
                'features': {
                    'list_teams_members': {'Team.ReadWrite.All','TeamMember.Read.All', 'TeamMember.ReadWrite.All'},
                    'edit_teams_members': {'Team.ReadWrite.All','TeamMember.ReadWrite.All'},
                    'list_channels': {'Channel.ReadBasic.All', 'Team.Read.All'},
                    'list_channel_members': {'ChannelMember.Read.All', 'ChannelMember.ReadWrite.All'},
                    'edit_channel_members': {'ChannelMember.ReadWrite.All'},
                    'read_channel_messages': {'ChannelMessage.Read.All'}
                }
            },
            
            # Microsoft 365 - SharePoint
            'sharepoint': {
                'base': {'Sites.Read.All', 'Sites.ReadWrite.All', 'Sites.FullControl.All'},
                'features': {
                    'list_sites': {'Sites.Read.All', 'Sites.ReadWrite.All', 'Sites.FullControl.All'}
                }
            },
            
            # Microsoft 365 - Outlook
            'outlook': {
                'base': {'Mail.Read', 'Mail.Read.All', 'Mail.ReadWrite', 'Mail.ReadWrite.All'},
                'features': {
                    'list_messages': {'Mail.Read', 'Mail.Read.All', 'Mail.ReadWrite', 'Mail.ReadWrite.All'},
                    'list_sent_items': {'Mail.Read', 'Mail.Read.All', 'Mail.ReadWrite', 'Mail.ReadWrite.All'},
                    'send_email': {'Mail.Send', 'Mail.ReadWrite', 'Mail.ReadWrite.All'}
                }
            },    
            # Entra ID Role Assignment
            'roles': {
                'base': {'RoleManagement.Read.Directory', 'RoleManagement.ReadWrite.Directory', 'Directory.Read.All', 'Directory.ReadWrite.All'},
                'features': {
                    'manage_role_assignments': {'RoleManagement.ReadWrite.Directory'}
                }
            },
            
            # Graph API Notifications
            'graph_notifications': {
                'base': {
                    'ChannelMessage.Read.All', 
                    'Chat.Read.All', 
                    'Chat.ReadWrite.All',
                    'ChatMessage.Read.All',
                    'ChatMessage.ReadWrite.All',
                    'CallRecords.Read.All', 
                    'TeamsActivity.Read.All'
                },
                'features': {
                    'create_subscriptions': {
                        'ChannelMessage.Read.All', 
                        'Chat.Read.All', 
                        'Chat.ReadWrite.All',
                        'ChatMessage.Read.All',
                        'ChatMessage.ReadWrite.All',
                        'CallRecords.Read.All', 
                        'TeamsActivity.Read.All'
                    },
                    'manage_subscriptions': {
                        'ChannelMessage.Read.All', 
                        'Chat.Read.All', 
                        'Chat.ReadWrite.All',
                        'ChatMessage.Read.All',
                        'ChatMessage.ReadWrite.All',
                        'CallRecords.Read.All', 
                        'TeamsActivity.Read.All'
                    }
                }
            },
            
            # Intune
            'intune': {
                'base': {'DeviceManagementManagedDevices.Read.All', 'DeviceManagementManagedDevices.ReadWrite.All'},
                'features': {
                    'list_devices': {'DeviceManagementManagedDevices.Read.All', 'DeviceManagementManagedDevices.ReadWrite.All'},
                    'windows_macos_scripts': {'DeviceManagementScripts.ReadWrite.All'},
                    'linux_scripts': {'DeviceManagementConfiguration.ReadWrite.All', 'DeviceManagementEndpointSecurity.ReadWrite.All'}
                }
            },
            
            # Entra ID - Presence
            'presence': {
                'base': {'Presence.Read.All', 'Presence.ReadWrite.All'}
            }
            
        }
    
    def has_base_access(self, module):
        """Checks if it has base access to the module"""
        if module not in self.modules:
            # Module not found in permissions
            return False  # Module doesn't exist

        base_permissions = self.modules[module]['base']
        has_access = any(permission in self.roles for permission in base_permissions)
        if not has_access:
            # Missing base permissions for module access
            pass
        return has_access

    def has_feature_access(self, module, feature):
        """Checks if it has access to a specific feature of the module"""
        # Checking feature access permissions
        if not self.has_base_access(module):
            # No base access to module
            return False
        if module not in self.modules or feature not in self.modules[module]['features']:
            # Feature not found in module configuration
            return False

        feature_permissions = self.modules[module]['features'][feature]
        has_access = any(permission in self.roles for permission in feature_permissions)
        # Feature access check completed
        if not has_access:
            # Missing permissions for feature access
            pass
        return has_access

    def check_access(self):
        """Returns a dictionary with the access status for each module and its features"""
        access = {}
        for module, config in self.modules.items():
            module_access = {
                'base': self.has_base_access(module),
                'features': {}
            }
            if module_access['base'] and 'features' in config:
                for feature in config['features']:
                    module_access['features'][feature] = self.has_feature_access(module, feature)
            access[module] = module_access
        return access

