#!/bin/bash

# This script creates a simple IPTables POSTROUTING scenario.
# In this scenario, the final execution should end without any change
# given that there would be EXTERNAL_IP on top of the POSTROUTING chain already.

iptables -t nat -F POSTROUTING #< Flushing the current NAT rule

iptables -w -t nat -I POSTROUTING -j MASQUERADE
iptables -w -t nat -I POSTROUTING -j EXTERNAL_IP

/scripts/nomad-extip-manager.sh

# Let's check the iptables status.
iptables -t nat -L POSTROUTING -n -v
