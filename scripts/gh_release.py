"""Create (or reuse) the GitHub release for the current version and print the
asset upload URL. Used by the release flow:

    GH_TOKEN=<token> python scripts/gh_release.py
    curl -X POST ... "<upload_url>?name=UncleCZNMMMI-v<ver>.zip"  (manual download)
    curl -X POST ... "<upload_url>?name=UncleCZNMMMI-v<ver>.exe"  (auto-update)

The token comes from `git credential fill` on the publishing machine; it is
never stored here. The upload URL is written to rel_upload.txt (git-ignored).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com/repos/CaptainBexo/UncleDecodeCZN/releases"
TOKEN = os.environ.get("GH_TOKEN") or sys.exit("set GH_TOKEN")
HERE = os.path.dirname(os.path.abspath(__file__))


def call(url, data=None, method=None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "token " + TOKEN)
    req.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    return json.load(urllib.request.urlopen(req))


def main():
    ver = re.search(r'VERSION = "([^"]+)"',
                    open(os.path.join(ROOT, "ui", "version.py"), encoding="utf-8").read()).group(1)
    tag = "v" + ver
    body = open(os.path.join(ROOT, "README_RELEASE.md"), encoding="utf-8").read()
    payload = json.dumps({"tag_name": tag, "name": tag, "body": body}).encode()
    try:
        rel = call(API, payload, "POST")
    except urllib.error.HTTPError as e:
        if e.code != 422:            # 422 = release for this tag already exists
            raise
        rel = call(API + "/tags/" + tag)
    out = os.path.join(HERE, "rel_upload.txt")
    open(out, "w").write(rel["upload_url"].split("{")[0])
    print("release created: %s | id: %s" % (rel["tag_name"], rel["id"]))
    print("upload_url -> " + out)


main()
