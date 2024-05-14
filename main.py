import pprint
from dotenv import load_dotenv
from prefect import flow, task, get_run_logger
from prefect.tasks import task_input_hash
from datetime import timedelta
import httpx
import ollama
import os
from langchain_community.graphs import Neo4jGraph
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


@task
def get_repo_commits(url):
    load_dotenv('.env', override=True)

    token = os.getenv('GITHUB_API_KEY')

    headers = {'Authorization': f'Bearer {token}'}
    logger = get_run_logger()

    try:
        logger.info(httpx.get('https://api.github.com/rate_limit', headers=headers).json())
        response = httpx.get(url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError if the response status is 4xx, 5xx
        data = response.json()
    except httpx.HTTPStatusError:
        print(f"HTTP error occurred in get_repo_commits from repo {url}")
        logger.error(f"HTTP error occurred while getting data from {url}")
        return
    except Exception as e:
        print(f"An error occurred: {e}")
        logger.error(f"An error occurred: {e}")
        return
    logger.info(f"Successfully received data from {url}")
    return data


@task
def extract_files(commit):
    load_dotenv('.env', override=True)

    token = os.getenv('GITHUB_API_KEY')

    headers = {'Authorization': f'Bearer {token}'}
    logger = get_run_logger()

    files = []
    url = commit.get('url', 'NONE')
    try:
        files_commit = httpx.get(url, headers=headers)
        files_commit.raise_for_status()  # Raises an HTTPError if the response status is 4xx, 5xx
        files_data = files_commit.json()

        for file in files_data.get('files', []):
            filename = file.get('filename', 'NONE')
            patch = file.get('patch', 'NONE')
            raw_url = file.get('raw_url', 'NONE')

            files.append({
                "filename": filename,
                "patch": patch,
                "raw_url": raw_url
            })
    except httpx.HTTPStatusError:
        print(f"HTTP error occurred while getting data from {url}")
        logger.error(f"HTTP error occurred while getting data from {url}")
    except Exception as e:
        print(f"An error occurred: {e}")
        logger.error(f"An error occurred: {e}")
    return files


@task
def get_commit_info(data):
    result_list = []
    logger = get_run_logger()
    for commit in data:
        try:
            commit_message = commit.get('commit', {}).get('message', 'NONE')
            author = commit.get('commit', {}).get('author', {})
            date = commit.get('commit', {}).get('author', {}).get('date', 'NONE')
            url = commit.get('url', 'NONE')
            id = commit.get('node_id', 'NONE')
            files = extract_files.submit(commit)

            result_list.append({
                "commit_message": commit_message,
                "author": author,
                "date": date,
                "url": url,
                "id": id,
                "files": files.result()
            })
            logger.info(f"Successfully processed commit {commit_message} at {url}")
        except httpx.HTTPStatusError:
            print(f"HTTP error occurred while getting data from {url}")
            logger.error(f"HTTP error occurred while getting data from {url}")
            continue  # Continue with the next iteration
        except Exception as e:
            print(f"An error occurred: {e}")
            logger.error(f"An error occurred: {e}")
            continue  # Continue with the next iteration
    return result_list


# @task
# def get_repo_summary(commits):
#     logger = get_run_logger()
#
#     commits_with_summary = []
#
#     for commit in commits:
#         try:
#             response = ollama.chat(model="llama3", format='json', messages=[
#                 {
#                     'role': 'user',
#                     'content': f"""
#                     Here is the commit data: {commit}
#                     Analyze this commit from a GitHub repository. Summarize the main changes in a paragraph,
#                     including the patch details. Identify the functions and files that were modified.
#                     Assess the importance of this commit to the overall codebase on a scale from 1 to 5,
#                     with 5 being the most crucial. Format the analysis in a compact JSON format without any new lines
#                     or unnecessary spaces. Include keys 'Files', 'Functions', 'Summary', 'Importance'.
#                     For each file, list the filename, its raw URL, and include the patch content.
#                     Specify which functions were affected in each file. The JSON output should be compact
#                     and readable in a single line if possible.
#                     """
#                 }
#             ])
#             logger.info(f"Successfully received summary for commit data")
#             commit['summary'] = response['message']['content']
#             pprint.pprint(commit['summary'])
#             commits_with_summary.append(commit)
#         except Exception as e:
#             print(f"An error occurred: {e}")
#             logger.error(f"An error occurred: {e}")
#     return commits_with_summary

@task(cache_key_fn=task_input_hash, cache_expiration=timedelta(hours=1))
def get_repo_summary(commit):
    logger = get_run_logger()
    logger.info(f"Getting summary for commit data - {commit['commit_message']}")
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
            logger.info(f"Successfully received summary for commit data - {commit['commit_message']}")
        except json.JSONDecodeError:
            # Log and attempt to fix the JSON
            logger.warning(f"Invalid JSON string, attempting to fix it.")
            commit['summary'] = parse_stringified_json(response['message']['content'])
            if commit['summary'] is None:
                logger.error("Failed to fix the JSON string.")
                raise
        return commit
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return None


@flow(log_prints=True, retries=3, retry_delay_seconds=10)
def get_repo_info(url):
    """
    Given a GitHub repository, get the number of commits and the commit info
    """
    logger = get_run_logger()
    load_dotenv('.env', override=True)
    commits = get_repo_commits(url)
    commit_info = get_commit_info(commits)

    commits_with_summary = []

    for commit in commit_info:
        commit_w_summary = get_repo_summary.submit(commit)
        commits_with_summary.append(commit_w_summary.result())

    kg = Neo4jGraph(
        url=os.getenv('NEO4J_URI'),
        username=os.getenv('NEO4J_USERNAME'),
        password=os.getenv('NEO4J_PASSWORD'),
        database=os.getenv('NEO4J_DATABASE')
    )

    add_commit_node_query = """
MERGE (c:Commit {id: $commit.id})
ON CREATE SET
    c.message = $commit.commit_message,
    c.date = $commit.date,
    c.url = $commit.url,
    c.summary = $summary.Summary,
    c.importance = $summary.Importance
MERGE (a:Author {name: $commit.author.name, email: $commit.author.email})
MERGE (c)-[:COMMITTED_BY]->(a)
WITH c, a, $summary.Functions AS functions, $commit.files AS files
UNWIND files AS file
MERGE (f:File {filename: file.filename})
SET f.patch = file.patch,
    f.raw_url = file.raw_url
MERGE (c)-[:AFFECTS_FILE]->(f)
WITH c, functions
UNWIND functions AS function
MERGE (fn:Function {name: function})
MERGE (c)-[:AFFECTS_FUNCTION]->(fn)
    """

    for commit in commits_with_summary:
        summary = commit['summary']
        try:
            # First attempt to parse with json.loads
            summary_dict = json.loads(summary)
        except json.JSONDecodeError:
            # If that fails, attempt to parse with parse_stringified_json
            summary_dict = parse_stringified_json(commit['summary'])
            if not isinstance(summary_dict, dict):
                logger.error(f"Failed to parse summary for commit {commit['id']}: {summary_dict}")
                pprint.pprint(commit['summary'])
                continue
        pprint.pprint(summary_dict)
        try:
            logger.info(f"Ingesting commit {commit['id']}")
            kg.query(add_commit_node_query, params={"commit": commit, "summary": summary_dict})
        except Exception as e:
            print(f"Failed to ingest commit {commit['id']} due to {e}")


if __name__ == '__main__':
    get_repo_info("https://api.github.com/repos/PrefectHQ/prefect/commits")
    # get_repo_info.serve(
    #     name="repo-tryout",
    #     tags=["testing", "tutorial"],
    #     description="Given a GitHub repository, logs repository statistics for that repo.",
    #     parameters={"url": "https://api.github.com/repos/PrefectHQ/prefect/commits"},
    #     version="tutorial/deployments",
    # )
    # get_repo_info.from_source(
    #     source="https://github.com/MuddyBootsCode/mbc_prefect_tryout.git",
    #     entrypoint="main.py:get_repo_info",
    # ).deploy(
    #     name="repo_tryout2",
    #     work_pool_name="tryout_pool",
    # )
