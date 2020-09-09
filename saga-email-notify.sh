#!/usr/bin/bash
DIR="$(dirname "$0")"
$DIR/saga-suchagent.py "https://www.saga.hamburg/immobiliensuche" > /tmp/saga-suchagent.html

if [ -s "/tmp/saga-suchagent.html" ]
then 
   cat /tmp/saga-suchagent.html | recode UTF-8..ISO-8859-2 | mail -a "Content-Type: text/html; charset=ISO-8859-2; format=flowed" -s "Aktuelle Saga Angebote" $1
fi