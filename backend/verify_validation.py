import urllib.request
import urllib.parse
import json
import sys

def post_json(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

def test_validation():
    print("--- Starting Validation Verification Tests ---")
    store_url = "http://localhost:8000/api/jobs/store"
    
    # Test 1: Invalid Source
    payload_invalid_source = {
        "user_id": 1,
        "title": "Software Engineer",
        "company": "Naukri Corp",
        "location": "Bangalore",
        "description": "Naukri job description",
        "apply_url": "https://www.naukri.com/job-1",
        "source": "OtherSource",
        "status": "Saved"
    }
    
    code, resp = post_json(store_url, payload_invalid_source)
    print(f"Test 1 (unsupported source) -> Code: {code}, Response: {resp}")
    assert code == 400, f"Expected 400, got {code}"
    assert "Only 'Naukri' source is supported" in resp.get("detail", ""), "Expected source error detail"
    print("Test 1 Passed!")

    # Test 2: Invalid URL (Not starting with https)
    payload_invalid_protocol = {
        "user_id": 1,
        "title": "Software Engineer",
        "company": "Naukri Corp",
        "location": "Bangalore",
        "apply_url": "http://www.naukri.com/job-1",
        "source": "Naukri"
    }
    code, resp = post_json(store_url, payload_invalid_protocol)
    print(f"Test 2 (http protocol) -> Code: {code}, Response: {resp}")
    assert code == 400, f"Expected 400, got {code}"
    assert "Apply URL must start with 'https://'" in resp.get("detail", ""), "Expected protocol error detail"
    print("Test 2 Passed!")

    # Test 3: Invalid URL (Not belonging to Naukri)
    payload_invalid_domain = {
        "user_id": 1,
        "title": "Software Engineer",
        "company": "Example External Company",
        "location": "Bangalore",
        "apply_url": "https://careers.google.com/job-1",
        "source": "Naukri"
    }
    code, resp = post_json(store_url, payload_invalid_domain)
    print(f"Test 3 (google domain) -> Code: {code}, Response: {resp}")
    assert code == 400, f"Expected 400, got {code}"
    assert "Apply URL must belong to Naukri" in resp.get("detail", ""), "Expected domain error detail"
    print("Test 3 Passed!")

    # Test 4: Valid Naukri Job
    payload_valid = {
        "user_id": 1,
        "title": "Real Naukri Job Test",
        "company": "Real Naukri Company",
        "location": "Bangalore",
        "description": "This is a real job description from Naukri.",
        "apply_url": "https://www.naukri.com/real-naukri-job-test-1",
        "source": "Naukri",
        "status": "Applied" # Should be overridden to Discovered
    }
    code, resp = post_json(store_url, payload_valid)
    print(f"Test 4 (Valid Naukri Job) -> Code: {code}, Response: {resp}")
    assert code == 200, f"Expected 200, got {code}"
    assert resp.get("success") is True, "Expected success response"
    print("Test 4 Passed!")

    print("\n--- All Validation Verification Tests Passed Successfully! ---")

if __name__ == "__main__":
    test_validation()
