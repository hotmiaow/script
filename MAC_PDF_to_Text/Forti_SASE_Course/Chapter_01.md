# Module 1: Forti SASE Course

# Extracted Text from Forti_SASE.pdf

## Page 1

SASE
乾颐堂
Defend
SASE
Connect
（B
教主VIP，聊点高级的！
主讲人：现任明教教主
北京乾颐堂网络实验室出品

## Page 2

dd
血
4
SASE理论介绍
部署与初始化
HA
ZTNA
SAML
SSLVPN与L2LVPN
FSSO
SWG
乾颐堂

## Page 3

乾颐堂
第1部分. SASE理论介绍

## Page 4

SASE理论介绍
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
飞塔SASE
教主VIP
Cisco •
Broadcom
ibass
Versa會
ABILTYTO EXECUTE
Forcepoint
生VP
NICHE PLAYERS
COMPLETENESS OF VISION
•Nelskope
• McAfee Enterprise
• Forcepoint （Bitglass）
iSASE
教主VIP
VISIONARIES
As of February 2022
© Gartner, Inc
教主VIP
教主VIP
飞塔SASE
乾颐堂
SASE 2022
CHAL:ENGERS
LEADERS
X塔SASE
淡
Palo Alto Networks
•
飞塔SASE
4

## Page 5

ISASE理论介绍
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP
网络结构的变化
飞塔SASE
Historic traffic flows led to the age of the single，
onspremise security stack
飞塔SASE
教主VIP
Internet
经典的网络流
• TRAFFIC-
Anternal 80%
Internet 20%
维护的安全堆栈
TRAFFIC
Internal 80%
Internet 20%
教主VIP
Security Stack
周
YBranch offices
•MPLS
< VPN）
飞塔SASE
老
Data center HQ
Roaming/mobile
乾颐堂
5

## Page 6

］SASE理论介绍
塔SASE
教主VIP
飞塔NGFW与ZTNA
网络结构的变化
水塔SASE
Changes in the types of traffic, origins, and destinations
navewnverted the trattic model
飞塔SASE
Internet
1aas
Private cloud
疫情也让远程
办公成为日常
云时代网络
流发生改变
saa-
FRAFFTC
Interral 20%
Internet 80%
围
Branch offices
Browsing
Bottleneck
TRAFFIC
Internal 20%
Internet 80%
＜（MPLS
VPN
2Problems：
• Costs
• Performance
• # Tools/vendors
• Integrations
•
Maintenance
飞塔SASE
Data center / HQ
Roaming/mobile
乾颐堂
6

## Page 7

］SASE理论介绍
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP
网络结构的变化
DIA直接互联网访问
飞塔SASE
A more modegg *direct internet access" approach
飞塔SASE
教主VIP
无边界
网络
Network：
Decentralized
网络：去中心化
securtyg P
Protect traffic from multiple
Iocations at the cloud edge
安全：在云边界的多
个位置保护流量
Internet / SaaS》）
SD WAN TDIA/DCA
T
5G
苔SASE
围
Branch offices
Data center / HQ
Roaming/mobile
乾颐堂
7

## Page 8

业务需求迫使企业网络架构发生变化
传统网络架构
Gartner
>
现代化网络架构
飞塔SASE
Network
Carrier
在多地域，分布式的数据中心部署安全基础设施会引发过高的采
购和运维成本，而且增加攻击面，因此网络与安全的IT 领导层将
更喜欢网络和安全的云交付模式（网络/安全即服己。实现较低的
：易复杂度和成本，并拥有更好的性能
•同物理位置的访问体验大相径庭
企业数据几乎都存在数据中心内
。 网络流量要回到集中点进行转发与处理
• 建立区域服务来优化网络性能和访问体验
• 直连到SaaS， IaaS， 和 企业自建的全球分布式数据中心
网络流量在边缘处快速转发和处理
© Fortinet Inc. All Rights Reserved.

## Page 9

什么是SASE
安全访问服务边缘Secure Access Service Edge（SASE）
提供融合了网络与安全即服务的能力，具体包括SD-
WAN, SWG（Security Web Gateway）， CASB（Cloud
Access Security Brokers）， FWaaS与零信任（ZTNA）。
SASE 使用场景包括分支办公室，远程办公与本地安全访
问，SASE 可以基于用户和设备的身份认证提供零信任服
务，实时内容检测，安全与合规策略。
网络即服务
安全即服务
到2024年，至少40% 的机构将制定明确的战
略来采用 SASE
客户要求WAN边界与网络安全的融合，
提供简单、可扩展、灵活、低延迟和无
处不在的安全能力
连接它
飞塔SASE
保护它
安全访问服务边界
<
Gartner.
Market Trends : How to Win as WAN Edge and Security Converge
Into the Secure Access Service Edge - 29 July 2019
Source：
Gartner
© Fortinet Inc. All Rights Reserved.

## Page 10

ISASE理论介绍
教主VIP
飞塔SASE
云原生安全服务
SASE
The typical first step to address these issues is to
combine cloud delivered security services
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
云交付的网络与安全服务
教主VIP
93%
of orgs agree that moving
security to the cloud has
increased efficiency
把安全迁移到云会增加效率
DNS
security
教主的思考：让非标准的
网络与安全变得标准，更
易于标准化的实施与维护
Secure
web
gateway
Firewall
76%
of orgs are looking
for multi-function cloud
security services
提供多功能的云安全服务
Cloud
/Access
Security
Broker
CASB.
教主的思考：有效解决多
安全产品整合困难问题
教主的思考：不要低估云
交付的“弹性”，其实非常适
合中小企业
10

## Page 11

SASE理论介绍
教主VIP 飞塔SASE
教主VIP 飞塔SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
SASE组成部分
Secure Access Service Edge （SASE）
SASE
安全访问服务边缘
SD-WAN
飞塔SASE
Sandbox
Core
SWG
FWaas
CASB
Recommended
Browser Isolation
WAF NAC
ZTNA
核心组件
教主VIP
NGAV/EDR
推荐组件
WLAN技术也许是唯—
存留的传统网络技术
Optional
WLAN
VPN
Security as a Service
Network as a Service
安全即服务
网络即服务
11

## Page 12

SASE理论介绍
教主VIP 飞塔SASE
教主VIP飞塔SASE
0office365
我
飞塔SASE
教主VIP
HQ
教主VIP
飞K塔NGFW与ZTNA
传统VPN设计
yorce
z0om
教主VIP
飞塔SASE
飞塔SASE
Remote Worker
熟主VIP
绕行中心访
问互联网
Avg
8 SaaS
Applications
教主VIP 飞塔SASE
飞塔SASE
Traditional Design: VPN
乾颐堂
12

## Page 13

SASE理论介绍
教主VIP 飞塔SASE
教主VIP飞塔SASE
飞塔SASE
教主VIP
Ha
0 office 365
教主VIP
飞K塔NGFW与ZTNA
FWaaS和SWG
zoom
飞塔SASE
sil yorce
教主VIP
Remote Worker
；塔SASE
SWG负责安
全上网
AVGF
8Saas
Applications
FWaas, sWG
FWaaS负责对公司内部
资源网络访问的控制
飞塔SASE
Secure Web Gateway
乾颐堂
13

## Page 14

ISASE理论介绍
$SASE
SOFTWARE DEFINED PERIMETER （SDP）
教主VIP
飞塔NGFW与ZTNA
乾颐堂
ZTNA
飞塔SASE
Zero Trust
Network Access
教主VIP
Fortinet的EMS
n office365
SDP
Gateway
4
SDP Controller
Fortinet的FortiGate
AAzure
SDP
Gateway
教主VIP
Off Corporate Network
ZTNA （Zero Trust Network Access）是一种网络安全模
型，它的基本原则是“不信任任何事物”。ZTNA模型中的
SDP （Software-Defined Perimeter） 是一个框架，可以
创建一种基于需要知道的网络模型（你要能知道才能访
问），仅允许已验证的用户和设备访问它们需要的网络资
源。
SDP Gateway 和 SDP Controller 是SDP模型的两个关键
组件：
- SDP Gateway：这是网络中的物理或虚拟设备，用于
控制设备到应用程序或服务的访问。它基于从SDP
Controller接收的策略来管理访问请求。
（SDP Controller：这是控制整个SDP系统的核心。它管
理并验证用户身份，确定用户可以访问的资源，并将这
些策略传递给SDP Gateway。SDP Controller通常会与
身份提供商（如Active Directory或LDAP）集成，以进
行用户身份验证。
简单来说，SDP Controller负责验证用户并决定他们可
以访问哪些资源，然后SDP Gateway负责执行这些策略，
确保只有验证过的用户才能访问他们被授权的资源。
14

## Page 15

SASE理论介绍
SASE访问私有云
光SWG
FWaaS
Advantage over Traditional VPN：
-Save on MPLS
-Lower Latency"
Secure Web Gateway
FWaaS
SDP
Gateway
1 office 365
Firewalling
AntiMalware
WebFiltering
IPS
防火墙
防病毒
Web过滤
IPS
Corporate Network
主VP
教主VIP
飞K塔NGFW与ZTNA
飞塔SASE
乾颐堂
教主VIP
飞塔SASE
有了ZTNA不
需要VPN即可
访问内部资源
SDP
Gateway
飞塔SASE
Remote
15

## Page 16

］SASE理论介绍
飞塔SASE
教主VIP
飞塔SASE
更加高效的连接客
户到云端服务，不
管是移动用户还是
在公司内部的用户
SASE Integration
教主VIP
飞塔NGFW与ZTNA
SD-WAN的作用
飞塔SASE
乾颐堂
教主VIP
0 Office 365
教主VIP
Secure Web Gateway /FWaaS
飞塔SASE
ado
教主VIP
SD-WAN是SASE解决方
案的核心组件，也是提供
网络即服务的关键组件
SD-WAN on Prem
SY
>
-FEC
-Packet Duplication
-Q0S
-WAN Opt
-Cache
SD-WAN的主要特性
On Net
16

## Page 17

SASE理论介绍
教主VIP 飞塔SASE
教主VIP
飞塔SASE
SASE Integration
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
安全策略一致性
塔SASE
乾颐堂
1 office 365
教主VIP
Secure Web Gate way /FWaas
ZTNA让客户不管在
公司内部与否，都拥
有一致的安全策略
User Policy
SD-WAN on Prem
ISASE
-FEC
-Packet Duplication
-Q0S
-WAN Qpt
-Cache
塔SASE
On Net

## Page 18

ISASE理论介绍
飞塔SASE
CASB
User Policy
塔SASE
笼
CASB
教主VIP
飞塔SA&
SWG/FWaaS
1 office 365
-Visibility
-Application Level
Control
-DLP
-Quar antine
教主
教主VIP
飞塔NGFW与ZTNA
乾颐堂
CASB（Cloud Access Security Broker）是一种安全技术，主要用于
保护企业的云服务。CASB可以在企业和云服务提供商之间提供一个
安全的中介，以便管理和执行安全策略。
以下是CASB的一些主要功能：
可见性：CASB能够提供对企业使用的云服务的深入可见性，包括哪
些服务正在使用，谁在使用它们，以及他们如何使用。
数据安全：CASB可以帮助保护在云中存储的敏感数据，通过数据加
密，数据丢失预防（DLP）策略，和其他机制来防止数据泄露。
威胁防护：CASB可以帮助识别和防止针对云服务的威胁，如恶意软
件和账户劫持。
合规性：CASB可以帮助企业满足各种合规性要求，通过提供详细的
审计和报告功能，以证明他们的云使用符合相关的法规和标准。
简单来说）CASB是一种帮助企业安全使用云服务的二具，它可以提
供可见性，数据安全，威胁防护和合规性管理。
教主的思考：我们公司也
是一个需要CASB的案例
18

## Page 19

SASE Detailed View
SASE View
Secure access service edge
（SASE） 交付多种能力，例如
SD-WAN, SWG, CASB，
FWaaS 和零信任（ZTNA） 等多
个关键能力
SASE 支持多分支机构、移动办
公，混合办公，本地安全访问
互联网场景
• Employees
• Contractors
•Partners
• Devices
• Distributed
Applications
• Remote
•Mobile
• Offices
•Edge
Entities Anywhere
不管实体在任意位置
Source: Gartner
741491 C
一致的网络和安全策略
Consistent Network and Security Policy
User/Device ldentity
Context
WAN Edge
Services
• SD-WAN
• WAN Optimization
• Quality of Service
• Routing
• SaaS Acceleration
• Content Delivery/
Caching
•etc.
网络
SASE Cloud Infrastructure
Security
Services Edge
• Secure Web Gateway
• CASB
• ZTNA/VPN
•FWaaS
• Remote Browser
Isolation
•Encryption/
Decryption
• etC.
安全
• Applications
• APls
•Data
• Devices
•SaaS
• laaS
• Data Center
• Branch
•Edge
Threat
Awareness
Sensitive Data
Awareness
Zero Trust Access
Consistent User Experience
ZTNA实现一致性的用户体验
Resources Everywhere
不管资源在任意位置

## Page 20

本地和远程用户的融合
飞塔SASE
教主VI
不
塔SASE
教主VIP
本地
NGFW
SD-WAN
教主VIP
致主VP
教主VIP
Single-vendor
SASE
简化
一致的安全
更好的用户体验
远程用户
云端提供安全
飞塔SASE
教主VIP
© Fortinet Inc. All Rights Reserved.
塔SASE
Single-vendor
SASE的好处
• 降低复杂性，消除多种产品
• 单一终端的高效操作
• 通过减少产品和供应商来节
省成本
飞塔SASE
教主VIP
20

## Page 21

FortiSASE：基于云平台的安全和网络能力
塔SASE
单一终端
远程用户
AI.ML驱动的FortiOS提供一致性的体验
CN
Google
互联网
SWG
FWaaS
Do
ZTNA
CASB
CASB
SaaS
SD-WAN
居家办公
Cloud-Delivered Security （SSE）
SD-WAN
aWS
公有云
-AAE
目雕
数据中心
Fortinet Single-Vendor SASE 方案
提供一致安全性的混合办公方式
卓越的用户体验和运维效率
商务模型从CAPEX切换为OPEX
© Fortinet Inc. All Rights Reserved.
21

## Page 22

乾颐堂
第2部分.部署与初始化
K塔SASE
教主
飞塔SASE
教主VIP 飞塔SASE
SASE
教主VIP
飞塔SASE

## Page 23

2
部署与初始化
飞塔SASE
1.EMS
2.ZTNA-Agent
教主VIF
3.Site1-FGT1
4.Site1-FGT2
5.Site2-SWG
6.Site1-FAC
教主VIP
教主V1
教主VIP
飞塔NGFW与ZTNA
恢复快照
飞塔SASE
乾颐堂
推荐快照v2
推荐快照V2
推荐快照v2［已经加载授权V2］
推荐快照v2［已经加载授权v2］
推荐快照v2
已经加载授权v2
关键点：版本为7.2.4
（其他版本都是坑，不管低还是高）
飞塔SASE
飞塔SASE
教主VP
23

## Page 24

2
部署与初始化
FAC
ASE
Active Directory
.201
.200
192.168.1.0/24
10t3
FGT1
教主VIP
10
port2
.10
porti
SASE
教主VIP
飞K塔NGFW与ZTNA
环境拓扑
MALWARE
.202
飞塔SASE
乾颐堂
202.100.1.0/24
.254
port3
FGT2
.200
.254
202.100.100.0/24
.240
EMS
教主VIP
飞塔SASE
教主VIP
1
SWG
.254
202.100.2.0/24
.10
port1
port3
ISASE
port4
10.1.2.0/24
.10
172.16.1.0/24
.201
ZINA Agent
ASE
飞塔
port2

## Page 25

2
部署与初始化
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
两个DNS
飞塔SASE
乾颐堂
Sitel
飞塔SASE
Internet
FAC
I-EMS
飞塔
教生VIP
AD
日
千
教主VP
飞塔SASE
FGT
ZTNA
Agent
教主VIP
飞塔S
Site2
KSWG

## Page 26

2
部署与初始化
飞塔SASE
Sitel
飞塔SASE
AD
Active Directory
教主VIP
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FAG
两个DNS
脂d~2019
圍 DESKTOP-FKQFFRD
emS
目fac
冒fgt1
冒fgt2
冒 site1
冒 site2
冒swg
主机（A）
主机（A）
主机（A）
主机（A）
主机（A）
主机（A）
主机（A）
主机（A）
主机（A）
192.168.1.200
10.1.1.2
202.100.100.200
192.168.1.201
192.168.1.10
192.168.1.11）
192.168.1.1
172.16.1.1
202.100.2.10
静态
2023/5/8 15:00:00
静态
静态
静态
静态
静态
静态
静态
FGT
教主VIP 飞塔SASE
教主VIP 飞塔SASE
飞塔SASE
教主VIP

## Page 27

2
部署与初始化
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
两个DNS
静态
静态
飞塔SASE
乾颐堂
*in2008
sitel
dc2019
ems
tgtl
目目目
sWg
築士VP
主机（A）
主机（A）
主机（A）
主机 （A）
主机（A）
主机（A）
主机 （A）
主机 （A）
主机（A）
飞塔SASE
202.100.1.201
202,100.100.240
202.100.1. 111
202. 100.1.200
202. 100. 100.200
202.100.1.10
202.100.1.200
202.100.2.10
172.16.1.1
Internet
1-EMS
ZTNA
Agent
教主VIP
教主VIP 飞塔SASE
Site2
LSWG

## Page 28

2
部署与初始化
教主VIP
教主VIP
日 collinsctk / QYT_NGINX
Public
<》 Code
82
Pull requests © Actions
田 Projects
飞塔SASE
Y main、
Y9 1 branch
◎Otags
collinsctk Update readme.md
面.idea
冒cfssl
html
static
Dockerfile
C docker-compose.yaml
口 ngrinx.conf
1日readme.md
server.crt
C
server.key
D wiki
Q Security
区 Insights
安 Settings
Go to file
Add file-
5bcbb80 2 weeks ago
init.
Update auto_cert.py
Initial commit
Initial commit
Update Dockerfile
Update docker-compose.yaml
init
Update readme.md
init
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
关于NGINX与证书
https://github.com/collinsctk/QYT_NGINX
塔SASE
飞塔SASE
<> Code 、
9 17 commits
2 weeks ago
2 weeks ago
2 weeks ago
2 weeks ago
2 weeks ago
2 weeks ago
SASE
2 weeks agd
2 weeks aao
2 weeks ago
2 weeks ago

## Page 29

2
部署与初始化
飞塔SASE
教主VIP
飞塔SASE
教主VIP
5
教主VIP
教主VIP
飞K塔NGFW与ZTNA
关于NGINX与证书
飞塔SASE
前期环境准备，关闭防火墙（firewalld）和selinux
• linux环境
• docker
• dodker-compose
•互联网
• openSS
• python3
执行脚本产生证书与秘钥
＃ 进入cfsSl目录
［root@localhost cfssl］# pwd
/QYT_NGINX/cfssL
＃ 客户输入域名，产生证书与秘钥文件
［root@localhost cfssl］# python3 auto_cert.py
请输入域名：www.qytang.com
明文证书文件：/root/QYT_NGINX/cfssL/server.pem
明文秘钥文件：/root/QYT_NGINX/cfSSL/server-key.pem
PKCS12加密打包后的文件：/root/QYT_NGINX/cfssL/www.qytang.com.p12
PKCS12加密密码为：Cisc0123
直接用docker-compose拉起镜像
#址/docker-compose.Vamlo的日來
Iroot@localhost QYT_NGINX］# pwd
＃ 构建镜像
＃ 拉起服务
［root@localhost QYT_NGINX］# docker-compose up -d
根证书介绍
＃ 粮证书（有效期20年）
>on_NGINX/CfSSU/ca.cer
# 根证书的秘钥
OYT_NGINX/cfssl/ca-key.pem
粉
乾颐堂
G
教主VIP
飞塔SASE
教主VIP飞塔SASE

## Page 30

2
部署与初始化
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
初始化密码
飞塔SASE
Loading
flatkc...
ok
Loading /rootfs.gz...ok
Decompressing Linux...
Booting the kernel.
Parsing
ELF...
done.
飞塔SASE
System is starting...
starting system Maintenance.•.
Serial number is FGUMEUSKXNREAK29
FortiGate-VM64 login: admin
admin/空密码
Password：
You are forced to change your password. Please
New Password：
Confirn Password：
We lcome！
input a
new password.
HARNING: File System Check Recommended! An unsafe reboot May have caused an inco
nsistency in the disk drive.
It is strongly recommended that you check the file system
consistency before pro
ceeding.
Please run'execute disk list’and then 'execute disk scan
〈ref#）'
Note:The device will reboot and scan the disk during
startup. This May
take up
to an hour.
ortiGate-UM64 #
飞塔SASE|
乾颐堂
30

## Page 31

2
部署与初始化
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FGT1配置接口
X
FortiGate-UM64 # config systen interface
FortiGate-VM64 （interface）# edit port1
FortiGate-UM64 （port1） # set mode static
FortiGate-VM64 （port1） # set ip 202.100.1.10 255.255.255.0
FortiGate-VM64 （port1） # next
FortiGate-VM64 （interface）# edit port3
FortiGate-VM64 （port3）
# set Mode
static
FortiGate-VM64 （port3） # set ip 192.168.1.10 255.255.255.0
FortiGate-VM64 （port3）#
set allowaccess
ping https ssh http fgfm
FortiGate-VM64 （port3）
# end
Fort iGate-UM64 #
config system interface
edit portl
set mode static
set ip 202.100.1.10 255.255.255:0
set allowaccess ping https ssh http fgfm
next
edit port3
set mode static
set ip 192.168.1.10 255.255.255.0
set allowaccess ping https ssh http fgfm ftm
next
end
飞塔SASE
教主VP
31

## Page 32

2
部署与初始化
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP
FortiGate-VM64 # config
router static
FortiGate-VM64 （static）# edit 1
new entry'1' added
FortiGate-VM64 （1） # set device port1
FortiGate-VM64 （1） # set dst 0.0.0.0 0.0.0.0
FortiGate-VM64 （1） # set gateway 202.100.1.254
FortiGate-UM64 （1） # end
The dest ination
is
set to 0.0.0.0/0 which means all IP addresses.
FortiGate-UM64
＃
config router static
edit 1
set gateway 202.100.1.254
set device portl
next
end
粉
飞塔SASE
教主VIP
乾颐堂
FGT1配置默认路由
飞塔SASE
飞塔SASE
32

## Page 33

2
部署与初始化
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
乾颐堂
FGT2配置接口
FortiGate-UM64 # config system interface
sortiGate-VM64 （interface）# edit port1
FortiGate-VM64 （port1） # set mode static
FortiGate-VM64 （port1） # set ip 202.100.1.11 255.255.255.0
FortiGate-VM64 （port1） # next
FortiGate-VM64 （interface）# edit port3
FortiGate-VM64 （port3）
# set mode static
FortiGate-VM64 （port3） # set ip 192.168.1.11 255.255.255.0
FortiGate-VM64 （port3） # set allowaccess ping https ssh http fgfm
FortiGate-VM64 （port3）
# end
Fort iGate-UM64
#
config system interface
edit portl
set mode static
set ip 202.100.1.11 255.255.255.0
set allowaccess ping https ssh http fgfm
next
edit port3
set mode static
set ip 192.168.1.11 255.255.255.0
set allowaccess ping https ssh http fgfm ftm
next>
end
飞塔SASE
教主VIP
33

## Page 34

2
部署与初始化
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP
FortiGate-VM64 # config
router
static
FortiGate-UM64（static）# edit 1
new entry'1’
added
FortiGate-VM64 （1） # set device port1
FortiGate-VM64 （1） # set dst 0.0.0.0 8.0.8.0
FortiGate-VM64 （1） # set gateway
202.100.1.254
FortiGate-UM64 （1） # end
TThe destination is set to 0.0.0.0/B which Means all IP addresses.
Fort iGate-UM64 #
config router static
edit 1
set gateway 202.100.1.254
set device portl
next
end
主VIP
飞塔SASE
教主VIP
乾颐堂
FGT2配置默认路由
飞塔SASE
飞塔SASE
34

## Page 35

2
部署与初始化
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
SWG配置接口和默认路由
FortiGate-VM64 # config system interface
FortiGate-UM64 （interface）# edit port1
FortiGate-VM64 （port1） # set mode
static
FortiGate-VM64 （port1） # set ip 202.100.2.10 255.255.255.0
FortiGate-UM64 （port1） # end
FortiGate-VM64 # config router static
Fort iGate-UM64
（static）# edit 1
new entry
'1'
added
FortiGate-VM64 （1） # set device port1
FortiGate-VM64 （1） # set dst 0.0.0. 8.0.0.0
Fort iGate-VM64 （1） # set gateway 202.100.2.254
Fort iGate-UM64 （1） #
end
The destination is set to 0.0.0.0/0 which Means all IP addresses.
config system interface
edit port1
set mode static
set ip 202.100.2.10 255.255.255.0
set allowaccess ping https ssh http fgfm
next
end
config router static
edit 1
set gateway 202.100.2.254
set device portl
next
end
乾颐堂
35

## Page 36

2
部署与初始化
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
登录
教主VIP
田 fgt1.qytang.com/login?redir-×
= fgt2.qytang.com/login?redir=×
个心Q
91 o https://tgt1.qytang.com/ogin?redir=%2F
由导入书签.國FGT1 国 FGT2 田 SWG G Site1_NGINX @ EMS EH FAC
现在只能登录FGT1, FGT2
如果证书问题，清除缓存
教主VIP飞塔SASE
<
*
乾颐堂
×
教主VIP
山
教主VIP
飞塔SASE
飞塔SASE
罪
••••••••
教主VIP
教主VIP 飞塔S
教主VIP -飞塔SASE）
P/
教主VIP塔SASE
36

## Page 37

2
部署与初始化
飞塔SASE
加载授权
教主VIP
FortiGate - FortiGate-VM64 x
E fgt2.qytang.com/login?redir：×
个-C
◎ & as https://fgt1.qytang.com/system/vm/license?viewOnly=
白导入节签.国FGT1
国FGT2 ④ SWG ④ Site1_NGINX @ EMS SIF FAC
FortiGate VM License
。
VM is not licensed or license is invalid for current VM configuration.
Upload anew license or reconfgure the VM.
教主VIP
How will you license this VM？
◎ Full License
• Evaluation License
Upload License File
Select fle
+ Upload
◎ 文件上传，
＞此电脑，桌面，FortiSASE Lic
組织：
新建文件夹
教主VIP，
名称
快速访问
•桌面
下载
西文档
正图片
FortiSASE Lic
Tchano
本地磁盘（C）
|FAC-VMTM22004423 （2）.I10
FAIVMSTM23000095（4）.lic
FGVM02TM22023965.lic
FGVM02TM22023966.lic
口 FGVM02TM22023967.lic
匀此电脑
呼网络
文件名（N）：FGVM02TM22023965.lic
FGVMO2TM22023965.lic
FGVM02TM22023966.lic
FGVMO2TM22023967.lic
OK
Cancel
x
~C 搜索"FortiSASE Lic'
睡•
口
修改日期
2023/4/14 18:07
LIC 文件
2023/4/17110:31
LIC 文件
2022X11/23 16:46 LIC 文件
2022/1/231646 LIC文件
22/11/23 16:46
LIC 文件
大小
18 KB
18 KB
9 KB
9 KB
教主VIP
所有文件
打开（O）
取消
教主VIP
飞塔NGFW与ZTNA
飞塔SASE
<
女
◎山=
飞塔SASE
Sitel FGT1
Sitel/FGT2
Sitel'SWG
飞塔SASE
教主VIP，
乾颐堂
37

## Page 38

乾颐堂
第3部分.HA
教主
IP 飞K塔SASE
教主VP飞塔SASE
飞塔SASE
教主VIP 飞塔SASE
教市VP
飞塔SASE
教主VIP
飞塔SASE

## Page 39

3
HA
飞塔SASE
教主VIP
HA active-passive cluster
Switch
多
Internal
三种工作模式
心多
多
FortiGate-100D
Cluster
飞塔SA
教主VIP
教主VIP
Interna
Network
HA virtual cluster
Engineering
Gruten
Pot2
620.ma2
• root Traffic
Eng vdm Traffc
Guiteh
SASE
Jnternet
教主VIP
飞塔SASE
乾颐堂
放主VIP
Exlemal
Poser
Internet
Internal
Network
教主VIP
飞塔NGFW与ZTNA
SASE
HA active-active cluster
pon
Switch
多
Exera
Fouter
FortiGate-100D
Cluster
Internet
39

## Page 40

3
HA
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
AS VSAA
教主VIP
教主VIP
Active-Passive
• 主设备接收和处理所
有的流量
•备份设备被动等待
飞塔SAS
以前的主设备
ActVe-Active
• 主设备接收所有流量
• 重定向一些流量到备
份设备
飞塔SASE
教主VP
HA心跳接口
虚拟MAC地址
新的主设备
飞塔SASE
教主VIP
40

