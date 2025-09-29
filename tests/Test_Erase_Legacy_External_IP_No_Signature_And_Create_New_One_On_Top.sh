#!/bin/bash

# This script creates a simple IPTables POSTROUTING scenario.
# In this scenario, the final execution should create new EXTERNAL_IP rule with signature
# and delete the legacy EXTERNAL_IP (w/o signature) created in the script below.

iptables -t nat -F POSTROUTING #< Flushing the current NAT rule

iptables -w -t nat -I POSTROUTING -j EXTERNAL_IP
iptables -w -t nat -I POSTROUTING -j MASQUERADE

/scripts/nomad-extip-manager.sh

# Let's check the iptables status.
iptables -t nat -L POSTROUTING -n -v
