#!/usr/bin/env python
"""
Live test script for Context7 integration with Secondary Agent
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def login():
    """Login and get JWT token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123!"
        }
    )
    response.raise_for_status()
    return response.json()["access_token"]

def create_scraper(token):
    """Create a new scraper"""
    response = requests.post(
        f"{BASE_URL}/api/scrapers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Books to Scrape - Context7 Test",
            "target_url": "https://books.toscrape.com/"
        }
    )
    response.raise_for_status()
    return response.json()["id"]

def update_scraper_config(token, scraper_id):
    """Add data fields configuration"""
    response = requests.put(
        f"{BASE_URL}/api/scrapers/{scraper_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "scraping_config": {
                "data_fields": ["title", "price", "rating", "availability"],
                "special_requirements": "Extract all books from the first page"
            }
        }
    )
    response.raise_for_status()
    return response.json()

def trigger_generation(token, scraper_id):
    """Trigger Secondary Agent code generation"""
    print(f"\n🤖 Triggering code generation for scraper {scraper_id}...")
    print("⏳ This will take 30-60 seconds...\n")

    response = requests.post(
        f"{BASE_URL}/api/scrapers/{scraper_id}/generate",
        headers={"Authorization": f"Bearer {token}"},
        timeout=180  # 3 minutes
    )
    response.raise_for_status()
    return response.json()

def get_scraper(token, scraper_id):
    """Get scraper details"""
    response = requests.get(
        f"{BASE_URL}/api/scrapers/{scraper_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    response.raise_for_status()
    return response.json()

def main():
    print("=" * 70)
    print("Context7 Integration - Live Test")
    print("=" * 70)

    try:
        # Step 1: Login
        print("\n[Step 1] Logging in...")
        token = login()
        print("✓ Logged in successfully")

        # Step 2: Create scraper
        print("\n[Step 2] Creating scraper...")
        scraper_id = create_scraper(token)
        print(f"✓ Scraper created: {scraper_id}")

        # Step 3: Update configuration
        print("\n[Step 3] Updating scraper configuration...")
        update_scraper_config(token, scraper_id)
        print("✓ Configuration updated")

        # Step 4: Trigger generation
        print("\n[Step 4] Triggering code generation...")
        result = trigger_generation(token, scraper_id)

        # Step 5: Display results
        print("\n" + "=" * 70)
        print("GENERATION RESULTS")
        print("=" * 70)

        print(f"\nStatus: {result.get('status')}")
        print(f"Message: {result.get('message')}")

        generation_result = result.get('result', {})
        print(f"Success: {generation_result.get('success')}")
        print(f"Iterations: {generation_result.get('iterations')}")
        print(f"Tool Calls: {len(generation_result.get('tool_calls', []))}")

        # Check for Context7 tool calls
        tool_calls = generation_result.get('tool_calls', [])
        context7_calls = [tc for tc in tool_calls if 'context7' in tc.get('function', '')]

        print(f"\n📚 Context7 Tool Calls: {len(context7_calls)}")
        for tc in context7_calls:
            print(f"  - {tc.get('function')}")

        # Display generated code preview
        scraper_code = generation_result.get('scraper_code', '')
        if scraper_code:
            print(f"\n📝 Generated Code Length: {len(scraper_code)} characters")
            print("\n--- Code Preview (first 500 chars) ---")
            print(scraper_code[:500])
            print("...")

            # Check for problematic patterns
            print("\n🔍 Code Analysis:")
            if 'driver.select_all' in scraper_code:
                print("  ❌ WARNING: Code contains driver.select_all() (non-existent method)")
            else:
                print("  ✓ No driver.select_all() found")

            if 'driver.find_elements' in scraper_code:
                print("  ✓ Uses driver.find_elements() (correct Selenium method)")

            if 'driver.bs4' in scraper_code:
                print("  ✓ Uses driver.bs4 (BeautifulSoup integration)")

            if 'By.CSS_SELECTOR' in scraper_code:
                print("  ✓ Uses By.CSS_SELECTOR (correct import)")

        # Display reasoning log
        reasoning_log = generation_result.get('reasoning_log', [])
        if reasoning_log:
            print(f"\n🧠 Reasoning Log: {len(reasoning_log)} entries")
            print("\n--- First Reasoning Step ---")
            first_reasoning = reasoning_log[0]
            print(f"Iteration: {first_reasoning.get('iteration')}")
            print(f"Type: {first_reasoning.get('type')}")
            print(f"Text: {first_reasoning.get('text', '')[:200]}...")

        print("\n" + "=" * 70)
        print("TEST COMPLETE")
        print("=" * 70)

        # Save scraper ID for manual inspection
        print(f"\n📋 Scraper ID: {scraper_id}")
        print(f"View at: {BASE_URL}/api/scrapers/{scraper_id}")

    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        print(f"Response: {e.response.text}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
