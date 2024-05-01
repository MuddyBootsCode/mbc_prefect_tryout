from prefect import flow, task, get_run_logger
import httpx
from dotenv import load_dotenv
import ollama
import os


@task
def get_repo_commits(url):
    load_dotenv()
    token = os.getenv('GITHUB_API_KEY')
    headers = {'Authorization': f'Bearer {token}'}
    logger = get_run_logger()

    try:
        response = httpx.get(url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError if the response status is 4xx, 5xx
        data = response.json()
    except httpx.HTTPStatusError:
        print(f"HTTP error occurred while getting data from {url}")
        logger.error(f"HTTP error occurred while getting data from {url}")
        return
    except Exception as e:
        print(f"An error occurred: {e}")
        logger.error(f"An error occurred: {e}")
        return
    logger.info(f"Successfully received data from {url}")
    return data


@task
async def get_commit_info(data):
    result_list = []
    logger = get_run_logger()
    for commit in data:
        try:
            commit_message = commit.get('commit', {}).get('message', 'NONE')
            author = commit.get('commit', {}).get('author', {})
            date = commit.get('commit', {}).get('author', {}).get('date', 'NONE')
            url = commit.get('url', 'NONE')
            async with httpx.AsyncClient() as client:
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


@task
def get_repo_summary(data):
    logger = get_run_logger()
    try:
        response = ollama.chat(model="llama3", messages=[
            {
                'role': 'user',
                'content': f"""
                This is a commit history from a GitHub repo, summarize the commit
                and include mentions of the functions changed: {data}
                """
            }
        ])
        logger.info(f"Successfully received summary for commit data")
        return response
    except Exception as e:
        print(f"An error occurred: {e}")
        logger.error(f"An error occurred: {e}")


@flow(log_prints=True)
def get_repo_info(url):
    """
    Given a GitHub repository, get the number of commits and the commit info
    """
    data = get_repo_commits(url)
    result = get_commit_info(data)
    summary = get_repo_summary(result[0])
    print(summary)


if __name__ == '__main__':
    # get_repo_info.serve(
    #     name="repo-tryout",
    #     tags=["testing", "tutorial"],
    #     description="Given a GitHub repository, logs repository statistics for that repo.",
    #     parameters={"url": "https://api.github.com/repos/PrefectHQ/prefect/commits"},
    #     version="tutorial/deployments",
    # )
    get_repo_info.from_source(
        source="https://github.com/MuddyBootsCode/mbc_prefect_tryout.git",
        entrypoint="main.py:get_repo_info",
    ).deploy(
        name="repo_tryout2",
        work_pool_name="tryout_pool",
    )
