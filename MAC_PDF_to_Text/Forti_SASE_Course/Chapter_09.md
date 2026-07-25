# Module 9: Forti SASE Course

## Page 321

6
SSLVPN与L2LVPN
；塔SASE
教主VIP
飞塔NGFW与ZTNA
BGP
Routing Objects
Multicast
Diagnostics|
島 Policy & Objects
A Security Profles
口 VPN|
2 User &Authentication
分 WiFi Controller
g System
• Security Fabri
區 Log&Rep
swg # get router info ospf route
OSPF process e：
Codes: C- connected, D - Discard, 0 - OSPF, IA - OSPF inter area
N1 - OSPF NSSA external type 1, N2 - OSPF NSSA external type 2
- OSPF external type 1, E2 - OSPF external type 2
10.10.10.1/32 ［100］ via 10.10.10.1, Site2-Sitel-VPN, Area 0.0.0.0
10.18.10.2/32 ［100］ is directly connected, Sitez-Site1-VPN, Area 0.8.9.0
172.16.1.0/24 ［1］ is directly connected, port2, Area 0.9.8.0
192.168.1.8/24 【101］ via 10.18.18.1. Sitez-Site1-VPN, Area 8.8.8.0
swg #
飞塔SASE
乾颐堂
SWG查看OSPF邻居与路由
9 Dashboard|
F Network
DNS
IPAM
SD-WAN
CLI Console （1）、
swg # get router info ospf neighbor
OSPF process B, VRF 0：
Neighbor ID
Pri
State
1.1.1.1
Fu11/-
BL• I X
Dead Time
00:00:35
Address
10.10.10.1
Interface
Site2-Site1-VPN（tun-id:202.100.1.10）
Qadmin
飞塔SASE
321

## Page 322

6
SSLVPN与L2LVPN
飞塔SASE
中 Network
巴 Policy & Objects
CLI Console （1）•
fgt1 # get router info ospf neighbor
OSPF process Q, VRF 0：
Neighbor ID
Pri
State
2.2.2.2
Ful1/-
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FGT1测试对Site2网络的访问
21
ity Profles
9 admin
By Sequen
Dead Time
00:00:39
Address
10.10.10.2
Interface
Site1-Site2-VPN（tun-id:202.100.2.10）
Protocol Options
Traffic Shaping
' Security Profiles
息 VPN
2 User & Authentication
今 WiFi Controllen
章 System
• Security Fabric
區 Log & Rep
fgtl # get router info ospf route
OSPF process 0：
Codes: C- connected, D - Discard, 0 - OSPF, IA - OSPF inter area
N1 - OSPF NSSA external type 1, N2 - OSPF NSSA external type 2
E1 - OSPF external type 1, E2 - OSPF external type 2
10.10.10.1/32 ［100］ is directly connected, Sitel-Site2-VPN, Area 8.9.9.0
10.10.10.2/32 ［100］ via 10.10.10.2.
Site1-Site2-VPN, Area 0.9.0.9
172.16.1.0/24 ［101］ via 10.10.10.2，
Sitel-Site2-VPN, Area 0.0.0.0
192.168.1.0/24 ［1］ is directly connected, port3, Area 0.0.0.0
fgt1 # execute ping 172.16.1.1
PING 172.16.1.1 （172.16.1.1）： 56 data bytes
64 bytes from 172.16.1.1: icmp_seq=9 tt1=63 time=1.6 ms
64 bytes from 172.16.1.1: icmp_seq=1 tt1=63 time=1.5 ms
64 bytes from 172.16.1.1: icmp_seq=2 tt1=63 time=1.6 ms
64 bytes from
172.16.1.1: icmp_seq=3 tt1=63 time=1.6 ms
64 bytes from 172.16.1.1: icmp_seq=4 tt1=63 time=1.6 ms
--- 172.16.1.1 ping statistics ---
5 packets transmitted, 5 packets received, 0% packet loss
round-trip min/avg/max = 1.5/1.5/1.6 ms
fgt1 #
fgti#
⑦ AIl
⑦ AIl
no-inspection|
⑦ AIl
no-inspection|
⑦ AIl
no-inspection Q All|
no-inspection|
⑦ AIl
no-inspection|
D UTM
no-inspection|
D UTM
c Disabled
《塔SASE
Socrity Ratinp locrm
G0 Updated: 08:44:10 S
322

## Page 323

6
SSLVPN与L2LVPN
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FGT1配置防火墙策略放行SSLVPN到Site2的流量
G fgt1
m Dashboard
+ Network
L Policy &Objects
Firewall Policy
IPv4 DoS Policy
ZTNA.
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
2 User & Authentication
分 WiFiController
¢ System
• Security Fabric
區 Log& Report
HA: Primary 〉-②•4、② admin-
New Policy
onal Information
众
Name ⑧
Incoming Interface
permit-ss/vpn-to-site2
四 SSL-VPN tunnelinterface （ssl.roo x
⑧ APIPreview
Outgoing Interface
2 Site1-Site2-VPN
② Online Guides
• Relevant Documentation C
source
日 all
亞 SalesGroup
172.16.100.0/24
IP/MAC Based Access Control ⑧
Destination
口 all
_10.10.18.0124 — —
-1
Service
5 always
⑦ ALL
tunne！
tunneLD
（SSLVPN Tunnel
Action
v ACCEPT
② DENY
192.168.1.0/24
port3
port）202.180.1.0/24
.254
202.100.2.0124
（port1|
（portz）172.16.1.8/24
.254
Inspection ModeFlow-based Proxy-based
.254
（tunne】
Firewall/Network Options
1⑨NAT
Protocol Options
or default
Security Profles
AntiVirus
Web Filter
DNS Filter
Application Control O
IPS
File Filter
飞塔SASE
（tunne10）
Loopbacke
3.3.3.3/24
SSL Inspection
I no-inspection
Logging Options
Log Allowed Traffic
Security Event
v7.2.4
OK
Cancel
教主VIP
323

## Page 324

6 SSLVPN与L2LVPN
回 fgt1
& Dashboard
+ Network
L Policy &Objects
Firewall Policy
IPv4 DoS Policy
LINA
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
A Security Profiles
旦 VPN
2 User & Authentication
今 WiFi Controller
¢ System
• Security Fabric
區 Log & Report
教主VIP
飞塔NGFW与ZTNA
FGT1配置防火墙策略放行SSLVPN到Site2的流量
Q
+Create New
• Edit
白 Delete
Q Policy lookup
Name
permit-internet-traffic
From
Source
Destination
Schedule
Service
permit-inside-to-dmz-traffic
1 port2
port3
port2
port1
口 all
回 all
5 always
⑦ ALL
permit-dc-inbound-traffic
port1
permit-fac-inbound-traffic
port1
port3
port3
port3
permit-ss/vpn-full-tunnel-traffic
② SSL-VPN tunnel interface （ssl.root）
port3
permit-sslvpn-split-tunnel-traffic
② SSL-VPN tunnel interface （ssl.root）
port3
permit-sslvpn-web-access-traffic
② SSL-VPN tunnel interface （ssl.root）
port3
port3
口 all
口 all
日 all
出 SalesGroup
口 all
幫 SplitTunnelGroup
口 all
莊 WebAccessGroup
口 all
屆 Site1-Site2-VPNJocal
會 DMZ-DC
5 always
5 always
5 always
Q ALL
Z ALL
會 DMZ-FAC
日 all
见 ALL
7 always
见 ALL
洄 Site1-DMZ-Net
. always
⑦ ALL
回 all
5 always
Q ALL
vpn_Site1-Site2-VPN_local_O
vpn_Site1-Site2-VPN._remote_.O
permit-sslvpn-to-site2
② Site1-Site2-VPN
② SSL-VPN tunnel interface （ssl.root）
②
Site1-Site2-VPN
port3
② Site1-Site2-VPN
加 Site1-Site2-VPN_remote
Implicit Deny.
口 any
品 Site1-Site2-VPN_remote
出 SalesGroup
日 all
口 all
尼 Site1-Site2-VPN_local
回 all
. always
a always
always
⑦ ALL
QALL
⑦ ALL
口 any
飞塔SASE
1 all
always
Q ALL
飞塔SASE
教主VIP
HA: Primary
>-
③•
9 admin、
口 Export-
Interface Pair View
By Sequence
Action
VACCEPT
NAT
⑦ Enabled
Security Profles
no-inspection
ACCEPT
ACCEPT
• Disabled
Ino-inspection
no-inspection
③ AIl
③ AIl
ACCEPT
no-inspection
③ AIl
• ACCEPT
Disabled
no-inspection
③ AIl
vACCEPT
◎ Enabled
no-inspection
Q AIl
SACCEPT
∞ Disabled
no-inspection
© AIl
v ACCEPT
VACCEPT
ACCEPT
Disabled
no-inspection
D UTM
t Disabled
∞ Disabled
no-inspection
sst no-inspection
D UTM
S AIl
② DENY
t Disablec
飞塔SASE
教主VIP
FIRTINET
v7.24
⑨ Security Rating Issues
11 Updated: 11:23:27
？
乾颐堂
324

## Page 325

6
SSLVPN与L2LVPN
教主VIP
飞K塔NGFW与ZTNA
SWG配置静态路由解决去往SSLVPN PooI的路由
回swg
m Dashboard
+ Network
Interfaces
DNS
SD-WAN
Static Routes
Policy Routes
RIP
OSPF
BGP
Kouung ODlees
Diagnostics
L Policy & Objects
• Security Profiles
口 VPN
2 User & Authentication
分 WiFi Controller
¢ System
. SecurityFabric
E Log & Report
=Q
New Static Route
>- ②•4①•②admin、
onalInformation
Iterface
Subnet
Named Address Internet Service
172.16.100.0/241
E Site2-Site1 VPN：
⑧ APIPreview
Administrative Distance 0
众
② Online Guides
• Relevant Documentation C
• Video Tutorials C
.rteacommen
• Enabled © Disabled
含0/255
飞塔SASE
由 Advanced Options
D） Hot Ouections at FortiAncwers
D Join the Discussion C
172.16.100.0/24
谷SASE
_10.20.10.0/24
Cunnel
CuneL
SSLVPN Tunnel
192.168.1.0/24
飞塔SASE
202.100.1.0/24
portl
.254
202.100.2.0/24
porti
port2172.16.1.8/24
254
-202.100.3.0/24
SASE
FSRTINET
V7.24
教主VIP
教主VIP
.10
GigabitEthernet1
10.10.20.0/24
Loopbacke）
3.3.3.3/24
乾颐堂
325

## Page 326

6
SSLVPN与L2LVPN
G swg
m Dashboard
# Network
Intertaces
DNS
IPAM
SD-WAN
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Objects
Multicast
Diagnostics
L Policy & Objects
A Security Profles
Q VPN
2 User & Authentication
今 WiFi Controller
¢ System
• Security Fabric
區 Log& Report
教主VIP
飞K塔NGFW与ZTNA
SWG配置静态路由解决去往SSLVPN PooI的路由
=Q
>- ②、4①、② admin -
+Create New
•Edit
Clone
色 Delete
Search
Q
Destination 4
Interface s
Status =
Comments一
0.0.0.0/0
層 site2-Site1-VPN_remote
品 Site2-Site1-VPN_remote
公172.16.100.0/24
202.100.2.254
團 port1
② Site2-Site1-VPN|
Q Enabled
©-Disabled|
VPN: Site2-Site1-VPN （Created by VPN wizard）
VPN: Site2-Site1-VPN （Created by VPN wiz
2 Site2-Site1-VPN
⑦ Enabled
乾颐堂
塔SASE
教主VIP飞塔SASE
教主VIP 飞塔SASE
教主VIP飞塔SASE
326

## Page 327

6
SSLVPN与L2LVPN
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
salesuser拨号测试访问Site2网络
1obaxterm
回 FortiClient - Zero Trust Fabric Ags
文件 帮助
回收站
VPN 已连接
Firefox
Google
Chrome
FortiClient
四 命令提示符
icrosoft Windows ［版本 10.0.17763.4377
e） 2018 Microsort Corporation。保留所有权利，
C： \Users\Admin>ping 172.16. 1.1
172.16.1.1
字节的数据：
72.
16.1.1
的
回复：
时间=2ms
TTL=62.
1.1
1.1
复复」
嘂鷥
TTL=6%
回=1ms
TTL=62
1.1
約回复
时间=2me
TTL=62
172.16.1.1的Ping 統计信息：
=4，
已接收=4，丢失=0（0%丢失），
往返行程的估计时间（以臺秒为单位）：
敢短=Ims，敢长=2ms，
C：\UsersVAdmin〉-
% salesuser
S ZERO TRUST TELEMETRY
S REMOTE ACCESS
◎ ZTNA DESTINATION
⑦ MALWARE PROTECTION
愛 VULNERABILITY SCAN
」.…
VPN 连接 qyt-sslvpn
IP 地址 172.16.100.1
用户名 salesuser
连接时间 00:00:39
接收字节数 0.64 KB
发送字节数 19.65 KB
中浙连接
回 About
327

## Page 328

6
SSLVPN与L2LVPN
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
salesuser拨号测试访问Site2网络
教主VIP
-口
×
⑤ QVTANG NGINX
QYTANG NGINX ）
老
飞塔SASE
教主VIP
教主VIP
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE
328

## Page 329

6
SSLVPN与L2LVPN
；塔SASE
向sw8
$ Dashboard
+ Network
』 Policy & Objects
A Security Profiles
口 VPN2，
Overlay Controller VPN
IPsec Tunnels
IPsecWizard 3
IPsec Tunnel Template
=Q
VPN Creation Wizard
① VPN Setup
Name
Template type
Site2-Site3-VPN
［Site to Site Hub-and Spoke Remote Access
Custom
SSLVPN POOL
172.16.100.0/24
SSLVPN Settings
SSL-VPN Clients
VPN Location Map
2 User & Authentication
分 WiFi Controller
¢ System
• Security Fabric
區 Log & Report
.1
tunnel
SSLVPN TunneL
192.168.1.0/24
教主VIP
飞K塔NGFW与ZTNA
F RTINET
教主VIP
乾颐堂
SWG配置Site2到Site3的VPNS
Next>
Cancel
>- ②、4①、②admin-
飞塔SASE
10.10.10.0/24
教主VIP
1.2
tunne】
172.16.1.0/24
（ port2）
202.100.1.0/24
port1）
.254
飞塔SAS
教主VIP
202.100.2.0/24
（portil
.254
.254
202.100.3.0124
.10
GigabitEthernetl
tunne10
（Loopbacko
3.3.3.3/24
10.10.20.0/24
飞塔SASE
329

## Page 330

6 SSLVPN与L2LVPN
塔SASE
swg
Q
$ Dashboard
+ Network
L Policy & Objects
A Security Profles
Q VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSL-VPN Settings
SSLVPN Clients
VPN Location Map
2 User & Authentication
今 WiFi Controller
System
• Security Fabric
區 Log & Report
Comments
众
Network
IP Version
Remote Gateway
Interface
Local Gateway
Mode Confg
NAT Traversal
Keepalive Frequency
Dead Peer Detection
DPDretrycount
DPDretryinteral
Forward Error Correction
由 Advanced..
Authentication
Method
Pre-shared Key
Version
Mode
Phase 1 Proposal
Encryption
+ Add
DES
Diffe-Hellman Group
Key Lifetime （seconds）
SWG配置Site2到Site3的VPNS
Site2-Site3-VPN
Comments
M0/255
IPv6
StaticIP Address
202.100.3.10
團 port1
Enable
10
Disable
Disable On ldle
On Demand
20
Egress 口 Ingress 口
Pre-shared Key
Cisc0123
Aggressive
Main （ID protection）
Authentication
MD5
32日 31 日 30 口29口 28 0 27
口21 20 19
口 18 017 口16
口15口14四5
口2 01
86400
onal Information
© API Preview
② IPsec VPNs
E IPsec VPN Cookbook Recipes C
2 Configuring an IPsec VPN Connection C
SSLVPN POOL
172.16.100.0/24
192.168.1.0121 00ng
2202.100.1.0/24
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
>- ②•4①、②admin•
乾颐堂
— -19.10.18.0/24
.254
202.100.3.0/24
.10
GigabitEthexnet！
Loopbacka
133.3.3/24
202-00204雷
002 172.16.1.0124
10.10.20.0/24
-.|
F:RTINET
v7.24
OK
Cancel
330

## Page 331

6
SSLVPN与L2LVPN
飞塔SASE
SWG配置Site2到Site3的VPNS
Gswg
$ Dashboard
+ Network
』 Policy & Objects
A Security Profiles
口 VPN
Overlay Controller VPN
IPsec Tunnels
IPsec Wizard
IPsec Tunnel Template
SSL-VPN Portals
SSL-VPN Settings
SSL-VPN Clients
VPN Location Map
2 User & Authentication
=Q
NewVPN Tunnel
Diffie-Hellman Group
nal Information|
口1501455
⑧ APIPreview
Key Lifetime （seconds）
LocallD
86400
D IPsec VPNS
众
XAUTH
Type
Disabled
号 IPsec VPN Cookbook Recipes C
Phase 2 Selectors
Name
Site2-Site3-VPN
e Confguring an IPsec VPN Connection C
Local Address
0.0.0.0/0.0.0.0
Remote Address
0.0.0.0/0.0.0.0
SSLVPN POOL
172.16.100.0/24
New Phase 2
Name
Site2-Site3-VPN
Comments
Comments
点击展开
Local Address
Subnet
0.0.0.0/0.0.0.0
• Security Fabric
L Log & Report
Remote Address
Subnet
口 Advanced..
Phase 2 Proposal
+ Add
Encryption
DES
Enable Replay Detection E
Enable Perfect Forward Secrecy （PFS）
0.0.0.0/0.0.0.0
192.168.1.0/24 （port3
2202.100.1.0/24
Authentication
MD5
Difhe-Hellman Group
Local Port
Protocol
口 32
口 31 口 30 口 29 口 28 Q.27
口21
口20 口19 口 18 日 17の 16
口 15.
口
14M50201
AIl T
All
All
口
飞塔SASE
Auto-negotiate
Autokey Keep Alive
Key Lifetime
Seconds
Seconds
3600
教主VIP
FIRTINET
v7.2.4
OK
Cancel
教主VIP
飞K塔NGFW与ZTNA
>- ②•4①、②admin•
飞塔SASE
乾颐堂
— -10:10.10-0/24
.254
202 10020120
.10
GigabitEthernet1
Loopbacka
3.3.3.3/24
002 172.16.1.0124
10.10.20.0/24
-.I
331

## Page 332

6
SSLVPN与L2LVPN
swg
Dacnboara
+ Network
Interfaces
DNS
IPAM
SD-WAN
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Objects
Multicast
Diagnostics
L Policy & Objects
A Security Profles
口 VPN
2 User & Authentication
今 WiFi Controller
¢ System
• Security Fabric
區 Log& Report
SWG配置Site2-Site3-VPN隧道接口的IP地址
=
Q
Edit Interface
A. Site2-Site3-VPN
众
Name
Alias
Type
② Tunnel Interface
圖 port1
VRFID
Role ⑧
• Dedicated Management Port
Address
Addressing mode
Remote IP/Netmask
10.10.20.2
10.10.20.1/24
Administrative Access
IPv4
G HTTPS
口 EMG-Access
O FTM
口 Speed Test
Q DHCP Server
Security mode O
Traffic Shaping
Outbound shaping profle C
Micrallanenns
暂时还不能UP
直到配置了策略
口 HTTP⑧
口 SSH
口 RADIUS Accounting
习 PING
口 SNMP
口 SecurityFabric
Connection ®
飞塔SASE
间swg
Status
心Down
Additional Information
⑧ API Preview
SSLVPN POOL
172.16.100.0/24
— -19.10.18.0/24
2202.100.1.0/24
飞塔SASE
.254
202.100.3.0/24
.10
GigabitEthernet1
Commente
/A01255
Status
• Enabled© Disabled
教主VIP，
Loopbacka
133.3.3/24
OK
Cance
教主VIP
飞K塔NGFW与ZTNA
>- ②、4①、② admin、
乾颐堂
200.0020電
002 172.16.1.0124
10.10.20.0/24
-.I
FRTINET
v7.24
332

## Page 333

6
SSLVPN与L2LVPN
swg
2 Dashboard
+ Network
Interfaces
DNS
IPAM
Policy Routes
RIP
OSPF
BGP.
Routing Objects
Multicast
Diagnostics
』 Policy & Objects
A Security Profles
口 VPN
2 User & Authentication
今 WiFi Controller
# System
0 Security Fabric
區 Log & Report
SWG配置Site2-Site3-VPN隧道接口的IP地址
众
=Q
FortiGate VM64
團團
團團
24
+ Create New-|
• Edit
@ Delete
ite Interface
Search
Name=
Type =
Members=
日 3 802.3ad Aggregate ①
# fortilink
# 802.3adAggregate
日 圖 Physical Interface ④
團 port1
團 Physical Interface
DHCP Clientss
DHCP Ranges一
10.255.1.2-10,255.1.254
教主VIP
飞K塔NGFW与ZTNA
>-②、4①、② admin•
乾颐堂
jroup By Type-
Ref. =
• ② Site2-Site1-VPN
⋯• P Site2-Site3-VPN
團 port21
日 z Software Switch ①
Inside-LAN
日 A Tunnel Interface ①
回 NAT interface （naf.root）
② Tunnel Interface
② Tunnel Interface
圖 Physical Interface
Software Switch
② Tunnel Interface
圖 port3
團 port4
Dedicated to FortiSwitch
202.100.2.10/255.255.255.0
10.10.10.2/255.255，.255.255
10.10.20.2/255.255.255.255
172.16.1.10/255.255.255.0
10.1.2.10/255.255.255.0
0.0.0.0/0.0.0.0
教主VIP
Administrative Access =
PING
SecurityFabric Connection
PING
HTTPS
SSH
HTTP.
EMG:Access
PING
PING
PING
PING
FIRTInET
v7.24
② Security Rating Issues
2
。
飞塔SA
教主VIP
⑦|Updated: 11:31:332、
333

## Page 334

6
SSLVPN与L2LVPN
swg
$ Dashboard
+ Network
L Policy &Objects
Firewall Policy
IPv4 DoS Policy
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
A Security Profles
Q VPN
8 User & Authentication
今 WiFi Controller
¢ System
• Security Fabric
區 Log & Report
SWG配置防火墙策略放行Site2到Site3的流量
=Q
New Policy
onanormaon
食
Name⑧
permit-site2-site3-traffic
Incoming Interface
port2
配置完策略后
⑨ API Preview
隧道就会UP
Outgoing Interface
② Site2-Site3-VPN
Source
② Online Guides
• Relevant Documentation C
N Video Tutorials C
Consolidated Policy Configuration C
Destination
Hot Questions at FortiAnswers
ceaue
Service
. always
Q ALL
172.16.108.0/24
< ACCEPT O DENY
— -19:10.18.0/24
Firewall/Network Options
NAT
Protocol Options
ior default
2202.100.1.0/24
Security Profles
Antivirus
Web Filter
DNSFilter
Application Control
IPS
File Filter
SSL Inspection
no-inspection
飞塔SASE
飞塔SASE
.254
202 1002012
.10
GigabitEthexnet！
Logging Options
Log Allowed Traffic
Generate Logs when Session Starts
Capture Packets
Security Events
All Sassions
Comments| Write acomment...
教主VIP，
Loopbacka
3.3.3.3/24
OK
Cancel
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
>- ②、4①、②admin•
202.188.2.0/24
002 172.16.1.0124
10.10.20.0/24
1./
334

## Page 335

6
SSLVPN与L2LVPN
乾颐堂
回swg
2 Dashboard
+ Network
B Policy & Objects
Firewall Policy
TFV4 DO3FONG
Addresses
Internet Service Database
Services
Schedules
Virtual IPs
IP Pools
Protocol Options
Traffic Shaping
A Security Profles
Q VPN
2 User & Authentication
分 WiFi Controller
炒 System
• Security Fabric
區 Log & Report
FIRTINET
SWG配置防火墙策略放行Site3到Site2的流量
New Policy
ional Information
permit-site3-site2-traffic
众
Incoming Interface
配置完策略后
隧道就会UP
© API Preview
Outgoing Interface
port2
Source
白 all
Destination
日all
Schedule
Service
5 always
⑦ ALL
Action
ACCEPT O DENY
Firewall/Network Options
NAT
② 10
Protocol Options
T default
Security Profles
Aptvius
Web Filter
DNS Filter
Application Control O
IPS
File Filter
SSL Inspection
no-inspection
丞塔SASE
Logging Options
Log Allowed Traffic
Generate Logs when Session Starts O
Capture Packets
Security Events
All Sessions
Cammanto
| Write acomment..
③ Online Guides
• Relevant Documentation C
• Video Tutorials C
W Consolidated Policy Confguration C
• Hot Ouestions at FortiAnswers
SSLVPN POOL
172.16.108.0/24
— -19:10.18.0/24
2202.100.1.0/24
飞塔SASE
.254
202 1002012
.10
GigabitEthexnet！
教主VIP，
Loopbacka
3.3.3.3/24
OK
教主VIP
飞K塔NGFW与ZTNA
>- ②、4①、② admin、
202.188.2.0/24
1D
002 172.16.1.0124
10.10.20.0/24
-.I
335

## Page 336

6
SSLVPN与L2LVPN
回 swg
+ Network
山 Policy & Objects 2
Firewall Policy
IPv4 DoS Policy
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
2 User & Authentication
今 WiFi Controller
¢ System
• Security Fabric
區 Log& Report
入
FIRTINET
教主VIP
飞K塔NGFW与ZTNA
SWG配置防火墙策略放行Site1到Site3的流量
=Q
New Policy
N
>- ②•4①、Q admin•
nal Information
众
Name
Incoming Interface
permit-site1-site3-traffic
② Site2-Site1-VPN
© API Preview
Outgoing Interface
② Site2-Site3-VPN
口 all
② Online Guides
Relevant Documentation C
W Video Tutorials C
W Consolidated Policy Confguration C
J.
Destination
口 all
Schedule
Service
R always
⑦ ALL
• Hot Questions at FortiAnswers
Is Web Cache on the GUI？
vAnswers
• O Votes
SeeMoreC
Action
V ACCEPT
⑦ DENY
• 524V
教主VIP
Firewall/Network Options
NAT
10
Protocol Options
ROT default
Security Pcofles
Antivirus
） Web Filter
DNS Filter
Application Control O
IPS
File Filter
SSL Inspection
no-inspection
丞塔SASE
飞塔SASE
Logging Options
Log Allowed Traffic
Generate Logs when Session Starts O
Capture Packets
Security Events
All Sessions
教主VIP
Comments
Write acomment..
$724
OK
Cancel
飞塔SA&E
教主VIP
乾颐堂
336

## Page 337

6
SSLVPN与L2LVPN
G swg
.Dasnboara
+ Network
L Policy & Objects 2
Firewall Policy
IPv4 DoS Policy
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
卒 System
• Security Fabric
區 Log & Report
FRTINET
教主VIP
飞K塔NGFW与ZTNA
SWG配置防火墙策略放行Site3到Site1的流量
EQ
N
>- ②、4①、② admin-
New Policy
Honal Information
Name.
Incoming Interface
permit-site3-site1-traffic
② Site2-Site3-VPN
© API Preview
Outgoing Interface
© Site2-Site1-VPN|
source
日 all
② Online Guides|
• Relevant Documentation C
Video Tutorials C
• Consolidated Policy Confguration C
Destination
日 all
Schedule
Service
口 always
贝 ALL
电 Hot Questions at FortiAnswers
Is Web Cache onthe GUI？
• 1 Answers
See More C
Action
V ACCEPT
⑦ DENY
Firewall/Network Options
NAT
Protocol Options
SegityPromles
AntrVirus
-Web Filter
DNS Filter
Application Control O
IPS
File Filter
SSL Inspection
no-inspection
飞塔SASE
Logging Options
Log Allowed Traffic
Generate Logs when Session Starts O
Capture Packets
X1。
Security Events
All Sessions
飞塔SASE
教主VIP
Comments| writeacomment..
Anannn
v7.24
OK
Cancel
飞塔SASE
教主VIP
乾颐堂
337

## Page 338

6 SSLVPN与L2LVPN
飞塔SASE
=Q
向swB
$ Dashboard
+ Network
L Policy & Objects
Firewall Policy
TPV4 D03 POIIGV
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
2 User & Authentication
今 WiFi Controller
¢ System
• SecurityFabric
區 Log & Report
+ Create New
• Edit
Name
permit-inside-to-internet-traffic
vpn_Site2-Site1-VPN.local_O
vpn_Site2-Site1-VPN_remote_O
permit-site2-site3-traffic
permit-site3-site2-traffic
Delinlt-slte 1-sltes-ualno
permit-site3-site1-traffic
Implicit Deny
<塔SASE
教主VIP
飞塔SASE
⑧ Updated: 11:36:08 C
乾颐堂
SWG防火墻最终策略
自 Delete
Q Policy lookup
searc
From
source
Destination
Schedule
s4 Inside-LAN
圖 port2
圖 port2
port1
口 all
口 all
5 always
2 Site2-Site1-VPN
r Site2-Site1-VPN_local
② Site2-Site1-VPN
port2
• Site2-Site1-VPN_remote
圖 port2
② Site2-Site3-VPN
1 all
r Site2-Site1-VPN_remote
富 Site2-Site1-VPNJocal
1 all
5 always
always
always
② Site2-Site3-VPN
port2
口 all
② Site2-Site1-VPN
② Site2-Site3-VPN 1 all
② Site2-Site3-VPN ② Site2-Site1-VPN 口 all
口 all
回 all
5 always
⑦ always
口 all
always
口 any
口 any
1 all
回 all
always
Service
⑦ ALL
Z ALL
⑦ ALL
⑦ ALL
⑦ ALL
⑦ ALL
⑦ ALL
⑦ ALL
教主VIP
飞K塔NGFW与ZTNA
>-⑦• 41、②admin•
日 Export-
Interface Pair View
By Sequence
Action
NAT
Security Profles
L0g
Byte：
•ACCER！
⑦ Enabled
no-inspection
⑦ AIl
8.83 kB
• ACCEPT
• Disabled
no-inspection
ACCEPT
• Disabled
no-inspection
D UTM
D UTM
0B
1.32kB
< ACCEPT
• Disabled
AIl
0B
＜ ACCEPT
x DisaDled
no-inspection
S AIl
< ACCEPT
a Disabled
no-inspection 0 AIl
< ACCEPT ® Disabledsst no-inspection O All
0B
0B
0B
② DENY
x Disabled
0B
教主VIP 飞塔SASE
教主VIP
飞塔SASE
FSRTINET
v7.24
① Security Rating Issues
338

## Page 339

6
SSLVPN与L2LVPN
飞塔SASE
回swg
Dashboard
f Network（
DNS
SD-WAN
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Objects
Multicast
Diagnostics
L Policy & Objects
A Security Profles
口 VPN
• User & Authentication
分 WiFi Controller
¢ System
0 Security Fabric
區 Log& Report
RouterID
Areas
+Create New
AreaID
0.0.0.0
教主VIP
飞K塔NGFW与ZTNA
• Edit
Type
Regular
+Create New
• Edit
自 Delete
Network
172:16.1.0/24
10.10.10.0/24
10.10.20.0/24
Area
0.0.0.0
0.0.0.0
0.0.0.0
+Create New
• Edit
色 Delete
Name
Interfaces
Cost
Apply ToIP
Noresults
SWG OSPF添加网络宣告
色 Delete
Authentication
None
N
10.10.10.1
= View Routing Monitor
⑧ API Preview
>_ Eaitin CLl
② Online Guides
Relevant Documentation C
• Video Tutorials C
• Hot Questions at FortiAnswers
D Join the Discussion C
Authentication
荅SASE
Passive
飞塔SASE
ASE
>- ②、4①、②admin•
飞塔SAS
教主VIP
飞塔SASE
Summary Addresses
FRTINET
v7.24
教主VIP
Apply
教主VIP
乾颐堂
339

## Page 340

6
SSLVPN与L2LVPN
G swg
m Dashboard
+ Network
Interfaces
DNS
IPAM
SD-WAN
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Objects
Diagnostics
L Policy & Objects
A Security Profles
Q VPN
2 User & Authentication
今 WiFi Controller
章System
• Security Fabric
區 Log& Report
FRTINET
SWG 调整Site2-Site3-VPN隧道口的MTU
=Q
OSPF
N
Add Interface
2.2.2.2
Name
Interface
Site2-Site3-Tunnel
2 Site2-Site3-VPN
+ Create New
AreaID
Authentication
0.0.0.0
Regular
one
Prefx length
Cost ⑧
Priority
Authentication
BFD
Networktype
Passiveinterface
DRflfer out
None
Plain-Text
ospfauth：：message-digest
Global
Enable Disable
Broadcast
•
Networks
MTUignore
MTU
0
1400
+Create New
Edit
自 Delete
Area
Timers
17246.1
10.10.0/24
10.20.0/24
0.0.0.0
0.0.0.0
0.0.0.0
seconds
Interfaces
> Edit @ Delete
Name
Interfaces
Cost
Apply To IP
搭SASE
Passive
Hello interval
Dead interval
Transmit delay
Retransmit interval
Gracefulrestart synctimeout
40
seconds
Jseconds
seconds
OK
Cancel
mman Aanrpsced
教主VIP
教主VIP
教主VIP
飞K塔NGFW与ZTNA
>- ②•0①、②admin•
飞塔SAS
教主VIP
飞塔SASE
乾颐堂
340

## Page 341

6
SSLVPN与L2LVPN
向swg
$ Dashboard
+ Network
Interfaces
DNS
IPAM
SD-WAN
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Obiects
Mlticast
Diagnostics
』 Policy & Objects
• Security Profiles
口 VPN
& User & Authentication
今 WiFi Controller
#System
• Security Fabric
匹 Log & Report
F RTINET
v7.2.4
SWG 调整Site2-Site3-VPN隧道口的MTU
OSPF
Router ID
2.2.2.2
Areas
+Create New
• Edit
Area ID
Type
0.0.0.0
Regular
Networks
+Create New
• Edit
Netwos
172-1610/24
10.10:10.0/24
10.10.20.0/24
nt0n2000
+Create New
• Edit
Name
10.10.10.1
= View Routing Monitor
色 Delete
Additional Information
Authentication
None
© API Preview
>- Edit in CLI
② Online Guides
9 Relevant Documentation C
Video Tutorials C
教主VIP
會 Delete
曲 Hot Ouestions at FortiAncwers
◎ Join the Discussion C
Area
0.0.0.0
0.0.0.0
0.0.0.0
色 Delete
SASE
Interfaces
Cost
Site2-Site3-Tunnel P Site2-Site3-VPN 0
FApplyTolP.
AnyIP
Authentication
Passive
None.
• Disabled
飞塔SASE
summamy Addresses
教主VIP
先Apply
Apply
教主VIP
教主VIP
飞塔NGFW与ZTNA
乾颐堂
>- ②、4①、② admin、
飞塔SASE
341

## Page 342

6
SSLVPN与L2LVPN
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
SWG 查看OSPF邻居，路由，并测试
2 Dashboard
+ Network
DNS
CLI Console （1）.
swg # get router info ospf neighbor
OSPF process 0，
VRF 0：
Neighbor ID
Pri
1.1.1.1
State
Fu11/-
3.3.3.3
Dead Time
00:00:36
00:00:32
Address
10.10.10.1
10.10.20.1
Interface
Site2-Site1-VPN（tun-id:202.100.1.19）
clvez-sutes-/Ncun-10.262.100.s.1m
9 admin
K塔SASE
Routing Objects
Multicast
Diagnostics
L Policy & Objects
凸 Security Profles
口 VPN
2o User & Authentication
今 WiFi Controller
# System
• Security Fabr
區 Log & Rep
swg # get router info ospf route
OSPF process 0：
Codes: C- connected, D- Discard, 0- 0SPF, IA - 0SPF inter area
OSPF NSSA external type 1, N2 - OSPF NSSA external type 2
E1 - OSPF external type 1, E2 - OSPF external type 2
3.3.3.3/32 ［101］ via 10.10.20.1, Sitez-Site3-VPN, Area 0.0.0.0
10.10.10.1/32 ［100］ via 19.10.18.1, Site2-Site1-VPN, Area 0.0.0.0
10.10.10.2/32 ［100］ is directly connected, Site2-Sitel-VPN，
Area 0.9.9.0
18.10.20.0/24 ［1100］ via 10.10.28.1, Sitez-Site3-VPN.
Area 9.9.9.0
10.10.20.2/32 ［100］ is directly connected, Site2-Site3-VPN, Area 0.0.0.0
172.16.1.0/24 ［1］ is directly connected，
port2, Area 0.9.9.0
192.168.1.0/24 ［101］ via 10.10.10.1，
Site2-Site1-VPN, Area 0.0.0.0
swg # execute ping 3.3.3.3
PING 3.3.3.3 （3.3.3.3）： 56 data bytes
64 bytes from 3.3.3.3: icmp_seq=0 tt1=255 time=1.1 ms
64 bytes from 3.3.3.3: icmp_seq=1 tt1=255 time=1.8 ms
64 bytes from 3.3.3.3：
icmp_seq=2 tt1=255
time=0.9 ms
^C
--- 3.3.3.3 ping statistics ---
3 packets transmitted, 3 packets received, 0% packet loss
round-trip min/avg/max = 0.9/1.0/1.1 ms
swg#|
飞塔SASE
FERTINET
342

## Page 343

6
SSLVPN与L2LVPN
塔SASE
教主VIP
飞K塔NGFW与ZTNA
《塔SASE
15 Updated: 11:23:27 2
乾颐堂
FGT1 查看Site3的OSPF路由，并测试
9 admin
+ Network
B Policy & Objects
CLI Console （1）
fgt1 # get router info ospf route
OSPF process 0：
Codes: C- connected，
D - Discard, 0 - OSPF, IA - OSPF inter area
N1 - OSe- NSSA external typeT.
N2 - OSPF NSSA external
type 2
E1 - OSPF external type 1.
E2 - OSPF external
type 2
1o 3.3.3.3/32 ［201） via 10.10.10.2. Site1-Sitez-vPN，
Area 0.0.0.0
10.10.10.1/32 【100］ is directly connected, Site1-Site2-VPN，
Area 0.0.0.0
10.10.18.2/32 ［100］ via 18.10.10.2, Site1-Site2-VPN, Area 0.9.9.0
10.19.28.8/24 ［1200］ via 10.10.18.2, Site1-Sitez-VPN.
Area 0.0.0.0
18.10.28.2/32 ［109］ via 10.10.10.2, Site1-Sitez-VPN, Area 8.8.8.8
172.16.1.0/24 【101］ via 10.10.10.2.
Sitel-Site2-VPN, Area 0.0.0.0
192.168.1.8/24 ［1］ is directly connected，
port3, Area 0.0.0.0
fgti #0
ity Profles
國 管理员：C:WWindows\system32lcmd.exe
C：\Users\Administrator）ping 3.3.3.3
字节的数据：
3.3.3.3
的回复：字节=32 时间=1me TTL=253
經址億品包接收=4。丢失=0（0% 丢失）。
最短：ims，最卡： 2ms.
C：\Users\Administrator）.
⑦ AIl
no-inspection|
S AII|
no-inspection|
◎ AIl
no-inspection 0 AIl|
no-inspection 0 All|
no-inspection D UTM
no-inspection U UTM
no-inspection 0 All|
IP Pools
Protocol Options
Traffic Shaping
凸 Security Profiles
口 VPN|
2 User &Authentication
S WiFi Controller
¢System
• Security Fabrid
區 Log & Repo
粉
343

## Page 344

6
• SSLVPN与L2LVPN
Site1_DMZ_DC（管理PC）测试访问Site2,Site3网络
c 管理员：C:/Windows\system32）cmd.exe
C： \Users\Administrator>ping 172. 16.1.1
正在 Ping
172.16.1.1 具有 32 字节的数据：
来自
172.16.1.1 的回复：字节=32 时间=1ms
TTL=62
172.16.1.1 的回复：字节=32 时间=1ms
TTL=62
172.16.1.1
的回复：字节=32 时间=1ms
TTL=62
172.16.11 的克ing 统计信息
数据包：已发送=生，
忌接收：4，丢失=0（0%丢失），
往返行程的估计时间（以毫秒为单位）：
最短 = 1ms，最长=1ms，平均= 1ms
P：\Users\Administrator/ping 3.3.3.3
正在 Ping
3.3.3.3 具有 32 字节的数据：
来目
3.
3.
3.3 的回复：子节=32 时=1ms TTL=253
来自
3.3.
3.
3
的回复：字节=32 时间=1ms TTL=253
来目
3.
3.
3.
3
的回复：字节=32
时间=1ms TTL=253
米日
3.3.
3.3
的回复：字节=32
时间=1ms TTL=253
3.3.3.3
的 Ping 统计信息：
数据包：已发送=4，
已接收=4，丢失=0（0%丢失），
在返何程的估计时间（以毫秒为单位）：
最短 = Ims，最长 = Ims，平均= 1ms
C：\Users\Administrator〉
教主VIP
飞K塔NGFW与ZTNA
口
×
乾颐堂
344

## Page 345

6
SSLVPN与L2LVPN
<
教主VIP
飞塔NGFW与ZTNA
Firefox
Google
Chrome
Forticlient
3. 3.系間.門耕
𤍣中厦号泡接收
=4，丢失=0（0%丢失），
= 2ms，
C：\UsersVAdmin>ping 172.16.1.1
自自自目
16.1.
LTE
1回
𣊭邊：
172.16.1.1的Ping 統计信息：
=62
=62
1=62
TTL=62
丢失=0（0%丢失），
3ms，
C：\Users\Admin）ping 192. 168.1.1
正在
Ping
来来来.
192.
192. 168.1.1
的回复：
192.168.
来目
192 168
1的回复：
字节的数据：
间=2ms
TTL=63
TTL=63
间=2m
TTL=63
时间三ims
TTL=63
192.168.1.1 的 Ping 统计信息
岂接收 = 4，丢失=0（0% 丢失），
王返行程的估计时间（以毫秒为单位）
= 2ms，
= Ims
C：\Users\Admin〉
% salesuser
泌 ZERO TRUST TELEMETRY
S REMOTE ACCESS
◎ ZTNA DESTINATION
C MALWARE PROTECTION
SS VULNERABILITY SCAN.
1 报告
日 About
VPN 连接 qyt-sslvpn
IP 地址 172.16.100.1
用户名 salesuser
连接时间 00:16:26
接收字节数 2.96KB
发送字节数 45.11 KB
中断连接
念
SASE
乾颐堂
salesuser拨号测试访问Site1,Site2,Site3网络
可
MobaXterm
回收站
c1 命今提示符
C： \Users\Admin>ping 3.3.3.3
正在
Ping
3.3.
FortiClient - Zero Trust Fabric Agent
文件 帮助
VPN 已连接
345

## Page 346

乾颐堂
第7部分.FSSO
教主
P TS塔SASE
教主VIPK塔SASE
飞塔SASE
教主VIP 飞塔SASE
教主W
飞塔SASE
教主VIP
飞塔SASE

## Page 347

FSSO
飞塔SASE
向 fgt1
Dashboard
+ Network
』 Policy & Objects
A Security Profiles
口 VPN
2 User & Authentication
~ WiFi Controller
o System
. Security Fabric
匹 Log& Report
Forward Traffic
Local Traffic
Sniffer Traffic
ZTNA Traffic
System Events 2
Security Events
Reports
Log Settings
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FGT1 查看SSLVPN日志（UP）
=
Q
Summary
Logs
+ Q Search
Date/Time
2023/05/21 09:36:42
2023/05/21 09:36:41
2023/05/21 09:36:41
2023/05/21 09:36:34
2023/05/21 09:36:34
2023/05/21 09:36:34
2023/05/21 09:35:56
2023/05/21 09:33:18
2023/05/2109:33:18
2028/05/2109:33:18
2023/05/21 09:25:56
2023/05/21 09:15:56
2023/05/21 09:05:56
2023/05/2109:02:25
2023/05/21 09:02:25
2023/05/21 09:02:25
2023/05/21 09:02:16
2023/05/2109:02:11
2023/05/2109:01:13
2023/05/21 09:01:13
2023/05/21 09:01:13
2023/05/2109:01:13
Action
tunnel-up
tunnel-up
ss -new-con
ssl-new-con
ssl-new-con
ssl-exit-error
tunnel-stats
tunnel-down
tunnel-down
tunnel-down
tunnel-stats
tunnel-stats
tunnel-stats
tunnel-up
tunnel-up
ssl-new-con！
ssl-newcon
ssl-exit-error
negotiate
negotiate
tunnel-up
phase2-up
Message
SSL tunnel established
SSL tunnel established
SSL new connection
SSL new connection
SSL new connection
SSLexiterror
IPsec tunnel statistics
SSL tunnel shutdown
SSL tunnel shutdown
SSL tunnel shutdown
IPsectunnel statistics
IPsec tunnel statistics
IPsectunnel statistics
SSL tunnel established
SSL tunnel established
SSL new connection
SSL new connection
SSLexit error
negotiate IPsec phase 2
progress IPsec phase 2
IPsec connection status change
IPsec phase 2 status change
VPN Tunnel
S2SVPN
S2SVPN
S2SVPN
S2SVPN
S2SVPN
S2SVPN
S2SVPN
S2SVPN
HA: Primary
>-②、4、② admin、
Q
口 VPN Events，
@ Disk、
Log Details
Destination Host
口 Action
Action
Reason
口 Security
Level
口 Event
Remote IP
Tunnel4D
Tuhnellp
TunnerType
Message
口 Other
⑤ 1hour、日 Details
N/A
tunnel-up
tunnelestablished
Information
202.100.100.101
307,687,111
172.16.100.1
ssl-tunnel
SSL tunnel established
Log event original timestamp
Timezone
LogID
Type
Sub Type
1684630945473809700
+0800
0101039947
event
关注ID
FERTIET
0% 41
347

## Page 348

FSSO
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FGT1查看SSLVPN日志（UP）
教主VIP
date=2023-05-21 time=09:02:25 eventtime=1684630945473809731
tz="+0800"logid=90101039947" type="event'subtype="vpn"
Alevel="information" vd="root" logdesc="SSL VPN tunnel up"
action="tunnel-up" tunneltype="ssl-tunnel" tunnelid=307687111
aTOuP=SAIeSCrOUp OSt TOst-*N/A"reason-*unnel establshed主
remip=202.100.100.101 tunnelip=172.16.100.1 user="salesuser"
msg="SSL tunnel established"
飞塔SASE
教主VIP
飞塔SASE
教主VIP
飞塔SASE
教主VIP
348

## Page 349

FSSO
塔SASE
回 fgt1
$2 Dashboard
+ Network
B Policy & Objects
A Security Profles
旦 VPN
S User & Authentication
今 WiFiController
0 System
• Security Fabric
E Log & Report
Forward Traffic
Local Traffic
Sniffer Traffic
ZTNA Traffic
System Events
Security Events
Reports
Log Settings
FGT1 查看SSLVPN日志（DOWN）
=Q
Summary
Logs
C）
+ Q Search
Dacc/Time
Level
Action
Status
Message
2023/05/21 09:36:42
cunncluo
SSL tunnel established
2023/05/21 09:36:41
tunnel-up
SSLtunnelestablished
2023/05/21 09:36:41
ssl-new-con
SSL new connection
2023/05/21 09:36:34
sSl-new-con
SSL new connection
2023/05/21 09:36:34
2023/05/21 09:36:34
ssl-new-con
ssl-exit-error
SSL new connection
SSLexit error
2023/05/2109:35:56
tunnel-stats
IPsectunnel statistics
2023/05/2109:33:18
2023/05/2109:33:18
2023/05/2109:33:18
2023/05/2109:25:56
tunnel-down
SSL tunnel shutdown
SSL tunnel shutdown
tunnel-down
SSL tunnel shutdown
tunnel-stats
IPsectunnel statistics
2023/05/2109:15:56
2023/05/21 09:05:56
tunnel-stats
IPsectunnel statistics
tunnel-stats
IPsectunnel statistics
2023/05/21 09:02:25
tunnel-up
SSL tunnelestablished
2023/05/21 09:02:25
tunnel-up
SSL tunnel established
2023/05/21 09:02:25
2023/05/21 09:02:16
2023/05/21 09:02:11
ssl-new-con
ssl-new-con
ssl-exit-error
SSL new connection
SSL new connection
SSLexit error
2023/05/21 09:01:13
success
negotiate
negotiate IPsec phase 2
2023/05/21 09:01:13
negotiate
2023/05/21 09:01:13
2023/05/21 09:01:13
VPN Tunnel
S2SVPN
S2SVPN
S2SVPN
S2SVPN
S2SVPN
tunnel-up
phase2-up
progress IPsec phase 2
IPsec connection status change
IPsec phase 2.status change
S2SVPN
S2SVPN
S2SVPN
教主VIP
飞塔NGFW与ZTNA
乾颐堂
HA: Primary〉-⑧、 、②admin、
Q
口 VPN Events -
@ Disk、
Log Details
Sent Bytes
口 Action
Action
Reason
口 Security
Level
口 Event
Remote IP
Tunne/1D
TunnellR
Tunnel Type
Message
曰 Other
Q 1hour、田 Details
35.16 kB
tunnel-down
User requested termination of servi
Intarmatinn
202.100.100.101
307.687.111
172.16.100.1
ssl-tunnel
SSL tunnel shutdown
Log event original timestamp
1684632798404718000
Timezone
+0800
Log ID
0101039948
Type
event
Sub Type
关注ID
FERTINET
v7.2.4
0% 41
349

## Page 350

FSSO
SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
教主V
FGT1 查看SSLVPN日志（DOWN）*
date=2023-05-21 time=09:33:18 eventtime=1684632798404718137
tZ="+0800" logid=0101039948" type="event" subtype="vpn"
Slevel="information" vd="root" logdesc="SSL VPN tunnel down"
action="tunnel-down" tunneltype="ssl-tunnel" tunnelid=307687111
remip=202.100.100.101 tunnelip=172.16.100.1 user="salesuser"
group="SalesGroup" dst host="N/A" reason="User requested 说
教主VIP
termination of service" duration=1853 sentbyte=35156 rcvdbyte=111799
msg="SSL tunnel shutdown"
飞塔SA
教主VIP
教主VIP
教主VIP 飞塔SASE
教主VIP
飞塔SASE
350

## Page 351

FSSO
y
教主VIP
飞塔NGFW与ZTNA
禁用其他syslog
只是发送特定ID的
syslog
发送到位于
192.168.1.201（FAC）
的syslog服务器
FGT1 配置SYSLOG
config log syslogd flter
set forward-traffic disable
set local-traffic disable
set multicast-traffic disable
set sniffer-traffic disable
set ztna-traffic disable
set anomaly disable
set voip disable
config free-style
edit 1
set category event
set flter "（logid 0101039947） or （logid 0101039948）"
neXt
end
end
config log syslogd setting
set status enable
set server "192.168.1.201"
end
飞塔SASE
飞塔SASE
记得使用
CLI刷配置
教主VIP
飞塔SASE
乾颐堂
351

## Page 352

FSSO
塔SASE
FAC 激活SYSLOG SSO
EE FortiAuthenticator VM FAC-VMTM22004423
System
Edit SSO Configuration
Authentication
v successtully saved s50 connguration.
Fortinet SSO Methods.
5 SSO
2
General
Portal Services
SAML Authentication
Windows Event Log Sources
RADIUS Accounting Sources
Syslog Sources
FortiGate
Listening port：
• Enable encryption
• Enable authentication
Secret key：
Login expiry：
Extend user session beyond logoff by：
• Enable NTLM authentication
Fine-grained Controls
SSO Users
SSO Groups
Domain Groupings
FortiGate Filtering
IP Filtering Rules
Tiered Architecture
Monitor
Certificate Management
Logging
8000 S2
••••••
48062
f seconds （0-3600）
Fortinet Single Sign-On （FSSO）
Maximum concurrent user sessions：
［Confgure Per User/Group］
Log level：
Error
Warning
Debug
［Configure Log Filter］
• Enable Windows event log polling （e.g. domain controllers/Exchange servers）
• Enable FortiNAC SSO
• Enable RADIUS Accounting SSO clients
•O Enable Syslog SSO Configure syslog sources，
先提交，再回来点
2 Allow TLS encryption
Enable FortiClient SSO Mobility Agent Service
• Enable hierarchical FSSO tiering
• Enable DC/TS Agent Clients
• Restrict auto-discovered domain controllers to configured Windows event log sources and remote LDAP servers
• Enable Windows Active Directory workstation IP verifcation
• Disable NTLMv1 in client authentication to Windows AD server
Disable SMB1 in client connection to Windows AD server
User Group Membership
Group cache mode：
Passive
Active
Group cache item lifetime：
480 minutes （30-10080）
clearcachey
0Do not use cached groups and always load groups from server for the following SSO sources：
• Windows event log polling
• RADIUS Accounting SSO
• syslog SSO
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
admin、
教主VIP
此处容易出现直接配置
syslog source但是没有
激活syslog SSO的情况
飞塔SAS|
教主VP
352

## Page 353

FSSO
飞塔SASE
EH日 FortiAuthenticator VM FAC-VMTM22004423
System
4 +Create New
血 Delete
Authentication
Fortinet SSO Methods（
0X1500 syslog sources
& SSO
General
Portal Services
SAMLAuthentication
Windows Event Log Sources
RADIUS Accounting Sources
3 ISyslog Sources
Fine-grained Controls
SSO Users
SSO Groups
Domain Groupings
FortiGate Filtering
IP Filtering Rules
K诺SASE
教主VIP
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FAC 配置Syslog Source
苓SASE
• Edit
D
③
admin、
Syslog Sources
Matching Rules
教主VIP
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP 飞塔SASE
353

## Page 354

FSSO
飞塔SASE
FAC 配置Syslog Source
塔SASE
H FortiAuthenticator VM FAC-VMTM22004423
System
Create New Syslog Source
Authentication
Name：
Fortinet SSO Methods
IP address：
5 SSO
Matching rule：
General X/
SSO user type：
Portal Services
SAMLAuthentication
/ Windows Event Log Sources
RADIUS Accounting Sources
Syslog Sources
Fine-grained Controls
SSO Users
SSO Groups
Domain Groupings
FortiGate Filtering
IP Filtering Rules
Tiered Architecture
Monitor
SASE
Certificate Management
Logging
FGT1-SSLVPN|
192:168.1.10
［Please Select］v
◎ External
• Local users ⑦
◎ Remote users ⑧ QYTANGAD （dc2019.qytang.com）v
Strip off prefx or suffx from username if any
• Use a different attribute when searching user in the remote LDAP server （other than the username attribute in the remote LDAP server confg）
• Use prefix or suffx in username as domain （other than the remote LDAP server domain）
Cancel
教主VIP
飞塔NGFW与ZTNA
粉
教主VIP
飞塔SASE
教主VIP
飞塔SASE
教主VIP
飞塔SASE
乾颐堂
• ③ admin、
飞塔SASE
教主VIP
354

## Page 355

FSSO
飞塔SASE
區 Create New Syslog Matching Rule —Mozilla Firefox
凸
一 916 https://fac.qytang.com/admin/fsae/ssoparserule/add/？_to_ field=id&_popup=1
Create New Syslog Matching Rule
Name：
Description：
Mode：
syslog-match-rule
Key-value pairs
s-Om values
Fields To Extract
Trigger：
Auth Type Indlicators
Logon：
Lundaten
Logoff：
Username field：
Client IPv4 feld：
Client IPv6 feld：
Group feld：
Group list separator：
action-"tunnel-up*
ac0ons tunne.down
user="［f:usemamej"
tunnelip=（f:client._ipl｝
e.g.， Framed-IPv6-Address-ff:client_ipv6］）.
group-"（t:group）"
Test Rule
Test the matching rule above by entering a sample log line to parse below：.
date-2023-05-21 time-09:02:25 eventtime-1684630945473809731 tz-"+0800"logid-"0101039947"type-"event”
subtype= vpn" level="information"vd="root" logdesce"SSL VPN tunnel up" action="tunnel-up" tunneltype='ssi-tunnel™
tunnelid=307687111 remip=202.100.100.101 tunnelip=172.16.100.1 user= salesuser group= SalesGroup dst host= N/A|
reason-"tunnel established" msg-"SSL tunnel establishedy）
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FAC 配置Syslog Source
此处逗留太
久容易超时
Match！|
Test Ro
Authentication Type
Username
Client IP address
Client IPv6 address
Group
Logon
salesuser
172.16.100.1
SalesGroup
oK
action="tunnel-up"
action="tunnel-down"
user="｛iusername｝｝
tunnelip=｛：client_Ip｝
group="｛igroup｝"
严重注意
此处有空格
date=2023-05-21 time=09:02:25
eventtime=1684630945473809731
tz="+0800" logid="0101039947"
type="event" subtype="vpn"
level="information" vd="root"
logdesc="SSL VPN tunnel up"
action="tunnel-up" tunneltype="ss/-
tunnel" tunnelid=307687111
remip=202.100.100.101
tunnelp=172.16.100.1 user="salesuser"
group="SalesGroup" dst host="N/A"
reason="tupnel established"
msg="SSt tunnel established"
Close
355

## Page 356

FSSO
s塔SASE
FAC 配置Syslog Source
塔SASE
EH FortiAuthenticator VM FAC-VMTM22004423
System
Create New Syslog Source
Authentication
Name：
Fortinet SSO Methods
IPaddress：
B SSO
Matching rule：
General
SSO user type：
Portal Services/
SAML Authentication
Windows Event Log Sources
5
RADIUS Accounting Sources
Syslog Sources
Fine-grained Controls
SSO Users
SSO Groups
Domain Groupings
FortiGate Filtering
IP Filtering Rules
Tiered Architecture
Monitor
Certificate Management
YSASE.
Logging
FGT1-SSLVPN
192.168.1.10
syslog-match-rulev
• External 0
匹配出来的用户和组，就
是如下数据库的账户
◎ Remote users ① QYTANGAD （dc2019.qytang.com）v
• Strip off prefix or suffx from username if any
• Use a different attribute when searching user in the remote LDAP server （other than the username attribute in the remote LDAP server config）
• Use prefx or suffx in username as domain （other than the remote LDAP server domain）
OK
cance
教主VIP
飞K塔NGFW与ZTNA
教主VIP
飞塔SASE
教主VIP
飞塔SASE
飞塔SASE
教主VIP
乾颐堂
D ③ admin-
飞塔SASE
教主VIP
356

## Page 357

FSSO
飞塔SASE
日H FortiAuthenticator VM FAC-VMTM22004423
System
+ Create New Delete Edit
Authentication
Q The syslog source "FGT1-SSLVPNwas added successfiully.
Fortinet SSO Methods
口
& SSO
General, X/
FGT1-SSLVPN
Portal Services
oo svsog sources
SAML Authentication
Windows Event Log Sources
RADIUS Accounting Sources
Syslog Sources
Fine-grained Controls
SSO Users
SSO Groups
Domain Groupings
FortiGate Filtering
IP Filtering Rules
Tiered Architecture
Monitor
YSASE
Certificate Management
Logging
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
FAC 配置Syslog Source
塔SASE
？ admin、
Syslog Sources
Matching Rules
IP Addrecs
192.168.1.10
Matching Kule
syslog-match-rule
教主VIP
教主VIP 飞塔SASE
教主VIP 飞塔SASE
||P
教主VIP 飞塔SASE|
357

## Page 358

FSSO
飞塔SASE|
FAC 测试SSO
EHE FortiAuthenticator VM FAC-VMTM22004423
System
• Refresh 0 Export
C• Logoff AII
Authentication
Logon Time
Update Time
Fortinet SSO Methods
Monitor （1
G SSO
Domains
4 Sat May 20 19:05:2.. Sat May 20 19:05:27 ..
SSO Sessions
Windows Event Log Sources
FortiGates
1 SSO session
DC/TS Agents
NTLM Statistics
S Authentication
Certificate Management
Logging
（ Logoff Selected 2 Update Groups
Workstation
IP Address
Domain Grouping
172.16.100.1
172.16.100.1
DEFAULT
飞塔SASE
重新拨号
SSLVPN测试
教主VIP
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
教主VIP
教主VP
乾颐堂
Domain
QYTANG.COM
Username
SALESUSER
Source
Syslog
③
admin、
TU
Group
N=SALESUSER,OU=SALES,DC=Q'
ANG.DC=COM+CN=SALESGROUI
OU=SALES, DC=QYTANG, DC=COM-
CN=WSERS,CN=BUILTIN,DC=QYTA
NG.DC=COM+CN=DOMAIN USERS
CN=USERS,DC=QYTANG,DC=COM
把日志的用户和组，
映射到域的用户和组
飞塔SASE
飞塔SASE
358

## Page 359

FSSO
塔SASE
FAC 激活SSO认证
H FortiAuthenticator VM FAC-VMTM22004423
System
Authentication
Fortinet SSO Methods
& SSO
General
Portal Services
SAML Authentication
Windows Event Log Sources
RADIUS Accounting Sources
Syslog Sources
Fine-grained Controls
SSO Users
SSO Groups
Domain Groupings
FortiGate Filtering
IP Filtering Rules
Tiered Architecture
Monitor
Certificate Management
Logging
Edit SSO Confguration
FortiGate
Listening port：
• Enable encryption
• Enable authentication
Secret key：
Login expiry：
Extend user session beyond logoff by：
• Enable NTLM authentication
8000 62
•eeeee.eeoa
qytangccies
480 C minutes
O f seconds （0-3600）
Fortinet Single Sign-On （FSSO）
Maximum concurrent user sessions：
［Configure Per User/Group］
Log level：
Error
Warning
Debug
［Configure Log Filter］
• Enable Windows event log polling （e.g. domain controllers/Exchange servers）
• Enable FortiNAC SSO
• Enable RADIUS Accounting SSO clients
• Enable Syslog SSO［Configure syslog sources］
• Allow TLS encryption
O Enable FortiClient SSO Mobility Agent Service
2 Enable hierarchical FSSO tiering
• Enable DC/TS Agent Clients
• Restrict auto-discovered domain controllers to configured Windows event log sources and remote LDAP servers
• Enable Windows Active Directory workstation IP verifcation
• Disable NTLMv1 in client authentication to Windows AD server
0 Disable SMB1 in client connection to Windows AD server
User Group Membership
Group cache mode：
Passive
Active
Group cache item lifetime：
480 ^| minutes （30-10080）
D Do not use cached groups and always load groups from server for the following SSO sources
• Windows event log polling
• RADIUS Accounting SSO
• Syslog SSO
• FortiClient SSO Mobility Agent
教主VIP
飞K塔NGFW与ZTNA
苓SASE
乾颐堂
D③ admin、
飞塔SASE
教主VIP
教主VIP
飞塔SASE
359

## Page 360

FSSO
教主
飞塔SASE
向swg
=Q
¢2 Dashboard
「+ Create New
+ Network
山 Policy & Objects
凸 Security Profiles
旦 VPN
S User & Authentication
今 WiFi Controller
0 System
0 Security Fabric
Physical Topology
Logical Topology
Security Rating
Automation
Fabric Connectors
External Connectors
2
Asset Identity Center
Log&Report
YSASE
教主VIP
飞塔NGFW与ZTNA
SWG 连接FAC提供的FSSO
SASE
②Edit
|血 Delete
教主
>-③、、②admin、
飞塔SASE
教主VIP
Noresults
教主VIP 飞塔SASE
教主VIP 飞塔SASE
EERTIET
v7.2.4
教主VIP飞塔SASE
乾颐堂
360

