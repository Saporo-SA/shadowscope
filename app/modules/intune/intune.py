from app.utils.graph_api import GraphAPI
import json
import base64
from flask import current_app
from typing import List, Dict, Any, Optional

class Intune:
    def __init__(self, graph_api: GraphAPI):
        self.graph_api = graph_api
    
    def _get_script_type_and_endpoint(self, script_id: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Determine script type, platform, and correct endpoint by trying multiple endpoints.
        
        Args:
            script_id: The ID of the script
        
        Returns:
            Tuple of (script_type, platform, endpoint) or (None, None, None) if not found
            script_type: 'PowerShell' or 'Shell'
            platform: 'Windows', 'Linux', or 'macOS'
            endpoint: 'deviceManagementScripts', 'deviceShellScripts', or 'configurationPolicies'
        """
        try:
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            # Try PowerShell endpoint first (Windows)
            try:
                endpoint = f"deviceManagement/deviceManagementScripts/{script_id}"
                script = graph_api_beta.get(endpoint)
                if script is not None:
                    return ('PowerShell', 'Windows', 'deviceManagementScripts')
            except Exception:
                pass
            
            # Try Shell endpoint (macOS)
            try:
                endpoint = f"deviceManagement/deviceShellScripts/{script_id}"
                script = graph_api_beta.get(endpoint)
                if script is not None:
                    return ('Shell', 'macOS', 'deviceShellScripts')
            except Exception:
                pass
            
            # Try Linux configurationPolicies
            try:
                endpoint = f"deviceManagement/configurationPolicies/{script_id}"
                policy = graph_api_beta.get(endpoint)
                if policy is not None:
                    template_ref = policy.get('templateReference', {})
                    template_family = template_ref.get('templateFamily', '')
                    platforms = policy.get('platforms', '')
                    
                    if template_family == 'deviceConfigurationScripts' and platforms == 'Linux':
                        return ('Shell', 'Linux', 'configurationPolicies')
            except Exception:
                pass
            
            return (None, None, None)
        except Exception as e:
            current_app.logger.debug(f"Error detecting script type: {e}")
            return (None, None, None)
    
    def _get_script_platform(self, script: Dict[str, Any]) -> str:
        """
        Get platform information from script metadata.
        
        Args:
            script: Script dictionary
        
        Returns:
            Platform string: 'Windows', 'Linux', 'macOS', or 'Unknown'
        """
        odata_type = script.get('@odata.type', '')
        script_type = script.get('scriptType', '')
        platform = script.get('platform', '')
        platforms = script.get('platforms', '')
        
        if platform:
            return platform
        
        if platforms:
            platforms_lower = platforms.lower()
            if 'linux' in platforms_lower:
                return 'Linux'
            elif 'macos' in platforms_lower or 'mac os' in platforms_lower:
                return 'macOS'
            elif 'windows' in platforms_lower:
                return 'Windows'
        
        if 'deviceShellScript' in odata_type:
            return 'macOS'
        elif 'deviceManagementScript' in odata_type or script_type == 'PowerShell':
            return 'Windows'
        elif script_type == 'Shell':
            return 'Linux'
        
        return 'Unknown'
    
    def _extract_linux_script_from_policy(self, policy: Dict[str, Any]) -> Optional[str]:
        """
        Extract script content from Linux configuration policy.
        
        Args:
            policy: Configuration policy dictionary
        
        Returns:
            Decoded script content or None if not found
        """
        try:
            settings = policy.get('settings', [])
            for setting in settings:
                setting_instance = setting.get('settingInstance', {})
                setting_definition_id = setting_instance.get('settingDefinitionId', '')
                
                if setting_definition_id == 'linux_customconfig_script':
                    simple_setting_value = setting_instance.get('simpleSettingValue', {})
                    script_content_b64 = simple_setting_value.get('value', '')
                    
                    if script_content_b64:
                        try:
                            script_content = base64.b64decode(script_content_b64).decode('utf-8')
                            return script_content
                        except Exception as e:
                            current_app.logger.warning(f"Failed to decode Linux script content: {e}")
                            return None
        except Exception as e:
            current_app.logger.warning(f"Error extracting Linux script from policy: {e}")
        
        return None

    def get_intune_devices(self, filter_os: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get all Intune managed devices.
        
        Args:
            filter_os: Optional list of operating systems to filter by (e.g., ['Windows', 'Linux'])
        
        Returns:
            List of device dictionaries
        """
        try:    
            from app.utils.graph_api import GraphAPI
            
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            endpoint = "deviceManagement/managedDevices"
            params = {}
            
            if filter_os:
                filter_conditions = [f"operatingSystem eq '{os}'" for os in filter_os]
                params['$filter'] = ' or '.join(filter_conditions)
            
            devices = graph_api_beta.get_paginated(endpoint, params=params)
            
            if devices is None:
                current_app.logger.warning("No devices returned from API (response was None)")
                return []
            
            intune_devices = [
                device for device in devices 
                if device.get('managementAgent', '').lower() in ['mdm', 'easmdm', 'intunemdmandeas', 'configurationmanagerlient']
            ]
            
            current_app.logger.info(f"Retrieved {len(intune_devices)} Intune managed devices (filtered from {len(devices)} total devices)")
            return intune_devices
        except Exception as e:
            current_app.logger.error(f"Error getting Intune devices: {e}", exc_info=True)
            return []
    
    def run_script(self, script_id: str, device_id: str) -> Dict[str, Any]:
        """
        Run a script on an Intune device.
        
        Args:
            script_id: The ID of the script to run
            device_id: The ID of the device to run the script on
        
        Returns:
            Dictionary with operation result
        """
        try:
            endpoint = f"deviceManagement/deviceManagementScripts/{script_id}/assign"
            
            payload = {
                "deviceManagementScriptAssignments": [
                    {
                        "target": {
                            "@odata.type": "#microsoft.graph.groupAssignmentTarget",
                            "deviceAndAppManagementAssignmentFilterId": None,
                            "deviceAndAppManagementAssignmentFilterType": "none"
                        }
                    }
                ]
            }
            
            response = self.graph_api.post(endpoint, payload)
            
            if response.status_code in [200, 201, 204]:
                return {
                    'success': True,
                    'message': 'Script execution initiated successfully'
                }
            else:
                error_msg = f"Failed to run script: HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', error_msg)
                except (ValueError, KeyError, TypeError):
                    pass
                
                current_app.logger.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }
        except Exception as e:
            error_msg = f"Error running script: {str(e)}"
            current_app.logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
    
    def get_scripts(self) -> List[Dict[str, Any]]:
        """
        Get all Intune device management scripts from PowerShell, Shell (macOS), and Linux endpoints.
        
        Returns:
            List of script dictionaries with scriptType and platform metadata
        """
        try:
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            all_scripts = []
            
            # Fetch PowerShell scripts (Windows)
            try:
                endpoint = "deviceManagement/deviceManagementScripts"
                scripts = graph_api_beta.get_paginated(endpoint)
                if scripts:
                    for script in scripts:
                        script['scriptType'] = 'PowerShell'
                        script['platform'] = 'Windows'
                        script['@odata.type'] = script.get('@odata.type', '#microsoft.graph.deviceManagementScript')
                    all_scripts.extend(scripts)
            except Exception as e:
                current_app.logger.warning(f"Error fetching PowerShell scripts: {e}")
            
            # Fetch Shell scripts (macOS)
            try:
                endpoint = "deviceManagement/deviceShellScripts"
                scripts = graph_api_beta.get_paginated(endpoint)
                if scripts:
                    for script in scripts:
                        script['scriptType'] = 'Shell'
                        script['platform'] = 'macOS'
                        script['@odata.type'] = script.get('@odata.type', '#microsoft.graph.deviceShellScript')
                    all_scripts.extend(scripts)
            except Exception as e:
                current_app.logger.warning(f"Error fetching macOS Shell scripts: {e}")
            
            # Fetch Linux scripts from configurationPolicies
            try:
                endpoint = "deviceManagement/configurationPolicies"
                params = {
                    '$filter': "templateReference/templateFamily eq 'deviceConfigurationScripts'",
                    '$select': 'id,name,description,platforms,lastModifiedDateTime,technologies,settingCount,roleScopeTagIds,isAssigned,templateReference'
                }
                policies = graph_api_beta.get_paginated(endpoint, params=params)
                current_app.logger.info(f"Found {len(policies) if policies else 0} configuration policies with deviceConfigurationScripts template")
                
                if policies:
                    linux_policies = []
                    for policy in policies:
                        platforms = policy.get('platforms', '')
                        template_ref = policy.get('templateReference', {})
                        template_family = template_ref.get('templateFamily', '') if isinstance(template_ref, dict) else ''
                        
                        if platforms == 'Linux' or (platforms == 'Linux' and template_family == 'deviceConfigurationScripts'):
                            linux_policies.append(policy)
                    
                    current_app.logger.info(f"Found {len(linux_policies)} Linux configuration policies")
                    
                    for policy in linux_policies:
                        policy_id = policy.get('id')
                        if policy_id:
                            try:
                                full_policy = graph_api_beta.get(f"{endpoint}/{policy_id}")
                                if full_policy:
                                    script_content = self._extract_linux_script_from_policy(full_policy)
                                    full_policy['scriptType'] = 'Shell'
                                    full_policy['platform'] = 'Linux'
                                    full_policy['scriptContent'] = script_content
                                    full_policy['displayName'] = full_policy.get('name', '')
                                    full_policy['fileName'] = 'script.sh'
                                    full_policy['lastModifiedDateTime'] = full_policy.get('lastModifiedDateTime', policy.get('lastModifiedDateTime'))
                                    full_policy['@odata.type'] = '#microsoft.graph.deviceManagementConfigurationPolicy'
                                    all_scripts.append(full_policy)
                            except Exception as e:
                                current_app.logger.warning(f"Error fetching full Linux script policy {policy_id}: {e}", exc_info=True)
                                policy['scriptType'] = 'Shell'
                                policy['platform'] = 'Linux'
                                policy['displayName'] = policy.get('name', '')
                                policy['fileName'] = 'script.sh'
                                policy['scriptContent'] = None
                                policy['@odata.type'] = '#microsoft.graph.deviceManagementConfigurationPolicy'
                                all_scripts.append(policy)
                else:
                    current_app.logger.info("No configuration policies found, trying without filter")
                    try:
                        all_policies = graph_api_beta.get_paginated(endpoint, params={'$select': 'id,name,description,platforms,lastModifiedDateTime,templateReference'})
                        if all_policies:
                            for policy in all_policies:
                                platforms = policy.get('platforms', '')
                                template_ref = policy.get('templateReference', {})
                                template_family = template_ref.get('templateFamily', '') if isinstance(template_ref, dict) else ''
                                
                                if platforms == 'Linux' and template_family == 'deviceConfigurationScripts':
                                    policy_id = policy.get('id')
                                    if policy_id:
                                        try:
                                            full_policy = graph_api_beta.get(f"{endpoint}/{policy_id}")
                                            if full_policy:
                                                script_content = self._extract_linux_script_from_policy(full_policy)
                                                full_policy['scriptType'] = 'Shell'
                                                full_policy['platform'] = 'Linux'
                                                full_policy['scriptContent'] = script_content
                                                full_policy['displayName'] = full_policy.get('name', '')
                                                full_policy['fileName'] = 'script.sh'
                                                full_policy['lastModifiedDateTime'] = full_policy.get('lastModifiedDateTime', policy.get('lastModifiedDateTime'))
                                                full_policy['@odata.type'] = '#microsoft.graph.deviceManagementConfigurationPolicy'
                                                all_scripts.append(full_policy)
                                        except Exception as e:
                                            current_app.logger.warning(f"Error fetching Linux script policy {policy_id}: {e}", exc_info=True)
                    except Exception as e2:
                        current_app.logger.warning(f"Error fetching all policies: {e2}", exc_info=True)
            except Exception as e:
                current_app.logger.error(f"Error fetching Linux scripts: {e}", exc_info=True)
            
            if not all_scripts:
                current_app.logger.warning("No scripts returned from API")
                return []
            
            powershell_count = len([s for s in all_scripts if s.get('scriptType') == 'PowerShell'])
            shell_macos_count = len([s for s in all_scripts if s.get('platform') == 'macOS'])
            shell_linux_count = len([s for s in all_scripts if s.get('platform') == 'Linux'])
            
            current_app.logger.info(f"Retrieved {len(all_scripts)} Intune scripts ({powershell_count} PowerShell/Windows, {shell_macos_count} Shell/macOS, {shell_linux_count} Shell/Linux)")
            return all_scripts
        except Exception as e:
            current_app.logger.error(f"Error getting Intune scripts: {e}", exc_info=True)
            return []
    
    def get_script(self, script_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific Intune script by ID (tries PowerShell, Shell/macOS, and Linux endpoints).
        
        Args:
            script_id: The ID of the script to retrieve
        
        Returns:
            Script dictionary or None if not found
        """
        try:
            script_type, platform, endpoint_base = self._get_script_type_and_endpoint(script_id)
            
            if script_type is None:
                current_app.logger.warning(f"Script {script_id} not found")
                return None
            
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            endpoint = f"deviceManagement/{endpoint_base}/{script_id}"
            script = graph_api_beta.get(endpoint)
            
            if script is None:
                current_app.logger.warning(f"Script {script_id} not found")
                return None
            
            script['scriptType'] = script_type
            script['platform'] = platform
            
            if endpoint_base == 'configurationPolicies':
                script_content = self._extract_linux_script_from_policy(script)
                script['scriptContent'] = script_content
                script['displayName'] = script.get('name', '')
                script['fileName'] = 'script.sh'
            elif script.get('scriptContent'):
                try:
                    script['scriptContent'] = base64.b64decode(script['scriptContent']).decode('utf-8')
                except Exception as e:
                    current_app.logger.warning(f"Failed to decode script content: {e}")
            
            assignments = self.get_script_assignments(script_id, script_type, platform, endpoint_base)
            if assignments:
                script['assignments'] = assignments
            
            return script
        except Exception as e:
            current_app.logger.error(f"Error getting Intune script {script_id}: {e}", exc_info=True)
            return None
    
    def get_script_assignments(self, script_id: str, script_type: Optional[str] = None, 
                              platform: Optional[str] = None, endpoint_base: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get assignments for a specific Intune script.
        
        Args:
            script_id: The ID of the script
            script_type: Optional script type ('PowerShell' or 'Shell')
            platform: Optional platform ('Windows', 'Linux', or 'macOS')
            endpoint_base: Optional endpoint base name
        
        Returns:
            List of assignment dictionaries
        """
        try:
            if endpoint_base is None:
                if platform == 'Linux':
                    endpoint_base = 'configurationPolicies'
                elif platform == 'macOS':
                    endpoint_base = 'deviceShellScripts'
                else:
                    endpoint_base = 'deviceManagementScripts'
            
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            if endpoint_base == 'configurationPolicies':
                endpoint = f"deviceManagement/{endpoint_base}/{script_id}/assignments"
            elif endpoint_base == 'deviceShellScripts':
                endpoint = f"deviceManagement/{endpoint_base}/{script_id}/assignments"
            else:
                endpoint = f"deviceManagement/{endpoint_base}/{script_id}/assignments"
            
            assignments = graph_api_beta.get_paginated(endpoint)
            
            if not assignments:
                return []
            
            return assignments
        except Exception as e:
            current_app.logger.error(f"Error getting script assignments: {e}", exc_info=True)
            return []
    
    def _build_linux_configuration_policy(self, name: str, description: str, script_content: str, 
                                         run_as_account: str = "system") -> Dict[str, Any]:
        """
        Build configuration policy payload for Linux scripts.
        
        Args:
            name: Display name of the script
            description: Description of the script
            script_content: The script content (will be base64 encoded)
            run_as_account: Account to run as ("system" or "user")
        
        Returns:
            Dictionary with configuration policy payload
        """
        script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('utf-8')
        
        execution_context_value = "linux_customconfig_executioncontext_root" if run_as_account.lower() == "system" else "linux_customconfig_executioncontext_user"
        execution_context_template_id = "119f0327-4114-444a-b53d-4b55fd579e43"
        execution_context_instance_template_id = "2c59a6c5-e874-445b-ac5a-d53688ef838e"
        
        execution_frequency_value = "linux_customconfig_executionfrequency_15minutes"
        execution_frequency_template_id = "d0fb527e-606e-455f-891d-2a4de6a5db90"
        execution_frequency_instance_template_id = "f42b866f-ff2b-4d19-bef8-63e7c763d49b"
        
        execution_retries_value = "linux_customconfig_executionretries_2"
        execution_retries_template_id = "92b31053-6ebb-4d2d-9e4d-081fe15d5d21"
        execution_retries_instance_template_id = "a3326517-152b-4b32-bc11-8772b5b4fe6a"
        
        script_template_id = "18dc8a98-2ecd-4753-8baf-3ab7a1d677a9"
        script_instance_template_id = "add4347a-f9aa-4202-a497-34a4c178d013"
        
        payload = {
            "name": name,
            "description": description,
            "platforms": "Linux",
            "technologies": "linuxMdm",
            "roleScopeTagIds": ["0"],
            "settings": [
                {
                    "@odata.type": "#microsoft.graph.deviceManagementConfigurationSetting",
                    "settingInstance": {
                        "@odata.type": "#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance",
                        "settingDefinitionId": "linux_customconfig_executioncontext",
                        "choiceSettingValue": {
                            "@odata.type": "#microsoft.graph.deviceManagementConfigurationChoiceSettingValue",
                            "value": execution_context_value,
                            "children": [],
                            "settingValueTemplateReference": {
                                "settingValueTemplateId": execution_context_template_id
                            }
                        },
                        "settingInstanceTemplateReference": {
                            "settingInstanceTemplateId": execution_context_instance_template_id
                        }
                    }
                },
                {
                    "@odata.type": "#microsoft.graph.deviceManagementConfigurationSetting",
                    "settingInstance": {
                        "@odata.type": "#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance",
                        "settingDefinitionId": "linux_customconfig_executionfrequency",
                        "choiceSettingValue": {
                            "@odata.type": "#microsoft.graph.deviceManagementConfigurationChoiceSettingValue",
                            "value": execution_frequency_value,
                            "children": [],
                            "settingValueTemplateReference": {
                                "settingValueTemplateId": execution_frequency_template_id
                            }
                        },
                        "settingInstanceTemplateReference": {
                            "settingInstanceTemplateId": execution_frequency_instance_template_id
                        }
                    }
                },
                {
                    "@odata.type": "#microsoft.graph.deviceManagementConfigurationSetting",
                    "settingInstance": {
                        "@odata.type": "#microsoft.graph.deviceManagementConfigurationChoiceSettingInstance",
                        "settingDefinitionId": "linux_customconfig_executionretries",
                        "choiceSettingValue": {
                            "@odata.type": "#microsoft.graph.deviceManagementConfigurationChoiceSettingValue",
                            "value": execution_retries_value,
                            "children": [],
                            "settingValueTemplateReference": {
                                "settingValueTemplateId": execution_retries_template_id
                            }
                        },
                        "settingInstanceTemplateReference": {
                            "settingInstanceTemplateId": execution_retries_instance_template_id
                        }
                    }
                },
                {
                    "@odata.type": "#microsoft.graph.deviceManagementConfigurationSetting",
                    "settingInstance": {
                        "@odata.type": "#microsoft.graph.deviceManagementConfigurationSimpleSettingInstance",
                        "settingDefinitionId": "linux_customconfig_script",
                        "simpleSettingValue": {
                            "@odata.type": "#microsoft.graph.deviceManagementConfigurationStringSettingValue",
                            "value": script_content_b64,
                            "settingValueTemplateReference": {
                                "settingValueTemplateId": script_template_id
                            }
                        },
                        "settingInstanceTemplateReference": {
                            "settingInstanceTemplateId": script_instance_template_id
                        }
                    }
                }
            ],
            "templateReference": {
                "templateId": "92439f26-2b30-4503-8429-6d40f7e172dd_1"
            }
        }
        
        return payload
    
    def create_script(self, name: str, description: str, script_content: str, 
                     run_as_account: str = "system", enforce_signature_check: bool = False,
                     run_as32bit: bool = False, script_type: str = "PowerShell", 
                     platform: str = None) -> Dict[str, Any]:
        """
        Create a new Intune device management script.
        
        Args:
            name: Display name of the script
            description: Description of the script
            script_content: The script content (will be base64 encoded)
            run_as_account: Account to run as ("system" or "user")
            enforce_signature_check: Whether to enforce signature check (PowerShell only)
            run_as32bit: Whether to run as 32-bit (PowerShell only)
            script_type: Script type ("PowerShell" or "Shell")
            platform: Platform ("Windows", "Linux", or "macOS"). If None, inferred from script_type
        
        Returns:
            Dictionary with operation result
        """
        try:
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            script_type_lower = script_type.lower()
            is_shell = script_type_lower == "shell"
            
            if platform is None:
                if is_shell:
                    platform = "Linux"
                else:
                    platform = "Windows"
            
            platform_lower = platform.lower()
            
            if platform_lower == "linux":
                endpoint = "deviceManagement/configurationPolicies"
                payload = self._build_linux_configuration_policy(name, description, script_content, run_as_account)
            elif platform_lower == "macos":
                script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('utf-8')
                file_extension = ".sh"
                file_name = f"{name.replace(' ', '_')}{file_extension}"
                endpoint = "deviceManagement/deviceShellScripts"
                payload = {
                    "@odata.type": "#microsoft.graph.deviceShellScript",
                    "displayName": name,
                    "description": description,
                    "scriptContent": script_content_b64,
                    "runAsAccount": run_as_account,
                    "fileName": file_name
                }
            else:
                script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('utf-8')
                file_extension = ".ps1"
                file_name = f"{name.replace(' ', '_')}{file_extension}"
                endpoint = "deviceManagement/deviceManagementScripts"
                payload = {
                    "@odata.type": "#microsoft.graph.deviceManagementScript",
                    "displayName": name,
                    "description": description,
                    "scriptContent": script_content_b64,
                    "runAsAccount": run_as_account,
                    "enforceSignatureCheck": enforce_signature_check,
                    "runAs32Bit": run_as32bit,
                    "fileName": file_name
                }
            
            response = graph_api_beta.post(endpoint, payload)
            
            if response.status_code in [200, 201]:
                try:
                    script_data = response.json()
                    return {
                        'success': True,
                        'message': 'Script created successfully',
                        'script': script_data
                    }
                except (ValueError, KeyError, TypeError):
                    return {
                        'success': True,
                        'message': 'Script created successfully'
                    }
            else:
                error_msg = f"Failed to create script: HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', error_msg)
                except (ValueError, KeyError, TypeError):
                    pass
                
                current_app.logger.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }
        except Exception as e:
            error_msg = f"Error creating script: {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg
            }
    
    def update_script(self, script_id: str, name: str = None, description: str = None,
                     script_content: str = None, run_as_account: str = None,
                     enforce_signature_check: bool = None, run_as32bit: bool = None) -> Dict[str, Any]:
        """
        Update an existing Intune script.
        
        Args:
            script_id: The ID of the script to update
            name: Display name (optional)
            description: Description (optional)
            script_content: Script content (optional, will be base64 encoded)
            run_as_account: Account to run as (optional)
            enforce_signature_check: Whether to enforce signature check (optional, PowerShell only)
            run_as32bit: Whether to run as 32-bit (optional, PowerShell only)
        
        Returns:
            Dictionary with operation result
        """
        try:
            script_type, platform, endpoint_base = self._get_script_type_and_endpoint(script_id)
            if script_type is None:
                return {
                    'success': False,
                    'message': 'Script not found'
                }
            
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            if endpoint_base == 'configurationPolicies':
                if script_content is None and name is None and description is None:
                    return {
                        'success': False,
                        'message': 'No fields to update'
                    }
                current_policy = graph_api_beta.get(f"deviceManagement/{endpoint_base}/{script_id}")
                if current_policy is None:
                    return {
                        'success': False,
                        'message': 'Script not found'
                    }
                payload = self._build_linux_configuration_policy(
                    name or current_policy.get('name', ''),
                    description if description is not None else current_policy.get('description', ''),
                    script_content or self._extract_linux_script_from_policy(current_policy) or '',
                    run_as_account or 'system'
                )
                endpoint = f"deviceManagement/{endpoint_base}/{script_id}"
                response = graph_api_beta.patch(endpoint, payload)
            else:
                payload = {}
                if name is not None:
                    payload['displayName'] = name
                if description is not None:
                    payload['description'] = description
                if script_content is not None:
                    script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('utf-8')
                    payload['scriptContent'] = script_content_b64
                if run_as_account is not None:
                    payload['runAsAccount'] = run_as_account
                
                # Only include PowerShell-specific fields for PowerShell scripts
                if script_type == 'PowerShell':
                    if enforce_signature_check is not None:
                        payload['enforceSignatureCheck'] = enforce_signature_check
                    if run_as32bit is not None:
                        payload['runAs32Bit'] = run_as32bit
                
                if not payload:
                    return {
                        'success': False,
                        'message': 'No fields to update'
                    }
                
                endpoint = f"deviceManagement/{endpoint_base}/{script_id}"
                response = graph_api_beta.patch(endpoint, payload)
            
            if response.status_code in [200, 204]:
                return {
                    'success': True,
                    'message': 'Script updated successfully'
                }
            else:
                error_msg = f"Failed to update script: HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', error_msg)
                except (ValueError, KeyError, TypeError):
                    pass
                
                current_app.logger.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }
        except Exception as e:
            error_msg = f"Error updating script: {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg
            }
    
    def delete_script(self, script_id: str) -> Dict[str, Any]:
        """
        Delete an Intune script (tries PowerShell, Shell/macOS, and Linux endpoints).
        
        Args:
            script_id: The ID of the script to delete
        
        Returns:
            Dictionary with operation result
        """
        try:
            script_type, platform, endpoint_base = self._get_script_type_and_endpoint(script_id)
            if script_type is None:
                return {
                    'success': False,
                    'message': 'Script not found'
                }
            
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            endpoint = f"deviceManagement/{endpoint_base}/{script_id}"
            response = graph_api_beta.delete(endpoint)
            
            if response.status_code in [200, 204]:
                return {
                    'success': True,
                    'message': 'Script deleted successfully'
                }
            else:
                error_msg = f"Failed to delete script: HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', error_msg)
                except (ValueError, KeyError, TypeError):
                    pass
                
                current_app.logger.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg
                }
        except Exception as e:
            error_msg = f"Error deleting script: {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg
            }
    
    def execute_script(self, script_id: str, assignment_type: str, group_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a script by assigning it based on assignment type.
        
        Args:
            script_id: The ID of the script to execute
            assignment_type: Type of assignment - 'select_groups', 'all_devices', or 'all_users'
            group_id: Required when assignment_type is 'select_groups'
        
        Returns:
            Dictionary with operation result
        """
        try:
            script_type, platform, endpoint_base = self._get_script_type_and_endpoint(script_id)
            if script_type is None:
                return {
                    'success': False,
                    'message': 'Script not found'
                }
            
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            if endpoint_base == 'configurationPolicies':
                endpoint = f"deviceManagement/{endpoint_base}/{script_id}/assign"
            else:
                endpoint = f"deviceManagement/{endpoint_base}/{script_id}/assign"
            
            if assignment_type == 'select_groups':
                if not group_id:
                    return {
                        'success': False,
                        'message': 'Group ID is required for select_groups assignment'
                    }
                target = {
                    "@odata.type": "#microsoft.graph.groupAssignmentTarget",
                    "groupId": group_id
                }
            elif assignment_type == 'all_devices':
                target = {
                    "@odata.type": "#microsoft.graph.allDevicesAssignmentTarget"
                }
            elif assignment_type == 'all_users':
                target = {
                    "@odata.type": "#microsoft.graph.allLicensedUsersAssignmentTarget"
                }
            else:
                return {
                    'success': False,
                    'message': f'Invalid assignment type: {assignment_type}'
                }
            
            payload = {
                "deviceManagementScriptAssignments": [
                    {
                        "target": target
                    }
                ]
            }
            
            response = graph_api_beta.post(endpoint, payload)
            
            if response.status_code in [200, 201, 204]:
                message = 'Script assigned successfully'
                if assignment_type == 'select_groups':
                    message = 'Script assigned successfully to selected group'
                elif assignment_type == 'all_devices':
                    message = 'Script assigned successfully to all devices'
                elif assignment_type == 'all_users':
                    message = 'Script assigned successfully to all users'
                
                return {
                    'success': True,
                    'message': message
                }
            else:
                error_msg = f"Failed to assign script: HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', error_msg)
                    else:
                        error_msg = str(error_data)
                except (ValueError, KeyError, TypeError):
                    try:
                        error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    except:
                        pass
                
                current_app.logger.error(f"Script assignment error: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg
                }
        except Exception as e:
            error_msg = f"Error assigning script: {str(e)}"
            current_app.logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': error_msg
            }
    
    def get_script_execution_status(self, script_id: str, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the execution status of a script on a device.
        
        Args:
            script_id: The ID of the script
            device_id: The ID of the device
        
        Returns:
            Execution status dictionary or None if not found
        """
        try:
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            endpoint = f"deviceManagement/deviceManagementScripts/{script_id}/deviceRunStates"
            params = {'$filter': f"managedDeviceId eq '{device_id}'"}
            
            states = graph_api_beta.get_paginated(endpoint, params=params)
            
            if states and len(states) > 0:
                return states[0]
            return None
        except Exception as e:
            current_app.logger.error(f"Error getting script execution status: {e}", exc_info=True)
            return None
    
    def get_script_run_summary(self, script_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the run summary for a script execution.
        
        Tries multiple endpoints in order:
        1. deviceManagementScripts (most common - PowerShell scripts)
        2. deviceShellScripts (Shell scripts)
        3. deviceCustomAttributeShellScripts (Custom attribute scripts)
        
        Also fetches the most recent execution timestamp from deviceRunStates.
        
        Args:
            script_id: The ID of the script
        
        Returns:
            Run summary dictionary with successDeviceCount, errorDeviceCount, lastExecutionDateTime, etc. or None if not found
        """
        try:
            access_token = self.graph_api.headers['Authorization'].replace('Bearer ', '')
            graph_api_beta = GraphAPI(access_token, use_beta=True)
            
            endpoints = [
                f"deviceManagement/deviceManagementScripts/{script_id}/runSummary",
                f"deviceManagement/deviceShellScripts/{script_id}/runSummary",
                f"deviceManagement/deviceCustomAttributeShellScripts/{script_id}/runSummary"
            ]
            
            run_summary = None
            script_type = None
            
            for i, endpoint in enumerate(endpoints):
                try:
                    response = graph_api_beta.get(endpoint, raw_response=True)
                    
                    if response is None:
                        continue
                    
                    if response.status_code == 200:
                        try:
                            run_summary = response.json()
                            if i == 0:
                                script_type = 'deviceManagementScripts'
                            elif i == 1:
                                script_type = 'deviceShellScripts'
                            else:
                                script_type = 'deviceCustomAttributeShellScripts'
                            break
                        except (ValueError, KeyError, TypeError) as e:
                            current_app.logger.debug(f"Failed to parse response from {endpoint}: {e}")
                            continue
                    elif response.status_code == 404:
                        continue
                except Exception as e:
                    current_app.logger.debug(f"Endpoint {endpoint} failed: {e}")
                    continue
            
            if run_summary is None:
                return None
            
            try:
                if script_type == 'deviceManagementScripts':
                    run_states_endpoint = f"deviceManagement/deviceManagementScripts/{script_id}/deviceRunStates"
                elif script_type == 'deviceShellScripts':
                    run_states_endpoint = f"deviceManagement/deviceShellScripts/{script_id}/deviceRunStates"
                else:
                    run_states_endpoint = f"deviceManagement/deviceCustomAttributeShellScripts/{script_id}/deviceRunStates"
                
                run_states = graph_api_beta.get_paginated(run_states_endpoint)
                
                if run_states and len(run_states) > 0:
                    last_execution = None
                    for state in run_states:
                        execution_state = state.get('lastStateUpdateDateTime') or state.get('lastSyncDateTime')
                        if execution_state:
                            if last_execution is None or execution_state > last_execution:
                                last_execution = execution_state
                    
                    if last_execution:
                        run_summary['lastExecutionDateTime'] = last_execution
            except Exception as e:
                current_app.logger.debug(f"Failed to get execution timestamp: {e}")
            
            return run_summary
        except Exception as e:
            current_app.logger.error(f"Error getting script run summary: {e}", exc_info=True)
            return None