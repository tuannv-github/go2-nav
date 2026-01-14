#!/bin/bash

# GX10
sudo ip route add 10.1.100.250/32 via 192.168.1.1

# Xinmatrix
sudo ip route add 10.1.101.210/32 via 192.168.1.1

# GH81/GH82
sudo ip route add 10.1.101.211/32 via 192.168.1.1
sudo ip route add 10.1.101.212/32 via 192.168.1.1
