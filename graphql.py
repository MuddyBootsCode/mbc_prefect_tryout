import requests

# Your personal access token
access_token = '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'

# The GraphQL query
query = """
query {
  repository(name: "prefect") {
    name
    description
  }
}
"""

# The endpoint and headers
url = 'https://api.github.com/graphql'
headers = {
    'Authorization': f'bearer {access_token}',
    'Content-Type': 'application/json'
}

# Send the POST request
response = requests.post(url, json={'query': query}, headers=headers)

# Print the response
print(response.json())
