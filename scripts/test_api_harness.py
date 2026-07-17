#!/usr/bin/env python3
"""
Standalone terminal testing harness for FastAPI backend endpoints.
This script connects to the SQLite database, shows available data,
and allows testing of API endpoints with real HTTP requests.
"""

import sqlite3
import sys
import os
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# Add the project root to the path so we can import contexta modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

def get_db_path():
    """Get the path to the SQLite database"""
    return "contexta.db"

def connect_to_db():
    """Connect to the SQLite database"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found!")
        sys.exit(1)
    
    return sqlite3.connect(db_path)

def show_projects(conn):
    """Show all projects in the database"""
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM projects ORDER BY name")
    projects = cursor.fetchall()
    
    if not projects:
        print("No projects found in database.")
        return []
    
    print("\n📋 Available Projects:")
    print("-" * 50)
    for project in projects:
        print(f"ID: {project[0]:<36} | Name: {project[1]}")
    return projects

def show_artifact_versions(conn):
    """Show available artifact versions in the database with strict schema safety"""
    cursor = conn.cursor()
    try:
        # Check what columns actually exist in the versions table first
        cursor.execute("PRAGMA table_info(versions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Build a safe query dynamically based on what is actually in the table
        select_fields = ["id"]
        if "title" in columns: select_fields.append("title")
        if "type" in columns: select_fields.append("type")
        elif "artifact_type" in columns: select_fields.append("artifact_type")
        
        query = f"SELECT {', '.join(select_fields)} FROM versions"
        cursor.execute(query)
        versions = cursor.fetchall()
    except Exception as e:
        print(f"\n⚠️ Schema discovery failed: {e}")
        return []
    
    if not versions:
        print("No artifact versions found in database.")
        return []
    
    print("\n📦 Available Artifact Versions:")
    print("-" * 70)
    for version in versions:
        v_id = version[0]
        v_title = version[1] if len(version) > 1 else "N/A"
        v_type = version[2] if len(version) > 2 else "N/A"
        print(f"ID: {v_id:<36} | Title: {str(v_title)[:25]:<25} | Type: {v_type}")
    return versions


def get_api_base_url():
    """Get the base URL for the API server"""
    import os
    base_url = os.environ.get('API_BASE_URL', 'http://localhost:8000')
    return base_url

def test_endpoint(url, method='GET', data=None):
    """Make a real HTTP request to the API endpoint"""
    try:
        if method == 'GET':
            request = Request(url)
        elif method == 'POST':
            request = Request(url, data=data.encode('utf-8') if data else None)
            request.add_header('Content-Type', 'application/json')
        else:
            print(f"Unsupported HTTP method: {method}")
            return None
            
        response = urlopen(request)
        return response.read().decode('utf-8')
    except HTTPError as e:
        return f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    """Main function to run the testing harness"""
    print("🚀 FastAPI API Testing Harness")
    print("=" * 50)
    
    # Connect to database
    try:
        conn = connect_to_db()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)
    
    # Show available data
    projects = show_projects(conn)
    versions = show_artifact_versions(conn)
    
    conn.close()
    
    # Interactive menu
    while True:
        print("\n" + "=" * 50)
        print("🔧 Testing Options:")
        print("1. Test Project Detail Endpoint")
        print("2. Test Version Detail Endpoint") 
        print("3. Test Artifacts List Endpoint")
        print("4. Test Reviews List Endpoint")
        print("5. Test Proposals List Endpoint")
        print("6. Test Global Insights Endpoint")
        print("7. Test Node Detail Endpoint")
        print("8. Exit")
        
        choice = input("\nEnter your choice (1-8): ").strip()
        
        if choice == '1':
            if not projects:
                print("No projects available to test!")
                continue
                
            project_id = input("Enter Project ID to test: ").strip()
            if not project_id:
                print("Invalid Project ID!")
                continue
                
            api_url = f"{get_api_base_url()}/api/projects/{project_id}"
            print(f"\nTesting endpoint: {api_url}")
            response = test_endpoint(api_url)
            print("Response:")
            print("-" * 30)
            print(response)
            
        elif choice == '2':
            if not versions:
                print("No artifact versions available to test!")
                continue
                
            version_id = input("Enter Version ID to test: ").strip()
            if not version_id:
                print("Invalid Version ID!")
                continue
                
            api_url = f"{get_api_base_url()}/api/versions/{version_id}"
            print(f"\nTesting endpoint: {api_url}")
            response = test_endpoint(api_url)
            print("Response:")
            print("-" * 30)
            print(response)
            
        elif choice == '3':
            if not projects:
                print("No projects available to test!")
                continue
                
            project_id = input("Enter Project ID to test artifacts: ").strip()
            if not project_id:
                print("Invalid Project ID!")
                continue
                
            api_url = f"{get_api_base_url()}/api/projects/{project_id}/artifacts"
            print(f"\nTesting endpoint: {api_url}")
            response = test_endpoint(api_url)
            print("Response:")
            print("-" * 30)
            print(response)
            
        elif choice == '4':
            if not versions:
                print("No artifact versions available to test!")
                continue
                
            version_id = input("Enter Version ID to test reviews: ").strip()
            if not version_id:
                print("Invalid Version ID!")
                continue
                
            api_url = f"{get_api_base_url()}/api/versions/{version_id}/reviews"
            print(f"\nTesting endpoint: {api_url}")
            response = test_endpoint(api_url)
            print("Response:")
            print("-" * 30)
            print(response)
            
        elif choice == '5':
            if not versions:
                print("No artifact versions available to test!")
                continue
                
            version_id = input("Enter Version ID to test proposals: ").strip()
            if not version_id:
                print("Invalid Version ID!")
                continue
                
            api_url = f"{get_api_base_url()}/api/versions/{version_id}/proposals"
            print(f"\nTesting endpoint: {api_url}")
            response = test_endpoint(api_url)
            print("Response:")
            print("-" * 30)
            print(response)
            
        elif choice == '6':
            # Test Global Insights Endpoint
            api_url = f"{get_api_base_url()}/api/insights"
            print(f"\nTesting endpoint: {api_url}")
            response = test_endpoint(api_url)
            print("Response:")
            print("-" * 30)
            print(response)
            
        elif choice == '7':
            # Test Node Detail Endpoint
            if not projects:
                print("No projects available to test!")
                continue
                
            project_id = input("Enter Project ID to find a node: ").strip()
            if not project_id:
                print("Invalid Project ID!")
                continue
                
            # First get a node ID from the project
            api_url = f"{get_api_base_url()}/api/projects/{project_id}/versions"
            print(f"Fetching versions for project {project_id}...")
            response = test_endpoint(api_url)
            
            # For simplicity, we'll just ask for a node ID directly
            node_id = input("Enter Node ID to test: ").strip()
            if not node_id:
                print("Invalid Node ID!")
                continue
                
            api_url = f"{get_api_base_url()}/api/nodes/{node_id}"
            print(f"\nTesting endpoint: {api_url}")
            response = test_endpoint(api_url)
            print("Response:")
            print("-" * 30)
            print(response)
            
        elif choice == '8':
            print("Goodbye! 👋")
            break
            
        else:
            print("Invalid choice! Please enter 1, 2, 3, 4, 5, 6, 7, or 8.")

if __name__ == "__main__":
    main()