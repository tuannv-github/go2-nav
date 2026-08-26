#!/bin/bash

source common.sh

cmd="ss -tulnp | grep $SERVER_PORT"
echo "$cmd"

eval "$cmd"
