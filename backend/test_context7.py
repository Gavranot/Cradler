"""
Quick test script to verify Context7 integration
"""
import asyncio
import sys
sys.path.insert(0, '/app')

from agents.mcp.context7_client import Context7Client


async def test_context7():
    """Test Context7 client connectivity and functionality"""
    print("=" * 60)
    print("Context7 Integration Test")
    print("=" * 60)

    client = Context7Client()

    # Test 1: Health check
    print("\n[Test 1] Health Check...")
    try:
        is_healthy = await client.health_check()
        print(f"✓ Context7 service is reachable: {is_healthy}")
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        return

    # Test 2: Resolve Botasaurus library ID
    print("\n[Test 2] Resolving 'Botasaurus' library ID...")
    try:
        result = await client.resolve_library_id("Botasaurus")
        if result.get("success"):
            print(f"✓ Library ID: {result.get('library_id')}")
            print(f"  Matches: {len(result.get('matches', []))} libraries found")
        else:
            print(f"✗ Failed: {result.get('message')}")
    except Exception as e:
        print(f"✗ Resolution failed: {e}")

    # Test 3: Fetch Botasaurus documentation
    print("\n[Test 3] Fetching Botasaurus documentation...")
    try:
        result = await client.get_botasaurus_docs(topic="driver methods", tokens=5000)
        if result.get("success"):
            doc_length = len(result.get("documentation", ""))
            print(f"✓ Documentation retrieved: {doc_length} characters")
            print(f"  Library ID: {result.get('library_id')}")
            # Show first 200 chars
            doc_preview = result.get("documentation", "")[:200]
            print(f"  Preview: {doc_preview}...")
        else:
            print(f"✗ Failed: {result.get('message')}")
    except Exception as e:
        print(f"✗ Documentation fetch failed: {e}")

    # Test 4: Fetch generic library docs (BeautifulSoup)
    print("\n[Test 4] Fetching BeautifulSoup documentation...")
    try:
        result = await client.resolve_library_id("BeautifulSoup")
        if result.get("success"):
            library_id = result.get("library_id")
            print(f"✓ Resolved BeautifulSoup: {library_id}")

            docs = await client.get_library_docs(library_id=library_id, tokens=3000)
            if docs.get("success"):
                doc_length = len(docs.get("documentation", ""))
                print(f"✓ Documentation retrieved: {doc_length} characters")
            else:
                print(f"✗ Failed to fetch docs: {docs.get('message')}")
        else:
            print(f"✗ Resolution failed: {result.get('message')}")
    except Exception as e:
        print(f"✗ Test failed: {e}")

    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_context7())
