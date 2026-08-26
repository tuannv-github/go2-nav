#!/bin/bash

source common.sh

CMD="ssh -p $SERVER_PORT $ROBOT_USER_NAME@$SERVER_IP_ADDRESS"
echo "$CMD"

$CMD
