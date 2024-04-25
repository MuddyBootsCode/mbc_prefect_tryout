from prefect import flow, task
import httpx
from dotenv import load_dotenv
import os

load_dotenv()


@task
def get_repo_commits(url):
    token = os.getenv('GITHUB_API_KEY')
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = httpx.get(url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError if the response status is 4xx, 5xx
        data = response.json()
    except httpx.HTTPStatusError:
        print(f"HTTP error occurred while getting data from {url}")
        return
    except Exception as e:
        print(f"An error occurred: {e}")
        return
    return data


@task
def get_commit_info(data):
    result_list = []
    for commit in data:
        try:
            commit_message = commit.get('commit', {}).get('message', 'NONE')
            author = commit.get('commit', {}).get('author', {})
            date = commit.get('commit', {}).get('author', {}).get('date', 'NONE')
            url = commit.get('url', 'NONE')
            files_commit = httpx.get(url)
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


@flow(log_prints=True)
def repo_info(url):
    """
    Given a GitHub repository, get the number of commits and the commit info
    """
    data = get_repo_commits(url)
    print(len(data))
    result = get_commit_info(data)
    print(result[0])


# Run the flow
repo_info('https://api.github.com/repos/PrefectHQ/prefect/commits')
