#!/bin/bash

# This script creates a simple IPTables POSTROUTING scenario.
# In this scenario, the final execution should create new EXTERNAL_IP rule with signature
# and delete the legacy EXTERNAL_IP (w/ signature NEIM:1234) created in the script below.

iptables -t nat -F POSTROUTING #< Flushing the current NAT rule

iptables -w -t nat -I POSTROUTING -m comment --comment "NEIM:1234" -j EXTERNAL_IP 
iptables -w -t nat -I POSTROUTING -j MASQUERADE

/scripts/nomad-extip-manager.sh

# Let's check the iptables status.
iptables -t nat -L POSTROUTING -n -v