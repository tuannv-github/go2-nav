#!/bin/bash

sudo ip route del 10.1.100.250/32
sudo ip route del 10.1.106.210/32
sudo ip route del 10.1.101.211/32
sudo ip route del 10.1.101.212/32
sudo ip route del 129.126.114.218/32

# GX10
sudo ip route add 10.1.100.250/32 via 192.168.1.1

# Xinmatrix
sudo ip route add 10.1.106.210/32 via 192.168.1.1
sudo ip route add 129.126.114.218/32 via 192.168.1.1

# GH81/GH82
sudo ip route add 10.1.101.211/32 via 192.168.1.1
sudo ip route add 10.1.101.212/32 via 192.168.1.1
