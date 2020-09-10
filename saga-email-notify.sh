#!/usr/bin/bash
DIR="$(dirname "$0")"
TMP_FILE="$1/saga-suchagent.html"

if [ $# -lt 2 ]
then
  echo -e "
Saga Immobilien Suchagent mit E-Mailversand bei neuen Angeboten.\n\
\n\
Usage: \n\
  ./saga-email-notify.sh <tmp folder> <email address>\n\
\n\
Example: \n\
  ./saga-email-notify.sh /tmp your-email@mail.com\n\
"
  exit 1
fi

if [ $# -eq 3 ]
then
  $DIR/saga-suchagent.py "https://www.saga.hamburg/immobiliensuche" --filter $3 > $TMP_FILE
else
  $DIR/saga-suchagent.py "https://www.saga.hamburg/immobiliensuche" > $TMP_FILE
fi


if [ -s "$TMP_FILE" ]
then 
   cat $TMP_FILE | recode UTF-8..ISO-8859-2 | mail -a "Content-Type: text/html; charset=ISO-8859-2; format=flowed" -s "Aktuelle Saga Angebote" $2
fi