# Module 6: Forti SASE Course

## Page 201

5
SAML
塔SASE
SAML IdP配置
日 FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
& User Account Policies
登 User Management
Portals
呈 Remote Auth. Servers
& RADIUS Service
& TACACS+ Service
2 LDAP Service
%o OAuth Service
園 SAMLIdP 2
General3
Replacement Messages
Service Providers
F FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
Edit SAML Identity Provider Settings
D Enable SAML Identity Provider portal
Device FQDN：
fac.qytang.com
fac.avtang.com
7
Server address：
IdP-initiated login URL：
Username input format：
https://fac.qytang.com/saml-idp/portal/
◎ username@realm
◎ realmlusername
• realm/username
O Use default realm when user-provided realm is different from all configured realms
Realms：
Default
Realm
◎
qytangad | QYTANGAD （dc2019.qytang.com）v
+ Add arealm
• Legacy login sequence
Login session timeout：
（10
Default IdP certificate：
480 S| minutes （5-1440）
faccert |CN=fac.qytang.com
• Automatically switch IdP certificate before its expiry time
Default signing algorithm：
http:/www.w3.org/2001/04/xmldsig-more#rsa-sha256v
• Get nested groups for user
• Use geolocation in FortiToken Mobile push notifications
教主VIP
飞K塔NGFW与ZTNA
塔SASE
飞塔SASE
教主VIP
乾颐堂
D
③
admin、
飞塔SASE
Allow Local Users To Override
Remote Users
OFilter：
qytsalesgroup
） Filter local users：
OK
201

## Page 202

5
SAML
＄SASE
SAML SP配置
SASE
EHE FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
&o User Account Policies
必 User Management
心 Portals
呈 Remote Auth. Servers
Le RADIUS Service
品 TACACS+ Service
品 LDAP Service
&e OAuth Service
F SAMLIdP 2
General
Replacement Messages
Service Providers
EHB FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
Create New SAML Service Provider
IdP address：
SPname：
IdP prefix：
fac.qytang.com
fgta
qytangsamlvx+
IdP entity id：
http://fac.qytang.com/saml-idp/qytangsaml/metadata/
IdP single sign-on URL：
https://fac.qytang.com/saml-idp/qytangsaml/login/
IdP single logout URL：
https://fac.qytang.com/saml-idp/qytangsaml/logout/
Server certifcate：
faccert |CN=fac.qytang.com
IdP signing algorithm：
Use default signing algorithm in SAML IdP General pagev
• Support IdP-initiated assertion response
• Participate in single logout
Authentication
Authentication method：
• Mandatory password and OTP
◎ All configured password and OTP factors
• Password-only
• OTP-only
◎ FIDO
Configure subnets
专门为这个SP提供的前缀
屯
它
我FAC是IDP，我在
添加我的SP
Adaptive Authentication
Sends username in this
username
parameter：
Application name for FTM push
notification：
• Use FIDO-only authentication if requested by the SPX
Assertion Attribute Configuration
SASE
Subject NamelD：
Username
Format：
urn:oasis:names:tc:SAML:2.0:nameid-format:unspecifed
• Include realm name in subject NamelD
H Assertion Attributes
飞塔SASE
H Debugging Options
教主VIP
飞K塔NGFW与ZTNA
Save
Panna
教主MP
乾颐堂
D② admin-
飞塔SASE
飞塔SASE
202

## Page 203

5 SAML
塔SASE
SAML SP配置
苓SASE
H FortiAuthenticator VM FAC-VMTM22004423
Edit SAML Service Provider
D
System
Authentication
& User Account Policies
哎 User Management
+ Portals
量 Remote Auth. Servers
& RADIUS Service
& TACACS+ Service
2 LDAP Service
&o OAuth Service
2 SAML IdP
General
Replacement Messages
Service Providers
HH8 FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
IDP导入SP的证书
（METADATA的内容）
IdP address：
SP name：
IdP prefx：
fac.qytang.com
fgt1
Please select v
Server certificate：
faccert |CN=fac.qytang.com
IdP signing algorithm：
Use default signing algorithm in SAML IdP General page v
• Support ldP-initiated assertion response
• Participate in single logout
SP Metadata
教主VIP
含. Import SP metadata
http://site1.qytang.com/remote/saml/metadata/
SP entity ID：
SPACS （login） URL：
SP SLS （logout） URL：
6SAML request must be signed by SP
Certificate type：
之前在FGT1上复制的内容
https://site1.qytang.com/remote/saml/login
https://site1.qytang.com/remote/saml/logout
Alternative ACS URLs
SP certificate
Certificate fingerprints：
258945366015aa45b0ff9be0d96fd8e057bf214e27182e093ff96ea24846f6c7 v|
3
加载之前在FGT1上下
载的sitel.qytang.com
的不带密钥的证书
Fingerprint algorithm：
SHA-256
Certifcate issuer：
JC=CN/ST=beijing/L=beijing/0=qytang/CN=qytca
Certificate subject：
/C=CN/ST=beijing/L=beijing/0=qytang/OU=qytangnetdevops/CN=site1.qytang.com
Validity period：
2023-05-14 07:15:00+00:00 to 2033-05-11 07:15:00+00:00
• Use ACS URL from SP authentication request （override ACS URLs confgured above）
Authentication
Authentication method：
• Mandatory password and OTP
◎ All configured password and OTP factors
• Password-only
• OTP-only
D EIDO
X
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
admin、
203

## Page 204

5 SAML
SASE
EN FortiAuthenticator VM FAC-VMTM22004423
System
Authentication method：
Authentication
2 User Account Policies
User Management
Portals
三 Remote Auth.Servers
Q RADIUS Service
E TACACS+ Service
E LDAP Service
◎ OAuth Service
SAML IdP
General
Replacement Messages
Service Providers
H FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
教主VIP
飞塔NGFW与ZTNA
D②admin-
飞塔SASE
教主VIP
USER ID/Group映射方案
（METADATA的内容）
之 IdP metadata
OK
点OK结束
乾颐堂
SAML SP配置
O Mandatory password and OTP
◎ All configured password and OTP factors
• Password-only
◎ OTP-only
◎ FIDO
• Adaptive Authentication
Configure subnets
Sends username in this
s2r02
parameter：
Application name for FTM push
notification：
• Use FIDO-only authentication if requested by the SP
Assertion Attribute Configuration
Subject NamelD：
Username
Format：
urn:oasis:names:tc:SAML:2.0:nameid-format:unspecified
• Include realm name in subject NamelD
口 Assertion Attributes
Assertion attribute：
SAML attribute：
User attribute：
qytang-user
sAMAccountName
Assertion attribute：
SAML attribute：
User attribute：
qytang-group
Group
+ Add Assertion Attribute
+ Debugging Options
204

## Page 205

5 SAML
s塔SASE
FGT1加载微软域根证书
G fgt1
Dashboard
+ Network
L Policy & Objects
P Security Profiles
口 VPN
S User & Authentication
含 WiFi Controller
8 System
Administrators
Admin Profles
Fabric Management
Settings
HA
SNMP
Replacement Messages
FortiGuard
Feature Visibility
Certificates
/ Security Fabric
區 Log & Report
=Q
+ Create/Import、
＜Edit
前 Delete
Import CA Certificate
Names
E0 FortineL_GULserver
呵 Fortinet_SSL
國 Fortinet_SSL_DSA1024
國 Fortinet SSL DSA2048
Subjec
Ta, L= sunn
C=03L
C=US,ST
Salifornia, L = Sunn
C.=.US, ST = California, L= Sunn
C=US,ST = California. L = Sunn
Type
Upload
Online SCEP
+ ms_root.cer
E Fortinet_SSL_ECDSA256
C= US, ST = California, L = Sunn
E Fortinet_SSL_ECDSA384|
C= US, ST = California, L = Sunn
國 Fortinet SSL_ECDSA521
C = US, ST = California, L = Sunn
國 Fortinet_SSL_ED448
C=US, ST = California, L= Sunn
写 Fortinet_SSL_ED25519
C=US, ST = California, L = Sunn
國 Fortinet_SSLRSA1024
C= US, ST = California, L = Sunn
國 Fortine
RSA2048
5Forti
SSL_ RSA4096
ortinet_ Wif
C=US, ST = California, L = Sunn
C= US, ST= California, L = Sunn
女
fgt1.qytang.com
國 site1.qytang.com
曰 Remote CA Certificate ⑤
C= US, ST = California, L = Sunn
C=CN,ST = beijing, L= beijing，
C=CN, ST = beijing, L= beijing，
扇 CA_Cert_1
國 Fortinet CA
C=CN,ST =beling.L-beiner
C-US,ST-CatfondetySimn
项 Fortinet_CA_Backup
國 Fortinet_Sub_CA
國 Fortinet_Wif_CA
日 Remote Certifcate.
國 REMOTE Cert 1
California.L=Sur
=US, O= DigiCert Inc,CN=0
C=CN, ST = beijing, L= beijing，
FERTINET
v7.2.4
◎ Security Rating Issues
OK
Cancel
教主VP
教主VIP飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
HA: Primary〉-日、白、Q admin、
飞塔SASE
教主VIP 飞塔SASE
乾颐堂
205

## Page 206

5 SAML
；塔SASE
FGT1加载微软域根证书
（fet1
2 Dashboard
+ Network
』 Policy & Objects
4 Security Profles
口 VPN
User & Authentication
今 WiFi Controller
¢ System
Administrators
Admin Profiles
Fabric Management
Settings
HA
SNMP
Replacement Messages
FortiGuard
Feature Visibility
Certificates<
• Security Fabric
山 Log& Report
FHRTINET
=Q
+ Create/lmport、
②Edit
向 Delete
Name今
扇 Fortinet SSL
面 Fortinet SSL_DSA1024
司 Fortinet_SSL_DSA2048
面 Fortinet_SSL_ECDSA256
國 Fortinet_SSL_ECDSA384
面 Fortinet_SSL_ECDSA521
ro Fortinet_SSL_ED448
写 Fortinet_SSL_ED25519
面 Fortinet_SSL_RSA1024
司 Fortinet_SSL_RSA2048
司 Fortinet SSL RSA4096
G Fortinet_Wif
⑤ fgt1.qytang.com
面 site1.qytang.com
日 Remote CA Certificate 6
國 CA_Cert_1
國 CA Cert 2
國 Fortinet_CA
项 Fortinet_CA_ Backup
项 Fortinet_Sub_CA
國 Fortinet_Wif_CAL
日 Remote Certifcate ①
國 REMOTE_Cert_1
0 Security Rating Issues
© View Details
& Download
Search
Subject一
Comments 一
C-US,ST -Californi.
This certificate is embed...
C=US, ST =Californi..
This certificate is embed...
C = US, ST = Californi...
This certificate is embed..
C=US, ST =Californi...
This certifcate is embed..
C=US, ST = Californi... This certificate is embed...
C=US, ST = Californi... This certificate is embed...
C= US, ST= Californi...
This certificate is embed..
C=US, ST =Californi..
This certificate is embed..
C=US, ST =Californi..
This certificate is embed..
C=US, ST =Californi...
This certificate is embed...
C=US, ST = Californi... This certificate is embed...
C= US, ST = Californi.. This certificate is embed.
C=CN, ST =beijing..
C=CN, ST =beijing..
C= CN, ST = beijing，...
DC=com, DC =qyta..
C=US, ST =Californi..
C=US,ST =Californi..
C=US,ST=Californi..
C=US, O= DigiCert..
Issuer台
Fortinet
Fortinet
Fortinet
Fortinet
Fortinet
Fortinet
Fortinet
Fortinet
Fortinet
Fortinet
Fortinet
DigiCert Inc
qytang
qytang
qytang
qytang-DC2019-CA
Fortinet
Fortinet
Fortinet
XJDieiCertinc
C=CN,ST = beijing....
qytang
Expires
2025/08/08 14:05:25
2025/08/08 14:05:27
2025/08/08 14:05:28
2025/08/08 14:05:28
2025/08/08 14:05:28
2025/08/08 14:05:28
2025/08/08 14:05:28
2025/08/08 14:05:28
2025/08/08 14:05:25
2025/08/08 14:05:25
2025/08/08 14:05:27
2023/09/06 07:59:59
2033/05/11 18:01:00
2033/05/11 15:15:00
2043/05/08 11:40:00
2028/04/25 16:13:58
2056/05/28 04:27:39
2038/01/20 06:34:39
2056/05/28 04:48:33
2030/09/24 07:59:59
2033/05/12 08:55:00
Q
Status
Valid
3 Valid
Q Valid
3 Valid
Valid
Valid
Valid
& Valid
◎ Valid
⑦ Valid
⑦ Valid
③ Valid
3 Valid
3 Valid
② Valid
Valid
Valid
3 Valid
③ Valid
◎ Valid
S Valid
教主VIP
飞塔NGFW与ZTNA
乾颐堂
HA: Primary）-⑧、A、② admin、
Sources
Ref. 今
Factory
Factory
Factory
Factory
Factory
Factory
Factory
Factory
Factory
Factory
Factory
Factory
User
User
User
User
Factory
Factory
Factory
Factory
User
1
100% 26
206

## Page 207

5
SAML
飞塔SASE
教主VIP
Gfgt1
龙
$ Dashboard
+ Network
島 Policy & Objects
A Security Profiles
旦 VPN
2 User & Authentication
User Definition
2 User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
FortiTokens
今 WiFi Controller
女 System
. Security Fabric
山 Log& Report
三Q
Edit User Group
Name
Type
Members
SalesGroup-SAML
Firewall
Remote Groups
+Ad
Edit
前 Delete
Remote Server s
No results
教主VIP
FE:RTINET
M7.2.4
教主VIP
飞K塔NGFW与ZTNA
创建User Group
SASE
HA.Primary2-②、A•Bsdmin-
FortiGate
照fgt1
Send SSL-VPN Confguration
Additional Information
飞塔SASE
Group Name s
© API Preview
% References
>- Edit in CLI
教主VIP
② Online Guides
日 Relevant Documentation C
W Video Tutorials C
Q Hot Questions at FortiAnswers
◎ Join the Discussion C
飞塔SASE
oK
Cancel
飞塔SASE
教主VIP
飞塔SASE
教主VIP
乾颐堂
207

## Page 208

5
SAML
飞塔SASE
回 fgt1
： Dashboard
+ Network
L Policy & Objects
A Security Profiles
旦 VPN
• User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
Fortokens
分 WiFi Controller
0 System
. Security Fabric
E Log& Report
教主VIP
飞塔NGFW与ZTNA
日Q
Edit User Group
Name
Type
Members
SalesGroup-SAML
Firewall
Remote Grouns
+Add
||• Edit|
亩 Delete
Remote Server s
Group Na
® FAC-SSO
qytsalesgroup
创建User Group
Add Group Match
Remote Server
Groups
@ FAC-SSO
AnySpecify2
qytsalesgroup
+
HA: Pimary 2-②、A-e admin-
×
飞塔SASE
教主VIP
教主VIP
飞塔SASE
教主VIP
飞塔SASE
FERTINET
OK
Cancel
教主VIP 飞塔SASE
乾颐堂
208

## Page 209

5
SAML
飞塔SASE
向fet1
G2 Dashboard
+ Network
L Policy & Objects
凸 Security Profles
口 VPN
S User & Authentication
User Definition
User Groups
Guest Management
LDAP Servers
RADIUS Servers
Single Sign-On
Authentication Settings
FortiTokens
分 WiFi Controller
o System
/ Security Fabric
Log & Report
教主VIP
飞K塔NGFW与ZTNA
HA: Primary〉-日、A、② admin、
PortiGate
啊.fgt！.
Send SSL-VPN Confguration
Additional intormation
飞塔SASE
© API Preview
% References
>- Editin CLI
教主VIP
② Online Guides
Relevant Documentation C
W Video Tutorials C
• Hot Questions at FortiAnswers
◎ Join the Discussion C
OK
Cancel
飞塔SASE］
教主VIP
飞塔SASE
教主VIP
乾颐堂
创建User Group
=Q
Edit User Group
Name
SalesGroup-SAML.
Firewall
Type
Members
Remote Groups
+Add
•Edit
面 Delete
Remote Server 4
@ FAC-SSO
Group Name 4
qytsalesgroup
飞塔SASE
FERTINET
V7.2.4
在此页面中查找
入<
高亮全部（A）
口 区分大小写（C
口 匹配变音符号（）
口 全词匹配M）
209

## Page 210

5 SAML
飞塔SASE
回fst1
Dashboard
+ Network
L Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZINA.
Authentication Rules
2
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Trafhic Shaping
A Security Profiles
口 VPN
2 User & Authentication
今 WiFi Controller
• System
• Security Fabric
臣 Log& Report
=
Q
+ Create New、
Edit
Authentication Rule
Authentication Scheme|
Implicit
向 Delete
Search
Name
Source Address
合SASE
教主VIP
飞K塔NGFW与ZTNA
创建Authentication Schemes
乾颐堂
Protocol
Q
Authentication Scheme
HA: Primary
>②•A、② admin、
① Authentication Rules
Authentication Schemes
SSO Authentication Scheme
Comments
教主VIP
教主VIP飞塔SASE
教主VIP 飞塔SASE
FERTINET
v7.2.4
教主VIP 飞塔SASE
210

## Page 211

5 SAML
飞塔SASE
回fgt1
62 Dashboard
中 Network
L Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZTNA
Authentication Rules
Addresses
Internet Service
Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
A Security Profiles
口 VPN
2 User & Authentication
WiFi Controller
0 System
Wh Security Fabric
FIRTINET
V7.2.4
在此页面中查找
教主VIP
飞塔NGFW与ZTNA
高亮全部（A）口 区分大小写（C）
飞塔SASE
VFOK
匹配变音符号（））口 全词匹配（）
卡VIP。
飞塔SASE
Cancel
飞塔SASE
教主VIP
乾颐堂
创建Authentication Schemes
=
Q
Edit Authentication Scheme
Name
Method
ztna-saml-authen-scheme
SAML
SAML SSO server
User database
Timeout
③ FAC-SSO
120
Seconds
NXHA Primary 2- ②、A•9admin，
Additional Information
④ API Preview
%o References
>- Edit in CLI
② Online Guides
國 RetovantDosuimentateg @
“ Viaco Tutoras E次，
电 Hot Questions at FortiAnswers
D Join the Discussion C
飞塔SASE
211

## Page 212

5 SAML
飞塔SASE
G fgt1
$ Dashboard
+ Network
L Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZTNA
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
Security Profles
口 VPN
2 User & Authentication
今 WiFi Controller
0 System
C Security Fabric
區 Log & Report
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
创建Authentication Rule
Q
三Q
+CreateNew、
•Edit
前 Delete
Authentication Rule
Method
Authentication Scheme
ztna-saml-authen-scheme
SAML2
Search
User database t
&0 QYTANGAD
Negotiate NTLM S
Kerberos Keytab
Domain Controller
⑦ Enabled
FSSO Agent令
HA: Primary〉_③、 、 8 admin、
⑦ Authentication Rules Authentication Schemes
Two-factor Authentication
* Disabled
FSSO guest
& Disabled
教主VIP
含SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE
FSRTINET
教士VIP 飞塔SASE
212

## Page 213

5 SAML
飞塔SASE|
G fgt1
Dashboard
+ Network
L Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZINA
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Trafhic Shaping
A Security Profiles
口 VPN
2 User & Authentication
今 WiFi Controller
0 System
• Security Fabric
臣 Log& Report
=Q
Add New Rule
Name
Source Address
Incoming interface
Protocol
Authentication Scheme
IP-based Authentication
commente
Enable This Rule
含SASE
教主VIP
飞K塔NGFW与ZTNA
教主VIP 飞塔SASE
FERTINET
v7.2.4
教主VIP
飞塔SASE
OK
Cancel
飞塔SASE
教主VIP
乾颐堂
创建Authentication Rule
（天
ztna-saml-authen-rule
日all-
m port1
HTTP
ztna-saml-authen-scheme
① Enable C Disable
Write acomment..
① Enable
• Disable
M0/1023
Additional Information
④ APIPreview
② Online Guides
日 Relevant Documentation C
C Video Tutorials C
典 Hot Questions at FortiAnswers
HA: Primary〉-日、白、Q admin、
飞塔SASE
213

## Page 214

5
SAML
s塔SASE
回 fest1
2 Dashboard
+ Network
L Policy & Objects
Firewall Policy
IPv4 DoS Policy
2
ZTNA
Authentication Rules
Addresses
Internet Service
Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
TrafficShaping
A Security Profles
口 VPN
2 User & Authentication
WiFi Controller
0 System
. Security Fabric
FERTINET
在此页面中查找
教主VIP
飞K塔NGFW与ZTNA
修改ZTNA Rule
三Q
ZTNA Rules
ZTNA Servers
ZTNA Tags
+Create New
Edit，
面 Delete
Search
Name
XFrom
Source
deny-no-firewall
围 port1
回 all
ztna-access-server-rule
port1
回 all
出 SalesGroup-SAML
>
NS HA: Primary
>-③、D、 9admin、
Q
固 Export、
ZTNA Tag
ZTNA Server
Action
Security Profiles
ZTNAIP
No_Firewall
日 ztna-server
⑦ DENY
L0gX
& Disabled
ZTNAIP
ZTNA IP
Sales_Tag
1Firewall|
日 ztna-server < ACCEPT
只 ztna-ssh
_no-inspection © AII
733.51
>
飞塔SASE
飞塔SASE
>
>
>
• Security Rating Issues
V7.2.4
^ <口 高亮全部（A）口 区分大小写（C）
匹配变音符号（）
全词匹配（W）
教主VIP
飞塔SASE
>
② Updated: 18:05:46 C
X
乾颐堂
214

## Page 215

5
SAML
飞塔SASE
回fgt1
Dacnboamo
+ Network
L Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZTNA
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
A Security Profles
口 VPN
S User & Authentication
今 WiFi Controller
System
0 Security Fabric
巨 Log & Report
教主VIP
飞塔NGFW与ZTNA
FRTINET
教主VIP
OK
Cancel
教主VIP
乾颐堂
修改ZTNA Rule
=Q
Edit ZTNA Rule
Name ⑦
Incoming Interface
Source
ZTNATag
Match ZTNA Tags
ZTNA Server
Destination
Schedule
Action
Security Profles
AntiVirus
Web Filter
ztna-access-server-rule
團 porti
回 all
型 SalesGroup-SAML
ZTNAIP
Firewall
ZTNA IP
」 Sales_Tag
Any
口 ztna-server
Q ztna-ssh
x
口 all
always
< ACCEPT
⑦ DENY
Application Control O
IPS
File Filter
飞塔SASE
SSL Inspection
no-inspection
Logging Options
Log Allowed Traffic 0
Security Events
All Sessions
Additional Information
@ API Preview
>- Editin CLI
Online Guides
号 Relevant Documentation C
• Video Tutorials C
HCondltated Polto Cofgewratey E
• Hot Questions at FortiAnswe片
Unable to connect FortiGate to EMS Cloud
w 1 Answers
• O Votes
⑧ 501 Views
See More C
飞塔SASE
SASE
215

## Page 216

5
SAML
飞塔SASE
回 fgt1
$2 Dashboard
+ Network
』 Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZTNA
Authentication Rules
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
A Security Profles
口 VPN
S User & Authentication
今 WiFi Controller
0 System
• Security Fabric
•區 Log & Report
=Q
Edit ZTNA Server
Type ①
Name
IPv4
Comments
Network
External interface
ExternalIP
port1
202.100.1.111
External port
443
6 SAML
SAML SSO server
③ FAC-SSO
Services and Servers
>
Default certificate
Service/server mapping
國 site1.qytang.com
+ Create new
② Edit
Services
URL=
HTTPS
/
前 Delete
1
HReal savaed/
教主VIP
飞K塔NGFW与ZTNA
教主VIP
乾颐堂
修改ZTNA Server添加SAML认证
Additional Information
◎ API Preview
S References
>- Edit in CLI
② Online Guides
日 Relevant Documentation L
•• Video Tutorials E
e Hot Questionsat ForiAnswers
Unable to connect FortiGate to EMS Cloud
1 1Answers
• OVotes
• 490 Views
See More 区
HA: Primary〉-B、A、② admin、
飞塔SASE
飞塔SASE
飞塔SASE
OK
Cancel
FHRTINET
216

## Page 217

5 SAML
飞塔SASE
EH FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
& User Account Policies
營 User Management|
Local Users
Remote Users
Remote User Sync Rules
Social Login Users
Guest Users
User Groups
Usage Profle
Realms
FortiTokens
MAC Devices
IAM
+ Portals
呈 Remote Auth. Servers
RADIUS Service
TACACS+ Service
& LDAP Service
& OAuth Service
E SAMLIdP
HFACAgent
Hhorinet SSo Methods
Monitor
Certifcate Management
Logging
Import Remote LDAP Users
Remote LDAP server：
Action：
FSASE
教主VIP
飞K塔NGFW与ZTNA
D② admin-
飞塔SASE
教主VIP
丁十
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP
飞塔SASE
乾颐堂
FAC导入LDAP用户
苓SASE
QYTANGAD （dc2019.qytang.com）v
Import users by group memberships <
217

## Page 218

5 SAML
；塔SASE
H日 FortiAuthenticator VM FAC-VMTM22004423
system
> Import Remote LDAP Users
Authentication
Remote LDAP server：
& User Account Policies
Action：
登 User Management（
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
+ Portals
Remote Auth. Servers
RADIUS Service
SASE
& TACACS+ Service
2 LDAP Service
& OAuth Service
E SAMLIdP
X點 FACAsent
•Fortinet SSO Methods
Monitor
Certificate Management
Logging
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FAC导入LDAP用户
（ Import Remote LDAP Users by Group Memberships — Mozilla Firefox
• B a1 https://fac.qytang.com/ldap/userbrowser-by-group/？_popup=1&remote_Idap=
Import Remote LDAP Users by Group Memberships
LDAPserver：
dc2019.qytang.com:636
Distinguished name：
Member attribute：
dc=qytang.dc=com
memnan
Group filter：
User flter：
（objectClass=group）
（&（objectClass=user）objectCategory=person））
Apply
Clear
User attributes
• Filter child nodes
conngured username atuibute. rou can conngure other user mapping attributes above.
Only users that are members of groups will be shown below （users must be part of member attribute of the groups）.
Select Visible
Select None
由口口 CN=Builtin
中口口 CN=Users
口口 OU=ADAdmin
中a OU-Sales
白 CN=SalesGroup
F MO CN=Salesuser
GOU-TAC
FortiToken Logo：
IAM Account：
Display name=salesuser, Last name=salesuser: Username=salesuser
［PleaseSelect］v
IPlease Selectl、
+X
飞塔SASE
o
目 山
×
？ admin、
教主VIP
OK
教主VIP
飞塔SASE
教主VIP
218

## Page 219

5 SAML
不
塔SASE
FAC导入LDAP用户
日H FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
& User Account Policies
User Management（•
口
Local Users
Remote Users
Remote User Sync Rules
Social Login Users
Guest Users
4 Import
• Export Users Delete O Re-Enable
S Successfully added 1 selected remote LDAP user（s） from "QYTANGAD （dc2019.qytang.com）”
wsemname
Remote LDAP Server
salesuser
QYTANGAD （dc2019.qytang.com）
1 / 30000 remote LDAP users
Usage Profle
2p2ms
FortiTokens
MAC Devices
IAM
安 Portals
W Remote Auth. Servers
E RADIUS Service
A TACACS+ Service
2 LDAP Service
& OAuth Service
閣 SAMLIdP
入彈FACAgent
Forfinet SSO Methods
Monitor
Certificate Management
Logging
$SASE
教主VIP飞塔SASE
Admin
Status
Token
教主VIP飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
admin、
LDAP
RADIUS
SAML
Token Requested
教主VIP
教主VIP 飞塔SASE
219

## Page 220

5
SAML
塔SASE
修改导入的LDAP用户，添加Token
EH： FortiAuthenticator VM FAC-VMTM22004423
System
Edit Remote LDAP User
Authentication
Lo User Account Policies
Remote LDAP server：
Username：
營 User Management
QYTANGAD （dc2019.qytang.com）
salesuser
CN=Salesuser,OU=Sales,DC=qytang,DC=com
Local users
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
+ Portals
Q Remote Auth.Servers
& RADIUS Service
E TACACS+ Service
R LDAP Service
& OAuth Service
E SAMLIdP
E FAC Agent
X:Fortinet SSO Methods
Monitor
③
Distinguished name：
• Disabled
•One-Time Password （OTP） authentication
Delver token conec trom
FortiToken Cloud
Deliver token code by：
Email
SMS
Dual （Email & SMS）
Mobile
Token：
Activation delivery method：
Email
FTKMOB3407896A2F
SMS
先提交再回来
+ Temporary token
• FIDO authentication
0Allow RADIUS authentication
0Sync in HA Load Balancing mode
User Role
Administrator
Sponsor
User
H User Information
Display name：
First name：
Salesuser
Last name：
Salesuser
Email：
Mobile number：
collinsctk@gmail.com
+86、13911053135
Dhone numher
Notify
SMS gateway：
Use defal
Certificate Management
Logging
Company：
Department：
Title：
Birthdate：
-m
Language：
FortiToken Logo：
Use default
［Please Select］v
教主VIP
飞塔NGFW与ZTNA
乾颐堂
D③ admin-
教主VIP
飞塔SA
填邮件与电话
教主VIP
220

## Page 221

5 SAML
塔SASE
修改导入的LDAP用户，添加Token
E FortiAuthenticator VM FAC-VMTM22004423
System
Edit Remote LDAP User
Authentication
Remote LDAP server：
QYTANGAD （dc2019.qytang.com）
& User Account Policies
Username
salesuser
營 User Management
Distinguished name：
CN=Salesuser,OU=Sales,DC=qytang,DC=com
Local Users
• Disabled
Remote Users
One-Time Password （OTP） authentication
Remote User Sync Rules
Deliver token codes from：
FordAuuiendcatol
FortiToken Cloud
Social Login Users
Deliver token code by：
FortiToken
Email
SMS （+86-13911053135）
Guest Users
Hardware
Mobile
User Groups
Usage Profle
Token：
FTKMOB3407896A2F
Realms
Activation delivery method：
Email
Show QR Code
FortiTokens
MAC Devices
IAM
Portals
W Remote Auth.Servers
RADIUS Service
+ Temporary token
• FIDO authentication
OAllow RADIUS authentication
0 Sync in HA Load Balancing mode
， User Role
Role：
& TACACS+ Service
+ User Information
& LDAP Service
& OAuth Service
H Password Recovery Options
日 SAMLIdP
F TACACS+
E FAC Agent
亞 Usage Information
XFortinet SSO Methods
Monitor
•日 Certificate Bindings
•田 Devices
Administrator
Snonsor
User
飞塔SASE
Certifcate Management
Dual （Email & SMS）
esloken
F RADIUS Attributes
Logging
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
D③ admin-
Activation Code for FortiToken Mobile FTKMOB3407896A2F："EEIDSHHJTS JWD7N"
Expiry date: May 19, 2023, 9:21 p.m.
Cancel
221

## Page 222

5
SAML
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
手机APP安装FortiToken
11:49
三の
6
飞塔SASE
Q fortitoken
取消
FortiToken Mobile
商务
實實文次次 14
Picselart - 艺术效果
照片效果和搅拌机
获取
乾颐堂
飞塔SASE
教主VIP
教主VIP 飞塔SASE
團型
ISASE
教主VIP
飞
InfoToken
工具
获取
355729
Today
游戏
教主VIP 飞塔SASE
222

## Page 223

5
SAML
教主VIP飞塔SASE
教主VIP 飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP飞塔SASE
飞塔SASE
手动输入
FERTINET
教主VIP 飞塔SASE
FHHBTINET
飞塔SASE
教主VIP
乾颐堂
手机APP 扫描二维码添加令牌
11:22
设置
、添加帐号
欢迎使用 FortiToken移动
扫描或输入密钥以添加帐号
11:25
设置
FortiToken 6A2F
384170
FortiToken
管理十
飞塔SASE
教主VIP
223

## Page 224

5 SAML
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
教主VIP
教主VIP
Chrome 应用...
添加快捷方式
教主VIP
飞塔SASE
乾颐堂
FortiClient.再次访问服务器
教主VIP
爷
教主VIP
◎ 新标签页
×
个
① sitel.qytang.com
选择证书
若要接收后续 Google Chrome 更新，您需使用Windo 请选择证书，以在 sktel.qytang.com:443 上对您本人进行身份验证，
主题背景
颁发者
E9A73C36337F40CABC9CBDA8.
FCTEMS8823002976
清空缓存
再测试
飞塔SASE
序列号
718B5ABFE766E45.
证书信息
确定
取消
Q 在Google 上搜索，或者输入一个网址
E 口：
了解详情 ×
教主VIP
飞塔SASE|
224

## Page 225

5 SAML
飞塔SASE
教主VIP
Ea Login
个
教主VIP
飞塔NGFW与ZTNA
FortiClient.再次访问服务器
• fac.qytang.com/sam-ip/qytangsaml/bgi/？SAMLRequest=hZJLb8IWEIT92FSUR7cGleBQuQgLQqUh9RoT30UrJApYS0%2FVu2VLV640%.. E 口2：
教主VIP
|0|回I 8
了解详情 ×
教主VIP
飞塔SASE
飞塔SASE
salesuser
教主VIP，
教主VIP
教主VR/K塔SASE
教主VIP/塔SASE
乾颐堂
225

## Page 226

5 SAML
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FortiClient.再次访问服务器
教主VIP
e Login
个
教主VIP
<
［01回L8
• fac.qytang.com/sam-idp/qytangsaml/lgin/？csrfmiddlewaretoken=ZuR FgghFUHo2L9JjjaOGNCgTRXvXnywwZ0FhAhS5c8sL8k8v.. or國区 口1：
了解详情 ×
教主VIP
飞塔SASE
飞塔SASE
salesuser
Cisc0123
教主VIP，
飞塔SASE
教主VIP
老
Not salesuser? Sign in as a different user
教主VIP/塔SASE
226

## Page 227

5 SAML
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
［0|回_ 8
了解详情 ×
教主VIP
飞塔SASE
飞塔SASE
教主VIP，
教主VIP
Enter Your Token Code
salesuser
384170
Verify
Not salesuser? Sign in as a different user
输入令牌
飞塔SASE
教主VIP，
乾颐堂
FortiClient.再次访问服务器
教主VIP
e9 Login
个
×十
• fac.qytang.com/samHidp/qytangsamVbogin/？csrfmiddlewaretoken=ZuRFgghFUHo2L9JjiaOGNCgTRXvXnywwZ0FhAhS5c8sL8k8V.. on 電区众口1：
教主VIP
227

## Page 228

5 SAML
教主VIP
教主VIP
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
FortiClient 再次访问服务器
ASE
爷
S QYTANG NGINX
个
×
• site1.qytang.com
|0l回I8
<
图白攻口。：
4 QYTANG NGINX
我
教主\
飞塔SASE
教主VIP，
乾颐堂
飞塔SASE
教主VIP，
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP/塔SASE
228

## Page 229

5
SAML
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
TCP Forwarding也会触发SAME
2 192.168.1.1（0ot）
1obaxterm
回收站
Firefox
X server|
Tools Games
Settings Mac
Solt
四4. 192.168.1.1 （10ot）
MubExec, Tunnelng Packages
w roruclent- cero Irus
user sessons
Q Login （278）
证书
Forticlient
K塔SASE
salesuser
Add Full Name
Phone
Add Phot
电子邮件
Get personalinfofrom.
H1 os Updated 5/23/2023 上午9:19:59
四Linkedin
G Google
• Salesforce
状态
Hostname
Domair
+/0n-tabnd
DESKTOP-FKQFFRD
Zero Trust Tags a
Sales_ Tag
Firewalll
激活 Windows
转到”设置”以激活 Windows。
229

## Page 230

5
SAML
飞塔SASE
Site1_FGT1
（ Dashboard
+ Network
L Policy & Objects
Firewall Policy
IPv4 DoS Policy
ZTNA
Authentication Rules
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
4 Security Profiles
回 VPN
S User & Authentication
分 WiFi Controller
¢ System
• Security Fabric
區 Log & Report
Q
ZTNA Rules
ZTNA Servers
ZTNA Tags
+ Create New
• Edit
@ Delete
Searcl
Name
From
deny-no-frewall
port1
ztna-access-server-rule
port1
Policy
Set Status
Y Filter by Name
四 Copy
尼 Paste
+ Insert Empty Policy
SASE
Show Matching Logs
LShow in FortiView
•Edit
>_ Editin CLI
白 Delete Policy
教主VIP
飞K塔NGFW与ZTNA
教主VIP
飞塔SASE
②| Updated: 09:16:01 C
乾颐堂
查看日志
Source
all
回 all
mSalesGroup-SAML
ZTNA Tag
ZTNAIP
」No_Firewall
ZITNAIP
.Sales_Tag
Firewall|
ZTNA Server
口 ztna-server
• 口 ztna-server
只 ztna-ssh
Action
② DENY
< ACCEPT
HA: Primary）-⑧、A、② admin-
Security Profiles
no-inspection
Log
③ AIl
S AIl
c Export
0B
12.29kB
飞塔SASE
教主VIP 飞塔SASE
FERTINET
0 Security Rating Issues
230

## Page 231

5
SAML
飞塔SASE
G Site1 FGT1
82 Dashboard
+ Network
L Policy & Objects
• Security Profiles
口 VPN
2 User & Authentication
今 WiFi Controller
¢ System
• Security Fabric
匹 Log & Rcport|1
Local Traffic
Sniffer Traffic
ZTNA Traffic
System Events
Security Events
Reports
Log Settings
用户信息
查看日志
=Q
C
Policy UUID == 1eb16346-fad3-51ed-c5B2-cec12404bf.. x + Q Search
Date/Time
2023/05/26 09:55:09
2023/05/26 09:54:35
2023/05/26 09:54:35
2023/05/26 09:54:29
2023/05/26 09:54:10
2023/05/26 09:53:55
^>
2023/05/26 09:53:54
2023/05/26 09:53:44
4 2023/05/26 09:53:35
2023/05/26 09:53:20
2023/05/26 09:52:09
2023/05/26 09:52:08
2023/05/2609:51:54
2023/05/26 09:51:24
2023/05/26 09:51:24
2023/05/26 09:51:19
2023/05/26 09:50:56
2023/05/26 09:50:06
2023/05/26 09:48:55
Source
o salesuser （202.100.100.201）
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
salesuser （202,100,100.201）
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100,100.201
202,100,100.201
ZTNA Server
只 ztna-ssh
ztna-ssh
口 ztna-ssh
口 ztna-ssh
旦 ztna-ssh
旦 ztna-ssh
只 ztna-ssh
口 ztna-ssh
只 ztna-server
Q ztna-ssh
旦 ztna-ssh
只 ztna-ssh
只 ztna-ssh
口 ztna-ssh
只 ztna-ssh
只 ztna-ssh
只 ztna-ssh
只 ztna-ssh
Q ztna-ssh
Destination
192.168.1.1
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
192.168.1.1
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
202.100.1.111
FERTINET
Service
SSH
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
HTTPS
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
tcp/2222
\tCp/2222
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
有数据
HA: Primary
>-
Q
位 Disk、
Result
< Accept （2.81 kB/21 B）
V Accept （517 B/0B）
V Accept （547 B/0B）
< Accept （1.70 kB/0B）
< Accept （1.70 kB/0B）
< Accept （1.70 kB/0B）
Y Accept （2.30KB/0B）
< Accept （1.70 kB/0B）
< Accept （13.88 kB/6.20 kB）
< Accept （1.70kB/0 B）
< Accept （1.70kB/0B）
< Accept （1.70 kB/0B）
V Accept （1.70 kB/0B）
< Accept （517B/0B）
< Accept （547 B/0B）
V Accept （1.70 kB/0B）
V Accept （1.70kB/0 B）
V Accept （1.70 kB/0B）
< Accept （1.70kB/0B）
②、A、②admin、
© 1hour、
日 Details
Policy ID
X
-VP
19
231

## Page 232

SAML
飞塔SASE
向 Site1_FGT1
8 Dashboard
4 Network
山 Policy & Objects
A Security Profiles
旦 VPN
2 User & Authentication
分 WiFiController
¢ System
• Security Fabric
E Log& Report
Forward Traffic
Local Traffic
Sniffer Traffic
ZTNA Traffic
System Events
Security Events
Reports
Log Settings
教主VIP
飞K塔NGFW与ZTNA
查看日志
=Q
Policy UUID == 1eb16346-fad3-51ed-c582-cec12404bf... x + Q Search
Date/Time
Source
2023/05/26 09:55:09
2023/05/26 09:54:35
2023/05/26 09:54:35
2023/05/26 09:54:29
2023/05/26 09:54:10
2023/05/26 09:53:55
2023/05/26 09:53:44
2023/05/26 09:53:35
2023/05/26 09:53:20
2023/05/26 09:52:09
2023/05/26 09:52:08
2023/05/26 09:51:54
2023/05/26 09:51:24
2023/05/26 09:51:24
2023/05/26 09:51:19
2023/05/26 09:50:56
2023/05/26 09:50:06
2023/05/26 09:48:55
B salesuser （202.100.100.201）
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
salesuser （202,100.100.201）
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
ZTNA Server
只 ztna-ssh
日 ztna-ssh
. ztna-ssh
只
.ztna-ssh
ztna-ssh
见 ztna-ssh
见 ztna-ssh
见 ztna-ssh
只 ztna-server
口 ztna-ssh
见 ztna-ssh
里 ztna-ssh
只ztna-ssh
口 ztna-ssh
只 ztna-ssh
只 ztna-ssh
只 ztna-ssh
口 ztna-ssh
只 ztna-ssh
Destination
Service
192.168.1.1
SSH
202.100.1.111
tcp/2222
202.100.1.111
tcp/2222
202.100.1.111
tcp/2222
202.100.1.111
202.100.1.111
tcp/2222
tcp/2222
202.100.1.111
202.100.1.111
192.168.1.1
tcp/2222
tcp/2222
HTTPS
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111
tcp/2222
202.100.1.111 tcp/2222
Result
V. Accept （2.81 kB/21 B）
Y Accept （517 B/0B）
V Accept （547 B/0B）
V Accept （1.70kB/0B）
V Accept （1.70kB/0B）
< Accept （1.70 kB/0B）
V Accept （2.30kB/0B）
V Accept （1.70kB/0B）
V Accept （13.88 kB / 6.20 kB）
V Accept （1.70 kB/0B）
V Accept （1.70kB/0B）
V Accept （1.70kB/0B）
V Accept （1.70 kB/0B）
V Accept （517B/0B）
V Accept （547 B/0B）
V Accept （1.70kB/0B）
V Accept （1.70kB/0B）
< Accept （1.70 kB）0B）
< Accept （1.70kB/0B）
F推RTINET
SASE
不》
HA:Primary
>- ②•A、②admin•
Q
（ Disk、
© 1hour、
日 Details
Pol Log Details
口 General
Absolute Date/Time
ast Access Time
Duration
Session ID
VDOM
2023-05-26
09:53:35
165
40,516
口 Source
Source
Source Port
Source Country/Region
Source Interface
FortiClient ID
Group
202.100.100.201
51,428
China
圖 port！
3BC53CF242304506B6BB1BB3D29
8D82D
salesuser
SalesGroup-SAML
口 Destination
Destination
Destination Port
Destination Country/Region
Destination Interface
192.100.1.1
443
Reserved
圖 port3
口 Application Control
Category
Protocol
Service
unscanned
飞塔SASE
HTTPS
日 Data
Received Bytes
Sent Bytes
19
6.20kB
13.88kB
13882
乾颐堂
源
232

## Page 233

5 SAML
；塔SASE
查看日志
G site1_FGT1
E Dashboard
+ Network
』 Policy & Objects
4 Security Profiles
息 VPN
2 User & Authentication
分 WiFi Controller
¢ System
粉 Security Fabric
區 Log & Report
Forward Traffic
Local Traffic
Sniffer Trafhic
ZTNA Traffic
System Events
Security Events
Reports
Log Settings
=
Q
C上
（ Policy UUID == 1eb16346-fad3-51ed-c582-cec12404bf.. X + Q Search
Date/Time
2023/05/26 09:55:09
2023/05/26 09:54:35
2023/05/26 09:54:35
2023/05/26 09:54:29
2023/05/26 09:54:10
2023/05/26 09:53:55
<
2023/05/26 09:53:54
2023/05/26 09:53:44
2023/05/26 09:53:35
2023/05/26 09:53:20
女
2023/05/26 09:52:09
2023/05/26 09:52:08
2023/05/2609:51:54
2023/05/2609:51:24
2023/05/26 09:51:24
2023/05/26 09:51:19
2023/05/26 09:50:56
2023/05/26 09:50:06
2023/05/26 09:48:55
Source
ZTNA Server
salesuser （202.100.100.201）
202.100.100.201
202.100.100.201
口 ztna-ssh
只 ztna-ssh
口 ztna-ssh
202.100.100.201
里 ztna-ssh
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
salesuser （202,100,100.201）
里 ztna-ssh
日 ztna-ssh
Q ztna-ssh
只 ztna-ssh
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
202.100.100.201
里 ztna-server
只 ztna-ssh
口 ztna-ssh
只 ztna-ssh
口 ztna-ssh
Q ztna-ssh
只 ztna-ssh
ztna-ssh
只 ztna-ssh
只 ztna-ssh
只 ztna-ssh
ecTinati0n
Service
192.168.1.1
SSH
202.100.1.111
tcp/2222
202.100.1.111
tcp/2222
202.100.1.111
202.100.1.111
tcp/2222
tcp/2222
202.100.1.111 tcp/2222
202.100.1.111 tcp/2222
202.100.1.111
tcp/2222
192.168.1.1
HTTPS
202.100.1.111
tcp/2222
202.100.1.111
tcp/2222
202.100.1.111
202.100.1.111
tcp/2222
tcp/2222
202.100.1.111
tcp/2222
202.100.1.111
tcp/2222
202.100.1.111
tcp/2222
202.100.1.111 tcp/2222
202.100.1.111
tcp/2222
202.100.1.111
tcp/2222
教主VIP
飞塔NGFW与ZTNA
乾颐堂
Result
V Accept （2.81 kB/21 B）
< Accept （517 B/0B）
V Accept （547 B/0B）
V Accept （1.70 kB/0B）
< Accept （1.70 kB/0B）
< Accept （1.70 kB/0B）
V Accept （2.30kB/0B）
V Accept （1.70 kB/0B）
< Accept （13.88 kB / 6.20 kB）
< Accept （1.70kB/0B）
V Accept （1.70kB/0B）
V Accept （1.70 kB/0B）
< Accept （1.70 kB/0B）
V Accept （517 B/0B）
< Accept （547 B/0B）
V Accept （1.70 kB/0B）
< Accept （1.70 kB/0B）
V Accept （1.70 kB/0B）
<Accept（1.70kKB/0B）
FRTIDET
Pol Log Details
口 Action
Action
Policy UUID
Policy Type
口 Security
Level
口 Cellular
Service
曰 Other
Log eventoriginal timestamp
Timezone
LOg ID
Sub Type
Source Interface Role
Destination Interface Role
Proxy Application Category
Policy Name
Authentication Server
API Gateway ID
VIP
ZTNA Server
Client Device Manageable
Client Device Tags
EMS Connection
19
HA: Primary》-
②、白、Qadmin、
Q家 Disk、
© 1hour、日 Details
accept
1eb16346-fad3-51ed-C582-cec1240
4bf89
Proxy
notice
HTTPS
1685066015351533600
+0800
0005000024
traffic
ztna
unnennen
undefined
http
ztna-access-server-rile-
FAC-SSO
ztna-server
只 ztna-server
manageable
ZTNAMAC
ZTNA MAG
ZTNAIP
ZTNAMAG
の Online
Sales_Tag
all registered_clients
allregistered_clients
Firewall
标签
233

## Page 234

乾颐堂
第6部分. SSLVPN与L2LVPN
塔SASE
K塔SASE
教主VIP 飞塔SASE
教主VIP
飞塔SASE

## Page 235

6
SSLVPN与L2LVPN
教主
SASE
Remote Access
Profile
EMS
实验拓扑
飞塔SASE
教主VIP
ZTNA Agent
FGT
教主VIP
Radius
Syslog SSO
FAC
教主VIP
飞K塔NGFW与ZTNA
飞塔SASE
主VIP
1dap
Active Directory
SSLVPN
ASE
Explicit Proxy
SSLVPN POOL
172.16.100.0/24
教主VIP
S2SVPN
SWG
FSSO
教主VIP
INTERNET
教主VIP
飞塔SASE
乾颐堂
235

## Page 236

6
SSLVPN与L2LVPN
教主VIP
飞K塔NGFW与ZTNA
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE
乾颐堂
FAC配置Radius服务
EHE FortiAuthenticator VM FAC-VMTM22004423
System
Create New Authentication Client
Authentication
Name：
& User Account Policies
Client address：
妥 User Management
FGT
IP/Hostname
Subnet
fgt1.qytang.com
心 Portals
m Remote Auth! Servers
RADIUS Service 2）
Secret：
• Accept RADIUS accounting messages for usage enforcement
• Support RADIUS Disconnect messages
［Clients 3
Policies
Certificates
Services
Dictionaries
Accounting Proxy
& TACACS+ Service
M LDAP Service
%o OAuth Service
F SAMLIdP
H FAC Agent
SSASE.
Fortinet SSO Methods
Monitor
Certificate Management
Logging
N
Range
oK
D? admin-
意，
教主VIP
236

## Page 237

6 SSLVPN与L2LVPN
沦
EH日 FortiAuthenticator VM FAC-VMTM22004423
System
+ Create New 2 Import Delete Edit
◎ The Authentication client "FGT （fgt1.qytang.com） was added successfully.
& User Account Policies
总 User Management
香 Portals
三 Remote Auth. Servers
RADIUS Service
Clients
Policies
Certificates
Services
Dictionaries
Accounting Proxy
TACACS+ Service
2 LDAP Service
&o OAuth Service
E SAML IdP
HH FAC Agent
Fortinet SSO Methods
Monitor
Certificate Management
Logging
Name.
FGT
1/ 10000 Authentication clients
SASE
FAC配置Radius服务
Client Name/IP
Tu.cytang.com
教主VIP
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
D③ admin-
教主VIP 飞塔SASE
237

## Page 238

6 SSLVPN与L2LVPN
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP，
Active Directory 用户和计算机
文件（F 操作（A） 看（V）帮助（H）
山 Active Directory 用户和计算机 （DC2019.qytang.c
保存的查询
~ mqytang.com
> G ADAdmin
Builtin
Computers
Domain Controllers
ForeignSecurityPrincipals
Keys
LostAndFound
Managed Service Accounts
Program Data
Sales
System
TAC
Users
I NTDS Quotas
TPM Devices
QytSplit
QytWeb
名称
您SalesGroup
S Salesuser
类型
安全组-全局
用户
描述
教主VIP
飞塔SASE
教主VIP
飞塔SASE
教主VIP 飞塔SASE
教主VR塔SASE
乾颐堂
AD用户状态［Sales］
飞塔SASE
238

## Page 239

6 SSLVPN与L2LVPN
塔SASE
教主VIP
飞塔NGFW与ZTNA
AD用户状态［QytSplit］
飞塔SASE|
乾颐堂
Active Directory 用户和计算机
文件（月
操作（A） 查看（V） 帮助（H）
× 1日副
3路街了回3
日 Active Directory 用户和计算机 ［DC2019.qytang.c
保存的 询
~ 開qytang.com
名称
龜qyt-split
& qyt-split-user
ADAdmin
Builtin
Computers
Domain Controllers
ForeignSecurityPrincipals
Keys
LostAndFound
Managed Service Accounts
Program Data
Sales
System
TAC
Users
NTDS Quotas
TPM Devices
QytSplit
QytWeb
飞塔SASE
教主VIP
类型
安全組•全局
用户
描述
飞塔SASE
教主VIP）
教主VIP 飞塔SASE
教主XP个塔SASE
239

## Page 240

6 SSLVPN与L2LVPN
不
塔SASE
教主VIP
飞塔NGFW与ZTNA
AD用户状态［QytWeb］
飞塔SASE
Active Directory 用户和计算机
文件（日
操作（A） 查看（V） 帮助（H）
飞塔SASE
Active Directory 用户和计算机 ［DC2019.qytang.c
保存的 询
v開qytang.com
> G ADAdmin
二 Builtin
Computers
Domain Controllers
ForeignSecurityPrincipals
］ Keys
LostAndFound
Managed Service Accounts
Program Data
Sales
System
TAC
Users
1 NTDS Quotas
TPM Devices
QyvtSplit
QvtWeb
名称
應qyt-web
& qyt-web-user
类型
安全组-全局
用户
描述
教主VIP
飞塔SASE
教主VIP 飞塔SASE
教主VIP，
飞塔SASE
乾颐堂
240

