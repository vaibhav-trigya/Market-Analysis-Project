import requests

url = "http://localhost:5000/task-status/report"
response = requests.get(url)
print(response.json())
