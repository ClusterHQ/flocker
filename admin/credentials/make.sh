#!/bin/bash
echo "This will delete all existing .crt and .key files in your working directory, proceed? (y/n)"
read -t 10 -n 1 key
if [[ $key = y ]]
then
    rm *.crt *.key
else
    echo ""
    echo "Exiting with no action."
    exit 0
fi
echo ""
read -p "Enter hostname / IP address of control service: " ip
flocker-ca initialize tutorialcluster
flocker-ca create-control-certificate $ip
flocker-ca create-node-certificate
flocker-ca create-node-certificate
flocker-ca create-api-certificate user
echo ""
echo "Done."
