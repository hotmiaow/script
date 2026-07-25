# Module 2: Forti SASE Course

## Page 41

3
J HA
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
飞塔SASE
飞塔SASE
教主VIP
MAC:X
客户端
Virtual MAC: 09-01-01
Virtual MAC: 09-01-01
Physical MAC: 0b-a1-cO
1-SYN
HTTP Proxy
primary
2-SYN
3b - SYN/ACK
Physical MAC: 0b-a4-8c
secondary
1.dstMAC 09-01-01, SICMAC X, TCP SYN aport 80
2.dStMAC Ob-a4-8c, srcMAC Ob-a1-c0; FcP SYN dport 80
3a. dstMAC Y, srcMAC 0b-a4-8exTCP SYN dport 80
3b. dstMAC X, srcMAC 0b-a4-8c, TCP SYN ACK sport 80 （from HTTP proxy）
飞塔SASE
服务器
MAC:Y
3a- SYN
Physical MAC: 0b-a4-8e
飞塔SASE
教主VIP
乾颐堂
AA工作原理（1）
教主VIP
41

## Page 42

3
HA
飞塔SASE
AA工作原理（2）
教主VIP
教主VIP
CVirtual MAC: 09-01-01
Virual MAC: 09-01-01
Physical MAC:0b-a1-cO
4-ACK_
客户端一
5-ACK/
HTTP Proxy
primary
secondary
Physical MAC: 0b-a4-8c
教主VIP
4.dstMAC 09-01-01, srcMAC X, TCPACK dport 80
5.dstMAC 0b-a4-8c, SrcMAC Ob:a1-c0, TCP ACK dport 80
教主VIP
教主VIP
飞塔NGFW与ZTNA
飞塔SASE
豇颐堂
飞塔SASE
沙服务器
教主VIP 飞塔SASE
42

## Page 43

HA
教主VIP 飞塔SASE
教主VIP 飞塔SASE
客户端
教主VIP
飞K塔NGFW与ZTNA
飞塔SASE
教主VIP
乾颐堂
AA工作原理（3）
教主VIP
HTTP Proxy
primary
secondary
Virtual MAC: 09-01-03
Virtual MAC: 09-01-03
Physical MAC: 0b-a1-c2
6 - SYN/ACK
7-SYN/ACKY
8-ACK
Physical MAC: 0b-a4-8e
飞塔SASE
服务器
6. dstMAC 09-01-03, STCMAC Y, TCP SYN ACK sport 80
教主VIP
7. dstMAC 0b-a4-8e, srcMAC 0b-a1-c2, TCPSYN ACK sport 80
8. dstMAC Y, srcMAC 0b-a4-8e, TCR ACK dport 80
教主VIP
43

## Page 44

3
HA
飞塔SASE
教主VIP
飞塔SASE
教主VIP
非常类似思科的AA
需要支持VDOM，虚
拟化设备不支持
教主VIP
飞K塔NGFW与ZTNA
Virtual Cluster工作原理
飞塔SASE
nternal
Network
Engineering
Network
飞塔SASE
Port 2
Port 1
• root Traffic
Eng_vdm Traffic
Switch
Port 5
Port 6
Switch
Internet
Switch
Port 5
「FaATInET
Port 6
Switch
Router
教主VIP
Port 2
FGT_ha_2
Port 1
飞塔SASE
乾颐堂
44

## Page 45

3
HA
教主VIP
飞塔NGFW与ZTNA
HA的配置需求
飞塔SASE
进行HA配置，硬件和软件版本需满足如下要求
•防火墙硬件型号相同
飞塔SASE
•同型号硬件要求硬件版本，内存容量，CPU型号，硬盘容量等相同
• 相同的软件版本
•设备的所有接口不能工作在DHCP，PPPoE模式下。没有使用的接口IP地
址模式也需要选择为"自定义”
如果HA的两台FW存在上述不安致的情况，那么作备用的防火墙将会被
Shutdown（ Shutdown the box ! The system is halted！）
乾颐堂
45

## Page 46

3
HA
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
①
乾颐堂
教主VIP
连接状态的监控接口数量
教主VIP
这是HA运行时间
飞塔SASE
教主VIP
主设备选举规则
HA主设备选举比较顺序
教主V
多
有效接口数目
末
运行时间
高
优先级
$SASE
序列号
短
低
小
生VIP
飞塔SASE
飞塔SASE
教主VIP
SSASE
教去
成为主设备
教主
成为从设备
教主VIP 飞塔SASE
46

## Page 47

3 HA
教主VIP
飞塔NGFW与ZTNA
心跳接口和监控接口
飞塔SASE
心跳接口包含敏感的集群配置信息
1.必须有一个心跳接口，但为实现冗余推荐使用两个
2:FortiGate交换接口不能用于心跳接口
飞塔SASE
数。监控接口通常是处理高优先級流量的网络接日班主心
1. 不要把所有接口配置內监控接口
2. 不要监控心跳接口
3.可以监控 VLAN接口
Mode
Device priority 0
Active-Active
100
Cluster Settings
Group name
MGMT1
Change
Session pickup
Monitor interfaces
Heartbeat interfaces
监控接口
心跷按口
飞塔SASE
• Management Interface Reservation
• Unicast Heartbeat
教主VIP
乾颐堂
47

## Page 48

3
HA
教主VIP
教主VIP
飞塔SASE
回 Site1_FGT1
e2 Dashboard
+ Network
』 Policy & Objects
A Security Profles
口 VPN
2 User & Authentication
不
¢ System
Fabric Management
Settings
HA
Replacement Messages
Certifcates
• Security Fabric
區 Log & Report
教主VIP
FRTINET
教主VIP
飞K塔NGFW与ZTNA
FGT1配置HA
飞塔SASE
>-②•4•Qadmin、
High Availability
Mode
Device priority ⑧
Active-Passive
128
Cluster Settings
GroupID ⑧
Group name
Password
Session picku
vonitor intertacec
⑦
Heartbeat interfaces
aytang-Broup
qytang
port2
圖 port3
團 port4
• Management Interface Reservation
• Unicast Heartbeat
qytang
：X：
MP
飞塔SASE
tionalintormation
⑤APIPreview
>- Edit inCLI
品 High Availability
e Identifying the HA Cluster and Cluster Units C
5 FGSP （Session-Sync） Peer Setup C
roubleshoot an a -ormation
E Check HA Sync Status C
2 HA Active-Passive Cluster Setup C
2 HA Active-Active Cluster Setup C
• HA Virtual Cluster Setup L
教主VP，
（？ Online Guidex
号 Relevant Documentation C
W Video Tutorials C
Hot Questions at FortiAnswers
Does "ha-direct" affect SNMP？
wAnswerg
e • votes
• 703 Views
HAsync issues due to speed test
g Answerd
e O votes
See More ［
飞塔SASE~
飞塔SASE
oK
Cancel
教主VP
教主VIP
飞塔SASE
乾颐堂
48

## Page 49

3
HA
教主VIP
教主VIP
飞塔SASE
G FGVM02TM22023966
6 Dashboard
+ Network
L Policy & Objects
B Security Profiles
口 VPN
User & Authentication
WiFi Controller
System
Admin Profiles
Fabric Management
Settings
HA
SNMP
Replacement Messages
FortiGuard
Feature Visibility
Certificates
0 Security Fabric
區 Log & Report
1v
1
食
教主VIP
FERTINET
FGT2配置HA
=Q
High Availability
Mode
Device priority ®
Active-Passive
100
Cluster Settings
Group ID ⑦
Group name
Password
Session pickup
Monitor interfaces
qytang-group
qytang
0
圖 port1
圖 port2
圖 port3
×x
Heartbeat interfaces
圖 port4
• Management Interface Reservation
• Unicast Heartbeat
飞塔SASE
qytang
OK
Cancel
教主VIP
搭SASE
教主VIP
飞塔NGFW与ZTNA
飞塔SASE
ional Information
© API Preview
>_ Edit in CLI
品 High Availability
Identifying the HA Cluster and Cluster Units C
E FGSP （Session-Sync） Peer Setup C
日 Troubleshoot an HA Formation C
E Check HA Sync Status C
Cluster Setup
E HA Active-Passive Cluster Setup C
E HA Active-Active Cluster Setup C
Q HA Virtual Cluster Setup C
② Online Guides
e Relevant Documentation C
W Video Tutorials C
© FortiAnswers
◎ Join the Discussion （
教主VIP
飞塔SASE
乾颐堂
49

## Page 50

3
HA
飞塔SASE
教主VIP
教主VIP
FGVMO2TM22023965
# Dashboard
+ Network
』 Policy & Objects
A SecurityProfles
旦 VPN
2 User & Authentication
合 WiFi Controller
¢ System
Administrators
Admin Profiles
Fabric Management
Settings
HA
SNMP
Replacement Messages
FortiGuard
reauure VislDllley
Certificates
粉 Security Fabric
區 Log & Report
教主VIP
飞塔NGFW与ZTNA
1
3
1
查看HA状态
=
Q
=： FortiGate VM64
9 11 13 15 17 19 21 23
IIk！
6 8 101 14 16 18 20 22 24
FGVM02TM22023965 （Primary）
C Refresh & Edit
× Remove device from HA cluster
Status
Priority
Hostname
Serial No.
Role
◎ Synchronized
S Synchronized
128
100
FGVM02TM220 FGVM02TM22023965
FGVMO2TM220 FGVMO2TM22023966
Primary
Secondary
塔SASE|
HA: Primary〉-⑦、02、② admin•
飞塔SASE
System Uptime
25m29s
33m 37s
Sessions
25
3=
Throughput
153.00 kbps
23.00kbps
教主VIP
飞塔SASE
FERTINET
教主VIP 飞塔SASE
教主VIP，
飞塔SASE
◎
乾颐堂
50

## Page 51

3 HA
教主VIP
飞K塔NGFW与ZTNA
查看CLI查看HA配置
飞塔SASE
FGVMO2TM22023965 ＃ show system ha
show是查配置
config system ha
set group-name "qytang-group"
set mode a-p
set password ENC
yZ3UTYQypZqJqwCLbN890gHPft+OMSd4WinhrJXLYUZC1+rOnDvK2KVO5|WkQLm7k3
DAOEDQZpHqLSz99EuJxQzkGckt7xqLI23xWTWGY/s+XP/1b9Uj3Me8z8WZQeaAxzSC5J
KG2AwaNvOmYbpXIncDjcc/YxKpEcaKVVa6tMnoyAAnV1m3LN6mNSD+yhpLaz7/Yg==
set hbdev "port4"0
set session-pickup enable
set override disable
set monitor "port1" "port2""port3"
end
教主VIP
教主VIP
飞塔SASE
iSASE
乾颐堂
51

## Page 52

3 HA
教主VIP
飞K塔NGFW与ZTNA
y
查看CL查看HA状态
get是查状态
飞塔SASE
FGVM02TM22023965 # get system ha status
HA Health Status: OK
Model: FortiGate-VM64
Mode: HA A-P
Group:0
Debug:0
Cluster Uptime: 0 days 0:14:58
飞塔SASE
Cluster state change time: 2023-05-18 18:45:42
Primary selected using：
<2023/05/18 18:45:42> vcluster-1: FGVM02TM22023965 is selected as the primary because its uptime is larger than peer member FGVM02TM22023966.
<2023/05/18 18:35:06> vcluster-1: FGVM02TM22023965 is selected as the primary because it's the only member in the cluster.
ses_pickup: enable, ses_pickup_delay=disable
override: disable
Configuration Status：
FGVM02TM22023965（updated 2 seconds ago）： in-sync
FGVM02TM22023966（updated 5 seconds ago）： in-sync
System Usage stats：
FGVMO2TM22023965（updated 2 seconds ago）：
sessions=54, average-cpu-user/nice/system/idle=0%/0%/1%/99%，memory=41%
FGVMO2TM22023966（updated 5 seconds ago）：
sessions=48, average-cpu-user/nice/system/idle =1%/0%/0%/99%， memory=40%
~~~忽略部分输出~~~
Primary : FGVM02TM22023965, FGVM02TM22023965, HA cluster index = 1
Secondary :FGVMO2TM22023966, FGVMO2TM22023966, HA cluster index =0
number of vcluster: 1
飞塔SASE
vcluster 1:work 169.254.0.2
Primary: FGVMO2TM22023965, HA operating index = 0
Secondary: FGVM02TM22023966, HA operating index = 1
教主VIP
乾颐堂
52

## Page 53

3
HA
飞塔SASE
教主VIP
教主VIP
向 FGVMO2TM22023965
82 Dashboard
+ Network
山 Policy & Objects
• Security Profles
回 VPN
User & Authentication
今 WiFi Controller
System
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
2
0 Security Fabric
區 Log & Report
1
1
食
FRTINET
教主VIP
飞塔NGFW与ZTNA
加载根证书
塔SASE
=
Q
>- ②、4②、Q admin、
+ Create/Import、
Certificate
Generate CSR
白 Delete
© View Details
& Download
Sparch
Q
Subject令
CA Certificate
Remote Certificate
CRL
isted
C= US, ST = California, L = Sunnyvale,O = Fortine..
C = US, ST = California, L = Sunnyvale, O = Fortine..
口 Local Certificate
國 Fortinet_Factory
C = US, ST = California, L = Sunnyvale, O= Fortine..
耶 Fortinet_Factory_Backup
C= US, ST = California, L = Sunnyvale, O = Fortine..
面 Fortinet_GUI_Server
C=US, ST = California, L = Sunnyvale, O= Fortine..
面 Fortinet_SSL
C= US, ST = California, L = Sunnyvale, O = Fortine..
國 Fortinet_SSL_DSA1024
C.=US, ST = California, L=Sunnyvale, O = Fortine..
r Fortinet_SSL_DSA2048
C= US, ST = California, L = Sunnyvale, O= Fortine..
r Fortinet_SSL_ECDSA256
C=US, ST = California, L = Sunnyvale, O= Fortine..
面 Fortinet_SSL_ECDSA384
C =US, ST = California, L = Sunnyvale, O= Fortine..
面 Fortinet_SSL_ECDSA521
C = US, ST = California, L = Sunnyvale, O = Fortine..
國 Fortinet_SSL_ED448
C= US, ST = California, LF Sunnyvale, O= Fortine..
國 Fortinet SSL_ED25519
C=US, ST = California, L= Sunnyvale, O = Fortine..
面 Fortinet SSL_RSA1024
C=US,ST = Califoria,L= Sunnyvale, O = Fortine..
同 Fortinet_SSL_RSA2048
C=US,ST= California,L= Sunnyvale,O= Fortine..
國 Fortinet_SSL_RSA4096
C=US,ST= California. L =Sunnyvale. O = Fortine..
扇 Fortinet_Win
C-US,ST=California,L =Sunnyvale. O= *Fortin..
口 Remote CA Certificate ④
國 Fortinet_CA
冢 Fortinet,CA_Backup
同 Fortinot Sub CA
C= US, ST = California, L = Sunnyvale, O= Fortine..
C= US, ST = California, L = Sunnyvale, O = Fortine.
C-IIS ST-Californis 1-Sinniaalo D-Foctino
0 Security Rating Issues
Comments=
Issuers
Expires令
St：
This is the default CA certificate the SSL Inspectio.. Fortinet
This is the default CA certificate the SSL Inspectio..
Fortinet
2033/05/18 18:17:46
2032/10/1401:22:28
This certifcate is embedded in the hardware at th..
Fortinet
2056/01/18 19:14:07
This certificate is embedded in the hardware at th...
Forinet y
| 2038/01/18 19:14:07
This is the default CA certificate the SSL Inspectio.. Fortinet
2025/08/2018:18:15
This certifcate is embedded in the hardware at th..
Fortinet
2025/08/20 18:17:46
This certifcate is embedded in the hardware at th...
Fortinet
2025/08/20 18:17:49
This certificate is embedded in the hardware at th..
Fortinet
2025/08/20 18:17:49
This certificate is embedded in the hardware at th..
Fortinet
2025/08/20 18:17:49
This certificate is embedded in the hardware at th..
Fortinet
2025/08/20 18:17:49
This certificate is embedded in the hardware at th...
Fortinet
2025/08/20 18:17:49
This certificate is embedded in the hardware at th.
Fortinet
2025/08/20 18:17:49
This certificate is embedded in the hardware atth...
Fortinet
2025/08/20 18:17:49
This certificate is embedded in the hardware at th...
Fortinet
2025/08/2018:17:46
This certifcate is embedded inthe hardware at th..
Fortinet
2025/08/20 18:17:47
This certificate is embedded in the hardware at th..
Fortinet
2025/08/20 18:17:48
Thiscertifcateisembeddedin the frmware andi..
DigiCert Inc
2022/11/04 16:59:59
Fortinet
Fortinet
Fortinot
2056/05/27 13:27:39
2038/01/1914:34:39
mnaAn/0718M8.32，
0% 2
；塔SASE
乾颐堂
53

## Page 54

3
HA
教主VIP
教主VIP
飞塔SASE
向 FGVMO2TM22023965
82 Dashboard
+ Network
L Policy &Objects
• Security Profiles
回 VPN
S User & Authentication
今 WiFi Controller
System
Administrators
Admin Profles
FabricManagement
Settings
HA
SNMP
Replacement Messages
FortiGuard
Feature Visibility
Certificates
0 Security Fabric
區 Log & Report
1~
1
食
FRTINET
教主VIP
飞塔NGFW与ZTNA
乾颐堂
=Q
NameX
口 Local CACertin
罰 Fortinet_CA_SSL
呵 Fortinet_CA_Untrusted
口 Local Certifhicate 15
而 Fortinet_Factory
呵 Fortinet_ Factory_Backu
罰 Fortinet_GUI_Server
面 Fortinet_SSL
同 Fortinet_SSL_DSA1024
F Fortinet SSL_ DSA2048
呵 Fortinet_SSL_ECDSA251
國 Fortinet_SSL_ECDSA38/
司 Fortinet_SSL_ECDSA52
19 Fortinet SSL_ED448|
写 Fortinet_SSL_ED25519
國 Fortinet SSL_RSA1024
面 Fortinet_SSL_RSA2048
區 Fortinet.SSL.RSA4096，
國 Fortinet Wi
日 Remote CA Certfieate
國 Fortine
$t,GA_Backup
sot Cub CA
Security Rating Issues
加载根证书
Import CA Certificate
Type
Upload
Online SCEP
+ Upload
OK
◎ 文件上传
个 •～个口，此电脑，本地磁盘（C；）>share
组织•
新建文件夹
快速访问
口桌面
下载
购文档
一图片
1 FortiSASE_Lic
Snare
本地磁盘（Ci）
•此电脑
•网络
名称
E ems.qytang.com
wfac.qytang.com
配 fac.qytang.com
E3 fgt1.qytang.com
a IdP
a IdP-New
n ms root
La qytang root］
site1.qytang.com
配 swg.qytang.com
文件名（N）：qytang root
塔SASE
>- ②、4②、Q admin、
飞塔SASE
修改日期
2023/5/14 18:06
2023/5/16 9:32
2023/5/15 9:00
2023/5/14 18:06
2023/5/15 9:10
2023/5/15 9:55
2023/5/14 9:59
2023/5/14 10:52
2023/5/14 15:19
2022561442
Cancel
~已 搜寮
类型
Personal Information Exchange
安全证书
Personal intormation exchange
Personal Information Exchange
安全证书
安全证书
安全证书
安全证书
Personal Information Eychange A
Personal Infomation Exchange
大小
3 KB
2 KB
3 KB
3KB
2 KB
2 KB
2 KB
2K8
3 KB
3 KB
所有文件
打开（O）
安全证书（cer）
存粹的证书
Personal Information Exchange（p12）
证书+密钥
飞塔SASI
取消
教主VP
54

## Page 55

3
HA
教主VIP
教主VIP
飞塔SASE
向 FGVMO2TM22023965
# Dashboard
+ Network
L Policy & Objects
A Security Profiles
口 VPN
2 User & Authentication
今 WiFiController
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
Certificates
粉 Security Fabric
山 Log & Report
1
<
1
食
教主VIP
FIRTINET
加载根证书
= Q
+ Create/Import、
Import CA Certificate
Name
Type
日LocalCACoyie@Upload
Online SCEP
+ qytang_root.cer
國 Fortinet.CA_SSL
E Fortinet_CA_Untrusted
口 Local Certificate 15
F Fortinet_Factory
呵 Fortinet_Factory_Backu|
E Fortinet_GUI_Server
呵 Fortinet_SSL
罰 Fortinet SSL_DSA1024
罰 Fortinet_SSL_DSA2048
司 Fortinet SSL_ECDSA25：
呵 Fortinet_SSL_ECDSA38，
國 Fortinet_SSL_ECDSA52|
國 Fortinet_SSL_ED448
邱 Fortinet_SSL_ED25519
國 Fortinet_SSL_RSA1024
司 Fortinet_SSL_RSA2048
罰 Fortinet SSL RSA4096
國 Fortinet_Wih
口 Remote CA Certficate
飞塔SASE
顾 Fortfhe
.Backup
vecurity Kating Issues
OK
Cancel
教主VIP
飞塔NGFW与ZTNA
塔SASE
>-②•4②、②admin、
×
飞塔SASE
教主VIP，
教主VIP 飞塔SASE
教主VIP/塔SASE
乾颐堂
55

## Page 56

3
HA
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP
教主VIP
G FGVMO2TM22023965
#2 Dashboard
f Network
B Policy & Objects
• Security Profles
回 VPN
2 User & Authentication
今 WiFi Controller
¢ System
Administrators
Admin Profiles
FabricManagement
Settings
HA
SNMP
Replacement Messages
FortiGuard
Feature Visibility
Certificates
2
• Security Fabric
區 Log& Report
FRTINET
加载FGT1个人证书
=
Q
塔SASE
>- ②•A②、② admin、
+ Create/Import、
Certificate
Generate CSR|
白 Delete
◎ View Details
& Download
Search
Q
Subject令
Comments
Issuer二
Expires令
CA Certificate
C-US,ST -California, L=Sunnyvale. O- Fortine.：
C=US, ST = California, L = Sunnyvale, O = Fortine..
Thisis.the default CA certificate the SSL. Inspectio..
Fortinet
This is the default CA certificate the SSL Inspectio.
Fortinet
2033/05/18 18:17:46
2032/10/1401:22:28
1
1
食
v7.2.2
CRL
sted
口 Local Certificate
面 Fortinet_Factory
C =US, ST = California, L = Sunnyvale, O= Fortine..
This certifcate is embedded in the hardware at th.. Fortinet
2056/01/18 19:14:07
面 Fortinet_Factory_Backup
C=US, ST = California, L = Sunnyvale, O= Fortine..
This certificate is embedded in the hardware at th.. Fortinet
、2038/01/18 19:14:07
面 Fortinet_GUI_Server
C = US, ST = California, L = Sunnyvale, O = Fortine..
Thisis the default CA certificate the SSL Inspectio.. Fortinet 2
2025/08/2018:18:15
EG Fortinet_SSL
C=US, ST = California, L = Sunnyvale, O = Fortine...
This certifcate is embedded in the hardware at th..
Fortinet
2025/08/20 18:17:46
面 Fortinet_SSL_DSA1024
C=US, ST = California, L = Sunnyvale,O = Fortine..
This certificate is embedded in the hardware at th...
Fortinet
2025/08/20 18:17:49
國 Fortinet_SSL_DSA2048
C=US, ST = California, L = Sunnyvale,O = Fortine..
This certificate is embedded in the hardware at th.. Fortinet
2025/08/20 18:17:49
國 Fortinet_SSL_ECDSA256
C= US, ST = California, L = Sunnyvale, O = Fortine..
This certifcate is embedded in the hardware at th.. Fortinet
2025/08/2018:17:49
同 Fortinet SSL_ECDSA384
C= US, ST = California, L = Sunnyvale,O = Fortine...
This certificate is embedded in the hardware at th.. Fortinet
2025/08/20 18:17:49
國 Fortinet_SSL_ECDSA521
C= US, ST = California, L= Sunnyvale, O= Fortine..
This certificate is embedded in the hardware at th... Fortinet
2025/08/20 18:17:49
國 Fortinet_SSL_ED448
C-US, ST = California, L =Sunnyvale, O= Fortine..
This certifcate is embedded in the hardware at th.. Fortinet
2025/08/20 18:17:49
國 Fortinet_SSL_ED25519
C= US, ST = California, L= Sunnyvale, O= Fortine..
This certifcate is embedded in the hardware at th.. Fortinet
2025/08/2018:17:49
r Fortinet SSL_RSA1024
C= US, ST =California, L=Sunnyvale, O=Fortine..
This certihcate is embedded in the hardware atth. Fortinet
2025/08/20 18:17:46
面 Fortinet_SSL_RSA2048
C= US,ST - Calfornia, L =Sunnyvale. O = Fortine..
This certifcate is embedded in the hardware at th.. Fortinet
2025/08/20 18:17:47
同 Fortinet_SSL_RSA4096
C=US,ST =California, L= Sunnyvale,O= Fortine...
This certificate is embedded in the hardware at th...
Fortinet
2025/08/20 18:17:48
國 Fortinet_Wif
C=US,ST = California, L = Sunnyvale,O= "Fortin..
This certificate is embedded in the frmware andi.. DigiCert Inc
2022/11/04 16:59:59
日 Remote CA Certificate ⑤
颐CA_Cert.1
项 Fortinet_CA|
C =CN, ST = beijing, L= beijing, O= qytang, CN=..
C= US, ST = California, L = Sunnyvale, O = Fortine.
國 Fortinot CA Rocbun
aytang
Fortinet
Eartinat
6 Security Rating Issues
2043/05/720:40.00
2056/05/27 13:27:39
28/01/014-2 120
0% ②2
；塔SASE
FSASE
乾颐堂
56

## Page 57

3
HA
飞塔SASE
教主VIP
教主VIP
G FGVM02TM22023965
6 Dashboard
中 Network
L Policy & Objects
B Security Profles
口 VPN
User & Authentication
今 WiFiController
¢ System
Admin Profles
Fabric Management
Settings
HA
SNMP
Replacement Messages
FortiGuard
Feature Visibility
Certifcates
W Security Fabric
區 Log & Report
①
<
1
食
教主VIP
飞K塔NGFW与ZTNA
×
=Q
+ Create/Import、
Names
回LocaiCACa
罰 Fortinet_CA_SSD
面 Fortinet_CA_Untrusted
口 Local Certificate 15
罰 Fortinet_ Factory
写 Fortinet_Factory_Backu
呵 Fortinet_GUl_Server
罰 Fortinet_SSL|
EG Fortinet_SSL_DSA1024
罰 Fortinet SSL DSA2048
司 Fortinet SSL ECDSA25/
呵 Fortinet_SSL_ECDSA38
國 Fortinet_SSL_ECDSA52
局 Fortinet SSL ED448
Fortinet_SSL_ED25519
國 Fortinet_SSL_RSA1024
國 Fortinet SSL_RSA2048
呵 Fortinet_SSL_RSA4096
司 Fortinet_Wif
口 Remote CACertiicate
员F
fARankn
Security Rating Issues
加载FGT1个人证书
塔SASE
>. @-42.eamm-
Create Certificate
Choose Method
Certificate Det
Create Certificate
Review
尚 Automatically Provision Certificate
Use Let's Encrypt and the ACME protocol to automate certifcate creation and maintenance. You will need to enable DDNS or purchase adomain.
Use Let's Encrypt
项 Generate New Certificate
FortiGate can generate a certificate using our self-signed CA: Fortinet_CA_SSL
Using a server certificate from a trusted CA is strongly recommended.
Generate Certificate
• Import Certificate
importan existingcerticafe via Fleuolosd.
Import Certificate
飞塔SASE
主VIP
飞塔SASE
Cancel
飞塔SASE
教主VIP，
乾颐堂
57

## Page 58

3
HA
教主VIP
教主VIP
飞塔SASE
FGVMO2TM22023965
# Dashboard
+ Network
』 Policy &Objects
A SecurityProfles
旦 VPN
S User & Authentication
WiFi Controller
System
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
粉 Security Fabric
區 Log& Report
1
1
教主VIP
FERTINET
加载FGT1个人证书
=Q
+ Create/Import、
Create Certifcate
NameS
日 Local CA Certi
• Fortinet_CA_SSL
Choose Method
Certificate Detai
E Fortinet_CA_Untrusted
口 Local Certificate （15
• Import Certifcate
Type
Local Certificate
PKCS #12 Certificate
|Certificate
F Fortinet_Factory
F Fortinet_Factory_Backu
呵 Fortinet_GUI_Server
呵 Fortinet_SSL
罰 Fortinet_SSL_DSA1024
Certificate with key fle
+ fgt1.qytang.com.p12
Password
b-----••
Confrm password
Certifcate name
•o.....。
fgt1.qytang.com
同 Fortinet_SSL_DSA2048
國 Fortinet SSL_ECDSA25/
写 Fortinet_SSL_ECDSA38，
司 Fortinet_SSL_ECDSA52
司 Fortinet_SSL_ED448
同 Fortinet SSL_ED25519
写 Fortinet_SSL_RSA1024
國 Fortinet_SSL_RSA2048
K塔SASE
写 Fortinet_Wif
日 Remote CA Certifcate
项 CA_Cert
Create Certificate
◎
◎
飞塔SASE
6 Security Rating Issues
教主VIP
Create
Back
Cancel
教主VIP
飞K塔NGFW与ZTNA
塔SASE
>- 日•4②、②admin、
×
Review
飞塔SASE
教主VIP
教主VIP）
飞塔SASE
乾颐堂
58

## Page 59

3
HA
飞塔SASE
教主VIP
教主VIP
向 FGVMO2TM22023965
82 Dashboard
+ Network
山 Policy & Objects
• Security Profiles
回 VPN
User & Authentication
今 WiFi Controller
¢ System
Administrators
Admin Profles
FabricManagement
Settings
HA
SNMP
Replacement Messages
FortiGuard
Feature Visibility
Certificates
0 Security Fabric
區 Log & Report
1v
1
食
FRTINET
教主VIP
飞塔NGFW与ZTNA
FGT1最终证书
=Q
塔SASE
>- ②、0②、② admin 、
+ Create/Import-
白 Delete
◎ View Details
& Download
Search
Q
Issuer二
Names
Subjects
Comments -
Expires
口 Local Certificate 16
買 fgt1.qytang.com
C= CN, ST = beijing, L = beijing, O= qytang, OU = qytangnetde..
qytang
2033/05/11
國 Fortinet_Wih
C= US,ST = California, L = Sunnyvale, O = "Fortinet, Inc"， CN =..
This certifcate is embedded in the frmware and i...
DigiCert Inc 2022/11/04
r Fortinet_SSL
C = US, ST = California, L = Sunnyvale, O = Fortinet, OU = Forti...
This certifcate is embedded in the hardware at th..
Fortinet
2025/08/20
國 Fortinet SSL_DSA1024
C=US, ST = California, L = Sunnyvale, O = Fortinet, OU - Forti...
This certificate is embedded in the hardware at th.. Fortinet
2025/08/20
写 Fortinet_SSL_DSA2048
C =US, ST = California, L = Sunnyvale, O= Fortinet, OU = Forti...
This certifcate is embedded in the hardware at th....
Fortinet
2025/08/20
r Fortinet_SSL_ECDSA256
C=US, ST = California, L = Sunnyvale, O = Fortinet, OU = Forti...
This certifcate is embedded in the hardware at th..
Frortinet
2025/08/20
國 Fortinet_SSL_ECDSA384
C=US, ST = California, L = Sunnyvale, O = Fortinet, OU = Forti...
This certifcate is embedded in the hardware at th..
Fortinet
2025/08/20
r Fortinet_SSL_ECDSA521
C = US, ST = California, L = Sunnyvale, O = Fortinet, OU = Forti...
This certificate is embedded in the hardware at th...
Fortinet
2025/08/20
面 Fortinet SSL_ED448
C= US, ST = California, L = Sunnyvale, O = Fortinet, OU = Forti...
This certifcate is embedded in the hardware at th..
Fortinet
2025/08/20
E Fortinet_SSL_ED25519
C =US, ST = California, L = Sunnyvale, O = Fortinet, OU = Forti...
This certificate is embedded in the hardware at th...
Fortinet
2025/08/120
E Fortinet SSL_RSA1024
C =US, ST = California, L = Sunnyvale,O = Fortinet, OU = Forti...
This certificate is embedded in the hardware at th...
Fortinet
2025/08/20
國 Fortinet_SSL_RSA2048
C= US, ST = California, L = Sunnyvale, O = Fortinet, OU = Forti...
This certifcate is embedded in the hardware at th...
Fortinet
2025/08/20
國 Fortinet_SSL_RSA4096
C= US, ST = California.， Le Sunnyvale, O = Fortinet, OU = Forti...
This certifcate is embeddedin the hardware at th..
Fortinet
2025/08/20
EG Fortinet_Factory
C=US,ST =California,L= Sunnyvale. O = Fortinet, OU.= Forti..
This certifcate isembedded in the hardware at th..
Fortinet
2056/01/18
E Fortinet_Factory_Backup
C=US, ST =California,L= Sunnyvale, O = Fortinet, OU= Forti...
This certifcate is embedded in the hardware at th..
Fortinet
2038/01/18
r Fortinet_GUI_Server
C =US, ST = California, L = Sunnyvale, O = Fortinet Ltd.，OU-...
This is the default CA certificate the SSL Inspectio.. Fortinet
2025/08/20
日 Remote CA Certificate ⑤
项 CA Cert_1
项 Fortinet_CA
取 Fortinet_CA_Backup
Fortinet.Sub_CA
品 Fortinet Wif CA
C=CN, ST = beijing, L= beijing, O= qytang, CN =qytca
C= US, ST = California, L = Sunnyvale, O = Fortinet, OU = Certi..
C= US, ST = California, L =Sunnyvale, O = Fortinet, OU=Certi..
C= US,ST =California, L = Sunnyvale, O = Fortinet, OU=Certi.
CHIIS O= DioiCert In~CN = DiciCert TIS RSASHA25 202
qytang
Fortinet
Fortinet
Fortinet
DicicerfInn
0 Security Rating Issues
2043/05/07
2056/05/27
2038/01/19
2056/05/27
2020/n0/22
55% 23
；塔SASE
s塔SASE
乾颐堂
59

## Page 60

3
HA
飞塔SASE
教主VIP
教主VIP
向 FGVMO2TM22023965
82 Dashboard
+ Network
Policy & Objects
A Security Profles
旦 VPN
S User & Authentication
今 WiFi Controller
¢ System
Administrators
Admin Profles
Fabric Management
Settings
SNMP
Replacement Messages
Feature Visibility
Certificates
0 Security Fabric
區 Log & Report
教主VIP
飞K塔NGFW与ZTNA
FERTINET
v7.2.2
Apply
乾颐堂
FGT1系统配置
1~
1
女
•=Q
System Settings
Host name /fgt1
System Time
Current system time
Time zone
Set Time
2023/05/18 18:55:53
eect semen
（GMT+8:00） Beijing, ChongQing, Hon 、
NTP PTP Manual settings
FortiGuard
60
Sync interval
Setup device as local NTP server
Listen on Interfaces
Minutes （1- 1440）
# fortilink
Administration Settings
HTTP port
Redirect to HTTPS
80
HTTPS port
443
Port conficts with the SSL-VPN port
setting
HTTPS server certificate
國 fgt1.qytang.com
SSH port
Telnet port
Idle timeout
22
23
Minutes （1-480）
ACME interface ①
<Allow concurrent sessions
Allcu anminictrative Inainicina ForticlnadS
塔SASE
HA: Primary）-②•4②•② admin、
conanommnanonl
④ API Preview
>- Editin CLI
cVirtualDomair
E Howto Confgure Virtual Domains C
日 Guides
e Using confguration save mode C
教主VIP
② Online Guides
Relevant Documentation C
I Video Tutorials C
Q FortiAnswers
D Jointhe Discussion C
seauri Reatine baove
A Default Port HTTPs
A Default Port SSH
A USB Auto Confguration
A Admin Password Policy
A FortiGate Identifcation
Show Dismissed O
飞塔SASE
飞塔SASE
60

## Page 61

3
HA
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
教主VIP
导入书签.
C
教主VIP
飞塔SASE®
田 FGT1
再次连接确认证书
◎
凸
FGT2 ④SW
https://fgt1.qytang.com/login2redir =%2F
连接安全性：fgt1.qytang.com
凸 您已安全地连接至此网站。
验证者：qytang
Mozilla 不认识此证书颁发者。它可能是由您的操作系统或管理
员身份添加。详细了解
更多信息
SASE
教主VIP，
飞塔SASE
admin
Login
教主VIP
山
页面信息 — https://fgt1.qytang.com/login?redir=.
4o
常规（G）
媒体（M）
权限（P）
安全（S）
网站身份
网站：
所有者：
验证者：
fgt1.qytang.com
此网站未提供所有者信息，
qytang
查看证书（V）
隐私和历史记录
我之前访问过该网站吗？
是，1,030次
此网站在我的计算机上存储了信息 有，136 KB 网站
吗？
数据
清除 Cookie 和网站数据
我保存过该网站的任何密码吗？ 是
查看已保存的密码（W）
技术细节
连接已加密 （TLS AES 256 GCM SHA384, 256位密钥，TLS 1.3）
您当前查看的页面在传送到互联网之前已被加密。
加密使得未经授权的人难以查看计算机之间交流的信息。因此，其他人不太可能拦
截此网页的传送并从中读取此页面。
飞塔SA
教主VIP
帮助
61

## Page 62

3 HA
飞塔SASE
教主VIP
向 fgt1
8 Dashboard
+ Network
Interfaces
DNS 2
IPAM
教主VIP
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Objects
教主VIP
Diagnostics
凸 Policy & Objects
A Security Profiles
旦 VPN
2 User & Authentication
今 WiFi Controller
女 System
. Security Fabric
Log& Report
FRTINET
教主VIP
飞塔NGFW与ZTNA
配置DNS
=Q
DNS Settings
DNS servers
Use FortiGuard Servers
|Specify
Primary DNSserver ④） 192.168.1.200
Secondary DNSserver
U.0.0.U
ocacoanname
13,720 ms
DNS Protocols
DNS （UDP/53） ①0
TLS （TCP/853） ①
HTTPS （TCP/443） ① 0
HA: Primary ）- ②、A①、② admin -
塔SASE
DNS Filter Rating Servers
2caitonan ormanon
⑧ APIPreview
飞塔SASE
飞塔SASE
Apply
⑦ Online Guides
号 Relevant Documentation C
C Video Tutorials C
P FortiAnswers
> Join the Discussion C
飞塔SASE
教主VIP
飞塔SASE
教主VIP，
乾颐堂
62

## Page 63

3
HA
教主VIP
教主VIP
飞塔SASE
回 fgt1
E Dashboard
+ Network
L Policy & Objects
P Security Profles
S User & Authentication
女 System
aa awanaaemen
Feature Visibility 2
• Security Fabric
區 Log & Report
教主VIP
FRTINET
教主VIP
飞塔NGFW与ZTNA
三〇
Feature Visibility
Core Features
0 Advanced Routing
〇 IPv6
• Switch Controller ⑧
0VPN
OWiFiController
众
激活多接口策略
田
田
Securitv Features
• Application Control
• Data Leak Prevention
O DNS Filter
Q Email Filter
• Endpoint Control
O Explicit Proxy 0
0 File Filter
0 Intrusion Prevention
0 Video Filter （|
• Web Application Firewall C
0Web Filter
• Zero TrustNetworkAccess @
Additional Features
• Advanced Endpoint Control
⑦ Advanced Wireless Features
⑦ Allow Unnamed Policies
O Certificates
⑦ DNS Database
O DoS Policy
⑦ Email Collection
0 FortiFxtender （
⑦ ICAP 0
0 Implicit Firewall Policies
• Load Balance
• Local In Policy
• Local Out Routing
⑦ Multicast Policy
O Multiple Interface Policies
⑦ Operational Technology （OT）、
Q Policy Advanced Options
飞塔SASE
HA: Primary >-②、A、Q admin-
Changes ©
3 Multiple Interface Policies
教主VIP
飞塔SASE|
田
田
田
教主VIP
教主VR飞塔SASE
乾颐堂
63

## Page 64

3
HA
飞塔SASE|
配置Port2
教主VIP
教主VIP
@ fet1
B Dashboard
+ Network 1
Interfaces
DNS
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Objects
Diagnostics
』 Policy & Objects
A Security Profles
口 VPN.
2 User & Authentication
今 WiFi Controller
¢ System
Secrih Eahric
區 Log& Report
教主VIP
1>
Edit Interface
Name
Alias
Type
VRF ID ⑧
Role ①
！.port2
團 Physical Interface
Undefined
• Dedicated Management Port
Accress
Addressing mode
IP/Netmask
Secondary IP address O
Manual ||DHCP Auto-managed by IPAM One-Arm Sniffer
10.1.1.10/255.255.255.0
Acministrative access
Receive LLDP ⑧
Transmit LLDP ⑧
• DHCP Server
Network
Device detection ⑧0
Security mode
。
O HTTPS
口 FMG-Access
口FIM
口HTTP⑧
口 SSH
口 RADIUS Accounting
口 Speed Test
Use VDOM Setting Enable Disable
Use VDOM Setting Enable Disable
飞塔SASE
习 PING
口 SNMP
Security Fabric
口 comnection®
Traffc Shaping
v7.22
教主VIP
飞塔NGFW与ZTNA
飞塔SASE
HA: Primary ）- ②•4②•② admin-
教主VIP
化塔SASE
@ tgt1
Status
个UP
00:09:0f:09:00:01
Additional Information
④ API Preview
% References
>- Editin CLI
② Online Guides
3 Relevant Documentation C
t-ortAncprs
Join the Discussion C
飞塔SASE
教主VR/塔SASE
乾颐堂
64

## Page 65

3
HA
飞塔SASE
教主VIP
教主VIP
回 fgt1
© Dashboard
$ Network
nueltaces
DNS
IPAM
SD-WAN
Static Routes
Policy Routes
RIP
OSPF
BGP
Routing Obiects
Multicast
Diagnostics
L Policy & Objects
A Security Profles
旦 VPN
2 User & Authentication
の WiFi Controller
# System
• Security Fabric
區 Log & Report
〈主VP
教主VIP
飞塔NGFW与ZTNA
接口最终配置
• 。
= FortiGate VM64、
"II
+ Create New-
•Edit
Names
日 加 802.3adAgereBate ①
H fortilink
日團 Physical Interface ④
團 port1
團 port2
團 port3
①>
團 port4
>日② Tunnel Interface ①
A NAT interface （naf.root）
v7.2.2
• Seurity Rating /soves
色 Delete
Types
H 802.3ad Aggregate
團 Physical Interface
團 Physical Interface
團 Physical Interface
團 Physical Interface
D Tunnel Interface
Search
Dedicated to FortiSwitch
202.100.1.10/255.255.255.0
192.168.1.10/255.255.255.0
0.0.0.0/0.0.0.0
飞塔SASE
HA: Primary >-②、4②、②admin•
團Group By Type•
飞塔SASE
Administrative Access t
DHCP Clients=
DHCP Kanges
PING
Security Fabric Connection
10255.12-10255.1254 2
PING
HTTP
FEMG AcCess
PING
PING
HTTPS
FMG-ACCCSS
。
飞塔SASE
乾颐堂
65

## Page 66

3
HA
回 fgt1
2 Dashboard
4 Network
山 Policy & Objects
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
• Security Profiles
旦 VPN
S User & Authentication
分 WiFi Controller
• System
W Security Fabric
山 Log & Report
塔SASE|
教主VIP
飞塔NGFW与ZTNA
放行上网流量
防火墻策略配置
Q
+Create New
•Edt
回 Delete|
Q Policy Lookup
Search
WX HA: Primary >-②、4②、② admin-
固 Export、 Interface Pair View By Sequence
Name
From
To
Source
Destination
Schedule
Service
Action
NAT
Security Profles
Log
Bytes
permit-internet-traffic.
permit-inside-to-dmz-traffic
圖 port2
圖 port1 all
圖 port3
圖 port2圖 port3 all
口 all
1o always
⑦ ALL
V ACCEPT
⑦ Enabled
no-inspection ⑦ All
122.28 kB
日 all
7 always
⑦ ALL
一< ACCEPT & Disabled
rsL no-inspection
S All
VOB
Implicit Deny
口 any
口 any
日 all
日 all
Io always
Z ALL
⑦ DENY
x Disabled
M18113kB
NATX
Log
放行Inside去往
DMZ的流量
FSASE
①>
飞塔SASE
教主VIP
飞塔SASE
飞塔SASE
FRTINET
V7.2.2
U secunity Kating ssues
教主VIP
③ Updated: 10:21:03 2
草Z颐堂
66

## Page 67

乾颐堂
第4部分.ZTNA
教主
IP T塔SASE
教主VPK塔SASE
K塔SASE
教主VIP 飞塔SASE
飞塔SASE
教主VIP
飞塔SASE

## Page 68

4 ZTNA
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
Gartner对ZTNA的定义
Zero trust network access （ZTNA） is a product or service that creates an
identity- and context-based, JOgical access boundary around an applicationor set
of applications. The applications are hidden from discovery, and access is restricted
via a trust broker to a set of named entities. The broker verifies the identity，
context and policy adherence of the specified participants before allowing access
and prohibits lateral movement elsewhere in the network. This removes application
assets from public visibility and significantly reduces the surface area for attack.
“零信任网络访问（ZTNA）是一种产品或服务，它围绕一个应用程序或一组应用
程序创建了基于身份和上下文的逻辑访问边界。这些应用程序被隐藏，以防被发现，
通过信任代理对一组指定实体的访问进行限制。该代理在允许访问之前，会验证指定
参与者的身份（SAML），上下文（TAG）以及策略的遵守情况［实时的主机态势感知］，并
禁止他们在网络中的横向移动。这样就将应用程序资产从公开可见性中移除，并显著
减少了攻击面。"
68

## Page 69

4 ZTNA
教主VIP
飞塔NGFW与ZTNA
乾颐堂
ZTNA的原则
飞塔SASE
*永不信任，持续验证（从不信任，始终验证）
2.最小化访问授权
飞塔SASE
心控制对应用、数据和资源的访问，而不是网络
粉•基于需求或角色给予最小访问权限
3.假设已经“失陷"［内外一致对待，实时态势感知］
• 以网络内和网络外都存在攻击者为安全设计前提
•无论在企业网内还是企业网外访问，都一致对待：全不受信
千）
69

## Page 70

ZTNA
教主VIP
飞塔NGFW与ZTNA
豆颐堂
ZTNA精细的控制
飞塔SASE
.每个连接，验证用户身份
2.支持强身份验证（MFA） ［FortiToken］和单点登录（SSO）ISAML］
3.每个会话，验证设备身份［颁发的设备证书］
4每个会话，验证设备状态［是否打开防火墙…］谢主么
5.仅允许用户访问必要的应用程序和数据
6.应用程序隐藏在Internet访问代理中［你知道才能访问］
教主VIP
飞塔SASE
教主VIP
70

## Page 71

ZTNA
教主VIP
飞塔NGFW与ZTNA
ZTNA的优势
塔SASE
1.提供比VPN更出色的用户体验
2.通过持续验证和细粒度的应用程序访问策略，确保卓
越的安全性
33.无论应用程序部署在本地、私有云还是公有云，均可
对应用程序访问进行有效控制
4.完美适用于混合网络模型，确保本地用户和远程用户
安全访问企业网络
飞塔SASE
豆颐堂
粉
教主VIP
71

## Page 72

4
ZTNA
飞塔SASE
教主VIP
飞塔NGFW与ZTNA
教主VIP
教主VIP
飞塔SASE
VPN
客户端
数据中心防火墻
外部网络
飞塔SA
教主VIP
网络级别的访问
VPN与ZTNA的区别
教主VP
Cloud
飞塔SASE
飞塔SASE
教主VIP
客户端
内部/外部网络
零信任访问访问
接入代理
FOS
教主VIP
塔SASE|
应用级别的访问
适合混合的多云环境
飞塔SASE
数据中心
引
塔SASE
乾颐堂
72

## Page 73

4
ZTNA
教主VIP
飞塔SASE
教主VIP
飞塔SA
教主VIP
飞塔NGFW与ZTNA
Fortinet ZTNA的主要组件
SDP （Software-Defined Perimeter）
飞塔SASE
SDP Gateway
SDP Controller
乾颐堂
飞塔SASE
FortiGate 下一代防火墙
FortiClient EMS
FortiClient
教主VIP
教主VIP 飞塔SASE
教主VIP 飞塔SASE
飞塔SASE
教主VIP
73

## Page 74

4 ZTNA
代理7层模型，主力方案
ZTNA 访问代理
• HTTPS 和TCP 访问代理解决方案和架构
•适用于远程访问和内部网络访问
杀同于 VPN，无需持久性连接
飞塔SASE
教主VIP
（回18t1
m Dashboard
+ Network
F Pollev & Obleats
Firewall Policy
IPv4 DoS Policy
ZTNA
Addresses
Internet Service Database
IP Pools
Protocol Options
Traffe Shaping
A Seuriw Prohle
Q VPN
中 System
⑥ Socurity Fabric
區 Log & Report
教主VIP
飞K塔NGFW与ZTNA
两种部署方案
传统VPN的一种升级
ZTNA 非访问代理（又称 ZTNA 安全访问）
•远程用户继续沿用VPN 访问网络，但必须事先采用
ZTNA 规则和标签进行额外的设备验证及安全态势检查
•通过支持 ZTNA 安全态势检查的本地访问策略，为本地
用户提供相应的访问权限
Edit Policy
Name ◎
Incoming Interface
permit-ssivpn-tratfc
12 SSLVPN tunnel interface （ssLroo x
select Entres
Qbearch
口 ZINA TAG（11）
x Statistics （since last reset/
只是在VPN相关
的防火墙策略里
边增加标签条件
Last used
Outgoing Interface
圖 port3
22hour（s）ag0
1day（s） ago
all.registered.clients
自a|l
Acme session
No Firev，
all roistered clantd
icount
Total bytes
cirrent handundth 0ha
229.75kB
回al
角 Clear Counters
E always
Acian
EUS AI1 TNKNOWN PIIEN LaSt/ Days BytesT
250 kB
FMS AII IINMANAGEAPIE
EOTEMC AI EORTICOD 2OOKH
Flow-based Prowy-based
Firewall/Network Options
NAT
Protocol Options
100kB
SOkB
AntVinie
乾颐堂
74

## Page 75

4
ZTNA
教主VIP
飞塔SASE
教主VIP
飞塔SASE
教主VIP
教主VIP
飞K塔NGFW与ZTNA
教主V！
访问代理工作流
公共云
品品应用程序
ZTNA标签
按规则标记终端
将标记的终端列表发送到
FortiGate
EMS证书
签名和安装
塔SASE
Saas
应用程序
信任验证
验证用户身份（SSO/MFA）
验证安全态势（On-net*）
验证访问权限
设备证书/
v 验证设备证书
启动到目的地的流量
v\代理安全地将流量转发到访问代理
SSL加密
带设备（D 的证书
数据中心
塔SASE
EMS
评估
标签
用户登录
设备信息（操作系统、网络信息、型号）
登录用户信息
安全态势（病毒库软件、漏洞检测）
设备证节
由 EMS CA 签名的证书
在终端上安装
© Fortinet Inc. All Rights Reserved.
FSASE
所有终端
签发ZTNA的设备证书
乾颐堂
75

## Page 76

4 ZTNA
设备认证
态势感知
客户身份
认证
y
教主VIP
飞塔NGFW与ZTNA
豇颐堂
HTTPS 访问代理
FortiGate HTTPS 访问代理可用作 HTTP 服务器的反
向代理。当客户端连接至受保护服务器托管的 Web 页面
时，该地址将解析为 FortiGate 的访问代理所提供的虚拟
IP 地址。FortiGate 代理该连接并进行 用户身份验证，将
在浏览器页面提示用户提供终端证书，根据从 FortiClient
EMS 同步的 ZTNA 终端信息 记录对证书进行验证。如果
网络中还配置了身份验证方案（如SAML身份验证），则客
户端将被重定向至 强制闪户认证页面进行登录操作。一旦
验证通过，则根据 ZTNA 规则放行流量，FortiGate 会将
web 页面 信息返回至客户端。
76

## Page 77

J ZTNA
TCP流量
封装到TLS
隧道、》
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
TCP 转发访问代理
TCP 转发访问代理是 HTTPS 反向代理的特殊应用。
与HTTPS反向代理相比，TCP流量并非将流量 代理至
Web 服务器，而是通过建立 HTTPS 隧道在客户端和访问
代理之间进行传输，继而将流量转发至受保护资源。
FortiClient 指定代理网关后配置客户端通过 ZTNA 连接至
需要访问的目标。随后与 FortiGate 的访问代理的虚拟IP
建立HTTPS连接，验证客户端证书后，根据 ZTNA 规则
授予访问权限。TCP 流量 从 FortiGate 转发至受保护的目
的地，最终建立端到端连接。
77

## Page 78

4
ZTNA
教主VIP
飞塔NGFW与ZTNA
Web Access Proxy vs TCP Forwarding Access Proxy
Device
Web Browser
⑤ New/Tab
个 之
G
③ https://5.5.5.1:10001
FGT
ZTNA VIP 5.5.5.1:10001
ZTNA AP
https://FGT VIP:vipport
Client Certificate required
Client Certificate
Server Content
Protected
HTTP（S） Server
Real IP 192.168.235.35
飞塔SASE
http（s）：//Server_IP
Web Access Proxy
（WAP）
Server Content
Forticlient
FGT
ZTNA AP
Protected
App Server
Web Browser or Client
App （RDP, SSH. ...）
RDP,SSH,WWW：
192.168.235.35
@ ZINA DESTINATION
Win RDP
Destination Host 192.168.235.35:3389
Praxy Gateway 5.5.5.5:10001
ZTNA VIP 5.5.5.1:10001
SSL negotiation + FCT Device Cert
TLS tunnel to 5.5.5.1:10001
Server Content
Real IP 192.168.235.35
TCP:ServerJR :port
Server Content
TCP Forwarding
Access Proxy
（TFAP）
（主VIP
乾颐堂
78

## Page 79

4
ZTNA
飞塔SASE
教主VIP
飞K塔NGFW与ZTNA
乾颐堂
教主VIP
注意有三个根证书
教主VIP
1. 乾颐堂根证书
ZTNA Agent
qytang_root
default_ZTNAROOtCA
ems发放ztna证书
2. EMS ZTNA根证书
公司内部应用的通信使用：乾颐堂证书
ZTNA的TLS隧道使用：EMS内置的ZTNA证书
aytang_root
sitel.qytang.com
ZTNA示意图
qytang_root
ems.qyang.com
连接EMS
评估客户状态
颁发ZTNA证书
ZTNA访问
qytang_root
fgt1.qytang.com
ztna-server
ztna-ssh
SASE
微软证书只是用于LDAPs
3.微软域根证书
EMS
FGT
SMTP
ms_root
ldap
Fabric Security Connector
获取标签信息
Active Directory
202.100.1.111:443
202.100.1.111:2222
sitel.qytang.com:443
192.168.1.1:22
79

## Page 80

4
ZTNA
飞塔SASE
教主VIP
G fgt1
Dashboard
+ Network
L Policy & Objects
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
A SecurityProfles
旦 VPN
2 User & Authentication
今 WiFi Controller
¢ System
. Security Fabric
E Log & Report
教主VIP
飞K塔NGFW与ZTNA
FERTIET
v7.2.4
教主VIP
乾颐堂
Q
New VirtuallP
VIPtype
Name
Comments
IPv4
DMZ-DC
colon
會
Change
Network
Interface
Type
External IP address/range 0
Map to
IPv4 address/range
• Optional Filters
Q Port Forwarding
配置DMZ-DC的Virtual IP
塔SASE
HA: Primary〉1、 、②admin、
名0/255
飞塔SASE
圖 port1
Static NAT FODN
202.100.1.200
192.168.1.200
飞塔SASE
FortiGate
啊 fgt1
Statistics （since last reset）|
Last used N/A
First used N/A
Hitcount0
亩 Clear Counters
Additianal Informatinm
⑨ APIPreview
② Online Guides
旦 Relevant Documentation C
• Video Tutorials C
P Hot Questions at FortiAnswers
D Jointhe Discussion C
教主VIP
OK
Cancel
飞塔SASE
80

