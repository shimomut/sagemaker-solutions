import json
import requests

def get_text(input_text):

    headers = {
        "Content-Type" : "application/json",
    }

    data = {
        "inputs" : input_text, 
        "parameters" : {
            "max_new_tokens": 500,
            "temperature": 0.5
        }
    }

    response = requests.post( "http://127.0.0.1:8080/generate", headers=headers, json=data )

    return json.loads(response.text)["generated_text"]

while True:
    input_text = input("Your input: ")
    generated_text = get_text(input_text)
    print("Generated text:", generated_text)
    print("")
