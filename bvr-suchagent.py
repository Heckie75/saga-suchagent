#!/usr/bin/python3
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import urllib3
from bs4 import BeautifulSoup
from mako.template import Template

template = """
<html>
<body>
<h1>Aktuelle Angebote vom Bauverein Rüstringen</h1>
% for o in objects:
    <h2>${o["title"]}</h2>
    <p>${o["short_descr"]}</p>

    % if o["thumbnail"] is not None:
    <a href="${o["href"]}">
        <img src="${o["thumbnail"]}" alt="${o["id"]} - ${o["title"]}">
    </a>
    <br>
    % endif
    <a href="${o["href"]}">${o["id"]}</a>

    <h3>Adresse</h3>
	<p>
    ${o["details"]["address"]["street"]}<br/>
    ${o["details"]["address"]["zipcode"]} ${o["details"]["address"]["city"]}
    </p>
    <p>
    ${o["details"]["area"]}
    </p>

    ${o["details"]["descr"]}

    % if o["details"]["properties"] and len(o["details"]["properties"]) > 0:
    <h3>Objektdaten</h3>
    <table>
    % for p in o["details"]["properties"]:
        <tr>
            <td><b>${p["key"]}</b></td>
            <td>${p["text"]}</td>
        </tr>
    % endfor
    </table>
    % endif

    % if o["details"]["features"] and len(o["details"]["features"]) > 0:
    <h3>Ausstattung / Merkmale</h3>
    <ul>
    % for a in o["details"]["features"]:
    <li>${a}</li>
    % endfor
    </ul>
    % endif

    % if o["details"]["energy"] and len(o["details"]["energy"]) > 0:
    <h3>Energieausweis</h3>
    <table>
    % for p in o["details"]["energy"]:
        <tr>
            <td><b>${p["key"]}</b></td>
            <td>${p["text"]}</td>
        </tr>
    % endfor
    </table>
    % endif

    % for i in o["details"]["images"]:
        <p>
            <img src="${i["img"]}">
        </p>
    % endfor

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
zimmer =  list(
    filter(lambda p: p["key"] == "Zimmer", o["details"]["properties"]))[0]["value"]
flaeche = list(filter(
    lambda p: p["key"] == "Wohnfl\u00e4che ca.", o["details"]["properties"]))[0]["value"]
miete = list(filter(lambda p: p["key"] == "Gesamtmiete",
             o["details"]["properties"]))[0]["value"]
%>
${o["id"]}\t${o["title"]}\t${zimmer}\t${flaeche}\t${miete}\t${o["details"]["address"]["street"]}\t${o["details"]["address"]["zipcode"]}\t${o["details"]["address"]["district"]}\t${o["details"]["address"]["city"]}\t${o["href"]}\t${o["first_seen"]}\t${o["last_seen"]}\\
% endfor
"""


class Bvr:

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

    def __init__(self, settings):

        self.http = urllib3.PoolManager()
        self.match_obj_id = re.compile("^.*-in-wilhelmshaven-mieten-(\d+-?\w*)/$")

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
        soup = BeautifulSoup(data, "html.parser")

        for div in soup.find_all("div", attrs={"class": "property"}):

            _a = div.find("a", attrs={"class": "thumbnail"})
            if _a.find("img"):
                _thumbnail = _a.find("img")["src"]
            else:
                _thumbnail = None

            _div_details = div.find("div", attrs={"class": "property-details"})

            objects.append(
                {
                    "id": self.match_obj_id.match(_a["href"]).group(1),
                    "title": _div_details.find("a").text,
                    "thumbnail": _thumbnail,
                    "href": _a["href"],
                    "short_descr": _div_details.find("div", attrs={"class": "property-subtitle"}).text.strip(),
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

        def _parse_address(h2):

            match = re.match(r"^([^,]+), ([0-9]+) ([^,]+)(, )?(.*)$", h2)
            address = {
                "street": match.group(1).strip() if match else "",
                "zipcode": match.group(2).strip() if match else "",
                "city": match.group(3).strip() if match else ""
            }

            return address

        def _read_table(_table):

            rv = []

            for prop in _table.find_all("li", attrs={"class": "list-group-item"}):
                key = ""
                for _div in prop.find_all("div", attrs={"class", re.compile("(dt|dd).*")}):
                    if _div["class"][0].startswith("dt"):

                        key = _div.text.strip()

                    elif _div["class"][0].startswith("dd"):

                        text = _div.text.strip()
                        value = _convert_property(key, text)
                        rv.append(
                            {
                                "key": key,
                                "text": text,
                                "value": value
                            }
                        )
                        key = ""

            return rv

        def _convert_property(key, value):

            _convertable_props = ["Etage", "Etagen im Haus", "Wohnfl\u00e4che\u00a0ca.", "Zimmer", "Schlafzimmer",
                                  "Badezimmer", "Baujahr", "Kaution", "Kaltmiete", "Nebenkosten", "Endenergie­verbrauch"]

            def _converter(s):
                s = s.replace(" 1/2", ",5")
                match = re.match(r"([0-9\.,]+).*", s)
                return float(match.group(1).replace(".", "").replace(",", ".")) if match else 0

            if key in _convertable_props:
                return _converter(value)
            else:
                return value

        details = {
            "title": "",
            "descr": "",
            "address": None,
            "area": "",
            "images": [],
            "properties": [],
            "features": [],
            "energy": []
        }

        request = self.http.request("GET", url)
        data = request.data.decode('utf-8')
        soup = BeautifulSoup(data, 'html.parser')

        # image gallery
        _image_gallery = soup.find("div", attrs={"id": "immomakler-galleria"})
        if _image_gallery:
            for _a in _image_gallery.find_all("a"):
                details["images"].append(
                    {
                        "img": _a["href"]
                    }
                )

        # Objektbeschreibung
        details["title"] = soup.find("h1").text.strip()
        details["descr"] = "".join([str(_e) for _e in soup.find("div", attrs={
                                   "class": "property-description panel panel-default"}).find("div", attrs={"class": "panel-body"}).find_all()])
        details["address"] = _parse_address(soup.find("h2").text)
        details["area"] = "".join([str(_e) for _e in soup.find("div", attrs={
                                   "class": "property-map panel panel-default"}).find("div", attrs={"class": "panel-body"}).find_all("p")])

        # Objektdaten
        details["properties"] = _read_table(
            soup.find("div", attrs={"class": "property-details panel panel-default"}))

        # E-Pass
        details["energy"] = _read_table(
            soup.find("div", attrs={"class": "property-epass panel panel-default"}))

        # Merkmale
        _features = soup.find(
            "div", attrs={"class": "property-features panel panel-default"})

        if _features:
            for _feature in _features.find_all("li"):
                details["features"].append(_feature.text.strip())

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


if __name__ == "__main__":

    # args
    parser = argparse.ArgumentParser(
        description="Überwache Wohnungsangebote vom Bauverein Rüstringen in Wilhelmshaven")
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

    try:
        bvr = Bvr(settings)

        if args.empty:
            bvr.storage = {}

        objects_from_listing = bvr.parse_objects_from_listing()

        objects_to_report = bvr.process_objects(
            objects_from_listing, args.current)

        if not args.transient:
            bvr.store_json()

        if args.all:
            objects_to_report = [o for o in bvr.storage.values()]

        if settings["filter"] and not args.unfiltered:
            objects_to_report = bvr.apply_filter(
                objects_to_report, settings["filter"])

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
    except Exception as ex:
        print(str(ex), file=sys.stderr)
