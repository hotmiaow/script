# Forti SASE Course - Master Notes Summary

This document provides a concise summary of the topics covered in each chapter of the **Forti SASE Course**. Use these notes to quickly navigate the core concepts, configurations, and lab setups distributed across the 10 modules.

## 📌 Chapter 1: SASE Theory & Architecture Overview
*   **Topic:** SASE Theory (SASE理论介绍)
*   **Key Highlights:**
    *   Transitioning from traditional centralized network models (MPLS/VPN) to modern Decentralized/Direct Internet Access (DIA) approaches.
    *   Definition of Secure Access Service Edge (SASE) and its core components: SD-WAN, SWG (Secure Web Gateway), CASB, FWaaS, and ZTNA.
    *   The difference between Traditional VPN setups and ZTNA (Zero Trust Network Access), using SDP (Software-Defined Perimeter) concepts.
    *   The benefits of a Single-Vendor SASE solution for centralized management and cohesive security policies.

## 📌 Chapter 2: High Availability (HA) & Deployment
*   **Topic:** Deployment, Initialization, and HA (部署与初始化 / HA)
*   **Key Highlights:**
    *   Detailed explanation of FortiGate High Availability working principles (Active-Active vs Active-Passive failover, Virtual MAC routing, and session syncing).
    *   Base HA setup requirements: Similar hardware, identical firmware, matched interface configs.
    *   Configuring Heartbeat (sync) vs Monitor interfaces.
    *   Configuring FortiGate HA clusters via GUI/CLI (`get system ha status`).
    *   Importing root CA certificates into the appliance to prepare for secure communications.

## 📌 Chapter 3: ZTNA Setup & EMS Initialization
*   **Topic:** ZTNA & Endpoint Management Server (安装与初始化EMS)
*   **Key Highlights:**
    *   Deploying and initializing the FortiClient Endpoint Management Server (EMS).
    *   Integrating EMS with Microsoft Active Directory (LDAP integration).
    *   Creating ZTNA Servers and mapping them to services on FortiGate.
    *   Enabling SMTP services for EMS to send automated email alerts.
    *   Creating ZTNA Zero Trust Tagging rules to classify endpoints based on AD groups or status.

## 📌 Chapter 4: ZTNA Destinations & End-User Testing
*   **Topic:** ZTNA Agent & Access (FortiClient ZTNA)
*   **Key Highlights:**
    *   Connecting the FortiClient (Zero Trust Fabric Agent) to the EMS server to receive telemetry and tags.
    *   Adding ZTNA Destinations (like SSH, Web) inside EMS to publish applications to authorized endpoints.
    *   Testing secure ZTNA access (e.g., using MobaXterm to securely access an internal SSH server without a VPN).
    *   Enabling and enforcing Malware Protection (Anti-Virus) profiles dispatched directly from EMS.

## 📌 Chapter 5: SAML Theory
*   **Topic:** SAML Authentication Concept (SAML 理论)
*   **Key Highlights:**
    *   Deep-dive into Security Assertion Markup Language (SAML) 2.0 for Single Sign-On (SSO).
    *   Understanding the roles of Identity Providers (IdP) and Service Providers (SP).
    *   Establishing trust lines via the exchange of XML Metadata and certificates.
    *   How NameID mapping and formats govern user data synchronization.

## 📌 Chapter 6: SAML Configuration (FAC & FortiGate)
*   **Topic:** SAML Implementation 
*   **Key Highlights:**
    *   Configuring FortiAuthenticator (FAC) as the ultimate SAML Identity Provider (IdP).
    *   Configuring FortiGate as a corresponding Service Provider (SP).
    *   Handling user attributes and assertions (mapping AD users to FortiGate remote user groups).
    *   Loading external/domain certificates into FortiGate to properly secure the SP-IdP metadata exchange.

## 📌 Chapter 7: SSL VPN & RADIUS Setup
*   **Topic:** SSL VPN and RADIUS Policies (SSLVPN与L2LVPN / RADIUS)
*   **Key Highlights:**
    *   Leveraging FortiAuthenticator to serve RADIUS authentication for SSL VPN clients.
    *   Creating specific User Group schemes on the FAC to manage access types:
        *   Full-Tunnel Access
        *   Split-Tunnel Access
        *   Web-Only Access
    *   Injecting custom Fortinet RADIUS attributes (`Fortinet-Group-Name`) so FortiGate knows which tunnel profile to assign upon connection.

## 📌 Chapter 8: SSL VPN Connectivity & Testing
*   **Topic:** SSL VPN End-User Testing
*   **Key Highlights:**
    *   Launching FortiClient to test the RADIUS/SSL VPN configurations.
    *   Validating the **Full Tunnel** setup (verifying that all traffic routes to the Corporate Gateway; internet drops if unauthorized). 
    *   Validating the **Split Tunnel** setup (verifying that internal domain `site1.qytang.com` routes over VPN, while public traffic like `baidu.com` routes locally via the ISP).
    *   Analyzing SSL VPN tunnel logs and connection events on FortiGate and authentication events on FortiAuthenticator.

## 📌 Chapter 9: L2L VPN & Routing (OSPF)
*   **Topic:** Site-to-Site VPN and Dynamic Routing (SSLVPN与L2LVPN / 路由)
*   **Key Highlights:**
    *   Validating internal routing using OSPF. `get router info ospf neighbor` CLI diagnostics over tunnels.
    *   Setting up static routes on the Secure Web Gateway (SWG) to ensure traffic can be directed back to the SSL VPN IP pool.
    *   Configuring a robust IPsec Site-to-Site VPN using the IPsec Wizard between distinct sites (Site 2 and Site 3).
    *   Adjusting firewall policies so Remote Access (SSL VPN) users can traverse cross-site to access resources mapped to another branch network.

## 📌 Chapter 10: FSSO & Secure Web Gateway (SWG)
*   **Topic:** Fortinet Single Sign-On & SWG Explicit Proxy (SWG / FSSO)
*   **Key Highlights:**
    *   Enabling the SWG (Secure Web Gateway) appliance to rely on centralized identity via FSSO.
    *   Connecting the SWG to FAC's FSSO agent service to extract real-time user login data.
    *   Enabling the **Explicit Proxy** feature in FortiOS (requiring CLI setup `config system settings`, `set gui-proxy-inspection enable` first).
    *   Creating Authentication Schemes utilizing FSSO, to seamlessly filter web proxy traffic based on authenticated AD user profiles.
