from urllib.parse import urlencode

import requests

URL = "http://api.conceptnet.io/c/en/{}?"

_RELATED_LOCATION_ARGUMENTS = {
    "rel": "/r/AtLocation",
    "limit": 100
}
_DEFAULT_ARGUMENTS = {
    "limit": 200
}


def _get_data(word, arguments=None):
    if not arguments:
        arguments = _DEFAULT_ARGUMENTS
    url = URL.format(word) + urlencode(arguments, False, "/")
    return requests.get(url).json()


def _get_edges(word, arguments=None):
    return _get_data(word, arguments)["edges"]


def get_related_locations(word):
    edges = _get_edges(word, _RELATED_LOCATION_ARGUMENTS)
    locations = [_get_weight_and_label(edge) for edge in edges if edge["rel"]["label"] == "AtLocation"]
    # pp.pprint(locations)
    return locations


def _get_weight_and_label(edge):
    return edge["weight"], edge["end"]["label"]


print(get_related_locations("cat"))
