import requests
import datetime
from flask import Flask, jsonify
from newsapi import NewsApiClient
import os
import base64

from peft import PeftModel, PeftConfig
from transformers import AutoModelForCausalLM, AutoTokenizer

config = PeftConfig.from_pretrained("yuriachermann/Not-so-bright-AGI-Llama3.1-8B-UC200k-v2")
base_model = AutoModelForCausalLM.from_pretrained("VAGOsolutions/Llama-3-SauerkrautLM-8b-Instruct")
model = PeftModel.from_pretrained(base_model, "yuriachermann/Not-so-bright-AGI-Llama3.1-8B-UC200k-v2")
tokenizer = AutoTokenizer.from_pretrained("VAGOsolutions/Llama-3-SauerkrautLM-8b-Instruct")

app = Flask(__name__)

pplx_key = "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"
news_api = NewsApiClient(api_key="e194b22299a64a58bf96756191249647")

@app.route('/', methods=['GET'])
def get_home():
    toReturn = jsonify({"text": "Welcome to the Triage backend server! API requests may be requested from this URL."})
    toReturn.headers.add('Access-Control-Allow-Origin', '*')
    return toReturn


def lastweek(string=True):
    day = datetime.date.today() - datetime.timedelta(7)
    return day

@app.route('/news/<string:disasterName>', methods=['GET'])
def get_news(disasterName):
    lweek = lastweek(True)
    articles = news_api.get_everything(q=disasterName, from_param=lweek)

    arr = articles["articles"]
    lim = min(10, len(arr))
    arr = arr[:lim]

    toReturn = jsonify({"articles": arr})
    toReturn.headers.add('Access-Control-Allow-Origin', '*')
    return toReturn

@app.route('/getRisk/<string:address>', methods=['GET'])
def getRisk(address):
    client_id = "0q700A0v22eSwKlJnFFWGZttA9wwDc72"
    client_secret = "59F6aKA9QxE59j0V"
    credentials = f"{client_id}:{client_secret}"
    base64_value = base64.b64encode(credentials.encode()).decode()

    token_url = "https://api.precisely.com/oauth/token"
    headers = {
        "Authorization": f"Basic {base64_value}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials"
    }

    response = requests.post(token_url, headers=headers, data=data)
    access_token = response.json()["access_token"]

    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    richter_value = 'all'
    include_geometry = 'N'

    earthUrl = f'https://api.precisely.com/risks/v1/earthquake/byaddress?address={address}&richterValue={richter_value}&includeGeometry={include_geometry}'
    fireUrl = f'https://api.precisely.com/risks/v2/fire/byaddress?address={address}'
    floodUrl = f'https://api.precisely.com/risks/v1/shoreline/distancetofloodhazard/byaddress?address={address}'

    earthResponse = requests.get(earthUrl, headers=headers)
    fireResponse = requests.get(fireUrl, headers=headers)
    floodResponse = requests.get(floodUrl, headers=headers)

    if len(earthResponse.json()) == 0:
        earthResponse = 'No Risk'
    else:
        earthResponse = earthResponse.json()['riskLevel']

    toReturn = jsonify({"earth": earthResponse, "fire": fireResponse.json()['riskDesc'], "flood":floodResponse.json()['waterBody'][0]['distance']['value']})
    toReturn.headers.add('Access-Control-Allow-Origin', '*')
    return toReturn


@app.route('/intel-llama-question/<string:disasterName>/<string:query>', methods=['GET'])
def intel_llama_question(disasterName, query):
    prompt = "You are Triage, a real-time disaster detection and relief AI assistant to answer questions regarding " + disasterName + ". You will be provided summaries of recent and relevant news sources that may help inform your responses. Keep your answers relevant and helpful as the user may currently be involved in a disaster. Decline answering unrelated questions.\n\nUser query: " + query + "\n\nNEWS ARTICLES:\n"

    news = get_news(disasterName)
    articles = news.json["articles"]
    #print(articles)
    for article in articles:
        prompt += "\nArticle Title: " + article["title"] + "\nArticle Description: " + article["description"] + "\nArticle Content: " + article["content"] + "\n\n"

    print("prompt made!")
    inputs = tokenizer(prompt, return_tensors="pt")
    print("tokenized!")
    output_tokens = model.generate(**inputs, max_length=500)
    print("generated!")
    response = tokenizer.decode(output_tokens[0], skip_special_tokens=True)
    print("decoded!")

    toReturn = jsonify({"answer": response})
    toReturn.headers.add('Access-Control-Allow-Origin', '*')
    return toReturn

@app.route('/perplexity-question/<string:disasterName>/<string:query>', methods=['GET'])
def perplexity_question(disasterName, query):
    '''
    lweek = lastweek(True)
    articles = news_api.get_everything(q=disasterName, from_param=lweek, sort_by="relevancy", page_size=5, page=1)

    arr = articles["articles"]
    print(type(arr))
    print(arr)
    '''
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
    "model": "llama-3.1-sonar-small-128k-online",
    "messages": [{
        "role": "system",
        "content": "You are Triage, a real-time disaster detection and relief AI assistant to answer questions regarding " + disasterName + ". Keep your answers relevant and helpful. The user may currently be involved in a disaster. Decline answering unrelated questions."
      },
      {
        "role": "user",
        "content": query
      }],
      "max_tokens": 1000,
      "temperature": 0.2,
      "top_p": 0.9,
      "return_citations": False,
      "return_images": False,
      "return_related_questions": False,
      "search_recency_filter": "week",
      "top_k": 0,
      "stream": False,
      "presence_penalty": 0,
      "frequency_penalty": 1
    }
    headers = {
        "Authorization": "Bearer " + pplx_key,
        "Content-Type": "application/json"
    }

    response = requests.request("POST", url, json=payload, headers=headers)
    answer = response.json()["choices"][0]["message"]["content"]

    print(answer)

    toReturn = jsonify({"answer": answer})
    toReturn.headers.add('Access-Control-Allow-Origin', '*')
    return toReturn

if (__name__ == "__main__"):

    app.run(port="6969", debug=True)