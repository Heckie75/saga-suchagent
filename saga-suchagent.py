#!/usr/bin/python3
import argparse
from bs4 import BeautifulSoup
from datetime import datetime
import json
import logging
from mako.template import Template
import os
from pathlib import Path
import re
import urllib3

template = """
<html>
<body>
<h1>Aktuelle Saga Angebote</h1>
% for o in objects:

    <h2>${o["title"]}</h2>

    <a href="${o["href"]}">
        <img src="${o["thumbnail"]}" alt="${o["id"]} - ${o["title"]}">
    </a>
    <br>
    <a href="${o["href"]}">${o["id"]}</a>
<%
summary = o["short_descr"].replace("\\n", "<br>\\n")
addresse = o["details"]["descr"].replace("\\n", "<br>\\n")
%>
    <p>
    ${summary}
    </p>
    <h3>Adresse</h3>
	<p>
    ${addresse}
    </p>

    <table>
    % for p in o["details"]["properties"]:
<%
if type(p["value"]) is bool:
    value = "Ja" if p["value"] else "Nein"
else:
    value = p["value"]
%>
        <tr>
            <td><b>${p["key"]}</b></td>
            <td>${value}</td>
        </tr>
    % endfor
    </table>

    % for i in o["details"]["images"]:
        <p>
            <img src="${i["img"]}" alt="${i["alt"]}">
            <br>
            <sup>${i["alt"]}</sup>
        </p>
    % endfor

    <h3>Lagebeschreibung<h3>
    % for a in o["details"]["area"]:
    <h4>${a["key"]}</h4>
    <p>${a["value"]}</p>
    % endfor

    % for a in o["details"]["additions"]:
    <h3>${a["key"]}</h3>
    <p>${a["value"]}</p>
    % endfor
    <hr>
% endfor
</body>
</html>
"""


class Saga:

    http = None
    match_obj_id = None
    base_url = None
    url = None
    storage = None
    storage_path = None

    def __init__(self, url):

        self.http = urllib3.PoolManager()
        self.match_obj_id = re.compile(".+/([0-9\.]+)")
        self.url = url

        _m_baseurl = re.match("((https|http)://[^/]+)", url)
        if _m_baseurl:
            self.base_url = _m_baseurl.group(1)
        else:
            self.base_url = ""

        self.storage_path = "%s%s.saga.json" % (str(Path.home()), os.path.sep)
        self.load_storage()

    def load_storage(self):

        try:
            data = open(self.storage_path, "r").read()
            self.storage = json.loads(data)
        except FileNotFoundError:
            self.storage = {}

    def store_json(self):

        try:
            f = open(self.storage_path, "w")
            f.write(json.dumps(self.storage, indent=2))
            f.close()
        except FileNotFoundError:
            self.storage = {}

    def parse_objects_from_listing(self):

        objects = []

        request = self.http.request("GET", self.url)
        data = request.data.decode('utf-8')
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

    def process_listing(self, objects):

        new_objects = []

        for o in objects:

            if o["id"] in self.storage:

                self.storage[o["id"]]["last_seen"] = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S")

            else:

                details = saga._parse_details(o["href"])
                o["details"] = details
                o["first_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                o["last_seen"] = o["first_seen"]
                self.storage[o["id"]] = o
                new_objects.append(o)

        return new_objects

    def _parse_details(self, url):

        details = {
            "descr": "",
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
        for _item in _image_gallery.find_all("a", attrs={"class": re.compile("rsImg.*")}):
            details["images"].append(
                {
                    "img": self.base_url + _item["href"],
                    "alt": _item.img["alt"] if _item.img.has_attr("alt") else ""
                }
            )

        # Objektbeschreibung
        _objektbeschreibung = soup.find("h2").findNext("p")
        if _objektbeschreibung:
            details["descr"] = _objektbeschreibung.text.strip()
        else:
            details["descr"] = ""

        # Fakten
        props = soup.find("dl", attrs={"class": "dl-props"})
        key = ""
        for prop in props.find_all():
            if prop.name == "dt":

                key = prop.text

            elif prop.name == "dd":

                value = prop.text
                if value == "" and prop.has_attr("class"):
                    value = (prop["class"] == "checked")

                details["properties"].append(
                    {
                        "key": key,
                        "value": value
                    }
                )
                key = ""

        # Sonstiges
        for h3 in soup.findAll("h3"):
            details["additions"].append(
                {
                    "key": h3.text,
                    "value": h3.findNext("p").text
                }
            )

        # Lagebeschreibung
        for h6 in soup.find("h4").findAllNext("h6"):
            details["area"].append(
                {
                    "key": h6.text,
                    "value": h6.findNext("p").text
                }
            )

        return details




if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Überwache Saga Wohnungsangebote')
    parser.add_argument("path", help="Die URL, die zu prüfen ist")
    args = parser.parse_args()

    saga = Saga(args.path)
    objects = saga.parse_objects_from_listing()
    new_objects = saga.process_listing(objects)
    saga.store_json()

    if len(new_objects) > 0:
        t = Template(template)
        print(t.render(objects=new_objects))
        exit(0)