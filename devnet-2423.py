print """
 _____    _             _   _                  _    ____ ___
|_   _|__| |_ _ __ __ _| |_(_) ___  _ __      / \  |  _ \_ _|
  | |/ _ \ __| '__/ _` | __| |/ _ \| '_ \    / _ \ | |_) | |
  | |  __/ |_| | | (_| | |_| | (_) | | | |  / ___ \|  __/| |
  |_|\___|\__|_|  \__,_|\__|_|\___/|_| |_| /_/   \_\_|  |___|

  ===========================================================
 ____  _______     ___   _ _____ _____   ____  _  _  ____  _____
|  _ \| ____\ \   / / \ | | ____|_   _| |___ \| || ||___ \|___ /
| | | |  _|  \ \ / /|  \| |  _|   | |     __) | || |_ __) | |_ \\
| |_| | |___  \ V / | |\  | |___  | |    / __/|__   _/ __/ ___) |
|____/|_____|  \_/  |_| \_|_____| |_|   |_____|  |_||_____|____/

Tim Garner <tigarner@cisco.com>
Remi Philippe <rephilip@cisco.com>

https://github.com/tetration-exchange/devnet-2423/
"""

# Import Tetration client
from tetpyclient import RestClient
import json
import os, sys
import requests.packages.urllib3

from datetime import datetime
from datetime import timedelta

from flask import Flask
from flask import Response
from flask import request
app = Flask(__name__)

API_ENDPOINT = "https://markv.insbu.net"
CRED_FILE = "./api_credentials_markv.json"

# I hate implementing try catch everywhere, will create a wrapper function
# this function only implements some basic verifications
def query(method, endpoint, payload=""):
    try:
        if method == "POST":
            resp = rc.post(endpoint, json_body=json.dumps(payload))
        elif method == "GET":
            resp = rc.get(endpoint)

        if resp.status_code != 200:
            raise Exception("Status Code - " + str(resp.status_code) + "\nError - " + resp.text +"\n")
    except Exception as e:
        print e
        #sys.exit(1)

    if resp.status_code == 200:
        return resp.json()

# Might be useful to connect somewhere, we'll put all the connect logic here
def connect():
    # Check credentials file exists
    if os.path.exists(CRED_FILE) == False:
        sys.exit(
            "Error! Credentials file is not present"
        )
    requests.packages.urllib3.disable_warnings()

    # Class Constructor
    rc = RestClient(API_ENDPOINT, credentials_file=CRED_FILE, verify=False)
    return rc

def get_sensors():
    sensors = {}
    # DEVNET Code Start, tag=sensors
    all_sensors = query("GET", "/sensors")
    for s in all_sensors['results']:
        # I don't care about the Tetration hosts for now, let's ignore them
        if not any(d.get('vrf', None) == 'Tetration' for d in s['interfaces']):
            sensors[s['uuid']] = {
                "hostname": s['host_name'],
                "uuid": s['uuid'],
                "interfaces": list(map(lambda x: {"ip": x['ip'], "type": x['family_type'], "vrf": x['vrf'], "mac": x['mac']}, s['interfaces'])),
            }
    # DEVNET Code End
    return sensors

def get_application(app_id):
    retval = {}
    # DEVNET Code Start, tag=application
    # let's get the app details...
    details = query("GET", "/applications/" + app_id + "/details")

    # ...and the scope details...
    scope = query("GET", "/app_scopes/" + details['app_scope_id'])

    # what are my external dependencies?
    d = details.get('inventory_filters')
    if d == None:
        d = []
    # this can also be written as details.get('inventory_filters', [])

    # who is part of my application?
    c = details.get('clusters')
    if c == None:
        c = []
    # this can also be written as details.get('clusters', [])

    # make it pretty!
    retval = {
        "scope": {k: v for k, v in scope.iteritems() if k == "id" or k == "name" or k == "parent_app_scope_id"},
        "name": details['name'],
        "id": app_id,
        "external": list(map(lambda x: {"id": x['id'], "name": x['name']}, d)),
        "clusters": list(map(lambda x: {"id": x['id'], "name": x['name'], "external": x['external'], "nodes": x['nodes']}, c))
    }
    # DEVNET Code End
    return retval

def get_flows(search_query, offset=""):
    res = []
    # DEVNET Code Start, tag=flows
    if not offset:
      search_query['offset'] = offset

    flows = query("POST", "/flowsearch", search_query)
    if flows['results'] == None:
        return []

    res = flows['results']

    if "offset" in flows:
        res += get_flows(search_query, flows['offset'])
    # DEVNET Code End
    return res

def get_stats(flows):
    metrics = {}
    # DEVNET Code Start, tag=stats
    metrics = {
        "rev_pkts": sum([f.get('rev_pkts') for f in flows]),
        "fwd_pkts": sum([f.get('fwd_pkts') for f in flows]),
        "rev_bytes": sum([f.get('rev_bytes') for f in flows]),
        "fwd_bytes": sum([f.get('fwd_bytes') for f in flows]),
    }
    # DEVNET Code End
    return metrics

####
# All this is just web presentation using flask
####

# Routes
@app.route('/')
def root():
  return app.send_static_file('index.html')

@app.route('/<path:path>')
def static_proxy(path):
  # send_static_file will guess the correct MIME type
  return app.send_static_file(path)

@app.route("/api/v1/flows", methods=['POST'])
def api_get_flows():
    now = datetime.now()
    t1 = now # - timedelta(minutes=360)
    t0 = t1 - timedelta(hours=1)

    src_scope_name = request.get_json().get('src_scope')
    dst_scope_name = request.get_json().get('dst_scope')
    src_hostname = request.get_json().get('src_hostname')
    dst_hostname = request.get_json().get('dst_hostname')
    src_port = request.get_json().get('src_port')
    dst_port = request.get_json().get('dst_port')

    if request.get_json().get('stats'):
        stats = True
    else:
        stats = False

    search_query = {
      "t0": t0.strftime('%s'),
      "t1": t1.strftime('%s'),
      #"scopeID": str("594f4f4c755f02573d146bc2"),
      #"limit": 10,
      "filter": {
        "type": "and",
        "filters": []
        }
    }

    if src_scope_name is not None:
        search_query['filter']['filters'].append({
            "type": "eq",
            "field": "src_scope_name",
            "value": src_scope_name
        })

    if dst_scope_name is not None:
        search_query['filter']['filters'].append({
            "type": "eq",
            "field": "dst_scope_name",
            "value": dst_scope_name
        })

    if src_hostname is not None:
        search_query['filter']['filters'].append({
            "type": "eq",
            "field": "src_hostname",
            "value": src_hostname
        })

    if dst_hostname is not None:
        search_query['filter']['filters'].append({
            "type": "eq",
            "field": "dst_hostname",
            "value": dst_hostname
        })

    if src_port is not None:
        search_query['filter']['filters'].append({
            "type": "eq",
            "field": "src_port",
            "value": src_port
        })

    if dst_port is not None:
        search_query['filter']['filters'].append({
            "type": "eq",
            "field": "dst_port",
            "value": dst_port
        })

    #print json.dumps(search_query)
    flows = get_flows(search_query, offset="")
    if stats:
        metrics = get_stats(flows)
        return Response(json.dumps(metrics), mimetype='application/json')
    else:
        return Response(json.dumps(flows), mimetype='application/json')

@app.route("/api/v1/sensors", methods=['GET'])
def api_get_sensors():
    # get all our sensors
    sensors = get_sensors()

    return Response(json.dumps(sensors), mimetype='application/json')

@app.route("/api/v1/application/<app_id>", methods=['GET'])
def api_get_application(app_id):
    app = []
    current_app = get_application(app_id)
    app.append(current_app)

    return Response(json.dumps(app), mimetype='application/json')


@app.route("/api/v1/applications", methods=['GET'])
def api_get_applications():
    # get all our application
    all_applications = query("GET", "/applications")
    app = []
    for a in all_applications:
        if a['primary'] == True:
            current_app = get_application(a['id'])
            app.append(current_app)

    return Response(json.dumps(app), mimetype='application/json')

# establish a global connection
rc = connect()
