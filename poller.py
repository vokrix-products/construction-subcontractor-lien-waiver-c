import os
import time
import json
import datetime
import requests
import processor

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
PRODUCT_ID = os.environ.get("PRODUCT_ID", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

UPLOADS_BUCKET = "uploads"
RESULTS_BUCKET = "results"

HEADERS = {
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "apikey": SUPABASE_SERVICE_KEY,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def download_file(bucket, file_path):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY})
    resp.raise_for_status()
    return resp.content


def insert_notification(product_id, customer_id, title, body, notif_type):
    try:
        payload = {
            "product_id": product_id,
            "customer_id": customer_id,
            "title": title,
            "body": body,
            "type": notif_type,
            "read": False,
        }
        requests.post(
            "https://njyvnmczoydsaewvfhyq.supabase.co/rest/v1/notifications",
            headers=HEADERS,
            json=payload,
            timeout=30,
        )
    except Exception:
        pass


def update_job(job_id, status, output_file_path, result_summary):
    patch = {
        "status": status,
        "output_file_path": output_file_path,
        "result_summary": result_summary,
        "completed_at": datetime.datetime.utcnow().isoformat(),
    }
    try:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{job_id}",
            headers=HEADERS,
            json=patch,
            timeout=30,
        )
    except Exception:
        pass


def process_job(job):
    job_id = job.get("id")
    customer_id = job.get("customer_id")
    input_path = job.get("input_file_path")
    if not input_path:
        raise ValueError("missing input_file_path")

    file_bytes = download_file(UPLOADS_BUCKET, input_path)
    records = processor.process_file(file_bytes)

    result_key = f"results/{job_id}.json"
    result_payload = json.dumps(records).encode("utf-8")
    requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{RESULTS_BUCKET}/{result_key}",
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "apikey": SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
        data=result_payload,
        timeout=60,
    )

    for rec in records:
        record_payload = {
            "product_id": PRODUCT_ID,
            "customer_id": customer_id,
            "title": rec.get("title"),
            "status": rec.get("status"),
            "details": rec.get("details") or {},
            "source_file_path": input_path,
            "due_date": rec.get("due_date"),
        }
        requests.post(
            f"{SUPABASE_URL}/rest/v1/records",
            headers=HEADERS,
            json=record_payload,
            timeout=30,
        )

    summary = f"Processed {len(records)} record(s)."
    update_job(job_id, "completed", result_key, summary)
    insert_notification(PRODUCT_ID, customer_id, "Processing complete", "Your upload has been processed successfully.", "success")


def poll():
    while True:
        try:
            url = f"{SUPABASE_URL}/rest/v1/jobs?status=eq.pending&job_type=eq.process_upload&product_id=eq.{PRODUCT_ID}&select=*"
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            jobs = resp.json()
            for job in jobs:
                try:
                    process_job(job)
                except Exception as e:
                    job_id = job.get("id")
                    customer_id = job.get("customer_id")
                    update_job(job_id, "failed", None, f"Error: {str(e)}")
                    insert_notification(PRODUCT_ID, customer_id, "Processing failed", "There was an error processing your upload.", "error")
        except Exception:
            pass
        time.sleep(60)


if __name__ == "__main__":
    print("Poller started")
    poll()
