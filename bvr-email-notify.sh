#!/usr/bin/bash
DIR="$(dirname "$0")"

if [ $# -lt 3 ]
then
  echo -e "
Bauverein Rüstringen Suchagent mit E-Mailversand bei neuen Angeboten.\n\
\n\
Usage: \n\
  ./bvr-email-notify.sh <settings file> <email address> <tmp folder>\n\
\n\
Example: \n\
  ./bvr-email-notify.sh settings.json your-email@mail.com /tmp\n\
"
  exit 1
fi

TMP_FILE="$3/bvr-suchagent.html"

$DIR/bvr-suchagent.py $1 > ${TMP_FILE}

if [ -s ${TMP_FILE} ]
then
   cat ${TMP_FILE} | recode UTF-8..ISO-8859-2 | mail -a "Content-Type: text/html; charset=ISO-8859-2; format=flowed" -s "Aktuelle Bauverein Ruestringen Angebote" $2
fi
rm -f ${TMP_FILE}
