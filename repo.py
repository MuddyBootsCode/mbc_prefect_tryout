import httpx
from ollama import AsyncClient
import ollama
from dotenv import load_dotenv
import pprint
import os
import json

load_dotenv('.env', override=True)

import json
import re


def parse_stringified_json(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            obj[key] = parse_stringified_json(value)
    elif isinstance(obj, list):
        return [parse_stringified_json(item) for item in obj]
    elif isinstance(obj, str):
        # Try to detect and parse stringified JSON
        try:
            # Use regex to detect if the string looks like a JSON object or array
            if re.match(r'^\[.*\]$', obj.strip()) or re.match(r'^\{.*\}$', obj.strip()):
                return parse_stringified_json(json.loads(obj))
        except json.JSONDecodeError:
            pass
    return obj


def get_repo_commits(url):
    token = os.getenv('GITHUB_API_KEY')
    headers = {'Authorization': f'Bearer {token}'}

    try:
        response = httpx.get(url, headers=headers)
        print(httpx.get('https://api.github.com/rate_limit', headers=headers).json(), ' Rate limit')
        # response = httpx.get(url)
        response.raise_for_status()  # Raises an HTTPError if the response status is 4xx, 5xx
        data = response.json()
    except httpx.HTTPStatusError:
        print(f"HTTP error occurred in get_repo_commits from repo {url}")
        return
    except Exception as e:
        print(f"An error occurred: {e}")
        return
    print(f"Successfully received data from {url}")
    return data


async def get_commit_info(data):
    result_list = []
    for commit in data:
        try:
            commit_message = commit.get('commit', {}).get('message', 'NONE')
            author = commit.get('commit', {}).get('author', {})
            date = commit.get('commit', {}).get('author', {}).get('date', 'NONE')
            url = commit.get('url', 'NONE')
            async with httpx.AsyncClient() as client:
                print(f"Getting data from {url}")
                files_commit = await client.get(url)
                files_commit.raise_for_status()
                files_data = files_commit.json()

            files = []
            for file in files_data.get('files', []):
                filename = file.get('filename', 'NONE')
                patch = file.get('patch', 'NONE')
                raw_url = file.get('raw_url', 'NONE')

                files.append({
                    "filename": filename,
                    "patch": patch,
                    "raw_url": raw_url
                })

            result_list.append({
                "commit_message": commit_message,
                "author": author,
                "date": date,
                "url": url,
                "files": files
            })
        except httpx.HTTPStatusError:
            print(f"HTTP error occurred while getting data from {url}")
            continue  # Continue with the next iteration
        except Exception as e:
            print(f"An error occurred: {e}")
            continue  # Continue with the next iteration
    return result_list


def get_repo_summary(commit):
    try:
        response = ollama.chat(model="llama3", format='json', stream=False, messages=[
            {
                'role': 'user',
                'content': f"""
                Here is the commit data: {commit}
                Analyze this commit from a GitHub repository. Summarize the main changes,
                including the patch details. Identify the functions and files that were modified.
                Assess the importance of this commit to the overall codebase on a scale from 1 to 5,
                with 5 being the most crucial. Format the analysis in a compact JSON format without any new lines
                or unnecessary spaces. Include keys 'Files', 'Functions', 'Summary', 'Importance'.
                For each file, list the filename, its raw URL, and include the patch content.
                Specify which functions were affected in each file. The JSON output should be compact
                and readable in a single line if possible.
                """
            }
        ])
        try:
            commit['summary'] = response['message']['content']
        except KeyError:
            print(f"An error occurred: {response}")
            return commit
        return commit
    except Exception as e:
        return None


async def main():
    url = "https://api.github.com/repos/prefecthq/prefect/commits"
    data = get_repo_commits(url)
    commits = await get_commit_info(data[0:1])
    for commit in commits:
        summary = get_repo_summary(commit)
        commit['summary'] = parse_stringified_json(summary)
        pprint.pprint(commit)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
    # main()
