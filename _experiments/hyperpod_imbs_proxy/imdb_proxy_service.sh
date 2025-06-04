#!/bin/bash

iptables -t nat -D OUTPUT -d 169.254.169.254 -p tcp --dport 80 -j DNAT --to-destination 169.254.0.2:9081
iptables -t nat -D OUTPUT -d 169.254.169.254 -p tcp --dport 80 -m owner --uid-owner 0 -j DNAT --to-destination 169.254.0.2:9081
iptables -t nat -D OUTPUT -d 169.254.169.254 -p tcp --dport 80 -m owner ! --uid-owner 0 -j DNAT --to-destination 127.0.0.1:8080

iptables -t nat -I OUTPUT 1 -d 169.254.169.254 -p tcp --dport 80 -m owner --uid-owner 0 -j DNAT --to-destination 169.254.0.2:9081
iptables -t nat -I OUTPUT 1 -d 169.254.169.254 -p tcp --dport 80 -m owner ! --uid-owner 0 -j DNAT --to-destination 127.0.0.1:8080

iptables -t nat -L OUTPUT --line-numbers
