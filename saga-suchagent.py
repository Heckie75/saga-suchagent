#!/usr/bin/python3
# -*- coding: utf-8 -*-
import argparse
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import urllib3
from bs4 import BeautifulSoup
from mako.template import Template

template = """
<html>
<body>
<h1>Aktuelle Saga Angebote</h1>
% for o in objects:
    <h2>${o["title"]}</h2>

    % if o["thumbnail"] is not None:
    <a href="${o["href"]}">
        <img src="${o["thumbnail"]}" alt="${o["id"]} - ${o["title"]}">
    </a>
    <br>
    % endif
    <a href="${o["href"]}">${o["id"]}</a>
<%
summary = o["short_descr"].replace("\\n", "<br>\\n")
%>
    <p>
    ${summary}
    </p>

<%
addresse = o["details"]["descr"].replace("\\n", "<br>\\n")

if o["details"]["coords"] and len(o["details"]["coords"]) > 0:
  lat = o["details"]["coords"][0]["lat"]
  lng = o["details"]["coords"][0]["lng"]
  maps = "geo:%s,%s" % (lat, lng)
  google_maps = "https://www.google.com/maps/search/%s,%s" % (lat, lng)
  osm = "http://www.openstreetmap.org/?mlat=%s&mlon=%s&zoom=14" % (lat, lng)
else:
   maps = None
   google_maps = None
   osm = None
%>

    <h3>Adresse</h3>
	<p>
    ${addresse}

% if maps:
    <br><br><a href="${maps}">Karte</a>&nbsp;&nbsp;&nbsp;<a href="${google_maps}">Google Maps</a>&nbsp;&nbsp;&nbsp;<a href="${osm}">Open Street Map</a>
% endif
    </p>

    % if o["details"]["properties"] and len(o["details"]["properties"]) > 0:
    <table>
    % for p in o["details"]["properties"]:
        <tr>
            <td><b>${p["key"]}</b></td>
            <td>${p["text"]}</td>
        </tr>
    % endfor
    </table>
    % endif

    % for a in o["details"]["additions"]:
    <h3>${a["key"]}</h3>
    <p>${a["text"]}</p>
    % endfor

    % for i in o["details"]["images"]:
        <p>
            <img src="${i["img"]}" alt="${i["alt"]}">
            <br>
            <sup>${i["alt"]}</sup>
        </p>
    % endfor

    % if o["details"]["area"] and len(o["details"]["area"]) > 0:
    <h3>Lagebeschreibung<h3>
    % for a in o["details"]["area"]:
    <h4>${a["key"]}</h4>
    <p>${a["text"]}</p>
    % endfor
    % endif

    % if "application" in o:
    <h3>Bewerbung</h3>
    <table>
        <tr><td>Anrede</td><td>${o["application"]["contact"]["salutation"]}</td></tr>
        <tr><td>Vorname</td><td>${o["application"]["contact"]["surname"]}</td></tr>
        <tr><td>Name</td><td>${o["application"]["contact"]["name"]}</td></tr>
        <tr><td>Straße</td><td>${o["application"]["contact"]["street"]}</td></tr>
        <tr><td>Hausnummer</td><td>${o["application"]["contact"]["number"]}</td></tr>
        <tr><td>PLZ</td><td>${o["application"]["contact"]["zip"]}</td></tr>
        <tr><td>Stadt</td><td>${o["application"]["contact"]["city"]}</td></tr>
        <tr><td>Telefon</td><td>${o["application"]["contact"]["tel"]}</td></tr>
        <tr><td>E-Mail</td><td>${o["application"]["contact"]["email"]}</td></tr>
    </table>
    <table>
        <tr><td>
            ${o["application"]["response"]}
        </td></tr>
    </table>
    % endif

    <hr>

% endfor
<small>Zusammengestellt von saga-suchagent, <a href="https://github.com/Heckie75/saga-suchagent">https://github.com/Heckie75/saga-suchagent</a><small>
</body>
</html>
"""

csv = """\\
id\tTitel\tZimmer\tFlaeche\tGesamtmiete\tStrasse\tPLZ\tStadtteil\tOrt\tURL\terstellt\tzuletzt gesehen\\
% for o in objects:
<%
zimmer =  list(filter(lambda p: p["key"] == "Zimmer", o["details"]["properties"]))[0]["value"]
flaeche = list(filter(lambda p: p["key"] == "Wohnfl\u00e4che ca.", o["details"]["properties"]))[0]["value"]
miete = list(filter(lambda p: p["key"] == "Gesamtmiete", o["details"]["properties"]))[0]["value"]
%>
${o["id"]}\t${o["title"]}\t${zimmer}\t${flaeche}\t${miete}\t${o["details"]["address"]["street"]}\t${o["details"]["address"]["zipcode"]}\t${o["details"]["address"]["district"]}\t${o["details"]["address"]["city"]}\t${o["href"]}\t${o["first_seen"]}\t${o["last_seen"]}\\
% endfor
"""


class Saga:

    YES = "Ja"
    NO = "Nein"

    http = None
    match_obj_id = None
    base_url = None
    url = None
    storage = None
    storage_path = None
    storage_changed = False
    filter = None

    application = None

    def __init__(self, settings):

        self.http = urllib3.PoolManager()
        self.match_obj_id = re.compile(".+/([0-9\.]+)")

        # apply settings
        self.url = settings["url"]
        self.base_url = re.match("((https|http)://[^/]+)", self.url).group(1)

        self.storage_path = settings["storage"]
        if self.storage_path.startswith("~"):
            self.storage_path = self.storage_path.replace(
                "~", str(Path.home()))

        self.filter = settings["filter"]

        # load storage
        self.load_storage()

    def load_storage(self):

        try:
            data = open(self.storage_path, "r").read()
            self.storage = json.loads(data)
            self.storage_changed = False
        except FileNotFoundError:
            self.storage = {}
        except ValueError:
            self.storage = {}

    def store_json(self):

        if self.storage_changed == False:
            return

        try:
            f = open(self.storage_path, "w")
            f.write(json.dumps(self.storage, indent=2))
            f.close()
            self.storage_changed = False
        except FileNotFoundError:
            self.storage = {}

    def parse_objects_from_listing(self):

        objects = []

        request = self.http.request("GET", self.url)
        try:
            data = request.data.decode('utf-8')
        except:
            data = request.data.decode('latin-1')

        soup = BeautifulSoup(data, 'html.parser')

        for div in soup.find_all('div', attrs={"class": re.compile("teaser3 teaser3--listing.*")}):

            _obj_id = self.match_obj_id.match(div.a["href"])

            if div.find("img"):
                _thumbnail = self.base_url + div.find("img")["src"]
            else:
                _thumbnail = None

            objects.append(
                {
                    "id": _obj_id.group(1),
                    "ref": _obj_id.group(1).split("."),
                    "title": div.a.h3.text,
                    "thumbnail": _thumbnail,
                    "href": self.base_url + div.a["href"],
                    "short_descr": div.p.text.strip(),
                    "details": None,
                    "first_seen": None,
                    "last_seen": None
                }
            )

        return objects

    def process_objects(self, objects, current=False):

        def _now():
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        current_objects = []

        for o in objects:

            if o["id"] in self.storage:

                if current or datetime.strptime(self.storage[o["id"]]["last_seen"], "%Y-%m-%d %H:%M:%S") < datetime.now() - timedelta(days=7):
                    current_objects.append(self.storage[o["id"]])

                self.storage[o["id"]]["last_seen"] = _now()

            else:
                details = self.parse_details(o["href"])
                o["details"] = details
                o["first_seen"] = _now()
                o["last_seen"] = o["first_seen"]
                self.storage[o["id"]] = o
                current_objects.append(o)

            self.storage_changed = True

        return current_objects

    def parse_details(self, url):

        def _parse_descr(descr):

            address = {
                "street": None,
                "zipcode": None,
                "city": None,
                "district": None
            }

            lines = descr.split("\n")
            if len(lines) > 1:
                address["street"] = lines[0]
                ccq = lines[1].strip().split(" ")
                if len(ccq) >= 2:
                    address["zipcode"] = ccq[0]
                    address["city"] = ccq[1]

                if len(ccq) == 3 and ccq[2][0] == "(" and ccq[2][-1] == ")":
                    address["district"] = ccq[2][1:-1]

            return address

        def _parse_coordinates(s):

            matcher = re.compile(
                ".*var points =(\[[^\]]+\]).*", flags=re.MULTILINE | re.DOTALL)
            matches = matcher.match(s)
            if matches:
                return json.loads(matches.group(1))
            else:
                return None

        def _convert_property(key, value):

            _convertable_props = ["Netto-Kalt-Miete", "Betriebskosten",
                                  "Heizkosten", "Gesamtmiete", "Zimmer", "Wohnfl\u00e4che ca.", "Etage"]

            def _converter(s):
                s = s.replace(" 1/2", ",5")
                match = re.match(r"([0-9\.,]+).*", s)
                return float(match.group(1).replace(".", "").replace(",", ".")) if match else 0

            if value in [self.YES, self.NO]:
                return value == self.YES
            elif key in _convertable_props:
                return _converter(value)
            else:
                return value

        details = {
            "descr": "",
            "address": None,
            "coords": None,
            "images": [],
            "properties": [],
            "additions": [],
            "area": []
        }

        request = self.http.request("GET", url)
        data = request.data.decode('utf-8')
        soup = BeautifulSoup(data, 'html.parser')

        # image gallery
        _image_gallery = soup.find(
            "div", attrs={"class": "image-gallery-slider-wrapper"})
        if _image_gallery:
            for _item in _image_gallery.find_all("a", attrs={"class": re.compile("rsImg.*")}):
                details["images"].append(
                    {
                        "img": self.base_url + _item["href"],
                        "alt": _item.img["alt"] if _item.img.has_attr("alt") else ""
                    }
                )

        # geo daten
        _script = soup.find("script", text=re.compile(".+var points ="))
        if _script and len(_script.contents) == 1:
            details["coords"] = _parse_coordinates(_script.contents[0])

        # Objektbeschreibung
        _objektbeschreibung = soup.find("h2").findNext("p")
        if _objektbeschreibung:
            details["descr"] = _objektbeschreibung.text.strip()
            details["address"] = _parse_descr(details["descr"])

        # Fakten
        props = soup.find("dl", attrs={"class": "dl-props"})
        key = ""
        for prop in props.find_all():
            if prop.name == "dt":

                key = prop.text

            elif prop.name == "dd":

                text = prop.text
                if text == "" and prop.has_attr("class"):
                    text = self.YES if (
                        prop["class"] == "checked") else self.NO

                value = _convert_property(key, text)

                details["properties"].append(
                    {
                        "key": key,
                        "text": text,
                        "value": value
                    }
                )
                key = ""

        # Sonstiges
        for h3 in soup.findAll("h3"):
            details["additions"].append(
                {
                    "key": h3.text,
                    "text": h3.findNext("p").text
                }
            )

        # Lagebeschreibung
        for h6 in soup.find("h4").findAllNext("h6"):
            details["area"].append(
                {
                    "key": h6.text,
                    "text": h6.findNext("p").text
                }
            )

        return details

    def apply_filter(self, objects, filter=filter):

        if filter is None:
            return objects

        filtered_objects = []

        def _traverse(object, subfilter):

            keep = True
            for key in subfilter.keys():
                if key in object:
                    if type(object[key]) is dict:

                        keep = _traverse(object[key], subfilter[key])

                    elif type(object[key]) is list:

                        for _f in subfilter[key]:
                            _k = False
                            for _o in object[key]:
                                _k |= _traverse(_o, _f)
                            if not _k:
                                keep = False
                                break

                    elif type(object[key]) is str:

                        keep = re.match(
                            subfilter[key], object[key]) is not None

                    elif type(object[key]) in [int, float] and type(subfilter[key]) in [int, float]:

                        keep = float(object[key]) == float(subfilter[key])

                    elif type(object[key]) in [int, float] and type(subfilter[key]) is list:

                        if len(subfilter[key]) == 1:
                            keep = float(object[key]) == float(
                                subfilter[key][0])
                        elif len(subfilter[key]) == 2:
                            keep = float(object[key]) >= float(subfilter[key][0]) and float(
                                object[key]) <= float(subfilter[key][1])

                    if not keep:
                        break

            return keep

        for obj in objects:

            keep = _traverse(obj, filter)
            if keep:
                filtered_objects.append(obj)

        return filtered_objects

    def send_application(self, objects):

        for o in objects:

            fields = {
                "property_contact[object]": o["id"],
                "property_contact[type]": self.application["type"],
                "property_contact[salutation]": self.application["contact"]["salutation"],
                "property_contact[name]": self.application["contact"]["name"],
                "property_contact[surname]": self.application["contact"]["surname"],
                "property_contact[street]": self.application["contact"]["street"],
                "property_contact[number]": self.application["contact"]["number"],
                "property_contact[zip]": self.application["contact"]["zip"],
                "property_contact[city]": self.application["contact"]["city"],
                "property_contact[tel]": self.application["contact"]["tel"],
                "property_contact[email]": self.application["contact"]["email"],
                "property_contact[privacynote]": "1",
                "formid": self.application["formid"]
            }

            headers = {
                'cookie': "cookie-has-decided=1; marketing-cookies-disabled=0",
                'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0",
                'host': "www.saga.hamburg",
                'accept': "*/*",
                'accept-language': "de,en-US;q=0.7,en;q=0.3",
                'accept-encoding': "gzip, deflate, br",
                'content-type': "application/x-www-form-urlencoded; charset=UTF-8",
                'x-requested-with': "XMLHttpRequest",
                'origin': "https://www.saga.hamburg",
                'dnt': "1",
                'connection': "keep-alive",
                'referer': "https://www.saga.hamburg/objekt/wohnungen/%s" % o["id"],
                'sec-fetch-dest': "empty",
                'sec-fetch-mode': "cors",
                'sec-fetch-site': "same-origin",
                'te': "trailers"
            }

            response = self.http.request(
                method="POST", url=self.application["url"] % o["id"], headers=headers, fields=fields)

            o["application"] = {
                "contact": self.application["contact"],
                "response": response.data.decode('utf-8')
            }


if __name__ == "__main__":

    # args
    parser = argparse.ArgumentParser(
        description="Überwache Saga Wohnungsangebote")
    parser.add_argument("settings", help="Angabe der Datei mit Einstellungen")
    parser.add_argument(
        "--json", "-j", help="Ausgabe als JSON anstelle von HTML", action='store_true')
    parser.add_argument(
        "--csv", help="Ausgabe als CSV anstelle von HTML", action='store_true')
    parser.add_argument(
        "--current", "-c", help="Ausgabe derzeitig gelistete Angebote anstatt nur neue", action='store_true')
    parser.add_argument(
        "--unfiltered", "-u", help="Wende Filter nicht an", action='store_true')
    parser.add_argument(
        "--all", "-a", help="Verwende alle Angebote des Storage", action='store_true')
    parser.add_argument(
        "--empty", "-e", help="Lösche Immobilien im Storage", action='store_true')
    parser.add_argument(
        "--formular", "-f", help="Sende Formular für Bewerbung", action='store_true')
    parser.add_argument(
        "--transient", "-t", help="Speichere Immobilien nicht im Storage", action='store_true')
    args = parser.parse_args()

    # load settings
    try:
        data = open(args.settings, "r").read()
        settings = json.loads(data)
    except FileNotFoundError:
        logging.log(logging.ERROR, "Setting file not found")
        exit(1)
    except ValueError:
        logging.log(logging.ERROR, "Setting file not valid")
        exit(1)

    saga = Saga(settings)

    if args.empty:
        saga.storage = {}

    objects_from_listing = saga.parse_objects_from_listing()
    objects_to_report = saga.process_objects(
        objects_from_listing, args.current)

    if not args.transient:
        saga.store_json()

    if args.all:
        objects_to_report = [o for o in saga.storage.values()]

    if settings["filter"] and not args.unfiltered:
        objects_to_report = saga.apply_filter(
            objects_to_report, settings["filter"])

    if args.formular:
        saga.send_application(objects_to_report)

    if args.json:
        # Ausgabe als JSON
        print(json.dumps(objects_to_report, indent=2))
    elif args.csv:
        # Ausgabe als CSV
        t = Template(csv)
        print(t.render(objects=objects_to_report))
    elif len(objects_to_report) > 0:
        # Ausgabe als HTML
        t = Template(template)
        print(t.render(objects=objects_to_report))
