from django.shortcuts import render
from django.http import HttpResponse
from django.http import JsonResponse
from django.template import loader
from django.views.decorators.csrf import csrf_exempt
import requests
import json
import random
import os
from copy import deepcopy
from django.contrib.auth.decorators import login_required


def getSSLEnv():
    search_ssl = os.getenv("SEARCH_SSL", "False")
    search_ssl_no_verify = os.getenv("SEARCH_SSL_NO_VERIFY", "True")
    if search_ssl == "True":
        search_ssl = True
    else:
        search_ssl = False
    if search_ssl_no_verify == "True":
        search_ssl_no_verify = True
    else:
        search_ssl_no_verify = False
    scheme = "http"
    if search_ssl:
        scheme = "https"
    return (search_ssl, not search_ssl_no_verify, scheme)


# login_required(login_url='/accounts/login/')
def index(request):
    template = loader.get_template("search/index.html")
    (search_ssl, search_ssl_verify, scheme) = getSSLEnv()
    shost = os.getenv("SEARCH_HOST", "localhost")
    sport = os.getenv("SEARCH_PORT", "9090")
    context = {"search_server_url": scheme + "://" + shost + ":" + sport}
    return HttpResponse(template.render(context, request))

# login_required(login_url='/accounts/login/')
@csrf_exempt
def status(request):
    jstatus = {"status":""}
    try:
        with open("/tmp/c4i_status.json") as json_f:
            jstatus = json.load(json_f)
            json_f.close()
    except Exception as e:
        print(e)
        pass
    return JsonResponse(jstatus, safe=False)


# login_required(login_url='/accounts/login/')
@csrf_exempt
def suggester(request):
    term = request.GET.get("q", "")
    shost = os.getenv("SEARCH_HOST", "localhost")
    sport = os.getenv("SEARCH_PORT", "9090")
    (search_ssl, search_ssl_verify, scheme) = getSSLEnv()
    url = scheme + "://" + shost + ":" + sport + "/api/searching/suggest?q=" + str(term)
    response = requests.get(url, verify=search_ssl_verify)
    results = json.loads(response.content)["results"]
    suggest_table = []
    if ("suggest" in results) and ("full_text-suggest" in results["suggest"]):
        for option in results["suggest"]["full_text-suggest"]:
            for item_i in option["options"]:
                suggest_table.append({"value": item_i["text"], "data": item_i["_source"]})
    return JsonResponse(suggest_table, safe=False)


# login_required(login_url='/accounts/login/')
@csrf_exempt
def query_with_doc(request):
    content = request.POST.get("content", "")
    q_from = request.POST.get("from", 0)
    q_size = request.POST.get("size", 10)
    shost = os.getenv("SEARCH_HOST", "localhost")
    sport = os.getenv("SEARCH_PORT", "9090")
    (search_ssl, search_ssl_verify, scheme) = getSSLEnv()
    url = scheme + "://" + shost + ":" + sport + "/api/searching/query_with_doc"
    data = {"from": int(q_from), "size": int(q_size), "content": content}
    response = requests.post(
        url,
        data=json.dumps(data),
        headers={"Content-type": "application/json", "Accept": "application/json"},
        verify=search_ssl_verify,
    )
    results = json.loads(response.content)
    return JsonResponse(results, safe=False)


# login_required(login_url='/accounts/login/')
@csrf_exempt
def querying(request):
    request_data = json.loads(request.body)
    query = request_data["content"]
    q_from = request_data["from"]
    q_size = 10
    shost = os.getenv("SEARCH_HOST", "localhost")
    sport = os.getenv("SEARCH_PORT", "8000")
    (search_ssl, search_ssl_verify, scheme) = getSSLEnv()
    url = scheme + "://" + shost + ":" + sport + "/api/searching/querying"
    options = {}
    if "options" in request_data:
        options = request_data["options"]
    data = {"from": int(q_from), "size": int(q_size), "content": query, "options": options}
    response = requests.post(
        url,
        data=json.dumps(data),
        headers={"Content-type": "application/json", "Accept": "application/json"},
        verify=search_ssl_verify,
    )
    results = json.loads(response.content)
    return JsonResponse(results, safe=False)


# login_required(login_url='/accounts/login/')
@csrf_exempt
def doc(request):
    doc_id = request.GET.get("doc_id", "")
