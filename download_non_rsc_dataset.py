import json
import os
import time
import requests
from collections import Counter

JSON_FILE = "full_dataset_final.json"
OUTPUT_DIR = "extracted_data_full_dataset/downloaded_images"
LOG_FILE = "extracted_data_full_dataset/download_failures.txt"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(JSON_FILE, "r") as f:
    data = json.load(f)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
})

total = len(data)
downloaded = 0
skipped = 0
failed = 0

publisher_counts = Counter(
    info["DOI"].split("/")[0]
    for info in data.values()
    if info["DOI"].split("/")[0] != "10.1039"
)

print("=" * 70)
print("TEMExtraction - Non-RSC Dataset Downloader")
print("=" * 70)
print(f"Total dataset entries : {total}")
print(f"Non-RSC entries       : {sum(publisher_counts.values())}")
print(f"RSC entries skipped   : {data and total - sum(publisher_counts.values())}")
print()
print("Publishers to download:")
for publisher, count in sorted(publisher_counts.items()):
    print(f"  {publisher}: {count}")
print()
print(f"Output directory: {OUTPUT_DIR}")
print("=" * 70)

with open(LOG_FILE, "w") as log:
    log.write("TEMExtraction dataset download failures\n")
    log.write("=" * 70 + "\n")

    for index, (filename, info) in enumerate(data.items(), start=1):

        doi = info["DOI"]
        publisher = doi.split("/")[0]
        url = info["Composite_Figure_URL"]

        # Skip RSC
        if publisher == "10.1039":
            continue

        output_path = os.path.join(OUTPUT_DIR, filename)

        # Resume support
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 1000:
            skipped += 1
            print(
                f"[{index}/{total}] SKIP  {filename}",
                flush=True
            )
            continue

        print(
            f"\n[{index}/{total}] DOWNLOAD"
            f"\nPublisher : {publisher}"
            f"\nDOI       : {doi}"
            f"\nURL       : {url}",
            flush=True
        )

        success = False

        for attempt in range(1, 4):
            try:
                response = session.get(
                    url,
                    timeout=30,
                    allow_redirects=True
                )

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                size = len(response.content)

                print(
                    f"  Attempt {attempt}: "
                    f"HTTP={response.status_code}, "
                    f"TYPE={content_type}, "
                    f"SIZE={size}",
                    flush=True
                )

                if (
                    response.status_code == 200
                    and size > 1000
                    and content_type.startswith("image/")
                ):
                    with open(output_path, "wb") as out:
                        out.write(response.content)

                    downloaded += 1
                    success = True

                    print(
                        f"  SAVED -> {output_path}",
                        flush=True
                    )

                    break

                else:
                    print("  Invalid response", flush=True)

            except Exception as e:
                print(
                    f"  ERROR: {repr(e)}",
                    flush=True
                )

            if attempt < 3:
                time.sleep(2)

        if not success:
            failed += 1

            log.write("\n")
            log.write(f"FILE: {filename}\n")
            log.write(f"DOI : {doi}\n")
            log.write(f"URL : {url}\n")
            log.write("-" * 70 + "\n")
            log.flush()

            print(
                f"  FAILED -> logged in {LOG_FILE}",
                flush=True
            )

        # Small delay to avoid hammering publisher servers
        time.sleep(0.2)

print()
print("=" * 70)
print("DOWNLOAD COMPLETE")
print("=" * 70)
print(f"Downloaded this run : {downloaded}")
print(f"Already existed     : {skipped}")
print(f"Failed              : {failed}")
print()
print(f"Images directory    : {OUTPUT_DIR}")
print(f"Failure log         : {LOG_FILE}")
print("=" * 70)
