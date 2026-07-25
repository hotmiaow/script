# Module 7: Forti SASE Course

## Page 241

6 SSLVPN与L2LVPN
FAC上已有的用户salesuser（已经绑定令牌）
日H FortiAuthenticator VM FAC-VMTM22004423
System
Edit Remote LDAP User
Authentication
Remote LDAP server：
QYTANGAD （dc2019.qytang.com）|
& User Account Policies
Username：
salesuser
營 User Management
Distinguished name：
Local Users X
CN=Salesuser.ou=Sales, Dc=gytang,DC=com
• Disabled
Remote Users
O One-Time Password （OTP） authentication
Remote User Sync Rules
Deliver token codes from：
FortiAuthenticator
FortiToken Cloud
Social Login Users
Deliver token code by：
FortiToken
Email
SMS （+86-13911053135）
Guest Users
User Groups
Hardware
Mobile
Realms
FortiTokens
MAC Devices
IAM
心 Portals
Remote Auth. Servers
& RADIUS Service
& TACACS+ Service
2 LDAP Service
& OAuth Service
E SAMLIdP
H FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
Dual （Email & SMS）|
Test Token
Token：
Activation delivery method：
FTKMOB3407896A2F
Email
+ Temporary token
• FIDO authentication
Allow RADIUS authentication
OSyncin HA Load Balancing mode
User Role
Role：
Administrator
Sponson
User
H User Information
H Password Recovery Options
H TACACS+
H Usage Information
H Certificate Bindings
H Devices
飞塔SASE
H RADIUS Attributes
元
怎
oK
教主VIP
Cancel
教主VIP
飞K塔NGFW与ZTNA
D③admin、
飞塔SASE
教主VP
飞塔SASE
乾颐堂
241

## Page 242

6
SSLVPN与L2LVPN
义
；塔SASE
EHE FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
• Edit User Group
Name：
Type：
User retrieval：
qytsalesgroup
2o User Account Policies
營 User Management
Local Users
Remote Users
Remote User Sync Rules
Social Login Users
Guest Users
User Groups
Usage Profile
Realms
FortiTokens
MAC Devices
IAM
臺 Portals
E Remote Auth. Servers
& RADIUS Service
& TACACS+Service
& LDAP Service
& OAuth Service
戲 SAMLIdP
E FACAgent
Fortinet SSOMethods
Monitor
Certifcate Management
Logging
LDAP flter：
• Usage Profle
TACACS+ authorization rule：
◎ Specify an LDAP Flter
O Set a list of imported remote LDAP users
QYTANGCA （dc2019.qytang.com） ~
（&lobiectClass.person）ImemberOf-CN-SakesGroup，.OU-Sales. DC-avtang.DC.comjl）
［ Please Select］v
［ Please Select］<
口 RADIUS Attributes
RADIUS Attribute：
vanaon
Fortinet
Attribute ID：
Fortinet-Group-Name
Value Type：
Value：
full-tunnel
Type：
String
+ Add RADIUS Attr
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FAC上修改组qytsalesgroup
D③ admin-
SCT GIOUDHIIC
添加Radius的属性
飞塔的组属性
淡
full-tunnel
qytsalesgroup
ASF
主MP飞塔S
242

## Page 243

6 SSLVPN与L2LVPN
塔SASE
FAC上创建组fac_split_tunnel_group
EHE FortiAuthenticator VM FAC-VMTM22004423
Edit User Group
Name：
Type：
• User retrieval：
义
System
Authentication
& User Account Policies
營 User Management，
2
Local Users|
Remote Users
Remote User SyncRules
Social Login Users
Guest Users
User Groups
Usage Profle
Realms
FortiTokens
MAC Devices
IAM
臺 Portals
凱 Remote Auth. Servers
& RADIUS Service
& TACACS+ Service
& LDAP Service
& OAuth Service
戲 SAMLIdP
E8 FACAgent
Fortinet SSO Methods
Monitor
Certibcate Management
Logging
fac_split_tunnel.group
Remote LDAP：
LDAP flter：
O Usage Profle
TACACS+ authorization rule：
◎ Specify an LDAP hlter
◎ Set a list of imported remote LDAP users
QYTANGCA （dc2019.aytang.com）v
（&lobjectClass-personM（memberOf-CN-qyt-split.OU-QytSplit,DC-qytang.DC-com））
［Please Select］v
［ Please Select］v
Test Fiter
口 RADIUS Attributes
「RADIUS Attribute：
Vendor：
Attribute ID：
Value Type：
Value：
Fortinet
Fortinet-Group-Name
Static
Dynamic
split-tunnel
添加Radius的属性
飞塔的组属性
Type：
String
+ Add RADIUS，
full-tunnel
qytsalesgroup
split-tunnel
fac_split_ tunnel_group_Sk
教主VIP
飞塔NGFW与ZTNA
乾颐堂
D ？ admin
飞塔SASE
243

## Page 244

6 SSLVPN 与L2LVPN
；塔SASE
FAC上创建组fac_web_access_group
日 FortiAuthenticator VM FAC-VMTM22004423
System
Create New User Group
Authentication
Name：
2 User Account Policies
Type：
營 User Management 2
User retrieva！：.
Local Users
Remote Users
Remote User Sync Rules
Social Login Users|
Guest Users
Remote LDAP：
LDAP flter：
O Usage Profle
TACACS+ authorization rule：
［ser Groups
Usage Profile
Realms
FortiTokens
MAC Devices
IAM
臺 Portals
口 RADIUS Attributes
RADIUS Attribute：
Vendor：
Attribute ID：
Value Type：
Value：
Fortinet
Fortinet-Group-Name
Static
web-3cces5
T Remote Auth. Servers
• RADIUS Service
Type：
String
& TACACS+ Service
+ Add RADIUS Ancibute
& LDAP Service
& OAuth Service
B SAMLIdP
E8 FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
fac_web_access_group
Local
Remate LDAP
mote RADIUS
Remote SAML
1o Specify an LDAP filter］
• Set a list of imported remote LDAP users
QYTANGCA （dc2019.qytang.com） v
（&（objectClass-person）I（memberOf-CN-qyt-web,OU-QytWeb,DC-qytang.DC-com》）
［ Please Select］~
【Please Select】v
Test Filser
Dynamic
添加Radius的属性
飞塔的组属性
教主VIP
飞塔NGFW与ZTNA
乾颐堂
full-tunnel
split-tunnel
web-access
qytsalesgroup
fac_split tunnel_group.
fac_web_access group
244

## Page 245

6
SSLVPN与L2LVPN
FSASE
日H FortiAuthenticator VM FAC-VMTM22004423
System
>+ Create New Delete Edit
Authentication
& User Account Policies
密 User Management ①
口
口
口
fac_split_tunnel_group
fac_web_access_group
Remote Users
qytsalesgroup
Remote User Sync Rules
SocialLogin Users
Guest Users
User Groups/ 2
Usage Profile
Realms
FortiTokens
MAC Devices
IAM.
臺 Portals
凱 Remote Auth. Servers
RADILIS Sorica
& TACACS+ Service
& LDAP Service
& OAuth Service
P SAMLIdP
E FAC Agent
Fortinet SSO Methods
Monitor
Certihcate Management
Logging
塔SASE
教主VIP
飞K塔NGFW与ZTNA
Type
Remote LDAP
Romate LDAP
Remote LDAP
Remote Server
LDAP: QYTANGCA （dc2019.qytang.com）
LDAP: QYTANGCA （dc2019.qytang.com）
LDAP: QYTANGCA （dc2019.qytang.com）
Members
NumberOfUsers
教主VIP
教主VIP飞塔SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE|
乾颐堂
FAC上最终的Group
SSASE
D③ admin-
245

## Page 246

6
SSLVPN与L2LVPN
$SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FAC配置Radius策略
日H FortiAuthenticator VM FAC-VMTM22004423
System
+ Create New|| Delete Edit
⑦ Overview
Authentication|
2/ 30000 Authentication policies
& User Account Policies
營 User Management
+ Portals
W Remote Auth. Servers
& RADIUS Service 2
Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
& TACACS+ Service
R LDAP Service
& OAuth Service
點 SAMLIdP
FSASE
EH8 FAC Agent
Fortinet SSO Methods.
Monitor
Certificate Management
Logging
D③ admin、
老
教主VIP
教主VIP飞塔SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE
246

## Page 247

6
SSLVPN与L2LVPN
滚
FSASE
EH FortiAuthenticator VM FAC-VMTM22004423
System
& User Account Policies
心 User Management
分 Portals
言 Remote Auth. Servers
RADIUS Service
Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
& TACACS+ Service
& LDAP Service
& OAuth Service
點 SAMLIdP
H FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
RADIUS clients
Policy name：
Description：
RADIUS clients：
SSASE
教主VIP
飞K塔NGFW与ZTNA
FAC配置Radius策略
Authentication type
Identity source
RADIUS attributecrit
Radius-Policy
Available RADIUS Clients ©
Q Filter
Chosen RADIUS Clients ②
FGT （fgt1.qytang.com）
搭SASE
ithentication factors|
RADIUS response
D ② oomind
飞塔SASE
教主VIP
Remove all
Choose all|
Discard and exit
Next
飞塔SASE
教主VIP
教主VIP飞塔SASE
乾颐堂
247

## Page 248

6 SSLVPN与L2LVPN
塔SASE
FAC配置Radius策略
EHP FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
& User Account Policies
登 User Management
A Portals
W Remote Auth. Servers
RADIUS Service
Clients
Policies
Certificates
Services
RADIUS clients
> RADIUS attribute criteria
Authentication type
Identity source
• RADIUS authentication request must contain specifc attributes
Previous
Discar
Next.
Accounting Proxy
& TACACS+ Service
R LDAP Service
& OAuth Service
SAMLIdP
HB FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
搭SASE
教主VIP
飞塔NGFW与ZTNA
塔SASE
hentication factors
KADIUS response
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE
乾颐堂
D ③ admin-
飞塔SASE
教主VIP
248

## Page 249

6
SSLVPN与L2LVPN
塔SASE
日H FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
& User Account Policies
User Management
少 Portals
三 Remote Auth. Servers
RADIUS Service
Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
A TACACS+ Service
4 LDAP Service
& OAuth Service
E SAMLIdP
HB FAC Agent
Fortinet SSO Methods
Monitor
Certihicate Management
Logging
RADIUS clients
Authentication type：
SSASE
教主VIP
飞K塔NGFW与ZTNA
FAC配置Radius策略
Identity source
SASE
thentication factors
RADIUS response
》 RADIUS attribute criteria
Authentication type
◎ Password/OTP authentication
9 Accept EAP
O MAC authentication bypass （MAB）
• Client Certifcates （EAP-TLS）
Previous
Discard and exit
Next
D② admi-
飞塔SASE
教主VIP
教主VIP 飞塔SASE
教主VIP飞塔SASE
教主VIP
飞塔SASE
乾颐堂
249

## Page 250

6
SSLVPN与L2LVPN
$SASE
FAC配置Radius策略
日H FortiAuthenticator VM FAC-VMTM22004423
System
& User Account Policies
User Management
臺 Portals
呈 Remote Auth, Servers
& RADIUS Service
Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
& TACACS+Service
& LDAP Service
& OAuth Service
F SAMLIdP
H8 FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
教主VIP
RADIUS clients
RADIUS attribute criteria
Authentication type
Identity source
• Eduroam
Username format：
◎ username@realm
◎ realm/usemame
•Use default realm when user-provided realm is different from all configured realms
Realms：
Default
Allow Local Users To Override
Use Windows AD Domain
Realm
◎
qytangca | QYTANGCA（dc2019.qytang.com）v
Discord and exit
Next
塔SASE
飞塔SASE
教主VIP
教主VIP
httos//ac.avtana.com/admin/fac auth/authoolio/add/#idcientrealm sat-0-aroups.popupcontent -
教主VIP
飞K塔NGFW与ZTNA
苓SASE
RADIUS response
Delete
乾颐堂
D③ admin-
飞塔SASE
Groups©
0 Filter: fac_split_tunnel_group.
fac_web_access_8roup, ayts.
Filter local users: /
选择三个FAC的Group：
• fac split tunnel group
• fac web access_group
qytsalesgroup
飞塔SASE
250

## Page 251

6 SSLVPN与L2LVPN
FSASE
EH FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
& User Account Policies
彰 User Management
Portals
言 Remote Auth.Servers
RADIUS Service
Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
& TACACS+ Service
2 LDAPService
& OAuth Service
點 SAMLIdP
E8 FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
RADIUS clients
> RADIUS attribute criteria
◎ Mandatory password and OTP
© All confgured password and OTP factors
Password-only
• OTP-only
RADIUS attribute for user IP：
Framed-IP-Address
• Adaptive Authentication
+ Device authorization
+ Advanced options
［Default］
SASE
教主VIP
飞塔NGFW与ZTNA
FAC配置Radius策略
SSASE
Authentication type
Identity source
Authentication factors
RADIUS response
D③ admin-
飞塔SASE
Next
教主VIP
教主VIP 飞塔SASE
教主VIP 飞塔SASE
飞塔SASE
教主VIP
乾颐堂
251

## Page 252

6 SSLVPN与L2LVPN
$SASE
中H日 FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
& User Account Policies
User Management
+ Portals
量 Remote Auth. Servers
& RADIUS Service
\Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
& TACACS+ Service
2 LDAPService
k OAuth Service
B SAMLIdP
F8 FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
RADIUS clients
Authentication
User Authentication Result
Successful
Failed
ISASE
FAC配置Radius策略
> RADIUS attribute criteria
Authentication type
Identity source
RADIUS Authentication Response
Return User Attribute：
Access-Accept
Access-Reject
Return User Group Attributes
RADIUS response
Return Additional Attributes
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
admin、
J.
Previous
Discard and exit
Save and exit
返回组的属性
教主VIP 飞塔SASE
飞塔SASE
教主VIP
飞塔SASE
教主VIP
252

## Page 253

6 SSLVPN与L2LVPN
SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FAC配置Radius策略
E FortiAuthenticator VM FAC-VMTM22004423
System
>+ Create New Delete / Edit ① Overview
Auithenhicahion
◎ The Policy "Radius-Policy" was saved successfully.
& User Account Policies
RADIUS Clients
營 User Management
小 Portals
Radius-Policy
FGT
m Remote Auth. Servers
atmonhicahon nolicios
RADIUS Service
Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
& TACACS+ Service
9 LDAP Service
& OAuth Service
酯 SAMLIdP
HH FAC Agent
'SASE
Fortinet SSO Methods
Certifcate Management
Logging
Authentication Type
RADIUS Attribute Criteria
Password/OTP authentication
•？
admin、
Priority
Authentication Type
Password/OTP
教主VIP
教主VIP飞塔SASE
教主VIP 飞塔SASE
教主VIP飞塔SASE
253

## Page 254

6 SSLVPN与L2LVPN
s塔SASE
向fst1
（ Dashboard
$ Network
B Policy & Objects
A Security Profiles
口 VPN
S User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers2
Single Sign-On
Authentication Settings
FortiTokens
今 WiFi Controller
¢ System
0 Security Fabric
區 Log & Report
=Q
New RADIUS Server
Name
Authentication method
NASIP
Include in every user group O
）~
Primary Server
IP/Name
Secret
Connection status
£6
Test Connectivity
Test User Credentials
SecondaryServer
IP/Name
Secret
Test Connectivity
Test User Credentials
教主VIP
飞塔NGFW与ZTNA
飞塔SASE
oK
教主VIP
Sg塔SASE
飞塔SASE
教主VP
乾颐堂
FGT1上配置Radius
SSASE
QYT-Radius-FAC
DefaultSpecify
fac.qytang.com
Q Successful
PortiGate
啊 fgt1
Additional Information
④ API Preview
② Online Guides
e Relevant Documentation C
W Video Tutorials C
e Hot Questions at FortiAnswers
教主VIP
Can we use special characters in Radius passwords？
6 1 Ancwers
• O Votes
⑧ 345 Views
See More C
HA: Primary）-日、A、②admin、
飞塔SASE
254

## Page 255

6
SSLVPN与L2LVPN
塔SASE
教主VIP
飞K塔NGFW与ZTNA
教主VIP 飞塔SASE
乾颐堂
FGT1上配置Radius
向fgt1
$ Dashboard
4 Network
』 Policy & Objects
P Security Profles
旦 VPN
2 User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
FortiTokens
分 WiFi Controller
¢ System
. Security Fabric
區 Log & Report
=
Q
+Create New
QYT-Radius-FAC
•Edit
|「 Clone @ Delete
Name
Server IP/Name
fac.qytang.com
SASE
HA: Primary〉-②、白、Q admin、
Ref.一
教主VIP
飞塔SA
答SASE
教主VIP 飞塔SASE
教主VIP
飞塔SASE
https://fat1.qvtanq.com/user/saml w7.2.4
255

## Page 256

6 SSLVPN与L2LVPN
塔SASE
FGT1上创建Radius的组［SalesGroujp］
回fgt1
（ Dashboard
+ Network
』 Policy & Objects
凸 Security Profiles
口 VPN
S User & Authentication
User Definition
|User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
FortiTokens
今 WiFi Controller
0 System
W Security Fabric
區 Log & Report
=Q
New User Group
Name
Type
SalesGroup
Firewall
Fortinet Single Sign-On （FSSO）
RADIUS Single Sign-On （RSSO）
Guest
Members
+
Remote Groups
+Add
Edit
向 Delete
Remote Server 1
Group Name今
SSASE
No results
FortiGate
啊 fgt1
Additional Information
© API Preview
② Online Guides
日 Relevant Documentation C
• Video Tutorials C
教主VIP
P Hot Questions at FortiAnswer
D Join the Discussion C
教主VIP
飞K塔NGFW与ZTNA
FERTINET
v7.2.4
教主VIP
乾颐堂
HA: Primary〉-②、 、② admin•
飞塔SASE
飞塔SASE
OK
教主VIP
Sag塔SASE
飞塔SASE
256

## Page 257

6 SSLVPN与L2LVPN
飞塔SASE
FGT1上创建Radius的组［SalesGroujp］
回 fgt1.
=Q
2 Dashboard
+ Network
』 Policy & Objects
A Security Profiles
Q VPN
2 User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
New User Group
Add Group Match
Remote Server
SalesGroup
Groups
Firewall
Fortinet Single Sign-On （FSSO）
RADIUS Single Sign-On （RSSO）
Guest
2o QYT-Radius-FAC
Any Specily | 2
。
Members
Kemote urouDs
+Add | / Edit|
自 Delete
Remote Server
Group Name=
Authentication settings
No results
教主VIP
FortiTokens
今 WiFi Controller
意 System
• Security Fabric
區 Log& Report
塔SASE
教主VIP
飞K塔NGFW与ZTNA
FIRTINET
1724
OK
Cance
教主VIP
乾颐堂
HA: Primary >-②、4、②admin、
飞塔SASE
飞塔SASE
教主VIP
飞塔SASE
257

## Page 258

6 SSLVPN与L2LVPN
s塔SASE
FGT1上创建Radius的组［SalesGroup］
回 fgt1
$ Dashboard
+ Network
L Policy & Objects
A Security Profles
Q VPN.
2 User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication settings
FortiTokens
分 WiFi Controller
¢ System
• Security Fabric
區 Log & Report
众
=Q
New User Group
Name.
Type
SalesGroup
Firewall
Fortinet Single Sign-On （FSSO）
RADIUS Single Sign-On （RSSO）
Guest
Members
Remote Groups
+Add Edit
Delere
Remote Server
品 QYT-Radius-FAC
Group Name s
full tunnel
SSASE
FortiGate
啊 fgt1
Additional Information|
④ API Preview
② Online Guides|
E. Rolavant Dommentation a
W Video Tutorials C
© Hot Questions at FortiAnswers
◎ Join the Discussion C
教主VIP
飞塔NGFW与ZTNA
乾颐堂
HA: Primary》-②、4、② admin、
飞塔SASE
天
SalesGroup
full-tunnel
split-tunnel
web-access
aytsalesgroup
fac_split_tunnel_group
- fac web access group
FRTINET
V7.24
258

## Page 259

6
SSLVPN与L2LVPN
X
回 fgt1
$3 Dashboard
+ Network
L Policy & Objects
A Security Profiles
口 VPN
S User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
分 WiFi Controller
如 System
• Security Fabric
區 Log & Report
FGT1上创建Radius的组［SplitTunnelGroup］
Q
New User Group
Name
SplitTunnelGroup
Firewall
Fortinet Single Sign-On （FSSO）
RADIUS Single Sign-On （RSSO）
Guesf
ortiGate
I T8t1
Additional Information
② API Preview
Members
Remote Groups
② Online Guides
e Relevant Documentation C
• Video Tutorials C
+Add||
•Edit
曲 Delete
Remote Servers
2o QYT-Radius-FAC
Group Name =
split-tunnel
v Hot ouestions at FortiAnswers
Join the Discussion C
然SASE
SalesGroup
full-tunnel
qytsalesgroup
SplitTunnelGroup
split-tunne
fac_split_tunnel_group
web-access
- fac web access group
教主VIP
飞K塔NGFW与ZTNA
HA: Primary >-@•A、Q admin-
飞塔SASE
FRTINET
乾颐堂
259

## Page 260

6
SSLVPN与L2LVPN
教主VIP
飞K塔NGFW与ZTNA
MA Binary 2-9•A•9adi-
Gfgt1
® Dashboard
+ Network
』 Policy & Objects
A Security Profiles
口 VPN
& User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
FortiTokens
今 WiFi Controller
¢ System
• Security Fabric
區 Log & Report
FGT1上创建Radius的组［WebAccessGroup］
= Q
New User Group
WebAccessGroup
）Firewall
Fortinet Single Sign-On （FSSO）
RADIUS Single Sign-On （RSSO）
Guest
Members
Remote Groups
+Add
• Edit
會 Delete
Remote Servers
8 QYT-Radius-FAC
Group Name =
web-access|
啊fgt1
fiananarmam
④ API Preview
② Online Guides
• Relevant Documentation C
e Video Tutorials C
Hot Questions at FortiAnswers
◎ Join the Discussion C
飞塔SASE
答SASE
SalesGroup
SplitTunnelGroup
WebAccessGroup
full-tunnel
split-tunne
web-access
qytsalesgroup
fac_split tunnel_group
- fac_ web_access_group
FRTINET
乾颐堂
260

## Page 261

6
SSLVPN与L2LVPN
飞塔SASE|
Gtsti
$2 Dashboard
+ Network
』 Policy & Objects
A Security Profiles
口 VPN
3 User & Authentication 1
User Definition
User Groups 2
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
FortiTokens
今 WiFi Controller
¢ System
• Security Fabric
區 Log& Report
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FGT1上创建Radius的组
=Q
+Create New
eFait|i im Cone
Group Name =
Guest-group
SSO_Guest_Users
SalesGroup
SalesGroup-SAML
公 SplitTunnelGroup
WebAccessGroup
Delete Search
出 Firewall
ForuneLsingle ign-0n（aa0）
出 Firewall
料 Firewall
Firewall
Group Type =
Members =
品 QYT-Radius-FAC
® FAC-SSO
3o QYT-Radius-FAC
8o QYT-Radius-FAC
HA: Primary >-②、4、② admin-
Ref. =
飞塔SASE
SalesGroup
SplitTunnelGroup
WebAccessGroup
full-tunnel
split-tunnel
qytsalesgroup
fac split_tunnel_group
web-access
fac_ web_access_group
FRTINET
261

## Page 262

6 SSLVPN与L2LVPN
飞塔SASE|
回 fgt1
88 Dashboard
+ Network
L Policy & Objects
A Security Profiles
旦 VPN 1
Overlay Controller VPN
IPsec Tunnels
IPsecWizard
IPsec Tunnel Template
2 SSL-VPN Portals
SSL-VPN Settings
SSLVPN Clients
VPN Location Map
2 User & Authentication
今 WiFi Controller
0 System
. Security Fabric
區 Log& Report
=Q
3
+ Create New
full-access
tunnel-access
web-access
套SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FGT1上创建SSE-VPN Portals
^Edit
|画 Delete
Search
Q
Name令
Tunnel Modes
HA:Primary
>- ③、4、②admin、
Web Modes
⑦ Enabled
◎ Enabled
* Disabled
⑦ Enabled
x Disabled
⑦ Enabled
教主VIP
类似于Group Policy
教主VIP 飞塔SASE
飞塔SASE
教主VIP
FERTINET
教主VIP飞塔SASE
262

## Page 263

6
SSLVPN与L2LVPN
Gfgt1
2 Dashboard
+ Network
L Policy & Obiects
A Security Profles
口 VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
\ SSL:VPN Portals 2
SSLVPN Settings
SSLVPN Clients
VPN Location Map
S User & Authentication
今 WiFi Controller
章 System
• Security Fabric
匹 Log & Report
教主VIP
飞K塔NGFW与ZTNA
FGT1上创建SSL-VPN Portals ［qytang-full-tunnel］
三Q
HA: Primary 〉-②•4、Q admin、
New SSL-VPN Portal
白
FRTINET
Name
qytang-full-tunnel
Limit Users to One SSL-VPN Connection at a Time
Select Entries
Qbearch
口 ADDRESS （2）
口 site1-dmz-nginx
E SSLVPN_TUNNEL_ADDR1
+ Create
啊 fgt1
Additional Infor mation
0 Tunnel Mode
Split tunneling
④ API Preview
Disabled
All client traffic will be directed over the SSL-VPN tunnel，
Enabled Based on Policy Destination
Onlyclienftrafhcinwhichthedectination matchesfhedestination oftheconh：
② Online Guides
E Relevant Documentation C
• Video Tutorials C
• Enabled for Trusted Destinations
Only client traffic which does not match explicitly trusted destinations will be di
Source IP Pools
© Hot Questions at FortiAnswers
送、
Confguring FortiGate SSL VPN with Azure Active Directory （Azure AD）
0 2 Answers
• O Votes
• 2942 Vieys
What certificate should l use for SSL Deep Inspection？
• 2 Votes
• 1,662 Views
Tunnel Mode Client Options
Allowclient to save password
Allowclient to connectautomatically O
Allowclient to keep connections alive O
DNS SplitTunneling
See More C
• Host Check
• Restrict to Specific OS Versions
0 Web Mode
SSL-VPN Portal
Neutrino
塔SASE
飞塔SASE
Portal Message
Theme
Show Session Information
Show Connection Launcher C
Show Login History
User Bookmarks
Rewrite Content IP/UI/
RDP/VNC clipboard
Close
OK
Cancel
飞塔SASE
教主VIP
①
乾颐堂
263

## Page 264

6 SSLVPN 与L2LVPN
FGT1上创建SSL-VPN Portals ［qytang-full-tunnel］
教主VIP
飞K塔NGFW与ZTNA
HA: Primary〉-⑦•4、②admin•
旬 fgtl
Dashboard
+ Network
』 Policy &Objects
A Security Profiles
口 VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSL-VPN Settings
SUFVEN Clenis
VPN Location Map
& User & Authentication
今 WiFi Controller
¢ System
© Security Fabric
區 Log & Report
=Q
New SSL-VPN Portal
Name
qytang-full-tunnel
LimitUsers to One SSL-VPN Connection at a Time
0 Tunnel Mode
Splittunneling
Select Entries
• Search
CREATE NEW
+ Address|
+ Address Group
• Enabled Based on Policy Destination
Only client trafficin which the destination matches the destination of the confg
• Enabled for Trusted Destinations
Only client traffic which does not match explicitly trusted destinations will be di
Source IP Dools
Tunnel Mode Client Options
Allow client to save password
Allowclient to connect automatically O
Allow client to keep connections alive O
DNSSplit Tunneling
• Host Check
• Restrict to Specific OS Versions
0 Web Mode
Portal Message
Theme
Chaw Saccinn Information
0
Show Connection Launcher C
Show Login History
0
User Bookmarks
Rewrite Content IP/UI/
RDP/NCclipboard
SSL-VPN Portal
Neutrino
塔SASE
吧 fgt1
Additional Information
⑧ APIPreview
⑦ Online Guides
e Relevant Documentation C
• Video Tutorials C
• Hot Questions at FortiAnswers|
Configuring FortiGate SSL VPN with Azure Active Directory （Azure AD）
0 2 Answers
•〇Wotae
• 2942 Miew
教主VIP
What certificate should l use for SSL Deep Inspection？
• 2 Answers
See More C
飞塔SASE
FRTINET
教主VIP
OK
Cancel
教主VIP
飞塔SASE
乾颐堂
264

## Page 265

6
SSLVPN与L2LVPN
向 fgt1.
1 Dashboard
+ Network
』 Policy & Objects
台 Security Profles
Q VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSLVPN Settings
SSLVPN Clients
VPN Location Map
2 User & Authentication
分 WiFi Controller
System
• Security Fabric
區 Log & Report.
教主VIP
飞塔NGFW与ZTNA
FGT1上创建SSL-VPN Portals ［qytang-full-tunnel］
三Q
New SSL-VPN Portal
HA:Ptmary 2-9•A、Oamin-
New Address
qytang-full-tunnel
Users to One SSLVPNConnection at a Tge
0 Tunnel Mode
Type
IP Range
Interface
Qytang-SSLVPN-Pool
Change
IPRange
172.16.100.1-172.16.100.100
• any
解决Pool路由问题
Split tunneling
◎ Disabled
acienttcaincwill becirec en overtne、-nne
Write acomment..
众
◎ Enabled Based on Policy Destination
Only client traffic in which the destination matches the destinati
directed over the SSL-VPN tunnel.
Enabled for Trusted Destinations
Only client traffic which does not match explicitly trusted destina
oK
Cancel
Routing Address Override
Source IP Pools
Tunnel Mode Cfie
Mlow.dlie
1to connect automatically
tent to keep connections alive C
DyS Split Tunneling
◎ Host Check
• Restrict to Specific OS Versions
© Web Mode
Portal Message
Theme
SSL-VPN Portal
Neutrino
nsacaiannrnrmarnn
Show Connection Launcher C
Show Login History
User Bookmarks
飞塔SASE
飞塔SASE
教主VIP
FIRTINET
教主VIP
飞塔SASE
乾颐堂
265

## Page 266

6 SSLVPN与L2LVPN
旬 fgtl
$ Dashboard
+ Network
B Policy & Objects
A Security Profiles
Q VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSL-VPN Settings
SSL-VPN Clients
VPN Location Map
2 User & Authentication
今 WiFi Controller
章 System
• Security Fabric
區 Log & Report
教主VIP
飞塔NGFW与ZTNA
FGT1上创建SSL-VPN Portals ［qytang-full-tunnel］
=Q
HA: Primary >-②•4•②admin-
New SSL-VPN Portal
J Name,qytang full-tunnel
啊 fgt1
Limit Users to One SSL-VPN Connection at a TimeS
Additional Information|
2
spit uunneling
Disabled
All client traffic will be directed over the SSL-VPN tunnel.
全部走vpn
• Enabled based on Pollcy Destination
Only client traffic in which the destination matches the destination of the configured firewall policies will be directed over
the SSL-VPN tunnel.
O Enabled for Trusted Destinations
Only client traffic which does not match explicitly trusted destinations will be directed over the SSL-VPN tunnel.
某些走vpn
Source IP Pools
扫 Qytang-SSLVPN-Pool
大。
某些不走vpnKetive Dratory hareAD
What certificate should I use for SSL Deep Inspection？
0 2 Angwprd
• 2 Votes
See More C
Tunnel Mode Client Options
Allowclient to.save paesword
Allow Cient to comnectautomatically O
Allowdlientto keep connections alive O
DNS Split Tunneling
Q Host Check
• Restrict to Specific OS Versions
0 Web Mode
塔SASE
Portal Message
Theme
Show Session Information
Show Connection Launcher O
Show Login History
User Bookmarks
Rewrite Content IP/UI/
RDP/VNCclipboard
SSL-VPN Portal
Neutrino
教主VIP
FRRTINET
OK
Cancel
飞塔SASE
教主VIP
①
乾颐堂
266

## Page 267

6
SSLVPN与L2LVPN
回 fgt1.
2 Dashboard
+ Network
』 Policy & Objects
A Security Profles
口 VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Tunnel Template
SSL-VPN Portals 2
SSL-VPN Settings
SSL-VPN Clients
VPN Location Map
S User & Authentication
分 WiFi Controller
¢ System
• Security Fabric
區 Log & Report
FGT1上创建SSL-VPN Portais ［qytang:Split-tunnel］
教主VIP
飞K塔NGFW与ZTNA
HA: Primary >-②•4•②admin-
①
乾颐堂
=Q
New SSL-VPN Portal
3Name qytang-split-tunnel
Limit Users to One SSL-VPN Connection at a Time S
0 Tunnel Mode
Split tunneling
• Disabled
All client traffic will be directed over the SSL-VPN tunnel.
Enabled Based on Policy Destination
Only client trafhicin which the destination matches the destination of the configured firewall policies wil be
directed over the SSL-VPN tunnel.
O Enabled for Trusted Destinations
Only client traffic which does not match explicitly trusted destinations will be directed over the SSL-VPN
tunnel.
Routing Address Override
Source IP Pools
E Qytang-SSLVPN-Pool
Tunnel Mode Client Options
Allow client to save password
Allowclient to connect automatically
Allow client to keep connections alive O
DNS Split Tunneling
Split DNS
+Create New
色 Delete
Domains
qytang.com
Primary DNS Servers
192.168.1.200
Secondary DNS Server：
0.0.0.0
特定域名，送到特
点的DNS去解析
啊 fgt！
Additional Information|
全部走vpn
某些走vpn
某些不走vpn
What certificate should luse for SSL Deep Inspection？
0 2 Answers
• 2 Votes
• 1,662 Views
See More C
云
Pure Active Directory （Azure AD）
飞塔SASE
• Host Check
FRTINET
OK
Cancel
教主VIP
267

## Page 268

6 SSLVPN与L2LVPN
FGTI上创建SSL-VPN Portals ［qytang:web-access］
教主VIP
飞K塔NGFW与ZTNA
HA: Primary 〉-②、4、② admin、
S7
Gfgtl
28 Dashboard
+ Network
』 Policy & Objects
A Security Profiles
旦 VPN
1
Overlay Controller VPN|
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals 2
SSL-VPN Settings
SSL-VPN Clients
VPN Location Map
2 User & Authentication
今 WiFi Controller
¢ System
粉 Security Fabric
L Log & Report
食
=Q
New SSLVPN Portal
3 Name
qytang-web-access
Limit Users to One SSL-VPN Connection at a Time C
• Tunnel Mode
取消隧道
• Restrict to Specific OS Versions
0 Web Mode
Portal Message
Theme
Show Session Information
0
Show Connection Launcher ©
Show Login History
0
User Bookmarks
0
Rewrite Content IP/UI/
RDP/NCclipboard
Predefned Bookmarks
•+Create New
• Edit
Qytang SSL-VPN Portal
Neutrino
色 Delete
Search
Name=
Type =
Location=
site1.qytang.co.. HTTP/HTTPS
https://site1.qyta..
囧 fgt1
Additional Information
⑧ API Preview
② Online Guides
• Relevant Documentation C
B Video Tutorials C
• Hot Ouettons atFortAnsweX太，
X
Confguring FortiGate SSL VPN with Azure Active Directory （Azure AD）
• 2 Answers|
• O Votes
• 2,942 Views
What certificate should I use for SSL Deep Inspection？
• 2 Votes
• 1,662 Views
See More C
<
Description
Qytang Site1 Web Site
为sitel.qytang.com做书签
0 FortiClient Download
Download Method
Customize Download Location O
Direct SSL-VPN Proxy
飞塔SASE
FRTINET
OK
教主VIP
①
乾颐堂
268

## Page 269

6
SSLVPN与L2LVPN
向 fgt1
2 Dashboard
+ Network
』 Policy & Objects
A Security Profiles
口 VPN
Overlay Controller VPN
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSL-VPN Settings
SSL-VPN Clients
VPN Location Map
2 User & Authentication
今 WiFi Controller
System
0 Security Fabric
區 Log & Report
教主VIP
飞塔NGFW与ZTNA
FGTI上创建SSL-VPN Portals ［qytang:web-access］
众
New SSL-VPN Portal
Cvdnk weD dcces
ImitUsers to One SSL-VPN Connection at a Tiine
⑦ Tunnel Mode
◎ Restrict to Specific OS Versions
© Web Mode
Fortal Message
Theme
Show Session Information
Show Connection Launcher C
Show Login History
User Bookmarks
Rewrite ContentF
RDPINCC
ned Bookmarks
Qytang SSL-VPN Portal
Neutrino
Sreate New
Name=
Type=
Type
URL
Description
Single Sign-On
site1.qytang.com
HTTP/HTTPS
https://site1.qytang.com
Qytang Site1 Web Site
Disable SSL-VPN Login Alternative
OK
HA: Primary >-②•4、② admin-
Cancel
教主VIP
乾颐堂
自 Delete|| Search
Location =
Q
Description =
飞塔SASE，
◎
飞塔SASE
0 FortiClient Download
Customize Download Locatid
SL-VPN Proxy
教主VIP
FRTINET
V7.24
教主VIP 飞塔SASE
269

## Page 270

6
SSLVPN与L2LVPN
飞塔SASE|
G fgt1
m Dashboard
+ Network
』 Policy & Objects
A Security Profiles
口 VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSLVPN Settings
SSLVPN Clients
VPN Location Map
& User &Authentication
分 WiFi Controller
妳 System
• Security Fabric
區 Log & Report
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
+Create New
。Edit
full-access
qytang-full-tunnel
qytang-split-tunnel
qytang-web-access
FGT1上创建SSE-VPN Portals
色 Delete
Search
羽
Q
Tunnel Mode =
v Enabled
⑦ Enabled
⑦ Enabled
• Disabled
◎ Enabled
• Disabled
v tnabled
⑦ Enabled
⑦ Enabled
⑦ Enabled
Disabled
3 Enabled
HA: Primary >-②•4•② admin•
Weh Mode-
教主VIP
答SASE
教主VIP飞塔SASE
教主VIP 飞塔SASE
ERRTINET
V724.
教主VIP 飞塔SASE
270

## Page 271

6 SSLVPN与L2LVPN
；塔SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FGT1上修改SSL-VPN配置
向 fgt1
（2 Dashboard
+ Network
E Policy & Objects
• Security Profiles
旦 VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSL-VPN Settings
SSLVPN Clients
VPN Location Map
S User & Authentication
今 WiFi Controller
¢ System
0 Security Fabric
區 Log & Report
1Q
SSLVPN Settings
SSLVPN settigs are not fuiy confiBureg
Connection Settings 0
Enable SSL-VPN
Listen on Interface（s）
port1
Listen on Port
8443
①
Web mode access will be listening at
https://202.100.1.10:8443
Server Certificate
Redirect HTTP tO SSL-VPN O
Restrict Access
Idle Logout
Inactive For
Require Client Certificate O
r fgt1.qytang.com
Allow access from any host
Limit access to specific hosts
300
Seconds
Tunnel Mode Client Settings 0
Address Range
Automatically assign addresses Specify custom IP ranges
Tunnel users will receive IPs in the range of 10.212.134.200-
10.212.134.210
DNS Server
DNS Server #1
DNS Server #2
Specify WINS Servers O
Same as client system DNS
192.168.1.200
0.0.0.0
Specify
HA: Primary）-日、A、② admin、
Additional Information
⑧ API Preview
>_ Edit in CLI
口 SSL VPN Setup Guides
Web Mode
日 Web Mode for Remote User C
Tunnel Mode
e Full Tunnel for Remote User C
Split Tunnel for Remote User Q
Tunnel Mode Host Check C
e Multi-Realm C
Authentication
日 Certificate Authentication C
e LDAP-Integrated Certifcate Authentication C
FortiToken Mobile Push Authentication C
E RADIUS on FortiAuthenticator C
E RADIUS and FortiToken Mobile Push on FortiAuthenticator C
e Local User Password Policy C
日 RADIUS Password Renew on FortiAuthenticator C
LDAP User Password Renew C
VPN Setup on FortiClient
E Confguring an SSL VPN Connection C
bubleshooting
e Troubleshooting C
②
Online Guides
e Relevant Documentation C
B Video Tutorials C
Q Hot Questions at FortiAnswers
Configuring FortiGate SSL VPN with Azure Active Directorv （AzUre AD）
FRTINET
Apply
271

## Page 272

6
SSLVPN与L2LVPN
塔SASE
（回 fgt1
2 Dashboard
+ Network
』 Policy & Objects
A Security Profles
Q VPN
Overlay Controller VPN™
IPsec Tunnels
IPsec Tunnel Template
qytang-full-tunnel
qytang-split-tunnel
qytang-web-access
教主VIP
飞塔NGFW与ZTNA
乾颐堂
SSL-VPN Settings
Server Certificate
Redirect HTTP to SSLVPN O
Restrict Access
Idle Logout
Reauire Client Certificate O
e Client Setting
ge
#1
S Servers O
Settings
Browser：
Authentication/Portal Mapping 0
+ Create New
• Edit
Users/Groupst
品 SalesGroup
SplitTunnelGroup
出 WebAccessGroup
All Other Users/Groups
FGT1上修改SSL-VPN配置
• htps://202.100.1.10:8443
E fgt1.qytang.com
Allow access from any host Limit access to specific hosts
300
Seconds
SalesGroup
SplitTunnelGroup
WebAccessGroup
4
@ Delete
Send SSL-VPN Confguration
© APIPreview|
EditinCLI
口 SSL VPN Setup Guides
日 Web Mode for Remote User C
日 Full Tunnel for Remote User C
⑤ Split Tunnel for Remote User C
9 Tunnel Mode Host Check C
full-tunnel
4
split-tunnel
4
henticatia
ication C
Pushon Fd
ulAuuen
web-access
4
kion C
② Online Guides
日 Relevant Documentation C
W Video Tutorials C
Portal令
qytang-full-tunnel
qytang-split-tunnel
qytang-web-access
qytang-web-access
P Hot Questions at FortiAnswers
Confguring FortiGate SSL VPN with Azure Active Directory （Azure AD）
映射组到Portal（SSLVPN策略）
use for SSL Deep Inspection？
⑦1662 Vewe
◎ Security Rating Issues
Chaw Dicmiceed O
HA: Primary >-②• 、Q admin-
qytsalesgroup
fac_split_ tunnel group
fac web access_group
FIRTINET
Apply
272

## Page 273

6
SSLVPN与L2LVPN
Tgt1.
1 Dashboard
+ Network
L Policy & Objects.
Firewall Policy 2
IPv4 DoS Policy
ZTNA
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
IP Pools
Protocol Options
Traffic Shaping
A Security Profles
口 VPN
S User & Authentication
今 WiFi Controller
System
• Security Fabric
E Log & Report
众
FGT1上放行SSLVPN的流量 ［Full Tunnel］
Snal Information
⑧ API Preview
② Online Guides
Relevant Documentation C
W Video Tutorials C
LCansalidated DalicCanfaration CX
不能配置ZTNA的标签
因为ZTNA Client不在线，无法注册到EMS
SeeMore 已
必.
教主VIP
飞塔NGFW与ZTNA
①
乾颐堂
HA: Primary〉-②、4、②admin、
=Q
New Policy
Name ①
Incoming Interface
permit-ss/vpn-full-tunnel-traffic
2 SSL-VPN tunnelinterface （ssl.roo x
Outgoing Interface
1 port3
Source
口 all
甜 SalesGroup
IP/MAC Based Access Control 0
Destination
口 all
Schedule
Service
7 always
Q ALL
Action
< ACCEPT
② DENY
Inspection Mode
Flow-based Proxy-based
Firewall/Network Options
〈NAT
Protocol Options
i default
Security Profles
AntiVirus
Web Filter
DNS Filter
Application Control C
IPS
SSL Inspection
ho-inspection
Logging Options
Log Allowed Traffic
Security Events
All Sessions
飞塔SASE
飞塔SASE
FIRTINET
v724
教主VIP
OK
Cancel
教主VIP
飞塔SASE
273

## Page 274

6
SSLVPN与L2LVPN
FGT1上放行SSLVPN的流量［Split Tunnel］
教主VIP
飞K塔NGFW与ZTNA
HA: Primary >-⑧-4、②admin-
乾颐堂
向 fgt1.
2 Dashboard
+ Network
』 Policy &Objects
Firewall Policy 2
IPv4 DoS Policy
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffc Shaping
A Security Profiles
口 VPN
2 User & Authentication
分 WiFi Controller
妳 System
• Security Fabric
區 Log & Report
众
=Q
New Policy
Name ①
Incoming Interface
permit-sslvpn-split-tunnel-trafhc
2 SSLVPN tunnel interface （ssl.roo x
Outgoing Interface
port3（
source
日 all
幫 SplitTunnelGroup
IP/MAC Based Access Control
ZTNA IF
Firewall
ZTNAIP
I Sales_Tag
Destination
回 Site1-DMZ-Net
Schedule
Service
5 always
⑦ ALL
Action
V ACCEPT
⑦ DENY
Inspection Mode
Flow-based Proxy-based
Fiewal/ Network Options
10 NAT
Protocol Options
oor default
Security Profles
AntiVirus
Web Filter
DNS Filter
Application Control O
IPS
File Filter
SSLInspection
ho-inspection
LoggingOptions
Log Allowed Traffic
n Security Events
_All Sessions_
Jitional Information|
⑧ API Preview
② Online Guides
• Relevant Documentation C
@ Video Tutorials C
Hitetanlcy Confguration C
可以配置ZTNA的标签
控制访问的目标
Site1-DMZ-Net（192.168.1.0/24）
ortiAnswers
BUI？
教主VP
它是由目的网络决定隧道分割
Based On Policy Destination
塔SASE
入
FRTINET
OK
教主VIP
飞塔SAgE
274

## Page 275

6
SSLVPN与L2LVPN
Tgt1.
1 Dashboard
+ Network
L Policy & Objects
Firewall Policy 2
IPv4 DoS Policy
ZTNA
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
IP Pools
Protocol Options
Traffic Shaping
A Security Profles
口 VPN
S User & Authentication
今 WiFi Controller
System
• Security Fabric
E Log & Report
FGT1上放行SSLVPN的流量［Web. Actess］
众
Snal Information
⑧ API Preview
② Online Guides
Relevant Documentation C
W Video Tutorials C
• Consolidated Policy Confguration C
• Hot Questions at FortiAnswers
Is Web Cache on the GU！？
• O Votes
• 524V
See More C
教主VIP
教主VIP
飞塔NGFW与ZTNA
乾颐堂
HA: Primary〉-②、4、②admin、
=Q
New Policy
Name ①
Incoming Interface
permit-sslvpn-web-access-traffic
② SSL-VPN tunnelinterface （ssl.roo ：
Outgoing Interface
圖 port3
Source
口 all
亞 WebAccessGroup
IP/MAC Based Access Control
Destination
日 all
Schedule
Service
always
Q ALL
Action
< ACCEPT
② DENY
Inspection Mode
Flow-based Proxy-based
Firewall/Network Options
9KNAT
Protocol Options
or default
Security Profles
AntiVirus
Web Filter
DNS Filter
Application Control C
IPS
SSL Inspection
ho-inspection
Logging Options
Log Allowed Traffic
Security Events
All Sessions
飞塔SASE
飞塔SASE
FRTINET
v724
教主VIP
OK
Cancel
教主VP
飞塔SA&E
275

## Page 276

6
SSLVPN与L2LVPN
G fgt1
$ Dashboard
+ Network
• Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZTNA.
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
IP Pools
Protocol Options
Traffic Shaping
A Security Profiles
口 VPN
2 User & Authentication
分 WiFi Controller
章 System
• Security Fabric
區 Log & Report
FIRTINET
教主VIP
飞塔NGFW与ZTNA
FGT1上放行SSLVPN流量的防火墙最终策略
=
Q
HA: Primary
>-①• •
Q admin•
+Create New
•Edit
自 Delete
Q Policy lookup
c Export、
Interface Pair View
By Sequence
From
Source
Destinauion
Action
NAT
Security Profles
Log
Bytes
permit-internet-traffc
permit-inside-to-dmz-traffic
permit-dc-inbound-traffc
團 port2
圖 port3
圖 port2
團 port1
］ port1
日 all
口 all
n always
Q ALL
ACCEPT
©. Enabled
no-inspection
⑦ AIl
9.49MB
port3
回 all
port3
口 all
permit-fac-inbound-traffic
圖 port1
port3
1 all
回 all
會 DMZ-DC
會 DMZ-FAC
5o always
5 always
Q ALL
⑦ ALL
always
⑦ ALL
permit-ss/vpn-full-tunnel-traffic
② SSL-VPN tunnel interface （ssl.root）
圖 port3
口 all
D always
Q ALL
＜ACCEPT
＜ ACCEPT
< ACCEPT
<ACCEPT
∞ Disabled
t Disabled
• Disabled
出 SalesGroup
回 all
• Disabled
S AIl
S AIl
no-inspection
OAIl
no-inspection
O AIl
13.76 MB
1.81 MB
0B
permit-sslvpn-split-tunnel-traffic
1 SSL-VPN tunnel interface （ssl.root）
圖 port3
permit-sslvpn-web-access-traffic
A SSL-VPN tunnel interface （ssl.root）
圖 port3
莊 SplitTunnelGroup
口 all
甜 WebAccessGroup 1 all
E sitel-DMeNet
To always
QALL
< ACCEPT @ Disabled|
• no-inspection O All
0B
n always
Q ALL
< ACCEPT @ Disabled g no-inspection
S AIl
0B
Implicit Deny
塔SASE
口 any
口 any
口 all
口 all
5 always
Q ALL
② DENY
• Disabled
628.33 kB=
飞塔SASE
飞塔SASE
教主VIP
飞塔SASE
⑤ Security Rating Issues
教主VIP
T 8/8 |Updated: 09:04:32 2
草Z颐堂
276

## Page 277

6 SSLVPN与L2LVPN
飞塔SASE
H FortiClient Endpoint Management Server
@ Dashboard
Remote Access Profiles
E Edit
Lo Endpoints
Name
Default
这 Deployment & Installers
段 Endpoint Policy &.Components>
［ Endpoint Proiles］1
<
© Remole Access
2
⑦ ZTNA Destinations
价 Web Filter
• Vulnerability Scan
派 Malware Protection
& Sandbox
爱 Firewall
• System Settings
Zero Trust Tags
SSASE
Q FortiGuard Outbreak Detecti..
◎ Software Inventory
炒 Quarantine Management
喺 Administration
宮 User Management
# System Settings
教主VIP
飞塔NGFW与ZTNA
EMS 配置SSEVPN拨入点
G Clone
乾颐堂
囚Invitations ②~ 0 2 8 admin v
+ Add
c Import from File 2 Refresh
Updated
2023-05-19 17:45
教主VIP
在此页面中查找
飞塔SASE
改主VIP
高亮全部（A）
〕区分大小写（
匹配变音符号（）
口
全词匹配（M）
教主VIP 飞塔SASE
教主VIP
飞塔SASE
×
277

## Page 278

6 SSLVPN与L2LVPN
；塔SASE
E FortiClient Endpoint Management Server
m Dashboard
口 Endpoints
这 Deployment & Installers
B Endpoint Policy & Components >
日 Endpoint Pomies
0 Remote Access
◎ ZTNA Destinations
i Web Filter
② Vulnerability Scan
派 Malware Protection
感 Sandbox
桑 Firewall
• System Settings
島 Zero Trust Tags
G FortiGuard Outbreak Detecti..》
Software Inventory
炒 Quarantine Management
登 Administration
E User Management
妳 System Settings
Remote Access Profile
Name
Gheneral
Allow Personal VPN ⑧
Show VPN before Logon ®
Enable Secure Remote Access
O SSL VPN
1 IPsec VPN
VPN Tunnels
Name
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
EMS 配置SSEVPN拨入点
Default
VPN Tunnel
① Changes to this VPN tunnel will not be saved until the profile is saved.
Please select VPN type
写 囚 Invitations ⑨ A & admin v
• Expand AIl
- Collapse All
Basic
Advanced
教主V
Manual
Next
Cancel
XML
No ltems Found
Remate Satevay
+ Add Tunnel
飞塔SA：
Save
Discard Changes
Revert To Default
在此页面中查找
高亮全部（A）
口 区分大小写（C
口 匹配变音符号（）
全词匹配（）
教主VIP
278

## Page 279

6 SSLVPN与L2LVPN
：塔SASE
EMS 配置SSEVPN拨入点
EnP FortiClient Endpoint Management Server
>
d Endpoints
您 Deployment & Installers
Endpoint Policy & Components >
Endpoint Profiles
© Remote Access
◎ ZTNA Destinations
（ Web Filter
③ Vulnerability Scan
派 Malware Protection
K Sandbox
桑 Firewall
存 System Settings
Zero Trust Tags
FoniGuard Outoreak Detect.
⑨ Software Inventory
分 Quarantine Management
隊 Administration
因 User Management
森 System Settings
>
Creating VPN Tunnel
Remote A @ Changes to this VPN tunnel will not be saved until the profile is saved.
Basic Settings
Basic Settings
Name
Split Tunnel
Name
Application Based 呈
（-pneral
qyt-sslvpn
Advanced Settings
Cannot contain the characters \"&%<>
Allow Persona
On Connect Script
Type
Show VPN be
On Disconnect Script
SSL VPN
IPsec VPN
Enable Secure
Remote Gateway
fgt1.qytang.com
IO SSL VP
Port
1O IPsec V
8443
VPN Tunnels
Name
；塔SASE
Save
Require Certificate
• Prompt for Usemame
Cancel
在此页面中查找
高亮全部（A） 区分大小写（C
口 匹配变音符号（）
［ 全词匹配（M）
教主VIP
飞塔NGFW与ZTNA
乾颐堂
區 Invitations ②v A & admin v
Expand All
• Collapse AIl
isic
Advanced
教主V
Save
Discard Changes
Revert To Default
way
+ Add Tunnel
教主VIP
飞塔SA
279

## Page 280

6 SSLVPN与L2LVPN
塔SASE
H FortiClient Endpoint Management Server
@ Dashboard
>
Remote Access Profile
L Endpoints
这 Deployment & Installers
點 Endpoint Policy & Components >
Name
口 Endpoint Rrofles
<
General
O Remote Access
@ ZTNA Destinations
Allow Personal VPN ⑧
价 Web Filter
Show VPN before Logon ⑧
• Vulnerability Scan
Enable Secure Remote Access
派 Malware Protection
Auto Connect
K Sandbox
Firewall
SSLVPN
• System Settings
• IPsec VPN
Zero Trust Tags
Q FortiGuard Outbreak Detecti..
③ Software Inventory
炒 Quarantine Management
火 Administration
•配 User Management
VPN Tunnels
Name
qyt-sslvpn
# System Settings
教主VIP
飞K塔NGFW与ZTNA
EMS 配置SSEVPN拨入点
乾颐堂
Default|
因 Invitations ⑦~白
B admin v
• Expand AIl
• Collapse AIl
Basic
Advanced
教主VIP
Select a Tunnel
+ Add Tunnel
Type
SSL
Remote Gateway
fgt1.qytang.com
Save
Discard Changes Revert To Default
在此页面中查找
入V
高亮全部（A）
区分大小写（C 匹配变音符号（）口 全词匹配（M）
教主VIP
280

