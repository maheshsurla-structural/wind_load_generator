import requests

def MidasAPI(method, command, body=None):
    """Function to interact with MIDAS Civil NX API."""
    base_url = "https://moa-engineers.midasit.com:443/civil"
    mapi_key = "eyJ1ciI6Im1haGVzaEBtaWRhc2l0LmNvbSIsInBnIjoiY2l2aWwiLCJjbiI6IlFwMjFWTUhnVFEifQ.d00c3fc21c2796ca99cb5197efe694a3ab2d09364d87c833d56d91951a11efb8"
    url = base_url + command
    headers = {"Content-Type": "application/json", "MAPI-Key": mapi_key}

    try:
        response = requests.request(method, url, headers=headers, json=body)
        response.raise_for_status()
        print(f"{method} {command}: {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None