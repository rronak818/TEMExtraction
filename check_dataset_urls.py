import json
import urllib.request
import urllib.error
from collections import Counter

with open("full_dataset_final.json") as f:
    data = json.load(f)

results = Counter()
failed = []

for i, (key, info) in enumerate(data.items(), 1):
    url = info["Composite_Figure_URL"]

    try:
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(req, timeout=15) as response:
            status = response.getcode()

    except Exception as e:
        status = getattr(e, "code", "ERROR")
        failed.append((key, info["DOI"], url, status))

    results[str(status)] += 1

    if i % 100 == 0:
        print("Checked:", i)

print("\nRESULTS")
print("=======")

for status, count in results.items():
    print(status, ":", count)

print("\nFAILED URLS:", len(failed))

with open("failed_urls.txt", "w") as f:
    for key, doi, url, status in failed:
        f.write("{}\t{}\t{}\t{}\n".format(key, doi, status, url))
