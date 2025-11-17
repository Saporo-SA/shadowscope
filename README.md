<div align="center">

```
███████╗██╗  ██╗ █████╗ ██████╗  ██████╗ ██╗    ██╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗
██╔════╝██║  ██║██╔══██╗██╔══██╗██╔═══██╗██║    ██║██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝
███████╗███████║███████║██║  ██║██║   ██║██║ █╗ ██║███████╗██║     ██║   ██║██████╔╝█████╗  
╚════██║██╔══██║██╔══██║██║  ██║██║   ██║██║███╗██║╚════██║██║     ██║   ██║██╔═══╝ ██╔══╝  
███████║██║  ██║██║  ██║██████╔╝╚██████╔╝╚███╔███╔╝███████║╚██████╗╚██████╔╝██║     ███████╗
╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝  ╚══╝╚══╝ ╚══════╝ ╚═════╝ ╚═════╝ ╚═╝     ╚══════╝
```

### Advanced Red Team Assessment Tool for Microsoft 365 & Azure

[![GPL v3](https://img.shields.io/badge/License-GPL%20v3-ff715b?style=flat-square)](LICENSE)
[![By SAPORO](https://img.shields.io/badge/By-SAPORO-ff715b?style=flat-square)](https://saporo.io)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)](https://www.python.org/)

</div>

## 🎯 Overview

**ShadowScope** is a comprehensive offensive security assessment tool designed for Red Team operations against Microsoft 365 and Azure environments. It provides a centralized dashboard for enumeration, privilege escalation assessment, lateral movement planning, and data exfiltration capabilities within compromised tenants.

Built with a focus on **attack surface visualization**, ShadowScope automatically maps available attack vectors based on Microsoft Graph API permissions, enabling security professionals to understand the full scope of compromise from a single service principal or access token.

### 🎯 Core Abuse Approach

ShadowScope specializes in **abusing excessive permissions granted to Service Principals** — a common misconfiguration in enterprise environments. The tool performs:

- **Automated Graph API Permission Enumeration**: Instantly identifies all Microsoft Graph API permissions assigned to a compromised service principal, revealing the complete attack surface across Entra ID and Microsoft 365
- **Azure Resource Access Validation (Alpha)**: Verifies service principal access to Azure infrastructure through the Azure Management REST API, including subscriptions, resource groups, and management group hierarchies
- **Permission-to-Attack Mapping**: Translates abstract API permissions into concrete offensive capabilities, showing exactly what actions can be performed with the current privilege level
- **Cross-Platform Compromise Assessment**: Evaluates potential impact across both identity (Entra ID/Graph API) and infrastructure (Azure Resources) layers

By leveraging overprivileged service principals, the tool demonstrates the real-world impact of excessive permission grants, helping security teams identify misconfigurations and enforce the principle of least privilege in their Azure/M365 deployments.

## 🚀 Key Features

### 🔐 Authentication Methods

ShadowScope supports multiple authentication approaches:

- **Service Principal Authentication**: Authenticate using Client ID, Client Secret, and Tenant ID
- **Access Token Authentication**: Directly use Microsoft Graph API tokens
- **Azure Management Token**: Optional REST API token for Azure Resource Management access

### 📊 Attack Surface Dashboard

The main dashboard provides real-time visualization of:

- **Attack Vectors Count**: Number of available attack techniques based on permissions
- **API Permissions**: Complete list of Microsoft Graph API permissions granted
- **Accessible Resources**: Count of enumerated resources (users, groups, files, etc.)
- **Privilege Level**: Calculated percentage representing compromise severity
- **Attack Likelihood Meter**: Visual gradient showing overall attack potential (Low → Critical)

### ⚔️ Attack Tactics Mapping

#### 🔺 **Privilege Escalation**
- Assign Entra ID roles to controlled users
- Add users to privileged groups
- Grant Microsoft Graph API permissions
- Add secrets to service principals

#### 🔄 **Lateral Movement**
- Compromise service principals
- Expand API permissions
- Hijack group memberships

#### 🎣 **Phishing**
- Send emails on behalf of users
- Weaponize SharePoint files

#### 📤 **Data Exfiltration**
- Extract confidential documents from SharePoint
- Read private Teams conversations
- Access email attachments
- Read all user emails

#### ♾️ **Persistence**
- Grant persistent API permissions
- Create backdoor credentials

#### 🔍 **Discovery**
- Enumerate user accounts
- List service principals
- Map group structures
- Identify role assignments
- Browse SharePoint sites
- Discover Teams channels

---

## 🏢 Entra ID (Azure AD) Features

### 👤 Users
- **List all users** in the tenant
- **View detailed user information**: UPN, display name, account status
- **On-Premises Synchronization Detection**: Identify users synchronized from on-premises Active Directory
- **Manage authentication methods**: View and reset MFA/passwordless methods
- **Group memberships**: See which groups users belong to
- **User presence status**: Check real-time presence status (Available, Away, Busy, Offline)
- **Aggregated role view**: View all roles (Entra ID directory roles + Azure RBAC roles) in a unified interface

### 👥 Groups
- **Enumerate all security and Microsoft 365 groups**
- **Role-Assignable Group Detection**: Identify groups that can be assigned to Entra ID roles
- **Dynamic Group Identification**: Detect dynamic groups and view their membership rules
- **Dynamic Membership Rule Analysis**: Extract and display the filter rules used for dynamic group membership
- **Group membership management**: Add/remove members
- **Nested group visualization**
- **Owner and member listings**

### 🏛️ Administrative Units
- **List administrative units** for delegated administration
- **View AU memberships**
- **Manage AU member assignments**: Add/remove members

### 🔑 Service Principals (Enterprise Applications)
- **List all service principals** in the tenant
- **Enumerate all Microsoft Graph API permissions** granted to applications
- **View application permissions and roles assigned to the Service Principal** 
- **Add new Graph API permissions** to service principals for privilege escalation
- **Add client secrets** to service principals for persistence or application lateral movement or privilege escalation
- **Manage role assignments**
- **API permission analysis**

### 👑 Roles
- **Enumerate all Entra ID roles**
- **View role members**
- **Identify privileged role assignments**
- **Role assignment capabilities** (privilege escalation)

---

## 📧 Microsoft 365 Features

### 📨 Outlook (Email)
- **List all users with mailboxes**
- **Read user emails**: Inbox, Sent Items, Drafts
- **View email details**: Subject, sender, recipients, body
- **Download attachments**
- **Compose and send emails** on behalf of users
- **Email search functionality**

### 📁 SharePoint
- **List all SharePoint sites** in the organization
- **Browse document libraries and drives**
- **Navigate folder structures**
- **Download files and documents**
- **File metadata extraction**
- **Advanced threat hunting**: Search across SharePoint for sensitive keywords

### 💬 Teams
- **List all Microsoft Teams**
- **Enumerate team members**
- **Team membership management**: Add/remove team members
- **Browse channels within teams**
- **Channel membership management**: Add/remove channel members
- **Read channel messages and conversations**
- **View channel members**
- **Teams structure mapping**

---

## 📱 Microsoft Intune Features

### 🖥️ Device Management
- **List all Intune managed devices** across Windows, macOS, iOS, Android, and Linux platforms
- **Filter devices by operating system** for targeted enumeration
- **View device details**: Device name, OS version, compliance status, enrollment date
- **Device type identification**: Desktop, laptop, mobile, tablet
- **Management agent detection**: MDM, EAS MDM, Intune MDM and EAS, Configuration Manager Client

### 📜 Script Management
- **Enumerate device management scripts**: PowerShell scripts (Windows), Shell scripts (macOS), and Linux configuration scripts
- **View script content**: Decode and display script source code
- **Create new scripts**: Deploy PowerShell, Shell, or Linux scripts to managed devices
- **Update existing scripts**: Modify script content, execution context, and configuration
- **Delete scripts**: Remove device management scripts
- **Script assignment management**: Assign scripts to specific groups, all devices, or all users
- **View script execution status**: Monitor script run summaries and device execution states
- **Multi-platform support**: Windows (PowerShell), macOS (Shell), Linux (Shell via configuration policies)

### ⚙️ Script Execution
- **Execute scripts on devices**: Trigger script execution through Intune assignments
- **Assignment types**: Target specific groups, all devices, or all licensed users
- **Execution context**: Run as system or user account
- **PowerShell-specific options**: Enforce signature checks, run as 32-bit process
- **Linux script configuration**: Custom execution frequency and retry settings

---

## ☁️ Azure Resources (Alpha)

### 🏗️ Management Groups
- **List management group hierarchy**
- **View subscriptions within management groups**
- **Detailed management group information**

### 🔐 Subscriptions
- **Enumerate all accessible subscriptions**
- **View subscription details**
- **Resource provider information**

### 📦 Resource Groups
- **List resource groups per subscription**
- **View contained resources**
- **Resource group properties and tags**

---

## 🔍 Advanced Threat Hunting

### Search Capabilities
- **Cross-platform search**: Search across SharePoint, Teams chats, and Outlook (when permissions allow)
- **Chat message search**: Search Teams 1:1 and group chat messages for sensitive information
- **Keyword-based discovery**: Find sensitive data like passwords, secrets, keys, tokens, credentials
- **Pre-defined search tags**: Quick access to common sensitive terms
- **Result highlighting**: Matched keywords highlighted in search results
- **Download capabilities**: Direct download links for discovered files

---

## 🔔 Graph API Notifications

### 📡 Real-Time Monitoring
- **Change notification subscriptions**: Create webhook subscriptions to monitor Microsoft 365 resources in real-time
- **Subscription management**: Create, list, renew, and delete notification subscriptions
- **Webhook infrastructure**: Built-in webhook endpoints for receiving and processing notifications
- **Lifecycle notifications**: Handle subscription validation and lifecycle events

### 📨 Supported Resource Types
- **Teams Channel Messages**: Monitor all Teams channel messages with keyword filtering
- **Teams Chat Messages**: Track 1:1 and group chat conversations across the organization

### 🔍 Keyword Filtering
- **Teams message filtering**: Define keywords to track sensitive information in Teams messages
- **Real-time alerts**: Receive notifications when messages contain specified keywords
- **Custom keyword lists**: Configure multiple keywords for targeted monitoring
- **Pre-defined sensitive terms**: Quick access to common credential-related keywords

### 🔐 Subscription Features
- **Expiration management**: Set and renew subscription expiration times (up to 3 days)
- **Status monitoring**: Track subscription status (Active, Expiring Soon, Expired)
- **Client state validation**: Secure webhook validation with client state tokens
- **Message content retrieval**: Automatically fetch and store message content from notifications
- **Context extraction**: Extract team names, channel names, and chat participants from resource paths

---

## 🔧 Installation

### Prerequisites
- Python 3.8+

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/Saporo-SA/shadowscope.git
cd shadowscope
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the application**
```bash
python run.py
```

4. **Access the interface**
```
http://127.0.0.1:5000
```
---

## ⚠️ Legal Disclaimer

**ShadowScope is designed for authorized security assessments and penetration testing only.**

- ✅ Use only on systems you own or have explicit written permission to test
- ✅ Follow responsible disclosure practices
- ✅ Comply with all applicable laws and regulations
- ❌ Unauthorized access to computer systems is illegal
- ❌ The developers assume no liability for misuse

This tool is intended for:
- Red Team operations
- Authorized penetration testing
- Security research in controlled environments
- Educational purposes in legal contexts

---

## 🤝 Contributing

We welcome contributions from the security community!

### Areas for Improvement
- Additional Microsoft 365 modules (OneDrive, Planner, etc.)
- More attack techniques and tactics
- Enhanced Azure Resource Management features
- Automated exploitation modules
- Report generation capabilities

### How to Contribute
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📚 Resources

### Documentation
- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/api/overview)
- [Azure Resource Manager REST API](https://docs.microsoft.com/en-us/rest/api/resources/)
- [MITRE ATT&CK Framework](https://attack.mitre.org/)

---

## 🙏 Acknowledgments

- Microsoft for the Graph API and comprehensive documentation
- The offensive security community for research and techniques

---

## 👨‍💻 Author & Credits

### Developed by Elbert Santos (tuxtrack) at SAPORO SA

**ShadowScope** was originally created as a personal research project by Elbert Santos and is now officially developed and maintained as part of [**SAPORO**](https://saporo.io)'s offensive security toolkit.

**Lead Developer & Maintainer:**
- **Elbert Santos** (Security Researcher & Offensive Security Specialist at SAPORO)
  - **LinkedIn**: [https://www.linkedin.com/in/elbertsantos/](https://www.linkedin.com/in/elbertsantos/)
  - **GitHub**: [https://github.com/tuxtrack](https://github.com/tuxtrack)
  - **X (Twitter)**: [https://x.com/tuxtrack](https://x.com/tuxtrack)

**Organization:**
- [**SAPORO**](https://saporo.io) - A leading cybersecurity company specializing in offensive security operations and red team assessments
  - **Website**: [https://saporo.io](https://saporo.io)
  - **GitHub**: [https://github.com/Saporo-SA](https://github.com/Saporo-SA)

---

## 📄 License

**GNU General Public License v3.0**

Copyright (c) 2024 SAPORO

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see [https://www.gnu.org/licenses/](https://www.gnu.org/licenses/).

### Legal Notice

This tool is designed for **authorized security assessments and penetration testing only**.

- ✅ Use only on systems you own or have explicit written permission to test
- ✅ Follow responsible disclosure practices
- ✅ Comply with all applicable laws and regulations
- ❌ Unauthorized access to computer systems is illegal
- ❌ The developers assume no liability for misuse

For the full license text, see the [LICENSE](LICENSE) file.

---

<div align="center">
  <p>Made with ❤️ by <a href="https://saporo.io">SAPORO</a></p>
  <p><sub>Empowering Red Teams to Secure the Cloud</sub></p>
</div>
