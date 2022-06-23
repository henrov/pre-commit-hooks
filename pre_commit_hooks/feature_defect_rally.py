#!/usr/bin/env python3
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from pyral import Rally, rallyWorkset

PREFIX_FIX = 'fix'
PREFIX_FEAT = 'feat'

ENTITY_USER_STORY = 'UserStory'
ENTITY_DEFECT = 'Defect'


# parameter 0 = project id, parameter 1 = object id
URL_USER_STORY = "https://rally1.rallydev.com/#/{0}/dashboard?detail=%2Fuserstory%2F{1}"
URL_DEFECT = "https://rally1.rallydev.com/#/{0}/dashboard?detail=%2Fdefect%2F{1}"

# parameter 0 = workspace, parameter 1 = formatted id
GIT_LOG_RALLY_CACHE = "~/.git-log-rally-cache/{0}/{1}"

# https://rally1.rallydev.com/#/349498782336d/iterationstatus?detail=%2Fuserstory%2F640795934475&view=6aa90802-1bff-4a7e-9ece-b04344c6750a
# projectid 49498782336d
# objectid  640795934475

class RallyCache:
    _rally = None
    _workspace = None
    _project = None
    
    

    def __init__(self, formatted_id_list):
        self._formatted_id_list = formatted_id_list
        # initialize workspace with value from environment; needed for use of cache in case of direct mode
        self._workspace = os.environ.get('RALLY_WORKSPACE')

    def _get_rally_workset(self):
        if self._rally is None:
            # args is empty because all parameters should be taken from environment variables
            server, user, password, apikey, workspace, project = rallyWorkset(args=[])
            if apikey:
                self._rally = Rally(server, apikey=apikey, workspace=workspace, project=project)
            else:
                self._rally = Rally(server, user, password, workspace=workspace, project=project)
            self._workspace = workspace
            self._project = project
        return self._rally

    def get_rally_details(self, entity, prefix, formatted_id):
        cache_file_path = self._get_cache_file_for_id(formatted_id)
        # if a cache file exists and is not older than 24h, use that
        if cache_file_path.exists() and (time.time() - os.path.getmtime(cache_file_path)) < 24 * 3600:
            with open(cache_file_path, "r") as f:
                value = json.load(f)
        else:
            self._get_rally_workset()
            query_result = self._rally.get(entity, fetch=True,
                                           query=f'FormattedID = "{formatted_id}"',
                                           workspace=self._workspace, project=self._project)
            if query_result.errors:
                logging.error(
                    f"request could not be successfully serviced for {formatted_id}, error code: {query_result.status_code}")
                logging.error("\n".join(query_result.errors))
            if query_result.resultCount == 0:
                logging.error(f"no item found for {formatted_id}")
            elif query_result.resultCount > 1:
                logging.error(f"more than 1 item returned matching your criteria for {formatted_id}")
            value = None
            for result_row in query_result:
                value = get_message_line(entity, prefix, result_row)
            cache_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file_path, "w") as f:
                json.dump(value, f)
        return value

    def _get_cache_file_for_id(self, formatted_id):
        return Path(GIT_LOG_RALLY_CACHE.format(self._workspace, formatted_id)).expanduser().resolve()


def get_message_line(entity, prefix, result_row):
    project_id = str(result_row.Project.ObjectID)
    object_id = str(result_row.ObjectID)
    parent, url = get_parent_and_url(entity, object_id, project_id, result_row)
    if parent is None:
        return f"{prefix}: [{result_row.FormattedID}]({url}) CONTEXT {result_row.Name}"
    else:
        return f"{prefix}: [{result_row.FormattedID}]({url}) CONTEXT {result_row.Name} ({parent.FormattedID} - {parent.Name})"


def get_entity_and_prefix(formatted_id):
    entity = None
    prefix = None
    if formatted_id.startswith("US"):
        entity = ENTITY_USER_STORY
        prefix = PREFIX_FEAT
    if formatted_id.startswith("DE"):
        entity = ENTITY_DEFECT
        prefix = PREFIX_FIX
    return entity, prefix


def get_parent_and_url(entity, object_id, project_id, rls):
    parent = None
    url = None
    if entity == ENTITY_USER_STORY:
        parent = rls.UnifiedParent
        url = URL_USER_STORY.format(project_id, object_id)
    if entity == ENTITY_DEFECT:
        parent = None
        url = URL_DEFECT.format(project_id, object_id)    	
    return parent, url


# main entry to the program
def main() -> None:

        

    direct_mode = False
    # get the list of formatted id's from the command-line arguments if a "--" was set
    if len(sys.argv) > 1 and sys.argv[1] == "--":
        formatted_id_list = set([arg.upper() for arg in sys.argv[2:]])
        direct_mode = True
    else:
        commit_msg_file = sys.argv[1]
        command = "git rev-parse --abbrev-ref HEAD"
        process = subprocess.run(command.split(' '), capture_output=True, text=True)
        match = re.search(r'(feature|defect|hotfix)/(US[0-9]{2,}|DE[0-9]{2,})',
                          process.stdout.strip(), flags=re.IGNORECASE)
        
        
        if not match:	
            print("-----------------------------------------------------------------------------------")
            print("No valid user story or defect ID in the branch name, changelog will not be amended.")
            print("-----------------------------------------------------------------------------------")          
            return 1
            
        formatted_id_list = [match.group(2)]

    rally_cache = RallyCache(formatted_id_list)

    if len(formatted_id_list) == 0:
        print("no valid ID's specified on the command line")
        return 1
    else:
        if not direct_mode:
            with open(commit_msg_file, "r") as f:
                commit_msg = f.read()
        for formatted_id in formatted_id_list:
            entity, prefix = get_entity_and_prefix(formatted_id)
            value = rally_cache.get_rally_details(entity, prefix, formatted_id)
            if direct_mode:
                print(value)
            else:
                with open(commit_msg_file, "w") as f:
                    f.write(value)
                    f.write("\n")
                    f.write(commit_msg)


if __name__ == '__main__':
    exit(main())
