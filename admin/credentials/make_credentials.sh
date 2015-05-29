#!/bin/bash
echo "This will delete all existing .crt and .key files in your working directory, proceed? (y/n)"
read -t 10 -n 1 key
if [[ $key = y ]]
then
    rm *.crt *.key
    rm -rf node1/
    rm -rf node2/
else
    echo ""
    echo "Exiting with no action."
    exit 0
fi
echo ""
read -p "Enter hostname / IP address of control service: " ip
flocker-ca initialize tutorialcluster
flocker-ca create-control-certificate $ip
mkdir node1
mkdir node2
flocker-ca create-node-certificate -o ./node1/
mv ./node1/*.crt ./node1/node1.crt
mv ./node1/*.key ./node1/node1.key
flocker-ca create-node-certificate -o ./node2/
mv ./node2/*.crt ./node2/node2.crt
mv ./node2/*.key ./node2/node2.key
flocker-ca create-api-certificate user
echo ""
echo "Done."
