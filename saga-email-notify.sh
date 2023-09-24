#!/usr/bin/bash
DIR="$(dirname "$0")"

if [ $# -lt 3 ]
then
  echo -e "
Saga Immobilien Suchagent mit E-Mailversand bei neuen Angeboten.\n\
\n\
Usage: \n\
  ./saga-email-notify.sh <settings file> <email address> <tmp folder>\n\
\n\
Example: \n\
  ./saga-email-notify.sh settings.json your-email@mail.com /tmp\n\
"
  exit 1
fi

TMP_FILE="$3/saga-suchagent.html"

# $DIR/saga-suchagent.py $1 --formular > ${TMP_FILE}
$DIR/saga-suchagent.py $1 > ${TMP_FILE}

if [ -s ${TMP_FILE} ]
then
   cat ${TMP_FILE} | recode UTF-8..ISO-8859-2 | mail -a "Content-Type: text/html; charset=ISO-8859-2; format=flowed" -s "Aktuelle Saga Angebote" $2
   /opt/signal-cli/bin/signal-cli send -m "Neue Saga Angebote" --note-to-self > /dev/null
fi
rm -f ${TMP_FILE}
