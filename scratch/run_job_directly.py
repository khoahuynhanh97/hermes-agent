import sys
import os
import json
from pathlib import Path

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.job_watcher import JobWorker

worker = JobWorker()

# Let's find the job file
inbox_dir = Path(".agent_jobs/inbox")
job_file = inbox_dir / "job_20260701_160354_66e18f.json"

if not job_file.exists():
    # Check in processing too just in case
    processing_file = Path(".agent_jobs/processing") / "job_20260701_160354_66e18f.json"
    if processing_file.exists():
        job_file = processing_file
        print("Job file is already in processing folder.")
    else:
        print(f"Error: Job file {job_file} does not exist.")
        sys.exit(1)

with open(job_file, "r", encoding="utf-8") as f:
    job = json.load(f)

print("Starting execution for job:", job["job_id"])

# Move to processing if it's not already there
processing_dir = Path(".agent_jobs/processing")
processing_dir.mkdir(parents=True, exist_ok=True)
processing_file = processing_dir / job_file.name

if job_file.resolve() != processing_file.resolve():
    if job_file.exists():
        job_file.rename(processing_file)

try:
    # Run the tasks
    files_created, summary = worker.execute_job_tasks(job)
    print("\nExecution completed successfully!")
    print("Files created:", files_created)
    print("Summary:", summary)
    
    # Write done file in outbox
    outbox_dir = Path(".agent_jobs/outbox")
    outbox_dir.mkdir(parents=True, exist_ok=True)
    done_file = outbox_dir / f"{job['job_id']}.done.json"
    
    done_data = {
        "job_id": job["job_id"],
        "status": "done",
        "project_slug": job["target"].get("project_slug"),
        "output_dir": job["target"].get("output_dir"),
        "files_created": files_created,
        "summary": summary
    }
    
    with open(done_file, "w", encoding="utf-8") as out_f:
        json.dump(done_data, out_f, ensure_ascii=False, indent=2)
        
    print(f"Done file written to {done_file}")
    
    # Remove from processing
    if processing_file.exists():
        processing_file.unlink()
        
except Exception as e:
    import traceback
    print("Error during execution:", e)
    traceback.print_exc()
    # Move back to failed
    failed_dir = Path(".agent_jobs/failed")
    failed_dir.mkdir(parents=True, exist_ok=True)
    if processing_file.exists():
        processing_file.rename(failed_dir / job_file.name)
